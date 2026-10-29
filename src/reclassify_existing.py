"""One-off audit script to reclassify, personalize with individual briefs, and prune existing trends."""

import argparse
import concurrent.futures
import json
import logging
import os
import random
import re
import sys
import time
from typing import Any, Dict, List, Literal, Optional
from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field
from src.artist_profiler import format_roster_context_for_llm, load_artist_profiles
from src.config import (
    GEMINI_API_KEYS,
    GEMINI_MODEL,
    GEMINI_TIMEOUT_SECONDS,
)
from src.models import ArtistJustification
from src.sheets import SheetsClient
from src.tracker import TrendLifecycleTracker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("TrendPipeline.Reclassifier")

EXPLICIT_STATUS_LITERAL = Literal[
    "🚀 Surging",
    "🔥 Peak",
    "📉 Cooling",
    "💤 Stale",
    "🌲 Evergreen",
    "💡 Idea",
]


class AuditedTrendDecision(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    trend_id: str = Field(..., description="The ID of the trend (e.g. 'T020').")
    keep: bool = Field(
        ...,
        description="True if this trend is genuinely strategic and actionable for at least one roster artist. False if generic, gimmicky, or irrelevant.",
    )
    rejection_reason: str = Field(
        "",
        description="If keep is False, provide a 1-sentence reason why it is being pruned.",
    )
    matched_artists: List[str] = Field(
        default_factory=list,
        alias="target_artists",
        description="Specific roster artist name(s) who should execute this trend (e.g. ['Nick Marcus', 'Allira']).",
    )
    status: EXPLICIT_STATUS_LITERAL = Field(
        ...,
        description="Calibrated status: '🌲 Evergreen' (foundational craft template), 'Idea' (YouTube/topic), '🚀 Surging' (<8d), '🔥 Peak' (8-14d), or '📉 Cooling' (15-27d).",
    )
    how_to_execute: str = Field(
        ...,
        alias="how_to_execute_it",
        description="Refined 1-sentence tactical prompt telling the assigned artist exactly what to film.",
    )
    personalized_justifications: List[ArtistJustification] = Field(
        default_factory=list,
        description="List of individualized justifications for each matched artist. NEVER mention other artists in a block.",
    )


class ReclassificationAuditBatch(BaseModel):
    audited_trends: List[AuditedTrendDecision] = Field(default_factory=list)


class ExistingTrendReclassifier:

    def __init__(self, no_timeout: bool = False):
        if not GEMINI_API_KEYS:
            raise ValueError("No Gemini API keys found in environment variables!")
        self.api_keys = GEMINI_API_KEYS
        self.current_key_idx = 0
        self.client = self._init_client(self.api_keys[self.current_key_idx])
        self.sheets = SheetsClient()
        self.artist_profiles = load_artist_profiles(sheets_client=self.sheets)
        self.no_timeout = no_timeout
        self.timeout_val = None if no_timeout else GEMINI_TIMEOUT_SECONDS
        logger.info(
            f"Initialized Reclassifier with {len(self.api_keys)} API key(s) "
            f"and model '{GEMINI_MODEL}'."
        )

    def _init_client(self, api_key: str) -> genai.Client:
        return genai.Client(api_key=api_key)

    def _rotate_key(self) -> bool:
        if self.current_key_idx + 1 < len(self.api_keys):
            self.current_key_idx += 1
            next_key = self.api_keys[self.current_key_idx]
            self.client = self._init_client(next_key)
            masked = f"{next_key[:6]}...{next_key[-4:]}"
            logger.warning(
                f"[KEY ROTATION] Switched to Key #{self.current_key_idx + 1} ({masked})"
            )
            return True
        logger.warning(
            "[KEY ROTATION WRAP] Reached end of key list. Cycling back to Key #1."
        )
        self.current_key_idx = 0
        self.client = self._init_client(self.api_keys[0])
        return False

    def run_audit(self, dry_run: bool = False) -> None:
        logger.info("=== Starting One-Off Audit & Personalization of Trends ===")
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
            f"Found {len(manual_rows)} manual trends (will keep untouched) "
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
            "   - 'matched_artists': Name 1 to 3 specific artists from our roster who should execute this.\n"
            "   - 'personalized_justifications': Return a list of objects containing 'artist_name' and 'justification' "
            "     for EACH artist in 'matched_artists'.\n"
            "     PRIVACY RULE: Speak directly to that artist ONLY. NEVER mention or compare any other roster artist in their block.\n"
            "   - 'status': Assign accurately. YouTube links MUST be '💡 Idea'. Only foundational craft templates get '🌲 Evergreen'.\n"
            "   - 'how_to_execute': Refine the prompt to suit the assigned artist.\n\n"
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
        logger.info(
            f"Sending {len(automated_rows)} trends to Gemini for audit (Timeout: {timeout_desc})..."
        )

        max_attempts = max(4, len(self.api_keys) * 2)
        attempt = 0
        response = None

        while attempt < max_attempts:
            attempt += 1
            logger.info(
                f"Calling {GEMINI_MODEL} (Attempt {attempt}/{max_attempts}, "
                f"Key #{self.current_key_idx + 1}/{len(self.api_keys)})..."
            )

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
                if response and response.text:
                    logger.info("Successfully received audit response from Gemini.")
                    break
            except concurrent.futures.TimeoutError:
                executor.shutdown(wait=False, cancel_futures=True)
                logger.warning(
                    f"{GEMINI_MODEL} timed out after {self.timeout_val}s on Key #{self.current_key_idx + 1}."
                )
                self._rotate_key()
                continue
            except Exception as exc:
                executor.shutdown(wait=False, cancel_futures=True)
                err_str = str(exc)
                logger.warning(f"{GEMINI_MODEL} audit error on attempt {attempt}: {err_str}")

                # 1. Quota Exhaustion (429) -> Rotate API key immediately
                if any(c in err_str.lower() for c in ["429", "resource_exhausted", "quota"]):
                    logger.info("Quota limit reached. Rotating to next API key...")
                    self._rotate_key()
                    time.sleep(1.5)
                    continue

                # 2. Server Capacity / Overloaded (503 / 529 / unavailable / overloaded)
                if any(
                    c in err_str.lower()
                    for c in [
                        "503",
                        "529",
                        "unavailable",
                        "overloaded",
                        "disconnected",
                        "connection",
                    ]
                ):
                    self._rotate_key()
                    backoff = (12.0 * attempt) + random.uniform(1.0, 4.0)
                    logger.info(
                        f"Capacity/overload spike (503/529) on {GEMINI_MODEL}. "
                        f"Rotated key and pacing backoff for {backoff:.1f}s to let cluster clear buffer..."
                    )
                    time.sleep(backoff)
                    continue

                time.sleep(3.0)

        if not response or not response.text:
            logger.error(
                f"Unified reclassification audit failed across all {max_attempts} attempts."
            )
            return

        batch_result = ReclassificationAuditBatch.model_validate_json(response.text)
        decision_map = {item.trend_id: item for item in batch_result.audited_trends}

        # Build canonical roster name mapping
        artist_sheet_rows = self.sheets.get_sheet_values("Artist roster")
        roster_map = {}
        if len(artist_sheet_rows) >= 4:
            for row in artist_sheet_rows[4:]:
                if len(row) >= 2 and row[1].strip():
                    roster_map[row[1].strip().lower()] = row[1].strip()

        kept_automated_rows: List[List[str]] = []
        pruned_count = 0
        kept_count = 0

        print("\n" + "=" * 90)
        print("A&R AUDIT & PERSONALIZATION RESULTS:")
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
            # Reconcile casing
            matched_canonical = []
            for a in decision.matched_artists:
                if a.strip().lower() in roster_map:
                    matched_canonical.append(roster_map[a.strip().lower()])

            deduped_artists = list(dict.fromkeys(matched_canonical))
            matched_names = "; ".join(deduped_artists)
            matched_count = len(deduped_artists)

            clean_justifications = {}
            for a_name in deduped_artists:
                just = None
                for item in decision.personalized_justifications:
                    if item.artist_name.strip().lower() == a_name.lower():
                        just = item.justification.strip()
                        break
                clean_justifications[a_name] = just or (
                    "This trend provides an authentic promotional angle for your current release cycle."
                )

            serialized_json = json.dumps(clean_justifications, ensure_ascii=False)

            # 16-column format (Col M blank, Col P JSON)
            updated_row = [
                r[0],  # Col A: ID
                r[1],  # Col B: Trend name
                r[2],  # Col C: Trend summary
                r[3],  # Col D: Platform
                r[4],  # Col E: Type
                r[5],  # Col F: Genres
                r[6],  # Col G: Date spotted
                decision.status,  # Col H: Status
                r[8],  # Col I: Example link
                decision.how_to_execute,  # Col J: How to execute it
                r[10] if len(r) > 10 else "",  # Col K: Hashtags
                r[11] if len(r) > 11 else "Automated Pipeline",  # Col L: Source
                "",  # Col M: Notes (STRICTLY BLANK)
                matched_count,  # Col N: Matched Artists Count
                matched_names,  # Col O: Matched Artists Names
                serialized_json,  # Col P: Personalised Justifications
            ]
            kept_automated_rows.append(updated_row)
            print(f"✅ [KEPT & PERSONALIZED] {t_id}: '{r[1][:30]}' -> Artists ({matched_count}): {matched_names}")
            print(f"    Status: {decision.status} | Action: {decision.how_to_execute}")
            print(f"    Col P (JSON): {serialized_json[:110]}...")
            print("-" * 90)

        print(
            f"\nAudit Summary: Total Automated: {len(automated_rows)} | "
            f"Kept: {kept_count} | Pruned: {pruned_count}"
        )

        if dry_run:
            logger.info("[DRY RUN] Skipping live Google Sheets modifications.")
            return

        self.sheets.ensure_column_p_header()

        # Re-pad manual rows to 16 columns if needed
        padded_manual_rows = []
        for mr in manual_rows:
            row_copy = list(mr)
            while len(row_copy) < 16:
                row_copy.append("")
            padded_manual_rows.append(row_copy)

        final_data_rows = padded_manual_rows + kept_automated_rows
        ws = self.sheets.spreadsheet.worksheet("Trend library")

        start_row = 5
        end_row = start_row + len(final_data_rows) - 1
        update_range = f"A{start_row}:P{end_row}"

        logger.info(f"Writing {len(final_data_rows)} rows to 'Trend library' ({update_range})...")
        ws.update(range_name=update_range, values=final_data_rows)

        # Clear obsolete trailing rows across Columns A to P
        old_total_rows = len(active_rows)
        if old_total_rows > len(final_data_rows):
            excess_rows = old_total_rows - len(final_data_rows) + 15
            wipe_start = end_row + 1
            wipe_end = end_row + excess_rows
            wipe_range = f"A{wipe_start}:P{wipe_end}"
            empty_block = [[""] * 16 for _ in range(excess_rows)]
            logger.info(f"Cleaning up {excess_rows} obsolete rows from range {wipe_range}...")
            ws.update(range_name=wipe_range, values=empty_block)

        # Post-audit lifecycle check
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