"""Supabase client wrapper for the scraper."""

import os
from functools import lru_cache

from supabase import create_client, Client


@lru_cache(maxsize=1)
def get_client() -> Client:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
    return create_client(url, key)


def upsert_listing(data: dict) -> bool:
    """
    Insert or update a listing row.

    Returns True if this is a brand-new listing (i.e. a row was inserted),
    False if it already existed and was updated.
    """
    client = get_client()

    # Only store raw_html on the first scrape — don't overwrite it on updates
    existing = (
        client.table("listings")
        .select("id, raw_html")
        .eq("source", data["source"])
        .eq("external_id", data["external_id"])
        .execute()
    )
    is_new = len(existing.data) == 0

    if not is_new and existing.data[0].get("raw_html"):
        # Strip raw_html so we don't overwrite the original stored copy
        data = {k: v for k, v in data.items() if k != "raw_html"}

    (
        client.table("listings")
        .upsert(data, on_conflict="source,external_id")
        .execute()
    )
    return is_new


def get_enabled_sources() -> list[dict]:
    """Return all sources where is_enabled = true."""
    client = get_client()
    result = client.table("sources").select("*").eq("is_enabled", True).execute()
    return result.data


def mark_source_scraped(source_name: str) -> None:
    """Update last_scraped_at for a source."""
    from datetime import datetime, timezone

    client = get_client()
    (
        client.table("sources")
        .update({"last_scraped_at": datetime.now(timezone.utc).isoformat()})
        .eq("name", source_name)
        .execute()
    )
