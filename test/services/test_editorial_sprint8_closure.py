"""Sprint 8 Automated Tests: Pipeline Closure, Canonical 5 Acts, Humor Cards & Artifact Sync.

Validates:
1. Canonical 5 dramatic acts in NarrativePhase and PHASE_MULTIPLIERS.
2. Humor Engine & Meme break card generation (Section 11) with <= 1.5s duration and hard cut.
3. Task Runner editorial artifact synchronization into task storage (Section 22/23).
4. End-to-end integration and stability.
"""

from pathlib import Path
import subprocess
import pytest

from app.models.schema import VideoParams
from app.services.audio.mastering import PHASE_MULTIPLIERS
from app.services.director.schemas import NarrativePhase
from app.services.media_ranker.candidate_builder import CandidateBuilder
from app.services.task import _run_editorial_pipeline
import app.services.state as sm
import app.utils.utils as utils


def test_canonical_five_acts_and_phase_multipliers():
    """Validates the canonical 5 dramatic acts from the report and audio ducking multipliers."""
    # 1. Canonical enum values
    assert NarrativePhase.PROMESSA.value == "promessa"
    assert NarrativePhase.OBJETO.value == "objeto"
    assert NarrativePhase.BASTIDORES.value == "bastidores"
    assert NarrativePhase.REVELACAO.value == "revelacao"
    assert NarrativePhase.FECHAMENTO.value == "fechamento"

    # 2. Multipliers mapped
    assert PHASE_MULTIPLIERS["promessa"] == 1.00
    assert PHASE_MULTIPLIERS["objeto"] == 0.85
    assert PHASE_MULTIPLIERS["bastidores"] == 0.65
    assert PHASE_MULTIPLIERS["revelacao"] == 0.30
    assert PHASE_MULTIPLIERS["fechamento"] == 0.10

    # 3. Aliases mapped
    assert PHASE_MULTIPLIERS["aspiration"] == 1.00
    assert PHASE_MULTIPLIERS["commodity"] == 0.85
    assert PHASE_MULTIPLIERS["production"] == 0.65
    assert PHASE_MULTIPLIERS["labor"] == 0.30
    assert PHASE_MULTIPLIERS["reveal"] == 0.30
    assert PHASE_MULTIPLIERS["conclusion"] == 0.10


def test_humor_engine_meme_card_generation(tmp_path: Path):
    """Validates that joke/humor queries generate fast, high-contrast meme clips (Section 11)."""
    builder = CandidateBuilder(media_cache_dir=tmp_path / "cache")

    # Search with meme visual type and comedic literal query
    candidates = builder.search_query(
        query="oil barrel falling literal",
        target_duration=1.2,
        enable_synthetic_fallback=True,
        visual_type="meme",
    )

    assert len(candidates) >= 1
    top = candidates[0]
    assert top.provider == "synthetic_meme"
    assert top.duration <= 1.5
    assert top.duration >= 0.8
    assert top.width == 1080
    assert top.height == 1920
    assert Path(top.local_path).exists()
    assert Path(top.local_path).stat().st_size > 1000


def test_task_runner_editorial_artifact_synchronization(tmp_path: Path, monkeypatch):
    """Validates that _run_editorial_pipeline copies storyboards and plan to task storage."""
    # Mock network media calls
    monkeypatch.setattr("app.services.material.search_videos_pixabay", lambda *a, **kw: [])
    monkeypatch.setattr("app.services.material.search_videos_pexels", lambda *a, **kw: [])

    # Mock custom task directory
    task_id = "sprint8_test_task_sync"
    custom_task_dir = tmp_path / "tasks" / task_id
    monkeypatch.setattr(utils, "task_dir", lambda tid: str(custom_task_dir))

    params = VideoParams(
        video_subject="Ocultamento do Trabalho",
        video_script="Uma camiseta custa oitenta reais. Mas o valor vem do trabalho humano.",
        video_aspect="9:16",
        pipeline_mode="editorial",
    )

    result = _run_editorial_pipeline(task_id, params)

    assert result.get("status") == "succeeded" or result.get("video_path") is not None
    assert custom_task_dir.exists()

    # Check that artifacts were copied to task directory
    html_artifact = custom_task_dir / "storyboard.html"
    md_artifact = custom_task_dir / "storyboard.md"
    plan_artifact = custom_task_dir / "assembly_plan.json"

    assert html_artifact.exists(), "storyboard.html must be copied to task directory"
    assert md_artifact.exists(), "storyboard.md must be copied to task directory"
    assert plan_artifact.exists(), "assembly_plan.json must be copied to task directory"

    from app.models import const
    task_state = sm.state.get_task(task_id)
    assert task_state.get("state") == const.TASK_STATE_COMPLETE
    assert task_state.get("storyboard_html") is not None
    assert task_state.get("storyboard_md") is not None
