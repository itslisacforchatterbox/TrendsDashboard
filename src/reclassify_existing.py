"""One-off audit script to reclassify, personalize, or prune existing 'Automated Pipeline' trends."""

import argparse
import concurrent.futures
import json
import logging
import os
import re
import sys
from typing import Any, Dict, List, Literal, Optional
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from src.artist_profiler import format_roster_context_for_llm, load_artist_profiles
from src.config import (
    GEMINI_API_KEYS,
    GEMINI_MODEL,
    GEMINI_TIMEOUT_SECONDS,
)
from src.sheets import SheetsClient
from src.tracker import TrendLifecycleTracker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("TrendPipeline.Reclassifier")

# Explicit calibrated lifecycle states (disallowing generic 'Active')
EXPLICIT_STATUS_LITERAL = Literal[
    "🚀 Surging",
    "🔥 Peak",
    "📉 Cooling",
    "💤 Stale",
    "💡 Evergreen",
    "Idea",
]


class AuditedTrendDecision(BaseModel):
    trend_id: str = Field(..., description="The ID of the trend (e.g. 'T020').")
    keep: bool = Field(
        ...,
        description="True if this trend is genuinely strategic and actionable for at least one roster artist. False if generic, gimmicky, or irrelevant.",
    )
    rejection_reason: str = Field(
        "",
        description="If keep is False, provide a 1-sentence reason why it is being pruned.",
    )
    target_artists: List[str] = Field(
        default_factory=list,
        description="Specific roster artist name(s) who should execute this trend (e.g. ['Nick Marcus', 'Allira']).",
    )
    status: EXPLICIT_STATUS_LITERAL = Field(
        ...,
        description="Must choose an explicit lifecycle state: '💡 Evergreen' (foundational craft template), 'Idea' (YouTube/topic), '🚀 Surging' (<8d old), '🔥 Peak' (8-14d), or '📉 Cooling' (15-27d). Do NOT use generic 'Active'.",
    )
    artist_fit_reasoning: str = Field(
        "",
        description="1-2 sentences explaining why this specifically fits the assigned artist's sound and aesthetic.",
    )
    how_to_execute_it: str = Field(
        ...,
        description="Refined 1-sentence tactical prompt telling the assigned artist exactly what to film.",
    )
    notes: str = Field(
        "",
        description="Refined A&R notes and strategic considerations.",
    )


class ReclassificationAuditBatch(BaseModel):
    audited_trends: List[AuditedTrendDecision] = Field(default_factory=list)


