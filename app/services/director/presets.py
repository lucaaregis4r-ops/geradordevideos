"""Editorial Presets for Scene Director.

Decouples the video production engine from a single topic or structure:
- 'ensaio_documental': Paced cadence, archival photos, contextual inquiry, historical evidence.
- 'internet_retro': High-dynamic tempo, desktop/document aesthetics, literal absurd humor.
- 'explicador_cientifico': Methodical breakdown, diagrams, formulas, data cards, concrete mechanisms.
- 'economia_cotidiana': Tangible commodity biography (aspiration -> commodity -> production -> labor -> reveal).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class EditorialPreset:
    name: str
    display_title: str
    description: str
    target_pace_seconds: tuple[float, float]  # (min_duration, max_duration) per scene
    allowed_phases: List[str]
    default_phase: str
    color_palette: Dict[str, str]             # Primary, secondary, accent, background
    allowed_transitions: List[str]
    preferred_components: List[str]
    system_prompt_guidance: str
    concrete_entity_seeds: List[str] = field(default_factory=list)

    @property
    def narrative_phases(self) -> List[str]:
        return self.allowed_phases

    @property
    def allowed_components(self) -> List[str]:
        return self.preferred_components

    @property
    def pace_wpm(self) -> int:
        avg_dur = (self.target_pace_seconds[0] + self.target_pace_seconds[1]) / 2.0
        return int(60.0 / avg_dur * 6.0)


PRESETS: Dict[str, EditorialPreset] = {
    "economia_cotidiana": EditorialPreset(
        name="economia_cotidiana",
        display_title="Economia Cotidiana (Projeto Mercadoria)",
        description="Biografia tangível de um objeto: fetiche da mercadoria, cadeia produtiva e trabalho humano.",
        target_pace_seconds=(2.5, 4.5),
        allowed_phases=["aspiration", "commodity", "production", "labor", "reveal"],
        default_phase="commodity",
        color_palette={"bg": "#0D0E11", "text": "#FFFFFF", "accent": "#E63946", "secondary": "#F1FAEE"},
        allowed_transitions=["cut", "fade"],
        preferred_components=["price_tag", "editorial_crop", "split_screen"],
        system_prompt_guidance=(
            "ESTRUTURA: Progressão em 5 atos:\n"
            "1. aspiration: Luxo, aspiração, finanças, números abstratos.\n"
            "2. commodity: O objeto físico no cotidiano (preço, loja, vitrine).\n"
            "3. production: Matéria-prima, fiação, fábricas, maquinário industrial.\n"
            "4. labor: O trabalho humano concreto, esforço vivo, operários, costura.\n"
            "5. reveal: Contraste do valor, provocação e fechamento crítico."
        ),
        concrete_entity_seeds=["camiseta", "caneca", "etiqueta", "fábrica", "máquina", "algodão", "costura", "dinheiro", "loja"],
    ),
    "ensaio_documental": EditorialPreset(
        name="ensaio_documental",
        display_title="Ensaio Documental & Histórico",
        description="Investigação histórica e contemporânea com arquivos, documentos, lugares e contexto sóbrio.",
        target_pace_seconds=(3.5, 5.5),
        allowed_phases=["tese", "contexto", "evidencia", "analise", "sintese"],
        default_phase="contexto",
        color_palette={"bg": "#121214", "text": "#E8E6E3", "accent": "#C9A227", "secondary": "#A8A29E"},
        allowed_transitions=["cut", "fade", "dissolve"],
        preferred_components=["historical_archive", "editorial_crop", "split_screen"],
        system_prompt_guidance=(
            "ESTRUTURA: Ensaio documental sóbrio e investigativo:\n"
            "1. tese: Apresentação da pergunta fundamental ou do paradoxo histórico.\n"
            "2. contexto: Espaço, época, personagens e atmosfera de época ou local.\n"
            "3. evidencia: Fotografias de arquivo, recortes de jornais, cartas, registros oficiais.\n"
            "4. analise: Confronto entre o passado e o reflexo contemporâneo.\n"
            "5. sintese: Conclusão meditativa, imagem de impacto final com pergunta reflexiva."
        ),
        concrete_entity_seeds=["fotografia", "documento", "jornal", "cidade", "rua", "mapa", "carta", "edifício", "monumento"],
    ),
    "internet_retro": EditorialPreset(
        name="internet_retro",
        display_title="Internet Retrô / Desktop Investigativo",
        description="Ritmo dinâmico com recortes de pop-culture, estética desktop, humor literal e recortes secos.",
        target_pace_seconds=(1.2, 3.0),
        allowed_phases=["hook_pop", "desconstrucao", "humor_literal", "plot_twist", "remix"],
        default_phase="desconstrucao",
        color_palette={"bg": "#0A0B10", "text": "#FFFFFF", "accent": "#00F0FF", "secondary": "#FF0055"},
        allowed_transitions=["cut"],
        preferred_components=["split_screen", "price_tag", "data_card"],
        system_prompt_guidance=(
            "ESTRUTURA: Rápido, irônico e visualmente dinâmico:\n"
            "1. hook_pop: Choque estético nos primeiros 2 segundos.\n"
            "2. desconstrucao: Análise com documentos, capturas e recortes em ritmo ágil.\n"
            "3. humor_literal: Metáforas abstratas interpretadas ao pé da letra com humor seco.\n"
            "4. plot_twist: Quebra brusca de expectativa visual e sonora.\n"
            "5. remix: Colagem final reflexiva e chamada para o comentário."
        ),
        concrete_entity_seeds=["recibo", "etiqueta", "captura", "computador", "pasta", "notícia", "meme", "gráfico"],
    ),
    "explicador_cientifico": EditorialPreset(
        name="explicador_cientifico",
        display_title="Explicador Científico e Tecnológico",
        description="Didática clara com diagramas, visualização de grandezas físicas, anatomia de processos e rigor.",
        target_pace_seconds=(2.5, 4.5),
        allowed_phases=["enigma", "mecanismo", "experimento", "implicacao", "conclusao"],
        default_phase="mecanismo",
        color_palette={"bg": "#080C14", "text": "#E2E8F0", "accent": "#38BDF8", "secondary": "#94A3B8"},
        allowed_transitions=["cut", "fade"],
        preferred_components=["data_card", "editorial_crop", "split_screen"],
        system_prompt_guidance=(
            "ESTRUTURA: Rigor didático e clareza científica:\n"
            "1. enigma: Fenômeno contra-intuitivo ou observação empírica intrigante.\n"
            "2. mecanismo: Como o processo realmente funciona (átomos, engrenagens, física, biologia).\n"
            "3. experimento: A medição, o gráfico, o dado ou o telescópio/laboratório.\n"
            "4. implicacao: O impacto tangível na escala humana ou cósmica.\n"
            "5. conclusao: Resposta ao enigma inicial com visual limpo e elegante."
        ),
        concrete_entity_seeds=["telescópio", "foguete", "planeta", "átomo", "gráfico", "laboratório", "cálculo", "microscópio"],
    ),
}


def get_preset(name: str = "editorial") -> EditorialPreset:
    """Retrieves an EditorialPreset by name with alias fallbacks."""
    key = (name or "editorial").lower()
    if key in ("editorial", "default", "mercadoria", "economia"):
        key = "economia_cotidiana"
    elif key in ("documental", "documentary", "historia"):
        key = "ensaio_documental"
    elif key in ("retro", "internet", "vhs"):
        key = "internet_retro"
    elif key in ("ciencia", "science", "cientifico", "explicador"):
        key = "explicador_cientifico"

    return PRESETS.get(key, PRESETS["economia_cotidiana"])


def list_presets() -> List[EditorialPreset]:
    """Returns all available editorial presets."""
    return list(PRESETS.values())


EDITORIAL_PRESETS = PRESETS
