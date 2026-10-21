"""Directives parser for human scripts.

Extracts optional inline direction tags without mutating the intended narration.
Example tags:
- [visual: formula F = m * a]
- [graphic], [formula], [quote], [number], [chart], [map], [stock], [photo], [archive]
- [keep-media]
- [pronounce: spoken text]
- [pause: 300ms]
- [emphasis: word]
"""

from __future__ import annotations
from dataclasses import dataclass, field
import re
from typing import Any

# Regex to match tags like [visual: ...], [graphic], [TELA DIVIDIDA], [pause: 300ms], etc.
_DIRECTIVE_PATTERN = re.compile(r"\[([a-zA-Z0-9_\sÀ-ÿ.—–:-]+)\]")


@dataclass
class ScriptDirective:
    tag: str
    value: str | None = None
    position: int = 0
    raw: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "value": self.value,
            "position": self.position,
            "raw": self.raw,
        }


@dataclass
class ParsedScriptSection:
    raw_text: str
    clean_narration: str
    directives: list[ScriptDirective] = field(default_factory=list)


def strip_stage_directions(text: str) -> str:
    """Strips all stage directions, camera instructions, markdown formatting,
    headers, dividers, and structural labels so that ONLY spoken narration remains.
    """
    t = text
    # 1. Bracketed stage directions: [anything inside brackets]
    t = re.sub(r"\[[^\]]+\]", " ", t)
    # 2. Markdown headers (# Title, ## Section)
    t = re.sub(r"(?m)^\s*#+.*$", " ", t)
    # 3. Horizontal rules (---, ===, ___)
    t = re.sub(r"(?m)^\s*[-=_]{3,}\s*$", " ", t)
    # 4. Structural voiceover / scene labels
    t = re.sub(r"(?i)\*\*(?:narração|narrador|voz|tela|corte|abertura|imagem|áudio|música|final|pausa)[^*]*\*\*:?", " ", t)
    t = re.sub(r"(?i)^\s*(?:narração|narrador|voz|tela preta|final|corte|abertura):\s*", " ", t, flags=re.MULTILINE)
    # 5. Remove bold/italic markers
    t = re.sub(r"\*{1,3}", "", t)
    # 6. Normalize whitespace
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n\s*\n+", "\n\n", t).strip()
    return t


def parse_directives(text: str) -> tuple[str, list[ScriptDirective]]:
    """Separates inline directives and stage directions from the narration text.
    Returns:
        tuple[clean_narration, list[ScriptDirective]]
    """
    directives: list[ScriptDirective] = []

    for match in re.finditer(r"\[([a-zA-Z0-9_\sÀ-ÿ.—–:-]+)\]", text):
        raw = match.group(0)
        content = match.group(1).strip()
        if ":" in content:
            tag, val = content.split(":", 1)
            directives.append(
                ScriptDirective(tag=tag.strip().lower(), value=val.strip(), position=match.start(), raw=raw)
            )
        else:
            directives.append(
                ScriptDirective(tag=content.lower(), value=None, position=match.start(), raw=raw)
            )

    clean = strip_stage_directions(text)
    return clean, directives


def strip_directives(text: str) -> str:
    """Convenience helper to get only the spoken clean narration text."""
    clean, _ = parse_directives(text)
    return clean
