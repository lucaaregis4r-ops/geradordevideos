from pathlib import Path
from types import SimpleNamespace

import pytest
from app.services.assembly.readiness import can_render, readiness_report
from app.services.assembly.schemas import QualityScore
from app.services.branding.kit import BrandKit, load_kit, save_kit
from app.services.graphics.typography_engine import TypographyEngine


@pytest.mark.parametrize('alert', ['segments_without_visual=2 (max=0)', 'synthetic_assets=1 (max=0)',
    'duplicate_assets=1 (max=0)', 'invalid_timeline:s1', 'text_safe_area_errors=1 (max=0)',
    'low_resolution_count=1 (max=0)', 'creator_limit:someone=3 (max=2)'])
def test_preview_never_bypasses_structural_failures(alert):
    assert not can_render(QualityScore(alerts=[alert, 'pending_review:s1']), allow_preview=True)


def test_editorial_preview_is_explicit():
    score = QualityScore(alerts=['pending_review:s1'])
    assert not can_render(score)
    assert can_render(score, allow_preview=True)
    assert can_render(QualityScore(passed=True))


def test_missing_report_identifies_scene_and_queries():
    segment = SimpleNamespace(asset_id='missing_a', asset_path='', scene_ref='scene_010', segment_id='a')
    scene = SimpleNamespace(scene_id='scene_010', narration='Um pacote de café.', queries=['coffee bag shelf'])
    result = readiness_report(SimpleNamespace(segments=[segment]), SimpleNamespace(scenes=[scene]))
    assert result['covered_segments'] == 0
    assert result['pending'][0]['cena'] == 'scene_010'
    assert result['pending'][0]['buscas'] == ['coffee bag shelf']


def test_brand_snapshot_is_independent(tmp_path):
    current, snapshot = tmp_path/'current.json', tmp_path/'project.json'
    kit = BrandKit(accent='#FF0000', voice_rate=0.9)
    save_kit(kit, current); save_kit(kit, snapshot)
    save_kit(BrandKit(accent='#00FF00'), current)
    assert load_kit(snapshot) == kit
    assert load_kit(current).accent == '#00FF00'
    with pytest.raises(ValueError):
        BrandKit(voice_rate=3)


def test_palette_changes_pixels_without_moving_text():
    red = TypographyEngine(accent='#FF0000').render_overlay('TESTE')
    blue = TypographyEngine(accent='#0000FF').render_overlay('TESTE')
    assert red.getbbox() == blue.getbbox()
    assert red.tobytes() != blue.tobytes()
    x1,y1,x2,y2 = red.getbbox()
    assert x1 >= 60 and x2 <= 1020 and y1 >= 250 and y2 <= 1570


def test_all_explicit_search_alternatives_are_attempted(tmp_path):
    from unittest.mock import Mock
    from app.services.media_ranker.media_searcher import MediaSearcher
    from app.services.director.schemas import Scene
    builder = Mock(); builder.search_query.return_value = []; builder.search_attempts = []
    library = Mock(); library.search_library.return_value = []
    graphics = Mock(); graphics.is_graphic_scene.return_value = False
    ranker = Mock(); ranker.rank_candidates.return_value = []
    searcher = MediaSearcher(candidate_builder=builder, smart_library=library, graphics_engine=graphics,
        semantic_ranker=ranker, media_cache_dir=tmp_path, asset_catalog=Mock())
    queries = ['coffee bag shelf', 'worker stocking coffee package', 'hands arranging coffee bags']
    searcher.search_for_scene(Scene('s', 'Café na prateleira.', 'Pacotes de café', queries))
    assert [c.kwargs['query'] for c in builder.search_query.call_args_list] == queries


def test_gemini_catalog_and_preview_route(tmp_path, monkeypatch):
    from app.services.voice_studio.catalog import production_voices
    from app.services.voice_studio.voice_provider import EdgeVoiceProvider, legacy_voice
    from app.config import config
    options = production_voices()
    assert any(v['id'] == 'gemini:Kore-Firm' for v in options)
    assert len([v for v in options if v['provider'] == 'edge']) == 5
    monkeypatch.setitem(config.app, 'gemini_api_key', 'test-only')
    calls = []
    def fake_tts(**kwargs):
        calls.append(kwargs)
        Path(kwargs['voice_file']).write_bytes(b'test audio')
    monkeypatch.setattr(legacy_voice, 'tts', fake_tts)
    result = EdgeVoiceProvider().synthesize('Olá.', 'gemini:Kore-Firm', output_path=tmp_path/'voice.mp3')
    assert result['provider'] == 'gemini'
    assert calls[0]['voice_name'] == 'gemini:Kore-Firm'


def test_missing_gemini_key_has_actionable_error(monkeypatch):
    from app.config import config
    from app.services.voice_studio.catalog import validate_voice_configuration
    monkeypatch.setitem(config.app, 'gemini_api_key', '')
    with pytest.raises(ValueError, match='chave Gemini'):
        validate_voice_configuration('gemini:Kore-Firm')


def test_music_is_applied_with_real_ffmpeg(tmp_path):
    import subprocess
    from app.services.factory import ShortsFactory
    (tmp_path/'audio').mkdir()
    video, music = tmp_path/'source.mp4', tmp_path/'music.wav'
    subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','color=c=blue:s=160x284:r=25:d=2',
                    '-f','lavfi','-i','sine=frequency=500:duration=2','-c:v','libx264','-c:a','aac',
                    '-shortest',str(video)], check=True)
    subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','sine=frequency=200:duration=1',str(music)], check=True)
    output = ShortsFactory._apply_music(tmp_path,'test',str(video),SimpleNamespace(segments=[]),str(music),0.12)
    assert Path(output).is_file() and output != str(video)
    duration = float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration',
                                             '-of','default=nw=1:nk=1',output]))
    assert abs(duration-2) < 0.15
