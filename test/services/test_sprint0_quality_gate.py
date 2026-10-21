"""Unit tests for Sprint 0: Quality Gate Enforcement, Error Handling & Synthetic Detection.

Validates:
1. QualityScore records explicit alerts and counts synthetic assets.
2. QualityChecker fails plans containing synthetic placeholders by default.
3. MediaCandidate carries is_synthetic and error_detail flags.
4. CandidateBuilder marks generated placeholders with is_synthetic=True and low scores.
5. MediaSearcher retries next candidate if download fails on the first candidate.
6. ShortsFactory stops before rendering and returns rejected status when Quality Gate fails.
7. Baseline scripts (economy, science, sports) exist in test fixtures.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.services.assembly.quality_checker import QualityChecker
from app.services.assembly.schemas import AssemblyPlan, AssemblySegment, QualityScore
from app.services.director.scene_director import LocalRuleDirectorProvider
from app.services.director.schemas import Scene, ScenePlan
from app.services.factory import ShortsFactory
from app.services.media_ranker.candidate_builder import CandidateBuilder
from app.services.media_ranker.media_searcher import MediaSearcher
from app.services.media_ranker.schemas import MediaCandidate


def test_quality_score_alerts_and_serialization():
    """Validates alerts and synthetic_assets fields in QualityScore."""
    qs = QualityScore(
        asset_count=2,
        duplicate_assets=1,
        synthetic_assets=1,
        passed=False,
        alerts=["duplicate_assets=1 (max=0)", "synthetic_assets=1 (max=0)"],
    )
    data = qs.to_dict()
    assert data["synthetic_assets"] == 1
    assert data["passed"] is False
    assert len(data["alerts"]) == 2
    assert "duplicate_assets=1 (max=0)" in data["alerts"]

    restored = QualityScore.from_dict(data)
    assert restored.synthetic_assets == 1
    assert restored.passed is False
    assert restored.alerts == qs.alerts


def test_quality_checker_flags_synthetic_assets():
    """QualityChecker must reject plans with synthetic placeholder clips in production mode."""
    checker = QualityChecker()

    plan = AssemblyPlan(
        project_id="synthetic_test",
        segments=[
            AssemblySegment(
                segment_id="seg_0",
                start=0.0,
                end=3.0,
                asset_id="syn_abc123",  # Synthetic asset ID
                asset_type="video",
                asset_path="/cache/synthetic_abc.mp4",
                purpose="explanation",
            ),
            AssemblySegment(
                segment_id="seg_1",
                start=3.0,
                end=6.0,
                asset_id="real_asset",
                asset_type="photo",
                asset_path="/cache/real.jpg",
                purpose="hook",
            ),
        ],
        total_duration=6.0,
    )

    score = checker.evaluate(plan)
    assert score.passed is False
    assert score.synthetic_assets == 1
    assert any("synthetic_assets=1" in a for a in score.alerts)


def test_media_candidate_schema_is_synthetic():
    """Validates is_synthetic and error_detail in MediaCandidate."""
    c = MediaCandidate(
        provider="synthetic_photo",
        asset_id="syn_123",
        query="factory",
        is_synthetic=True,
        error_detail="API timeout",
    )
    d = c.to_dict()
    assert d["is_synthetic"] is True
    assert d["error_detail"] == "API timeout"

    restored = MediaCandidate.from_dict(d)
    assert restored.is_synthetic is True
    assert restored.error_detail == "API timeout"


def test_candidate_builder_marks_synthetic_and_low_score(tmp_path):
    """CandidateBuilder marks fallback clips as synthetic with honest low scores."""
    builder = CandidateBuilder(media_cache_dir=tmp_path / "cache")
    # Search with synthetic fallback explicitly enabled
    results = builder.search_query(
        query="unlikely_query_string_xyz_123",
        target_duration=3.0,
        enable_synthetic_fallback=True,
        visual_type="stock_video",
    )
    assert len(results) == 1
    candidate = results[0]
    assert candidate.is_synthetic is True
    assert candidate.provider == "synthetic_local"
    assert candidate.technical_score <= 0.20
    assert candidate.final_score <= 0.20


def test_media_searcher_retry_on_download_failure(tmp_path):
    """If top candidate fails to download, MediaSearcher must try the next candidate."""
    searcher = MediaSearcher(media_cache_dir=tmp_path / "cache")

    scene = Scene(
        scene_id="s1",
        narration="Teste de recuperação de download.",
        intent="test",
        queries=["query1"],
    )

    cand1 = MediaCandidate(
        provider="pexels",
        asset_id="cand_fail",
        query="query1",
        url="https://fail.com/video1.mp4",
        final_score=0.90,
    )
    cand2 = MediaCandidate(
        provider="pexels",
        asset_id="cand_success",
        query="query1",
        url="https://success.com/video2.mp4",
        final_score=0.85,
    )

    plan = ScenePlan(
        script_id="test_plan",
        script_version="v001",
        script_hash="h1",
        total_scenes=1,
        estimated_duration=4.0,
        scenes=[scene],
    )

    with patch.object(searcher, "search_for_scene", return_value=[cand1, cand2]):
        # Mock material.save_video: fail on cand1, succeed on cand2
        fake_local_file = tmp_path / "cache" / "downloaded_video2.mp4"
        fake_local_file.write_text("dummy video content")

        def mock_save_video(video_url, save_dir):
            if "fail" in video_url:
                raise RuntimeError("403 Forbidden: Invalid token")
            return str(fake_local_file)

        with patch("app.services.material.save_video", side_effect=mock_save_video):
            populated = searcher.populate_scene_plan(plan=plan, download_selected=True)

        # cand2 should have been downloaded and selected
        selected = populated.scenes[0].selected_media
        assert selected["asset_id"] == "cand_success"
        assert selected["local_path"] == str(fake_local_file)
        assert searcher.deduplicator.is_used("cand_success") is True
        # cand_fail must NOT be marked used
        assert searcher.deduplicator.is_used("cand_fail") is False


def test_shorts_factory_halts_on_failed_quality_gate(tmp_path):
    """ShortsFactory halts before rendering when Quality Gate fails."""
    factory = ShortsFactory(base_dir=tmp_path / "factory", allow_placeholders=False)
    factory.director.provider = LocalRuleDirectorProvider()

    # Create dummy failing quality score
    failing_qs = QualityScore(
        passed=False,
        duplicate_assets=2,
        alerts=["duplicate_assets=2 (max=0)"],
    )

    with patch.object(factory.quality_checker, "evaluate", return_value=failing_qs):
        with patch.object(factory.director, "direct_script") as mock_direct:
            dummy_scene = Scene(
                scene_id="s1",
                narration="Texto de teste.",
                intent="test",
                queries=["tshirt"],
            )
            mock_plan = ScenePlan(
                script_id="test_script",
                script_version="v001",
                script_hash="h1",
                total_scenes=1,
                estimated_duration=4.0,
                scenes=[dummy_scene],
            )
            mock_direct.return_value = mock_plan

            with patch("app.services.voice.tts"):
                with patch("app.services.video_project.VideoProject.render") as mock_render:
                    result = factory.produce_draft(
                        script_id="test_rejection",
                        script_text="Texto de teste.",
                        enforce_quality_gate=True,
                    )

                    # FFmpeg render MUST NOT have been called
                    mock_render.assert_not_called()

                    # Result status must indicate Quality Gate rejection
                    assert result["status"] == "rejected_by_quality_gate"
                    assert result["video_path"] is None
                    assert "Quality Gate failed" in result["error"]
                    assert result["quality_score"]["passed"] is False


def test_baseline_fixtures_exist():
    """Validates that the three baseline scripts are present and populated."""
    fixtures_dir = Path("test/fixtures/scripts")
    expected = [
        "01_economia_cotidiana.md",
        "02_ciencia_espaco.md",
        "03_esporte_tatica.md",
    ]
    for script_name in expected:
        path = fixtures_dir / script_name
        assert path.exists(), f"Missing baseline fixture: {path}"
        content = path.read_text(encoding="utf-8").strip()
        assert len(content) > 50, f"Baseline fixture {path} is suspiciously short"
