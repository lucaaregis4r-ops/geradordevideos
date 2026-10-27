"""Unit and integration tests for Sprint 4: Review Studio & Human Editorial Workflow."""

import json
from pathlib import Path
import tempfile
import pytest

from app.services.review.review_manager import ReviewManager
from app.services.director.schemas import ScenePlan, Scene, VisualBeat


class TestReviewManagerWorkflow:
    """Tests the 2-step editorial management backend."""

    @pytest.fixture
    def test_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            mgr = ReviewManager(storage_dir=tmp_path)
            yield tmp_path, mgr

    def test_direct_script_creates_scenes_manifest(self, test_env):
        tmp_path, mgr = test_env
        script_text = (
            "Quer entender como a economia funciona de verdade? "
            "Começa com uma caneca de vinte reais. "
            "O petróleo caiu."
        )
        res = mgr.direct_script(
            script_id="proj_test_01",
            script_text=script_text,
            title="Episódio Piloto",
            channel="default",
            brand_preset="explicador_cientifico",
        )

        assert res["project_id"] == "proj_test_01"
        assert res["total_scenes"] >= 1
        assert Path(res["plan_path"]).exists()

        plan = res["plan"]
        assert plan.brand_preset == "explicador_cientifico"
        assert plan.scenes[0].narration == "Quer entender como a economia funciona de verdade?"

    def test_update_scene_metadata_preserves_narration_integrity(self, test_env):
        tmp_path, mgr = test_env
        script_text = "Primeira frase literal do autor. Segunda frase literal do autor."
        mgr.direct_script("proj_test_02", script_text, brand_preset="economia_cotidiana")

        orig_data = mgr.get_project_data("proj_test_02")
        orig_narration = orig_data["plan"].scenes[0].narration

        # Update metadata: change queries, text overlay, and component
        updated_plan = mgr.update_scene_metadata(
            project_id="proj_test_02",
            scene_id="scene_001",
            queries=["custom tangible query one", "custom query two"],
            component_type="price_tag",
            text_overlay="R$ 19,90",
            text_level="title",
            intent="Intenção refinada pelo editor",
        )

        sc = updated_plan.scenes[0]
        # Sacred narration check: MUST NOT BE ALTERED
        assert sc.narration == orig_narration
        assert sc.queries == ["custom tangible query one", "custom query two"]
        assert getattr(sc, "component_type", None) == "price_tag"
        assert sc.text_overlay == "R$ 19,90"
        assert sc.text_level == "title"
        assert sc.intent == "Intenção refinada pelo editor"

    def test_update_beat_metadata(self, test_env):
        tmp_path, mgr = test_env
        # Create plan with beats
        folder = tmp_path / "projects" / "proj_beats"
        folder.mkdir(parents=True, exist_ok=True)
        plan = ScenePlan(
            script_id="proj_beats",
            script_version="v001",
            script_hash="h1",
            total_scenes=1,
            estimated_duration=5.0,
            scenes=[
                Scene(
                    scene_id="scene_001",
                    narration="Frase longa para teste de beats.",
                    intent="Intent",
                    queries=["initial query"],
                    visual_beats=[
                        VisualBeat(beat_id="beat_a", queries=["query a"]),
                        VisualBeat(beat_id="beat_b", queries=["query b"]),
                    ],
                )
            ],
            created_at="2026-10-21T00:00:00Z",
        )
        with (folder / "scenes.json").open("w", encoding="utf-8") as f:
            f.write(plan.to_json(indent=2))

        # Update beat_b metadata
        updated = mgr.update_beat_metadata(
            project_id="proj_beats",
            scene_id="scene_001",
            beat_id="beat_b",
            queries=["updated beat query"],
            component_type="split_screen",
            text_overlay="VS",
        )

        beat_b = updated.scenes[0].visual_beats[1]
        assert beat_b.queries == ["updated beat query"]
        assert beat_b.component_type == "split_screen"
        assert beat_b.text_overlay == "VS"

    def test_evaluate_project_quality_and_credits(self, test_env):
        tmp_path, mgr = test_env
        folder = tmp_path / "projects" / "proj_qa"
        folder.mkdir(parents=True, exist_ok=True)
        from PIL import Image
        media_path = folder / "fixture.jpg"
        Image.new("RGB", (1080, 1920), "blue").save(media_path)

        plan = ScenePlan(
            script_id="proj_qa",
            script_version="v001",
            script_hash="h1",
            total_scenes=1,
            estimated_duration=4.0,
            scenes=[
                Scene(
                    scene_id="scene_001",
                    narration="Frase de avaliação de qualidade.",
                    intent="Intent",
                    queries=["query valid"],
                    duration_hint=4.0,
                    selected_media={
                        "asset_id": "asset_100",
                        "local_path": str(media_path),
                        "media_type": "image",
                        "semantic_status": "reviewed",
                        "url": "http://example.com/video.mp4",
                        "author": "Diretor X",
                        "license": "Creative Commons",
                        "semantic_score": 0.85,
                    },
                )
            ],
            created_at="2026-10-21T00:00:00Z",
        )
        with (folder / "scenes.json").open("w", encoding="utf-8") as f:
            f.write(plan.to_json(indent=2))

        eval_res = mgr.evaluate_project_quality("proj_qa")
        assert eval_res["project_id"] == "proj_qa"
        assert "quality_score" in eval_res
        assert eval_res["passed"] is True
        assert Path(eval_res["storyboard_html_path"]).exists()
        assert Path(eval_res["storyboard_md_path"]).exists()
        assert Path(eval_res["credits_md_path"]).exists()
        assert Path(eval_res["manifest_json_path"]).exists()

    def test_list_projects_summary(self, test_env):
        tmp_path, mgr = test_env
        mgr.direct_script("p1", "Frase do projeto um.", title="Projeto 1")
        mgr.direct_script("p2", "Frase do projeto dois.", title="Projeto 2")

        summaries = mgr.list_projects_summary()
        ids = [s["project_id"] for s in summaries]
        assert "p1" in ids
        assert "p2" in ids
        assert any(s["title"] == "Projeto 1" for s in summaries)
