"""Shorts Factory Master Pipeline Orchestrator.

Implements the end-to-end vision (Section 1 & Section 60):
HUMAN SCRIPT -> SCENE DIRECTOR -> MEDIA SEARCHER -> VOICE ENGINE -> VIDEO PROJECT -> VIDEO DRAFT.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Callable, Optional

from loguru import logger
from app.config import config
from app.services import voice
from app.services.assembly.planner import AssemblyPlanner
from app.services.assembly.pre_visualizer import PreVisualizer
from app.services.assembly.quality_checker import QualityChecker
from app.services.assembly.schemas import AssemblyPlan
from app.services.audio.mastering import (
    master_voice_track,
    mix_voice_with_adaptive_bgm,
    remux_video_with_audio,
)
from app.services.director.scene_director import SceneDirector
from app.services.director.schemas import ScenePlan
from app.services.editorial.pronunciation import PronunciationEngine
from app.services.editorial.script_manager import ScriptManager
from app.services.graphics.typography_engine import TypographyEngine, composite_overlay_to_clip
from app.services.media_ranker.media_searcher import MediaSearcher
from app.services.utils.ken_burns import create_ken_burns_clip, is_image_file
from app.services.video_project import VideoProject


def _measure_audio_duration(path: Path | str) -> float:
    """Measures exact duration in seconds of an audio file using ffprobe."""
    import subprocess
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        dur = float(result.stdout.strip())
        return max(0.1, round(dur, 2))
    except Exception as exc:
        logger.warning("Failed to probe audio duration for {}: {}", path, exc)
        return 0.0


class ShortsFactory:
    """Master orchestrator for the Shorts Factory."""

    def __init__(
        self,
        base_dir: str | Path = "storage",
        voice_name: str = "pt-BR-AntonioNeural-Male",
        allow_placeholders: bool = False,
    ):
        self.base_dir = Path(base_dir).resolve()
        self.allow_placeholders = allow_placeholders
        self.projects_dir = self.base_dir / "projects"
        self.scripts_dir = self.base_dir / "scripts"
        self.media_cache_dir = self.base_dir / "media_cache"
        self.audio_cache_dir = self.base_dir / "audio_cache"

        for d in [self.projects_dir, self.scripts_dir, self.media_cache_dir, self.audio_cache_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self.script_manager = ScriptManager(storage_dir=self.scripts_dir)
        self.pronunciation_engine = PronunciationEngine()
        self.director = SceneDirector(script_manager=self.script_manager)
        self.searcher = MediaSearcher(
            media_cache_dir=self.media_cache_dir,
            enable_synthetic_fallback=self.allow_placeholders,
        )
        self.assembly_planner = AssemblyPlanner(deduplicator=self.searcher.deduplicator)
        self.quality_checker = QualityChecker()
        self.pre_visualizer = PreVisualizer()
        self.typography_engine = TypographyEngine()
        from app.services.editorial.credits_generator import CreditsGenerator
        self.credits_generator = CreditsGenerator(catalog=self.searcher.asset_catalog)
        self.voice_name = voice_name

    def produce_draft(
        self,
        script_id: str,
        script_text: str,
        *,
        title: str = "",
        channel: str = "default",
        brand_style: str = "editorial",
        voice_name: Optional[str] = None,
        bgm_path: Optional[str | Path] = None,
        bgm_volume: float = 0.20,
        enforce_quality_gate: bool = True,
        allow_unpassed_draft: bool = False,
        on_progress: Optional[Callable[[str, float], None]] = None,
    ) -> dict[str, Any]:
        """Executes the complete pipeline:

        1. Save & lock human script version
        2. Direct script into scenes (LLM)
        3. Synthesize voice audio with timestamps for each scene
        4. Search and select media candidates
        5. Initialize VideoProject and render draft video
        """
        chosen_voice = voice_name or self.voice_name
        project_folder = self.projects_dir / script_id
        project_folder.mkdir(parents=True, exist_ok=True)

        # Reset media searcher deduplication state for this production run
        self.searcher.reset()

        # 1. Direct Script (Saves script_v00X and generates ScenePlan)
        if on_progress:
            on_progress("Directing script into visual scenes...", 0.20)
        plan = self.director.direct_script(
            script_id=script_id,
            script_text=script_text,
            title=title,
            channel=channel,
            brand_preset=brand_style,
            output_dir=project_folder,
        )

        # 2. Voice Synthesis for each scene
        audio_dir = project_folder / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        accum_time = 0.0
        total_scenes = len(plan.scenes)
        for idx, scene in enumerate(plan.scenes):
            if on_progress:
                voice_pct = 0.20 + (idx / max(1, total_scenes)) * 0.35
                on_progress(f"Sintetizando voz: cena {idx+1}/{total_scenes} ({scene.scene_id})...", voice_pct)
            audio_path = audio_dir / f"{scene.scene_id}.mp3"
            # Apply pronunciation engine to translate formulas/acronyms for the TTS
            spoken_text = self.pronunciation_engine.to_spoken(scene.narration)
            voice.tts(
                text=spoken_text,
                voice_name=chosen_voice,
                voice_rate=1.0,
                voice_file=str(audio_path),
            )
            # Master the voice track to EBU R128 (-14.0 LUFS) with high-pass and compressor
            mastered_path = audio_dir / f"{scene.scene_id}_mastered.mp3"
            try:
                master_voice_track(audio_path, mastered_path, target_lufs=-14.0)
                final_audio_path = mastered_path
            except Exception as e:
                logger.warning("Voice mastering failed for scene {}: {}. Using unmastered audio.", scene.scene_id, e)
                final_audio_path = audio_path

            scene.overlay = scene.overlay or {}
            scene.overlay["spoken_text"] = spoken_text
            scene.overlay["audio_file"] = str(final_audio_path)

            measured_dur = _measure_audio_duration(final_audio_path)
            if measured_dur > 0:
                scene.overlay["audio_duration"] = measured_dur
                scene.start = round(accum_time, 2)
                scene.end = round(accum_time + measured_dur, 2)
                accum_time += measured_dur
            elif scene.end is not None and scene.start is not None:
                accum_time = scene.end

        if accum_time > 0:
            plan.estimated_duration = round(accum_time, 2)

        # 3. Media Search & Candidate Collection
        def search_progress(sub_msg: str, frac: float):
            if on_progress:
                on_progress(sub_msg, 0.55 + frac * 0.20)

        self.searcher.populate_scene_plan(
            plan=plan,
            candidates_per_scene=5,
            download_selected=True,
            save_plan_path=project_folder / "scenes.json",
            on_progress=search_progress,
        )

        # 4. Generate AssemblyPlan and Run Quality Check
        if on_progress:
            on_progress("Building assembly plan and evaluating quality...", 0.75)
        assembly_plan = self.assembly_planner.build_plan(plan)
        quality_score = self.quality_checker.evaluate(assembly_plan)

        assembly_plan_path = project_folder / "assembly_plan.json"
        with assembly_plan_path.open("w", encoding="utf-8") as f:
            f.write(assembly_plan.to_json(indent=2))

        # Generate pre-render storyboard reports (HTML & Markdown)
        storyboard_files = self.pre_visualizer.save_reports(
            plan=assembly_plan,
            output_dir=project_folder,
            scene_plan=plan,
            title=title or getattr(plan, "title", ""),
        )

        # Generate credits and license manifest
        credits_files = self.credits_generator.save_credits(
            plan=assembly_plan,
            output_dir=project_folder,
            project_title=title or getattr(plan, "title", ""),
        )

        # Enforce Quality Gate: block rendering if rejected unless explicitly allowed as preview
        if enforce_quality_gate and not allow_unpassed_draft and not quality_score.passed:
            alert_summary = ", ".join(quality_score.alerts) if quality_score.alerts else "unspecified quality violations"
            logger.warning(
                "Quality Gate REJECTED draft for script '{}': {}",
                script_id, alert_summary
            )
            return {
                "script_id": script_id,
                "revision_id": None,
                "status": "rejected_by_quality_gate",
                "plan_path": str(project_folder / "scenes.json"),
                "assembly_plan_path": str(assembly_plan_path),
                "storyboard_md_path": str(storyboard_files["markdown"]),
                "storyboard_html_path": str(storyboard_files["html"]),
                "credits_md_path": str(credits_files["credits_md"]),
                "manifest_json_path": str(credits_files["manifest_json"]),
                "quality_score": quality_score.to_dict(),
                "video_path": None,
                "total_scenes": plan.total_scenes,
                "estimated_duration": plan.estimated_duration,
                "error": f"Quality Gate failed: {alert_summary}",
            }

        # 5. Assemble Project Manifest for VideoProject
        if on_progress:
            on_progress("Creating editable project manifest...", 0.85)
        project_scenes = []
        scene_by_id = {s.scene_id: s for s in plan.scenes}
        overlays_dir = project_folder / "overlays"
        composited_dir = project_folder / "composited"
        ken_burns_dir = project_folder / "ken_burns"

        total_segments = len(assembly_plan.segments)
        for seg_idx, segment in enumerate(assembly_plan.segments):
            if on_progress:
                comp_pct = 0.75 + (seg_idx / max(1, total_segments)) * 0.15
                on_progress(f"Compondo cena {seg_idx+1}/{total_segments} ({segment.segment_id})...", comp_pct)
            scene = scene_by_id.get(segment.scene_ref)
            narration = scene.narration if scene else ""
            audio_path = (scene.overlay or {}).get("audio_file") if scene else None
            footage_path = segment.asset_path
            scene_key = segment.segment_id
            seg_duration = float(segment.end - segment.start)

            # If asset is an editorial component, render it programmatically
            if segment.asset_type in ("price_tag", "split_screen", "historical_archive", "data_card", "editorial_crop"):
                comp_video = project_folder / "components" / f"{segment.segment_id}_{segment.asset_type}.mp4"
                comp_video.parent.mkdir(parents=True, exist_ok=True)
                if not comp_video.exists():
                    try:
                        from app.services.graphics.graphics_engine import GraphicsEngine
                        ge = GraphicsEngine()
                        rendered = ge.render_editorial_component(
                            component_type=segment.asset_type,
                            output_path=comp_video,
                            duration=seg_duration,
                            metadata={
                                "text": segment.overlay_text or narration,
                                "title": narration[:30] if narration else "",
                                "subtitle": segment.overlay_text or "",
                                "value": segment.overlay_text or "100%",
                                "label": narration[:20] if narration else "MÉTRICA",
                                "year": "1980",
                                "label_left": "ANTES",
                                "label_right": "DEPOIS",
                            },
                        )
                        if rendered and Path(rendered).exists():
                            footage_path = str(rendered)
                    except Exception as e:
                        logger.warning("Failed to render component {}: {}", segment.asset_type, e)

            if not footage_path or not Path(footage_path).exists():
                if self.allow_placeholders or allow_unpassed_draft:
                    # Fallback to synthetic clip if permitted for test/preview
                    fallback_clip = self.media_cache_dir / f"fallback_{scene_key}.mp4"
                    from .media_ranker.candidate_builder import _generate_synthetic_clip
                    query = scene.queries[0] if (scene and scene.queries) else (narration or segment.segment_id)
                    _generate_synthetic_clip(query, fallback_clip)
                    footage_path = str(fallback_clip)
                    logger.warning("Segment '{}' using synthetic placeholder fallback: {}", scene_key, fallback_clip)
                else:
                    logger.error("Segment '{}' missing valid footage file: {}", scene_key, footage_path)

            # If asset is a static image, convert to vertical Ken Burns video clip
            if footage_path and Path(footage_path).exists() and is_image_file(footage_path):
                ken_burns_dir.mkdir(parents=True, exist_ok=True)
                kb_clip = ken_burns_dir / f"{scene_key}_kb.mp4"
                motion = getattr(scene, "preferred_motion", "zoom_in") if scene else "zoom_in"
                try:
                    create_ken_burns_clip(
                        image_path=footage_path,
                        output_path=kb_clip,
                        duration=max(seg_duration, 3.0),
                        motion=motion,
                    )
                    footage_path = str(kb_clip)
                except Exception as e:
                    logger.warning("Ken Burns animation failed for '{}': {}", footage_path, e)

            # If segment has text overlay and is not a component card, render safe area PNG and composite onto clip
            if segment.asset_type not in ("price_tag", "split_screen", "historical_archive", "data_card", "editorial_crop"):
                if segment.overlay_text and segment.overlay_text.strip() and footage_path and Path(footage_path).exists():
                    try:
                        overlays_dir.mkdir(parents=True, exist_ok=True)
                        composited_dir.mkdir(parents=True, exist_ok=True)
                        overlay_png = overlays_dir / f"{scene_key}_overlay.png"
                        self.typography_engine.render_overlay_to_file(
                            text=segment.overlay_text,
                            output_path=overlay_png,
                            level=segment.text_level,
                        )
                        comp_clip = composited_dir / f"{scene_key}_comp.mp4"
                        composite_overlay_to_clip(
                            video_path=footage_path,
                            overlay_png_path=overlay_png,
                            output_path=comp_clip,
                        )
                        footage_path = str(comp_clip)
                    except Exception as e:
                        logger.warning("Typography overlay composition failed for segment '{}': {}", scene_key, e)

            # Handle audio for multi-beat scene segments
            seg_audio_file = audio_path
            if scene and getattr(scene, "has_multiple_beats", False) and audio_path and Path(audio_path).exists():
                scene_st = scene.start if scene.start is not None else 0.0
                rel_st = max(0.0, round(segment.start - scene_st, 2))
                beat_audio = audio_dir / f"{scene_key}_audio.mp3"
                if not beat_audio.exists():
                    try:
                        import subprocess
                        cmd_slice = [
                            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                            "-ss", str(rel_st),
                            "-t", str(seg_duration),
                            "-i", str(audio_path),
                            "-c:a", "libmp3lame", "-q:a", "2",
                            str(beat_audio),
                        ]
                        subprocess.run(cmd_slice, check=True)
                        seg_audio_file = str(beat_audio)
                    except Exception as e:
                        logger.warning("Audio slice failed for segment {}: {}", scene_key, e)
                else:
                    seg_audio_file = str(beat_audio)

            resolved_path = str(Path(footage_path).resolve()) if (footage_path and Path(footage_path).exists()) else (footage_path or "")
            project_scenes.append(
                {
                    "id": scene_key,
                    "narration": narration,
                    "duration": seg_duration,
                    "footage": resolved_path,
                    "audio": audio_path,
                }
            )

        video_project = VideoProject(project_folder / "render_project")
        rev_spec = video_project.create_revision(
            {
                "project_id": script_id,
                "settings": {"width": 1080, "height": 1920, "fps": 30},
                "scenes": project_scenes,
            }
        )
        rev_id = rev_spec["revision_id"]

        # 6. Render Video Draft
        if on_progress:
            on_progress("Rendering draft video with FFmpeg...", 0.90)
        render_status = video_project.render(rev_id)

        if on_progress:
            on_progress("Production completed!", 1.0)

        export_info = render_status.get("export", {})
        final_video_path = export_info.get("path")

        # 7. Optional Adaptive BGM Automation & Remuxing
        if bgm_path and Path(bgm_path).exists() and final_video_path and Path(final_video_path).exists():
            if on_progress:
                on_progress("Applying adaptive BGM automation with sidechain ducking...", 0.95)
            try:
                import subprocess
                extracted_voice = project_folder / "audio" / "extracted_voice.wav"
                cmd_extract = [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", str(final_video_path),
                    "-vn", "-ac", "2", "-ar", "48000",
                    str(extracted_voice),
                ]
                subprocess.run(cmd_extract, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                mixed_audio = project_folder / "audio" / "adaptive_bgm_mix.wav"
                phase_segments = [s.to_dict() for s in assembly_plan.segments]
                mix_voice_with_adaptive_bgm(
                    voice_path=extracted_voice,
                    bgm_path=bgm_path,
                    output_path=mixed_audio,
                    phase_segments=phase_segments,
                    base_volume=bgm_volume,
                )

                remuxed_video = project_folder / f"{script_id}_mastered.mp4"
                remux_video_with_audio(
                    video_path=final_video_path,
                    audio_path=mixed_audio,
                    output_path=remuxed_video,
                )
                final_video_path = str(remuxed_video)
            except Exception as e:
                logger.warning("Adaptive BGM automation failed for script '{}': {}", script_id, e)

        final_status = "preview_unpassed_quality" if (not quality_score.passed and allow_unpassed_draft) else render_status["state"]
        return {
            "script_id": script_id,
            "revision_id": rev_id,
            "status": final_status,
            "plan_path": str(project_folder / "scenes.json"),
            "assembly_plan_path": str(assembly_plan_path),
            "storyboard_md_path": str(storyboard_files["markdown"]),
            "storyboard_html_path": str(storyboard_files["html"]),
            "credits_md_path": str(credits_files["credits_md"]),
            "manifest_json_path": str(credits_files["manifest_json"]),
            "quality_score": quality_score.to_dict(),
            "video_path": final_video_path,
            "total_scenes": plan.total_scenes,
            "estimated_duration": plan.estimated_duration,
        }

    def render_existing_draft(
        self,
        script_id: str,
        on_progress: Optional[Callable[[str, float], None]] = None,
    ) -> dict[str, Any]:
        """Renders video from an existing assembly plan without re-fetching media or TTS."""
        project_folder = self.projects_dir / script_id
        plan_file = project_folder / "scenes.json"
        assembly_file = project_folder / "assembly_plan.json"

        if not plan_file.exists() or not assembly_file.exists():
            raise FileNotFoundError(f"Project files missing for {script_id}")

        with plan_file.open("r", encoding="utf-8") as f:
            plan = ScenePlan.from_dict(json.load(f))
        with assembly_file.open("r", encoding="utf-8") as f:
            assembly_plan = AssemblyPlan.from_dict(json.load(f))

        if on_progress:
            on_progress("Preparando composição das cenas existentes...", 0.1)

        project_scenes = []
        scene_by_id = {s.scene_id: s for s in plan.scenes}
        overlays_dir = project_folder / "overlays"
        composited_dir = project_folder / "composited"
        ken_burns_dir = project_folder / "ken_burns"
        audio_dir = project_folder / "audio"

        total_segments = len(assembly_plan.segments)
        for seg_idx, segment in enumerate(assembly_plan.segments):
            if on_progress:
                comp_pct = 0.1 + (seg_idx / max(1, total_segments)) * 0.6
                on_progress(f"Compondo cena {seg_idx+1}/{total_segments}...", comp_pct)

            scene = scene_by_id.get(segment.scene_ref)
            narration = scene.narration if scene else ""
            audio_path = (scene.overlay or {}).get("audio_file") if scene else None
            footage_path = segment.asset_path
            scene_key = segment.segment_id
            seg_duration = float(segment.end - segment.start)

            if not footage_path or not Path(footage_path).exists():
                fallback_clip = self.media_cache_dir / f"fallback_{scene_key}.mp4"
                from .media_ranker.candidate_builder import _generate_synthetic_clip
                query = scene.queries[0] if (scene and scene.queries) else (narration or segment.segment_id)
                _generate_synthetic_clip(query, fallback_clip)
                footage_path = str(fallback_clip)

            if footage_path and Path(footage_path).exists() and is_image_file(footage_path):
                ken_burns_dir.mkdir(parents=True, exist_ok=True)
                kb_clip = ken_burns_dir / f"{scene_key}_kb.mp4"
                motion = getattr(scene, "preferred_motion", "zoom_in") if scene else "zoom_in"
                try:
                    create_ken_burns_clip(
                        image_path=footage_path,
                        output_path=kb_clip,
                        duration=max(seg_duration, 3.0),
                        motion=motion,
                    )
                    footage_path = str(kb_clip)
                except Exception as e:
                    logger.warning("Ken Burns animation failed for '{}': {}", footage_path, e)

            if segment.asset_type not in ("price_tag", "split_screen", "historical_archive", "data_card", "editorial_crop"):
                if segment.overlay_text and segment.overlay_text.strip() and footage_path and Path(footage_path).exists():
                    try:
                        overlays_dir.mkdir(parents=True, exist_ok=True)
                        composited_dir.mkdir(parents=True, exist_ok=True)
                        overlay_png = overlays_dir / f"{scene_key}_overlay.png"
                        self.typography_engine.render_overlay_to_file(
                            text=segment.overlay_text,
                            output_path=overlay_png,
                            level=segment.text_level,
                        )
                        comp_clip = composited_dir / f"{scene_key}_comp.mp4"
                        composite_overlay_to_clip(
                            video_path=footage_path,
                            overlay_png_path=overlay_png,
                            output_path=comp_clip,
                        )
                        footage_path = str(comp_clip)
                    except Exception as e:
                        logger.warning("Typography overlay composition failed for segment '{}': {}", scene_key, e)

            resolved_path = str(Path(footage_path).resolve()) if (footage_path and Path(footage_path).exists()) else (footage_path or "")
            project_scenes.append(
                {
                    "id": scene_key,
                    "narration": narration,
                    "duration": seg_duration,
                    "footage": resolved_path,
                    "audio": audio_path,
                }
            )

        video_project = VideoProject(project_folder / "render_project")
        rev_spec = video_project.create_revision(
            {
                "project_id": script_id,
                "settings": {"width": 1080, "height": 1920, "fps": 30},
                "scenes": project_scenes,
            }
        )
        rev_id = rev_spec["revision_id"]

        if on_progress:
            on_progress("Renderizando vídeo final com FFmpeg...", 0.75)
        render_status = video_project.render(rev_id)

        if on_progress:
            on_progress("Renderização concluída com sucesso!", 1.0)

        export_info = render_status.get("export", {})
        final_video_path = export_info.get("path")

        return {
            "script_id": script_id,
            "revision_id": rev_id,
            "status": "rendered_force_preview",
            "video_path": final_video_path,
        }

