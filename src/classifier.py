"""Gemini Flash LLM engine with Single-Call Unified Extraction, paced backoff for 503s, and key rotation."""

import concurrent.futures
import hashlib
import json
import logging
import os
import random
import time
from collections import defaultdict
from typing import Dict, List
from google import genai
from google.genai import types
from src.config import (
    CACHE_DIR,
    GEMINI_API_KEYS,
    GEMINI_MODEL,
    GEMINI_TIMEOUT_SECONDS,
)
from src.models import ExtractedTrend, RawItem, UnifiedTrendResponse

logger = logging.getLogger("TrendPipeline.Classifier")

CHECKPOINT_CACHE_FILE = os.path.join(
    CACHE_DIR, "classified_trends_checkpoint.json"
)

SYSTEM_INSTRUCTION = (
    "You are an elite music marketing director for an independent artist development label. "
    "Your objective is CURATION OVER QUANTITY. "
    "Review the raw social media activity and charts divided by platform. "
    "For EACH platform section (TikTok, YouTube, Spotify), select and extract ONLY the top 3 to 5 "
    "most compelling, practically executable trends for independent artists.\n\n"
    "CRITICAL CLASSIFICATION FRAMEWORK:\n"
    "1. 'trend_nature' MUST be either 'Evergreen_Format' or 'Temporal_Wave':\n"
    "   - 'Evergreen_Format': Timeless, structural templates where an artist uses their OWN original music "
    "     (e.g., studio sneak peeks, acoustic performances, open-verse duets, lyric breakdowns, DAW beat flips). "
    "   - 'Temporal_Wave': Fleeting audio memes, charting commercial radio songs, dance crazes, or news events.\n"
    "2. 'genres' MUST strictly draw from our roster categories: "
    "   ['Pop', 'R&B', 'Dark R&B', 'Hip-Hop', 'Rap', 'Pop Rap', 'Trap', 'Indian Hip-Hop', "
    "    'R&B/Soul', 'Soul', 'House', 'Dance', 'Edm', 'Indie Pop', 'Afrobeats', 'All']. "
    "   Map specific styles into these categories (e.g. Melodic Rap -> Hip-Hop, Rap; Alt-Pop -> Pop, Indie Pop; Deep House -> House, Dance).\n"
    "3. 'how_to_execute_it' must be a direct 1-sentence prompt telling the artist what to film or perform."
)


