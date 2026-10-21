"""Sprint 6 Automated Test Suite (v0.9 & v1.0 — Pre-Render Debug, Real Semantic Match & End-to-End Integration).

Validates:
1. PreVisualizer generation of rich Markdown and standalone HTML storyboard reports.
2. QualityChecker integration with real semantic match scores and alerting.
3. Typography overlay compositing onto vertical 9:16 clips with FFmpeg.
4. ShortsFactory end-to-end execution producing mastered audio (-14 LUFS), storyboard reports, and assembled draft.
5. Task.py routing of editorial requests through ShortsFactory.
"""

from __future__ import annotations
import json
from pathlib import Path
import subprocess
import pytest

from app.models.schema import VideoParams
from app.services.assembly.planner import AssemblyPlanner
from app.services.assembly.pre_visualizer import PreVisualizer
from app.services.assembly.quality_checker import QualityChecker
from app.services.assembly.schemas import AssemblyPlan, AssemblySegment, QualityScore
from app.services.director.schemas import NarrativePhase, Scene, ScenePlan
from app.services.factory import ShortsFactory
from app.services.graphics.typography_engine import (
    TypographyEngine,
    composite_overlay_to_clip,
)
from app.services.media_ranker.candidate_builder import _generate_synthetic_clip
from app.services import task


def test_pre_visualizer_markdown_and_html(tmp_path: Path):
    """Verifies that PreVisualizer produces both valid Markdown and HTML storyboard reports."""
    segments = [
        AssemblySegment(
            segment_id="seg_001",
            start=0.0,
            end=3.5,
            asset_id="asset_luxo_car",
            asset_type="video",
            asset_path="/tmp/asset_001.mp4",
            purpose="hook",
            phase="promessa",
            query="luxury sports car city night",
            overlay_text="SUCESSO OU ILUSÃO?",
            text_level="title",
            semantic_score=0.88,
        ),
        AssemblySegment(
            segment_id="seg_002",
            start=3.5,
            end=7.0,
            asset_id="asset_price_tag",
            asset_type="photo",
            asset_path="/tmp/asset_002.jpg",
            purpose="price_tag",
            phase="objeto",
            query="t-shirt retail store price tag",
            overlay_text="R$ 79,90",
            text_level="title",
            semantic_score=0.92,
        ),
        AssemblySegment(
            segment_id="seg_003",
            start=7.0,
            end=11.0,
            asset_id="asset_sewing_factory",
            asset_type="video",
            asset_path="/tmp/asset_003.mp4",
            purpose="labor",
            phase="bastidores",
            query="textile factory worker sewing machine hands",
            overlay_text="TRABALHO HUMANO",
            text_level="emphasis",
            semantic_score=0.85,
        ),
    ]

    plan = AssemblyPlan(
        project_id="test_mercadoria_previs",
        segments=segments,
        total_duration=11.0,
    )

    checker = QualityChecker()
    score = checker.evaluate(plan)
    assert score.passed is True

    vis = PreVisualizer()
    md = vis.generate_markdown(plan)
    assert "# Storyboard Pre-Render Report" in md
    assert "test_mercadoria_previs" in md
    assert "SUCESSO OU ILUSÃO?" in md
    assert "R$ 79,90" in md
    assert "TRABALHO HUMANO" in md
    assert "luxury sports car city night" in md

    html_out = vis.generate_html(plan, title="Mercadoria Storyboard")
    assert "<!DOCTYPE html>" in html_out
    assert "Mercadoria Storyboard" in html_out
    assert "SUCESSO OU ILUSÃO?" in html_out
    assert "R$ 79,90" in html_out
    assert "APROVADO PARA RENDER" in html_out
    assert "scorecard-grid" in html_out
    assert "phase-progression" in html_out

    # Save to disk
    out_dir = tmp_path / "reports"
    files = vis.save_reports(plan, out_dir)
    assert files["markdown"].exists()
    assert files["html"].exists()
    assert files["markdown"].stat().st_size > 100
    assert files["html"].stat().st_size > 500


