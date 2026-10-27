"""Read an explicit Fábrica V1 brief without asking an LLM to rewrite it."""
from __future__ import annotations

from datetime import datetime, timezone
import re

from app.services.editorial.directives import strip_stage_directions
from app.services.editorial.script_manager import ScriptVersion
from .presets import get_preset
from .schemas import Scene, ScenePlan, VisualBeat
from .scene_validator import validate_scene_plan
from .visual_intent import estimate_duration_seconds

_HEADER = re.compile(r"^# ROTEIRO F[ÁA]BRICA V1$", re.IGNORECASE)
_SCENES = re.compile(r"^## CENA (\d+)\s*$", re.MULTILINE | re.IGNORECASE)
_BLOCK = re.compile(r"^(IMAGEM|NARRAÇÃO|TEXTO):\s*(.*)$", re.IGNORECASE)
_OPTIONS = re.compile(r"^(TIPO|DESCRIÇÃO|BUSCAS|EVITAR):\s*(.*)$", re.IGNORECASE)
_ABSTRACT = re.compile(r"\b(?:economy|market|wealth|value|capitalism|supply chain)\b", re.IGNORECASE)


def is_factory_screenplay(text: str) -> bool:
    lines = text.strip().splitlines()
    return bool(lines and _HEADER.fullmatch(lines[0].strip()))


def build_screenplay_plan(script: ScriptVersion, brand_preset: str = "editorial") -> ScenePlan | None:
    if not is_factory_screenplay(script.raw_text):
        return None
    parts = _SCENES.split(script.raw_text)
    if len(parts) == 1:
        raise ValueError("Roteiro Fábrica V1: inclua blocos '## CENA 01', '## CENA 02' e assim por diante.")
    preset = get_preset(brand_preset)
    scenes: list[Scene] = []
    current_time = 0.0
    count = (len(parts) - 1) // 2
    for index in range(count):
        number, body = parts[1 + index * 2:3 + index * 2]
        label = f"Cena {index + 1:02d}"
        if int(number) != index + 1:
            raise ValueError(f"{label}: numere as cenas em ordem, sem repetir ou pular números.")
        sections: dict[str, list[str]] = {}
        section = None
        order = []
        for line in body.splitlines():
            match = _BLOCK.match(line.strip())
            if match:
                section = match[1].upper()
                if section in sections:
                    raise ValueError(f"{label}: o bloco {section} está repetido.")
                order.append(section)
                sections[section] = [match[2]]
            elif section and line.strip() != "---":
                sections[section].append(line)
        if order != ["IMAGEM", "NARRAÇÃO", "TEXTO"]:
            raise ValueError(f"{label}: use os blocos IMAGEM:, NARRAÇÃO: e TEXTO:, nessa ordem.")
        options = {}
        for line in sections["IMAGEM"]:
            match = _OPTIONS.match(line.strip())
            if match:
                field = match[1].upper()
                if field in options:
                    raise ValueError(f"{label}: o campo {field} está repetido.")
                options[field] = match[2].strip()
        media_type = options.get("TIPO", "video").casefold()
        if media_type not in {"video", "vídeo", "imagem"}:
            raise ValueError(f"{label}: TIPO deve ser video ou imagem.")
        description = options.get("DESCRIÇÃO", "")
        queries = list(dict.fromkeys(q.strip() for q in options.get("BUSCAS", "").split("|") if q.strip()))
        if not description or not 3 <= len(queries) <= 5:
            raise ValueError(f"{label}: inclua DESCRIÇÃO e de três a cinco BUSCAS diferentes separadas por |.")
        if any(_ABSTRACT.search(query) for query in queries):
            raise ValueError(f"{label}: BUSCAS devem descrever objetos e ações concretas, sem termos abstratos.")
        narration = strip_stage_directions("\n".join(sections["NARRAÇÃO"]))
        if not narration:
            raise ValueError(f"{label}: a NARRAÇÃO está vazia.")
        text = " ".join("\n".join(sections["TEXTO"]).split())
        overlay = None if text.casefold() in {"", "nenhum"} else text
        if overlay and len(overlay.split()) > 4:
            raise ValueError(f"{label}: use até quatro palavras em TEXTO, ou escreva nenhum.")
        visual_type = "stock_image" if media_type == "imagem" else "stock_video"
        duration = estimate_duration_seconds(narration)
        scene_id = f"scene_{index + 1:03d}"
        beat = VisualBeat(
            beat_id=f"{scene_id}_a", duration=duration, intent=description, queries=queries,
            visual_type=visual_type, text_overlay=overlay,
            text_level="emphasis" if overlay else "caption",
            preferred_media="image" if media_type == "imagem" else "video",
            forbidden_elements=[x.strip() for x in options.get("EVITAR", "").split("|") if x.strip()],
        )
        scenes.append(Scene(
            scene_id=scene_id, narration=narration, intent=description, queries=queries,
            visual_type=visual_type, start=round(current_time, 2), end=round(current_time + duration, 2),
            duration_hint=duration, text_overlay=overlay, text_level=beat.text_level,
            narrative_function="hook" if index == 0 else "conclusion" if index == count - 1 else "explanation",
            narrative_phase=preset.narrative_phases[min(len(preset.narrative_phases) - 1, index * len(preset.narrative_phases) // count)],
            visual_beats=[beat],
        ))
        current_time += duration
    plan = ScenePlan(
        script_id=script.script_id, script_version=script.version_tag, script_hash=script.sha256,
        total_scenes=len(scenes), estimated_duration=round(current_time, 2), scenes=scenes,
        brand_preset=brand_preset, created_at=datetime.now(timezone.utc).isoformat(), title=script.title,
    )
    valid, errors = validate_scene_plan(plan, script.clean_narration)
    if not valid:
        raise ValueError("Roteiro Fábrica V1: confira se todo o texto falado está dentro de NARRAÇÃO. " + "; ".join(errors))
    return plan
