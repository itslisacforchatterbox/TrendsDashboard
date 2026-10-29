"""One-off script to backfill missing execution strategies and individualized artist justifications."""

import argparse
import concurrent.futures
import json
import logging
import os
import random
import re
import sys
import time
from typing import Any, Dict, List, Optional
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("TrendPipeline.Backfill")


# ------------------------------------------------------------------------------
# Pydantic Schema for Backfilling (Strict OpenAPI 3.0 Compliant)
# ------------------------------------------------------------------------------
class BackfillTrendItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    trend_id: str = Field(..., description="The ID of the trend (e.g. 'T003').")
    how_to_execute: str = Field(
        ...,
        alias="how_to_execute_it",
        description="Actionable 1-sentence tactical prompt telling the artist exactly what to film or perform.",
    )
    matched_artists: List[str] = Field(
        default_factory=list,
        alias="target_artists",
        description="List of 1 to 3 specific roster artist names who should execute this trend.",
    )
    personalized_justifications: List[ArtistJustification] = Field(
        default_factory=list,
        description="List of individualized justifications for each matched artist. NEVER mention other artists in a block.",
    )


class BackfillBatchResponse(BaseModel):
    items: List[BackfillTrendItem] = Field(default_factory=list)


# ------------------------------------------------------------------------------
# Backfill Engine
# ------------------------------------------------------------------------------
class TrendJustificationBackfiller:

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
            f"Initialized Backfiller with {len(self.api_keys)} API key(s) "
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

    def run_backfill(self, dry_run: bool = False) -> None:
        logger.info("=== Starting Backfill of Missing Strategies & Justifications ===")
        all_rows = self.sheets.get_sheet_values("Trend library")

        if len(all_rows) < 5:
            logger.info("No rows found in 'Trend library'.")
            return

        active_rows: List[List[str]] = []
        for r in all_rows[4:]:
            if not r or not r[0].strip() or not re.match(r"^T\d{3,}$", r[0].strip()):
                break
            active_rows.append(r)

        logger.info(f"Loaded {len(active_rows)} active trend rows from sheet.")

        # Identify rows needing strategy (Col J) or justifications (Col P)
        rows_needing_backfill: List[List[str]] = []
        for r in active_rows:
            strategy = r[9].strip() if len(r) > 9 else ""
            justifications_json = r[15].strip() if len(r) > 15 else ""

            # Needs backfill if strategy is blank, or Col P is blank or empty JSON "{}"
            if not strategy or not justifications_json or justifications_json in ["{}", "[]"]:
                rows_needing_backfill.append(r)

        logger.info(
            f"Found {len(rows_needing_backfill)} trends requiring backfill out of {len(active_rows)} total rows."
        )

        if not rows_needing_backfill:
            logger.info("All trends already have strategies and individualized justifications. Nothing to do!")
            return

        # Prepare context and prompt for Gemini
        roster_context = format_roster_context_for_llm(self.artist_profiles)
        prompt = (
            "You are an elite Record Label Head and A&R Director generating missing execution briefs and private memos.\n"
            "Below is our active artist roster followed by a list of cataloged trends that need execution strategies "
            "and/or individualized artist justifications.\n\n"
            f"{roster_context}\n\n"
            "BACKFILL INSTRUCTIONS:\n"
            "1. 'how_to_execute': If the trend is missing an execution prompt, generate a direct, actionable 1-sentence prompt "
            "   telling the artist what to film or perform. If an execution prompt already exists, refine it to be more tactical.\n"
            "2. 'matched_artists': Assign 1 to 3 specific artists from our roster who authentically fit this trend's musicality and aesthetic.\n"
            "3. 'personalized_justifications': Return a list of items with 'artist_name' and 'justification' for EACH artist in 'matched_artists'.\n"
            "   CRITICAL PRIVACY RULE: Inside each justification, speak directly to or about that artist ONLY (e.g. 'Your smooth falsetto...'). "
            "   NEVER mention, compare, or reference any other artist from our roster in another artist's memo block.\n\n"
            "TRENDS TO BACKFILL:\n"
        )

        for r in rows_needing_backfill:
            t_id = r[0].strip()
            name = r[1].strip() if len(r) > 1 else ""
            summary = r[2].strip() if len(r) > 2 else ""
            platform = r[3].strip() if len(r) > 3 else ""
            t_type = r[4].strip() if len(r) > 4 else ""
            genres = r[5].strip() if len(r) > 5 else ""
            current_strategy = r[9].strip() if len(r) > 9 else "None"
            current_artists = r[14].strip() if len(r) > 14 else "None"
            link = r[8].strip() if len(r) > 8 else ""

            prompt += (
                f"[{t_id}] '{name}' | Platform: {platform} ({t_type}) | Genres: {genres} | URL: {link}\n"
                f"Summary: {summary}\n"
                f"Current Strategy: {current_strategy}\n"
                f"Currently Assigned: {current_artists}\n\n"
            )

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=BackfillBatchResponse,
            temperature=0.1,
        )

        timeout_desc = "DISABLED" if self.no_timeout else f"{self.timeout_val}s"
        logger.info(
            f"Sending {len(rows_needing_backfill)} trends to Gemini for backfill (Timeout: {timeout_desc})..."
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
                    logger.info("Successfully received backfill response from Gemini.")
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
                logger.warning(f"{GEMINI_MODEL} error on attempt {attempt}: {err_str}")

                if any(c in err_str.lower() for c in ["429", "resource_exhausted", "quota"]):
                    logger.info("Quota limit reached. Rotating API key...")
                    self._rotate_key()
                    time.sleep(1.5)
                    continue

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
                        f"Capacity spike (503/529) on {GEMINI_MODEL}. "
                        f"Rotated key and pacing backoff for {backoff:.1f}s..."
                    )
                    time.sleep(backoff)
                    continue

                time.sleep(3.0)

        if not response or not response.text:
            logger.error(
                f"Backfill generation failed across all {max_attempts} attempts."
            )
            return

        batch_result = BackfillBatchResponse.model_validate_json(response.text)
        backfill_map = {item.trend_id: item for item in batch_result.items}

        # Build canonical roster name mapping
        artist_sheet_rows = self.sheets.get_sheet_values("Artist roster")
        roster_map = {}
        if len(artist_sheet_rows) >= 4:
            for row in artist_sheet_rows[4:]:
                if len(row) >= 2 and row[1].strip():
                    roster_map[row[1].strip().lower()] = row[1].strip()

        print("\n" + "=" * 90)
        print("BACKFILL RESULTS PREVIEW:")
        print("=" * 90)

        # Merge backfilled data into active_rows (padded to 16 columns)
        final_rows: List[List[str]] = []
        updated_count = 0

        for r in active_rows:
            row_copy = list(r)
            while len(row_copy) < 16:
                row_copy.append("")

            t_id = row_copy[0].strip()
            item = backfill_map.get(t_id)

            if item:
                updated_count += 1
                # 1. Update strategy in Column J if previously blank or refined
                if not row_copy[9].strip() or len(row_copy[9].strip()) < 15:
                    row_copy[9] = item.how_to_execute

                # 2. Reconcile matched artists
                matched_canonical = []
                for a in item.matched_artists:
                    if a.strip().lower() in roster_map:
                        matched_canonical.append(roster_map[a.strip().lower()])

                # If no direct match found, retain existing or fall back
                if not matched_canonical and row_copy[14].strip():
                    for existing_a in row_copy[14].split(";"):
                        if existing_a.strip().lower() in roster_map:
                            matched_canonical.append(roster_map[existing_a.strip().lower()])

                deduped_artists = list(dict.fromkeys(matched_canonical))
                row_copy[13] = str(len(deduped_artists))
                row_copy[14] = "; ".join(deduped_artists)

                # 3. Build individualized justifications JSON matching exact roster casing
                clean_justifications = {}
                for a_name in deduped_artists:
                    just = None
                    for j in item.personalized_justifications:
                        if j.artist_name.strip().lower() == a_name.lower():
                            just = j.justification.strip()
                            break
                    clean_justifications[a_name] = just or (
                        "This trend aligns with your sonic identity and creative direction, "
                        "providing a strong organic discovery angle for your unreleased catalog."
                    )

                serialized_json = json.dumps(clean_justifications, ensure_ascii=False)
                row_copy[15] = serialized_json

                # Column M (Notes) is preserved as-is if manual notes exist; do NOT overwrite!
                # If automated source and no manual notes, keep blank

                print(f"✨ [BACKFILLED] {t_id}: '{row_copy[1][:30]}' -> Artists ({len(deduped_artists)}): {row_copy[14]}")
                print(f"    Strategy (Col J): {row_copy[9]}")
                print(f"    Col P (JSON):     {serialized_json[:110]}...")
                print("-" * 90)

            final_rows.append(row_copy)

        print(f"\nBackfill Complete: Updated {updated_count} trends across {len(final_rows)} total rows.")

        if dry_run:
            logger.info("[DRY RUN] Skipping live Google Sheets update.")
            return

        self.sheets.ensure_column_p_header()

        ws = self.sheets.spreadsheet.worksheet("Trend library")
        start_row = 5
        end_row = start_row + len(final_rows) - 1
        update_range = f"A{start_row}:P{end_row}"

        logger.info(f"Writing {len(final_rows)} backfilled rows to 'Trend library' ({update_range})...")
        ws.update(range_name=update_range, values=final_rows)

        logger.info("=== Backfill of Strategies & Justifications Synchronized Successfully ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill missing strategies and artist justifications")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without modifying Google Sheets.")
    parser.add_argument("--no-timeout", action="store_true", help="Disable execution timeout for local execution.")
    args = parser.parse_args()

    backfiller = TrendJustificationBackfiller(no_timeout=args.no_timeout)
    backfiller.run_backfill(dry_run=args.dry_run)