"""Pexels Photo Provider.

Fetches high-resolution stock photos from the Pexels Photos API (/v1/search).
Preserves photographer attribution, original dimensions, and public page URLs.
"""

from __future__ import annotations
import urllib.parse
from typing import List, Optional

import requests
from loguru import logger

from app.config import config
from app.services.media_ranker.schemas import MediaCandidate
from .base import MediaSourceProvider


class PexelsPhotoProvider(MediaSourceProvider):
    @property
    def name(self) -> str:
        return "pexels_photos"

    def is_available(self) -> bool:
        keys = config.app.get("pexels_api_keys", [])
        if isinstance(keys, str):
            return bool(keys.strip())
        return bool(keys and len(keys) > 0)

    def _get_api_key(self) -> Optional[str]:
        keys = config.app.get("pexels_api_keys", [])
        if isinstance(keys, str):
            return keys.strip()
        if isinstance(keys, list) and keys:
            return str(keys[0]).strip()
        return None

    def search(
        self,
        query: str,
        media_type: str = "image",
        aspect: str = "portrait",
        limit: int = 10,
    ) -> List[MediaCandidate]:
        if not self.is_available():
            return []

        api_key = self._get_api_key()
        if not api_key:
            return []

        headers = {
            "Authorization": api_key,
            "User-Agent": "FabricaDeShorts/2.0 (EditorialStudio; +https://github.com)",
        }

        params = {
            "query": query,
            "per_page": min(limit, 30),
            "orientation": aspect if aspect in ("portrait", "landscape", "square") else "portrait",
        }

        url = f"https://api.pexels.com/v1/search?{urllib.parse.urlencode(params)}"
        logger.info("Searching Pexels Photos: query='{}' aspect={}", query, aspect)

        try:
            resp = requests.get(
                url,
                headers=headers,
                proxies=config.proxy,
                timeout=(10, 30),
            )
            if resp.status_code != 200:
                logger.warning(
                    "Pexels photos search returned status {}: {}",
                    resp.status_code, resp.text[:200]
                )
                return []

            data = resp.json()
            photos = data.get("photos", [])
            candidates: List[MediaCandidate] = []

            for photo in photos:
                if not isinstance(photo, dict):
                    continue

                photo_id = str(photo.get("id", ""))
                src = photo.get("src", {})
                if not isinstance(src, dict):
                    continue

                # Best download URL: portrait crop if vertical, else large2x or original
                download_url = src.get("portrait") or src.get("large2x") or src.get("original") or ""
                if not download_url:
                    continue

                thumbnail = src.get("tiny") or src.get("small") or download_url
                width = int(photo.get("width") or 1080)
                height = int(photo.get("height") or 1920)

                candidates.append(
                    MediaCandidate(
                        provider="pexels_photos",
                        provider_asset_id=photo_id,
                        asset_id=f"pexels_photo_{photo_id}",
                        query=query,
                        width=width,
                        height=height,
                        duration=0.0,
                        url=download_url,
                        thumbnail=thumbnail,
                        source_page=photo.get("url", ""),
                        media_type="image",
                        creator_name=photo.get("photographer", ""),
                        creator_url=photo.get("photographer_url", ""),
                        license_id="Pexels License",
                        license_url="https://www.pexels.com/license/",
                        technical_score=0.90,
                        final_score=0.90,
                    )
                )

            return candidates

        except Exception as e:
            logger.warning("Pexels photos search failed for query='{}': {}", query, e)
            return []
