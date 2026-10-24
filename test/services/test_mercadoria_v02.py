"""Tests for v0.2 of the Mercadoria Video Production Pipeline.

Validates:
1. Scene schema extensions (narrative fields, round-trip serialization).
2. AssemblyPlan and QualityScore data structures.
3. Graduated deduplication penalties, category diversity and callback bypass.
4. AssemblyPlanner timeline generation, narrative-aware duration & transitions.
5. QualityChecker pre-render gates and alert triggers.
6. ShortsFactory integration producing assembly_plan.json.
"""

import json
from pathlib import Path
import pytest

from app.services.assembly.planner import AssemblyPlanner
from app.services.assembly.quality_checker import QualityChecker
from app.services.assembly.schemas import AssemblyPlan, AssemblySegment, QualityScore
from app.services.director.scene_director import LocalRuleDirectorProvider
from app.services.director.schemas import (
    NarrativeFunction,
    NarrativePhase,
    Scene,
    ScenePlan,
    TextLevel,
    VisualType,
)
from app.services.factory import ShortsFactory
from app.services.media_ranker.deduplicator import MediaDeduplicator
from app.services.media_ranker.schemas import MediaCandidate


def test_scene_schema_extension():
    """Validates Scene serialization/deserialization with new editorial fields."""
    scene = Scene(
        scene_id="scene_001",
        narration="Uma camiseta custa oitenta reais.",
        intent="Apresentar o produto e preço no mercado",
        queries=["t-shirt price tag store", "retail store clothing"],
        visual_type="stock_video",
        preferred_motion="zoom_in",
        start=0.0,
        end=3.2,
        narrative_function=NarrativeFunction.HOOK.value,
        narrative_phase=NarrativePhase.COMMODITY.value,
        importance=5,
        text_overlay="R$ 80,00",
        text_level=TextLevel.TITLE.value,
        humor=False,
        intentional_callback=None,
        entities=["camiseta", "reais"],
        duration_hint=3.0,
    )

    data = scene.to_dict()
    assert data["narrative_function"] == "hook"
    assert data["narrative_phase"] == "commodity"
    assert data["importance"] == 5
    assert data["text_overlay"] == "R$ 80,00"
    assert data["text_level"] == "title"
    assert data["humor"] is False
    assert data["entities"] == ["camiseta", "reais"]

    restored = Scene.from_dict(data)
    assert restored.scene_id == scene.scene_id
    assert restored.narrative_function == "hook"
    assert restored.narrative_phase == "commodity"
    assert restored.importance == 5
    assert restored.text_overlay == "R$ 80,00"
    assert restored.text_level == "title"
    assert restored.entities == ["camiseta", "reais"]
    assert restored.duration_hint == 3.0


def test_scene_defaults_backward_compatibility():
    """Validates backward compatibility when legacy dicts without new fields are parsed."""
    legacy_data = {
        "scene_id": "legacy_001",
        "narration": "Texto legado.",
        "intent": "Intent",
        "queries": ["query 1"],
    }
    s = Scene.from_dict(legacy_data)
    assert s.narrative_function == "explanation"
    assert s.narrative_phase == "commodity"
    assert s.importance == 3
    assert s.text_overlay is None
    assert s.text_level == "caption"
    assert s.humor is False
    assert s.intentional_callback is None
    assert s.entities == []
    assert s.duration_hint == 3.0


def test_assembly_schemas_roundtrip():
    """Validates AssemblyPlan and QualityScore serialization and metrics."""
    seg1 = AssemblySegment(
        segment_id="seg_001",
        start=0.0,
        end=3.0,
        asset_id="asset_a",
        asset_type="video",
        asset_path="/path/to/a.mp4",
        purpose="hook",
        scene_ref="scene_001",
        is_callback=False,
    )
    seg2 = AssemblySegment(
        segment_id="seg_002",
        start=3.0,
        end=5.5,
        asset_id="asset_b",
        asset_type="photo",
        asset_path="/path/to/b.jpg",
        purpose="example",
        scene_ref="scene_002",
        is_callback=False,
    )
    seg3 = AssemblySegment(
        segment_id="seg_003",
        start=5.5,
        end=8.0,
        asset_id="asset_a",
        asset_type="video",
        asset_path="/path/to/a.mp4",
        purpose="conclusion",
        scene_ref="scene_003",
        is_callback=True,  # Deliberate callback should not count as involuntary duplicate
    )

    qs = QualityScore(
        asset_count=3,
        duplicate_assets=0,
        semantic_match_avg=0.85,
        visual_diversity=0.8,
        passed=True,
    )

    plan = AssemblyPlan(
        project_id="mercadoria_test",
        segments=[seg1, seg2, seg3],
        total_duration=8.0,
        quality_score=qs,
    )

    # Asset ID lists and counts
    assert plan.asset_ids == ["asset_a", "asset_b", "asset_a"]
    assert plan.unique_asset_count == 2
    # seg3 is a callback, so involuntary duplicate count must be 0
    assert plan.duplicate_count == 0

    json_str = plan.to_json()
    loaded = AssemblyPlan.from_json(json_str)
    assert loaded.project_id == "mercadoria_test"
    assert len(loaded.segments) == 3
    assert loaded.segments[2].is_callback is True
    assert loaded.quality_score is not None
    assert loaded.quality_score.passed is True


