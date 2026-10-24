from unittest.mock import Mock

import pytest

from app.services.media_ranker.schemas import MediaCandidate
from app.services.media_ranker.technical_filter import rank_and_filter_candidates
from app.services.media_sources.base import SearchRequest, SearchResult
from app.services.media_sources.manager import MediaSourcesManager
from app.services.media_sources.mixkit import MixkitProvider, PageMetadata


def test_photos_do_not_remove_landscape_video_before_semantics():
    photos = [MediaCandidate(asset_id=str(i), media_type="image", width=1080, height=1920) for i in range(12)]
    video = MediaCandidate(asset_id="video", width=1920, height=1080, duration=10)
    result = rank_and_filter_candidates(photos + [video], top_k=10, prefer_video=True)
    assert video in result
    assert len(result) == 10


def test_search_cache_does_not_share_beat_mutations():
    provider = Mock()
    provider.name = "test"
    provider.is_available.return_value = True
    provider.search.return_value = [MediaCandidate(asset_id="one")]
    manager = MediaSourcesManager([provider])
    try:
        request = SearchRequest("sewing machine")
        first = manager._search_provider(provider, request)
        first.candidates[0].semantic_score = 1
        first.candidates[0].rights_status = "blocked_for_this_use"
        second = manager._search_provider(provider, request)
        assert second.candidates[0].semantic_score == 0
        assert second.candidates[0].rights_status == "rights_unknown"
    finally:
        manager._pool.shutdown()


def test_mixkit_discovery_is_bounded_and_ignores_preview_urls():
    provider = MixkitProvider()
    provider._page = Mock(return_value=''.join(
        f'<a class="item-grid-video-player__overlay-link" href="/free-stock-video/sewing-{i}/">Sewing machine {i}</a>'
        for i in range(20)))
    results = provider.search("sewing machine", limit=100)
    assert len(results) == 5
    assert all(c.url == c.source_page and c.width == 0 for c in results)
    assert provider._page.call_count == 1


def test_mixkit_restrictive_license_wins_over_structured_free_license():
    provider = MixkitProvider()
    provider._page = Mock(return_value='''<a data-license="videoRestricted"></a>
      <script type="application/ld+json">{"@type":"VideoObject", "license":"https://mixkit.co/license/#videoFree", "contentUrl":"https://assets.mixkit.co/preview.mp4"}</script>''')
    candidate = MediaCandidate(source_page="https://mixkit.co/free-stock-video/sewing-1/")
    with pytest.raises(ValueError, match="restricted_or_unconfirmed"):
        provider.resolve_candidate(candidate)
    assert candidate.rights_status == "blocked_for_this_use"


def test_mixkit_resolves_only_explicit_free_download():
    provider = MixkitProvider()
    provider._page = Mock(side_effect=['''<a data-license="videoFree"></a>
      <button data-download--button-modal-url-value="/free-stock-video/download/1/"></button>
      <script type="application/ld+json">{"@type":"VideoObject", "name":"Hands sewing fabric", "duration":"PT1M2.5S", "description":"created by Camera Person that you can", "contentUrl":"https://assets.mixkit.co/preview.mp4"}</script>''',
      '<a href="https://assets.mixkit.co/videos/1/download.mp4">Download</a>'])
    candidate = provider.resolve_candidate(MediaCandidate(source_page="https://mixkit.co/free-stock-video/sewing-1/"))
    assert candidate.url.endswith("download.mp4")
    assert candidate.duration == 62.5
    assert candidate.creator_name == "Camera Person"
    assert candidate.rights_status == "reviewed_allowed"


def test_mixkit_does_not_invent_high_resolution_urls():
    provider = MixkitProvider()
    provider._page = Mock(return_value='''<a data-license="videoFree"></a>
      <script type="application/ld+json">{"@type":"VideoObject", "contentUrl":"https://assets.mixkit.co/preview-720.mp4"}</script>''')
    with pytest.raises(ValueError, match="missing_download_link"):
        provider.resolve_candidate(MediaCandidate(source_page="https://mixkit.co/free-stock-video/sewing-1/"))


def test_video_search_includes_landscape_even_with_portrait_results(tmp_path):
    from app.services.media_ranker.candidate_builder import CandidateBuilder
    manager = Mock()
    manager.last_attempts = []
    manager.search.return_value = SearchResult([MediaCandidate(asset_id="portrait")])
    manager.search_photos.return_value = []
    builder = CandidateBuilder(tmp_path, manager)
    builder.search_query("sewing machine", visual_type="archive")
    requests = [c.args[0] for c in manager.search.call_args_list]
    assert [r.orientations for r in requests] == [("portrait",), ("landscape",)]
    assert all(r.include_archives for r in requests)


def test_local_photo_stays_a_photo(tmp_path):
    from PIL import Image
    from app.services.media_ranker.candidate_builder import CandidateBuilder
    Image.new("RGB", (1080, 1920), "red").save(tmp_path / "sewing.jpg")
    result = CandidateBuilder(tmp_path, Mock()).search_local_library("sewing machine")
    assert len(result) == 1
    assert result[0].media_type == "image"
    assert result[0].local_path.endswith("sewing.jpg")
    assert result[0].semantic_status == "unverified"
    assert not list(tmp_path.glob("**/*.mp4"))


