"""Media Sources Manager.

Coordinates multiple media providers (Pexels, Wikimedia Commons, Openverse)
with fallback strategies, timeout isolation, and provenance metadata tracking.
"""

from __future__ import annotations
from typing import List, Optional

from loguru import logger

from app.services.media_ranker.schemas import MediaCandidate
from .base import MediaSourceProvider
from .openverse import OpenverseProvider
from .pexels_photos import PexelsPhotoProvider
from .pixabay_photos import PixabayPhotoProvider
from .wikimedia_commons import WikimediaCommonsProvider


class MediaSourcesManager:
    """Orchestrates photo and archive searches across multiple external sources."""

    def __init__(self, providers: Optional[List[MediaSourceProvider]] = None):
        if providers is not None:
            self.providers = providers
        else:
            self.providers = [
                PixabayPhotoProvider(),
                PexelsPhotoProvider(),
                WikimediaCommonsProvider(),
                OpenverseProvider(),
            ]

    def search_photos(
        self,
        query: str,
        aspect: str = "portrait",
        limit_per_provider: int = 5,
    ) -> List[MediaCandidate]:
        """Queries all available photo/archive providers and returns merged candidates."""
        results: List[MediaCandidate] = []

        for provider in self.providers:
            if not provider.is_available():
                continue

            try:
                candidates = provider.search(
                    query=query,
                    media_type="image",
                    aspect=aspect,
                    limit=limit_per_provider,
                )
                results.extend(candidates)
            except Exception as e:
                logger.warning("Provider '{}' failed searching for '{}': {}", provider.name, query, e)

        return results
