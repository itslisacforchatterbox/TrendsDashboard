"""Orchestrator pipeline bringing all modular trend curation components together.

Supports granular execution modes:
  - Full automated end-to-end run (Ingest -> Classify -> Match -> Sync -> Lifecycle Audit)
  - --track-lifecycle : Audits and updates Column H statuses (Surging/Peak/Cooling/Stale)
  - --scrape-only      : Ingests raw platform items to .cache without calling Gemini or Sheets
  - --classify-only    : Evaluates cached raw items via Gemini without scraping
  - --source [name]    : Scrapes an isolated source (tiktok, youtube, spotify, rss)
  - --dry-run          : Simulates execution without modifying Google Sheets
  - --refresh-cache    : Bypasses local disk cache and forces fresh network fetches
"""

import argparse
import logging
import sys
from typing import Dict, List, Optional, Type
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
from src.tracker import TrendLifecycleTracker

# ------------------------------------------------------------------------------
# Logging Setup
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("TrendPipeline")

# ------------------------------------------------------------------------------
# Source Channel Registry
# ------------------------------------------------------------------------------
SOURCES_MAP: Dict[str, Type[BaseSource]] = {
    "tiktok": TikTokApifySource,
    "youtube": YouTubeSource,
    "spotify": SpotifyKworbSource,
    "rss": EditorialRSSSource,
}


def get_registered_sources() -> List[BaseSource]:
    """Instantiates all configured ingestion source channels."""
    return [cls() for cls in SOURCES_MAP.values()]


# ------------------------------------------------------------------------------
# Ingestion Controller (With Caching and Source Isolation)
# ------------------------------------------------------------------------------
def collect_raw_items(
    selected_source: Optional[str] = None,
    refresh_cache: bool = False,
    classify_only: bool = False,
) -> List[RawItem]:
    """Ingests raw trend items with caching and optional single-source filtering."""
    # If running in classify-only mode, pull strictly from existing disk cache
    if classify_only:
        cached = load_raw_cache(ttl_hours=9999.0)
        if cached:
            logger.info(
                f"[CLASSIFY-ONLY] Loaded {len(cached)} raw items from disk cache."
            )
            return cached
        logger.error(
            "No cache file found! Run with '--scrape-only' or '--refresh-cache' first."
        )
        return []

    # If cache exists, is fresh, and no source or refresh was requested, load it
    if not refresh_cache and not selected_source:
        cached = load_raw_cache()
        if cached is not None:
            return cached

    logger.info("--- Starting Multi-Source Ingestion ---")
    items: List[RawItem] = []

    # Determine which sources to scrape
    if selected_source:
        source_key = selected_source.lower().strip()
        if source_key not in SOURCES_MAP:
            logger.error(
                f"Unknown source '{selected_source}'. Choose from: {list(SOURCES_MAP.keys())}"
            )
            return []
        active_sources = [SOURCES_MAP[source_key]()]
    else:
        active_sources = get_registered_sources()

    for source in active_sources:
        logger.info(f"Collecting from: {source.name}...")
        try:
            fetched_items = source.fetch()
            items.extend(fetched_items)
            logger.info(f"Collected {len(fetched_items)} items from {source.name}.")
        except Exception as exc:
            logger.error(f"Error fetching from source '{source.name}': {exc}")

    logger.info(f"Total raw items collected: {len(items)}")

    # Always persist fetched items to cache (preserves Apify credits and API limits)
    if items:
        save_raw_cache(items)

    return items


# ------------------------------------------------------------------------------
# Orchestrator
# ------------------------------------------------------------------------------
def run_pipeline(
    dry_run: bool = False,
    refresh_cache: bool = False,
    scrape_only: bool = False,
    classify_only: bool = False,
    selected_source: Optional[str] = None,
    track_lifecycle: bool = False,
) -> None:
    """Coordinates ingestion, AI classification, matching, syncing, and lifecycle tracking."""
    logger.info(f"=== Starting Trend Curation Pipeline (dry_run={dry_run}) ===")

    # --------------------------------------------------------------------------
    # Mode A: Dedicated Lifecycle Audit Only
    # --------------------------------------------------------------------------
    if track_lifecycle:
        logger.info("Lifecycle tracking flag active. Auditing sheet records...")
        tracker = TrendLifecycleTracker()
        tracker.audit_and_update_lifecycle(dry_run=dry_run)
        logger.info("=== Lifecycle Tracking Audit Finished Successfully ===")
        return

    # --------------------------------------------------------------------------
    # Stage 1: Ingestion
    # --------------------------------------------------------------------------
    raw_items = collect_raw_items(
        selected_source=selected_source,
        refresh_cache=refresh_cache,
        classify_only=classify_only,
    )

    if scrape_only:
        logger.info(
            f"[SCRAPE-ONLY] Finished ingestion. Cached {len(raw_items)} items to disk."
        )
        return

    if not raw_items:
        logger.warning("No raw items available for processing. Pipeline exiting.")
        return

    # --------------------------------------------------------------------------
    # Stage 2: AI Classification (Single-Call Unified Prompt with Key Rotation)
    # --------------------------------------------------------------------------
    logger.info("--- Starting Structured AI Classification ---")
    classifier = TrendClassifier()
    extracted_trends = classifier.classify_chunks(raw_items)

    if not extracted_trends:
        logger.warning(
            "No trends were extracted by the classifier. Pipeline exiting."
        )
        return

    # --------------------------------------------------------------------------
    # Stage 3: Google Sheets Read, Deduplication & Artist Matching
    # --------------------------------------------------------------------------
    logger.info("--- Starting Deduplication & Artist Roster Matching ---")
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

    # --------------------------------------------------------------------------
    # Stage 4: Atomic Sync to Google Sheets
    # --------------------------------------------------------------------------
    logger.info("--- Starting Atomic Sync to Google Sheets ---")
    sheets.append_trends(prepared_trends, dry_run=dry_run)

    # --------------------------------------------------------------------------
    # Stage 5: Post-Run Lifecycle Tracking Audit
    # --------------------------------------------------------------------------
    logger.info("--- Starting Post-Run Lifecycle Status Audit ---")
    tracker = TrendLifecycleTracker(sheets_client=sheets)
    tracker.audit_and_update_lifecycle(dry_run=dry_run)

    logger.info("=== Trend Curation Pipeline Finished Successfully ===")


# ------------------------------------------------------------------------------
# CLI Entry Point
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Automated Music Trend Curation & Lifecycle Pipeline"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate execution without modifying Google Sheets.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Bypass disk cache, force fresh network scrapes, and overwrite cache.",
    )
    parser.add_argument(
        "--scrape-only",
        action="store_true",
        help="Scrape platforms and cache items without calling Gemini or modifying Sheets.",
    )
    parser.add_argument(
        "--classify-only",
        action="store_true",
        help="Load cached raw items and run Gemini classification + matching without re-scraping.",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Target a single source channel (tiktok, youtube, spotify, rss).",
    )
    parser.add_argument(
        "--track-lifecycle",
        action="store_true",
        help="Audit and update lifecycle statuses (Surging/Peak/Cooling/Stale) in Google Sheets without running a new scrape.",
    )

    args = parser.parse_args()

    run_pipeline(
        dry_run=args.dry_run,
        refresh_cache=args.refresh_cache,
        scrape_only=args.scrape_only,
        classify_only=args.classify_only,
        selected_source=args.source,
        track_lifecycle=args.track_lifecycle,
    )