def get_unified_signature(raw_items: List[RawItem]) -> str:
    content = "|".join([f"{it.source}:{it.url}" for it in raw_items])
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def load_checkpoints() -> Dict[str, List[dict]]:
    if not os.path.exists(CHECKPOINT_CACHE_FILE):
        return {}
    try:
        with open(CHECKPOINT_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning(f"Could not load classification checkpoints: {exc}")
        return {}


def save_checkpoint(sig: str, trends: List[ExtractedTrend]) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    checkpoints = load_checkpoints()
    checkpoints[sig] = [t.model_dump() for t in trends]
    try:
        with open(CHECKPOINT_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(checkpoints, f, indent=2)
    except Exception as exc:
        logger.warning(f"Failed to persist checkpoint to disk: {exc}")


def categorize_source_name(source: str) -> str:
    s = source.lower()
    if "tiktok" in s:
        return "TikTok"
    if "youtube" in s or "trends24" in s:
        return "YouTube"
    if "spotify" in s or "kworb" in s:
        return "Spotify"
    return "Editorial & Industry"


class TrendClassifier:

    def __init__(self):
        if not GEMINI_API_KEYS:
            raise ValueError(
                "No Gemini API keys found in environment variables!"
            )
        self.api_keys = GEMINI_API_KEYS
        self.current_key_idx = 0
        self.client = self._init_client(self.api_keys[self.current_key_idx])
        logger.info(
            f"Initialized Gemini Classifier with model '{GEMINI_MODEL}' and {len(self.api_keys)} API key(s)."
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

    def classify_chunks(
        self,
        raw_items: List[RawItem],
        chunk_size: int = 15,
        refresh_checkpoints: bool = False,
    ) -> List[ExtractedTrend]:
        """Executes a single unified prompt via Gemini Flash with paced backoff for 503 spikes."""
        if not raw_items:
            return []

        unified_sig = get_unified_signature(raw_items)
        checkpoints = {} if refresh_checkpoints else load_checkpoints()

        # Check local checkpoint cache
        if unified_sig in checkpoints:
            cached_data = checkpoints[unified_sig]
            cached_trends = [ExtractedTrend(**t) for t in cached_data]
            logger.info(
                f"[CACHE HIT] Loaded {len(cached_trends)} trends from disk checkpoint (0 Gemini quota used)."
            )
            return cached_trends

        buckets: Dict[str, List[RawItem]] = defaultdict(list)
        for it in raw_items:
            buckets[categorize_source_name(it.source)].append(it)

        # Full high-signal candidate pool
        capped_buckets: Dict[str, List[RawItem]] = {
            "TikTok": buckets.get("TikTok", [])[:8],
            "YouTube": buckets.get("YouTube", [])[:50],
            "Spotify": buckets.get("Spotify", [])[:30],
        }

        logger.info(
            f"Building Unified Prompt across: { {k: len(v) for k, v in capped_buckets.items() if v} }"
        )

        prompt = f"System Context:\n{SYSTEM_INSTRUCTION}\n\n"
        prompt += (
            "Task: For each platform section below (TikTok, YouTube, Spotify), select and extract "
            "the TOP 3 to 5 most practically executable music trends. Populate the corresponding schema list.\n\n"
        )

        for platform, items in capped_buckets.items():
            if not items:
                continue
            prompt += f"==================== {platform.upper()} CANDIDATES ({len(items)} items) ====================\n"
            for idx, it in enumerate(items, start=1):
                prompt += f"[{idx}] Source: {it.source} | URL: {it.url}\nData: {it.raw_text}\n\n"

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=UnifiedTrendResponse,
            temperature=0.1,
        )

        # Dedicated attempt loop with realistic pacing
        max_attempts = max(4, len(self.api_keys) * 2)
        attempt = 0

        while attempt < max_attempts:
            attempt += 1
            logger.info(
                f"Calling {GEMINI_MODEL} (Attempt {attempt}/{max_attempts}, Key #{self.current_key_idx + 1}/{len(self.api_keys)})..."
            )

            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = executor.submit(
                self.client.models.generate_content,
                model=GEMINI_MODEL,
                contents=prompt,
                config=config,
            )

            try:
                # 180s timeout accommodates full 3,000+ token generation without premature cutoff
                response = future.result(timeout=GEMINI_TIMEOUT_SECONDS)
                executor.shutdown(wait=False)

                if response.text:
                    unified_resp = UnifiedTrendResponse.model_validate_json(
                        response.text
                    )
                    all_trends = unified_resp.all_trends()

                    # Apply initial status mapping rules based on 3-Gate classification
                    for t in all_trends:
                        if t.trend_nature == "Evergreen_Format":
                            t.status = "💡 Evergreen"
                        elif (
                            "youtube.com" in t.example_link.lower()
                            or "youtu.be" in t.example_link.lower()
                            or t.platform.lower() == "youtube"
                        ):
                            t.status = "Idea"
                        else:
                            t.status = "Active"

                    logger.info(
                        f"[SUCCESS] Extracted via {GEMINI_MODEL}: "
                        f"{len(unified_resp.tiktok_trends)} TikTok, "
                        f"{len(unified_resp.youtube_trends)} YouTube, "
                        f"{len(unified_resp.spotify_trends)} Spotify trends. "
                        f"(Total: {len(all_trends)} trends in 1 API call)"
                    )
                    save_checkpoint(unified_sig, all_trends)
                    return all_trends

            except concurrent.futures.TimeoutError:
                executor.shutdown(wait=False, cancel_futures=True)
                logger.warning(
                    f"{GEMINI_MODEL} timed out after {GEMINI_TIMEOUT_SECONDS}s on Key #{self.current_key_idx + 1}."
                )
                self._rotate_key()
                continue

            except Exception as exc:
                executor.shutdown(wait=False, cancel_futures=True)
                err_str = str(exc)
                logger.warning(
                    f"{GEMINI_MODEL} call error on attempt {attempt}: {err_str}"
                )

                # 1. Quota errors (429) -> Rotate API key immediately
                if any(
                    c in err_str.lower()
                    for c in ["429", "resource_exhausted", "quota"]
                ):
                    logger.info(
                        "Quota limit reached. Rotating to next API key..."
                    )
                    self._rotate_key()
                    time.sleep(1.5)
                    continue

                # 2. Server capacity / traffic spikes (503 / unavailable)
                if any(
                    c in err_str.lower()
                    for c in [
                        "503",
                        "unavailable",
                        "disconnected",
                        "connection",
                    ]
                ):
                    self._rotate_key()
                    # Progressive backoff: 12s -> 24s -> 36s + jitter
                    backoff = (12.0 * attempt) + random.uniform(1.0, 4.0)
                    logger.info(
                        f"Temporary 503 spike on {GEMINI_MODEL}. Pacing backoff for {backoff:.1f}s to let Google cluster clear buffer..."
                    )
                    time.sleep(backoff)
                    continue

                time.sleep(3.0)

        logger.error(
            f"Unified classification failed across all {max_attempts} attempts."
        )
        return []