def test_mixkit_parses_current_download_options_and_modal():
    page = PageMetadata('<input data-download--video-options-target="downloadOption" value="/free-stock-video/download/1/?type=2160p">')
    assert page.modals == ["/free-stock-video/download/1/?type=2160p"]
    modal = PageMetadata('<div data-download--modal-url-value="https://assets.mixkit.co/videos/1/1-2160.mp4"></div>')
    assert modal.downloads == ["https://assets.mixkit.co/videos/1/1-2160.mp4"]


def test_native_fit_preserves_edges_under_overlay(tmp_path):
    import subprocess
    from PIL import Image, ImageDraw
    from app.services.graphics.typography_engine import composite_overlay_to_clip
    source = Image.new("RGB", (320, 180), "blue")
    draw = ImageDraw.Draw(source)
    draw.rectangle((0, 0, 70, 179), fill="red")
    draw.rectangle((250, 0, 319, 179), fill="lime")
    source.save(tmp_path / "source.png")
    Image.new("RGBA", (180, 320)).save(tmp_path / "overlay.png")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", str(tmp_path / "source.png"),
                    "-t", "1", "-pix_fmt", "yuv420p", str(tmp_path / "source.mp4")], check=True)
    composite_overlay_to_clip(tmp_path / "source.mp4", tmp_path / "overlay.png", tmp_path / "out.mp4",
                              width=180, height=320, crop_mode="fit", source_in=0.2, duration=0.3)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(tmp_path / "out.mp4"), "-frames:v", "1", str(tmp_path / "result.png")], check=True)
    duration = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(tmp_path / "out.mp4")]))
    assert 0.29 <= duration <= 0.35  # A single-frame PNG must not truncate the video.
    result = Image.open(tmp_path / "result.png")
    assert result.getpixel((10, 160))[0] > 200
    assert result.getpixel((170, 160))[1] > 200


def test_mix_is_duration_weighted_and_does_not_count_photos_as_video():
    from app.services.assembly.media_mix import summarize_media_mix
    # Build via the existing planner to retain the real schema contract.
    from app.services.assembly.planner import AssemblyPlanner
    from app.services.director.schemas import Scene, ScenePlan, VisualBeat
    scene = Scene("s", "Texto.", "", [], overlay={"audio_duration": 10}, visual_beats=[
        VisualBeat("v", duration=2, selected_media={"asset_id":"v", "local_path":"v.mp4", "media_type":"video"}),
        VisualBeat("p", duration=8, selected_media={"asset_id":"p", "local_path":"p.jpg", "media_type":"image"})])
    result = summarize_media_mix(AssemblyPlanner().build_plan(ScenePlan("p", "1", "hash", 1, 10, [scene])))
    assert result["video_ratio"] == 0.2
    assert result["below_target"]


def test_stock_video_sorts_content_before_provider_limit(monkeypatch):
    from types import SimpleNamespace
    from app.services.media_sources.pixabay_videos import PixabayVideoProvider
    from app.services import material
    def item(id, description):
        return SimpleNamespace(url=f"https://example.org/{id}.mp4", duration=10,
            source_info={"asset_id":id, "description":description, "rendition":{"width":1920,"height":1080}})
    monkeypatch.setattr(material, "search_videos_pixabay", lambda **kw: [
        item("network", "network server rack"), item("clothes", "clothing shop clothes")])
    result = PixabayVideoProvider().search("clothing rack", limit=1)
    assert result[0].provider_asset_id == "clothes"
    assert result[0].semantic_score == 0
    assert result[0].semantic_status == "unverified"


def test_scene_swap_requires_review_without_starting_tts(tmp_path, monkeypatch):
    from PIL import Image
    from app.services.review.review_manager import ReviewManager
    from app.services.director.schemas import Scene, ScenePlan
    from app.services.factory import ShortsFactory
    manager = ReviewManager(storage_dir=tmp_path)
    folder = manager.projects_dir / "swap"
    folder.mkdir()
    plan = ScenePlan("swap", "1", "hash", 1, 4, [Scene("s", "Narração intacta.", "", [])])
    (folder / "scenes.json").write_text(plan.to_json())
    photo = tmp_path / "photo.jpg"
    Image.new("RGB", (1920, 1080), "blue").save(photo)
    render = Mock(side_effect=AssertionError("A media swap must not start synthesis/render"))
    monkeypatch.setattr(ShortsFactory, "render_existing_draft", render)
    result = manager.swap_scene_media("swap", "s", photo, {
        "asset_id":"photo", "media_type":"image", "semantic_status":"reviewed", "semantic_score":1})
    assert result["status"] == "pending_review"
    assert result["selected_media"]["crop_mode"] == "fit"
    assert result["selected_media"]["semantic_status"] == "unverified"
    assert not render.called
    assert not (folder / "audio").exists()
