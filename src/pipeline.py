"""Orchestrator pipeline bringing all modular components together with granular CLI flags."""
import argparse
import logging
import sys
from typing import List, Optional
from src.cache import load_raw_cache, save_raw_cache
from src.classifier import TrendClassifier
from src.matcher import TrendMatcher
from src.models import RawItem
from src.sheets import SheetsClient
from src.sources.base import BaseSource
from src.sources.rss import EditorialRSSSource
from src.sources.spotify import SpotifyKworbSource
from src.sources.tiktok import TikTokApifySource
from src.sources.youtube import YouTubeSource

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("TrendPipeline")

SOURCES_MAP = {
    "tiktok": TikTokApifySource,
    "youtube": YouTubeSource,
    "spotify": SpotifyKworbSource,
    "rss": EditorialRSSSource,
}

def collect_raw_items(
    selected_source: Optional[str] = None,
    refresh_cache: bool = False,
    classify_only: bool = False,
) -> List[RawItem]:
    """Ingests raw trend items with caching and source isolation."""
    # If classify-only mode, pull strictly from existing disk cache
    if classify_only:
        cached = load_raw_cache(ttl_hours=9999.0)
        if cached:
            logger.info(f"Running in --classify-only mode. Loaded {len(cached)} items from cache.")
            return cached
        logger.error("No cache found! Run with '--scrape-only' or '--refresh-cache' first.")
        return []

    # If cache exists and no refresh was forced, load cache
    if not refresh_cache and not selected_source:
        cached = load_raw_cache()
        if cached is not None:
            return cached

    logger.info("--- Starting Multi-Source Ingestion ---")
    items: List[RawItem] = []

    # Determine which sources to scrape
    if selected_source:
        source_key = selected_source.lower()
        if source_key not in SOURCES_MAP:
            logger.error(f"Unknown source '{selected_source}'. Choose from: {list(SOURCES_MAP.keys())}")
            return []
        active_sources = [SOURCES_MAP[source_key]()]
    else:
        active_sources = [cls() for cls in SOURCES_MAP.values()]

    for source in active_sources:
        logger.info(f"Collecting from: {source.name}...")
        items.extend(source.fetch())

    logger.info(f"Total raw items collected: {len(items)}")

    # Always save cache so --source tiktok --scrape-only works
    if items:
        save_raw_cache(items)

    return items

def run_pipeline(
    dry_run: bool = False,
    refresh_cache: bool = False,
    scrape_only: bool = False,
    classify_only: bool = False,
    selected_source: Optional[str] = None,
) -> None:
    logger.info(f"=== Starting Trend Curation Pipeline (dry_run={dry_run}) ===")

    # 1. Ingestion Phase
    raw_items = collect_raw_items(
        selected_source=selected_source,
        refresh_cache=refresh_cache,
        classify_only=classify_only,
    )

    if scrape_only:
        logger.info(f"Scrape-only flag active. Successfully saved {len(raw_items)} items to cache.")
        return

    if not raw_items:
        logger.warning("No items available to classify. Pipeline exiting.")
        return

    # 2. Gemini Classification Phase
    classifier = TrendClassifier()
    extracted_trends = classifier.classify_chunks(raw_items)

    # 3. Google Sheets Read, Deduplication & Roster Match Phase
    sheets = SheetsClient()
    existing_trends = sheets.get_sheet_values("Trend library")
    artist_roster = sheets.get_sheet_values("Artist roster")
    send_log = sheets.get_sheet_values("Send log")

    prepared_trends = TrendMatcher.match_and_deduplicate(
        trends=extracted_trends,
        existing_rows=existing_trends,
        artist_rows=artist_roster,
        send_log_rows=send_log,
    )

    # 4. Atomic Write Phase
    sheets.append_trends(prepared_trends, dry_run=dry_run)
    logger.info("=== Trend Curation Pipeline Finished Successfully ===")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automated Music Trend Curation Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Simulate execution without modifying Google Sheets.")
    parser.add_argument("--refresh-cache", action="store_true", help="Force new API requests and overwrite disk cache.")
    parser.add_argument("--scrape-only", action="store_true", help="Scrape platforms and cache to disk without calling Gemini or Sheets.")
    parser.add_argument("--classify-only", action="store_true", help="Load cached items and run Gemini + Sheets without scraping.")
    parser.add_argument("--source", type=str, default=None, help="Scrape a single source only (tiktok, youtube, spotify, rss).")
    args = parser.parse_args()

    run_pipeline(
        dry_run=args.dry_run,
        refresh_cache=args.refresh_cache,
        scrape_only=args.scrape_only,
        classify_only=args.classify_only,
        selected_source=args.source,
    )