"""Central application configuration, environment variable loader, and taxonomy constants."""

import os
from typing import List, Literal
from dotenv import load_dotenv

# Load local .env variables into os.environ
load_dotenv()

# ==============================================================================
# Canonical Taxonomy Definitions (Strict Enums)
# ==============================================================================
PLATFORM_LITERAL = Literal["TikTok", "Instagram", "YouTube", "YouTube Shorts", "Multi-platform"]
TYPE_LITERAL = Literal["Sound", "Format", "Challenge", "Topic", "Hashtag"]

# Calibrated Lifecycle Status Taxonomy
STATUS_LITERAL = Literal[
    "Active",        # Newly ingested short-form sound
    "🚀 Surging",    # Rapid positive velocity (< 8 days old)
    "🔥 Peak",       # Peak saturation (8–14 days old)
    "📉 Cooling",    # Algorithmic decay (15–27 days old)
    "💤 Stale",      # Expired wave or topical idea (28+ days old)
    "💡 Evergreen",  # Timeless, audio-agnostic creator template
    "Idea",          # Non-audio creative suggestion or YouTube release
]

# Structural Lifecycle Nature (The 3-Gate Framework)
TREND_NATURE_LITERAL = Literal["Evergreen_Format", "Temporal_Wave"]

# Canonical Artist Roster Genre Taxonomy
CANONICAL_GENRES = [
    "Pop",
    "R&B",
    "Dark R&B",
    "Hip-Hop",
    "Rap",
    "Pop Rap",
    "Trap",
    "Indian Hip-Hop",
    "R&B/Soul",
    "Soul",
    "House",
    "Dance",
    "Edm",
    "Indie Pop",
    "Afrobeats",
    "All",
]

# ==============================================================================
# Google Cloud Service Account & Google Sheets
# ==============================================================================
GCP_SA_CREDENTIALS = os.getenv("GCP_SA_CREDENTIALS", "")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")

# ==============================================================================
# Ingestion API Credentials (Stage A)
# ==============================================================================
APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN", "")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")

# ==============================================================================
# Disk Caching & Model Configuration
# ==============================================================================
CACHE_DIR = ".cache"
CACHE_FILE = os.path.join(CACHE_DIR, "raw_ingested_cache.json")
DEFAULT_CACHE_TTL_HOURS = 12.0

# Gemini Model alias & execution timeout (180s allows full multi-trend JSON generation)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
GEMINI_TIMEOUT_SECONDS = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "300.0"))


# ==============================================================================
# Gemini API Key Pool & Automatic Rotation Support
# ==============================================================================
def get_gemini_api_keys() -> List[str]:
    """Retrieves all configured Gemini API keys (primary + backups) for rotation."""
    keys: List[str] = []

    # 1. Comma-separated list support
    raw_keys = os.getenv("GEMINI_API_KEYS", "")
    if raw_keys.strip():
        for k in raw_keys.split(","):
            cleaned = k.strip()
            if cleaned and cleaned not in keys:
                keys.append(cleaned)

    # 2. Individual fallback variables support
    for var in [
        "GEMINI_API_KEY",
        "GEMINI_API_KEY_BACKUP",
        "GEMINI_API_KEY_BACKUP_2",
        "GEMINI_API_KEY_BACKUP_3",
    ]:
        val = os.getenv(var)
        if val and val.strip() and val.strip() not in keys:
            keys.append(val.strip())

    return keys


GEMINI_API_KEYS = get_gemini_api_keys()
GEMINI_API_KEY = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else ""