"""Gemini Flash LLM engine with Artist-Tailored Curation, Strict Evergreen Gates, and Configurable Timeouts."""

import concurrent.futures
import hashlib
import json
import logging
import os
import random
import time
from collections import defaultdict
from typing import Dict, List, Optional
from google import genai
from google.genai import types
from src.artist_profiler import format_roster_context_for_llm, load_artist_profiles
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


def build_system_instruction(roster_context: str) -> str:
    return (
        "You are an elite, highly selective Music Marketing Director and A&R Strategist managing an independent roster.\n"
        "Your objective is HIGH-CONVICTION, ARTIST-TAILORED CURATION over raw quantity.\n\n"
        f"{roster_context}\n\n"
        "CURATION & EVALUATION DIRECTIVES:\n"
        "1. ARTIST-TAILORED MATCHING: Do NOT curate generic trends. For every trend you extract, specify exactly which "
        "   artist(s) on our roster should execute it in 'target_artists', and explain the exact strategic fit in 'artist_fit_reasoning' "
        "   (referencing their specific vocal style, recent releases, or social media aesthetic).\n"
        "2. STRICT 4-PILLAR EVERGREEN GATE (CRITICAL):\n"
        "   To prevent clutter, you must classify 'trend_nature' as 'Temporal_Wave' by default. "
        "   Set 'trend_nature' to 'Evergreen_Format' ONLY if the trend meets ALL FOUR criteria:\n"
        "     a) Audio-Agnostic: The format works using the artist's OWN original or unreleased music.\n"
        "     b) Timeless: The concept will be just as effective 2 years from now (e.g. lyric reveal, raw acoustic take, open-verse duet).\n"
        "     c) Structural Template: It is a repeatable storytelling or performance vehicle (Type = Format or Challenge).\n"
        "     d) High-Retention Value: It showcases core artistic craft (vocals, songwriting, beatmaking) rather than a fleeting visual gimmick.\n"
        "   If it relies on trending third-party radio audio, dance moves, movie trailers, seasonal cosplay, or memes, it is strictly 'Temporal_Wave'.\n"
        "3. TACTICAL EXECUTION: 'how_to_execute_it' must be a direct 1-sentence prompt telling the artist exactly what to film."
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

    def __init__(
        self,
        sheets_client: Optional[object] = None,
        no_timeout: bool = False,
        **kwargs,
    ):
        if not GEMINI_API_KEYS:
            raise ValueError(
                "No Gemini API keys found in environment variables!"
            )
        self.api_keys = GEMINI_API_KEYS
        self.current_key_idx = 0
        self.client = self._init_client(self.api_keys[self.current_key_idx])
        self.no_timeout = no_timeout
        self.timeout_val = None if no_timeout else GEMINI_TIMEOUT_SECONDS
        self.artist_profiles = load_artist_profiles(sheets_client=sheets_client)
        timeout_desc = "DISABLED" if self.no_timeout else f"{self.timeout_val}s"
        logger.info(
            f"Initialized Classifier with model '{GEMINI_MODEL}', {len(self.api_keys)} key(s), "
            f"timeout={timeout_desc}, and {len(self.artist_profiles)} artist profiles."
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
        """Executes unified artist-tailored trend extraction with candidate pools."""
        if not raw_items:
            return []

        unified_sig = get_unified_signature(raw_items)
        checkpoints = {} if refresh_checkpoints else load_checkpoints()

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

        capped_buckets: Dict[str, List[RawItem]] = {
            "TikTok": buckets.get("TikTok", [])[:15],
            "YouTube": buckets.get("YouTube", [])[:50],
            "Spotify": buckets.get("Spotify", [])[:40],
            "Editorial & Industry": buckets.get("Editorial & Industry", [])[:8],
        }

        logger.info(
            f"Building Artist-Tailored Prompt across: { {k: len(v) for k, v in capped_buckets.items() if v} }"
        )

        roster_context = format_roster_context_for_llm(self.artist_profiles)
        system_prompt = build_system_instruction(roster_context)

        prompt = f"System Context:\n{system_prompt}\n\n"
        prompt += (
            "Task: For each platform section below (TikTok, YouTube, Spotify, Editorial), select and extract "
            "the TOP 3 to 4 trends that MOST STRONGLY match our specific artists' sound, aesthetic, and releases. "
            "Populate each corresponding schema list.\n\n"
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

        max_attempts = max(4, len(self.api_keys) * 2)
        attempt = 0

        while attempt < max_attempts:
            attempt += 1
            timeout_desc = "NONE" if self.no_timeout else f"{self.timeout_val}s"
            logger.info(
                f"Calling {GEMINI_MODEL} (Attempt {attempt}/{max_attempts}, Key #{self.current_key_idx + 1}/{len(self.api_keys)}, Timeout: {timeout_desc})..."
            )

            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = executor.submit(
                self.client.models.generate_content,
                model=GEMINI_MODEL,
                contents=prompt,
                config=config,
            )

            try:
                # If no_timeout is active, future.result(timeout=None) will wait until Gemini finishes
                response = future.result(timeout=self.timeout_val)
                executor.shutdown(wait=False)

                if response.text:
                    unified_resp = UnifiedTrendResponse.model_validate_json(
                        response.text
                    )
                    all_trends = unified_resp.all_trends()

                    # Apply status mapping based on 3-Gate and link origin
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
                        f"[SUCCESS] Unified Call Extracted: "
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
                    f"{GEMINI_MODEL} timed out after {self.timeout_val}s on Key #{self.current_key_idx + 1}."
                )
                self._rotate_key()
                continue

            except Exception as exc:
                executor.shutdown(wait=False, cancel_futures=True)
                err_str = str(exc)
                logger.warning(
                    f"{GEMINI_MODEL} call error on attempt {attempt}: {err_str}"
                )

                if any(
                    c in err_str.lower()
                    for c in ["429", "resource_exhausted", "quota"]
                ):
                    logger.info("Quota reached. Rotating API key...")
                    self._rotate_key()
                    time.sleep(1.5)
                    continue

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
                    backoff = (12.0 * attempt) + random.uniform(1.0, 4.0)
                    logger.info(
                        f"503 load spike on {GEMINI_MODEL}. Pacing backoff for {backoff:.1f}s..."
                    )
                    time.sleep(backoff)
                    continue

                time.sleep(3.0)

        logger.error("Unified classification failed across all attempts.")
        return []