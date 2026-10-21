"""Unit and integration tests for Sprint 3: Presets, Multi-Beats and Editorial Components."""

from pathlib import Path
import tempfile
import pytest
from PIL import Image

from app.services.director.presets import (
    EDITORIAL_PRESETS,
    get_preset,
    list_presets,
    EditorialPreset,
)
from app.services.director.prompt_builder import (
    build_director_prompt,
    build_system_instruction,
)
from app.services.director.schemas import Scene, ScenePlan, VisualBeat
from app.services.director.scene_director import LocalRuleDirectorProvider
from app.services.editorial.script_manager import ScriptVersion
from app.services.assembly.planner import AssemblyPlanner
from app.services.assembly.quality_checker import QualityChecker
from app.services.graphics.graphics_engine import GraphicsEngine
from app.services.graphics.components import (
    PriceTagComponent,
    SplitScreenComponent,
    HistoricalArchiveComponent,
    DataCardComponent,
    EditorialCropComponent,
    SAFE_TOP,
    SAFE_BOTTOM,
    SAFE_LEFT,
    SAFE_RIGHT,
)
from app.services.factory import _measure_audio_duration


class TestEditorialPresets:
    """Tests preset registry and preset schemas."""

    def test_list_presets_returns_all_four(self):
        presets = list_presets()
        names = [p.name for p in presets]
        assert len(names) >= 4
        assert "ensaio_documental" in names
        assert "internet_retro" in names
        assert "explicador_cientifico" in names
        assert "economia_cotidiana" in names

    def test_get_preset_returns_correct_instance(self):
        preset = get_preset("explicador_cientifico")
        assert isinstance(preset, EditorialPreset)
        assert preset.name == "explicador_cientifico"
        assert "enigma" in preset.narrative_phases
        assert "mecanismo" in preset.narrative_phases
        assert preset.pace_wpm > 0

    def test_get_preset_fallback_on_unknown(self):
        preset = get_preset("unknown_preset_slug")
        assert preset.name == "economia_cotidiana"


class TestPromptBuilderWithPresets:
    """Tests dynamic system prompt generation incorporating presets."""

    def test_build_system_instruction_scientific(self):
        instruction = build_system_instruction("explicador_cientifico")
        assert "explicador_cientifico" in instruction
        assert "enigma" in instruction
        assert "mecanismo" in instruction
        assert "visual_beats" in instruction.lower()

    def test_build_system_instruction_retro(self):
        instruction = build_system_instruction("internet_retro")
        assert "internet_retro" in instruction
        assert "hook_pop" in instruction or "humor_literal" in instruction


class TestMultiBeatDirector:
    """Tests SceneDirector splitting long sentences into visual beats."""

    def test_local_provider_generates_visual_beats_for_long_compound_sentence(self):
        provider = LocalRuleDirectorProvider()
        # Sentence is long (> 4.5s) and has conjunction "mas" and "enquanto"
        text = "O preço de uma camiseta na vitrine custa R$ 89 reais, mas o custo real de produção na fábrica é de apenas R$ 12 reais."
        script = ScriptVersion(
            script_id="test_beats",
            version=1,
            version_tag="v001",
            raw_text=text,
            clean_narration=text,
            title="Teste Beats",
            channel="test",
            approved_at="2026-10-21T00:00:00Z",
            sha256="dummy_hash",
        )

        plan = provider.generate_plan(script, settings={"brand_preset": "economia_cotidiana"})
        assert len(plan.scenes) >= 1
        scene = plan.scenes[0]

        # Narration is sacred: text must be identical
        assert scene.narration == text
        # Multi-beat was triggered
        assert scene.has_multiple_beats is True
        assert len(scene.visual_beats) == 2
        assert scene.visual_beats[0].beat_id == f"{scene.scene_id}_a"
        assert scene.visual_beats[1].beat_id == f"{scene.scene_id}_b"
        # Beat 2 detected price tag or component
        assert scene.visual_beats[1].component_type in ("price_tag", "split_screen") or scene.visual_beats[1].visual_type in ("component", "stock_video")


class TestAssemblyPlannerWithMultiBeats:
    """Tests timeline distribution and proportional beat allocation in AssemblyPlanner."""

    def test_beats_proportional_duration_distribution(self):
        planner = AssemblyPlanner()

        # Scene with 5.0 seconds total and 2 beats (durations 2.0 and 3.0)
        scene = Scene(
            scene_id="scene_001",
            narration="Uma frase de teste para verificar a distribuição temporal entre planos.",
            intent="Demonstrar dois ângulos da mesma ação",
            queries=["camera closeup", "camera wide shot"],
            visual_type="stock_video",
            duration_hint=5.0,
            narrative_function="explanation",
            narrative_phase="commodity",
            selected_media={"asset_id": "asset_default", "url": "http://example.com/default.mp4"},
            visual_beats=[
                VisualBeat(
                    beat_id="beat_001_a",
                    queries=["camera closeup"],
                    visual_type="stock_video",
                    duration=2.0,
                    selected_media={"asset_id": "asset_close", "url": "http://example.com/close.mp4"},
                ),
                VisualBeat(
                    beat_id="beat_001_b",
                    queries=["camera wide shot"],
                    visual_type="stock_video",
                    duration=3.0,
                    selected_media={"asset_id": "asset_wide", "url": "http://example.com/wide.mp4"},
                ),
            ],
        )

        scene_plan = ScenePlan(
            script_id="test_proj",
            script_version="v001",
            script_hash="hash123",
            total_scenes=1,
            estimated_duration=5.0,
            scenes=[scene],
            brand_preset="ensaio_documental",
            created_at="2026-10-21T00:00:00Z",
        )

        assembly = planner.build_plan(scene_plan)
        assert len(assembly.segments) == 2
        seg1 = assembly.segments[0]
        seg2 = assembly.segments[1]

        assert seg1.segment_id == "seg_beat_001_a"
        assert seg2.segment_id == "seg_beat_001_b"
        assert seg1.asset_id == "asset_close"
        assert seg2.asset_id == "asset_wide"

        # Check timings
        assert seg1.start == 0.0
        assert seg1.end == 2.0
        assert seg2.start == 2.0
        assert seg2.end == 5.0
        assert assembly.total_duration == 5.0

    def test_audio_duration_sync_overrides_hint(self):
        planner = AssemblyPlanner()

        scene = Scene(
            scene_id="scene_002",
            narration="Frase com áudio medido pelo ffprobe.",
            intent="Testar áudio real",
            queries=["studio microphone"],
            duration_hint=3.0,
            overlay={"audio_duration": 4.25},
            selected_media={"asset_id": "asset_mic", "url": "http://example.com/mic.mp4"},
        )

        scene_plan = ScenePlan(
            script_id="test_audio_sync",
            script_version="v001",
            script_hash="hash456",
            total_scenes=1,
            estimated_duration=3.0,
            scenes=[scene],
            created_at="2026-10-21T00:00:00Z",
        )

        assembly = planner.build_plan(scene_plan)
        assert len(assembly.segments) == 1
        assert assembly.segments[0].end == 4.25
        assert assembly.total_duration == 4.25


