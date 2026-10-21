"""Tests for Sprint 1 (v0.3) of the Mercadoria Editorial Pipeline.

Validates:
1. System instruction forbids abstract queries and enforces complete editorial schema.
2. GeminiDirectorProvider maps all editorial fields and strips prohibited terms.
3. LocalRuleDirectorProvider intelligently infers narrative functions, phases, overlays and concrete queries.
4. Absolute literal character fidelity is preserved between scenes and original script.
"""

import json
from unittest.mock import MagicMock, patch
import pytest

from app.services.director.prompt_builder import SYSTEM_INSTRUCTION, build_director_prompt
from app.services.director.scene_director import GeminiDirectorProvider, LocalRuleDirectorProvider
from app.services.director.schemas import NarrativeFunction, NarrativePhase, Scene, TextLevel
from app.services.editorial.script_manager import ScriptVersion


def test_prompt_builder_contains_prohibited_terms_and_editorial_directives():
    """Validates that SYSTEM_INSTRUCTION explicitly forbids abstract terms and specifies all editorial keys."""
    # Negative prompt / prohibited terms
    assert "PROIBIÇÃO DE BUSCAS ABSTRATAS" in SYSTEM_INSTRUCTION
    for term in ["economy", "market", "wealth", "value", "capitalism", "supply chain"]:
        assert term in SYSTEM_INSTRUCTION.lower()

    # Editorial keys
    assert "narrative_function" in SYSTEM_INSTRUCTION
    assert "narrative_phase" in SYSTEM_INSTRUCTION
    assert "entities" in SYSTEM_INSTRUCTION
    assert "humor" in SYSTEM_INSTRUCTION
    assert "text_overlay" in SYSTEM_INSTRUCTION
    assert "text_level" in SYSTEM_INSTRUCTION
    assert "intentional_callback" in SYSTEM_INSTRUCTION

    # Functions
    for fn in ["hook", "setup", "example", "explanation", "concept", "contrast", "joke", "reveal", "conclusion"]:
        assert fn in SYSTEM_INSTRUCTION

    # Phases
    for ph in ["aspiration", "commodity", "production", "labor", "reveal"]:
        assert ph in SYSTEM_INSTRUCTION


def test_gemini_provider_parses_full_editorial_json():
    """Validates that GeminiDirectorProvider parses all editorial fields and strips abstract query slips."""
    provider = GeminiDirectorProvider(api_key="mock_key", model_name="mock_model")

    script_text = (
        "Quer entender como a economia funciona de verdade? "
        "Começa com uma caneca de vinte reais. "
        "O petróleo caiu. "
        "Operários trabalharam na fábrica de costura."
    )
    script_version = ScriptVersion(
        script_id="test_gemini_editorial",
        version=1,
        version_tag="script_v001",
        sha256="mock_hash",
        raw_text=script_text,
        clean_narration=script_text,
        approved_at="2026-10-20T00:00:00Z",
    )

    mock_json_response = {
        "scenes": [
            {
                "scene_id": "scene_001",
                "narration": "Quer entender como a economia funciona de verdade?",
                "intent": "Fisgar atenção com contraste de riqueza",
                "narrative_function": "hook",
                "narrative_phase": "aspiration",
                "entities": ["economia", "riqueza"],
                "visual_type": "stock_video",
                "queries": ["dubai skyscrapers luxury city", "economy", "expensive sports car"],
                "preferred_motion": "lateral",
                "importance": 4,
                "text_overlay": "ECONOMIA REAL",
                "text_level": "title",
                "humor": False,
                "duration_hint": 3.0,
                "intentional_callback": None,
            },
            {
                "scene_id": "scene_002",
                "narration": "Começa com uma caneca de vinte reais.",
                "intent": "Apresentar produto e preço",
                "narrative_function": "example",
                "narrative_phase": "commodity",
                "entities": ["caneca", "café"],
                "visual_type": "stock_video",
                "queries": ["ceramic coffee mug steam", "mug retail price tag"],
                "preferred_motion": "zoom_in",
                "importance": 3,
                "text_overlay": "R$ 20,00",
                "text_level": "title",
                "humor": False,
                "duration_hint": 3.0,
                "intentional_callback": None,
            },
            {
                "scene_id": "scene_003",
                "narration": "O petróleo caiu.",
                "intent": "Interpretar metáfora de forma literal absurda",
                "narrative_function": "joke",
                "narrative_phase": "commodity",
                "entities": ["petróleo"],
                "visual_type": "stock_video",
                "queries": ["oil barrel falling on ground literal", "crude oil container dropped"],
                "preferred_motion": "static",
                "importance": 2,
                "text_overlay": None,
                "text_level": "caption",
                "humor": True,
                "duration_hint": 1.2,
                "intentional_callback": None,
            },
            {
                "scene_id": "scene_004",
                "narration": "Operários trabalharam na fábrica de costura.",
                "intent": "Revelar o trabalho humano vivo",
                "narrative_function": "reveal",
                "narrative_phase": "labor",
                "entities": ["operários", "fábrica", "costura"],
                "visual_type": "stock_video",
                "queries": ["garment factory sewing machine workers", "textile apparel manufacturing"],
                "preferred_motion": "lateral",
                "importance": 5,
                "text_overlay": "QUEM FEZ ISSO?",
                "text_level": "title",
                "humor": False,
                "duration_hint": 4.5,
                "intentional_callback": "scene_002",
            },
        ]
    }

    mock_client = MagicMock()
    mock_model_response = MagicMock()
    mock_model_response.text = json.dumps(mock_json_response)
    mock_client.models.generate_content.return_value = mock_model_response

    with patch("google.genai.Client", return_value=mock_client):
        plan = provider.generate_plan(script_version)

    assert plan.total_scenes == 4
    s1, s2, s3, s4 = plan.scenes

    # Scene 1 - Hook & Prohibited term removal
    assert s1.narrative_function == "hook"
    assert s1.narrative_phase == "aspiration"
    assert s1.text_overlay == "ECONOMIA REAL"
    assert s1.text_level == "title"
    assert s1.humor is False
    assert s1.entities == ["economia", "riqueza"]
    # The term "economy" was in mock queries and must have been filtered out!
    assert "economy" not in s1.queries
    assert "dubai skyscrapers luxury city" in s1.queries

    # Scene 2 - Example & Price overlay
    assert s2.narrative_function == "example"
    assert s2.text_overlay == "R$ 20,00"
    assert s2.text_level == "title"

    # Scene 3 - Joke & Humor
    assert s3.narrative_function == "joke"
    assert s3.humor is True
    assert s3.duration_hint == 1.2
    assert "oil barrel falling on ground literal" in s3.queries

    # Scene 4 - Reveal & Intentional Callback
    assert s4.narrative_function == "reveal"
    assert s4.narrative_phase == "labor"
    assert s4.importance == 5
    assert s4.intentional_callback == "scene_002"
    assert s4.text_overlay == "QUEM FEZ ISSO?"


