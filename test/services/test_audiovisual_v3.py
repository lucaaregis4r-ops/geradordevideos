"""Offline regressions for the audiovisual plan; no provider calls or credentials."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from app.services.director.schemas import Scene, ScenePlan, VisualBeat
from app.services.assembly.planner import AssemblyPlanner
from app.services.assembly.quality_checker import QualityChecker
from app.services.media_ranker.schemas import MediaCandidate
from app.services.media_ranker.media_searcher import MediaSearcher
from app.services.media_ranker.semantic_ranker import SemanticRanker


def plan_for(scene):
    return ScenePlan("v3", "1", "hash", 1, 8, [scene])


def test_beats_keep_audio_and_do_not_reuse_scene_asset():
    scene = Scene("scene", "Texto intacto.", "costura", ["sewing machine"], humor=True,
                  overlay={"audio_duration": 4.0}, visual_beats=[
                      VisualBeat("a", duration=1), VisualBeat("b", duration=2), VisualBeat("c", duration=1)],
                  selected_media={"asset_id": "wrong", "local_path": "wrong.mp4"})
    result = AssemblyPlanner().build_plan(plan_for(scene))
    assert result.total_duration == 4.0
    assert [s.asset_type for s in result.segments] == ["video"] * 3
    assert all(s.asset_path == "" for s in result.segments)
    assert [s.end - s.start for s in result.segments] == [1, 2, 1]
    assert scene.narration == "Texto intacto."


def test_query_is_not_semantic_evidence():
    candidate = MediaCandidate(query="sewing machine fabric", semantic_score=0.99)
    score = SemanticRanker().evaluate_semantic_fit(candidate, "sewing machine fabric", "sewing machine fabric")
    assert score == 0
    assert candidate.semantic_status == "unverified"


def test_each_beat_searches_downloads_and_validates(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.media_ranker.asset_catalog._measure_media", lambda p: (1080, 1920, 8.0))
    builder = Mock()
    builder.search_query.side_effect = lambda query, **kw: [MediaCandidate(asset_id=query, query=query, url=f"https://example.org/{query}.mp4", duration=8)]
    library = Mock(); library.search_library.return_value = []
    graphics = Mock(); graphics.is_graphic_scene.return_value = False
    searcher = MediaSearcher(candidate_builder=builder, smart_library=library,
                             graphics_engine=graphics, media_cache_dir=tmp_path, asset_catalog=Mock())
    def download(c):
        p = tmp_path / f"{c.asset_id}.mp4"; p.write_bytes(b"fixture"); return str(p)
    def rank(**kwargs):
        for candidate in kwargs["candidates"]:
            candidate.semantic_score = 0.9
            candidate.semantic_status = "metadata_only"
        return kwargs["candidates"]
    searcher.semantic_ranker.rank_candidates = Mock(side_effect=rank)
    searcher._download_candidate_asset = Mock(side_effect=download)
    searcher.visual_evaluator = Mock()
    searcher.visual_evaluator.evaluate_media.return_value = SimpleNamespace(is_valid=True, perceptual_hash="", quality_score=1)
    scene = Scene("scene", "Intacta.", "", ["wrong"], visual_beats=[VisualBeat(str(i), queries=[q]) for i,q in enumerate(["needle", "cloth", "hands"])])
    searcher.populate_scene_plan(plan_for(scene))
    assert [call.kwargs["query"] for call in builder.search_query.call_args_list] == ["needle", "cloth", "hands"]
    assert searcher._download_candidate_asset.call_count == 3
    assert searcher.visual_evaluator.evaluate_media.call_count == 3
    assert all(Path(b.selected_media["local_path"]).exists() for b in scene.visual_beats)


def test_no_results_stays_pending(tmp_path):
    builder = Mock(); builder.search_query.return_value = []
    library = Mock(); library.search_library.return_value = []
    graphics = Mock(); graphics.is_graphic_scene.return_value = False
    searcher = MediaSearcher(candidate_builder=builder, smart_library=library, graphics_engine=graphics, media_cache_dir=tmp_path, asset_catalog=Mock())
    scene = Scene("s", "Texto.", "", ["shirt tag"], visual_beats=[VisualBeat("b", queries=["shirt tag"])])
    searcher.populate_scene_plan(plan_for(scene))
    assert scene.selected_media is None
    assert scene.visual_beats[0].status == "pending_media"
    assert not list(tmp_path.glob("*.mp4"))


def test_gate_includes_zero_semantics_and_missing_files():
    scene = Scene("s", "Texto.", "", [], selected_media={"asset_id":"x", "local_path":"/missing.mp4"})
    plan = AssemblyPlanner().build_plan(plan_for(scene))
    score = QualityChecker().evaluate(plan)
    assert not score.passed
    assert score.segments_without_visual == 1
    assert "pending_review:seg_s" in score.alerts


def test_single_beat_also_controls_selection():
    scene = Scene("s", "Texto.", "", [], visual_beats=[VisualBeat("b", selected_media={"asset_id":"photo", "local_path":"p.jpg", "media_type":"image"})])
    segment = AssemblyPlanner().build_plan(plan_for(scene)).segments[0]
    assert segment.asset_id == "photo"
    assert segment.asset_type == "photo"


def test_provider_diagnostics_are_distinct():
    import requests
    from app.services.media_sources.manager import MediaSourcesManager
    from app.services.media_sources.base import SearchRequest, ProviderCapabilities
    class Provider:
        capabilities = ProviderCapabilities(("video",))
        name = "fixture"
        available = True
        def is_available(self): return self.available
        def search(self, *a, **kw): return []
    p = Provider(); manager = MediaSourcesManager([p])
    request = SearchRequest("sewing machine")
    p.available = False
    assert manager._search_provider(p, request).status == "missing_credentials"
    p.available = True
    p.search = Mock(side_effect=requests.Timeout())
    assert manager._search_provider(p, request).status == "timeout"
    response = requests.Response(); response.status_code = 429
    p.search = Mock(side_effect=requests.HTTPError(response=response))
    assert manager._search_provider(p, request).status == "rate_limited"
    p.search = Mock(return_value=[])
    manager = MediaSourcesManager([p])
    assert manager._search_provider(p, request).status == "empty_results"


def test_commons_video_derivative_and_provenance(monkeypatch):
    from app.services.media_sources.wikimedia_commons import WikimediaCommonsProvider
    response = Mock()
    response.json.return_value = {"query":{"pages":{"42":{"videoinfo":[{
        "mime":"video/webm", "url":"https://example.org/original.webm", "width":1920,"height":1080,
        "descriptionurl":"https://example.org/File:42", "derivatives":[{"src":"https://example.org/720.webm", "type":"video/webm", "width":1280,"height":720}],
        "extmetadata":{"Artist":{"value":"Test creator"}, "LicenseShortName":{"value":"CC-BY"}, "ImageDescription":{"value":"Hands sewing cloth"}}
    }]}}}}
    monkeypatch.setattr("app.services.media_sources.wikimedia_commons.requests.get", Mock(return_value=response))
    c = WikimediaCommonsProvider().search("sewing", media_type="video")[0]
    assert c.media_type == "video" and c.width == 1280
    assert c.url.endswith("720.webm") and c.creator_name == "Test creator"
    assert c.license_id == "CC-BY" and c.description == "Hands sewing cloth"


def test_archive_missing_derivative_is_explicit(monkeypatch):
    from app.services.media_sources.internet_archive import InternetArchiveProvider
    response = Mock(); response.json.return_value = {"files":[{"name":"metadata.xml"}]}
    monkeypatch.setattr("app.services.media_sources.internet_archive.requests.get", Mock(return_value=response))
    with pytest.raises(ValueError, match="no_playable_derivative"):
        InternetArchiveProvider().resolve_asset("fixture")


def test_intervals_invalidate_only_video_stage():
    from app.services.video_project import stage_graph
    import copy
    spec = {"settings":{"width":1080,"height":1920,"fps":30}, "toolchain":{}, "scenes":[
        {"id":"one","narration":"Texto.","audio":"a.wav","footage":"a.mp4","duration":2,"source_in":0,"source_out":2},
        {"id":"two","narration":"Outra.","audio":"b.wav","footage":"b.mp4","duration":2,"source_in":0,"source_out":2}], "bgm":None}
    before = {s.key:s.fingerprint for s in stage_graph(spec)}
    spec["scenes"][0].update(source_in=1, source_out=3)
    after = {s.key:s.fingerprint for s in stage_graph(spec)}
    changed = {key for key in before if before[key] != after[key]}
    assert "one:scene" in changed
    assert "one:audio" not in changed
    assert not any(key.startswith("two:") for key in changed)


def test_literal_validator_rejects_small_word_or_punctuation_change():
    from app.services.director.scene_validator import validate_scene_plan
    scene = Scene("s", "Uma camiseta custa oitenta reais!", "etiqueta", ["shirt tag"])
    valid, _ = validate_scene_plan(plan_for(scene), "Uma camiseta custa oitenta reais.")
    assert not valid


def test_native_factory_preserves_multibeat_audio_and_rechecks_review(tmp_path):
    """Actual FFmpeg export: four spoken seconds must never become eight."""
    import json
    import subprocess
    from PIL import Image, ImageDraw
    from app.services.factory import ShortsFactory
    factory = ShortsFactory(base_dir=tmp_path)
    folder = factory.projects_dir / "native_v3"
    folder.mkdir()
    audio = folder / "voice.mp3"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=4:sample_rate=48000", str(audio)], check=True)
    beats = []
    for i, color in enumerate(((190, 80, 30), (40, 130, 190))):
        path = folder / f"frame_{i}.png"
        image = Image.new("RGB", (1080,1920), color)
        ImageDraw.Draw(image).rectangle((180, 400, 800, 1200), fill=(245,245,245))
        image.save(path)
        beats.append(VisualBeat(f"b{i}", duration=2, selected_media={"asset_id":f"image_{i}", "local_path":str(path),
                    "media_type":"image", "semantic_score":1, "semantic_status":"reviewed"}))
    scene = Scene("s", "Narração intacta.", "Test fixture", [], humor=True,
                  overlay={"audio_file":str(audio), "audio_duration":4}, visual_beats=beats)
    plan = plan_for(scene); plan.script_id = "native_v3"
    (folder / "scenes.json").write_text(plan.to_json())
    (folder / "assembly_plan.json").write_text(AssemblyPlanner().build_plan(plan).to_json())
    result = factory.render_existing_draft("native_v3")
    assert result["status"] == "succeeded"
    assert result["publishable"] is True
    audit = json.loads((folder / "render_audit.json").read_text())
    assert abs(audit["duration"] - 4) < 0.15
    # Stale saved approval must not permit exporting a newly missing beat.
    plan.scenes[0].visual_beats[1].selected_media = None
    (folder / "scenes.json").write_text(plan.to_json())
    blocked = factory.render_existing_draft("native_v3")
    assert blocked["status"] == "rejected_by_quality_gate"
    assert blocked["video_path"] is None


def test_candidate_builder_records_empty_provider_rounds(tmp_path):
    from app.services.media_ranker.candidate_builder import CandidateBuilder
    from app.services.media_sources.manager import MediaSourcesManager
    builder = CandidateBuilder(media_cache_dir=tmp_path, sources_manager=MediaSourcesManager(providers=[]))
    assert builder.search_query("shirt price tag") == []
    assert builder.search_attempts == []


def test_gate_enforces_creator_limit_on_imported_plan():
    scene = Scene("s", "Texto.", "", [], visual_beats=[
        VisualBeat(str(i), selected_media={"asset_id": str(i), "local_path": "missing.jpg"})
        for i in range(3)
    ])
    plan = AssemblyPlanner().build_plan(plan_for(scene))
    for segment in plan.segments:
        segment.provenance = {"creator_name": "Same Creator"}
    assert any(a.startswith("creator_limit:") for a in QualityChecker().evaluate(plan).alerts)
    plan.segments[-1].is_callback = True
    assert not any(a.startswith("creator_limit:") for a in QualityChecker().evaluate(plan).alerts)
