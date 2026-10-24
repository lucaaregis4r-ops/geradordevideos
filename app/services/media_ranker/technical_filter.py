"""Technical Filter and Pre-Ranker (First cheap filter).

Filters and scores media candidates based on:
1. Aspect ratio / Orientation (prefer vertical 9:16 portrait)
2. Resolution (prefer >= 1080x1920)
3. Duration (must cover or loop well over the scene duration)
4. Bitrate / format compatibility
"""

from __future__ import annotations
from typing import List

from .schemas import MediaCandidate


def score_technical_candidate(
    candidate: MediaCandidate, target_duration: float = 4.0
) -> float:
    """Computes a technical score from 0.0 to 1.0 for a media candidate."""
    score = 0.5  # Base score

    # 1. Orientation & Aspect Ratio (weight: 0.30)
    w = candidate.width or 0
    h = candidate.height or 0
    ratio = w / h if h > 0 else 0.5625  # 9:16 = 0.5625

    if abs(ratio - 0.5625) < 0.05:
        # Native 9:16 vertical
        score += 0.30
    elif ratio < 1.0:
        # Other portrait ratio (e.g. 4:5, 3:4)
        score += 0.20
    elif abs(ratio - 1.0) < 0.05:
        # Square
        score += 0.10
    else:
        # Landscape video (will need heavy center crop)
        score += 0.0

    # 2. Resolution (weight: 0.15)
    if min(w, h * 9 / 16) >= 1080 and min(h, w * 16 / 9) >= 1920:
        score += 0.15
    elif min(w, h * 9 / 16) >= 720 and min(h, w * 16 / 9) >= 1280:
        score += 0.10
    else:
        score += 0.0

    # 3. Duration match (weight: 0.15)
    dur = candidate.duration
    if dur <= 0:
        # Static image or unknown
        score += 0.05
    elif dur >= target_duration:
        # Fully covers the spoken scene without looping
        score += 0.15
    elif dur >= target_duration * 0.7:
        score += 0.10
    else:
        # Too short, will need multiple loops
        score += 0.02

    # Clamp between 0.0 and 1.0
    return min(1.0, max(0.0, round(score, 3)))


def rank_and_filter_candidates(
    candidates: List[MediaCandidate],
    target_duration: float = 4.0,
    top_k: int = 10,
    prefer_video: bool = False,
) -> List[MediaCandidate]:
    """Scores all candidates technically and returns the top_k best candidates."""
    for c in candidates:
        c.technical_score = score_technical_candidate(c, target_duration)
        # In Sprint 3 before multimodal ranking, final_score = technical_score
        c.final_score = c.technical_score

    # Sort descending by technical score
    sorted_candidates = sorted(candidates, key=lambda c: c.technical_score, reverse=True)
    if prefer_video:
        # Reserve room for actual footage, including unmeasured provider metadata.
        # Do not let portrait photos eliminate landscape videos before semantics.
        videos = [c for c in sorted_candidates if c.media_type == "video" and not c.is_synthetic
                  and (c.duration <= 0 or c.duration >= target_duration)]
        reserved = videos[:max(1, top_k // 2)]
        ids = {id(c) for c in reserved}
        return (reserved + [c for c in sorted_candidates if id(c) not in ids])[:top_k]
    return sorted_candidates[:top_k]
