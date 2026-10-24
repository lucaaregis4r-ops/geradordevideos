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


class ComponentType(str, Enum):
    STANDARD = "standard"
    EDITORIAL_CROP = "editorial_crop"
    SPLIT_SCREEN = "split_screen"
    DATA_CARD = "data_card"
    PRICE_TAG = "price_tag"
    HISTORICAL_ARCHIVE = "historical_archive"


@dataclass
class VisualBeat:
    """A visual shot within a spoken narration scene.

    Allows a single spoken phrase (e.g. 7 seconds) to contain 2 or 3 distinct visual shots
    without splitting, hallucinating, or re-synthesizing the audio narration.
    """
    beat_id: str
    duration: float = 2.0
    intent: str = ""
    queries: list[str] = field(default_factory=list)
    visual_type: str = "stock_video"
    component_type: str = ComponentType.STANDARD.value     # standard, editorial_crop, split_screen, data_card, price_tag, historical_archive
    preferred_motion: str = "lateral"
    shot_scale: str = "medium"           # wide, medium, close_up, extreme_close_up
    text_overlay: Optional[str] = None
    text_level: str = "caption"
    transition: str = "cut"
    selected_media: Optional[dict[str, Any]] = None
    media_candidates: list[dict[str, Any]] = field(default_factory=list)

    subject: str = ""
    action: str = ""
    context: str = ""
    required_elements: list[str] = field(default_factory=list)
    forbidden_elements: list[str] = field(default_factory=list)
    preferred_media: str = "video"
    fallback_media: list[str] = field(default_factory=lambda: ["image"])
    temporal_context: str = ""
    continuity_group: str = ""
    status: str = "pending_media"
    search_attempts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VisualBeat:
        return cls(
            beat_id=data["beat_id"],
            duration=float(data.get("duration", 2.0)),
            intent=data.get("intent", ""),
            queries=list(data.get("queries", [])),
            visual_type=str(data.get("visual_type", "stock_video")).lower(),
            component_type=str(data.get("component_type", "standard")).lower(),
            preferred_motion=str(data.get("preferred_motion", "lateral")).lower(),
            shot_scale=str(data.get("shot_scale", "medium")).lower(),
            text_overlay=data.get("text_overlay"),
            text_level=str(data.get("text_level", "caption")).lower(),
            transition=str(data.get("transition", "cut")).lower(),
            selected_media=data.get("selected_media"),
            media_candidates=list(data.get("media_candidates", [])),
            subject=data.get("subject", ""),
            action=data.get("action", ""),
            context=data.get("context", ""),
            required_elements=data.get("required_elements", []),
            forbidden_elements=data.get("forbidden_elements", []),
            preferred_media=data.get("preferred_media", "video"),
            fallback_media=data.get("fallback_media", ["image"]),
            temporal_context=data.get("temporal_context", ""),
            continuity_group=data.get("continuity_group", ""),
            status=data.get("status", "pending_media"),
            search_attempts=list(data.get("search_attempts", [])),
        )


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
    visual_beats: list[VisualBeat] = field(default_factory=list)

    @property
    def has_multiple_beats(self) -> bool:
        return len(self.visual_beats) > 1

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["visual_beats"] = [b.to_dict() for b in self.visual_beats]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Scene:
        # Normalize visual_type & preferred_motion to strings
        v_type = data.get("visual_type", "stock_video")
        if isinstance(v_type, VisualType):
            v_type = v_type.value
        m_type = data.get("preferred_motion", "lateral")
        if isinstance(m_type, MotionType):
            m_type = m_type.value

        raw_beats = data.get("visual_beats", [])
        beats = [VisualBeat.from_dict(b) if isinstance(b, dict) else b for b in raw_beats]

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
            visual_beats=beats,
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
