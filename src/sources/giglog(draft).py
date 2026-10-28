import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import List, Optional
import requests

from src.models import RawItem
from src.sources.base import BaseSource

ALLOWED_SECTIONS = {"news", "features", "industry", "reviews", "gigs"}
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

        try:
            resp = session.get(SITEMAP_URL, timeout=10)
            resp.raise_for_status()
        except Exception:
            return []

        root = ET.fromstring(resp.content)
        ns = {"sm": "http://www.sitemapindex.org/schemas/sitemap/0.9"}
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=14)
        candidates = []

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
            if section.lower() not in ALLOWED_SECTIONS:
                continue

            lastmod_dt = None
            if lastmod_node is not None and lastmod_node.text:
                try:
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

        candidates.sort(key=lambda x: x["lastmod"], reverse=True)
        top_candidates = candidates[:12]

        items: List[RawItem] = []

        for item_data in top_candidates:
            url = item_data["url"]
            fallback_headline = item_data["slug"].replace("-", " ").title()
            
            # Fields to extract for the spreadsheet
            artist = ""
            venue = ""
            suburb = ""
            genre = ""
            website = ""
            event_date = item_data["date_str"]

            try:
                art_resp = session.get(url, timeout=10)
                if "Just a moment..." not in art_resp.text:
                    html = art_resp.text

                    # 1. Try extraction via JSON-LD structured metadata
                    json_ld_matches = re.findall(
                        r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
                    )
                    for match in json_ld_matches:
                        try:
                            data = json.loads(match.strip())
                            if isinstance(data, list):
                                data = data[0]
                            
                            # Parse Event schema if available
                            if data.get("@type") in ["MusicEvent", "Event"]:
                                artist = data.get("performer", {}).get("name", "") or data.get("name", "")
                                location = data.get("location", {})
                                venue = location.get("name", "")
                                address = location.get("address", {})
                                if isinstance(address, dict):
                                    suburb = address.get("addressLocality", "")
                                website = data.get("url", url)
                                genre = data.get("genre", "")
                                if data.get("startDate"):
                                    event_date = data["startDate"].split("T")[0]
                        except Exception:
                            pass

                    # 2. Fallback regex extraction from headline/titles (e.g., "Live Review: Artist @ Venue, Suburb")
                    if not artist or not venue:
                        h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)
                        title_text = re.sub(r"<[^>]+>", "", h1_match.group(1)).strip() if h1_match else fallback_headline
                        
                        # Parse patterns like "Artist @ Venue"
                        if " @ " in title_text:
                            parts = title_text.split(" @ ")
                            artist = parts[0].replace("Live Review:", "").strip()
                            venue_suburb = parts[1].split(",")
                            venue = venue_suburb[0].strip()
                            if len(venue_suburb) > 1:
                                suburb = venue_suburb[1].strip()
                        else:
                            artist = title_text

            except Exception:
                artist = fallback_headline

            # Format enriched raw_text so downstream processors/LLMs can extract directly into sheet columns
            raw_text = (
                f"Date: {event_date}\n"
                f"Artist: {artist}\n"
                f"Event Venue: {venue}\n"
                f"Suburb: {suburb}\n"
                f"Genre: {genre}\n"
                f"Website: {website or url}"
            )

            items.append(
                RawItem(
                    source=self.name,
                    url=url,
                    raw_text=raw_text,
                )
            )

        return items
