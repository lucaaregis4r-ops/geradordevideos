"""Candidate deduplication and diversity manager.

Ensures no scene receives duplicate URLs or asset IDs, and avoids reusing the
same footage in multiple scenes within the same video production.

Extended in v0.2 with:
- Gradual penalties (exact match, category similarity)
- Per-scene usage history
- Intentional callback bypass
- Visual category tracking for conceptual diversity
"""

from __future__ import annotations
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .perceptual_hash import hamming_distance
from .schemas import MediaCandidate


class MediaDeduplicator:
    def __init__(self, project_id: Optional[str] = None):
        self.project_id = project_id
        self._global_seen_assets: Set[str] = set()
        # Perceptual hash tracking: list of (phash, asset_key, scene_id)
        self._seen_perceptual_hashes: List[Tuple[str, str, str]] = []
        # Creator diversity tracking (max 2 assets per author across the video)
        self._creator_usage: Dict[str, int] = defaultdict(int)
        # Track which visual categories have been used and how recently
        self._category_usage: Dict[str, int] = defaultdict(int)
        # Track per-scene assignments for callback detection
        self._scene_asset_map: Dict[str, str] = {}
        # Assets explicitly marked as forbidden
        self._blocked_assets: Set[str] = set()

    def deduplicate_within_scene(
        self, candidates: Iterable[MediaCandidate]
    ) -> List[MediaCandidate]:
        """Removes duplicates based on url, asset_id, or local_path within a single query/scene."""
        seen_keys: Set[str] = set()
        unique: List[MediaCandidate] = []

        for c in candidates:
            key = c.asset_id or c.url or c.local_path or ""
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            unique.append(c)

        return unique

    def filter_globally_unused(
        self, candidates: List[MediaCandidate]
    ) -> List[MediaCandidate]:
        """Separates candidates that haven't been picked by other scenes yet."""
        fresh = [c for c in candidates if (c.asset_id or c.url) not in self._global_seen_assets]
        return fresh if fresh else candidates

    def find_perceptual_duplicate(
        self, phash: str, max_distance: int = 8
    ) -> Optional[Tuple[str, str, int]]:
        """Checks if a perceptual hash is close to any previously selected asset.

        Returns (seen_asset_key, seen_scene_id, distance) if found, else None.
        """
        if not phash:
            return None
        for seen_hash, seen_key, seen_scene in self._seen_perceptual_hashes:
            dist = hamming_distance(phash, seen_hash)
            if dist <= max_distance:
                return (seen_key, seen_scene, dist)
        return None

    def score_candidates(
        self,
        candidates: List[MediaCandidate],
        visual_category: str = "",
        intentional_callback: Optional[str] = None,
        max_perceptual_distance: int = 8,
    ) -> List[MediaCandidate]:
        """Applies graduated repetition penalties to candidate scores.

        Penalty tiers:
        - Exact asset reuse:         final_score *= 0.1   (near-zero)
        - Perceptual duplicate:      final_score *= 0.05  (visually identical clip)
        - Creator cap (>=2 uses):    final_score *= 0.2   (author variety rule)
        - Same visual category:      final_score *= 0.5   (discouraged)
        - Blocked asset:             filtered out entirely

        Intentional callbacks bypass all penalties.
        """
        if intentional_callback and intentional_callback in self._scene_asset_map:
            # Callback mode: promote the exact asset from the referenced scene
            callback_asset = self._scene_asset_map[intentional_callback]
            for c in candidates:
                key = c.asset_id or c.url
                if key == callback_asset:
                    c.final_score = max(c.final_score, 0.95)
            return candidates

        scored: List[MediaCandidate] = []
        for c in candidates:
            key = c.asset_id or c.url or ""

            # Block list: skip entirely
            if key in self._blocked_assets:
                continue

            # 1. Exact reuse penalty
            if key in self._global_seen_assets:
                c.final_score *= 0.1

            # 2. Perceptual duplicate penalty
            elif c.perceptual_hash and self.find_perceptual_duplicate(c.perceptual_hash, max_distance=max_perceptual_distance):
                c.final_score *= 0.05

            # 3. Creator diversity penalty (Hard Constraint 3: max 2 assets per author across video)
            elif c.creator_name and self._creator_usage.get(c.creator_name.lower(), 0) >= 2:
                c.final_score *= 0.2

            # 4. Category similarity penalty: applies if candidate matches the used category
            elif visual_category and self._category_usage.get(visual_category, 0) > 0:
                cand_cat = getattr(c, "category", "") or ""
                is_same_category = (
                    cand_cat == visual_category
                    if cand_cat
                    else (visual_category.lower() in f"{c.query} {c.asset_id}".lower())
                )
                if is_same_category:
                    recency = self._category_usage[visual_category]
                    # More recent usage = heavier penalty
                    penalty = max(0.5, 1.0 - (0.1 * recency))
                    c.final_score *= penalty

            scored.append(c)

        return scored

    def mark_used(
        self,
        candidate: MediaCandidate,
        scene_id: str = "",
        visual_category: str = "",
    ) -> None:
        """Records that a candidate has been selected for a scene."""
        key = candidate.asset_id or candidate.url
        if key:
            self._global_seen_assets.add(key)

        if candidate.perceptual_hash:
            self._seen_perceptual_hashes.append(
                (candidate.perceptual_hash, key or "", scene_id)
            )

        if candidate.creator_name:
            self._creator_usage[candidate.creator_name.lower()] += 1

        if scene_id:
            self._scene_asset_map[scene_id] = key or ""

        if visual_category:
            self._category_usage[visual_category] += 1

    def is_used(self, asset_id: str) -> bool:
        """Returns True if the asset or key has been marked as used."""
        return asset_id in self._global_seen_assets

    def block_asset(self, asset_id: str) -> None:
        """Permanently blocks an asset from being selected in this production."""
        self._blocked_assets.add(asset_id)

    def reset(self) -> None:
        """Clears all tracking state (use between separate video productions)."""
        self._global_seen_assets.clear()
        self._seen_perceptual_hashes.clear()
        self._creator_usage.clear()
        self._category_usage.clear()
        self._scene_asset_map.clear()
        self._blocked_assets.clear()

    # --- Diagnostics ---

    @property
    def used_asset_count(self) -> int:
        return len(self._global_seen_assets)

    @property
    def category_distribution(self) -> Dict[str, int]:
        return dict(self._category_usage)

    def get_callback_asset(self, scene_id: str) -> Optional[str]:
        """Returns the asset_id assigned to a scene, for callback lookups."""
        return self._scene_asset_map.get(scene_id)
