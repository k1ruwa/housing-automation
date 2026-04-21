"""
Pararius Amsterdam scraper.

Search/pagination: Playwright (JS-rendered results page).
Detail pages: httpx plain HTTP GET (bypasses headless-browser fingerprinting).
"""

import random
import re
import time
from urllib.parse import urljoin

import httpx
from playwright.sync_api import sync_playwright, Page

BASE_URL   = "https://www.pararius.com"
SEARCH_URL = f"{BASE_URL}/apartments/amsterdam"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent":                USER_AGENT,
    "Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language":           "en-US,en;q=0.9,nl;q=0.8",
    "Accept-Encoding":           "gzip, deflate, br",
    "Connection":                "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest":            "document",
    "Sec-Fetch-Mode":            "navigate",
    "Sec-Fetch-Site":            "none",
    "Sec-Fetch-User":            "?1",
}


def _random_delay(lo: float = 2.0, hi: float = 5.0) -> None:
    time.sleep(random.uniform(lo, hi))


def _extract_external_id(url: str) -> str:
    """
    /apartment-for-rent/amsterdam/b136c8bf/henrick-de-keijserplein → b136c8bf
    """
    parts = url.rstrip("/").split("/")
    for i, part in enumerate(parts):
        if part == "amsterdam" and i + 1 < len(parts):
            return parts[i + 1]
    raise ValueError(f"Cannot extract external_id from URL: {url}")


def _parse_price(text: str) -> float | None:
    """'€2,995 pcm' → 2995.0"""
    digits = re.sub(r"[^\d]", "", text)
    return float(digits) if digits else None


def _parse_size(text: str) -> float | None:
    """'93 m²' → 93.0"""
    m = re.search(r"(\d+(?:[.,]\d+)?)", text)
    return float(m.group(1).replace(",", ".")) if m else None


def _parse_bedrooms(text: str) -> int | None:
    m = re.search(r"(\d+)", text)
    return int(m.group(1)) if m else None


def _parse_address_from_title(title: str) -> str | None:
    """'For rent: Flat Henrick de Keijserplein in Amsterdam' → 'Henrick de Keijserplein'"""
    m = re.match(r"For rent:\s+\S+\s+(.+?)\s+in\s+\S.*$", title, re.IGNORECASE)
    return m.group(1).strip() if m else title


def _html_text(html: str, pattern: str) -> str | None:
    """Extract inner text using a regex on raw HTML, stripping tags."""
    m = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
    if not m:
        return None
    raw = m.group(1)
    # Strip HTML tags and decode basic entities
    text = re.sub(r"<[^>]+>", " ", raw)
    text = text.replace("&amp;", "&").replace("&nbsp;", " ").replace("&#39;", "'")
    return re.sub(r"\s+", " ", text).strip() or None


def _feature_value_html(html: str, term_label: str) -> str | None:
    """
    Find a value in the listing-features key→value table by term label.
    Pararius SSR HTML pattern:
      <dt class='listing-features__term'>Available</dt>
      <dd class='listing-features__description ...'>
        <span class='listing-features__main-description'>From 15-05-2026</span>
      </dd>
    """
    # Escape the label for regex
    escaped = re.escape(term_label)
    pattern = (
        rf"listing-features__term[^>]*>\s*{escaped}\s*</\w+>"   # the <dt> with our label
        r".*?"                                                     # skip to the <dd>
        r"listing-features__main-description[^>]*>(.*?)</span>"   # the value span
    )
    return _html_text(html, pattern)


