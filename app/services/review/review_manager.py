"""Review Manager: Handles project inspection, candidate switching, and partial re-rendering.

Provides the core engine behind the Review Studio (Sections 22 & 23).
"""

from __future__ import annotations
from dataclasses import asdict
import json
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional, Tuple

from app.services.director.schemas import ScenePlan
from app.services.media_ranker.candidate_builder import _generate_synthetic_clip
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

        return {
            "project_id": project_id,
            "plan": plan,
            "raw_plan": plan_data,
            "latest_video": latest_video,
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

        # Save updated scenes.json
        with scenes_file.open("w", encoding="utf-8") as f:
            f.write(plan.to_json(indent=2))

        # Re-build project manifest for VideoProject based on previous revision
        render_folder = folder / "render_project"
        vp = VideoProject(render_folder)
        try:
            prev_spec = vp.revision()
            prev_scenes = {s["id"]: s for s in prev_spec.get("scenes", [])}
            render_settings = prev_spec.get("settings", {"width": 1080, "height": 1920, "fps": 30})
        except Exception:
            prev_scenes = {}
            render_settings = {"width": 1080, "height": 1920, "fps": 30}

        def _extract_asset_path(val: Any) -> Optional[str]:
            if not val:
                return None
            if isinstance(val, dict):
                rel = val.get("path")
                if rel:
                    p = render_folder / rel
                    if p.exists():
                        return str(p.resolve())
                return None
            p = Path(val)
            if not p.is_absolute():
                p = render_folder / p
            return str(p.resolve()) if p.exists() else str(p)

        project_scenes = []
        for s in plan.scenes:
            if s.scene_id == scene_id:
                # Target swapped scene
                f_path = str(footage_file.resolve())
                prev_audio = (prev_scenes.get(s.scene_id) or {}).get("audio")
                audio_path = _extract_asset_path(prev_audio)
                if not audio_path:
                    def_audio = folder / "audio" / f"{s.scene_id}.mp3"
                    audio_path = str(def_audio.resolve()) if def_audio.exists() else None

                seg_dur = float(s.end - s.start) if (s.end and s.start) else (prev_scenes.get(s.scene_id) or {}).get("duration", 4.0)
                project_scenes.append(
                    {
                        "id": s.scene_id,
                        "narration": s.narration,
                        "duration": seg_dur,
                        "footage": f_path,
                        "audio": audio_path,
                    }
                )
            elif s.scene_id in prev_scenes:
                # 100% exact copy of unchanged scene from previous revision to guarantee cache hit!
                prev_s = prev_scenes[s.scene_id]
                footage_path = _extract_asset_path(prev_s.get("footage"))
                audio_path = _extract_asset_path(prev_s.get("audio"))
                project_scenes.append(
                    {
                        "id": s.scene_id,
                        "narration": prev_s.get("narration", s.narration),
                        "duration": prev_s.get("duration", 4.0),
                        "footage": footage_path,
                        "audio": audio_path,
                    }
                )
            else:
                selected = s.selected_media or {}
                f_path = selected.get("local_path")
                if not f_path or not Path(f_path).exists():
                    fallback_clip = self.media_cache_dir / f"fallback_{s.scene_id}.mp4"
                    _generate_synthetic_clip(s.queries[0] if s.queries else s.narration, fallback_clip)
                    f_path = str(fallback_clip)

                audio_file = folder / "audio" / f"{s.scene_id}.mp3"
                project_scenes.append(
                    {
                        "id": s.scene_id,
                        "narration": s.narration,
                        "duration": float(s.end - s.start) if (s.end and s.start) else 4.0,
                        "footage": str(Path(f_path).resolve()),
                        "audio": str(audio_file) if audio_file.exists() else None,
                    }
                )

        new_rev = vp.create_revision(
            {
                "project_id": project_id,
                "settings": render_settings,
                "scenes": project_scenes,
            }
        )
        rev_id = new_rev["revision_id"]

        # Track reused vs rebuilt stages
        reused_stages: List[str] = []
        built_stages: List[str] = []

        def on_stage(stage, reused):
            if reused:
                reused_stages.append(stage.key)
            else:
                built_stages.append(stage.key)

        status = vp.render(rev_id, on_stage=on_stage)
        export_path = status.get("export", {}).get("path")

        return {
            "project_id": project_id,
            "revision_id": rev_id,
            "status": status["state"],
            "video_path": export_path,
            "swapped_scene": scene_id,
            "reused_stages": reused_stages,
            "built_stages": built_stages,
            "stages_count": len(reused_stages) + len(built_stages),
        }
