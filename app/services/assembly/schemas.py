"""Assembly Plan and Quality Score schemas.

Defines the intermediate representation between scene direction and video render.
The AssemblyPlan is a complete, reviewable blueprint of what the video will contain
*before* any rendering occurs. The QualityScore provides pass/fail gating metrics.
"""

from __future__ import annotations
from dataclasses import asdict, dataclass, field
import json
from typing import Any, Optional


@dataclass
class AssemblySegment:
    """A single visual segment in the final video timeline.

    Maps one Scene to a concrete asset, timing, overlay and transition.
    """
    segment_id: str
    start: float
    end: float
    asset_id: str
    asset_type: str               # video|photo|gif|graphic|text_card|screenshot|meme
    asset_path: str
    crop: str = "9:16"
    overlay_text: Optional[str] = None
    text_level: str = "caption"   # title|emphasis|caption
    transition: str = "cut"       # cut|fade|dissolve
    purpose: str = "explanation"  # narrative_function of the source scene
    scene_ref: str = ""           # scene_id this segment belongs to
    is_callback: bool = False     # True when asset is deliberately reused
    query: str = ""
    semantic_score: float = 0.0
    thumbnail: str = ""
    phase: str = ""
    is_synthetic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AssemblySegment:
        return cls(
            segment_id=data["segment_id"],
            start=float(data["start"]),
            end=float(data["end"]),
            asset_id=data["asset_id"],
            asset_type=data.get("asset_type", "video"),
            asset_path=data["asset_path"],
            crop=data.get("crop", "9:16"),
            overlay_text=data.get("overlay_text"),
            text_level=data.get("text_level", "caption"),
            transition=data.get("transition", "cut"),
            purpose=data.get("purpose", "explanation"),
            scene_ref=data.get("scene_ref", ""),
            is_callback=bool(data.get("is_callback", False)),
            query=data.get("query", ""),
            semantic_score=float(data.get("semantic_score", 0.0)),
            thumbnail=data.get("thumbnail", ""),
            phase=data.get("phase", ""),
            is_synthetic=bool(data.get("is_synthetic", False)),
        )


@dataclass
class QualityScore:
    """Pre-render quality metrics for an AssemblyPlan."""
    asset_count: int = 0
    duplicate_assets: int = 0
    semantic_match_avg: float = 0.0
    visual_diversity: float = 0.0
    text_safe_area_errors: int = 0
    low_resolution_count: int = 0
    segments_without_visual: int = 0
    synthetic_assets: int = 0
    consecutive_treatment_violations: int = 0
    passed: bool = False
    alerts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QualityScore:
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


@dataclass
class AssemblyPlan:
    """Complete, reviewable blueprint of a video before rendering.

    Generated after scene direction + media search + ranking + deduplication.
    Must pass quality gating before the render engine processes it.
    """
    project_id: str
    segments: list[AssemblySegment] = field(default_factory=list)
    total_duration: float = 0.0
    quality_score: Optional[QualityScore] = None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "project_id": self.project_id,
            "segments": [s.to_dict() for s in self.segments],
            "total_duration": self.total_duration,
        }
        if self.quality_score is not None:
            d["quality_score"] = self.quality_score.to_dict()
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AssemblyPlan:
        segments = [AssemblySegment.from_dict(s) for s in data.get("segments", [])]
        qs_data = data.get("quality_score")
        qs = QualityScore.from_dict(qs_data) if qs_data else None
        return cls(
            project_id=data["project_id"],
            segments=segments,
            total_duration=float(data.get("total_duration", 0.0)),
            quality_score=qs,
        )

    @classmethod
    def from_json(cls, text: str) -> AssemblyPlan:
        return cls.from_dict(json.loads(text))

    # --- Convenience helpers ---

    @property
    def asset_ids(self) -> list[str]:
        return [s.asset_id for s in self.segments]

    @property
    def unique_asset_count(self) -> int:
        return len(set(self.asset_ids))

    @property
    def duplicate_count(self) -> int:
        ids = self.asset_ids
        non_callback = [s.asset_id for s in self.segments if not s.is_callback]
        return len(non_callback) - len(set(non_callback))