def _scrape_detail_httpx(url: str, cookies: dict[str, str] | None = None) -> dict:
    """
    Fetch a listing detail page via plain HTTP GET and parse the SSR HTML.
    Avoids all headless-browser fingerprinting that blocks Playwright after
    the first request.
    """
    resp = httpx.get(url, headers=HEADERS, cookies=cookies or {}, follow_redirects=True, timeout=20)
    if resp.status_code == 403:
        # Rate-limited — back off and retry once
        print(f"[pararius] 403 on {url}, backing off 60s …")
        time.sleep(60)
        resp = httpx.get(url, headers=HEADERS, cookies=cookies or {}, follow_redirects=True, timeout=20)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} fetching {url}")

    html = resp.text

    # Confirm this is actually a listing page
    title_raw = _html_text(html, r'<h1[^>]*listing-detail-summary__title[^>]*>(.*?)</h1>')
    if not title_raw:
        raise RuntimeError(
            f"Title not found in HTML — page may be blocked or listing removed: {url}"
        )

    title        = title_raw
    address      = _parse_address_from_title(title)
    neighborhood = _html_text(html, r'<span[^>]*listing-detail-summary__location[^>]*>(.*?)</span>')

    price_raw    = _html_text(html, r'<span[^>]*listing-detail-summary__price-main[^>]*>(.*?)</span>')
    price_eur    = _parse_price(price_raw) if price_raw else None

    size_raw     = _html_text(html, r'<li[^>]*illustrated-features__item--surface-area[^>]*>(.*?)</li>')
    size_m2      = _parse_size(size_raw) if size_raw else None

    bedrooms_raw = _feature_value_html(html, "Number of bedrooms")
    if bedrooms_raw:
        bedrooms = _parse_bedrooms(bedrooms_raw)
    else:
        rooms_raw = _html_text(html, r'<li[^>]*illustrated-features__item--number-of-rooms[^>]*>(.*?)</li>')
        bedrooms  = _parse_bedrooms(rooms_raw) if rooms_raw else None

    available_raw  = _feature_value_html(html, "Available")
    available_from: str | None = None
    if available_raw:
        date_m = re.search(r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})", available_raw)
        available_from = date_m.group(1) if date_m else available_raw[:50]

    description  = _html_text(html, r'<div[^>]*listing-detail-description__additional[^>]*>(.*?)</div>')
    external_id  = _extract_external_id(url)

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
        "raw_html":       html,
    }


def _collect_listing_urls(page: Page) -> tuple[list[str], dict[str, str]]:
    """
    Paginate the Pararius Amsterdam search results.
    Returns (listing_urls, cookies) — cookies are passed to httpx so detail
    page requests look like a continuation of a real browser session.
    """
    urls: list[str] = []
    current_url = SEARCH_URL

    while True:
        page.goto(current_url, wait_until="domcontentloaded", timeout=30_000)

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

    # Extract session cookies to pass to httpx requests
    raw_cookies = page.context.cookies()
    cookies = {c["name"]: c["value"] for c in raw_cookies if "pararius" in c.get("domain", "")}
    return urls, cookies


def scrape() -> list[dict]:
    """
    Entry point: scrape all active Pararius Amsterdam listings.

    - Playwright: collects listing URLs from the JS-rendered search pages
    - httpx: fetches each detail page as a plain HTTP request (no browser
      fingerprint, bypasses Pararius bot-detection that blocks headless Chrome
      after the first request)
    """
    listings: list[dict] = []

    # Phase 1 — collect listing URLs via Playwright (search pages need JS)
    # Also grab session cookies to pass to httpx so detail requests look like
    # a continuation of the same browser session.
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx     = browser.new_context(user_agent=USER_AGENT)
        page    = ctx.new_page()
        listing_urls, session_cookies = _collect_listing_urls(page)
        ctx.close()
        browser.close()

    print(f"[pararius] found {len(listing_urls)} listings, {len(session_cookies)} session cookies")

    # Phase 2 — scrape detail pages via httpx (no browser fingerprint)
    # 8-15s delay keeps us under Pararius's per-window rate limit (~15 req/min).
    # On 403, _scrape_detail_httpx backs off 60s and retries once automatically.
    failed = 0
    for i, url in enumerate(listing_urls, 1):
        try:
            _random_delay(8.0, 15.0)
            listing = _scrape_detail_httpx(url, cookies=session_cookies)
            listings.append(listing)
            print(f"[pararius] scraped {i}/{len(listing_urls)}: {listing['external_id']}")
        except Exception as e:
            failed += 1
            print(f"[pararius] SKIP {i}/{len(listing_urls)} ({url}): {e}")
            if failed > len(listing_urls) // 2:
                raise RuntimeError(
                    f"Too many failures ({failed}/{i}) — Pararius layout "
                    "may have changed or requests are being blocked."
                )

    return listings
