"""Artist Profiler: Dynamically loads rich artist personas directly from private Google Sheets."""

import json
import logging
import os
import re
from typing import List, Optional
from src.config import DATA_DIR
from src.models import ArtistProfile

logger = logging.getLogger("TrendPipeline.Profiler")

ARTIST_PROFILES_FILE = os.path.join(DATA_DIR, "artist_profiles.json")


def load_artist_profiles_from_sheet(sheets_client) -> List[ArtistProfile]:
    """Reads artist dossiers dynamically from the private 'Artist profiles' tab in Google Sheets."""
    spreadsheet = sheets_client.spreadsheet
    sheet_map = {ws.title.strip().lower(): ws for ws in spreadsheet.worksheets()}
    tab_name = "artist profiles"

    if tab_name not in sheet_map:
        logger.warning(
            f"Worksheet 'Artist profiles' not found in spreadsheet. "
            f"Please ensure the tab exists in your private Google Sheet."
        )
        return []

    ws = sheet_map[tab_name]
    rows = ws.get_all_values()

    # Table headers are on Row 4, data begins on Row 5
    if len(rows) < 5:
        logger.warning("Worksheet 'Artist profiles' has no data rows (starts at Row 5).")
        return []

    profiles: List[ArtistProfile] = []
    for r in rows[4:]:
        if not r or len(r) < 2 or not r[1].strip():
            continue

        genres = [g.strip() for g in re.split(r"[,;]+", r[2]) if g.strip()] if len(r) > 2 else []
        tracks = [t.strip() for t in re.split(r"[,;]+", r[5]) if t.strip()] if len(r) > 5 else []
        channels = [c.strip() for c in re.split(r"[,;]+", r[7]) if c.strip()] if len(r) > 7 else []
        themes = [th.strip() for th in re.split(r"[,;]+", r[8]) if th.strip()] if len(r) > 8 else []

        profiles.append(
            ArtistProfile(
                songstats_id=r[0].strip() if len(r) > 0 else "N/A",
                name=r[1].strip(),
                genres=genres,
                brand_identity=r[3].strip() if len(r) > 3 else "",
                bio=r[4].strip() if len(r) > 4 else "",
                top_tracks=tracks,
                musical_profile=r[6].strip() if len(r) > 6 else "",
                primary_channels=channels,
                recent_content_themes=themes,
            )
        )

    logger.info(
        f"Loaded {len(profiles)} private artist profiles dynamically from Google Sheets ('Artist profiles')."
    )

    # Cache locally to disk for offline performance (git-ignored)
    save_artist_profiles_to_disk(profiles)
    return profiles


def save_artist_profiles_to_disk(profiles: List[ArtistProfile]) -> None:
    """Saves profiles to local disk cache (never committed to Git)."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(ARTIST_PROFILES_FILE, "w", encoding="utf-8") as f:
            json.dump([p.model_dump() for p in profiles], f, indent=2)
    except Exception as exc:
        logger.warning(f"Could not cache artist profiles to disk: {exc}")


def load_artist_profiles(sheets_client=None) -> List[ArtistProfile]:
    """Loads profiles from Google Sheets (Primary) or local disk cache (Offline fallback)."""
    # 1. Primary: Load fresh data directly from private Google Sheet
    if sheets_client:
        try:
            sheet_profiles = load_artist_profiles_from_sheet(sheets_client)
            if sheet_profiles:
                return sheet_profiles
        except Exception as exc:
            logger.warning(f"Could not load profiles from Google Sheets: {exc}")

    # 2. Offline Fallback: Load from local disk cache if available
    if os.path.exists(ARTIST_PROFILES_FILE):
        try:
            with open(ARTIST_PROFILES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [ArtistProfile(**item) for item in data]
        except Exception as exc:
            logger.warning(f"Failed to read local artist profiles cache: {exc}")

    logger.warning("No artist profiles available in Google Sheets or local cache.")
    return []


def format_roster_context_for_llm(profiles: List[ArtistProfile]) -> str:
    """Formats rich artist personas into a dense instruction block for Gemini."""
    if not profiles:
        return "TARGET ARTIST ROSTER: No specific artist profiles loaded."

    lines: List[str] = ["TARGET ARTIST ROSTER & CREATIVE PROFILES:"]
    for p in profiles:
        top_songs = ", ".join(p.top_tracks[:3]) if p.top_tracks else "Catalog"
        genres = ", ".join(p.genres)
        themes = "; ".join(p.recent_content_themes[:3]) if p.recent_content_themes else "General music"
        lines.append(
            f"• [{p.name}] Genres: {genres} | Era/Brand: {p.brand_identity} | "
            f"Key Tracks: {top_songs} | Social Content Style: {themes}"
        )
    return "\n".join(lines)