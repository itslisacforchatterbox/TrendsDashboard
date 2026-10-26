"""Google Sheets connection and atomic batch writes via gspread."""
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
            creds = Credentials.from_service_account_info(json.loads(GCP_SA_CREDENTIALS), scopes=scopes)
        elif os.path.exists(GCP_SA_CREDENTIALS):
            creds = Credentials.from_service_account_file(GCP_SA_CREDENTIALS, scopes=scopes)
        else:
            raise FileNotFoundError(f"Service account file not found: {GCP_SA_CREDENTIALS}")
        return gspread.authorize(creds)

    def get_sheet_values(self, title: str) -> List[List[str]]:
        sheet_map = {ws.title.strip(): ws for ws in self.spreadsheet.worksheets()}
        if title in sheet_map:
            return sheet_map[title].get_all_values()
        logger.warning(f"Tab '{title}' not found in spreadsheet.")
        return []

    def append_trends(self, trends: List[Dict[str, Any]], dry_run: bool = False) -> None:
        if not trends:
            logger.info("No new trends to append.")
            return

        rows = [
            [
                t["id"], t["trend_name"], t["trend_summary"], t["platform"],
                t["type"], t["genres"], t["date_spotted"], t["status"],
                t["example_link"], t["how_to_execute_it"], t["hashtags_keywords"],
                t["source"], t["notes"], t["matched_count"], t["matched_names"]
            ]
            for t in trends
        ]

        if dry_run:
            logger.info(f"[DRY RUN] Prepared {len(rows)} rows for 'Trend library'. Skipping live append.")
            return

        ws = self.spreadsheet.worksheet("Trend library")
        logger.info(f"Executing atomic batch append of {len(rows)} rows to 'Trend library'...")
        ws.append_rows(rows, value_input_option="USER_ENTERED", table_range="A4:O4")
        logger.info("Atomic batch append completed successfully.")