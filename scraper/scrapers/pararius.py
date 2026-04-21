"""
Pararius Amsterdam scraper.

Uses Playwright to handle the JS-rendered listing pages.
Paginates the search results, then fetches each detail page.
Fails loudly on selector mismatches — never inserts silent garbage.
"""

import random
import re
import time
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout

BASE_URL = "https://www.pararius.com"
SEARCH_URL = f"{BASE_URL}/apartments/amsterdam"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _random_delay(lo: float = 2.0, hi: float = 5.0) -> None:
    time.sleep(random.uniform(lo, hi))


def _extract_external_id(url: str) -> str:
    """
    Pull the Pararius listing ID from a URL path segment.

    e.g. /apartment-for-rent/amsterdam/b136c8bf/henrick-de-keijserplein
         → b136c8bf
    """
    # The ID is the segment after the city name — a short hex-like token
    parts = url.rstrip("/").split("/")
    # URL pattern: /apartment-for-rent/<city>/<id>/<slug>
    # city is index -3 from end when slug is present, -2 when not
    for i, part in enumerate(parts):
        if part in ("amsterdam",) and i + 1 < len(parts):
            return parts[i + 1]
    raise ValueError(f"Cannot extract external_id from URL: {url}")


def _parse_price(text: str) -> float | None:
    """'€2,995 pcm' or '€ 2.995 per month' → 2995.0"""
    digits = re.sub(r"[^\d]", "", text)
    return float(digits) if digits else None


def _parse_size(text: str) -> float | None:
    """'93 m²' → 93.0"""
    match = re.search(r"(\d+(?:[.,]\d+)?)", text)
    return float(match.group(1).replace(",", ".")) if match else None


def _parse_bedrooms(text: str) -> int | None:
    """'3 rooms' or '2' → int"""
    match = re.search(r"(\d+)", text)
    return int(match.group(1)) if match else None


def _parse_address_from_title(title: str) -> str | None:
    """
    'For rent: Flat Henrick de Keijserplein in Amsterdam' → 'Henrick de Keijserplein'
    """
    # Strip 'For rent: <type> ' prefix
    match = re.match(r"For rent:\s+\S+\s+(.+?)\s+in\s+\S.*$", title, re.IGNORECASE)
    return match.group(1).strip() if match else title


def _feature_value(page: Page, term_label: str) -> str | None:
    """
    Read a value from the listing-features key→value table by its term label.
    Pararius renders these as <dt class='listing-features__term'> / <dd> pairs.
    """
    return page.evaluate(
        """(label) => {
            const terms = document.querySelectorAll('.listing-features__term');
            for (const term of terms) {
                if (term.textContent.trim() === label) {
                    const desc = term.nextElementSibling;
                    if (!desc) return null;
                    const main = desc.querySelector('.listing-features__main-description');
                    return (main || desc).textContent.trim() || null;
                }
            }
            return null;
        }""",
        term_label,
    )