def test_deduplicator_graduated_penalties_and_callbacks():
    """Validates exact reuse penalty (0.1x), category penalty, blocklist, and callback bypass."""
    dedup = MediaDeduplicator()

    c1 = MediaCandidate(provider="test", asset_id="vid_100", query="factory", category="production", final_score=0.90)
    c2 = MediaCandidate(provider="test", asset_id="vid_200", query="factory", category="production", final_score=0.85)
    c3 = MediaCandidate(provider="test", asset_id="vid_300", query="office", category="office", final_score=0.80)

    # 1. Mark vid_100 used in scene_001 under category "production"
    dedup.mark_used(c1, scene_id="scene_001", visual_category="production")
    assert dedup.used_asset_count == 1
    assert dedup.category_distribution["production"] == 1

    # 2. Score new candidates for scene_002 with category "production"
    candidates = [
        MediaCandidate(provider="test", asset_id="vid_100", query="factory", category="production", final_score=0.90),  # exact reuse
        MediaCandidate(provider="test", asset_id="vid_200", query="factory", category="production", final_score=0.85),  # same category
        MediaCandidate(provider="test", asset_id="vid_300", query="office", category="office", final_score=0.80),   # fresh
    ]

    scored = dedup.score_candidates(candidates, visual_category="production")

    # vid_100 has exact reuse penalty: 0.90 * 0.1 = 0.09
    vid_100 = next(c for c in scored if c.asset_id == "vid_100")
    assert pytest.approx(vid_100.final_score, 0.01) == 0.09

    # vid_200 has category penalty: 0.85 * (1.0 - 0.1*1) = 0.765
    vid_200 = next(c for c in scored if c.asset_id == "vid_200")
    assert vid_200.final_score < 0.85

    # vid_300 is unaffected by "production" category
    vid_300 = next(c for c in scored if c.asset_id == "vid_300")
    assert pytest.approx(vid_300.final_score, 0.01) == 0.80

    # 3. Test Intentional Callback: should bypass penalty and promote vid_100
    callback_candidates = [
        MediaCandidate(provider="test", asset_id="vid_100", query="factory", category="production", final_score=0.50),
    ]
    callback_scored = dedup.score_candidates(
        callback_candidates,
        visual_category="production",
        intentional_callback="scene_001",
    )
    assert callback_scored[0].final_score >= 0.95

    # 4. Test Blocklist
    dedup.block_asset("vid_blocked")
    blocked_test = [
        MediaCandidate(provider="test", asset_id="vid_blocked", query="q", final_score=0.99),
        MediaCandidate(provider="test", asset_id="vid_ok", query="q", final_score=0.70),
    ]
    after_block = dedup.score_candidates(blocked_test)
    assert len(after_block) == 1
    assert after_block[0].asset_id == "vid_ok"


def test_assembly_planner_narrative_durations_and_categories():
    """Validates narrative-aware duration adjustment, humor capping, and transitions."""
    dedup = MediaDeduplicator()
    planner = AssemblyPlanner(deduplicator=dedup)

    scenes = [
        # Normal hook
        Scene(
            scene_id="s1",
            narration="Uma camiseta custa oitenta reais.",
            intent="hook",
            queries=["tshirt store"],
            narrative_function="hook",
            duration_hint=3.0,
            selected_media={"asset_id": "asset_1", "local_path": "/tmp/1.mp4", "type": "video"},
            entities=["camiseta", "reais"],
        ),
        # Humor joke scene - duration must be capped at <= 1.5s
        Scene(
            scene_id="s2",
            narration="O mercado ficou nervoso.",
            intent="joke",
            queries=["stressed trader funny"],
            narrative_function="joke",
            humor=True,
            duration_hint=4.0,  # hint is long, but humor should cap it
            selected_media={"asset_id": "asset_2", "local_path": "/tmp/2.mp4", "type": "video"},
        ),
        # Reveal concept scene - duration should be given space (>= 3.5s)
        Scene(
            scene_id="s3",
            narration="Mas oitenta reais não explicam o trabalho envolvido.",
            intent="reveal",
            queries=["factory workers"],
            narrative_function="reveal",
            duration_hint=2.0,  # hint is short, but reveal should expand it to at least 3.5s
            selected_media={"asset_id": "asset_3", "local_path": "/tmp/3.mp4", "type": "video"},
            entities=["trabalho"],
        ),
        # Deliberate callback to s1
        Scene(
            scene_id="s4",
            narration="Voltamos à camiseta.",
            intent="conclusion",
            queries=["tshirt store"],
            narrative_function="conclusion",
            intentional_callback="s1",
            duration_hint=3.0,
            selected_media={"asset_id": "asset_1", "local_path": "/tmp/1.mp4", "type": "video"},
        ),
    ]

    scene_plan = ScenePlan(
        script_id="test_script",
        script_version="v001",
        script_hash="h1",
        total_scenes=4,
        estimated_duration=12.0,
        scenes=scenes,
    )

    assembly_plan = planner.build_plan(scene_plan)
    assert len(assembly_plan.segments) == 4

    # Segment 1 (Hook)
    seg1 = assembly_plan.segments[0]
    assert seg1.start == 0.0
    assert seg1.end == 3.0

    # Segment 2 (Humor) - must be capped at 1.5s
    seg2 = assembly_plan.segments[1]
    assert seg2.start == 3.0
    assert pytest.approx(seg2.end - seg2.start, 0.01) == 1.5

    # Segment 3 (Reveal) - expanded to at least 3.5s
    seg3 = assembly_plan.segments[2]
    assert (seg3.end - seg3.start) >= 3.5
    assert seg3.transition == "cut"  # Hard cut for reveal

    # Segment 4 (Callback) - marked as callback
    seg4 = assembly_plan.segments[3]
    assert seg4.is_callback is True
    assert seg4.asset_id == "asset_1"


