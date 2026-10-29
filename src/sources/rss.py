"""Editorial blog and Substack newsletter RSS/HTML parser."""

import logging
from typing import List
import bs4
import feedparser
import requests
from src.models import RawItem
from src.sources.base import BaseSource

logger = logging.getLogger("TrendPipeline.Sources.RSS")


class EditorialRSSSource(BaseSource):
    name = "Editorial & Newsletters"

    FEEDS = [
        ("Substack - Trapital", "https://trapital.co/feed/"),
        ("Substack - Digital Native", "https://digitalnative.substack.com/feed"),
        ("NewEngen TikTok Trends", "https://vadbav.com/feed"),
    ]

    WEB_SOURCES = [
        ("Later Blog - Reels Trends", "https://later.com/blog/instagram-reels-trends/"),
        ("SocialBee - TikTok Trends", "https://socialbee.com/blog/tiktok-trends-you-cant-miss/"),
        ("SocialBee - Trending TikTok Songs", "https://socialbee.com/blog/trending-tiktok-songs/"),
    ]

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    def _fetch_rss(self) -> List[RawItem]:
        results: List[RawItem] = []
        for name, url in self.FEEDS:
            try:
                parsed = feedparser.parse(url)
                for entry in parsed.entries[:4]:
                    summary = bs4.BeautifulSoup(
                        entry.get("summary", ""), "html.parser"
                    ).get_text(strip=True)[:350]
                    results.append(
                        RawItem(
                            source=name,
                            raw_text=f"{entry.get('title', '')}. Details: {summary}",
                            url=entry.get("link", ""),
                        )
                    )
            except Exception as exc:
                logger.error(f"Failed to parse RSS feed {url}: {exc}")
        return results

    def _fetch_web_articles(self) -> List[RawItem]:
        results: List[RawItem] = []
        for name, url in self.WEB_SOURCES:
            try:
                resp = requests.get(url, headers=self.HEADERS, timeout=15)
                if resp.status_code == 200:
                    soup = bs4.BeautifulSoup(resp.text, "html.parser")
                    # Extract H2/H3 headers which represent named trend entries
                    headers = soup.select("article h2, article h3, .post-content h2, .post-content h3")
                    for h in headers[:5]:
                        title = h.get_text(strip=True)
                        if len(title) > 5 and not any(skip in title.lower() for skip in ["table of contents", "conclusion", "faqs", "related"]):
                            # Grab following paragraph text
                            p_elem = h.find_next("p")
                            desc = p_elem.get_text(strip=True)[:250] if p_elem else ""
                            results.append(
                                RawItem(
                                    source=f"Editorial ({name})",
                                    raw_text=f"Curated Industry Trend: '{title}'. Insight: {desc}",
                                    url=url,
                                )
                            )
            except Exception as exc:
                logger.warning(f"Could not scrape web source {url}: {exc}")
        return results

    def fetch(self) -> List[RawItem]:
        items: List[RawItem] = []
        items.extend(self._fetch_rss())
        items.extend(self._fetch_web_articles())
        logger.info(f"Retrieved {len(items)} curated editorial items.")
        return items