def _scrape_detail(page: Page, url: str) -> dict:
    """Fetch a single listing detail page and extract all fields."""
    page.goto(url, wait_until="domcontentloaded", timeout=30_000)

    # Wait for the title — ensures JS has rendered the key elements.
    # Timeout is generous (20s); if the title never appears the listing is
    # likely expired, removed, or behind a redirect — caller should skip it.
    try:
        page.wait_for_selector("h1.listing-detail-summary__title", timeout=20_000)
    except PWTimeout:
        raise RuntimeError(
            f"Title element never appeared on {url} — "
            "listing may be expired or removed."
        )

    raw_html = page.content()

    def _text(selector: str, required: bool = False) -> str | None:
        el = page.query_selector(selector)
        if el is None:
            if required:
                raise RuntimeError(
                    f"Required selector '{selector}' not found on {url} — "
                    "Pararius layout may have changed."
                )
            return None
        return el.inner_text().strip() or None

    title       = _text("h1.listing-detail-summary__title", required=True)
    address     = _parse_address_from_title(title) if title else None
    neighborhood = _text(".listing-detail-summary__location")

    # Price: use the more specific -main variant to avoid picking up similar-listings prices
    price_text  = _text(".listing-detail-summary__price-main")
    price_eur   = _parse_price(price_text) if price_text else None

    # Size and rooms from the illustrated features strip
    size_text   = _text(".illustrated-features__item--surface-area")
    size_m2     = _parse_size(size_text) if size_text else None

    # Prefer explicit bedroom count; fall back to total rooms
    bedrooms_raw = _feature_value(page, "Number of bedrooms")
    if bedrooms_raw:
        bedrooms = _parse_bedrooms(bedrooms_raw)
    else:
        rooms_text = _text(".illustrated-features__item--number-of-rooms")
        bedrooms   = _parse_bedrooms(rooms_text) if rooms_text else None

    # Available-from from the features key-value table
    available_raw  = _feature_value(page, "Available")
    available_from: str | None = None
    if available_raw:
        date_match = re.search(r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})", available_raw)
        available_from = date_match.group(1) if date_match else available_raw[:50]

    description = _text(".listing-detail-description__additional")

    external_id = _extract_external_id(url)

    return {
        "source":         "pararius",
        "external_id":    external_id,
        "url":            url,
        "title":          title,
        "address":        address,
        "neighborhood":   neighborhood,
        "price_eur":      price_eur,
        "size_m2":        size_m2,
        "bedrooms":       bedrooms,
        "available_from": available_from,
        "description":    description,
        "raw_html":       raw_html,
    }


def _dismiss_consent(page: Page) -> None:
    """
    Click the 'I understand' privacy dialog that Pararius shows on first visit.
    Without this the browser context has no consent cookie and detail pages
    render as blank pages.
    """
    try:
        btn = page.locator("button.button--primary", has_text="I understand").first
        if btn.count() > 0:
            btn.click(timeout=5_000)
            print("[pararius] consent dialog dismissed")
    except Exception:
        pass  # Dialog may not appear every time — safe to ignore


def _collect_listing_urls(page: Page) -> list[str]:
    """Paginate the Pararius Amsterdam search results and return all listing URLs."""
    urls: list[str] = []
    current_url = SEARCH_URL

    while True:
        page.goto(current_url, wait_until="domcontentloaded", timeout=30_000)

        # Dismiss consent dialog on first search page load
        if not urls:
            _dismiss_consent(page)

        anchors = page.query_selector_all("a.listing-search-item__link--title")
        if not anchors:
            raise RuntimeError(
                f"No listing links found on {current_url} — "
                "Pararius search page layout may have changed."
            )

        for a in anchors:
            href = a.get_attribute("href")
            if href:
                urls.append(urljoin(BASE_URL, href))

        next_btn = page.query_selector("a[rel='next']")
        if not next_btn:
            break

        next_href = next_btn.get_attribute("href")
        if not next_href:
            break

        current_url = urljoin(BASE_URL, next_href)
        _random_delay()

    return urls


def scrape() -> list[dict]:
    """
    Entry point: scrape all active Pararius Amsterdam listings.
    Returns a list of listing dicts ready for db.upsert_listing().
    """
    listings: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT)
        page    = context.new_page()

        listing_urls = _collect_listing_urls(page)
        print(f"[pararius] found {len(listing_urls)} listings across all pages")

        failed = 0
        for i, url in enumerate(listing_urls, 1):
            try:
                _random_delay()
                listing = _scrape_detail(page, url)
                listings.append(listing)
                print(f"[pararius] scraped {i}/{len(listing_urls)}: {listing['external_id']}")
            except Exception as e:
                failed += 1
                print(f"[pararius] SKIP {i}/{len(listing_urls)} ({url}): {e}")
                # If more than half the listings are failing something is
                # structurally wrong — abort so the caller sends an error alert.
                if failed > len(listing_urls) // 2:
                    raise RuntimeError(
                        f"Too many failures ({failed}/{i}) — Pararius layout "
                        "may have changed or bot-detection kicked in."
                    )

        browser.close()

    return listings
