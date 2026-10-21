"""Tests for Sprint 2: Seleção Visual e Deduplicação Perceptual.

Validates:
1. Perceptual hashing (dHash, pHash, Hamming distance)
2. VisualEvaluator (multi-frame sampling, black/blank rejection, metrics)
3. MediaDeduplicator (perceptual duplicate penalty, author diversity cap, project reset)
4. SemanticRanker (removal of artificial 0.90 baseline for smart_library, true semantic matching)
5. QualityChecker (sliding window diversity, consecutive treatment limits)
"""

from pathlib import Path
import numpy as np
import pytest
from PIL import Image

from app.services.assembly.quality_checker import QualityChecker
from app.services.assembly.schemas import AssemblyPlan, AssemblySegment
from app.services.media_ranker.deduplicator import MediaDeduplicator
from app.services.media_ranker.perceptual_hash import (
    compute_dhash,
    compute_phash,
    hamming_distance,
    is_perceptual_match,
)
from app.services.media_ranker.schemas import MediaCandidate
from app.services.media_ranker.semantic_ranker import SemanticRanker
from app.services.media_ranker.visual_evaluator import VisualEvaluator


def test_perceptual_hashing_basic_and_distance():
    """Validates dHash, pHash, and Hamming distance calculation."""
    # Create test pattern 1
    im1 = Image.new("RGB", (120, 120), color=(200, 50, 50))
    # Rescaled version of the same pattern
    im1_scaled = Image.new("RGB", (240, 240), color=(200, 50, 50))

    # Completely different image (gradient / checkered)
    arr = np.zeros((120, 120, 3), dtype=np.uint8)
    arr[::2, ::2] = [255, 255, 255]
    im2 = Image.fromarray(arr)

    h1 = compute_phash(im1)
    h1_scaled = compute_phash(im1_scaled)
    h2 = compute_phash(im2)

    # Identical content resized must have Hamming distance <= 2
    assert hamming_distance(h1, h1_scaled) <= 2
    assert is_perceptual_match(h1, h1_scaled, max_distance=4) is True

    # Substantially different images must have Hamming distance > 10
    dist_diff = hamming_distance(h1, h2)
    assert dist_diff > 10
    assert is_perceptual_match(h1, h2, max_distance=8) is False

    # dHash test
    dh1 = compute_dhash(im1)
    dh2 = compute_dhash(im2)
    assert isinstance(dh1, str) and len(dh1) == 16
    assert isinstance(dh2, str) and len(dh2) == 16


def test_visual_evaluator_image_inspection(tmp_path):
    """Validates VisualEvaluator metrics, black frame detection, and corrupted file handling."""
    evaluator = VisualEvaluator(temp_dir=tmp_path / "thumbs")

    # 1. Healthy image
    healthy_path = tmp_path / "healthy.jpg"
    arr = np.zeros((300, 300, 3), dtype=np.uint8)
    for i in range(300):
        arr[i, :, :] = int(i * 255 / 300)
    arr[:, 150:, 0] = 200
    Image.fromarray(arr).save(healthy_path)

    metrics = evaluator.evaluate_media(healthy_path, media_type="photo")
    assert metrics.is_valid is True
    assert metrics.quality_score >= 0.35
    assert metrics.mean_luminance > 30.0
    assert metrics.mean_contrast > 20.0
    assert len(metrics.perceptual_hash) == 16

    # 2. Pitch black image
    black_path = tmp_path / "black.jpg"
    Image.new("RGB", (200, 200), color=(0, 0, 0)).save(black_path)
    black_metrics = evaluator.evaluate_media(black_path, media_type="photo")
    assert black_metrics.is_valid is False
    assert black_metrics.rejection_reason == "excessive_black_frames"
    assert black_metrics.quality_score <= 0.10

    # 3. Nonexistent file
    missing_metrics = evaluator.evaluate_media(tmp_path / "missing.jpg")
    assert missing_metrics.is_valid is False
    assert missing_metrics.rejection_reason == "file_not_found_or_empty"


def test_deduplicator_perceptual_duplicate_detection():
    """Validates that candidate with identical perceptual hash is penalized unless callback."""
    dedup = MediaDeduplicator()

    # Asset A selected for scene 1
    cand_a = MediaCandidate(
        provider="pexels",
        asset_id="asset_001",
        url="https://example.com/a.mp4",
        perceptual_hash="1122334455667788",
        final_score=0.90,
    )
    dedup.mark_used(cand_a, scene_id="scene_001")

    # Asset B from a different URL/provider, but with nearly identical pHash (Hamming distance 2)
    # Binary: '1122334455667788' vs '112233445566778a' (distance = 1 bit)
    cand_b_duplicate = MediaCandidate(
        provider="pixabay",
        asset_id="asset_002_diff_url",
        url="https://other.com/clip_b.mp4",
        perceptual_hash="112233445566778a",
        final_score=0.85,
    )

    # Fresh candidate C with completely different pHash
    cand_c_fresh = MediaCandidate(
        provider="commons",
        asset_id="asset_003_fresh",
        url="https://commons.wikimedia.org/c.jpg",
        perceptual_hash="ffff0000aaaa5555",
        final_score=0.80,
    )

    scored = dedup.score_candidates([cand_b_duplicate, cand_c_fresh])

    # cand_b_duplicate must suffer severe perceptual duplicate penalty (final_score *= 0.05)
    b_res = next(c for c in scored if c.asset_id == "asset_002_diff_url")
    assert b_res.final_score < 0.10

    # cand_c_fresh remains unpenalized
    c_res = next(c for c in scored if c.asset_id == "asset_003_fresh")
    assert c_res.final_score == 0.80

    # Test intentional callback bypass
    callback_scored = dedup.score_candidates(
        [cand_b_duplicate],
        intentional_callback="scene_001",
    )
    # Exact callback asset is promoted to >= 0.95
    cb_a = MediaCandidate(
        asset_id="asset_001",
        perceptual_hash="1122334455667788",
        final_score=0.50,
    )
    res_cb = dedup.score_candidates([cb_a], intentional_callback="scene_001")
    assert res_cb[0].final_score >= 0.95


