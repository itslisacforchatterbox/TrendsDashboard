"""YouTube Data API v3 and Trends24 fallback parser."""
import logging
from typing import List
import bs4
import requests
from src.config import YOUTUBE_API_KEY
from src.models import RawItem
from src.sources.base import BaseSource

logger = logging.getLogger("TrendPipeline.Sources.YouTube")

class YouTubeSource(BaseSource):
    name = "YouTube Trending AU"

    def fetch(self) -> List[RawItem]:
        results: List[RawItem] = []

        # 1. Official YouTube Data API v3
        if YOUTUBE_API_KEY:
            try:
                logger.info("Querying YouTube Data API v3 (Australia Music Category)...")
                url = "https://www.googleapis.com/youtube/v3/videos"
                params = {
                    "part": "snippet,statistics",
                    "chart": "mostPopular",
                    "regionCode": "AU",
                    "videoCategoryId": "10",
                    "maxResults": "25",
                    "key": YOUTUBE_API_KEY,
                }
                resp = requests.get(url, params=params, timeout=20)
                if resp.status_code == 200:
                    for item in resp.json().get("items", []):
                        snip = item.get("snippet", {})
                        v_id = item.get("id")
                        results.append(RawItem(
                            source="YouTube Trending API",
                            raw_text=f"Trending Music Video: '{snip.get('title')}' by {snip.get('channelTitle')}. Description: {snip.get('description', '')[:250]}",
                            url=f"https://www.youtube.com/watch?v={v_id}",
                        ))
                    logger.info(f"Retrieved {len(results)} videos from official YouTube API.")
            except Exception as exc:
                logger.error(f"YouTube Data API query failed: {exc}")

        # 2. Trends24 Static HTML Fallback
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            resp = requests.get("https://youtube.trends24.in/australia/#today-group-music", headers=headers, timeout=20)
            if resp.status_code == 200:
                soup = bs4.BeautifulSoup(resp.text, "html.parser")
                cards = soup.select(".trend-card") or soup.select("ol.trend-card__list li")
                count = 0
                for c in cards[:10]:
                    link = c.find("a")
                    if link and link.get_text(strip=True):
                        href = link.get("href", "")
                        results.append(RawItem(
                            source="YouTube Trends24 AU",
                            raw_text=f"Surging YouTube Video: {link.get_text(strip=True)}",
                            url=href if href.startswith("http") else f"https://youtube.trends24.in{href}",
                        ))
                        count += 1
                logger.info(f"Retrieved {count} fallback items from Trends24.")
        except Exception as exc:
            logger.error(f"Trends24 scraper failed: {exc}")

        return results