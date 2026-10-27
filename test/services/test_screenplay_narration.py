"""Narration must survive screenplay parsing and an altered LLM response."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.services.editorial.directives import strip_stage_directions
from app.services.editorial.script_manager import ScriptManager
from app.services.director.scene_director import GeminiDirectorProvider, LocalRuleDirectorProvider
from app.services.director.scene_validator import validate_scene_plan


SCREENPLAY = '''## MERCADORIA

**[0–3s]**
**IMAGEM:** Uma caneca. Fundo limpo. Quase documental.

**NARRAÇÃO:**
Isto é uma caneca.

**TEXTO NA TELA:**
UMA CANECA.

---

**[3–7s]**
**IMAGEM:** Pessoa tomando café.
Ritmo muito rápido.

**NARRAÇÃO:** Uma caneca serve para colocar café.

Café serve, entre outras coisas, para tornar uma reunião tolerável.

**CORTE SECO.**
**TEXTO GRANDE:**
MERCADORIA.

---

**[35–39s]**
**IMAGEM:** Close dramático na etiqueta.
R$ 29,90.

**NARRAÇÃO:**
Curiosamente…

nada disso aparece na etiqueta.

Na etiqueta aparece:

vinte e nove e noventa.
'''
EXPECTED = ('Isto é uma caneca. Uma caneca serve para colocar café. '
            'Café serve, entre outras coisas, para tornar uma reunião tolerável. '
            'Curiosamente… nada disso aparece na etiqueta. Na etiqueta aparece: vinte e nove e noventa.')


def normalized(text):
    return ' '.join(text.split())


def test_screenplay_excludes_complete_visual_and_overlay_blocks(tmp_path):
    script = ScriptManager(tmp_path).save_script('screenplay', SCREENPLAY)
    assert normalized(script.clean_narration) == EXPECTED
    assert strip_stage_directions(script.clean_narration) == script.clean_narration
    plan = LocalRuleDirectorProvider().generate_plan(script)
    assert validate_scene_plan(plan, script.clean_narration) == (True, [])
    assert normalized(' '.join(s.narration for s in plan.scenes)) == EXPECTED


@pytest.mark.parametrize('altered', ['Isto é uma xícara.', 'Uma caneca serve para colocar café.'])
def test_altered_llm_plan_uses_original_text_in_local_fallback(tmp_path, monkeypatch, altered):
    from google import genai
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(text=json.dumps({'scenes': [{
        'scene_id':'scene_001', 'narration':altered, 'intent':'Uma caneca na mesa',
        'queries':['ceramic coffee mug table'],
    }]}))
    monkeypatch.setattr(genai, 'Client', lambda **kwargs: client)
    script = ScriptManager(tmp_path).save_script('screenplay', SCREENPLAY)
    plan = GeminiDirectorProvider(api_key='offline-fixture').generate_plan(script)
    assert validate_scene_plan(plan, script.clean_narration) == (True, [])
    assert normalized(' '.join(s.narration for s in plan.scenes)) == EXPECTED
    prompt = client.models.generate_content.call_args.kwargs['contents']
    assert 'IMAGEM:' in prompt and 'exclusivamente do ROTEIRO APROVADO' in prompt


def test_visual_notes_change_version_without_changing_narration_hash(tmp_path):
    manager = ScriptManager(tmp_path)
    first = manager.save_script('screenplay', SCREENPLAY)
    second = manager.save_script('screenplay', SCREENPLAY.replace('Fundo limpo.', 'Fundo azul.'))
    assert second.version == first.version + 1
    assert second.sha256 == first.sha256
    assert second.clean_narration == first.clean_narration
    assert manager.save_script('screenplay', second.raw_text).version == second.version


def test_unlabelled_scene_after_timestamp_preserves_its_narration():
    raw = '**NARRAÇÃO:** Primeira frase.\n\n### [0:07 — 0:18]\nSegunda frase literal.'
    assert normalized(strip_stage_directions(raw)) == 'Primeira frase. Segunda frase literal.'
