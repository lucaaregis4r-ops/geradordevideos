"""Assembly Planner — builds an AssemblyPlan from a directed ScenePlan.

Transforms the output of SceneDirector + MediaSearcher into a concrete,
reviewable timeline of segments with assets, timings, overlays and transitions.

This is the critical intermediate step that was missing from the original
pipeline: instead of going directly from search results to render, we now
produce a complete blueprint that can be inspected, validated, and edited
before any video is rendered.
"""

from __future__ import annotations
import logging
from typing import Optional

from app.services.director.schemas import Scene, ScenePlan
from app.services.media_ranker.deduplicator import MediaDeduplicator
from .schemas import AssemblyPlan, AssemblySegment

logger = logging.getLogger(__name__)


class AssemblyPlanner:
    """Builds an AssemblyPlan from a ScenePlan whose scenes have selected_media."""

    def __init__(self, deduplicator: Optional[MediaDeduplicator] = None):
        self._dedup = deduplicator or MediaDeduplicator()

    def build_plan(self, scene_plan: ScenePlan) -> AssemblyPlan:
        """Converts a ScenePlan into an AssemblyPlan.

        Each scene becomes one AssemblySegment. The planner:
        1. Reads the selected_media from each scene
        2. Applies deduplication scoring
        3. Adjusts timing based on narrative function
        4. Sets overlay text and level from scene metadata
        5. Marks callbacks
        """
        segments: list[AssemblySegment] = []
        current_time = 0.0

        for scene in scene_plan.scenes:
            segment = self._scene_to_segment(scene, current_time)
            segments.append(segment)
            current_time = segment.end

        total_duration = current_time if segments else 0.0

        plan = AssemblyPlan(
            project_id=scene_plan.script_id,
            segments=segments,
            total_duration=total_duration,
        )

        self._validate_no_involuntary_duplicates(plan)
        return plan

    def _scene_to_segment(self, scene: Scene, start_time: float) -> AssemblySegment:
        """Converts a single Scene into an AssemblySegment."""
        media = scene.selected_media or {}
        asset_id = media.get("asset_id", media.get("url", f"missing_{scene.scene_id}"))
        asset_path = media.get("local_path", media.get("url", ""))
        asset_type = self._resolve_asset_type(scene, media)

        # Duration: prefer duration_hint from narrative classification,
        # fall back to audio-measured duration, then default
        duration = self._compute_duration(scene)
        end_time = start_time + duration

        # Detect intentional callback
        is_callback = bool(scene.intentional_callback)

        # Record usage in deduplicator
        category = self._infer_visual_category(scene)
        if media:
            from app.services.media_ranker.schemas import MediaCandidate
            dummy = MediaCandidate(
                asset_id=asset_id,
                url=media.get("url", ""),
                query=scene.queries[0] if scene.queries else "",
            )
            self._dedup.mark_used(
                candidate=dummy,
                scene_id=scene.scene_id,
                visual_category=category,
            )

        query = media.get("query", scene.queries[0] if scene.queries else "")
        semantic_score = float(media.get("semantic_score", media.get("final_score", 0.0)))
        thumbnail = media.get("thumbnail", "")
        phase = getattr(scene, "narrative_phase", "")
        is_synthetic = bool(media.get("is_synthetic", False))

        return AssemblySegment(
            segment_id=f"seg_{scene.scene_id}",
            start=round(start_time, 2),
            end=round(end_time, 2),
            asset_id=asset_id,
            asset_type=asset_type,
            asset_path=asset_path,
            crop="9:16",
            overlay_text=scene.text_overlay,
            text_level=scene.text_level,
            transition=self._choose_transition(scene),
            purpose=scene.narrative_function,
            scene_ref=scene.scene_id,
            is_callback=is_callback,
            query=query,
            semantic_score=semantic_score,
            thumbnail=thumbnail,
            phase=phase,
            is_synthetic=is_synthetic,
        )

    def _compute_duration(self, scene: Scene) -> float:
        """Determines segment duration based on narrative function and content."""
        # Humor: keep it short (≤ 1.5s)
        if scene.humor or scene.narrative_function == "joke":
            if scene.start is not None and scene.end is not None and scene.end > scene.start:
                return min(float(scene.end - scene.start), 1.5)
            return min(scene.duration_hint, 1.5)

        # Audio-measured duration takes priority if available
        overlay = scene.overlay or {}
        audio_duration = overlay.get("audio_duration")
        if audio_duration and isinstance(audio_duration, (int, float)):
            return float(audio_duration)

        # Pre-timed scene from director
        if scene.start is not None and scene.end is not None and scene.end > scene.start:
            return float(scene.end - scene.start)

        # Title/transition: brief
        if scene.narrative_function in ("transition",):
            return min(scene.duration_hint, 2.0)

        # Concepts and reveals can be longer
        if scene.narrative_function in ("concept", "reveal", "conclusion"):
            return max(scene.duration_hint, 3.5)

        # Default: use the hint
        return max(1.5, scene.duration_hint)

    def _resolve_asset_type(self, scene: Scene, media: dict) -> str:
        """Determines the asset type from scene metadata and media info."""
        # If media has an explicit type, use it
        if media.get("type"):
            return media["type"]
        # Map visual_type to asset_type
        vt = scene.visual_type.lower()
        mapping = {
            "stock_video": "video",
            "stock_image": "photo",
            "gif": "gif",
            "graphic": "graphic",
            "formula": "text_card",
            "number": "text_card",
            "quote": "text_card",
            "title": "text_card",
            "screenshot": "screenshot",
            "meme": "meme",
            "map": "graphic",
            "generated_image": "photo",
            "illustration": "graphic",
            "advertisement": "photo",
        }
        return mapping.get(vt, "video")

    def _choose_transition(self, scene: Scene) -> str:
        """Selects transition type based on narrative function."""
        if scene.narrative_function in ("reveal", "contrast"):
            return "cut"  # Hard cuts for impact
        if scene.narrative_function in ("transition", "conclusion"):
            return "fade"
        return "cut"

    def _infer_visual_category(self, scene: Scene) -> str:
        """Infers a broad visual category from scene entities and function."""
        entities = scene.entities
        if not entities:
            return scene.narrative_function

        # Map common entities to categories
        category_map = {
            "dinheiro": "money", "preço": "money", "reais": "money",
            "real": "money", "valor": "money", "custo": "money",
            "fábrica": "production", "máquina": "production", "indústria": "production",
            "trabalho": "labor", "trabalhador": "labor", "operário": "labor",
            "costura": "labor", "costureira": "labor",
            "loja": "market", "mercado": "market", "shopping": "market",
            "supermercado": "market", "prateleira": "market",
            "camiseta": "object", "celular": "object", "café": "object",
            "carro": "aspirational", "dubai": "aspirational", "luxo": "aspirational",
            "riqueza": "aspirational", "executivo": "aspirational",
            "algodão": "raw_material", "matéria-prima": "raw_material",
            "caminhão": "logistics", "transporte": "logistics", "contêiner": "logistics",
        }
        for entity in entities:
            cat = category_map.get(entity.lower())
            if cat:
                return cat
        return scene.narrative_function

    def _validate_no_involuntary_duplicates(self, plan: AssemblyPlan) -> None:
        """Logs warnings for any unintentional asset reuse."""
        seen: dict[str, str] = {}
        for seg in plan.segments:
            if seg.is_callback:
                continue
            if seg.asset_id in seen:
                logger.warning(
                    "Involuntary duplicate: asset %s in segments %s and %s",
                    seg.asset_id, seen[seg.asset_id], seg.segment_id,
                )
            else:
                seen[seg.asset_id] = seg.segment_id