def test_local_rule_director_infers_editorial_metadata():
    """Validates that LocalRuleDirectorProvider infers narrative functions, entities and concrete queries."""
    provider = LocalRuleDirectorProvider()

    script_text = (
        "Quer entender como a economia funciona?\n"
        "Uma camiseta custa R$ 79,90.\n"
        "O petróleo caiu de repente.\n"
        "Mas antes dela chegar à loja existiram costureira e fábrica de tecido.\n"
        "Quem fez as coisas?"
    )
    script_version = ScriptVersion(
        script_id="test_local_editorial",
        version=1,
        version_tag="script_v001",
        sha256="mock_hash_local",
        raw_text=script_text,
        clean_narration=script_text,
        approved_at="2026-10-20T00:00:00Z",
    )

    plan = provider.generate_plan(script_version)
    assert plan.total_scenes == 5

    s1 = plan.scenes[0]
    assert s1.narrative_function == "hook"
    assert s1.narrative_phase == "aspiration"

    s2 = plan.scenes[1]
    assert s2.narrative_function == "example"
    assert s2.text_overlay == "R$ 79,90"
    assert s2.text_level == "title"
    assert "camiseta" in s2.entities
    # Concrete query mapping
    assert any("t-shirt" in q for q in s2.queries)

    s3 = plan.scenes[2]
    assert s3.narrative_function == "joke"
    assert s3.humor is True
    assert s3.duration_hint <= 1.5
    assert any("oil barrel" in q for q in s3.queries)

    s4 = plan.scenes[3]
    assert s4.narrative_function in ("reveal", "explanation")
    assert s4.narrative_phase in ("labor", "production")

    s5 = plan.scenes[4]
    assert s5.narrative_function == "conclusion"

    # Verify no abstract prohibited queries exist
    prohibited = {"economy", "market", "wealth", "value", "capitalism"}
    for sc in plan.scenes:
        for q in sc.queries:
            assert q.lower() not in prohibited


def test_script_character_fidelity_preserved():
    """Validates that realign_narration_with_original preserves exact characters."""
    script_text = "Uma camiseta custa oitenta reais. O mercado não acorda de mau humor."
    script_version = ScriptVersion(
        script_id="test_fidelity",
        version=1,
        version_tag="script_v001",
        sha256="mock_hash_fid",
        raw_text=script_text,
        clean_narration=script_text,
        approved_at="2026-10-20T00:00:00Z",
    )

    provider = LocalRuleDirectorProvider()
    plan = provider.generate_plan(script_version)

    recomposed = " ".join(s.narration for s in plan.scenes)
    assert recomposed == script_text
