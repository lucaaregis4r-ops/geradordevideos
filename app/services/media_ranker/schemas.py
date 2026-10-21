"""Media Candidate schemas for Media Searcher and Ranker.

Defines the structure for candidate stock and local assets according to Section 12.
"""

from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any, Optional


@dataclass
class MediaCandidate:
    provider: str = "unknown"
    provider_asset_id: str = ""
    asset_id: str = ""
    query: str = ""
    width: int = 1080
    height: int = 1920
    duration: float = 0.0
    url: str = ""
    thumbnail: str = ""
    source_page: str = ""
    media_type: str = "video"
    creator_name: str = ""
    creator_url: str = ""
    license_id: str = ""
    license_url: str = ""
    content_hash: str = ""
    perceptual_hash: str = ""
    technical_score: float = 0.0
    visual_quality_score: float = 0.0
    semantic_score: float = 0.0
    final_score: float = 0.0
    category: str = ""
    local_path: Optional[str] = None
    is_synthetic: bool = False
    error_detail: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MediaCandidate:
        return cls(
            provider=data.get("provider", "unknown"),
            provider_asset_id=str(data.get("provider_asset_id", "")),
            asset_id=str(data.get("asset_id", "")),
            query=data.get("query", ""),
            width=int(data.get("width", 1080)),
            height=int(data.get("height", 1920)),
            duration=float(data.get("duration", 0.0)),
            url=data.get("url", ""),
            thumbnail=data.get("thumbnail", ""),
            source_page=data.get("source_page", ""),
            media_type=data.get("media_type", "video"),
            creator_name=data.get("creator_name", ""),
            creator_url=data.get("creator_url", ""),
            license_id=data.get("license_id", ""),
            license_url=data.get("license_url", ""),
            content_hash=data.get("content_hash", ""),
            perceptual_hash=data.get("perceptual_hash", ""),
            technical_score=float(data.get("technical_score", 0.0)),
            visual_quality_score=float(data.get("visual_quality_score", 0.0)),
            semantic_score=float(data.get("semantic_score", 0.0)),
            final_score=float(data.get("final_score", 0.0)),
            category=data.get("category", ""),
            local_path=data.get("local_path"),
            is_synthetic=bool(data.get("is_synthetic", False)),
            error_detail=data.get("error_detail"),
        )
