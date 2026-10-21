"""Schemas for Scene Director.

Defines the central Scene and ScenePlan structures according to the specification.
"""

from __future__ import annotations
from dataclasses import asdict, dataclass, field
from enum import Enum
import json
from typing import Any, Optional


class NarrativeFunction(str, Enum):
    """Classifies the rhetorical purpose of a scene segment."""
    HOOK = "hook"
    SETUP = "setup"
    EXAMPLE = "example"
    EXPLANATION = "explanation"
    CONCEPT = "concept"
    CONTRAST = "contrast"
    JOKE = "joke"
    REVEAL = "reveal"
    TRANSITION = "transition"
    CONCLUSION = "conclusion"


class NarrativePhase(str, Enum):
    """Tracks the visual/tonal progression of the video argument across 5 dramatic acts."""
    # Canonical 5 acts from editorial report
    PROMESSA = "promessa"        # Ato 1 — Promessa / Aspiration
    OBJETO = "objeto"            # Ato 2 — Objeto / Commodity
    BASTIDORES = "bastidores"    # Ato 3 — Bastidores / Production
    REVELACAO = "revelacao"      # Ato 4 — Revelação / Labor
    FECHAMENTO = "fechamento"    # Ato 5 — Fechamento / Conclusion

    # Compatibility aliases
    ASPIRATION = "aspiration"
    COMMODITY = "commodity"
    PRODUCTION = "production"
    LABOR = "labor"
    REVEAL = "reveal"


class TextLevel(str, Enum):
    """Typographic hierarchy for on-screen text overlays."""
    TITLE = "title"          # 1-5 words, huge
    EMPHASIS = "emphasis"    # short phrase, medium
    CAPTION = "caption"      # subtitle-style, small


class VisualType(str, Enum):
    STOCK_VIDEO = "stock_video"
    STOCK_IMAGE = "stock_image"
    LOCAL_MEDIA = "local_media"
    ARCHIVE = "archive"
    GRAPHIC = "graphic"
    FORMULA = "formula"
    MAP = "map"
    QUOTE = "quote"
    NUMBER = "number"
    TITLE = "title"
    GENERATED_IMAGE = "generated_image"
    GIF = "gif"
    SCREENSHOT = "screenshot"
    MEME = "meme"
    ILLUSTRATION = "illustration"
    ADVERTISEMENT = "advertisement"


class MotionType(str, Enum):
    NONE = "none"
    LATERAL = "lateral"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    PAN_UP = "pan_up"
    PAN_DOWN = "pan_down"
    STATIC = "static"


@dataclass
class Scene:
    scene_id: str
    narration: str
    intent: str
    queries: list[str]
    visual_type: str = "stock_video"
    preferred_motion: str = "lateral"
    start: Optional[float] = None
    end: Optional[float] = None
    overlay: Optional[dict[str, Any]] = None
    media_candidates: list[dict[str, Any]] = field(default_factory=list)
    selected_media: Optional[dict[str, Any]] = None
    confidence: float = 0.0
    # --- Editorial / narrative fields (v0.2+) ---
    narrative_function: str = "explanation"
    narrative_phase: str = "commodity"
    importance: int = 3
    text_overlay: Optional[str] = None
    text_level: str = "caption"
    humor: bool = False
    intentional_callback: Optional[str] = None
    entities: list[str] = field(default_factory=list)
    duration_hint: float = 3.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Scene:
        # Normalize visual_type & preferred_motion to strings
        v_type = data.get("visual_type", "stock_video")
        if isinstance(v_type, VisualType):
            v_type = v_type.value
        m_type = data.get("preferred_motion", "lateral")
        if isinstance(m_type, MotionType):
            m_type = m_type.value

        return cls(
            scene_id=data["scene_id"],
            narration=data["narration"],
            intent=data.get("intent", ""),
            queries=list(data.get("queries", [])),
            visual_type=str(v_type).lower(),
            preferred_motion=str(m_type).lower(),
            start=data.get("start"),
            end=data.get("end"),
            overlay=data.get("overlay"),
            media_candidates=data.get("media_candidates", []),
            selected_media=data.get("selected_media"),
            confidence=float(data.get("confidence", 0.0)),
            # Editorial fields with safe defaults
            narrative_function=str(data.get("narrative_function", "explanation")).lower(),
            narrative_phase=str(data.get("narrative_phase", "commodity")).lower(),
            importance=int(data.get("importance", 3)),
            text_overlay=data.get("text_overlay"),
            text_level=str(data.get("text_level", "caption")).lower(),
            humor=bool(data.get("humor", False)),
            intentional_callback=data.get("intentional_callback"),
            entities=list(data.get("entities", [])),
            duration_hint=float(data.get("duration_hint", 3.0)),
        )


@dataclass
class ScenePlan:
    script_id: str
    script_version: str
    script_hash: str
    total_scenes: int
    estimated_duration: float
    scenes: list[Scene]
    brand_preset: str = "editorial"
    created_at: str = ""
    title: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "script_id": self.script_id,
            "script_version": self.script_version,
            "script_hash": self.script_hash,
            "total_scenes": self.total_scenes,
            "estimated_duration": self.estimated_duration,
            "scenes": [s.to_dict() for s in self.scenes],
            "brand_preset": self.brand_preset,
            "created_at": self.created_at,
            "title": self.title,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScenePlan:
        scenes = [Scene.from_dict(s) for s in data.get("scenes", [])]
        return cls(
            script_id=data["script_id"],
            script_version=data["script_version"],
            script_hash=data["script_hash"],
            total_scenes=len(scenes),
            estimated_duration=float(data.get("estimated_duration", 0.0)),
            scenes=scenes,
            brand_preset=data.get("brand_preset", "editorial"),
            created_at=data.get("created_at", ""),
            title=data.get("title", ""),
        )
