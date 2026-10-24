"""Media Searcher: Orchestrates candidate searching and selection for all scenes.

Implements the end-to-end pipeline:
ScenePlan -> Queries -> CandidateBuilder -> Deduplicator -> Technical Filter -> Top Candidates -> Project Manifest.
"""

from __future__ import annotations
from dataclasses import replace, asdict
from time import monotonic
import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from PIL import Image
import requests
from loguru import logger

from app.config import config
from app.services import material
from app.services.director.schemas import Scene, ScenePlan, VisualBeat
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
        relevance_evaluator: Optional[Any] = None,
    ):
        self.relevance_evaluator = relevance_evaluator
        self._beat_context = {}
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
        self.search_attempts: list[dict[str, Any]] = []

    def reset(self) -> None:
        """Resets deduplicator and internal tracking state between production runs."""
        self.deduplicator.reset()
        self.search_attempts.clear()

    def search_for_scene(
        self,
        scene: Scene,
        target_duration: float = 4.0,
        candidates_per_scene: int = 5,
    ) -> list[MediaCandidate]:
        """Searches across all queries for a single scene and returns top candidates."""
        if self.graphics_engine.is_graphic_scene(scene):
            return [self.graphics_engine.create_card_candidate(scene=scene, duration=target_duration)]
        all_raw_candidates: list[MediaCandidate] = []

        # 0. Check smart library first (acervo próprio aprovado)
        for q in scene.queries:
            lib_matches = self.smart_library.search_library(
                query=f"{q} {scene.intent}",
                target_duration=target_duration,
            )
            all_raw_candidates.extend(lib_matches)

        # 1. Run each query through candidate builder (external stock + local cache)
        deadline = monotonic() + 45
        for q in scene.queries:
            if monotonic() >= deadline:
                break
            raw = self.candidate_builder.search_query(
                query=q,
                target_duration=target_duration,
                enable_synthetic_fallback=self.enable_synthetic_fallback,
                visual_type=scene.visual_type,
                preferred_motion=scene.preferred_motion,
            )
            all_raw_candidates.extend(raw)
            manager = getattr(self.candidate_builder, "sources_manager", None)
            attempts = getattr(self.candidate_builder, "search_attempts", getattr(manager, "last_attempts", []))
            if isinstance(attempts, list):
                self.search_attempts.extend({"scene_id": scene.scene_id, "query": q,
                    "provider": a.provider, "status": a.status, "elapsed_ms": a.elapsed_ms,
                    "candidate_count": len(a.candidates)} for a in attempts)

        # 2. Deduplicate within scene
        deduped = self.deduplicator.deduplicate_within_scene(all_raw_candidates)

        # 3. Prefer candidates not yet used globally
        fresh = self.deduplicator.filter_globally_unused(deduped)

        prefer_video = scene.visual_type not in {"stock_image", "photo", "generated_image"}

        # 4. First stage: technical filter (take up to 10 candidates)
        tech_filtered = rank_and_filter_candidates(
            candidates=fresh,
            target_duration=target_duration,
            top_k=max(10, candidates_per_scene * 2),
            prefer_video=prefer_video,
        )

        # 5. Second stage: semantic multimodal ranker (take top candidates_per_scene * 2)
        sem_ranked = self.semantic_ranker.rank_candidates(
            scene_narration=scene.narration,
            scene_intent=f"{scene.intent} {' '.join(scene.queries)}",
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
        scored.sort(key=lambda c: (
            c.semantic_score >= 0.6,
            prefer_video and c.media_type == "video" and not c.is_synthetic
            and (c.duration <= 0 or c.duration >= target_duration),
            c.final_score,
        ), reverse=True)
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

    def _download_candidate_asset(self, candidate: MediaCandidate) -> str:
        """Downloads candidate asset to local media cache, supporting both videos and images."""
        if candidate.provider == "mixkit":
            from app.services.media_sources.mixkit import MixkitProvider
            MixkitProvider().resolve_candidate(candidate)
        if candidate.rights_status == "blocked_for_this_use":
            raise ValueError("asset_rights_blocked")
        if not candidate.url:
            return ""

        clean_url = candidate.url.split("?")[0].lower()
        is_image = (
            candidate.media_type == "image"
            or any(clean_url.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"))
            or candidate.provider in ("openverse", "pexels_photos")
        )

        if is_image:
            return self._download_image_asset(candidate)
        else:
            return material.save_video(
                video_url=candidate.url,
                save_dir=str(self.media_cache_dir),
            )

    def _download_image_asset(self, candidate: MediaCandidate) -> str:
        """Downloads and validates a static image asset with compliant headers."""
        url = candidate.url
        url_hash = hashlib.md5(url.split("#", 1)[0].encode("utf-8")).hexdigest()
        clean_url = url.split("?")[0].lower()
        ext = ".jpg"
        for potential_ext in (".png", ".webp", ".jpeg", ".jpg"):
            if clean_url.endswith(potential_ext):
                ext = ".jpg" if potential_ext == ".jpeg" else potential_ext
                break

        img_path = self.media_cache_dir / f"img-{url_hash}{ext}"
        if img_path.exists() and img_path.stat().st_size > 1024:
            return str(img_path)

        headers = {
            "User-Agent": "FabricaDeShortsBot/2.0 (https://github.com/lucasregis/fabrica; contact@fabricadeshorts.com)",
            "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
        }

        temp_path = self.media_cache_dir / f".tmp_{url_hash}{ext}"
        try:
            resp = requests.get(
                url,
                headers=headers,
                proxies=config.proxy,
                timeout=(10, 25),
                stream=True,
            )
            resp.raise_for_status()

            with open(temp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)

            # Validate and normalize with PIL
            with Image.open(temp_path) as img:
                img.verify()

            temp_path.replace(img_path)
            return str(img_path)
        except Exception as e:
            logger.warning("Failed to download image candidate {} ({}): {}", candidate.asset_id, url, e)
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            return ""

    def search_for_beat(self, scene: Scene, beat: VisualBeat, **kwargs) -> list[MediaCandidate]:
        """Use the beat's own retrieval context while preserving the approved narration."""
        target = replace(scene, scene_id=beat.beat_id, intent=beat.intent,
                         queries=list(beat.queries), visual_type=beat.visual_type,
                         preferred_motion=beat.preferred_motion, visual_beats=[],
                         text_overlay=beat.text_overlay, text_level=beat.text_level)
        return self.search_for_scene(target, **kwargs)

    def populate_scene_plan(
        self,
        plan: ScenePlan,
        candidates_per_scene: int = 5,
        download_selected: bool = True,
        save_plan_path: Optional[str | Path] = None,
        on_progress: Optional[Callable[[str, float], None]] = None,
    ) -> ScenePlan:
        """Enriches all scenes in the plan with media_candidates and a selected_media default."""
        total_scenes = len(plan.scenes)
        for idx, scene in enumerate(plan.scenes):
            if save_plan_path:
                checkpoint = Path(save_plan_path)
                checkpoint.parent.mkdir(parents=True, exist_ok=True)
                checkpoint.write_text(plan.to_json(), encoding="utf-8")
            if on_progress:
                scene_frac = idx / max(1, total_scenes)
                on_progress(f"Buscando mídias: cena {idx+1}/{total_scenes} ({scene.scene_id})...", scene_frac)

            if scene.visual_beats:
                total_hint = sum(max(0.01, b.duration) for b in scene.visual_beats)
                measured = (scene.overlay or {}).get("audio_duration")
                duration = measured or ((scene.end - scene.start) if scene.start is not None and scene.end is not None else total_hint)
                for beat in scene.visual_beats:
                    from .query_planner import plan_queries
                    beat.queries = plan_queries(beat)
                    attempt_start = len(self.search_attempts)
                    self._beat_context[beat.beat_id] = beat
                    beat_duration = duration * max(0.01, beat.duration) / total_hint
                    target = replace(scene, scene_id=beat.beat_id, intent=beat.intent,
                                     queries=list(beat.queries), visual_type=beat.visual_type,
                                     preferred_motion=beat.preferred_motion, visual_beats=[],
                                     selected_media=None, media_candidates=[], start=0.0,
                                     end=beat_duration, text_overlay=beat.text_overlay,
                                     text_level=beat.text_level)
                    # Treatments need real media. Only explicit graphic types create cards.
                    if beat.component_type in {"data_card", "price_tag"}:
                        target.visual_type = beat.component_type
                    child = replace(plan, scenes=[target], total_scenes=1)
                    self.populate_scene_plan(child, candidates_per_scene, download_selected)
                    beat.selected_media = target.selected_media
                    beat.media_candidates = target.media_candidates
                    beat.search_attempts = self.search_attempts[attempt_start:]
                    beat.status = "selected" if target.selected_media else "pending_media"
                scene.media_candidates = [c for b in scene.visual_beats for c in b.media_candidates]
                scene.selected_media = scene.visual_beats[0].selected_media
                continue

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
            visual_cat = scene.entities[0] if getattr(scene, "entities", None) else getattr(scene, "narrative_function", "")
            if candidates:
                for candidate in candidates:
                    if candidate.semantic_score < 0.6 and candidate.provider != "graphics_engine":
                        candidate.error_detail = "rejected_relevance" if candidate.semantic_status != "unverified" else "pending_review"
                        continue
                    local_p: Optional[str] = None

                    # Check if already local
                    if candidate.local_path and Path(candidate.local_path).exists():
                        local_p = candidate.local_path
                    elif download_selected and candidate.url:
                        try:
                            logger.info("Downloading candidate {} from {} for scene {}", candidate.asset_id, candidate.provider, scene.scene_id)
                            downloaded = self._download_candidate_asset(candidate)
                            if downloaded and Path(downloaded).exists():
                                candidate.local_path = downloaded
                                local_p = downloaded
                            else:
                                logger.warning("Download of candidate {} returned invalid path", candidate.asset_id)
                        except Exception as e:
                            logger.warning(
                                "Failed to download candidate {} from {}: {}. Trying next candidate...",
                                candidate.asset_id, candidate.provider, type(e).__name__
                            )
                            candidate.error_detail = str(e)
                    elif not download_selected:
                        selected_cand = candidate
                        break

                    # Validate local file visually and check perceptual duplication
                    if local_p:
                        try:
                            from .asset_catalog import _measure_media
                            from .shot_indexer import Shot, index_shots
                            from .clip_selector import select_clip
                            w, h, measured_duration = _measure_media(Path(local_p))
                            if w <= 0 or h <= 0:
                                candidate.error_detail = "decode_failed"
                                continue
                            candidate.width, candidate.height = w, h
                            from .crop_planner import useful_resolution
                            if min(useful_resolution(w, h)) < 720 and w >= 720 and h >= 720:
                                candidate.crop_mode = "fit"
                            useful_w, useful_h = useful_resolution(w, h, candidate.crop_mode)
                            if useful_w < 720 or useful_h < (720 if candidate.crop_mode == "fit" else 1280):
                                candidate.error_detail = "rejected_resolution"
                                continue
                            if candidate.media_type == "video":
                                candidate.duration = measured_duration
                                shots = (index_shots(local_p, measured_duration, self.media_cache_dir / "shots")
                                         if measured_duration > 20 else [Shot("full", 0, measured_duration)])
                                candidate.source_in, candidate.source_out = select_clip(shots, duration)
                            metrics = self.visual_evaluator.evaluate_media(
                                local_p,
                                media_type=candidate.media_type,
                                duration=duration,
                                source_in=candidate.source_in,
                            )
                            if not metrics.is_valid:
                                candidate.error_detail = metrics.rejection_reason or "decode_failed"
                                continue

                            beat_context = self._beat_context.get(scene.scene_id)
                            if self.relevance_evaluator and beat_context:
                                frames = []
                                for fraction in (0.15, 0.5, 0.85):
                                    image = (self.visual_evaluator.extract_image_frame(Path(local_p))
                                             if candidate.media_type == "image" else
                                             self.visual_evaluator.extract_video_frame(Path(local_p), candidate.source_in + duration * fraction))
                                    if image:
                                        frame_path = self.media_cache_dir / "eval_frames" / f"relevance_{scene.scene_id}_{fraction}.jpg"
                                        image.save(frame_path)
                                        frames.append(str(frame_path))
                                result = self.relevance_evaluator.assess(candidate, beat_context, frames)
                                candidate.semantic_status = result["status"]
                                candidate.semantic_score = result["score"]
                                if result["status"] == "rejected":
                                    candidate.error_detail = "rejected_relevance"
                                    continue
                            candidate.perceptual_hash = metrics.perceptual_hash
                            candidate.visual_quality_score = metrics.quality_score
                        except Exception as e:
                            candidate.error_detail = "decode_failed"
                            logger.warning("Visual evaluation failed for {}: {}", candidate.asset_id, e)
                            continue

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

            # Missing media remains a visible editorial pending state, never a disguised plate.
            if not selected_cand:
                scene.selected_media = None
                logger.warning("pending_media: no validated asset for {}", scene.scene_id)
            scene.media_candidates = [c.to_dict() for c in candidates]

        if save_plan_path:
            p = Path(save_plan_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("w", encoding="utf-8") as f:
                f.write(plan.to_json(indent=2))
            (p.parent / "search_attempts.json").write_text(json.dumps(self.search_attempts, ensure_ascii=False, indent=2), encoding="utf-8")

        return plan
