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
from loguru import logger
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
        asset_catalog: Optional[Any] = None,
        enable_synthetic_fallback: bool = False,
    ):
        self.media_cache_dir = Path(media_cache_dir).resolve()
        self.enable_synthetic_fallback = enable_synthetic_fallback
        if asset_catalog is None:
            from .asset_catalog import AssetCatalog
            self.asset_catalog = AssetCatalog(db_path=self.media_cache_dir.parent / "asset_catalog.db")
        else:
            self.asset_catalog = asset_catalog
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
        from .visual_evaluator import VisualEvaluator
        self.visual_evaluator = VisualEvaluator(temp_dir=self.media_cache_dir / "eval_frames")
        self.deduplicator = MediaDeduplicator()

    def reset(self) -> None:
        """Resets deduplicator and internal tracking state between production runs."""
        self.deduplicator.reset()

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
                enable_synthetic_fallback=self.enable_synthetic_fallback,
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

            selected_cand: Optional[MediaCandidate] = None
            if candidates:
                visual_cat = scene.entities[0] if getattr(scene, "entities", None) else getattr(scene, "narrative_function", "")

                for candidate in candidates:
                    local_p: Optional[str] = None

                    # Check if already local
                    if candidate.local_path and Path(candidate.local_path).exists():
                        local_p = candidate.local_path
                    elif download_selected and candidate.url:
                        try:
                            logger.info("Downloading candidate {} from {} for scene {}", candidate.asset_id, candidate.url, scene.scene_id)
                            downloaded = material.save_video(
                                video_url=candidate.url,
                                save_dir=str(self.media_cache_dir),
                            )
                            if downloaded and Path(downloaded).exists():
                                candidate.local_path = downloaded
                                local_p = downloaded
                            else:
                                logger.warning("Download of candidate {} returned invalid path", candidate.asset_id)
                        except Exception as e:
                            logger.warning(
                                "Failed to download candidate {} ({}): {}. Trying next candidate...",
                                candidate.asset_id, candidate.url, e
                            )
                            candidate.error_detail = str(e)
                    elif not download_selected:
                        selected_cand = candidate
                        break

                    # Validate local file visually and check perceptual duplication
                    if local_p:
                        try:
                            metrics = self.visual_evaluator.evaluate_media(
                                local_p,
                                media_type=candidate.media_type,
                                duration=candidate.duration or duration,
                            )
                            if not metrics.is_valid:
                                if metrics.rejection_reason in (
                                    "excessive_black_frames",
                                    "low_contrast_flat_media",
                                    "corrupted_image",
                                ):
                                    logger.warning(
                                        "Candidate {} rejected by visual evaluator: {}",
                                        candidate.asset_id, metrics.rejection_reason
                                    )
                                    candidate.error_detail = metrics.rejection_reason
                                    continue
                                else:
                                    logger.debug(
                                        "Candidate {} visual evaluation non-fatal: {}",
                                        candidate.asset_id, metrics.rejection_reason
                                    )

                            candidate.perceptual_hash = metrics.perceptual_hash
                            candidate.visual_quality_score = metrics.quality_score
                        except Exception as e:
                            logger.debug("Visual evaluation skipped for {}: {}", candidate.asset_id, e)

                        # Perceptual duplicate check against already chosen assets in this production
                        if candidate.perceptual_hash and not getattr(scene, "intentional_callback", None):
                            dup = self.deduplicator.find_perceptual_duplicate(candidate.perceptual_hash)
                            if dup:
                                logger.warning(
                                    "Candidate {} is perceptual duplicate of asset {} in scene {} (dist={})",
                                    candidate.asset_id, dup[0], dup[1], dup[2]
                                )
                                candidate.error_detail = f"perceptual_duplicate_of_{dup[0]}"
                                continue

                        selected_cand = candidate
                        break

                if selected_cand:
                    if selected_cand.local_path and Path(selected_cand.local_path).exists():
                        try:
                            self.asset_catalog.register_downloaded_asset(
                                selected_cand, Path(selected_cand.local_path)
                            )
                        except Exception as e:
                            logger.warning("Failed to register asset in catalog: {}", e)

                    self.deduplicator.mark_used(
                        selected_cand,
                        scene_id=scene.scene_id,
                        visual_category=visual_cat,
                    )
                    scene.selected_media = selected_cand.to_dict()
                else:
                    logger.error("All media candidates failed to download or are unavailable for scene {}", scene.scene_id)
                    scene.selected_media = {}
            else:
                logger.warning("No media candidates found for scene {}", scene.scene_id)
                scene.selected_media = {}

            # If scene has multiple visual beats, assign selected_media to each beat
            if getattr(scene, "has_multiple_beats", False) and scene.visual_beats:
                unused_candidates = [
                    c for c in candidates 
                    if (selected_cand is None or c.asset_id != selected_cand.asset_id)
                ]
                for beat_idx, beat in enumerate(scene.visual_beats):
                    if beat.selected_media:
                        continue
                    if beat.component_type:
                        beat.selected_media = {
                            "asset_id": f"comp_{beat.beat_id}",
                            "type": beat.component_type,
                            "local_path": "",
                            "query": beat.component_type,
                            "is_synthetic": False,
                            "semantic_score": 0.95,
                        }
                    elif beat_idx > 0 and unused_candidates:
                        beat_cand = unused_candidates.pop(0)
                        beat.selected_media = beat_cand.to_dict()
                    else:
                        beat.selected_media = scene.selected_media

        if save_plan_path:
            p = Path(save_plan_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("w", encoding="utf-8") as f:
                f.write(plan.to_json(indent=2))

        return plan
