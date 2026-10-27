from pathlib import Path
from unittest.mock import Mock

import pytest

from app.services.director.scene_director import SceneDirector
from app.services.director.screenplay_director import build_screenplay_plan, is_factory_screenplay
from app.services.director.scene_validator import validate_scene_plan
from app.services.editorial.script_manager import ScriptManager


EXAMPLE = Path(__file__).resolve().parents[2] / 'docs' / 'exemplos' / 'roteiro_caneca_fabrica_v1.md'


def test_factory_example_preserves_narration_and_uses_no_director_api(tmp_path):
    provider = Mock()
    provider.generate_plan.side_effect = AssertionError('An explicit brief must not be sent to an LLM')
    manager = ScriptManager(tmp_path / 'scripts')
    plan = SceneDirector(provider=provider, script_manager=manager).direct_script(
        'caneca', EXAMPLE.read_text(), save_plan=False)
    script = manager.get_latest('caneca')
    assert plan.total_scenes == 12
    assert validate_scene_plan(plan, script.clean_narration) == (True, [])
    assert 150 <= len(script.clean_narration.split()) <= 190
    assert not provider.generate_plan.called
    assert plan.scenes[0].queries[0] == 'ceramic mug kitchen table'
    assert plan.scenes[2].text_overlay == 'R$ 29,90'
    assert plan.scenes[1].text_overlay is None
    assert plan.scenes[0].visual_beats[0].forbidden_elements == ['animation', 'illustration', 'AI generated']
    assert all(s.visual_type == 'stock_video' and len(s.queries) == 3 for s in plan.scenes)
    assert plan.scenes[-1].narration.endswith('quem fez?')


def test_simple_script_keeps_existing_provider(tmp_path):
    manager = ScriptManager(tmp_path)
    script = manager.save_script('simple', 'Uma caneca sobre a mesa.')
    assert not is_factory_screenplay(script.raw_text)
    assert build_screenplay_plan(script) is None


@pytest.mark.parametrize(('old', 'new', 'error'), [
    ('## CENA 02', '## CENA 03', 'numere as cenas'),
    ('TIPO: video', 'TIPO: holograma', 'TIPO deve ser'),
    ('BUSCAS:', 'PESQUISA:', 'DESCRIÇÃO e de três'),
    ('ceramic mug kitchen table', 'economy market wealth', 'sem termos abstratos'),
    ('QUEM FEZ?', 'QUEM FOI QUE FEZ ISSO AQUI?', 'até quatro palavras'),
])
def test_malformed_explicit_brief_is_rejected_before_provider(tmp_path, old, new, error):
    manager = ScriptManager(tmp_path)
    script = manager.save_script('bad', EXAMPLE.read_text().replace(old, new, 1))
    with pytest.raises(ValueError, match=error):
        build_screenplay_plan(script)


def test_still_photo_is_kept_as_a_photo(tmp_path):
    script = ScriptManager(tmp_path).save_script('photo', EXAMPLE.read_text().replace('TIPO: video','TIPO: imagem',1))
    first = build_screenplay_plan(script).scenes[0]
    assert first.visual_type == 'stock_image'
    assert first.visual_beats[0].preferred_media == 'image'


def test_explicit_exclusions_use_metadata_not_query(tmp_path):
    from app.services.media_ranker.media_searcher import MediaSearcher
    from app.services.media_ranker.schemas import MediaCandidate
    from app.services.director.schemas import Scene, VisualBeat
    candidates = [MediaCandidate(asset_id='real', description='Hands shaping pottery', query='animation',
                                 width=1080, height=1920, duration=8),
                  MediaCandidate(asset_id='fake', description='Pottery animation',
                                 width=1080, height=1920, duration=8)]
    builder = Mock(); builder.search_query.return_value = candidates; builder.search_attempts = []
    library = Mock(); library.search_library.return_value = []
    graphics = Mock(); graphics.is_graphic_scene.return_value = False
    ranker = Mock(); ranker.rank_candidates.side_effect = lambda **kw: kw['candidates']
    searcher = MediaSearcher(candidate_builder=builder, smart_library=library, graphics_engine=graphics,
        semantic_ranker=ranker, media_cache_dir=tmp_path, asset_catalog=Mock())
    scene = Scene('s', 'Uma pessoa molda uma caneca.', 'Mãos moldando barro', ['hands shaping pottery'])
    beat = VisualBeat('b', queries=['hands shaping pottery'], forbidden_elements=['animation'])
    result = searcher.search_for_beat(scene, beat)
    assert [c.asset_id for c in result] == ['real']
