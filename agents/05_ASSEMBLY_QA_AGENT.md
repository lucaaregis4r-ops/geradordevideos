# 📊 Agente 05: Assembly Planner & Quality Control (QA)

**Localização no Código:** [app/services/assembly/](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/app/services/assembly/) / [app/services/review/](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/app/services/review/)  
**Arquivos Chave:** [planner.py](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/app/services/assembly/planner.py), [quality_checker.py](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/app/services/assembly/quality_checker.py), [schemas.py](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/app/services/assembly/schemas.py), [review_manager.py](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/app/services/review/review_manager.py)

---

## 1. Missão do Agente

O **Assembly & QA Agent** é o inspetor final antes do render. Ele transforma o `ScenePlan` enriquecido em uma timeline de montagem (`AssemblyPlan`) com timings milimétricos, calcula métricas de qualidade e bloqueia renderizações caso o plano viole as diretrizes editoriais.

Ele implementa o princípio:
> **"Nenhum vídeo é renderizado sem antes passar pelo crivo do QualityChecker ou pela aprovação humana no Review Studio."**

---

## 2. O Manifesto de Montagem (`AssemblyPlan`)

O `AssemblyPlan` é um documento estruturado intermediário contendo cada segmento da montagem:

```json
{
  "project_id": "mercadoria_v02",
  "total_duration": 78.4,
  "segments": [
    {
      "segment_id": "seg_scene_001",
      "start": 0.0,
      "end": 2.8,
      "asset_id": "dubai_luxury_012.mp4",
      "asset_type": "video",
      "asset_path": "/storage/media_cache/dubai_luxury_012.mp4",
      "crop": "9:16",
      "overlay_text": "ECONOMIA REAL",
      "text_level": "title",
      "transition": "cut",
      "purpose": "hook",
      "scene_ref": "scene_001",
      "is_callback": false
    }
  ],
  "quality_score": {
    "passed": true,
    "asset_count": 28,
    "duplicate_assets": 0,
    "semantic_match_avg": 0.88,
    "visual_diversity": 0.82,
    "text_safe_area_errors": 0,
    "low_resolution_count": 0,
    "segments_without_visual": 0
  }
}
```

---

## 3. Gates Rígidos do QualityChecker

A renderização é sumariamente **bloqueada** se qualquer uma das condições abaixo for violada:

1. `duplicate_assets > 0` (qualquer repetição involuntária de imagem).
2. `segments_without_visual > 0` (qualquer segmento com asset ausente ou vazio).
3. `text_safe_area_errors > 0` (qualquer texto invadindo as margens de 250px topo ou 350px base).
4. `semantic_match_avg < 0.60` (coerência semântica geral abaixo do limite editorial).
5. `visual_diversity < 0.30` (vídeo monótono composto apenas por um único tipo de mídia).

---

## 4. Modo de Revisão Humana no Review Studio

Antes de gastar minutos de codificação FFmpeg pesada, o operador humano tem à disposição o painel `webui/pages/1_🎬_Scene_Review.py` para:
- **Aprovar o Plano Visual:** Visualizar a prancha de thumbnails.
- **Trocar com 1 Clique:** Selecionar qualquer um dos 5 candidatos concorrentes da cena.
- **Bloquear Asset Indesejado (`block_asset`):** Eliminar permanentemente um vídeo inadequado (ex: cadeado, clichê corporativo).
- **Ajustar Overlay:** Modificar o texto de impacto sem alterar a narração falada.
