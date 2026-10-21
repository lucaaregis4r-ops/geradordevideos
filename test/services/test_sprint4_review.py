"""Sprint 4 Automated Tests: Review Studio & Partial Scene Re-render.

Validates:
1. ReviewManager project listing and data inspection.
2. Swapping media for a single scene.
3. Verification that only the modified scene is rebuilt while all other scenes are 100% reused from cache.
"""

import json
from pathlib import Path
import subprocess
import pytest

from app.services.factory import ShortsFactory
from app.services.media_ranker.candidate_builder import _generate_synthetic_clip
from app.services.review import ReviewManager


def test_review_manager_inspection_and_swap(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.services.material.search_videos_pixabay", lambda *a, **kw: [])
    monkeypatch.setattr("app.services.material.search_videos_pexels", lambda *a, **kw: [])
    base_dir = tmp_path / "factory"
    factory = ShortsFactory(base_dir=base_dir)

    test_script = (
        "Você provavelmente aprendeu que força é massa vezes aceleração. "
        "Mas empurrar um carrinho cheio é outra história."
    )

    # 1. Produce initial draft with 2 scenes
    init_res = factory.produce_draft(
        script_id="review_test_demo",
        script_text=test_script,
        title="Review Demo",
        channel="fisica",
    )
    assert init_res["status"] == "succeeded"

    # 2. Inspect with ReviewManager
    manager = ReviewManager(storage_dir=base_dir)
    projects = manager.list_projects()
    assert "review_test_demo" in projects

    data = manager.get_project_data("review_test_demo")
    assert data["project_id"] == "review_test_demo"
    assert data["total_scenes"] >= 2
    assert data["latest_video"] is not None
    assert Path(data["latest_video"]).exists()

    # 3. Create alternative footage for scene_002
    alt_clip = base_dir / "media_cache" / "custom_alt_clip.mp4"
    _generate_synthetic_clip("nova midia cena 2", alt_clip, duration=5.0)
    assert alt_clip.exists()

    # 4. Swap media for scene_002 ONLY
    swap_res = manager.swap_scene_media(
        project_id="review_test_demo",
        scene_id="scene_002",
        new_footage_path=alt_clip,
        new_candidate_info={
            "provider": "custom_test",
            "asset_id": "alt_002",
            "technical_score": 0.98,
        },
    )

    assert swap_res["status"] == "succeeded"
    assert swap_res["swapped_scene"] == "scene_002"
    reused = swap_res["reused_stages"]
    built = swap_res["built_stages"]
    print("DEBUG REUSED:", reused)
    print("DEBUG BUILT:", built)

    # Verify that scene_001 was 100% reused from cache
    assert "scene_001:scene" in reused, "Scene 1 video must be reused from cache!"
    assert "scene_001:audio" in reused
    assert "scene_001:timing" in reused

    # Verify that scene_002 was rebuilt
    assert "scene_002:scene" in built, "Scene 2 video must be rebuilt!"
    assert "assembly" in built, "Final assembly must re-concat!"

    # Verify new export video
    new_video = Path(swap_res["video_path"])
    assert new_video.exists() and new_video.stat().st_size > 0

    # Probe resolution
    probe_cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json",
        str(new_video),
    ]
    probe_out = subprocess.check_output(probe_cmd).decode()
    v_stream = json.loads(probe_out)["streams"][0]
    assert v_stream["width"] == 1080 and v_stream["height"] == 1920