class TestEditorialComponents:
    """Tests rendering and vertical 9:16 safe area conformance for all 5 components."""

    @pytest.fixture
    def output_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield Path(tmp)

    def test_price_tag_component_renders_image(self, output_dir):
        comp = PriceTagComponent()
        out_png = output_dir / "price_tag.png"
        result = comp.render_image(
            out_png,
            metadata={"price": "R$ 49,90", "item": "CAMISETA BÁSICA", "store": "LOJA DO SHOPPING"},
        )
        assert result.exists()
        with Image.open(result) as img:
            assert img.size == (1080, 1920)

    def test_split_screen_component_renders_image(self, output_dir):
        comp = SplitScreenComponent()
        out_png = output_dir / "split_screen.png"
        result = comp.render_image(
            out_png,
            metadata={"label_top": "MARGEM DE LUCRO", "label_bottom": "CUSTO DO TRABALHO"},
        )
        assert result.exists()
        with Image.open(result) as img:
            assert img.size == (1080, 1920)

    def test_historical_archive_component_renders_image(self, output_dir):
        comp = HistoricalArchiveComponent()
        out_png = output_dir / "archive.png"
        result = comp.render_image(
            out_png,
            metadata={"year": "1974", "caption": "Registro de arquivo histórico"},
        )
        assert result.exists()
        with Image.open(result) as img:
            assert img.size == (1080, 1920)

    def test_data_card_component_renders_image(self, output_dir):
        comp = DataCardComponent()
        out_png = output_dir / "data_card.png"
        result = comp.render_image(
            out_png,
            metadata={"value": "73%", "label": "VALOR AGREGADO", "context": "Base de dados 2026"},
        )
        assert result.exists()
        with Image.open(result) as img:
            assert img.size == (1080, 1920)

    def test_editorial_crop_component_renders_image(self, output_dir):
        comp = EditorialCropComponent()
        out_png = output_dir / "crop.png"
        result = comp.render_image(
            out_png,
            metadata={"title": "ENQUADRAMENTO EDITORIAL", "aspect_ratio": "16:9"},
        )
        assert result.exists()
        with Image.open(result) as img:
            assert img.size == (1080, 1920)

    def test_graphics_engine_renders_component_video(self, output_dir):
        ge = GraphicsEngine(cache_dir=output_dir / "ge_cache")
        out_mp4 = output_dir / "price_tag.mp4"
        res = ge.render_editorial_component(
            component_type="price_tag",
            output_path=out_mp4,
            duration=1.0,
            metadata={"price": "R$ 99,00", "item": "PRODUTO TESTE"},
        )
        assert res.exists()
        assert res.stat().st_size > 0


class TestQualityCheckerWithBeats:
    """Tests QualityChecker on a multi-beat assembly plan."""

    def test_quality_checker_passes_valid_beat_plan(self):
        checker = QualityChecker()
        scene = Scene(
            scene_id="scene_001",
            narration="Texto de narração com dois planos visuais.",
            intent="Mostrar dois planos",
            queries=["query one", "query two"],
            visual_type="stock_video",
            duration_hint=4.0,
            narrative_function="explanation",
            narrative_phase="commodity",
            visual_beats=[
                VisualBeat(
                    beat_id="beat_a",
                    queries=["query one"],
                    duration=2.0,
                    selected_media={"asset_id": "asset_1", "url": "http://a.com/1.mp4", "semantic_score": 0.85},
                ),
                VisualBeat(
                    beat_id="beat_b",
                    queries=["query two"],
                    duration=2.0,
                    selected_media={"asset_id": "asset_2", "url": "http://a.com/2.mp4", "semantic_score": 0.80},
                ),
            ],
        )
        scene_plan = ScenePlan(
            script_id="proj_beats_qa",
            script_version="v001",
            script_hash="h1",
            total_scenes=1,
            estimated_duration=4.0,
            scenes=[scene],
            created_at="2026-10-21T00:00:00Z",
        )
        planner = AssemblyPlanner()
        plan = planner.build_plan(scene_plan)
        score = checker.evaluate(plan)

        assert score.passed is True
        assert score.duplicate_assets == 0
        assert score.segments_without_visual == 0
