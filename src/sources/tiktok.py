"""Curated TikTok source: Grabs only the top 5 macro hits and top 3 high-impact creator formats."""
import logging
from typing import List
import bs4
import requests
from src.config import APIFY_API_TOKEN
from src.models import RawItem
from src.sources.base import BaseSource

logger = logging.getLogger("TrendPipeline.Sources.TikTok")


class TikTokCuratedSource(BaseSource):
    name = "TikTok Curated Trends"

    BILLBOARD_TIKTOK_URL = "https://www.billboard.com/charts/tiktok-billboard-top-50/"
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    def _fetch_top_charting(self) -> List[RawItem]:
        """Pulls strictly the Top 5 songs driving TikTok this week."""
        results: List[RawItem] = []
        try:
            resp = requests.get(self.BILLBOARD_TIKTOK_URL, headers=self.HEADERS, timeout=15)
            if resp.status_code == 200:
                soup = bs4.BeautifulSoup(resp.text, "html.parser")
                rows = soup.select("ul.o-chart-results-list-row")
                for row in rows[:5]:  # Top 5 only
                    title_elem = row.select_one("h3#title-of-a-story")
                    if not title_elem:
                        continue
                    song_title = title_elem.get_text(strip=True)
                    artist_elem = title_elem.find_next_sibling("span")
                    artist_name = artist_elem.get_text(strip=True) if artist_elem else "Trending Artist"

                    rank_elem = row.select_one("span.c-label")
                    rank = rank_elem.get_text(strip=True) if rank_elem else "Top"

                    results.append(
                        RawItem(
                            source="TikTok Top 5 Chart",
                            raw_text=(
                                f"TikTok Leaderboard #{rank}: '{song_title}' by {artist_name}. "
                                f"Surging audio powering top creator videos."
                            ),
                            url=f"https://www.tiktok.com/tag/{song_title.replace(' ', '').lower()}",
                        )
                    )
        except Exception as exc:
            logger.error(f"Failed to fetch top TikTok chart: {exc}")
        return results

    def _fetch_top_formats(self) -> List[RawItem]:
        """Pulls strictly 3 high-engagement creator formats (>50k views)."""
        if not APIFY_API_TOKEN:
            return []

        results: List[RawItem] = []
        try:
            from apify_client import ApifyClient
            client = ApifyClient(APIFY_API_TOKEN)

            run = client.actor("clockworks/free-tiktok-scraper").call(
                run_input={
                    "searchQueries": ["openversechallenge", "songtransition"],
                    "searchSection": "/video",
                    "maxItems": 10,
                }
            )
            dataset_id = getattr(run, "default_dataset_id", None) or run.get("defaultDatasetId")
            items = client.dataset(dataset_id).list_items().items

            for it in items:
                play_count = int(it.get("playCount") or 0)
                # Strict quality bar: only posts with proven traction (>50k views)
                if play_count < 50_000:
                    continue

                music = it.get("musicMeta") or {}
                music_name = music.get("musicName") or "Original Audio"
                author = (it.get("authorMeta") or {}).get("name") or "Creator"
                desc = it.get("text") or ""
                url = it.get("webVideoUrl") or "https://www.tiktok.com"

                results.append(
                    RawItem(
                        source="TikTok Proven Format",
                        raw_text=f"Proven Format: '{music_name}' by @{author}. Plays: {play_count:,}. Concept: {desc[:150]}",
                        url=url,
                    )
                )
                if len(results) >= 3:  # Cap at 3 format examples
                    break
        except Exception as exc:
            logger.error(f"Failed to fetch TikTok formats: {exc}")
        return results

    def fetch(self) -> List[RawItem]:
        items: List[RawItem] = []
        items.extend(self._fetch_top_charting())  # 5 macro items
        items.extend(self._fetch_top_formats())    # 3 proven formats
        logger.info(f"Retrieved {len(items)} curated, high-priority TikTok items.")
        return items


# Backward compatibility
TikTokApifySource = TikTokCuratedSource
TikTokSoundRadarSource = TikTokCuratedSource
TikTokMacroTrendSource = TikTokCuratedSource