class ExistingTrendReclassifier:

    def __init__(self, no_timeout: bool = False):
        if not GEMINI_API_KEYS:
            raise ValueError("No Gemini API keys found in environment variables!")
        self.sheets = SheetsClient()
        self.client = genai.Client(api_key=GEMINI_API_KEYS[0])
        self.artist_profiles = load_artist_profiles(sheets_client=self.sheets)
        self.no_timeout = no_timeout
        self.timeout_val = None if no_timeout else GEMINI_TIMEOUT_SECONDS

    def run_audit(self, dry_run: bool = False) -> None:
        logger.info("=== Starting One-Off Audit of Automated Trends ===")
        all_rows = self.sheets.get_sheet_values("Trend library")

        if len(all_rows) < 5:
            logger.info("No rows to audit.")
            return

        active_rows: List[List[str]] = []
        for r in all_rows[4:]:
            if not r or not r[0].strip() or not re.match(r"^T\d{3,}$", r[0].strip()):
                break
            active_rows.append(r)

        manual_rows: List[List[str]] = []
        automated_rows: List[List[str]] = []

        for r in active_rows:
            source = r[11].strip().lower() if len(r) > 11 else ""
            if "automated pipeline" in source:
                automated_rows.append(r)
            else:
                manual_rows.append(r)

        logger.info(
            f"Found {len(manual_rows)} manual/curated trends (will keep untouched) "
            f"and {len(automated_rows)} 'Automated Pipeline' trends to audit."
        )

        if not automated_rows:
            logger.info("No 'Automated Pipeline' rows found to audit.")
            return

        roster_context = format_roster_context_for_llm(self.artist_profiles)
        prompt = (
            "You are an elite Record Label Head and A&R Director performing a strict catalog cleanup.\n"
            "Below is our active artist roster followed by a list of previously automated trend entries.\n\n"
            f"{roster_context}\n\n"
            "AUDIT & PRUNING INSTRUCTIONS:\n"
            "1. Evaluate each trend ruthlessly against our specific artists. If a trend is generic filler, "
            "   a low-effort meme, cosplay/trailer gimmick, or does not authentically elevate any artist on our roster, "
            "   set 'keep': false and give a concise 'rejection_reason'.\n"
            "2. If 'keep': true:\n"
            "   - 'target_artists': Must name 1 to 3 specific artists from our roster who should execute this.\n"
            "   - 'artist_fit_reasoning': Explain why this fits their current releases, vocal style, or social aesthetic.\n"
            "   - 'status': MUST be chosen from ['🚀 Surging', '🔥 Peak', '📉 Cooling', '💤 Stale', '💡 Evergreen', 'Idea']. "
            "     YouTube links MUST be 'Idea'. Only foundational craft templates (acoustic, open verse) get '💡 Evergreen'.\n"
            "   - 'how_to_execute_it': Refine the prompt to suit the assigned artist.\n\n"
            "TRENDS TO AUDIT:\n"
        )

        for r in automated_rows:
            t_id = r[0].strip()
            name = r[1].strip() if len(r) > 1 else ""
            summary = r[2].strip() if len(r) > 2 else ""
            platform = r[3].strip() if len(r) > 3 else ""
            t_type = r[4].strip() if len(r) > 4 else ""
            genres = r[5].strip() if len(r) > 5 else ""
            link = r[8].strip() if len(r) > 8 else ""
            prompt += f"[{t_id}] '{name}' | Platform: {platform} ({t_type}) | Genres: {genres} | URL: {link}\nSummary: {summary}\n\n"

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ReclassificationAuditBatch,
            temperature=0.1,
        )

        timeout_desc = "DISABLED" if self.no_timeout else f"{self.timeout_val}s"
        logger.info(f"Sending {len(automated_rows)} trends to Gemini for A&R audit (Timeout: {timeout_desc})...")

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(
            self.client.models.generate_content,
            model=GEMINI_MODEL,
            contents=prompt,
            config=config,
        )

        try:
            response = future.result(timeout=self.timeout_val)
            executor.shutdown(wait=False)
        except Exception as exc:
            executor.shutdown(wait=False, cancel_futures=True)
            logger.error(f"Gemini audit call failed: {exc}")
            return

        if not response.text:
            logger.error("Empty response received from Gemini.")
            return

        batch_result = ReclassificationAuditBatch.model_validate_json(response.text)
        decision_map = {item.trend_id: item for item in batch_result.audited_trends}

        kept_automated_rows: List[List[str]] = []
        pruned_count = 0
        kept_count = 0

        print("\n" + "=" * 90)
        print("A&R AUDIT & PRUNING RESULTS:")
        print("=" * 90)

        for r in automated_rows:
            t_id = r[0].strip()
            decision = decision_map.get(t_id)

            if not decision or not decision.keep:
                pruned_count += 1
                reason = decision.rejection_reason if decision else "No decision returned"
                print(f"❌ [PRUNED] {t_id}: '{r[1][:35]}' -> Reason: {reason}")
                continue

            kept_count += 1
            matched_names = "; ".join(decision.target_artists)
            matched_count = len(decision.target_artists)

            notes_text = r[12] if len(r) > 12 else ""
            if decision.artist_fit_reasoning:
                notes_text = f"A&R Fit: {decision.artist_fit_reasoning} | {decision.notes}" if decision.notes else f"A&R Fit: {decision.artist_fit_reasoning}"

            updated_row = [
                r[0],  # ID
                r[1],  # Trend name
                r[2],  # Trend summary
                r[3],  # Platform
                r[4],  # Type
                r[5],  # Genres
                r[6],  # Date spotted
                decision.status,  # Status (Updated & Calibrated)
                r[8],  # Example link
                decision.how_to_execute_it,  # How to execute it (Personalized)
                r[10] if len(r) > 10 else "",  # Hashtags
                r[11] if len(r) > 11 else "Automated Pipeline",  # Source
                notes_text,  # Notes (Enriched)
                matched_count,  # Matched Artists Count
                matched_names,  # Matched Artists Names
            ]
            kept_automated_rows.append(updated_row)
            print(f"✅ [KEPT & PERSONALIZED] {t_id}: '{r[1][:30]}' -> Artists ({matched_count}): {matched_names}")
            print(f"    Status: {decision.status} | Action: {decision.how_to_execute_it}")
            print(f"    Reasoning: {decision.artist_fit_reasoning}")
            print("-" * 90)

        print(f"\nAudit Summary: Total Automated: {len(automated_rows)} | Kept: {kept_count} | Pruned: {pruned_count}")

        if dry_run:
            logger.info("[DRY RUN] Skipping live Google Sheets modifications.")
            return

        # Atomic replacement
        final_data_rows = manual_rows + kept_automated_rows
        ws = self.sheets.spreadsheet.worksheet("Trend library")

        start_row = 5
        end_row = start_row + len(final_data_rows) - 1
        update_range = f"A{start_row}:O{end_row}"

        logger.info(f"Writing {len(final_data_rows)} vetted trends to 'Trend library' ({update_range})...")
        ws.update(range_name=update_range, values=final_data_rows)

        # Clear obsolete trailing rows
        old_total_rows = len(active_rows)
        if old_total_rows > len(final_data_rows):
            excess_rows = old_total_rows - len(final_data_rows) + 15
            wipe_start = end_row + 1
            wipe_end = end_row + excess_rows
            wipe_range = f"A{wipe_start}:O{wipe_end}"
            empty_block = [[""] * 15 for _ in range(excess_rows)]
            logger.info(f"Cleaning up {excess_rows} obsolete rows from range {wipe_range}...")
            ws.update(range_name=wipe_range, values=empty_block)

        # Automatically execute Stage E lifecycle audit to synchronize all velocity statuses
        logger.info("Executing post-audit lifecycle synchronization...")
        tracker = TrendLifecycleTracker(sheets_client=self.sheets)
        tracker.audit_and_update_lifecycle(dry_run=False)

        logger.info("=== Google Sheets Cleanup, Personalization, & Status Audit Finished Successfully ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit, Personalize, and Clean Automated Trends")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without modifying Google Sheets.")
    parser.add_argument("--no-timeout", action="store_true", help="Disable execution timeout for local execution.")
    args = parser.parse_args()

    reclassifier = ExistingTrendReclassifier(no_timeout=args.no_timeout)
    reclassifier.run_audit(dry_run=args.dry_run)