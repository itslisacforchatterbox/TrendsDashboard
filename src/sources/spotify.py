"""Spotify Daily Chart Scraper via Kworb (Zero Auth, $0 Budget)."""
import logging
import re
from typing import List
import bs4
import requests
from src.models import RawItem
from src.sources.base import BaseSource

logger = logging.getLogger("TrendPipeline.Sources.Spotify")

class SpotifyKworbSource(BaseSource):
    name = "Spotify Daily Charts (Kworb)"

    CHART_URL = "https://kworb.net/spotify/country/au_daily.html"

    # Standard browser headers to prevent Cloudflare/datacenter IP blocks on GitHub Actions
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://kworb.net/spotify/",
        "DNT": "1",
    }

# fetch the primary artist image URL
    def _get_artist_image_url(self, track_id: str) -> str:
        """Helper to fetch artist profile image via oEmbed / public metadata endpoints without heavy auth."""
        try:
            # Using Spotify's public oEmbed endpoint as a zero-auth fallback
            oembed_resp = requests.get(f"https://open.spotify.com/oembed?url=https://open.spotify.com/track/{track_id}", timeout=5)
            if oembed_resp.status_code == 200:
                data = oembed_resp.json()
                # thumbnail_url typically provides the album/artist art associated with the track embed
                return data.get("thumbnail_url", "")
        except Exception:
            pass
        return ""
    

    def fetch(self) -> List[RawItem]:
        logger.info(f"Ingesting Spotify Australia Top 50 from Kworb: {self.CHART_URL}...")
        results: List[RawItem] = []

        try:
            resp = requests.get(self.CHART_URL, headers=self.HEADERS, timeout=20)
            if resp.status_code != 200:
                logger.error(f"Failed to load Kworb (HTTP {resp.status_code}).")
                return []

            soup = bs4.BeautifulSoup(resp.text, "html.parser")
            table = soup.find("table", id="spotifydaily") or soup.find("table", class_="sortable")
            if not table:
                logger.warning("Could not locate Spotify chart table on Kworb.")
                return []

            tbody = table.find("tbody")
            rows = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]

            # Ingest top 30 surging/popular tracks
            for row in rows[:30]:
                cells = row.find_all("td")
                if len(cells) < 7:
                    continue

                rank = cells[0].get_text(strip=True)
                title_cell = cells[2]
                streams = cells[6].get_text(strip=True)

                # Clean track & artist text e.g. "Tate McRae - Housewife"
                track_text = title_cell.get_text(separator=" ", strip=True)

                # Extract Spotify Track ID from href (e.g. "../track/2sFepQNyl1WjpROruP8bJ0.html")
                track_link = title_cell.find("a", href=re.compile(r"track/([a-zA-Z0-9]+)\.html"))
                if track_link:
                    match = re.search(r"track/([a-zA-Z0-9]+)\.html", track_link["href"])
                    spotify_track_id = match.group(1) if match else None
                    spotify_url = f"https://open.spotify.com/track/{spotify_track_id}"
                else:
                    spotify_url = "https://open.spotify.com"
                artist_image_url = self._get_artist_image_url(spotify_track_id) if spotify_track_id else ""
                results.append(
                    RawItem(
                        source="Spotify Daily AU (Kworb)",
                        raw_text=f"Spotify AU Rank #{rank}: {track_text}. Daily Streams: {streams}.",
                        url=spotify_url,
                    )
                )

            logger.info(f"Successfully extracted {len(results)} Spotify chart entries from Kworb.")

        except Exception as exc:
            logger.error(f"Error scraping Kworb chart: {exc}")

        return results
