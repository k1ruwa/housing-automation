"""Telegram alert helpers for the housing scraper."""

import os
import traceback

import httpx


def _token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    return token


def _chat_id() -> str:
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not chat_id:
        raise RuntimeError("TELEGRAM_CHAT_ID is not set")
    return chat_id


def _send(text: str) -> None:
    """Send a message via the Telegram Bot API (synchronous)."""
    url = f"https://api.telegram.org/bot{_token()}/sendMessage"
    payload = {
        "chat_id": _chat_id(),
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    response = httpx.post(url, json=payload, timeout=10)
    response.raise_for_status()


def send_alert(listing: dict) -> None:
    """Send a new-listing alert."""
    price = f"€{listing['price_eur']:,.0f}/mo" if listing.get("price_eur") else "price unknown"
    size = f"{listing['size_m2']} m²" if listing.get("size_m2") else ""
    bedrooms = f"{listing['bedrooms']} br" if listing.get("bedrooms") else ""
    meta = " · ".join(filter(None, [size, bedrooms]))

    lines = [
        "🏠 <b>New listing</b>",
        "",
        f"<b>{listing.get('title') or listing.get('address') or 'Untitled'}</b>",
        f"{listing.get('neighborhood') or listing.get('address') or ''}",
        f"{price}{' · ' + meta if meta else ''}",
    ]
    if listing.get("available_from"):
        lines.append(f"Available from: {listing['available_from']}")
    lines += ["", f"<a href=\"{listing['url']}\">View listing →</a>"]

    _send("\n".join(lines))


def send_error(context: str, error: Exception) -> None:
    """Send an error alert so failures are visible without checking logs."""
    text = (
        f"⚠️ <b>Scraper error</b> [{context}]\n\n"
        f"<code>{traceback.format_exc()[-800:]}</code>"
    )
    try:
        _send(text)
    except Exception:
        # If Telegram itself is broken, don't raise — just print
        print(f"[telegram] failed to send error alert: {error}")
