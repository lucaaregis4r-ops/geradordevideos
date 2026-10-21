"""Media Searcher: Orchestrates candidate searching and selection for all scenes.

Implements the end-to-end pipeline:
ScenePlan -> Queries -> CandidateBuilder -> Deduplicator -> Technical Filter -> Top Candidates -> Project Manifest.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from app.services import material
from app.services.director.schemas import Scene, ScenePlan
from .candidate_builder import CandidateBuilder
from .deduplicator import MediaDeduplicator
from .schemas import MediaCandidate
from .semantic_ranker import SemanticRanker
from .smart_library import SmartLibrary
from .technical_filter import rank_and_filter_candidates

if TYPE_CHECKING:
    from app.services.graphics.graphics_engine import GraphicsEngine


class MediaSearcher:
    def __init__(
        self,
        candidate_builder: Optional[CandidateBuilder] = None,
        smart_library: Optional[SmartLibrary] = None,
        semantic_ranker: Optional[SemanticRanker] = None,
        graphics_engine: Optional[Any] = None,
        media_cache_dir: str | Path = "storage/media_cache",
    ):
        self.media_cache_dir = Path(media_cache_dir).resolve()
        self.candidate_builder = candidate_builder or CandidateBuilder(
            media_cache_dir=self.media_cache_dir
        )
        self.smart_library = smart_library or SmartLibrary(
            library_dir=self.media_cache_dir
        )
        self.semantic_ranker = semantic_ranker or SemanticRanker()
        if graphics_engine is None:
            from app.services.graphics.graphics_engine import GraphicsEngine
            self.graphics_engine = GraphicsEngine(cache_dir=self.media_cache_dir / "graphics")
        else:
            self.graphics_engine = graphics_engine
        self.deduplicator = MediaDeduplicator()

    def search_for_scene(
        self,
        scene: Scene,
        target_duration: float = 4.0,
        candidates_per_scene: int = 5,
    ) -> list[MediaCandidate]:
        """Searches across all queries for a single scene and returns top candidates."""
        all_raw_candidates: list[MediaCandidate] = []

        # 0. Check smart library first (acervo próprio aprovado)
        for q in scene.queries:
            lib_matches = self.smart_library.search_library(
                query=f"{q} {scene.intent}",
                target_duration=target_duration,
            )
            all_raw_candidates.extend(lib_matches)

        # 1. Run each query through candidate builder (external stock + local cache)
        for q in scene.queries:
            raw = self.candidate_builder.search_query(
                query=q,
                target_duration=target_duration,
                visual_type=scene.visual_type,
                preferred_motion=scene.preferred_motion,
            )
            all_raw_candidates.extend(raw)

        # 2. Deduplicate within scene
        deduped = self.deduplicator.deduplicate_within_scene(all_raw_candidates)

        # 3. Prefer candidates not yet used globally
        fresh = self.deduplicator.filter_globally_unused(deduped)

        # 4. First stage: technical filter (take up to 10 candidates)
        tech_filtered = rank_and_filter_candidates(
            candidates=fresh,
            target_duration=target_duration,
            top_k=max(10, candidates_per_scene * 2),
        )

        # 5. Second stage: semantic multimodal ranker (take top candidates_per_scene * 2)
        sem_ranked = self.semantic_ranker.rank_candidates(
            scene_narration=scene.narration,
            scene_intent=scene.intent,
            candidates=tech_filtered,
            top_k=max(10, candidates_per_scene * 2),
        )

        # 5b. Repetition & diversity scoring with callback bypass
        visual_cat = scene.entities[0] if getattr(scene, "entities", None) else getattr(scene, "narrative_function", "")
        scored = self.deduplicator.score_candidates(
            candidates=sem_ranked,
            visual_category=visual_cat,
            intentional_callback=getattr(scene, "intentional_callback", None),
        )
        scored.sort(key=lambda c: c.final_score, reverse=True)
        sem_ranked = scored[:candidates_per_scene]

        # 6. If scene is graphic/formula/number/quote, prepend programmatic card as #1 candidate
        if self.graphics_engine.is_graphic_scene(scene):
            try:
                card_cand = self.graphics_engine.create_card_candidate(
                    scene=scene,
                    duration=target_duration,
                )
                sem_ranked.insert(0, card_cand)
                sem_ranked = sem_ranked[:candidates_per_scene]
            except Exception:
                pass

        return sem_ranked

    def populate_scene_plan(
        self,
        plan: ScenePlan,
        candidates_per_scene: int = 5,
        download_selected: bool = True,
        save_plan_path: Optional[str | Path] = None,
    ) -> ScenePlan:
        """Enriches all scenes in the plan with media_candidates and a selected_media default."""
        for scene in plan.scenes:
            # Estimate scene duration if start/end exist, else default to 4.0s
            duration = (scene.end - scene.start) if (scene.start is not None and scene.end is not None) else 4.0
            candidates = self.search_for_scene(
                scene=scene,
                target_duration=duration,
                candidates_per_scene=candidates_per_scene,
            )

            # Store candidates in scene
            scene.media_candidates = [c.to_dict() for c in candidates]

            if candidates:
                top_candidate = candidates[0]
                visual_cat = scene.entities[0] if getattr(scene, "entities", None) else getattr(scene, "narrative_function", "")
                self.deduplicator.mark_used(
                    top_candidate,
                    scene_id=scene.scene_id,
                    visual_category=visual_cat,
                )

                # Download or stage locally if needed
                if download_selected and not top_candidate.local_path:
                    try:
                        # Remote URL download using material service
                        downloaded = material.save_video(
                            video_url=top_candidate.url,
                            save_dir=str(self.media_cache_dir),
                        )
                        top_candidate.local_path = downloaded
                    except Exception:
                        pass

                scene.selected_media = top_candidate.to_dict()

        if save_plan_path:
            p = Path(save_plan_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("w", encoding="utf-8") as f:
                f.write(plan.to_json(indent=2))

        return plan
