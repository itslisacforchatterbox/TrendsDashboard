"""In-memory deduplication, artist matching, and individualized justification formatting."""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Set
from src.models import ExtractedTrend

logger = logging.getLogger("TrendPipeline.Matcher")


def normalize(text: str) -> str:
    if not text:
        return ""
    return " ".join(re.sub(r"[-_/]+", " ", text.strip().lower()).split())


def parse_genres(raw_val: Any) -> Set[str]:
    if not raw_val:
        return set()
    val_str = str(raw_val).strip()
    if val_str.startswith("[") and val_str.endswith("]"):
        try:
            return {
                normalize(str(x)) for x in json.loads(val_str) if normalize(str(x))
            }
        except Exception:
            pass
    return {normalize(x) for x in re.split(r"[,;/]+", val_str) if normalize(x)}


class TrendMatcher:

    @staticmethod
    def match_and_deduplicate(
        trends: List[ExtractedTrend],
        existing_rows: List[List[str]],
        artist_rows: List[List[str]],
        send_log_rows: List[List[str]],
    ) -> List[Dict[str, Any]]:
        existing_names: Set[str] = set()
        existing_links: Set[str] = set()
        existing_ids: List[int] = []

        if len(existing_rows) >= 4:
            for row in existing_rows[4:]:
                if not row or not row[0].strip():
                    break
                match = re.search(r"\d+", row[0])
                if match:
                    existing_ids.append(int(match.group()))
                if len(row) > 1 and row[1].strip():
                    existing_names.add(normalize(row[1]))
                if len(row) > 8 and row[8].strip():
                    existing_links.add(normalize(row[8]))

        if len(send_log_rows) >= 4:
            for row in send_log_rows[4:]:
                if len(row) > 2 and row[2].strip():
                    existing_names.add(normalize(row[2]))

        next_id = max(existing_ids, default=0) + 1

        # Build canonical roster name mapping (case-insensitive key -> exact sheet casing)
        roster_name_map: Dict[str, str] = {}
        if len(artist_rows) >= 4:
            for row in artist_rows[4:]:
                if len(row) >= 2 and row[1].strip():
                    canonical_name = row[1].strip()
                    roster_name_map[canonical_name.lower()] = canonical_name

        logger.info(f"Loaded {len(roster_name_map)} canonical artists from roster.")

        prepared: List[Dict[str, Any]] = []
        today_str = datetime.now(timezone.utc).strftime("%d %b %Y")

        for t in trends:
            norm_name = normalize(t.trend_name)
            norm_link = normalize(t.example_link)

            if norm_name in existing_names or (
                norm_link and norm_link in existing_links
            ):
                logger.info(f"Skipping duplicate trend: '{t.trend_name}'")
                continue

            # 1. Reconcile matched artist names against canonical roster casing
            matched_canonical_names: List[str] = []
            if t.matched_artists:
                for candidate in t.matched_artists:
                    c_clean = candidate.strip().lower()
                    if c_clean in roster_name_map:
                        matched_canonical_names.append(roster_name_map[c_clean])

            # Fallback to genre-matching if no direct artist was named
            if not matched_canonical_names:
                trend_genres = [
                    normalize(g) for g in re.split(r"[,;/]+", t.genres) if g.strip()
                ]
                is_all = "all" in trend_genres
                for row in artist_rows[4:]:
                    if len(row) >= 2 and row[1].strip():
                        a_name = row[1].strip()
                        a_genres = parse_genres(row[2] if len(row) > 2 else "")
                        if is_all or any(g in a_genres for g in trend_genres):
                            matched_canonical_names.append(a_name)

            deduped_artists = list(dict.fromkeys(matched_canonical_names))
            matched_count = len(deduped_artists)
            matched_names_str = "; ".join(deduped_artists)

            # 2. Extract justifications from compliant list of objects into dictionary
            clean_justifications: Dict[str, str] = {}
            for a_name in deduped_artists:
                justification_text = None
                for item in t.personalized_justifications:
                    if item.artist_name.strip().lower() == a_name.lower():
                        justification_text = item.justification.strip()
                        break

                if not justification_text:
                    justification_text = (
                        "This trend aligns with your sonic direction and brand aesthetic, "
                        "providing a strong organic discovery angle for your unreleased catalog."
                    )

                clean_justifications[a_name] = justification_text

            serialized_justifications = json.dumps(clean_justifications, ensure_ascii=False)

            prepared.append(
                {
                    "id": f"T{next_id:03d}",
                    "trend_name": t.trend_name,
                    "trend_summary": t.trend_summary,
                    "platform": t.platform,
                    "type": t.type,
                    "genres": t.genres,
                    "date_spotted": today_str,
                    "status": t.status,
                    "example_link": t.example_link,
                    "how_to_execute": t.how_to_execute,
                    "hashtags": t.hashtags,
                    "source": "Automated Pipeline",
                    "notes": "",  # Column M: INTENTIONALLY BLANK for agency managers
                    "matched_count": matched_count,
                    "matched_names": matched_names_str,
                    "personalized_justifications": serialized_justifications,  # Column P
                }
            )
            existing_names.add(norm_name)
            if norm_link:
                existing_links.add(norm_link)
            next_id += 1

        logger.info(f"Prepared {len(prepared)} new unique trends with individualized justifications.")
        return prepared