"""In-memory genre normalization, deduplication, and artist matching."""
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Set
from src.models import ExtractedTrend

logger = logging.getLogger("TrendPipeline.Matcher")

def normalize(text: str) -> str:
    """Normalizes string casing and punctuation."""
    if not text:
        return ""
    return " ".join(re.sub(r"[-_/]+", " ", text.strip().lower()).split())

def parse_genres(raw_val: Any) -> Set[str]:
    """Extracts a set of normalized genres from a cell."""
    if not raw_val:
        return set()
    val_str = str(raw_val).strip()
    if val_str.startswith("[") and val_str.endswith("]"):
        try:
            return {normalize(str(x)) for x in json.loads(val_str) if normalize(str(x))}
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
        # Index existing trends to prevent duplicates
        existing_names: Set[str] = set()
        existing_links: Set[str] = set()
        existing_ids: List[int] = []

        if len(existing_rows) >= 4:
            for row in existing_rows[4:]:
                if not row or not row[0].strip():
                    continue
                match = re.search(r"\d+", row[0])
                if match:
                    existing_ids.append(int(match.group()))
                if len(row) > 1 and row[1].strip():
                    existing_names.add(normalize(row[1]))
                if len(row) > 8 and row[8].strip():
                    existing_links.add(normalize(row[8]))

        # Include historical Send log trend names
        if len(send_log_rows) >= 4:
            for row in send_log_rows[4:]:
                if len(row) > 2 and row[2].strip():
                    existing_names.add(normalize(row[2]))

        next_id = max(existing_ids, default=0) + 1

        # Index Artist roster
        roster: List[Dict[str, Any]] = []
        if len(artist_rows) >= 4:
            for row in artist_rows[4:]:
                if len(row) >= 2 and row[1].strip():
                    roster.append({
                        "name": row[1].strip(),
                        "genres": parse_genres(row[2] if len(row) > 2 else ""),
                    })

        logger.info(f"Loaded {len(roster)} artists from roster.")

        prepared: List[Dict[str, Any]] = []
        today_str = datetime.now(timezone.utc).strftime("%d %b %Y")

        for t in trends:
            norm_name = normalize(t.trend_name)
            norm_link = normalize(t.example_link)

            if norm_name in existing_names or (norm_link and norm_link in existing_links):
                logger.info(f"Skipping duplicate trend: '{t.trend_name}'")
                continue

            trend_genres = [normalize(g) for g in re.split(r"[,;/]+", t.genres) if g.strip()]
            is_all = "all" in trend_genres

            matched = [
                a["name"] for a in roster
                if is_all or any(g in a["genres"] for g in trend_genres)
            ]
            deduped_matches = list(dict.fromkeys(matched))

            prepared.append({
                "id": f"T{next_id:03d}",
                "trend_name": t.trend_name,
                "trend_summary": t.trend_summary,
                "platform": t.platform,
                "type": t.type,
                "genres": t.genres,
                "date_spotted": today_str,
                "status": t.status,
                "example_link": t.example_link,
                "how_to_execute_it": t.how_to_execute_it,
                "hashtags_keywords": t.hashtags_or_keywords,
                "source": "Automated Pipeline",
                "notes": t.notes,
                "matched_count": len(deduped_matches),
                "matched_names": "; ".join(deduped_matches),
            })
            existing_names.add(norm_name)
            if norm_link:
                existing_links.add(norm_link)
            next_id += 1

        logger.info(f"Prepared {len(prepared)} new unique trends for cataloging.")
        return prepared