"""Trend Lifecycle Tracker: Quantitative delta evaluation, 3-Layer Evergreen protection, and table boundary safety."""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import requests
from src.config import CACHE_DIR, YOUTUBE_API_KEY
from src.sheets import SheetsClient

logger = logging.getLogger("TrendPipeline.Tracker")

SNAPSHOT_CACHE_FILE = os.path.join(CACHE_DIR, "metric_snapshots.json")


def parse_spotted_date(date_str: str) -> Optional[datetime]:
    if not date_str or not date_str.strip():
        return None
    s = date_str.strip()
    formats = ["%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%m/%d/%Y", "%Y/%m/%d"]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def extract_youtube_id(url: str) -> Optional[str]:
    if not url:
        return None
    match = re.search(r"(?:v=|\/|embed\/|watch\?v=)([0-9A-Za-z_-]{11})", url)
    return match.group(1) if match else None


def load_snapshots() -> Dict[str, Dict[str, Any]]:
    if not os.path.exists(SNAPSHOT_CACHE_FILE):
        return {}
    try:
        with open(SNAPSHOT_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning(f"Could not load metric snapshots: {exc}")
        return {}


def save_snapshots(snapshots: Dict[str, Dict[str, Any]]) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        with open(SNAPSHOT_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(snapshots, f, indent=2)
    except Exception as exc:
        logger.warning(f"Failed to save metric snapshots: {exc}")


class TrendLifecycleTracker:

    def __init__(self, sheets_client: Optional[SheetsClient] = None):
        self.sheets = sheets_client or SheetsClient()
        self.snapshots = load_snapshots()

    def batch_fetch_youtube_views(self, video_ids: List[str]) -> Dict[str, int]:
        if not video_ids or not YOUTUBE_API_KEY:
            return {}

        results: Dict[str, int] = {}
        for i in range(0, len(video_ids), 50):
            chunk = video_ids[i : i + 50]
            url = "https://www.googleapis.com/youtube/v3/videos"
            params = {
                "part": "statistics",
                "id": ",".join(chunk),
                "key": YOUTUBE_API_KEY,
            }
            try:
                resp = requests.get(url, params=params, timeout=15)
                if resp.status_code == 200:
                    for it in resp.json().get("items", []):
                        v_id = it.get("id")
                        v_count = int(
                            it.get("statistics", {}).get("viewCount", 0)
                        )
                        results[v_id] = v_count
            except Exception as exc:
                logger.error(f"YouTube batch API error: {exc}")

        return results

    def audit_and_update_lifecycle(
        self, dry_run: bool = False
    ) -> List[Tuple[str, str, str, str]]:
        logger.info("--- Starting Quantitative Trend Lifecycle Audit ---")
        rows = self.sheets.get_sheet_values("Trend library")

        if len(rows) < 5:
            logger.info("No rows to audit.")
            return []

        # Read strictly contiguous active table rows (stops at first empty row/non-ID)
        active_table_rows: List[List[str]] = []
        for r in rows[4:]:
            if not r or not r[0].strip():
                break
            if not re.match(r"^T\d{3,}$", r[0].strip()):
                break
            active_table_rows.append(r)

        logger.info(
            f"Auditing {len(active_table_rows)} active rows in 'Trend library'..."
        )

        today = datetime.now(timezone.utc)
        now_ts = time.time()

        # Batch query YouTube views
        yt_video_map: Dict[str, str] = {}
        for r in active_table_rows:
            if len(r) > 8:
                t_id = r[0].strip()
                link = r[8].strip()
                v_id = extract_youtube_id(link)
                if v_id:
                    yt_video_map[t_id] = v_id

        live_yt_views = self.batch_fetch_youtube_views(
            list(yt_video_map.values())
        )

        updated_statuses: List[List[str]] = []
        change_summary: List[Tuple[str, str, str, str]] = []

        for r in active_table_rows:
            t_id = r[0].strip()
            name = r[1].strip() if len(r) > 1 else ""
            platform = r[3].strip() if len(r) > 3 else ""
            trend_type = r[4].strip() if len(r) > 4 else ""
            date_spotted_str = r[6].strip() if len(r) > 6 else ""
            old_status = r[7].strip() if len(r) > 7 else "Active"
            link = r[8].strip() if len(r) > 8 else ""
            source_col = r[11].strip().lower() if len(r) > 11 else ""
            notes_col = r[12].strip().lower() if len(r) > 12 else ""

            spotted_dt = parse_spotted_date(date_spotted_str)
            age_days = (today - spotted_dt).days if spotted_dt else 14

            # ------------------------------------------------------------------
            # Layer 1: Structural & Curation Override for Evergreen Formats
            # ------------------------------------------------------------------
            # Exempt from calendar and velocity decay
            is_evergreen = (
                old_status == "💡 Evergreen"
                or "evergreen" in source_col
                or "evergreen" in notes_col
            )

            if is_evergreen:
                new_status = "💡 Evergreen"
                updated_statuses.append([new_status])
                if new_status != old_status:
                    change_summary.append((t_id, name, old_status, new_status))
                continue

            # ------------------------------------------------------------------
            # Layer 2: YouTube-Sourced Trends & Topics (Creative Ideas, 28-day expiration)
            # ------------------------------------------------------------------
            is_youtube_link = (
                "youtube.com" in link.lower() or "youtu.be" in link.lower()
            )
            is_topical_idea = (
                is_youtube_link
                or trend_type.lower() == "topic"
                or platform.lower() == "youtube"
                or old_status == "Idea"
            )

            if is_topical_idea:
                new_status = "💤 Stale" if age_days >= 28 else "Idea"
                updated_statuses.append([new_status])
                if new_status != old_status:
                    change_summary.append((t_id, name, old_status, new_status))
                continue

            # ------------------------------------------------------------------
            # Layer 3: Short-Form Audio Lifecycle (TikTok / Spotify Charts)
            # ------------------------------------------------------------------
            # Quantitative view velocity if YouTube Shorts video link is present
            v_id = yt_video_map.get(t_id)
            current_views = live_yt_views.get(v_id) if v_id else None

            if current_views is not None and "shorts" in platform.lower():
                prev_snapshot = self.snapshots.get(t_id)
                if prev_snapshot and "views" in prev_snapshot:
                    delta_views = current_views - prev_snapshot["views"]
                    delta_hours = max(
                        1.0, (now_ts - prev_snapshot["timestamp"]) / 3600.0
                    )
                    daily_velocity = (delta_views / delta_hours) * 24.0

                    if daily_velocity >= 40_000 and age_days <= 10:
                        new_status = "🚀 Surging"
                    elif daily_velocity >= 15_000 and age_days <= 21:
                        new_status = "🔥 Peak"
                    elif age_days <= 28:
                        new_status = "📉 Cooling"
                    else:
                        new_status = "💤 Stale"
                else:
                    new_status = (
                        "🚀 Surging"
                        if age_days <= 7
                        else (
                            "🔥 Peak"
                            if age_days <= 14
                            else "📉 Cooling" if age_days <= 27 else "💤 Stale"
                        )
                    )

                self.snapshots[t_id] = {
                    "views": current_views,
                    "timestamp": now_ts,
                    "video_id": v_id,
                }
            else:
                # Standard calibrated decay for native social sounds:
                # 0-7 days: Breakout
                # 8-14 days: Saturation Peak
                # 15-27 days: Algorithmic Decay
                # 28+ days: Stale / Dead Wave
                if age_days <= 7:
                    new_status = "🚀 Surging"
                elif age_days <= 14:
                    new_status = "🔥 Peak"
                elif age_days <= 27:
                    new_status = "📉 Cooling"
                else:
                    new_status = "💤 Stale"

            updated_statuses.append([new_status])
            if new_status != old_status:
                change_summary.append((t_id, name, old_status, new_status))

        save_snapshots(self.snapshots)

        if change_summary:
            logger.info(
                f"Detected {len(change_summary)} status transitions to synchronize:"
            )
            for t_id, name, old_s, new_s in change_summary:
                logger.info(f"[{t_id}] '{name[:30]}': {old_s} -> {new_s}")

        if dry_run:
            logger.info("[DRY RUN] Skipping live Google Sheets update.")
            return change_summary

        if updated_statuses:
            ws = self.sheets.spreadsheet.worksheet("Trend library")
            end_row = 4 + len(updated_statuses)
            update_range = f"H5:H{end_row}"

            logger.info(
                f"Executing atomic batch update of Column H ({update_range})..."
            )
            ws.update(range_name=update_range, values=updated_statuses)

            # Clean up ghost cells beneath the table (e.g. wiping cell H46 and beyond)
            cleanup_range = f"H{end_row + 1}:H{end_row + 10}"
            empty_payload = [[""] for _ in range(10)]
            ws.update(range_name=cleanup_range, values=empty_payload)
            logger.info(
                f"Cleared trailing ghost cells in range {cleanup_range}."
            )
            logger.info("Lifecycle statuses successfully synchronized.")

        return change_summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    tracker = TrendLifecycleTracker()
    tracker.audit_and_update_lifecycle(dry_run=False)