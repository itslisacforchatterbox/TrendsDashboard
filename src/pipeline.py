"""Orchestrator pipeline bringing all modular trend curation components together.

Features:
  - Multi-source ingestion (TikTok, YouTube 50, Spotify 40, RSS/Editorial)
  - Artist-tailored single-call unified Gemini extraction with 3-Gate Evergreen detection
  - Immediate auto-creation and sync of the 'Artist profiles' tab in Google Sheets
  - Dual-genre artist matching & link deduplication
  - Atomic Google Sheets synchronization
  - Stage E Post-run quantitative lifecycle status audit
  - Idempotency Gate (avoids redundant scraping on catch-up schedules)
  - Loud Failure signaling (sys.exit(1) on classification exhaustion)
  - CLI execution modes (--dry-run, --refresh-cache, --scrape-only, --classify-only, --no-timeout, --track-lifecycle, --force)
"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Type
from src.artist_profiler import ensure_artist_profiles_in_sheets
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

    if not refresh_cache and not selected_source:
        cached = load_raw_cache()
        if cached is not None:
            return cached

    logger.info("--- Starting Multi-Source Ingestion ---")
    items: List[RawItem] = []

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

    logger.info(f"Total raw items collected across sources: {len(items)}")

    if items:
        save_raw_cache(items)

    return items


# ------------------------------------------------------------------------------
# Idempotency Gate
# ------------------------------------------------------------------------------
def already_curated_today(existing_rows: List[List[str]]) -> bool:
    """Verifies whether today's quota of trends has already been synced to the sheet."""
    if len(existing_rows) < 5:
        return False

    today_str = datetime.now(timezone.utc).strftime("%d %b %Y").lower()
    today_count = 0

    for r in existing_rows[4:]:
        if len(r) > 6 and r[6].strip().lower() == today_str:
            today_count += 1

    return today_count >= 3


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
    force: bool = False,
    no_timeout: bool = False,
) -> None:
    """Coordinates ingestion, AI classification, matching, syncing, and lifecycle tracking."""
    logger.info(
        f"=== Starting Trend Curation Pipeline (dry_run={dry_run}, no_timeout={no_timeout}) ==="
    )

    # 1. Connect to Google Sheets
    sheets = SheetsClient()

    # 2. IMMEDIATE AUTO-CREATION: Ensure 'Artist profiles' tab is always present and synchronized
    if not dry_run:
        ensure_artist_profiles_in_sheets(sheets)

    # Mode A: Dedicated Lifecycle Audit Only
    if track_lifecycle:
        logger.info("Lifecycle tracking flag active. Auditing sheet records...")
        tracker = TrendLifecycleTracker(sheets_client=sheets)
        tracker.audit_and_update_lifecycle(dry_run=dry_run)
        logger.info("=== Lifecycle Tracking Audit Finished Successfully ===")
        return

    existing_trends = sheets.get_sheet_values("Trend library")

    # --------------------------------------------------------------------------
    # Idempotency Gate: Skip Gemini/scraping if today was already curated
    # --------------------------------------------------------------------------
    if not force and not scrape_only and not classify_only:
        if already_curated_today(existing_trends):
            logger.info(
                "Today's trends have ALREADY been successfully curated and cataloged. "
                "Skipping ingestion & Gemini to protect quotas. Running lifecycle audit only..."
            )
            tracker = TrendLifecycleTracker(sheets_client=sheets)
            tracker.audit_and_update_lifecycle(dry_run=dry_run)
            logger.info("=== Catch-up run completed: Idempotent skip successful ===")
            return

    # Stage 1: Ingestion
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
        logger.error("No raw items collected from sources. Exiting with failure.")
        sys.exit(1)

    # Stage 2: Artist-Tailored AI Classification
    logger.info("--- Starting Artist-Tailored AI Classification ---")
    classifier = TrendClassifier(sheets_client=sheets, no_timeout=no_timeout)
    extracted_trends = classifier.classify_chunks(raw_items)

    # Loud Failure: Signal GitHub Actions on complete classification failure
    if not extracted_trends:
        logger.error(
            "Gemini classification failed across all retries and keys! "
            "Exiting with status code 1 so GitHub Actions signals a failure."
        )
        sys.exit(1)

    # Stage 3: Matching & Personalization
    logger.info("--- Starting Personalization & Artist Roster Matching ---")
    artist_roster = sheets.get_sheet_values("Artist roster")
    send_log = sheets.get_sheet_values("Send log")

    prepared_trends = TrendMatcher.match_and_deduplicate(
        trends=extracted_trends,
        existing_rows=existing_trends,
        artist_rows=artist_roster,
        send_log_rows=send_log,
    )

    # Stage 4: Atomic Sync to Google Sheets
    logger.info("--- Starting Atomic Sync to Google Sheets ---")
    sheets.append_trends(prepared_trends, dry_run=dry_run)

    # Stage 5: Post-Run Lifecycle Status Audit
    logger.info("--- Starting Post-Run Lifecycle Status Audit ---")
    tracker = TrendLifecycleTracker(sheets_client=sheets)
    tracker.audit_and_update_lifecycle(dry_run=dry_run)

    logger.info("=== Trend Curation Pipeline Finished Successfully ===")


# ------------------------------------------------------------------------------
# CLI Entry Point
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Artist-Tailored Music Trend Curation & Lifecycle Pipeline"
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
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass the idempotency gate and run curation even if today's trends already exist in the sheet.",
    )
    parser.add_argument(
        "--no-timeout",
        action="store_true",
        help="Disable execution timeouts on Gemini generation for local runs.",
    )

    args = parser.parse_args()

    run_pipeline(
        dry_run=args.dry_run,
        refresh_cache=args.refresh_cache,
        scrape_only=args.scrape_only,
        classify_only=args.classify_only,
        selected_source=args.source,
        track_lifecycle=args.track_lifecycle,
        force=args.force,
        no_timeout=args.no_timeout,
    )