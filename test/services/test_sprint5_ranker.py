"""Sprint 5 Automated Tests: Semantic Media Ranker & Smart Library.

Validates:
1. Fast video frame extraction via Thumbnailer.
2. Smart Library asset registration, catalog persistence, and search prioritization.
3. Composite weighted scoring in SemanticRanker.
4. Two-stage ranking pipeline (Technical Filter -> Semantic Ranker).
"""

import json
from pathlib import Path
import pytest

from app.services.director.schemas import Scene
from app.services.media_ranker import (
    CandidateBuilder,
    MediaCandidate,
    MediaSearcher,
    SemanticRanker,
    SmartLibrary,
    Thumbnailer,
)
from app.services.media_ranker.candidate_builder import _generate_synthetic_clip


def test_thumbnailer_extraction(tmp_path: Path):
    video_path = tmp_path / "test_clip.mp4"
    _generate_synthetic_clip("carrinho supermercado", video_path, duration=3.0)
    assert video_path.exists()

    thumb_dir = tmp_path / "thumbs"
    thumbnailer = Thumbnailer(thumbnail_dir=thumb_dir)
    thumb_path = thumbnailer.extract_thumbnail(video_path, timestamp_sec=1.0)

    assert thumb_path is not None
    assert Path(thumb_path).exists()
    assert Path(thumb_path).stat().st_size > 0
    assert thumb_path.endswith(".jpg")


def test_smart_library_approval_and_search(tmp_path: Path):
    lib_dir = tmp_path / "smart_lib"
    library = SmartLibrary(library_dir=lib_dir)

    # 1. Create a dummy video to approve
    media_file = tmp_path / "heavy_cart_001.mp4"
    _generate_synthetic_clip("carrinho pesado supermercado", media_file, duration=4.0)

    # 2. Register approved asset with tags
    asset = library.register_approved_asset(
        media_path=media_file,
        tags=["shopping cart", "supermarket", "heavy", "physics", "mass", "force"],
        intent="demonstrar aumento de massa com carrinho cheio",
        asset_id="cart_heavy_001",
        duration=4.0,
    )

    assert asset.asset_id == "cart_heavy_001"
    assert asset.approved is True
    assert (lib_dir / "catalog.json").exists()

    # 3. Reload catalog in a new instance and search
    reloaded_lib = SmartLibrary(library_dir=lib_dir)
    results = reloaded_lib.search_library(query="shopping cart supermarket physics")

    assert len(results) >= 1
    top = results[0]
    assert top.asset_id == "cart_heavy_001"
    assert top.provider == "smart_library"
    assert top.final_score >= 0.90


def test_semantic_ranker_composite_scoring(tmp_path: Path):
    ranker = SemanticRanker()

    c_relevant_portrait = MediaCandidate(
        provider="stock",
        asset_id="rel_port",
        query="person pushing heavy shopping cart",
        width=1080,
        height=1920,
        duration=5.0,
        url="http://example.com/rel_port.mp4",
        semantic_score=0.92,
        description="Pessoa empurrar carrinho cheio dificuldade massa",
    )

    c_irrelevant_landscape = MediaCandidate(
        provider="stock",
        asset_id="irrel_land",
        query="tropical beach ocean sunset",
        width=1920,
        height=1080,
        duration=5.0,
        url="http://example.com/irrel_land.mp4",
        semantic_score=0.20,
        description="tropical beach ocean sunset",
    )

    ranked = ranker.rank_candidates(
        scene_narration="Mas empurrar um carrinho cheio é outra história.",
        scene_intent="demonstrar aumento da dificuldade devido à massa",
        candidates=[c_irrelevant_landscape, c_relevant_portrait],
        top_k=2,
    )

    assert ranked[0].asset_id == "rel_port"
    assert ranked[0].final_score > ranked[1].final_score
    assert ranked[0].semantic_score >= 0.85
    assert ranked[0].semantic_status == "metadata_only"
    assert ranked[1].final_score < 0.60


def test_media_searcher_two_stage_pipeline(tmp_path: Path):
    media_dir = tmp_path / "media_cache"
    searcher = MediaSearcher(media_cache_dir=media_dir)

    scene = Scene(
        scene_id="scene_001",
        narration="Você provavelmente aprendeu que força é massa vezes aceleração.",
        intent="mostrar fórmula e cálculo de física",
        queries=["physics calculation chalkboard", "science formula blackboard"],
        visual_type="formula",
    )

    top_candidates = searcher.search_for_scene(scene, target_duration=4.0, candidates_per_scene=3)

    assert len(top_candidates) >= 1
    assert len(top_candidates) <= 3
    for c in top_candidates:
        assert c.technical_score > 0.0
        assert c.final_score > 0.0
