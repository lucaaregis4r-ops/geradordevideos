"""Choose an interval inside a shot, preserving enough media for the spoken beat."""
from .shot_indexer import Shot


def select_clip(shots: list[Shot], duration: float) -> tuple[float, float]:
    for shot in shots:
        available = shot.source_out - shot.source_in
        if available + 1 / 30 < duration:
            continue
        margin = min(0.5, max(0.0, (available - duration) / 2))
        start = shot.source_in + margin
        return start, start + duration
    raise ValueError("no_shot_covers_beat")
