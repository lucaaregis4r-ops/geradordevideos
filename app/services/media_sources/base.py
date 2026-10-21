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
