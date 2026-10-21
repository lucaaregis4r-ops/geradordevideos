# 🔍 Agente 02: Media Ranker & Deduplication Engine

**Localização no Código:** [app/services/media_ranker/](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/app/services/media_ranker/)  
**Arquivos Chave:** [media_searcher.py](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/app/services/media_ranker/media_searcher.py), [deduplicator.py](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/app/services/media_ranker/deduplicator.py), [semantic_ranker.py](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/app/services/media_ranker/semantic_ranker.py), [candidate_builder.py](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/app/services/media_ranker/candidate_builder.py)

---

## 1. Missão do Agente

O **Media Ranker** é o curador visual do pipeline. Ele recebe o conjunto de queries gerado pelo Scene Director e executa busca, triagem técnica, ranqueamento semântico e aplicação de regras estritas de não-repetição.

Sua responsabilidade principal é garantir que:
1. **Nenhum asset seja repetido acidentalmente.**
2. **Nenhuma família repetitiva domine o vídeo** (eliminando a "síndrome dos cadeados").
3. **Mídias com alto alinhamento conceitual vençam** sobre mídias genéricas de banco de imagens.
4. **Retornos narrativos (`intentional_callback`) sejam respeitados.**

---

## 2. A Fórmula de Pontuação Composta (Composite Score)

Cada candidato a mídia recebe um score final calculado em múltiplos estágios:

$$\text{FinalScore} = (\text{ScoreSemântico} \times 0.50 + \text{QualidadeTécnica} \times 0.25 + \text{BônusDiversidade} \times 0.25) \times \text{FatorPenalidade}$$

### Tiers de Penalidade Gradual do Deduplicador:
1. **Reutilização Exata (`asset_id` já visto):**
   - Multiplicador: $\times 0.10$ (score praticamente zerado).
2. **Mesma Categoria Semântica / Família Visual Consecutiva:**
   - Multiplicador: $\times 0.50$ (desencoraja múltiplos vídeos de executivos na janela ou galpões seguidos).
3. **Asset na Lista Negra (`blocked_assets`):**
   - Eliminado imediatamente da lista de candidatos.
4. **Exceção de Callback Narrativo (`intentional_callback`):**
   - Se a cena solicitar deliberadamente o retorno do asset da cena X (ex: volta da camiseta de R$ 79,90 no fechamento), todas as penalidades são ignoradas e o asset recebe pontuação $\ge 0.95$.

---

## 3. O Fim do "Problema dos Cadeados"

O problema identificado no protótipo decorreu da repetição de vídeos de um único autor no Pixabay (*Matthias_Groeneveld* com cadeados em armazéns).

O Media Ranker resolve isso através de:
- **Limite por Autor/Criador:** No máximo 2 mídias do mesmo criador em todo o vídeo.
- **Deduplicação Perceptual:** Se duas mídias possuírem títulos, tags ou assinaturas quase idênticas, apenas a melhor avaliada é mantida.
- **Prioridade ao Acervo Aprovado (`SmartLibrary`):** Mídias locais validadas previamente pelo diretor humano têm preferência sobre bancos públicos externos.

---

## 4. Integração com a Fábrica

O método principal é:
```python
searcher = MediaSearcher()
enriched_plan = searcher.populate_scene_plan(
    plan=scene_plan,
    candidates_per_scene=5,
    download_selected=True,
)
```
Cada cena sai enriquecida com `media_candidates` (para troca manual na UI com 1 clique) e `selected_media` (a melhor classificada para montagem automática).