def test_quality_checker(tmp_path):
    from PIL import Image
    for i in range(5):
        Image.new("RGB", (720, 1280), (30 + i * 20, 100, 150)).save(tmp_path / f"asset_{i}.png")
    """Validates quality gating: passes clean plans and catches duplicates/missing visuals."""
    checker = QualityChecker()

    # 1. Clean plan with diverse asset types
    good_segments = [
        AssemblySegment(
            segment_id=f"seg_{i}",
            start=i * 2.0,
            end=(i + 1) * 2.0,
            asset_id=f"asset_{i}",
            asset_type="graphic" if i % 2 == 0 else "photo",
            asset_path=str(tmp_path / f"asset_{i}.png"),
            semantic_score=0.9, semantic_status="reviewed",
            purpose="explanation" if i % 2 == 0 else "concept",
        )
        for i in range(5)
    ]
    good_plan = AssemblyPlan(
        project_id="good_plan",
        segments=good_segments,
        total_duration=10.0,
    )

    good_score = checker.evaluate(good_plan)
    assert good_score.passed is True
    assert good_score.duplicate_assets == 0
    assert good_score.segments_without_visual == 0
    assert good_score.visual_diversity >= 0.3

    # 2. Bad plan with involuntary duplicate
    bad_segments = [
        AssemblySegment(
            segment_id="seg_0",
            start=0.0,
            end=2.0,
            asset_id="duplicate_asset",
            asset_type="video",
            asset_path="/tmp/dup.mp4",
        ),
        AssemblySegment(
            segment_id="seg_1",
            start=2.0,
            end=4.0,
            asset_id="duplicate_asset",  # in-voluntary duplicate
            asset_type="video",
            asset_path="/tmp/dup.mp4",
            is_callback=False,
        ),
    ]
    bad_plan = AssemblyPlan(
        project_id="bad_plan",
        segments=bad_segments,
        total_duration=4.0,
    )

    bad_score = checker.evaluate(bad_plan)
    assert bad_score.passed is False
    assert bad_score.duplicate_assets == 1

    # 3. Bad plan with missing visual
    missing_segments = [
        AssemblySegment(
            segment_id="seg_0",
            start=0.0,
            end=2.0,
            asset_id="missing_s1",
            asset_type="video",
            asset_path="",  # missing path
        )
    ]
    missing_plan = AssemblyPlan(
        project_id="missing_plan",
        segments=missing_segments,
        total_duration=2.0,
    )
    missing_score = checker.evaluate(missing_plan)
    assert missing_score.passed is False
    assert missing_score.segments_without_visual == 1


def test_shorts_factory_produces_assembly_plan(tmp_path):
    """Integration test: ShortsFactory produces assembly_plan.json during draft generation."""
    factory = ShortsFactory(base_dir=tmp_path / "factory")
    factory.director.provider = LocalRuleDirectorProvider()

    script_text = (
        "Uma camiseta custa oitenta reais.\n"
        "Mas o algodão veio do campo, passou pela fiação e pela fábrica de costura."
    )

    # Produce draft in offline/rule-based mode
    result = factory.produce_draft(
        script_id="test_mercadoria_draft",
        script_text=script_text,
        brand_style="editorial",
    )

    assert result["script_id"] == "test_mercadoria_draft"
    assert "assembly_plan_path" in result
    assert "quality_score" in result

    # Verify assembly_plan.json exists on disk and is valid
    plan_path = Path(result["assembly_plan_path"])
    assert plan_path.exists()

    with plan_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["project_id"] == "test_mercadoria_draft"
    assert len(data["segments"]) >= 1
    assert "quality_score" in data
