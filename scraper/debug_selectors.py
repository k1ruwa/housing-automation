"""
Diagnostic: simulates what the main scraper does (visits search page first,
then a detail page) so we can see what the consent wall looks like.
Run: python debug_selectors.py
"""
from playwright.sync_api import sync_playwright

SEARCH_URL = "https://www.pararius.com/apartments/amsterdam"
DETAIL_URL  = "https://www.pararius.com/apartment-for-rent/amsterdam/b136c8bf/henrick-de-keijserplein"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(user_agent=UA)

    # Step 1 — load the search page (same as the scraper does first)
    print("=== Loading search page ===")
    page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=30_000)

    print("\n--- Buttons on search page ---")
    for btn in page.query_selector_all("button"):
        txt = btn.inner_text().strip()[:80]
        cls = btn.get_attribute("class") or ""
        if txt:
            print(f"  [{cls}] → '{txt}'")

    # Step 2 — navigate to a detail page (same as the scraper does next)
    print("\n=== Loading detail page ===")
    page.goto(DETAIL_URL, wait_until="domcontentloaded", timeout=30_000)

    print("\n--- Buttons on detail page ---")
    for btn in page.query_selector_all("button"):
        txt = btn.inner_text().strip()[:80]
        cls = btn.get_attribute("class") or ""
        if txt:
            print(f"  [{cls}] → '{txt}'")

    print("\n--- H1 tags on detail page ---")
    for el in page.query_selector_all("h1"):
        print(f"  [{el.get_attribute('class')}] → '{el.inner_text().strip()[:80]}'")

    browser.close()