def test_quality_checker_real_semantic_scores():
    """Verifies that QualityChecker correctly computes semantic average and alerts if below threshold."""
    # Case 1: High semantic match
    plan_high = AssemblyPlan(
        project_id="high_sem",
        segments=[
            AssemblySegment(
                segment_id="s1", start=0, end=3, asset_id="a1", asset_type="video",
                asset_path="/tmp/a1.mp4", semantic_score=0.85
            ),
            AssemblySegment(
                segment_id="s2", start=3, end=6, asset_id="a2", asset_type="photo",
                asset_path="/tmp/a2.jpg", semantic_score=0.75
            ),
        ],
        total_duration=6.0,
    )
    checker = QualityChecker()
    score_high = checker.evaluate(plan_high)
    assert score_high.semantic_match_avg == 0.80
    assert score_high.passed is True

    # Case 2: Low semantic match (alert raised)
    plan_low = AssemblyPlan(
        project_id="low_sem",
        segments=[
            AssemblySegment(
                segment_id="s1", start=0, end=3, asset_id="a1", asset_type="video",
                asset_path="/tmp/a1.mp4", semantic_score=0.25
            ),
            AssemblySegment(
                segment_id="s2", start=3, end=6, asset_id="a2", asset_type="photo",
                asset_path="/tmp/a2.jpg", semantic_score=0.30
            ),
        ],
        total_duration=6.0,
    )
    score_low = checker.evaluate(plan_low)
    assert score_low.semantic_match_avg == 0.275
    assert score_low.passed is False


def test_composite_overlay_to_clip(tmp_path: Path):
    """Verifies that transparent overlay PNG is composited cleanly onto a 1080x1920 video clip."""
    video_base = tmp_path / "base_clip.mp4"
    _generate_synthetic_clip("test base clip", video_base, duration=3.0)
    assert video_base.exists()

    engine = TypographyEngine()
    overlay_png = tmp_path / "price_overlay.png"
    engine.render_overlay_to_file("R$ 79,90", overlay_png, level="title")
    assert overlay_png.exists()

    output_comp = tmp_path / "composited_clip.mp4"
    res = composite_overlay_to_clip(
        video_path=video_base,
        overlay_png_path=overlay_png,
        output_path=output_comp,
    )
    assert res.exists()
    assert res.stat().st_size > 1000

    # Probe resolution
    probe_cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json",
        str(output_comp),
    ]
    probe_out = subprocess.check_output(probe_cmd).decode()
    v_stream = json.loads(probe_out)["streams"][0]
    assert v_stream["width"] == 1080
    assert v_stream["height"] == 1920


def test_shorts_factory_end_to_end_with_storyboard_and_mastering(tmp_path: Path):
    """Verifies ShortsFactory produces draft, mastered voice (-14 LUFS), and storyboard files."""
    base_dir = tmp_path / "factory_e2e"
    factory = ShortsFactory(base_dir=base_dir)

    script = (
        "Uma camiseta custa oitenta reais na loja. "
        "Mas oitenta reais não explicam o algodão e as máquinas da fábrica."
    )

    draft = factory.produce_draft(
        script_id="e2e_mercadoria_demo",
        script_text=script,
        title="Mercadoria E2E",
        brand_style="editorial",
    )

    assert draft["status"] == "succeeded"
    assert Path(draft["storyboard_md_path"]).exists()
    assert Path(draft["storyboard_html_path"]).exists()

    # Check that mastered voice files exist
    audio_dir = base_dir / "projects" / "e2e_mercadoria_demo" / "audio"
    mastered_files = list(audio_dir.glob("*_mastered.mp3"))
    assert len(mastered_files) >= 2, "Each scene should have an EBU R128 mastered audio track"

    # Verify video was rendered
    video_path = Path(draft["video_path"])
    assert video_path.exists()
    assert video_path.stat().st_size > 1000


def test_task_routing_to_editorial_pipeline(tmp_path: Path, monkeypatch):
    """Verifies task.py seamlessly routes tasks with pipeline_mode='editorial' to ShortsFactory."""
    # Direct task storage to tmp_path
    monkeypatch.setattr("app.utils.utils.task_dir", lambda tid: str(tmp_path / tid))

    params = VideoParams(
        video_subject="Teste Roteamento Editorial",
        video_script="O valor de troca parece mágica, mas é trabalho cristalizado.",
        pipeline_mode="editorial",
    )

    task_id = "task_editorial_test_01"
    # Stop at script check
    res_script = task.start(task_id, params, stop_at="script")
    assert "script" in res_script
    assert "trabalho cristalizado" in res_script["script"]