def test_deduplicator_creator_diversity_cap():
    """Validates that a creator is limited to max 2 assets across the video."""
    dedup = MediaDeduplicator()

    # Use 2 assets by "Maria Silva"
    c1 = MediaCandidate(asset_id="v1", creator_name="Maria Silva", final_score=0.9)
    c2 = MediaCandidate(asset_id="v2", creator_name="Maria Silva", final_score=0.9)
    dedup.mark_used(c1, scene_id="s1")
    dedup.mark_used(c2, scene_id="s2")

    # 3rd asset by Maria Silva vs 1st asset by Carlos
    c3 = MediaCandidate(asset_id="v3", creator_name="Maria Silva", final_score=0.85)
    c4 = MediaCandidate(asset_id="v4", creator_name="Carlos Lima", final_score=0.80)

    scored = dedup.score_candidates([c3, c4])

    # c3 receives 0.2x penalty for exceeding author quota
    s_c3 = next(c for c in scored if c.asset_id == "v3")
    assert pytest.approx(s_c3.final_score, 0.01) == 0.85 * 0.2

    # c4 is untouched
    s_c4 = next(c for c in scored if c.asset_id == "v4")
    assert s_c4.final_score == 0.80


def test_deduplicator_reset_isolates_projects():
    """Validates that dedup.reset() clears all state and isolates consecutive video jobs."""
    dedup = MediaDeduplicator()

    cand = MediaCandidate(
        asset_id="clip_x",
        creator_name="Director A",
        perceptual_hash="12345678abcdef00",
        final_score=0.9,
    )
    dedup.mark_used(cand, scene_id="scene_01")
    assert dedup.is_used("clip_x") is True
    assert dedup.used_asset_count == 1

    # Reset for next project
    dedup.reset()
    assert dedup.is_used("clip_x") is False
    assert dedup.used_asset_count == 0
    assert len(dedup._seen_perceptual_hashes) == 0
    assert len(dedup._creator_usage) == 0

    # Same candidate scored in new project should not suffer reuse penalty
    test_cand = MediaCandidate(
        asset_id="clip_x",
        creator_name="Director A",
        perceptual_hash="12345678abcdef00",
        final_score=0.9,
    )
    scored = dedup.score_candidates([test_cand])
    assert scored[0].final_score == 0.9


def test_semantic_ranker_no_artificial_smart_library_bonus():
    """Validates that smart_library assets no longer receive an automatic 0.90 floor."""
    ranker = SemanticRanker()

    narration = "Uma camiseta de algodão custa oitenta reais na loja de shopping."
    intent = "Mostrar camiseta exposta em vitrine ou cabide com etiqueta de preço"

    # Irrelevant asset from smart_library (e.g. space rocket)
    irrelevant_local = MediaCandidate(
        provider="smart_library",
        asset_id="local_rocket_01",
        query="space rocket nasa launch",
        category="space",
        final_score=0.0,
    )

    # Relevant external stock video
    relevant_stock = MediaCandidate(
        provider="pexels",
        asset_id="pexels_shirt_01",
        query="t-shirt store mannequin clothing price tag",
        category="commodity",
        final_score=0.0,
    )

    ranked = ranker.rank_candidates(
        scene_narration=narration,
        scene_intent=intent,
        candidates=[irrelevant_local, relevant_stock],
    )

    # Relevant stock must beat the irrelevant local asset
    assert ranked[0].asset_id == "pexels_shirt_01"
    # The irrelevant smart_library asset must NOT have a high semantic score
    assert irrelevant_local.semantic_score < 0.60


def test_quality_checker_sliding_window_diversity_and_consecutive_limits():
    """Validates that sliding window diversity rewards variety and catches >3 consecutive identical types."""
    checker = QualityChecker()

    # 1. Plan with 12 segments alternating video, photo, and graphic (healthy long video)
    good_segments = [
        AssemblySegment(
            segment_id=f"seg_{i}",
            start=i * 2.0,
            end=(i + 1) * 2.0,
            asset_id=f"asset_{i}",
            asset_type=["video", "photo", "graphic"][i % 3],
            asset_path=f"/path/to/asset_{i}.mp4",
            purpose=["hook", "explanation", "reveal"][i % 3],
        )
        for i in range(12)
    ]
    good_plan = AssemblyPlan(
        project_id="diverse_long_plan",
        segments=good_segments,
        total_duration=24.0,
    )
    good_score = checker.evaluate(good_plan)
    assert good_score.passed is True
    assert good_score.visual_diversity >= 0.50
    assert good_score.consecutive_treatment_violations == 0

    # 2. Plan with 6 consecutive identical video segments (violates max_consecutive=3)
    monotonous_segments = [
        AssemblySegment(
            segment_id=f"mono_{i}",
            start=i * 2.0,
            end=(i + 1) * 2.0,
            asset_id=f"mono_asset_{i}",
            asset_type="video",
            asset_path=f"/path/to/mono_{i}.mp4",
            purpose="explanation",
            is_callback=False,
        )
        for i in range(6)
    ]
    mono_plan = AssemblyPlan(
        project_id="monotonous_plan",
        segments=monotonous_segments,
        total_duration=12.0,
    )
    mono_score = checker.evaluate(mono_plan)
    assert mono_score.consecutive_treatment_violations > 0
    assert mono_score.passed is False
    assert any("consecutive_treatment_violations" in a for a in mono_score.alerts)
