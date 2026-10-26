"""Editorial blog and Substack newsletter RSS parser."""
import logging
from typing import List
import bs4
import feedparser
from src.models import RawItem
from src.sources.base import BaseSource

logger = logging.getLogger("TrendPipeline.Sources.RSS")

class EditorialRSSSource(BaseSource):
    name = "Editorial & Newsletters"

    FEEDS = [
        ("Substack - Digital Native", "https://digitalnative.substack.com/feed"),
        ("Substack - Trapital", "https://trapital.co/feed/"),
        ("NewEngen TikTok Trends", "https://vadbav.com/feed"),
    ]

    def fetch(self) -> List[RawItem]:
        results: List[RawItem] = []
        for name, url in self.FEEDS:
            try:
                parsed = feedparser.parse(url)
                for entry in parsed.entries[:5]:
                    summary = bs4.BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(strip=True)[:350]
                    results.append(RawItem(
                        source=name,
                        raw_text=f"{entry.get('title', '')}. Details: {summary}",
                        url=entry.get("link", ""),
                    ))
            except Exception as exc:
                logger.error(f"Failed to parse RSS feed {url}: {exc}")
        return results