"""Base interface for external media source providers.

Defines the contract for stock, archive, and open image/video providers.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Optional

from app.services.media_ranker.schemas import MediaCandidate


class MediaSourceProvider(ABC):
    """Abstract base class for all media providers."""

    @property
    def capabilities(self):
        return ProviderCapabilities()

    def resolve_asset(self, candidate: MediaCandidate) -> list[dict]:
        return [{"url": candidate.url, "media_type": candidate.media_type,
                 "width": candidate.width, "height": candidate.height, "duration": candidate.duration}]

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g. 'pexels_photos', 'wikimedia_commons', 'openverse')."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if provider has required API keys or is open."""
        pass

    @abstractmethod
    def search(
        self,
        query: str,
        media_type: str = "image",
        aspect: str = "portrait",
        limit: int = 10,
    ) -> List[MediaCandidate]:
        """Searches provider for assets matching query and requirements."""
        pass


from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderCapabilities:
    media_types: tuple[str, ...] = ("image",)
    supports_orientation: bool = False
    supports_duration: bool = False
    requires_credentials: bool = False


@dataclass(frozen=True)
class SearchRequest:
    query: str
    media_type: str = "video"
    orientations: tuple[str, ...] = ("portrait",)
    limit: int = 5
    duration: float = 3.0
    beat_id: str = ""
    include_archives: bool = False


@dataclass
class SearchResult:
    candidates: list[MediaCandidate] = field(default_factory=list)
    status: str = "empty_results"
    elapsed_ms: float = 0.0
    warnings: list[str] = field(default_factory=list)
    next_cursor: Optional[str] = None
    provider: str = ""
