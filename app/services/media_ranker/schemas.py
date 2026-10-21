"""Media Candidate schemas for Media Searcher and Ranker.

Defines the structure for candidate stock and local assets according to Section 12.
"""

from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any, Optional


@dataclass
class MediaCandidate:
    provider: str = "unknown"
    asset_id: str = ""
    query: str = ""
    width: int = 1080
    height: int = 1920
    duration: float = 0.0
    url: str = ""
    thumbnail: str = ""
    source_page: str = ""
    technical_score: float = 0.0
    semantic_score: float = 0.0
    final_score: float = 0.0
    category: str = ""
    local_path: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MediaCandidate:
        return cls(
            provider=data.get("provider", "unknown"),
            asset_id=str(data.get("asset_id", "")),
            query=data.get("query", ""),
            width=int(data.get("width", 1080)),
            height=int(data.get("height", 1920)),
            duration=float(data.get("duration", 0.0)),
            url=data.get("url", ""),
            thumbnail=data.get("thumbnail", ""),
            source_page=data.get("source_page", ""),
            technical_score=float(data.get("technical_score", 0.0)),
            semantic_score=float(data.get("semantic_score", 0.0)),
            final_score=float(data.get("final_score", 0.0)),
            local_path=data.get("local_path"),
        )
