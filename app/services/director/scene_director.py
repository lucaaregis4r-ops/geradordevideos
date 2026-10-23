"""Scene Director for Fábrica de Shorts.

Main coordinator that transforms a locked human script into an executable scenes.json manifest.
Provides interchangeable LLM adapters (Gemini, OpenAI, Local Fallback) via DirectorProvider.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Optional

from app.config import config
from app.services.editorial.script_manager import ScriptManager, ScriptVersion
from .presets import get_preset
from .prompt_builder import SYSTEM_INSTRUCTION, build_director_prompt, build_system_instruction
from .schemas import Scene, ScenePlan, VisualBeat, VisualType
from .scene_validator import realign_narration_with_original, validate_scene_plan
from .visual_intent import estimate_duration_seconds, infer_visual_type


import logging

logger = logging.getLogger(__name__)


class DirectorProvider(ABC):
    """Abstract interface for Scene Director LLM providers."""

    @abstractmethod
    def generate_plan(
        self, script: ScriptVersion, settings: Optional[dict[str, Any]] = None
    ) -> ScenePlan:
        pass


class LocalRuleDirectorProvider(DirectorProvider):
    """Deterministic, rule-based director provider.

    Does not require an external API connection. Splits by punctuation/clauses and generates
    search queries using NLP heuristics. Ideal for regression tests and offline mode.
    """

    def generate_plan(
        self, script: ScriptVersion, settings: Optional[dict[str, Any]] = None
    ) -> ScenePlan:
        clean_text = script.clean_narration.strip()
        brand_preset_name = settings.get("brand_preset", "editorial") if settings else "editorial"
        preset = get_preset(brand_preset_name)

        # Split text into meaningful sentences
        raw_sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+|\n+", clean_text)
            if s.strip()
        ]
        if not raw_sentences:
            raw_sentences = [clean_text]

        # Group very short consecutive sentences into coherent editorial units (3.0s to 5.5s)
        merged_sentences = []
        curr_chunk = ""
        for s in raw_sentences:
            if not curr_chunk:
                curr_chunk = s
            elif estimate_duration_seconds(curr_chunk) + estimate_duration_seconds(s) <= 5.5:
                curr_chunk += " " + s
            else:
                merged_sentences.append(curr_chunk)
                curr_chunk = s
        if curr_chunk:
            merged_sentences.append(curr_chunk)
        raw_sentences = merged_sentences

        scenes: list[Scene] = []
        accumulated_time = 0.0
        total_count = len(raw_sentences)
        phases = preset.narrative_phases

        for idx, sentence in enumerate(raw_sentences):
            scene_id = f"scene_{idx + 1:03d}"
            dur = estimate_duration_seconds(sentence)
            v_type = infer_visual_type(sentence)
            lower_s = sentence.lower()

            # Map position to preset narrative phase
            phase_idx = min(len(phases) - 1, int((idx / max(1, total_count)) * len(phases)))
            n_phase = phases[phase_idx]

            # Infer narrative function and humor
            is_joke = any(k in lower_s for k in ["nervoso", "petróleo", "caiu", "ridícula", "piada"])
            if idx == 0:
                n_func = "hook"
            elif idx == total_count - 1:
                n_func = "conclusion"
            elif is_joke:
                n_func = "joke"
            elif any(k in lower_s for k in ["r$", "custa", "reais", "preço", "valor"]):
                n_func = "example"
            elif any(k in lower_s for k in ["fábrica", "máquina", "algodão", "produção"]):
                n_func = "explanation"
            elif any(k in lower_s for k in ["trabalho", "costureira", "operário", "trabalhador"]):
                n_func = "reveal"
            else:
                n_func = "explanation"

            # Extract price or keywords for text overlay
            price_match = re.search(r"R\$\s*\d+([.,]\d+)?", sentence)
            if price_match:
                t_overlay = price_match.group(0)
                t_level = "title"
            elif is_joke:
                t_overlay = None
                t_level = "caption"
            elif n_func in ("hook", "conclusion"):
                t_overlay = sentence[:25].upper()
                t_level = "title"
            else:
                t_overlay = None
                t_level = "caption"

            # Extract concrete entities
            concrete_candidates = ["camiseta", "caneca", "carro", "celular", "algodão", "fábrica", "preço", "trabalho", "dinheiro", "café", "loja", "máquina", "petróleo"]
            entities = [c for c in concrete_candidates if c in lower_s]
            if not entities:
                extracted_words = [w.lower() for w in re.findall(r"\b[a-zA-ZÀ-ÿ]{4,}\b", sentence)]
                entities = extracted_words[:2] if extracted_words else ["objeto"]

            # Generate concrete queries avoiding abstract terms ("economy", "market", "wealth", "value")
            prohibited_terms = {"economy", "market", "wealth", "value", "capitalism", "supply", "chain"}
            entity_main = entities[0] if entities else "product"
            
            # Map portuguese entity to english concrete visual
            en_map = {
                "camiseta": "t-shirt price tag store",
                "caneca": "ceramic coffee mug table",
                "carro": "luxury sports car city",
                "celular": "modern smartphone retail store",
                "algodão": "cotton field harvesting",
                "fábrica": "garment factory industrial sewing",
                "preço": "price tag in supermarket",
                "trabalho": "factory workers assembling products",
                "dinheiro": "counting cash money bills",
                "café": "hot coffee pouring cup",
                "loja": "clothing retail store interior",
                "máquina": "industrial textile weaving machine",
                "petróleo": "oil barrel falling on ground literal",
            }
            primary_query = en_map.get(entity_main, f"{entity_main} retail closeup")
            
            queries = [
                primary_query,
                f"{entity_main} product display",
                f"{entity_main} closeup visual",
            ]
            queries = [q for q in queries if not any(p in q.lower() for p in prohibited_terms)]
            if not queries:
                queries = ["retail store product display"]

            # Multi-beat planning: if scene duration is >= 4.5s and has multiple clauses, split into visual beats
            visual_beats: list[VisualBeat] = []
            if dur >= 4.5 and ("," in sentence or " e " in lower_s or " mas " in lower_s or " enquanto " in lower_s):
                beat_a = VisualBeat(
                    beat_id=f"{scene_id}_a",
                    queries=[queries[0]],
                    visual_type=v_type.value,
                    duration=round(dur * 0.5, 2),
                    text_overlay=t_overlay,
                    text_level=t_level,
                    intent=f"Plano 1: {queries[0]}",
                )

                # Detect if beat 2 should be an editorial component
                comp_type = None
                if price_match:
                    comp_type = "price_tag"
                elif any(k in lower_s for k in ["enquanto", "ao contrário", "versus", "vs", "diferente"]):
                    comp_type = "split_screen"
                elif any(k in lower_s for k in ["passado", "história", "antigamente", "século", "década"]):
                    comp_type = "historical_archive"
                elif any(k in lower_s for k in ["%", "estatística", "dados", "gráfico", "números"]):
                    comp_type = "data_card"

                beat_b_type = "component" if comp_type else v_type.value
                beat_b_queries = [queries[1]] if len(queries) > 1 else [queries[0]]
                beat_b = VisualBeat(
                    beat_id=f"{scene_id}_b",
                    queries=beat_b_queries,
                    visual_type=beat_b_type,
                    component_type=comp_type,
                    duration=round(dur * 0.5, 2),
                    text_overlay=None,
                    text_level="caption",
                    intent=f"Plano 2: {comp_type or beat_b_queries[0]}",
                )
                visual_beats = [beat_a, beat_b]

            scene = Scene(
                scene_id=scene_id,
                narration=sentence,
                intent=f"Apresentar '{sentence[:35]}...'" if len(sentence) > 35 else f"Apresentar '{sentence}'",
                queries=queries,
                visual_type=v_type.value,
                preferred_motion="lateral",
                start=round(accumulated_time, 2),
                end=round(accumulated_time + dur, 2),
                confidence=0.85,
                narrative_function=n_func,
                narrative_phase=n_phase,
                importance=4 if n_func in ("hook", "conclusion", "reveal") else 3,
                text_overlay=t_overlay,
                text_level=t_level,
                humor=is_joke,
                intentional_callback=None,
                entities=entities,
                duration_hint=1.2 if is_joke else (4.0 if n_func == "reveal" else dur),
                visual_beats=visual_beats,
            )
            scenes.append(scene)
            accumulated_time += dur

        plan = ScenePlan(
            script_id=script.script_id,
            script_version=script.version_tag,
            script_hash=script.sha256,
            total_scenes=len(scenes),
            estimated_duration=round(accumulated_time, 2),
            scenes=scenes,
            brand_preset=brand_preset_name,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        return plan


class GeminiDirectorProvider(DirectorProvider):
    """Google Gemini LLM provider for Scene Director."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        self.api_key = api_key or config.app.get("gemini_api_key", "")
        self.model_name = model_name or config.app.get("gemini_model_name", "gemini-3.5-flash")

    def generate_plan(
        self, script: ScriptVersion, settings: Optional[dict[str, Any]] = None
    ) -> ScenePlan:
        from google import genai
        from google.genai import types

        brand_style = settings.get("brand_preset", "editorial") if settings else "editorial"
        user_prompt = build_director_prompt(
            clean_script=script.clean_narration,
            channel=script.channel,
            brand_style=brand_style,
        )

        sys_instruction = build_system_instruction(brand_style)
        full_prompt = f"{sys_instruction}\n\n{user_prompt}"

        # Request JSON generation with automatic model fallback on temporary 503 high demand
        candidate_models = [self.model_name] + [
            m for m in ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-flash-lite-latest", "gemini-3.8-flash"]
            if m != self.model_name
        ]

        client = genai.Client(api_key=self.api_key)
        response = None
        last_error = None

        for model in candidate_models:
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=full_prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.3,
                    ),
                )
                if response and response.text:
                    break
            except Exception as exc:
                last_error = exc
                continue

        if not response or not response.text:
            logger.warning(
                "All Gemini candidate models failed (%s). Falling back to LocalRuleDirectorProvider.",
                last_error,
            )
            return LocalRuleDirectorProvider().generate_plan(script, settings)

        response_text = response.text.strip()
        # Parse JSON
        parsed = json.loads(response_text)
        raw_scenes = parsed.get("scenes", [])
        if not raw_scenes and isinstance(parsed, list):
            raw_scenes = parsed

        # Enforce exact character alignment with approved human text
        realigned = realign_narration_with_original(raw_scenes, script.clean_narration)

        # Build Scene objects and compute timestamps
        scenes: list[Scene] = []
        accumulated_time = 0.0

        prohibited_terms = {"economy", "market", "wealth", "value", "capitalism", "supply chain"}

        for idx, sc in enumerate(realigned):
            scene_id = sc.get("scene_id") or f"scene_{idx + 1:03d}"
            dur = estimate_duration_seconds(sc["narration"])
            dur_hint = float(sc.get("duration_hint", dur))

            # Filter prohibited abstract terms if the LLM slipped
            raw_queries = sc.get("queries", [sc["narration"][:20]])
            if isinstance(raw_queries, str):
                raw_queries = [raw_queries]
            cleaned_queries = [
                q.strip() for q in raw_queries
                if q.strip() and not any(p in q.lower() for p in prohibited_terms)
            ]
            if not cleaned_queries:
                cleaned_queries = raw_queries

            # Normalize entities list
            entities_val = sc.get("entities", [])
            if isinstance(entities_val, str):
                entities_val = [e.strip() for e in entities_val.split(",") if e.strip()]

            # Parse visual_beats if provided
            visual_beats_raw = sc.get("visual_beats", [])
            visual_beats: list[VisualBeat] = []
            if isinstance(visual_beats_raw, list):
                for b_idx, b in enumerate(visual_beats_raw):
                    if isinstance(b, dict):
                        b_id = b.get("beat_id", f"{scene_id}_{chr(97 + b_idx)}")
                        b_queries = b.get("queries", [sc["narration"][:20]])
                        if isinstance(b_queries, str):
                            b_queries = [b_queries]
                        visual_beats.append(
                            VisualBeat(
                                beat_id=b_id,
                                queries=b_queries,
                                visual_type=b.get("visual_type", "stock_video"),
                                component_type=b.get("component_type"),
                                duration=float(b.get("duration", dur / max(1, len(visual_beats_raw)))),
                                text_overlay=b.get("text_overlay"),
                                text_level=b.get("text_level", "caption"),
                                intent=b.get("intent", ""),
                            )
                        )

            scene = Scene(
                scene_id=scene_id,
                narration=sc["narration"],
                intent=sc.get("intent", ""),
                queries=cleaned_queries,
                visual_type=sc.get("visual_type", "stock_video"),
                preferred_motion=sc.get("preferred_motion", "lateral"),
                start=round(accumulated_time, 2),
                end=round(accumulated_time + dur, 2),
                confidence=float(sc.get("confidence", 0.9)),
                narrative_function=sc.get("narrative_function", "explanation"),
                narrative_phase=sc.get("narrative_phase", "commodity"),
                importance=int(sc.get("importance", 3)),
                text_overlay=sc.get("text_overlay"),
                text_level=sc.get("text_level", "caption"),
                humor=bool(sc.get("humor", False)),
                intentional_callback=sc.get("intentional_callback"),
                entities=entities_val,
                duration_hint=dur_hint,
                visual_beats=visual_beats,
            )
            scenes.append(scene)
            accumulated_time += dur

        plan = ScenePlan(
            script_id=script.script_id,
            script_version=script.version_tag,
            script_hash=script.sha256,
            total_scenes=len(scenes),
            estimated_duration=round(accumulated_time, 2),
            scenes=scenes,
            brand_preset=brand_style,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # Validate fidelity
        valid, errors = validate_scene_plan(plan, script.clean_narration)
        if not valid:
            raise ValueError(f"Scene plan validation failed: {'; '.join(errors)}")

        return plan


class SceneDirector:
    """High-level Facade for directing scripts into scene plans."""

    def __init__(
        self,
        provider: Optional[DirectorProvider] = None,
        script_manager: Optional[ScriptManager] = None,
    ):
        self.script_manager = script_manager or ScriptManager()
        if provider:
            self.provider = provider
        else:
            # Pick provider based on config
            gemini_key = config.app.get("gemini_api_key", "")
            if gemini_key:
                self.provider = GeminiDirectorProvider(api_key=gemini_key)
            else:
                self.provider = LocalRuleDirectorProvider()

    def direct_script(
        self,
        script_id: str,
        script_text: str,
        *,
        title: str = "",
        channel: str = "default",
        brand_preset: str = "editorial",
        save_plan: bool = True,
        output_dir: Optional[str | Path] = None,
    ) -> ScenePlan:
        # 1. Save and lock script version (Human Script Mode)
        script_version = self.script_manager.save_script(
            script_id=script_id,
            raw_text=script_text,
            title=title,
            channel=channel,
        )

        # 2. Invoke provider
        settings = {"brand_preset": brand_preset}
        plan = self.provider.generate_plan(script_version, settings)
        plan.title = title

        # 3. Save scenes.json
        if save_plan:
            out_folder = Path(output_dir) if output_dir else Path(f"storage/projects/{script_id}")
            out_folder.mkdir(parents=True, exist_ok=True)
            plan_file = out_folder / "scenes.json"
            with plan_file.open("w", encoding="utf-8") as f:
                f.write(plan.to_json(indent=2))

        return plan
