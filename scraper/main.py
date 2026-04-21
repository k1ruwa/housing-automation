"""
Housing scraper — entry point.

Runs a Pararius Amsterdam scrape immediately on startup,
then repeats every SCRAPE_INTERVAL_HOURS hours via APScheduler.
"""

import os
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv

# Load .env from the same directory as this file
load_dotenv(Path(__file__).parent / ".env")

import db
import telegram
from scrapers import pararius


def run_scrape() -> None:
    print("[main] starting scrape run")
    try:
        listings = pararius.scrape()
        new_count = 0

        for listing in listings:
            is_new = db.upsert_listing(listing)
            if is_new:
                new_count += 1
                try:
                    telegram.send_alert(listing)
                except Exception as e:
                    print(f"[main] telegram alert failed for {listing['external_id']}: {e}")

        db.mark_source_scraped("pararius")
        print(f"[main] done — {len(listings)} listings scraped, {new_count} new")

    except Exception as e:
        print(f"[main] scrape failed: {e}")
        telegram.send_error("pararius scrape", e)
        raise


def main() -> None:
    interval_hours = int(os.environ.get("SCRAPE_INTERVAL_HOURS", "3"))

    # Run immediately on startup so we don't wait for the first interval
    run_scrape()

    scheduler = BlockingScheduler()
    scheduler.add_job(run_scrape, "interval", hours=interval_hours)
    print(f"[main] scheduler started — next run in {interval_hours}h")
    scheduler.start()


if __name__ == "__main__":
    main()
