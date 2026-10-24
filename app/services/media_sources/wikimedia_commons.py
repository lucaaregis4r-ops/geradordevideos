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
from .base import MediaSourceProvider, ProviderCapabilities


def _strip_html(text: str) -> str:
    """Removes HTML tags commonly found in MediaWiki artist/credit fields."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", "", text)
    return " ".join(clean.split()).strip()


class WikimediaCommonsProvider(MediaSourceProvider):
    capabilities = ProviderCapabilities(("image", "video"))
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
            "gsrsearch": f"{query} filetype:{'video' if media_type == 'video' else 'bitmap'}",
            "gsrnamespace": 6,  # File namespace
            "gsrlimit": min(limit, 20),
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "format": "json",
        }

        if media_type == "video":
            params["prop"] = "videoinfo"
            params.pop("iiprop")
            params["viprop"] = "url|size|mime|extmetadata|derivatives"
        url = f"https://commons.wikimedia.org/w/api.php?{urllib.parse.urlencode(params)}"
        logger.info("Searching Wikimedia Commons: query='{}'", query)

        try:
            resp = requests.get(
                url,
                headers=headers,
                proxies=config.proxy,
                timeout=(10, 30),
            )
            resp.raise_for_status()

            data = resp.json()
            pages = (data.get("query") or {}).get("pages") or {}
            candidates: List[MediaCandidate] = []

            for page_id, page_info in pages.items():
                if not isinstance(page_info, dict):
                    continue

                imageinfo_list = page_info.get("videoinfo" if media_type == "video" else "imageinfo", [])
                if not imageinfo_list or not isinstance(imageinfo_list[0], dict):
                    continue

                info = imageinfo_list[0]
                mime = info.get("mime", "")
                if not mime.startswith(f"{media_type}/"):
                    continue

                download_url = info.get("url", "")
                if not download_url:
                    continue

                if media_type == "video":
                    variants = [v for v in info.get("derivatives", []) if v.get("src") and str(v.get("type", "")).startswith("video/")]
                    if variants:
                        best = max(variants, key=lambda v: int(v.get("width", 0)) * int(v.get("height", 0)))
                        download_url = best["src"]
                        info = {**info, "width": best.get("width", info.get("width", 0)), "height": best.get("height", info.get("height", 0))}
                width = int(info.get("width", 0))
                height = int(info.get("height", 0))
                source_page = info.get("descriptionurl", "")

                extmetadata = info.get("extmetadata", {})
                artist_raw = extmetadata.get("Artist", {}).get("value", "")
                artist = _strip_html(artist_raw) or "Wikimedia Commons contributor"
                license_name = extmetadata.get("LicenseShortName", {}).get("value", "")
                license_url = extmetadata.get("LicenseUrl", {}).get("value", "https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia")

                candidates.append(
                    MediaCandidate(
                        provider="wikimedia_commons",
                        provider_asset_id=str(page_id),
                        asset_id=f"commons_{page_id}",
                        query=query,
                        description=_strip_html(extmetadata.get("ImageDescription", {}).get("value", "")),
                        width=width,
                        height=height,
                        duration=0.0,
                        url=download_url,
                        thumbnail=download_url,
                        source_page=source_page,
                        media_type=media_type,
                        creator_name=artist,
                        creator_url=source_page,
                        license_id=license_name,
                        license_url=license_url,
                        technical_score=0.88,
                        final_score=0.88,
                    )
                )

            return candidates

        except Exception:
            raise
