"""Pixabay Photo Provider.

Searches Pixabay Image API for high-resolution vertical/portrait photos.
Integrates with the editorial Ken Burns pipeline and preserves author provenance.
"""

from __future__ import annotations
import urllib.parse
from typing import List

import requests
from loguru import logger

from app.config import config
from app.services.media_ranker.schemas import MediaCandidate
from .base import MediaSourceProvider, ProviderCapabilities


class PixabayPhotoProvider(MediaSourceProvider):
    capabilities = ProviderCapabilities(("image",), True, False, True)
    @property
    def name(self) -> str:
        return "pixabay_photos"

    def is_available(self) -> bool:
        keys = config.app.get("pixabay_api_keys", [])
        return bool(keys and keys[0])

    def search(
        self,
        query: str,
        media_type: str = "image",
        aspect: str = "portrait",
        limit: int = 10,
    ) -> List[MediaCandidate]:
        keys = config.app.get("pixabay_api_keys", [])
        if not keys or not keys[0]:
            return []

        key = keys[0]
        orientation = "vertical" if aspect == "portrait" else "all"
        clean_q = urllib.parse.quote_plus(query.strip())
        url = (
            f"https://pixabay.com/api/?key={key}&q={clean_q}"
            f"&image_type=photo&orientation={orientation}&per_page={max(3, min(limit, 20))}"
            f"&safesearch=true"
        )

        try:
            resp = requests.get(
                url,
                proxies=config.proxy,
                timeout=(5, 10),
            )
            resp.raise_for_status()

            data = resp.json()
            hits = data.get("hits", [])
            candidates: List[MediaCandidate] = []

            for hit in hits:
                if not isinstance(hit, dict):
                    continue

                photo_id = str(hit.get("id", ""))
                img_url = hit.get("largeImageURL") or hit.get("webformatURL")
                if not img_url:
                    continue

                w = int(hit.get("imageWidth") or 1080)
                h = int(hit.get("imageHeight") or 1920)
                user = hit.get("user") or "Pixabay Contributor"
                user_id = hit.get("user_id") or ""
                user_url = f"https://pixabay.com/users/{user}-{user_id}/" if user_id else f"https://pixabay.com/users/{user}/"
                page_url = hit.get("pageURL") or f"https://pixabay.com/photos/{photo_id}/"

                candidates.append(
                    MediaCandidate(
                        provider="pixabay_photo",
                        provider_asset_id=photo_id,
                        asset_id=f"pixabay_photo_{photo_id}",
                        query=query,
                        description=hit.get("tags", ""),
                        width=w,
                        height=h,
                        duration=0.0,
                        url=img_url,
                        thumbnail=hit.get("previewURL") or hit.get("webformatURL") or img_url,
                        source_page=page_url,
                        media_type="image",
                        creator_name=user,
                        creator_url=user_url,
                        license_id="Pixabay License",
                        license_url="https://pixabay.com/service/license-summary/",
                        technical_score=0.94,
                        final_score=0.94,
                    )
                )

            return candidates

        except Exception:
            raise
