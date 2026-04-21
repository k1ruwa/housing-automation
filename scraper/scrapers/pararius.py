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
    Pull the Pararius listing ID from a URL.

    e.g. /apartment-for-rent/amsterdam/PR00012345678/...
         → PR00012345678
    """
    match = re.search(r"/(PR\d+)", url)
    if not match:
        raise ValueError(f"Cannot extract external_id from URL: {url}")
    return match.group(1)


def _parse_price(text: str) -> float | None:
    """'€ 1.950 per month' → 1950.0"""
    digits = re.sub(r"[^\d]", "", text)
    return float(digits) if digits else None


def _parse_size(text: str) -> float | None:
    """'75 m²' → 75.0"""
    match = re.search(r"(\d+(?:[.,]\d+)?)", text)
    return float(match.group(1).replace(",", ".")) if match else None


def _parse_bedrooms(text: str) -> int | None:
    """'3 bedrooms' → 3"""
    match = re.search(r"(\d+)", text)
    return int(match.group(1)) if match else None


def _scrape_detail(page: Page, url: str) -> dict:
    """Fetch a single listing detail page and extract all fields."""
    page.goto(url, wait_until="domcontentloaded", timeout=30_000)
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

    title = _text("h1.listing-detail-summary__title", required=True)
    address = _text(".listing-detail-summary__address")
    neighborhood = _text(".listing-detail-summary__location")

    price_text = _text(".listing-detail-summary__price")
    price_eur = _parse_price(price_text) if price_text else None

    size_text = _text(
        ".listing-features__main-feature--surface-area .listing-features__main-feature-item"
    )
    size_m2 = _parse_size(size_text) if size_text else None

    bedrooms_text = _text(
        ".listing-features__main-feature--number-of-rooms .listing-features__main-feature-item"
    )
    bedrooms = _parse_bedrooms(bedrooms_text) if bedrooms_text else None

    available_text = _text(".listing-features__sub-description--available")
    # Normalise to YYYY-MM-DD if possible, otherwise store raw
    available_from: str | None = None
    if available_text:
        date_match = re.search(r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}-\d{2}-\d{2})", available_text)
        available_from = date_match.group(1) if date_match else available_text[:50]

    description = _text(".listing-detail-description__additional p")

    external_id = _extract_external_id(url)

    return {
        "source": "pararius",
        "external_id": external_id,
        "url": url,
        "title": title,
        "address": address,
        "neighborhood": neighborhood,
        "price_eur": price_eur,
        "size_m2": size_m2,
        "bedrooms": bedrooms,
        "available_from": available_from,
        "description": description,
        "raw_html": raw_html,
    }


def _collect_listing_urls(page: Page) -> list[str]:
    """
    Paginate the Pararius Amsterdam search results and return all listing URLs.
    """
    urls: list[str] = []
    current_url = SEARCH_URL

    while True:
        page.goto(current_url, wait_until="domcontentloaded", timeout=30_000)

        # All listing links on the results page
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

        # Next page
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
        page = context.new_page()

        listing_urls = _collect_listing_urls(page)
        print(f"[pararius] found {len(listing_urls)} listings across all pages")

        for i, url in enumerate(listing_urls, 1):
            try:
                _random_delay()
                listing = _scrape_detail(page, url)
                listings.append(listing)
                print(f"[pararius] scraped {i}/{len(listing_urls)}: {listing['external_id']}")
            except PWTimeout:
                raise RuntimeError(f"Timeout loading detail page: {url}")

        browser.close()

    return listings
