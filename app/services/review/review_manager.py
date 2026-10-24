"""Review Manager: Handles project inspection, candidate switching, and partial re-rendering.

Provides the core engine behind the Review Studio (Sections 22 & 23).
"""

from __future__ import annotations
from dataclasses import asdict
import json
import hashlib
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional, Tuple

from app.services.director.schemas import ScenePlan
from app.services.video_project import VideoProject


class ReviewManager:
    def __init__(self, storage_dir: str | Path = "storage"):
        self.storage_dir = Path(storage_dir).resolve()
        self.projects_dir = self.storage_dir / "projects"
        self.media_cache_dir = self.storage_dir / "media_cache"
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.media_cache_dir.mkdir(parents=True, exist_ok=True)

    def list_projects(self) -> List[str]:
        """Returns all project IDs that contain a scenes.json manifest."""
        projects = []
        for folder in sorted(self.projects_dir.iterdir()):
            if folder.is_dir() and (folder / "scenes.json").exists():
                projects.append(folder.name)
        return projects

    def get_project_data(self, project_id: str) -> Dict[str, Any]:
        """Loads scenes.json, current revision, and video export for the Review Studio."""
        folder = self.projects_dir / project_id
        scenes_file = folder / "scenes.json"
        if not scenes_file.exists():
            raise FileNotFoundError(f"scenes.json not found for project '{project_id}'")

        with scenes_file.open("r", encoding="utf-8") as f:
            plan_data = json.load(f)

        plan = ScenePlan.from_dict(plan_data)

        # Check render_project status
        render_folder = folder / "render_project"
        latest_video = None
        current_rev = None
        if render_folder.exists() and (render_folder / "project.json").exists():
            try:
                vp = VideoProject(render_folder)
                meta = vp.metadata()
                current_rev = meta.get("current_revision")
                export_info = meta.get("last_successful_export")
                if export_info and "path" in export_info:
                    p = Path(export_info["path"])
                    if p.exists():
                        latest_video = str(p)
            except Exception:
                pass

        audit_file = folder / "render_audit.json"
        audit = json.loads(audit_file.read_text()) if audit_file.is_file() else {}
        publishable = bool(audit.get("publishable") and audit.get("review_sha256") == hashlib.sha256(scenes_file.read_bytes()).hexdigest())
        return {
            "project_id": project_id,
            "plan": plan,
            "raw_plan": plan_data,
            "latest_video": latest_video,
            "publishable": publishable,
            "current_revision": current_rev,
            "total_scenes": len(plan.scenes),
        }

    def swap_scene_media(
        self,
        project_id: str,
        scene_id: str,
        new_footage_path: str | Path,
        new_candidate_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Swaps the footage for a single scene and executes an incremental partial re-render.

        Only the modified scene and the final assembly are rebuilt; unchanged scenes are 100% reused from cache.
        """
        folder = self.projects_dir / project_id
        scenes_file = folder / "scenes.json"
        with scenes_file.open("r", encoding="utf-8") as f:
            plan_data = json.load(f)

        plan = ScenePlan.from_dict(plan_data)
        target_scene = next((s for s in plan.scenes if s.scene_id == scene_id), None)
        if not target_scene:
            raise ValueError(f"Scene '{scene_id}' not found in project '{project_id}'")

        footage_file = Path(new_footage_path).resolve()
        if not footage_file.exists():
            raise FileNotFoundError(f"Media file '{new_footage_path}' not found")

        # Update selected_media in plan
        if new_candidate_info:
            updated_info = dict(new_candidate_info)
            from app.services.media_ranker.asset_catalog import _measure_media
            from app.services.media_ranker.crop_planner import useful_resolution
            width, height, duration = _measure_media(footage_file)
            updated_info.update(width=width, height=height, duration=duration)
            if min(useful_resolution(width, height)) < 720 and min(width, height) >= 720:
                updated_info["crop_mode"] = "fit"
            updated_info["local_path"] = str(footage_file)
            target_scene.selected_media = updated_info
        else:
            target_scene.selected_media = {
                "provider": "custom_swap",
                "asset_id": footage_file.stem,
                "local_path": str(footage_file),
                "url": str(footage_file),
                "technical_score": 1.0,
                "final_score": 1.0,
            }

        if target_scene.visual_beats:
            raise ValueError("This scene has beats; select a specific beat to replace its media.")
        target_scene.selected_media["semantic_status"] = "unverified"
        target_scene.selected_media["semantic_score"] = 0.0
        # Save updated scenes.json
        with scenes_file.open("w", encoding="utf-8") as f:
            f.write(plan.to_json(indent=2))

        # A replacement invalidates relevance approval. Do not synthesize audio or
        # start an export merely because the user is comparing a candidate.
        self.evaluate_project_quality(project_id)
        return {"project_id": project_id, "swapped_scene": scene_id,
                "status": "pending_review", "video_path": None,
                "selected_media": target_scene.selected_media}

    def direct_script(
        self,
        script_id: str,
        script_text: str,
        title: str = "",
        channel: str = "default",
        brand_preset: str = "editorial",
    ) -> Dict[str, Any]:
        """Directs a script into scenes.json (Etapa 1) without fetching heavy media or audio."""
        from app.services.director.scene_director import SceneDirector
        from app.services.editorial.script_manager import ScriptManager

        sm = ScriptManager(storage_dir=self.storage_dir / "scripts")
        director = SceneDirector(script_manager=sm)
        folder = self.projects_dir / script_id
        folder.mkdir(parents=True, exist_ok=True)

        plan = director.direct_script(
            script_id=script_id,
            script_text=script_text,
            title=title,
            channel=channel,
            brand_preset=brand_preset,
            save_plan=True,
            output_dir=folder,
        )

        return {
            "project_id": script_id,
            "plan": plan,
            "plan_path": str(folder / "scenes.json"),
            "total_scenes": len(plan.scenes),
            "estimated_duration": plan.estimated_duration,
        }

    def update_scene_metadata(
        self,
        project_id: str,
        scene_id: str,
        queries: Optional[List[str]] = None,
        component_type: Optional[str] = None,
        visual_type: Optional[str] = None,
        text_overlay: Optional[str] = None,
        text_level: Optional[str] = None,
        preferred_motion: Optional[str] = None,
        intent: Optional[str] = None,
    ) -> ScenePlan:
        """Updates editable editorial metadata for a scene. Narration is strictly immutable."""
        folder = self.projects_dir / project_id
        scenes_file = folder / "scenes.json"
        with scenes_file.open("r", encoding="utf-8") as f:
            plan_data = json.load(f)
        plan = ScenePlan.from_dict(plan_data)

        scene = next((s for s in plan.scenes if s.scene_id == scene_id), None)
        if not scene:
            raise ValueError(f"Scene '{scene_id}' not found in project '{project_id}'")

        if queries is not None:
            scene.queries = [q.strip() for q in queries if q.strip()]
        if visual_type is not None:
            scene.visual_type = visual_type
        if component_type is not None:
            setattr(scene, "component_type", component_type)
        if text_overlay is not None:
            scene.text_overlay = text_overlay.strip() if text_overlay.strip() else None
        if text_level is not None:
            scene.text_level = text_level
        if preferred_motion is not None:
            scene.preferred_motion = preferred_motion
        if intent is not None:
            scene.intent = intent
        for target in scene.visual_beats or [scene]:
            if target.selected_media:
                target.selected_media["semantic_status"] = "unverified"
                target.selected_media["semantic_score"] = 0.0

        with scenes_file.open("w", encoding="utf-8") as f:
            f.write(plan.to_json(indent=2))

        return plan

    def update_beat_metadata(
        self,
        project_id: str,
        scene_id: str,
        beat_id: str,
        queries: Optional[List[str]] = None,
        component_type: Optional[str] = None,
        visual_type: Optional[str] = None,
        text_overlay: Optional[str] = None,
        intent: Optional[str] = None,
    ) -> ScenePlan:
        """Updates editable editorial metadata for a VisualBeat."""
        folder = self.projects_dir / project_id
        scenes_file = folder / "scenes.json"
        with scenes_file.open("r", encoding="utf-8") as f:
            plan_data = json.load(f)
        plan = ScenePlan.from_dict(plan_data)

        scene = next((s for s in plan.scenes if s.scene_id == scene_id), None)
        if not scene:
            raise ValueError(f"Scene '{scene_id}' not found in project '{project_id}'")

        beat = next((b for b in scene.visual_beats if b.beat_id == beat_id), None)
        if not beat:
            raise ValueError(f"Beat '{beat_id}' not found in scene '{scene_id}'")

        if queries is not None:
            beat.queries = [q.strip() for q in queries if q.strip()]
        if component_type is not None:
            beat.component_type = component_type
        if visual_type is not None:
            beat.visual_type = visual_type
        if text_overlay is not None:
            beat.text_overlay = text_overlay.strip() if text_overlay.strip() else None
        if intent is not None:
            beat.intent = intent
        if beat.selected_media:
            beat.selected_media["semantic_status"] = "unverified"
            beat.selected_media["semantic_score"] = 0.0

        with scenes_file.open("w", encoding="utf-8") as f:
            f.write(plan.to_json(indent=2))

        return plan

    def search_media_for_scene(
        self,
        project_id: str,
        scene_id: str,
        candidates_per_scene: int = 5,
        download_selected: bool = False,
    ) -> List[Dict[str, Any]]:
        """Re-searches media candidates for a specific scene."""
        from app.services.media_ranker.media_searcher import MediaSearcher

        folder = self.projects_dir / project_id
        scenes_file = folder / "scenes.json"
        with scenes_file.open("r", encoding="utf-8") as f:
            plan_data = json.load(f)
        plan = ScenePlan.from_dict(plan_data)

        scene = next((s for s in plan.scenes if s.scene_id == scene_id), None)
        if not scene:
            raise ValueError(f"Scene '{scene_id}' not found in project '{project_id}'")

        searcher = MediaSearcher(media_cache_dir=self.media_cache_dir)
        dur = float(scene.end - scene.start) if (scene.end and scene.start) else scene.duration_hint
        candidates = searcher.search_for_scene(scene, target_duration=dur, candidates_per_scene=candidates_per_scene)
        scene.media_candidates = [c.to_dict() for c in candidates]
        if candidates and not scene.selected_media:
            scene.selected_media = candidates[0].to_dict()

        with scenes_file.open("w", encoding="utf-8") as f:
            f.write(plan.to_json(indent=2))

        return scene.media_candidates

    def search_media_for_all_scenes(
        self,
        project_id: str,
        candidates_per_scene: int = 5,
        download_selected: bool = True,
    ) -> ScenePlan:
        """Runs candidate collection for all scenes in the project."""
        from app.services.media_ranker.media_searcher import MediaSearcher

        folder = self.projects_dir / project_id
        scenes_file = folder / "scenes.json"
        with scenes_file.open("r", encoding="utf-8") as f:
            plan_data = json.load(f)
        plan = ScenePlan.from_dict(plan_data)

        searcher = MediaSearcher(media_cache_dir=self.media_cache_dir)
        enriched = searcher.populate_scene_plan(
            plan=plan,
            candidates_per_scene=candidates_per_scene,
            download_selected=download_selected,
            save_plan_path=scenes_file,
        )
        return enriched

    def swap_beat_media(
        self,
        project_id: str,
        scene_id: str,
        beat_id: str,
        new_footage_path: str | Path,
        new_candidate_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Swaps the selected media for a specific VisualBeat."""
        folder = self.projects_dir / project_id
        scenes_file = folder / "scenes.json"
        with scenes_file.open("r", encoding="utf-8") as f:
            plan_data = json.load(f)
        plan = ScenePlan.from_dict(plan_data)

        scene = next((s for s in plan.scenes if s.scene_id == scene_id), None)
        if not scene:
            raise ValueError(f"Scene '{scene_id}' not found")
        beat = next((b for b in scene.visual_beats if b.beat_id == beat_id), None)
        if not beat:
            raise ValueError(f"Beat '{beat_id}' not found in scene '{scene_id}'")

        f_path = str(Path(new_footage_path).resolve())
        if not Path(f_path).is_file():
            raise FileNotFoundError(f_path)
        if new_candidate_info:
            updated = dict(new_candidate_info)
            from app.services.media_ranker.asset_catalog import _measure_media
            from app.services.media_ranker.crop_planner import useful_resolution
            width, height, duration = _measure_media(Path(f_path))
            updated.update(width=width, height=height, duration=duration)
            if min(useful_resolution(width, height)) < 720 and min(width, height) >= 720:
                updated["crop_mode"] = "fit"
            updated["local_path"] = f_path
            updated["semantic_status"] = "unverified"
            updated["semantic_score"] = 0.0
            beat.selected_media = updated
        else:
            beat.selected_media = {
                "asset_id": Path(f_path).stem,
                "local_path": f_path,
                "url": f_path,
                "type": beat.visual_type,
            }

        with scenes_file.open("w", encoding="utf-8") as f:
            f.write(plan.to_json(indent=2))

        self.evaluate_project_quality(project_id)
        return {"project_id": project_id, "scene_id": scene_id, "beat_id": beat_id, "selected_media": beat.selected_media}

    def review_media(self, project_id: str, scene_id: str, beat_id: Optional[str],
                     approved: bool, reason: str = "") -> None:
        """Record explicit human relevance review for the current material and context."""
        path = self.projects_dir / project_id / "scenes.json"
        plan = ScenePlan.from_dict(json.loads(path.read_text(encoding="utf-8")))
        scene = next(s for s in plan.scenes if s.scene_id == scene_id)
        target = next(b for b in scene.visual_beats if b.beat_id == beat_id) if beat_id else scene
        if not target.selected_media:
            raise ValueError("pending_media")
        target.selected_media["semantic_status"] = "reviewed" if approved else "rejected"
        target.selected_media["semantic_score"] = 1.0 if approved else 0.0
        target.selected_media["review_reason"] = reason
        path.write_text(plan.to_json(), encoding="utf-8")
        self.evaluate_project_quality(project_id)

    def search_media_for_beat(self, project_id: str, scene_id: str, beat_id: str, prefer_video: bool = False) -> None:
        from dataclasses import replace
        from app.services.media_ranker.media_searcher import MediaSearcher
        path = self.projects_dir / project_id / "scenes.json"
        plan = ScenePlan.from_dict(json.loads(path.read_text(encoding="utf-8")))
        scene = next(s for s in plan.scenes if s.scene_id == scene_id)
        beat = next(b for b in scene.visual_beats if b.beat_id == beat_id)
        if prefer_video:
            beat.visual_type = "stock_video"
            beat.component_type = None
        target = replace(scene, visual_beats=[beat])
        searcher = MediaSearcher(media_cache_dir=self.media_cache_dir)
        from app.services.media_ranker.schemas import MediaCandidate
        for other_scene in plan.scenes:
            for other in other_scene.visual_beats or [other_scene]:
                if other is beat:
                    if other.selected_media and other.selected_media.get("semantic_status") == "rejected":
                        searcher.deduplicator.block_asset(other.selected_media["asset_id"])
                elif other.selected_media:
                    searcher.deduplicator.mark_used(MediaCandidate.from_dict(other.selected_media))
        searcher.populate_scene_plan(replace(plan, scenes=[target]))
        path.write_text(plan.to_json(), encoding="utf-8")
        self.evaluate_project_quality(project_id)

    def import_mixkit_for_beat(self, project_id: str, scene_id: str, beat_id: Optional[str], url: str) -> None:
        """Resolve one user-selected page, download its free rendition, then review."""
        import re
        from app.services.media_ranker.schemas import MediaCandidate
        from app.services.media_ranker.media_searcher import MediaSearcher
        match = re.fullmatch(r"https://mixkit\.co/free-stock-video/[a-z0-9-]+-(\d+)/?", url.strip())
        if not match:
            raise ValueError("Informe a página de um vídeo do Mixkit.")
        candidate = MediaCandidate(provider="mixkit", asset_id=f"mixkit_{match[1]}",
            provider_asset_id=match[1], source_page=url.strip(), url=url.strip())
        path = MediaSearcher(media_cache_dir=self.media_cache_dir)._download_candidate_asset(candidate)
        if not path:
            raise ValueError("O download não foi concluído; a seleção anterior foi preservada.")
        if beat_id:
            self.swap_beat_media(project_id, scene_id, beat_id, path, candidate.to_dict())
        else:
            self.swap_scene_media(project_id, scene_id, path, new_candidate_info=candidate.to_dict())

    def evaluate_project_quality(self, project_id: str) -> Dict[str, Any]:
        """Evaluates Quality Gate and generates pre-render reports for a project."""
        from app.services.assembly.planner import AssemblyPlanner
        from app.services.assembly.pre_visualizer import PreVisualizer
        from app.services.assembly.quality_checker import QualityChecker
        from app.services.editorial.credits_generator import CreditsGenerator
        from app.services.media_ranker.asset_catalog import AssetCatalog

        folder = self.projects_dir / project_id
        scenes_file = folder / "scenes.json"
        if not scenes_file.exists():
            raise FileNotFoundError(f"scenes.json not found for project '{project_id}'")

        with scenes_file.open("r", encoding="utf-8") as f:
            plan_data = json.load(f)
        plan = ScenePlan.from_dict(plan_data)

        planner = AssemblyPlanner()
        assembly_plan = planner.build_plan(plan)
        checker = QualityChecker()
        score = checker.evaluate(assembly_plan)
        from app.services.assembly.media_mix import summarize_media_mix
        media_mix = summarize_media_mix(assembly_plan)

        pre_vis = PreVisualizer()
        storyboard = pre_vis.save_reports(
            plan=assembly_plan,
            output_dir=folder,
            scene_plan=plan,
            title=getattr(plan, "title", project_id),
        )

        catalog = AssetCatalog(db_path=self.storage_dir / "asset_catalog.db")
        cred_gen = CreditsGenerator(catalog=catalog)
        credits_files = cred_gen.save_credits(
            plan=assembly_plan,
            output_dir=folder,
            project_title=getattr(plan, "title", project_id),
        )

        assembly_file = folder / "assembly_plan.json"
        with assembly_file.open("w", encoding="utf-8") as f:
            f.write(assembly_plan.to_json(indent=2))

        return {
            "project_id": project_id,
            "quality_score": score.to_dict(),
            "media_mix": media_mix,
            "passed": score.passed,
            "alerts": score.alerts,
            "assembly_plan_path": str(assembly_file),
            "storyboard_html_path": str(storyboard["html"]),
            "storyboard_md_path": str(storyboard["markdown"]),
            "credits_md_path": str(credits_files["credits_md"]),
            "manifest_json_path": str(credits_files["manifest_json"]),
            "total_segments": len(assembly_plan.segments),
            "total_duration": assembly_plan.total_duration,
        }

    def list_projects_summary(self) -> List[Dict[str, Any]]:
        """Returns summary of all projects with status, duration, and preset."""
        summaries = []
        for folder in sorted(self.projects_dir.iterdir()):
            if folder.is_dir() and (folder / "scenes.json").exists():
                try:
                    with (folder / "scenes.json").open("r", encoding="utf-8") as f:
                        data = json.load(f)
                    has_video = (folder / f"{folder.name}_mastered.mp4").exists()
                    if not has_video:
                        render_meta = folder / "render_project" / "project.json"
                        if render_meta.exists():
                            with render_meta.open("r", encoding="utf-8") as rf:
                                rdata = json.load(rf)
                                if rdata.get("last_successful_export"):
                                    has_video = True
                    summaries.append(
                        {
                            "project_id": folder.name,
                            "title": data.get("title", folder.name),
                            "total_scenes": len(data.get("scenes", [])),
                            "estimated_duration": data.get("estimated_duration", 0.0),
                            "brand_preset": data.get("brand_preset", "editorial"),
                            "created_at": data.get("created_at", ""),
                            "has_video": has_video,
                        }
                    )
                except Exception:
                    summaries.append({"project_id": folder.name, "title": folder.name, "total_scenes": 0, "has_video": False})
        return summaries
