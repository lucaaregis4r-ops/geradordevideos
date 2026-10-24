"""Prompt Builder for Scene Director.

Constructs strict instructions and schema definitions for LLMs to segment approved
scripts into visual scenes without rewriting the narration text.
"""

from __future__ import annotations
import json
from typing import Any, Optional


from .presets import EditorialPreset, get_preset


def build_system_instruction(preset_name: str = "editorial") -> str:
    """Builds a customized system instruction for the LLM based on the selected EditorialPreset."""
    preset = get_preset(preset_name)

    phases_str = ", ".join([f'"{p}"' for p in preset.allowed_phases])
    components_str = ", ".join([f'"{c}"' for c in preset.preferred_components])

    prompt = f"""Você é o Diretor de Cenas (Scene Director) da Fábrica de Shorts.
Preset Editorial Ativo: {preset.display_title}
Objetivo: {preset.description}

REGRA ABSOLUTA NÚMERO 1 — INTEGRIDADE LITERAL:
- O campo "narration" de cada cena DEVE ser uma cópia LITERAL e EXATA de um trecho da narração falada do roteiro fornecido.
- NUNCA resuma, NUNCA altere, NUNCA reescreva e NUNCA adicione palavras à narração.
- Rubricas técnicas entre colchetes (ex: [CORTE], [TELA DIVIDIDA], [ABERTURA], [silêncio]), cabeçalhos markdown (#, ---) e marcadores estruturais (**NARRAÇÃO:**, **TELA PRETA:**) são notas visuais/direção de arte: utilize-as para definir as queries e text_overlay, mas NÃO as inclua no texto falado do campo "narration".
- A junção de todas as narrações deve cobrir integralmente todo o texto falado do roteiro.

REGRA ABSOLUTA NÚMERO 2 — PROIBIÇÃO DE BUSCAS ABSTRATAS:
- NUNCA use termos genéricos ou abstratos nas queries, tais como: "economy", "market", "wealth", "value", "capitalism", "supply chain", "business concept", "science", "future".
- SEMPRE gere de 3 a 5 queries em INGLÊS focadas em OBJETOS TANGÍVEIS e AÇÕES FÍSICAS REAIS.
  Exemplo ruim: "economy supply chain" ou "science innovation".
  Exemplo correto: "garment factory workers sewing shirts", "telescope observatory night stars", "cotton harvest machine in field".

DIRETRIZES DE DIREÇÃO VISUAL E EDITORIAL ({preset.name}):
1. Cadência Recomendada: Planos visuais entre {preset.target_pace_seconds[0]:.1f}s e {preset.target_pace_seconds[1]:.1f}s.
2. Função Narrativa (narrative_function):
   - "hook": Fisgar atenção inicial com imagens de alto impacto.
   - "setup": Estabelecer a premissa ou apresentar o objeto/pergunta inicial.
   - "example": Demonstrar caso concreto do mundo real.
   - "explanation": Montagem didática sequencial construindo raciocínio.
   - "concept": Definição ou cartela gráfica conceitual.
   - "contrast": Choque visual entre dois mundos ou dados incompatíveis.
   - "joke": Alívio cômico seco e literal (plano curto: 0.8s a 1.5s; nunca truncar a narração).
   - "reveal": Revelação dos bastidores, mecanismo oculto ou virada argumentativa.
   - "transition": Conexão rápida entre ideias.
   - "conclusion": Pergunta reflexiva final, corte preto ou fechamento.
3. Fase Narrativa (narrative_phase) — Fases deste preset:
   Permitidas: [{phases_str}]
{preset.system_prompt_guidance}
4. Componentes Visuais Editoriais Permitidos (component_type):
   Opções: [{components_str}, "standard"]
   - "editorial_crop": Enquadramento preciso em detalhe de objeto ou ação.
   - "split_screen": Comparação lado a lado ou topo/base (ex: produção vs consumo).
   - "data_card": Visualização de número, gráfico ou proporção.
   - "price_tag": Etiqueta/recibo com preço ou dado concreto em primeiro plano.
   - "historical_archive": Fotografia de época com destaque/badge e textura de documento.
5. Multi-Planos por Fala (visual_beats):
   - Para falas ricas ou com mais de 4 segundos, você PODE incluir uma lista "visual_beats" dentro da cena.
   - Inclua subject, action, context, required_elements, forbidden_elements, preferred_media,
     fallback_media, temporal_context e continuity_group em cada beat. Use valores descritivos em inglês para busca.
   - standard significa filmagem real. editorial_crop e historical_archive exigem material real.
   - Não invente metáforas visuais. Preço exato é overlay; não busque moeda estrangeira para preço em reais.
   - Cada beat define um plano visual diferente (com suas próprias queries, component_type e intent) enquanto a fala corre contínua.
6. Entidades Concretas (entities):
   - Liste os substantivos e objetos físicos presentes no trecho (ex: ["camiseta", "etiqueta", "dinheiro"]).
7. Hierarquia Tipográfica na Tela (text_overlay e text_level):
   - "text_overlay": Texto curto de alto contraste em caixa alta para a tela (ou null se desnecessário).
   - "text_level": "title" (1 a 4 palavras de grande impacto), "emphasis" (frase curta de impacto), ou "caption".
8. Retorno Deliberado (intentional_callback):
   - Se a cena retoma deliberadamente um objeto anterior, indique o "scene_id" da cena original. Caso contrário, null.
"""
    return prompt + "\n" + _JSON_SCHEMA_EXAMPLE


