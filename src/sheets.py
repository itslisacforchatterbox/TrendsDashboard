"""Google Sheets connection, automatic header initialization, and atomic batch sync via gspread."""

import json
import logging
import os
from typing import Any, Dict, List, Optional
import gspread
from google.oauth2.service_account import Credentials
from src.config import GCP_SA_CREDENTIALS, GOOGLE_SHEET_ID

logger = logging.getLogger("TrendPipeline.Sheets")


class SheetsClient:

    def __init__(self):
        if not GOOGLE_SHEET_ID:
            raise ValueError("GOOGLE_SHEET_ID environment variable is missing.")
        self.gc = self._authenticate()
        self.spreadsheet = self.gc.open_by_key(GOOGLE_SHEET_ID)

    def _authenticate(self) -> gspread.Client:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.readonly",
        ]
        if GCP_SA_CREDENTIALS.strip().startswith("{"):
            creds = Credentials.from_service_account_info(
                json.loads(GCP_SA_CREDENTIALS), scopes=scopes
            )
        elif os.path.exists(GCP_SA_CREDENTIALS):
            creds = Credentials.from_service_account_file(
                GCP_SA_CREDENTIALS, scopes=scopes
            )
        else:
            raise FileNotFoundError(
                f"Service account file not found: {GCP_SA_CREDENTIALS}"
            )
        return gspread.authorize(creds)

    def get_sheet_values(self, title: str) -> List[List[str]]:
        sheet_map = {
            ws.title.strip().lower(): ws for ws in self.spreadsheet.worksheets()
        }
        if title.lower() in sheet_map:
            return sheet_map[title.lower()].get_all_values()
        logger.warning(f"Tab '{title}' not found in spreadsheet.")
        return []

    def ensure_column_p_header(self) -> None:
        """Ensures Column P has the 'Personalised Justifications' header on Row 4."""
        try:
            ws = self.spreadsheet.worksheet("Trend library")
            val = ws.acell("P4").value
            if not val or not val.strip():
                ws.update_acell("P4", "Personalised Justifications")
                logger.info(
                    "Initialized header 'Personalised Justifications' in cell P4 of 'Trend library'."
                )
        except Exception as exc:
            logger.warning(f"Could not verify Column P header: {exc}")

    def append_trends(
        self, trends: List[Dict[str, Any]], dry_run: bool = False
    ) -> None:
        """Formats records for the 16-column schema (A to P) and appends atomically."""
        if not trends:
            logger.info("No new trends to append.")
            return

        self.ensure_column_p_header()

        # Schema: A to P (16 Columns)
        # [ID, Trend name, Trend summary, Platform, Type, Genres, Date spotted, Status,
        #  Example link, How to execute it, Hashtags / keywords, Source, Notes,
        #  Matched Artists Count, Matched Artists Names, Personalised Justifications]
        rows: List[List[Any]] = []
        for t in trends:
            row = [
                t["id"],
                t["trend_name"],
                t.get("trend_summary", ""),
                t["platform"],
                t["type"],
                t["genres"],
                t["date_spotted"],
                t["status"],
                t.get("example_link", ""),
                t["how_to_execute"],
                t.get("hashtags", ""),
                t.get("source", "Automated Pipeline"),
                "",  # Column M: Notes strictly blank for manual manager entries
                t["matched_count"],
                t["matched_names"],
                t["personalized_justifications"],  # Column P: Serialized JSON string
            ]
            rows.append(row)

        if dry_run:
            logger.info(
                f"[DRY RUN] Prepared {len(rows)} rows for 'Trend library' (Columns A to P). Skipping live append."
            )
            print("\n" + "=" * 90)
            print("PREVIEW OF ROWS PREPARED FOR GOOGLE SHEETS:")
            print("=" * 90)
            for r in rows:
                print(f"[{r[0]}] {r[1]} | {r[3]} ({r[4]}) | Status: {r[7]} | Artists ({r[13]}): {r[14]}")
                print(f"     Action: {r[9]}")
                print(f"     Col M (Notes): '{r[12]}' (Preserved blank)")
                print(f"     Col P (JSON):  {r[15][:100]}...")
                print("-" * 90)
            return

        ws = self.spreadsheet.worksheet("Trend library")
        logger.info(
            f"Executing atomic batch append of {len(rows)} rows to 'Trend library' (A4:P4)..."
        )
        ws.append_rows(rows, value_input_option="USER_ENTERED", table_range="A4:P4")
        logger.info("Atomic batch append to Google Sheets completed successfully.")