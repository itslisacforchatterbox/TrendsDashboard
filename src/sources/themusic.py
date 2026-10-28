import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import List, Optional
import requests

from src.models import RawItem  # Adjust import according to your codebase
from src.sources.base import BaseSource  # Adjust import according to your codebase

ALLOWED_SECTIONS = {"news", "features", "industry", "reviews"}
SITEMAP_URL = "https://themusic.com.au/sitemap.xml?type=article&page=0"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

class TheMusicSource(BaseSource):
    name: str = "The Music"

    def fetch(self) -> List[RawItem]:
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})

        # Step 1: Fetch article sitemap
        try:
            resp = session.get(SITEMAP_URL, timeout=10)
            resp.raise_for_status()
        except Exception as e:
            # Return empty or handle logging as required by your framework
            return []

        # Step 2 & 3: Parse <url> tags and filter articles
        root = ET.fromstring(resp.content)
        # XML namespace for standard sitemaps
        ns = {"sm": "http://www.sitemapindex.org/schemas/sitemap/0.9"}

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=14)
        candidates = []

        # URL pattern: /{section}/{slug}/{id}/{dd-mm-yy}
        url_pattern = re.compile(
            r"https?://[^/]+/([^/]+)/([^/]+)/([^/]+)/(\d{2}-\d{2}-\d{2})/?$"
        )

        for url_node in root.findall("sm:url", ns):
            loc_node = url_node.find("sm:loc", ns)
            lastmod_node = url_node.find("sm:lastmod", ns)

            if loc_node is None or not loc_node.text:
                continue

            loc = loc_node.text.strip()
            match = url_pattern.search(loc)
            if not match:
                continue

            section, slug, article_id, date_str = match.groups()

            # Check section filter
            if section.lower() not in ALLOWED_SECTIONS:
                continue

            # Parse lastmod timestamp for sorting & 14-day window filtering
            lastmod_dt = None
            if lastmod_node is not None and lastmod_node.text:
                try:
                    # ISO 8601 format string parsing
                    lastmod_dt = datetime.fromisoformat(lastmod_node.text.replace("Z", "+00:00"))
                except ValueError:
                    pass

            if lastmod_dt and lastmod_dt < cutoff_date:
                continue

            candidates.append({
                "url": loc,
                "section": section,
                "slug": slug,
                "date_str": date_str,
                "lastmod": lastmod_dt or datetime.min.replace(tzinfo=timezone.utc),
            })

        # Sort by <lastmod> descending and cap at 12
        candidates.sort(key=lambda x: x["lastmod"], reverse=True)
        top_candidates = candidates[:12]

        # Step 4 & 5: Fetch article pages for H1 and standfirst, then construct RawItems
        items: List[RawItem] = []

        for item_data in top_candidates:
            url = item_data["url"]
            fallback_headline = item_data["slug"].replace("-", " ").title()
            headline = fallback_headline
            standfirst = ""

            try:
                art_resp = session.get(url, timeout=10)
                # Check for Cloudflare challenge response
                if "Just a moment..." in art_resp.text:
                    headline = fallback_headline
                else:
                    # Extract <h1> title
                    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", art_resp.text, re.IGNORECASE | re.DOTALL)
                    if h1_match:
                        headline = re.sub(r"<[^>]+>", "", h1_match.group(1)).strip()

                    # Extract standfirst / subtitle / meta description
                    standfirst_match = re.search(
                        r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']',
                        art_resp.text,
                        re.IGNORECASE | re.DOTALL,
                    )
                    if standfirst_match:
                        standfirst = standfirst_match.group(1).strip()
            except Exception:
                headline = fallback_headline

            # Build raw_text line
            raw_text = f"Section: {item_data['section']}\nDate: {item_data['date_str']}\nHeadline: {headline}\nStandfirst: {standfirst}".strip()

            items.append(
                RawItem(
                    source=self.name,
                    url=url,
                    raw_text=raw_text,
                )
            )

        return items
