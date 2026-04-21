"""
Temporary diagnostic script — dumps key elements from a Pararius detail page
so we can find the correct CSS selectors.
Run: python debug_selectors.py
"""
from playwright.sync_api import sync_playwright

URL = "https://www.pararius.com/apartment-for-rent/amsterdam/b136c8bf/henrick-de-keijserplein"
UA  = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(user_agent=UA)
    page.goto(URL, wait_until="domcontentloaded", timeout=30_000)

    # Dump all h1, h2 tags
    print("=== H1/H2 tags ===")
    for tag in ["h1", "h2"]:
        els = page.query_selector_all(tag)
        for el in els:
            cls = el.get_attribute("class") or ""
            txt = el.inner_text().strip()[:80]
            print(f"  <{tag} class='{cls}'> {txt}")

    # Dump all elements whose class contains "price"
    print("\n=== Elements with 'price' in class ===")
    for el in page.query_selector_all("[class*='price']"):
        cls = el.get_attribute("class") or ""
        txt = el.inner_text().strip()[:80]
        print(f"  class='{cls}' → {txt}")

    # Dump all elements whose class contains "address" or "location"
    print("\n=== Elements with 'address'/'location' in class ===")
    for sel in ["[class*='address']", "[class*='location']"]:
        for el in page.query_selector_all(sel):
            cls = el.get_attribute("class") or ""
            txt = el.inner_text().strip()[:80]
            print(f"  class='{cls}' → {txt}")

    # Dump elements with "feature" in class (size, bedrooms etc)
    print("\n=== Elements with 'feature' in class ===")
    for el in page.query_selector_all("[class*='feature']"):
        cls = el.get_attribute("class") or ""
        txt = el.inner_text().strip()[:80]
        if txt:
            print(f"  class='{cls}' → {txt}")

    browser.close()
