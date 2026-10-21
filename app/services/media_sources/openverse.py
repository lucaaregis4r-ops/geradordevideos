"""Openverse Provider.

Searches open-source, Creative Commons images across hundreds of cultural institutions
and open archives via the Openverse API (v1).
Filters specifically for commercial-friendly licenses (CC0, PDM, CC-BY, CC-BY-SA).
"""

from __future__ import annotations
import urllib.parse
from typing import List

import requests
from loguru import logger

from app.config import config
from app.services.media_ranker.schemas import MediaCandidate
from .base import MediaSourceProvider


class OpenverseProvider(MediaSourceProvider):
    @property
    def name(self) -> str:
        return "openverse"

    def is_available(self) -> bool:
        # Openverse API has public access for searches
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

        # Filter strictly for commercial use and modification allowed
        params = {
            "q": query,
            "license_type": "commercial,modification",
            "page_size": min(limit, 20),
        }

        url = f"https://api.openverse.org/v1/images/?{urllib.parse.urlencode(params)}"
        logger.info("Searching Openverse: query='{}'", query)

        try:
            resp = requests.get(
                url,
                headers=headers,
                proxies=config.proxy,
                timeout=(10, 30),
            )
            if resp.status_code != 200:
                logger.warning(
                    "Openverse search returned status {}: {}",
                    resp.status_code, resp.text[:200]
                )
                return []

            data = resp.json()
            results = data.get("results", [])
            candidates: List[MediaCandidate] = []

            for item in results:
                if not isinstance(item, dict):
                    continue

                item_id = str(item.get("id", ""))
                download_url = item.get("url", "")
                if not download_url:
                    continue

                source_page = item.get("foreign_landing_url") or item.get("detail_url") or ""
                thumbnail = item.get("thumbnail") or download_url
                creator = item.get("creator") or "Openverse contributor"
                creator_url = item.get("creator_url") or ""
                lic_code = str(item.get("license") or "").upper()
                lic_ver = item.get("license_version") or ""
                license_id = f"CC {lic_code} {lic_ver}".strip() if lic_code else "Creative Commons"
                license_url = item.get("license_url") or "https://creativecommons.org/"

                candidates.append(
                    MediaCandidate(
                        provider="openverse",
                        provider_asset_id=item_id,
                        asset_id=f"openverse_{item_id}",
                        query=query,
                        width=1080,
                        height=1920,
                        duration=0.0,
                        url=download_url,
                        thumbnail=thumbnail,
                        source_page=source_page,
                        media_type="image",
                        creator_name=creator,
                        creator_url=creator_url,
                        license_id=license_id,
                        license_url=license_url,
                        technical_score=0.86,
                        final_score=0.86,
                    )
                )

            return candidates

        except Exception as e:
            logger.warning("Openverse search failed for query='{}': {}", query, e)
            return []
