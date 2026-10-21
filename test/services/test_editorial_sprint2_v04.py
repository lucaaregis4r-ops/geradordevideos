"""Tests for Sprint 2 (v0.4) of the Mercadoria Editorial Pipeline.

Validates:
1. Ken Burns motion generator converts static images into 9:16 vertical MP4s (zoom-in, zoom-out, pan, static).
2. CandidateBuilder discovers local images and converts them using Ken Burns.
3. CandidateBuilder handles visual_type='stock_image' with cinematic photo plates.
4. AssemblyPlanner preserves multimedia asset_type taxonomy (video, photo, graphic, text_card).
5. QualityChecker rewards visual diversity when media formats are blended.
"""

from pathlib import Path
import pytest
from PIL import Image

from app.services.assembly.planner import AssemblyPlanner
from app.services.assembly.quality_checker import QualityChecker
from app.services.director.schemas import Scene, ScenePlan
from app.services.media_ranker.candidate_builder import CandidateBuilder
from app.services.utils.ken_burns import create_ken_burns_clip


def test_ken_burns_image_to_video_motions(tmp_path):
    """Validates that create_ken_burns_clip converts an image into 9:16 vertical MP4s with motion."""
    img_path = tmp_path / "test_input.png"
    # Create an arbitrary test image (1280x720 landscape to test cover cropping)
    img = Image.new("RGB", (1280, 720), color=(45, 120, 200))
    img.save(img_path)

    motions = ["zoom_in", "zoom_out", "pan_up", "static"]
    for motion in motions:
        out_path = tmp_path / f"out_{motion}.mp4"
        clip = create_ken_burns_clip(
            image_path=img_path,
            output_path=out_path,
            duration=1.5,
            motion=motion,
            width=1080,
            height=1920,
            fps=30,
        )
        assert clip.exists()
        assert clip.stat().st_size > 1000


def test_candidate_builder_detects_and_converts_local_photos(tmp_path):
    """Validates that CandidateBuilder finds local photos and returns them as local_photo candidates."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Place a photo matching "tshirt" in cache
    photo_file = cache_dir / "cotton_tshirt_store.jpg"
    img = Image.new("RGB", (1080, 1920), color=(20, 150, 80))
    img.save(photo_file)

    builder = CandidateBuilder(media_cache_dir=cache_dir)
    matches = builder.search_local_library(query="tshirt price tag", target_duration=2.0)

    assert len(matches) >= 1
    match = next(m for m in matches if "tshirt" in m.asset_id)
    assert match.provider == "local_photo"
    assert match.local_path is not None
    assert Path(match.local_path).exists()
    assert match.local_path.endswith(".mp4")


def test_candidate_builder_photo_intent_generates_photo_clip(tmp_path):
    """Validates synthetic fallback for stock_image generates a Ken Burns photo clip."""
    cache_dir = tmp_path / "cache"
    builder = CandidateBuilder(media_cache_dir=cache_dir)

    candidates = builder.search_query(
        query="lithium mining workers",
        target_duration=2.5,
        visual_type="stock_image",
        preferred_motion="zoom_in",
    )

    assert len(candidates) >= 1
    top = candidates[0]
    assert top.provider == "synthetic_photo"
    assert Path(top.local_path).exists()
    assert top.local_path.endswith(".mp4")


def test_assembly_planner_preserves_multimedia_types():
    """Validates that AssemblyPlanner maps scenes to diverse asset_type values (video, photo, graphic)."""
    planner = AssemblyPlanner()

    scenes = [
        Scene(
            scene_id="s1",
            narration="Uma camiseta custa oitenta reais.",
            intent="hook",
            queries=["tshirt store"],
            visual_type="stock_video",
            selected_media={"asset_id": "vid_1", "type": "video", "local_path": "/tmp/1.mp4"},
        ),
        Scene(
            scene_id="s2",
            narration="Foto histórica da fábrica têxtil.",
            intent="contexto",
            queries=["textile factory old photo"],
            visual_type="stock_image",
            selected_media={"asset_id": "photo_1", "local_path": "/tmp/photo.mp4"},
        ),
        Scene(
            scene_id="s3",
            narration="Relação entre trabalho e valor.",
            intent="conceito",
            queries=["formula value"],
            visual_type="graphic",
            selected_media={"asset_id": "card_1", "local_path": "/tmp/card.mp4"},
        ),
    ]

    scene_plan = ScenePlan(
        script_id="multimedia_test",
        script_version="v001",
        script_hash="h1",
        total_scenes=3,
        estimated_duration=9.0,
        scenes=scenes,
    )

    assembly_plan = planner.build_plan(scene_plan)
    assert len(assembly_plan.segments) == 3

    seg_types = [s.asset_type for s in assembly_plan.segments]
    assert "video" in seg_types
    assert "photo" in seg_types
    assert "graphic" in seg_types


def test_quality_checker_high_visual_diversity():
    """Validates that mixed media receives high visual_diversity score and passes QualityChecker."""
    planner = AssemblyPlanner()
    checker = QualityChecker()

    scenes = [
        Scene(
            scene_id="s1",
            narration="Cena 1 com vídeo.",
            intent="hook",
            queries=["dubai"],
            visual_type="stock_video",
            selected_media={"asset_id": "v1", "local_path": "/tmp/v1.mp4"},
        ),
        Scene(
            scene_id="s2",
            narration="Cena 2 com fotografia.",
            intent="example",
            queries=["tshirt"],
            visual_type="stock_image",
            selected_media={"asset_id": "p1", "local_path": "/tmp/p1.mp4"},
        ),
        Scene(
            scene_id="s3",
            narration="Cena 3 com cartela gráfica.",
            intent="concept",
            queries=["graph"],
            visual_type="graphic",
            selected_media={"asset_id": "g1", "local_path": "/tmp/g1.mp4"},
        ),
    ]

    scene_plan = ScenePlan(
        script_id="diversity_test",
        script_version="v001",
        script_hash="h_div",
        total_scenes=3,
        estimated_duration=9.0,
        scenes=scenes,
    )

    assembly_plan = planner.build_plan(scene_plan)
    quality_score = checker.evaluate(assembly_plan)

    assert quality_score.passed is True
    # With 3 distinct types out of 3 segments, diversity is high
    assert quality_score.visual_diversity >= 0.50