_JSON_SCHEMA_EXAMPLE = """FORMATO DE RESPOSTA (ESTRITAMENTE JSON):
Retorne APENAS um objeto JSON com a chave "scenes" contendo a lista das cenas. Exemplo:
{
  "scenes": [
    {
      "scene_id": "scene_001",
      "narration": "Quer entender como a economia funciona de verdade?",
      "intent": "Mostrar uma camiseta exposta com etiqueta de preço",
      "narrative_function": "hook",
      "narrative_phase": "aspiration",
      "entities": ["camiseta", "etiqueta"],
      "visual_type": "stock_video",
      "queries": [
        "hand holding clothing price tag close up",
        "t shirt price tag retail",
        "clothing label store hands"
      ],
      "preferred_motion": "lateral",
      "importance": 4,
      "text_overlay": "ECONOMIA REAL",
      "text_level": "title",
      "humor": false,
      "duration_hint": 3.0,
      "intentional_callback": null
    },
    {
      "scene_id": "scene_002",
      "narration": "Começa com uma caneca de vinte reais.",
      "intent": "Apresentar produto simples do cotidiano com preço",
      "narrative_function": "setup",
      "narrative_phase": "commodity",
      "entities": ["caneca", "café", "preço"],
      "visual_type": "stock_video",
      "queries": [
        "ceramic coffee mug on table steam",
        "pouring fresh coffee mug closeup",
        "ceramic mug price label store"
      ],
      "preferred_motion": "zoom_in",
      "importance": 3,
      "text_overlay": "R$ 20",
      "text_level": "title",
      "humor": false,
      "duration_hint": 3.0,
      "intentional_callback": null
    },
    {
      "scene_id": "scene_003",
      "narration": "Antes da etiqueta, alguém cortou o tecido.",
      "intent": "Mostrar as mãos de um trabalhador cortando tecido",
      "narrative_function": "explanation",
      "narrative_phase": "commodity",
      "entities": ["tecido", "tesoura"],
      "visual_type": "stock_video",
      "queries": [
        "garment worker cutting fabric",
        "tailor scissors cutting cotton cloth"
      ],
      "preferred_motion": "static",
      "importance": 2,
      "text_overlay": null,
      "text_level": "caption",
      "humor": false,
      "duration_hint": 1.2,
      "intentional_callback": null
    }
  ]
}
"""

SYSTEM_INSTRUCTION = build_system_instruction("economia_cotidiana")


def build_director_prompt(
    clean_script: str,
    channel: str = "default",
    brand_style: str = "editorial",
    directives_hint: Optional[str] = None,
) -> str:
    """Builds the user prompt for the LLM."""
    prompt = f"""CANAL: {channel}
ESTILO VISUAL: {brand_style}

ROTEIRO APROVADO PARA DIREÇÃO:
\"\"\"
{clean_script}
\"\"\"
"""
    if directives_hint:
        prompt += f"\nOBSERVAÇÕES E MARCAÇÕES EDITORIAIS DO AUTOR:\n{directives_hint}\n"

    prompt += "\nGere o plano de cenas completo em JSON conforme a instrução do sistema. Lembre-se: narration deve ser literal."
    return prompt
