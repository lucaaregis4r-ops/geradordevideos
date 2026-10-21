"""Wikimedia Commons Provider.

Searches Wikimedia Commons (w/api.php) for public domain and Creative Commons
images covering historical events, science, places, and personalities.
Preserves full license attribution, author credits, and original metadata.
"""

from __future__ import annotations
import re
import urllib.parse
from typing import List

import requests
from loguru import logger

from app.config import config
from app.services.media_ranker.schemas import MediaCandidate
from .base import MediaSourceProvider


def _strip_html(text: str) -> str:
    """Removes HTML tags commonly found in MediaWiki artist/credit fields."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", "", text)
    return " ".join(clean.split()).strip()


class WikimediaCommonsProvider(MediaSourceProvider):
    @property
    def name(self) -> str:
        return "wikimedia_commons"

    def is_available(self) -> bool:
        # Wikimedia Commons API is publicly accessible without API keys
        return True

    def search(
        self,
        query: str,
        media_type: str = "image",
        aspect: str = "portrait",
        limit: int = 10,
    ) -> List[MediaCandidate]:
        headers = {
            "User-Agent": "FabricaDeShorts/2.0 (EditorialStudio; mailto:admin@example.com)",
        }

        # Query MediaWiki API
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"{query} filetype:bitmap",
            "gsrnamespace": 6,  # File namespace
            "gsrlimit": min(limit, 20),
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "format": "json",
        }

        url = f"https://commons.wikimedia.org/w/api.php?{urllib.parse.urlencode(params)}"
        logger.info("Searching Wikimedia Commons: query='{}'", query)

        try:
            resp = requests.get(
                url,
                headers=headers,
                proxies=config.proxy,
                timeout=(10, 30),
            )
            if resp.status_code != 200:
                logger.warning(
                    "Wikimedia Commons search returned status {}: {}",
                    resp.status_code, resp.text[:200]
                )
                return []

            data = resp.json()
            pages = (data.get("query") or {}).get("pages") or {}
            candidates: List[MediaCandidate] = []

            for page_id, page_info in pages.items():
                if not isinstance(page_info, dict):
                    continue

                imageinfo_list = page_info.get("imageinfo", [])
                if not imageinfo_list or not isinstance(imageinfo_list[0], dict):
                    continue

                info = imageinfo_list[0]
                mime = info.get("mime", "")
                if not mime.startswith("image/"):
                    continue

                download_url = info.get("url", "")
                if not download_url:
                    continue

                width = int(info.get("width", 1080))
                height = int(info.get("height", 1920))
                source_page = info.get("descriptionurl", "")

                extmetadata = info.get("extmetadata", {})
                artist_raw = extmetadata.get("Artist", {}).get("value", "")
                artist = _strip_html(artist_raw) or "Wikimedia Commons contributor"
                license_name = extmetadata.get("LicenseShortName", {}).get("value", "Public Domain / CC")
                license_url = extmetadata.get("LicenseUrl", {}).get("value", "https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia")

                candidates.append(
                    MediaCandidate(
                        provider="wikimedia_commons",
                        provider_asset_id=str(page_id),
                        asset_id=f"commons_{page_id}",
                        query=query,
                        width=width,
                        height=height,
                        duration=0.0,
                        url=download_url,
                        thumbnail=download_url,
                        source_page=source_page,
                        media_type="image",
                        creator_name=artist,
                        creator_url=source_page,
                        license_id=license_name,
                        license_url=license_url,
                        technical_score=0.88,
                        final_score=0.88,
                    )
                )

            return candidates

        except Exception as e:
            logger.warning("Wikimedia Commons search failed for query='{}': {}", query, e)
            return []
