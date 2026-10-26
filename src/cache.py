"""Local disk-caching to preserve free Apify credits and API rate limits."""
import json
import logging
import os
import time
from typing import List, Optional
from src.config import CACHE_DIR, CACHE_FILE, DEFAULT_CACHE_TTL_HOURS
from src.models import RawItem

logger = logging.getLogger("TrendPipeline.Cache")

def save_raw_cache(items: List[RawItem]) -> None:
    """Saves raw scraped items to a local JSON cache file."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    payload = {
        "timestamp": time.time(),
        "items": [item.model_dump() for item in items],
    }
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    logger.info(f"Cached {len(items)} raw items to '{CACHE_FILE}' to protect Apify quota.")

def load_raw_cache(ttl_hours: float = DEFAULT_CACHE_TTL_HOURS) -> Optional[List[RawItem]]:
    """Loads raw items from cache if the file exists and is fresher than ttl_hours."""
    if not os.path.exists(CACHE_FILE):
        return None

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        cache_age_hours = (time.time() - data.get("timestamp", 0)) / 3600.0
        if cache_age_hours <= ttl_hours:
            logger.info(f"Loaded {len(data['items'])} items from cache (Age: {cache_age_hours:.1f}h / TTL: {ttl_hours}h).")
            return [RawItem(**it) for it in data["items"]]
        else:
            logger.info(f"Cache expired ({cache_age_hours:.1f}h old). Fetching fresh data.")
            return None
    except Exception as exc:
        logger.warning(f"Failed to read cache file: {exc}")
        return None