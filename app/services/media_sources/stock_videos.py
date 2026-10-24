"""Compatibility adapters over the existing authenticated video clients."""
from __future__ import annotations

from app.config import config
from app.models.schema import VideoAspect
from app.services import material
from app.services.media_ranker.schemas import MediaCandidate
from .base import MediaSourceProvider, ProviderCapabilities


class StockVideoProvider(MediaSourceProvider):
    capabilities = ProviderCapabilities(("video",), True, True, True)
    provider_name = ""

    @property
    def name(self) -> str:
        return self.provider_name

    def is_available(self) -> bool:
        return bool(config.app.get(f"{self.name}_api_keys"))

    def search(self, query, media_type="video", aspect="portrait", limit=5):
        search = getattr(material, f"search_videos_{self.name}")
        items = search(search_term=query, minimum_duration=2, strict_errors=True,
                       video_aspect=VideoAspect.portrait if aspect == "portrait" else VideoAspect.landscape)
        candidates = []
        for item in items[:limit]:
            info = item.source_info or {}
            rendition = info.get("rendition") or {}
            creator = info.get("creator") or {}
            asset_id = str(info.get("asset_id") or "")
            if not asset_id:
                continue
            candidates.append(MediaCandidate(
                provider=self.name, provider_asset_id=asset_id,
                asset_id=f"{self.name}_vid_{asset_id}", query=query,
                description=info.get("description", ""),
                width=int(rendition.get("width") or 0), height=int(rendition.get("height") or 0),
                duration=float(item.duration), url=item.url, source_page=info.get("source_page", ""),
                creator_name=creator.get("name", ""), creator_url=creator.get("url", ""),
                license_id=f"{self.name.title()} License",
                license_url="https://www.pexels.com/license/" if self.name == "pexels" else "https://pixabay.com/service/license-summary/",
            ))
        return candidates
