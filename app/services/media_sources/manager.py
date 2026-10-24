"""Media Sources Manager.

Coordinates multiple media providers (Pexels, Wikimedia Commons, Openverse)
with fallback strategies, timeout isolation, and provenance metadata tracking.
"""

from __future__ import annotations
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, wait
from time import monotonic
from copy import deepcopy
from dataclasses import replace
import requests

from loguru import logger

from app.services.media_ranker.schemas import MediaCandidate
from .base import MediaSourceProvider, ProviderCapabilities, SearchRequest, SearchResult
from .pexels_videos import PexelsVideoProvider
from .pixabay_videos import PixabayVideoProvider
from .coverr_videos import CoverrVideoProvider
from .mixkit import MixkitProvider
from .openverse import OpenverseProvider
from .internet_archive import InternetArchiveProvider
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
                PexelsVideoProvider(),
                PixabayVideoProvider(),
                CoverrVideoProvider(),
                MixkitProvider(),
                PixabayPhotoProvider(),
                PexelsPhotoProvider(),
                WikimediaCommonsProvider(),
                OpenverseProvider(),
                InternetArchiveProvider(),
            ]

        # Specialized archives are opt-in; avoid irrelevant NASA/LOC calls for every garment beat.
        if providers is None:
            from app.config import config
            if not config.app.get("editorial_mixkit_enabled", True):
                self.providers = [p for p in self.providers if p.name != "mixkit"]
            enabled = config.app.get("editorial_archive_providers", [])
            if "nasa" in enabled:
                from .nasa import NASAProvider
                self.providers.append(NASAProvider())
            if "loc" in enabled:
                from .loc import LibraryOfCongressProvider
                self.providers.append(LibraryOfCongressProvider())
        self._cache = {}
        self._retry_after = {}
        self._pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="media-search")
        self.last_attempts: list[SearchResult] = []

    def _search_provider(self, provider, request):
        start = monotonic()
        if not provider.is_available():
            return SearchResult(status="missing_credentials", provider=provider.name)
        if self._retry_after.get(provider.name, 0) > start:
            return SearchResult(status="rate_limited", provider=provider.name,
                                warnings=["retry_after_backoff"])
        if not getattr(provider, "capabilities", ProviderCapabilities()).supports_orientation:
            request = replace(request, orientations=("portrait",))
        key = (provider.name, request)
        cached = self._cache.get(key)
        if cached and cached[0] > start:
            return deepcopy(cached[1])
        try:
            candidates = provider.search(request.query, media_type=request.media_type,
                                         aspect=request.orientations[0], limit=request.limit)
            result = SearchResult(candidates, "ok" if candidates else "empty_results", provider=provider.name)
        except requests.Timeout:
            result = SearchResult(status="timeout", provider=provider.name)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if status == 429:
                try:
                    delay = max(1, min(3600, float(exc.response.headers.get("Retry-After", 5))))
                except (ValueError, TypeError):
                    delay = 5
                self._retry_after[provider.name] = monotonic() + delay
            result = SearchResult(status="rate_limited" if status == 429 else "authentication_failed" if status in (401, 403) else "provider_error", provider=provider.name)
        except Exception as exc:
            result = SearchResult(status="provider_error", warnings=[type(exc).__name__], provider=provider.name)
        result.elapsed_ms = (monotonic() - start) * 1000
        if result.status in {"ok", "empty_results"}:
            self._cache[key] = (monotonic() + (86400 if result.candidates else 900), deepcopy(result))
        return result

    def search(self, request: SearchRequest, timeout: float = 12.0) -> SearchResult:
        providers = [p for p in self.providers if request.media_type in getattr(p, "capabilities", ProviderCapabilities()).media_types
                     and (p.name != "internet_archive" or request.include_archives)]
        futures = {self._pool.submit(self._search_provider, p, request): p for p in providers}
        done, pending = wait(futures, timeout=timeout)
        attempts = [future.result() for future in futures if future in done]
        for future in pending:
            future.cancel()
            attempts.append(SearchResult(status="timeout", elapsed_ms=timeout * 1000, provider=futures[future].name))
        self.last_attempts = attempts
        candidates = [c for a in attempts for c in a.candidates]
        return SearchResult(candidates, "ok" if candidates else "pending_media",
                            warnings=[f"{a.provider}:{a.status}" for a in attempts])

    def search_photos(self, query: str, aspect: str = "portrait", limit_per_provider: int = 5) -> List[MediaCandidate]:
        return self.search(SearchRequest(query, "image", (aspect,), limit_per_provider)).candidates
