# 🤖 Fábrica de Shorts — Hub de Agentes e Pipelines Editoriais

Bem-vindo à pasta central de especificações e diretrizes de agentes para a **Fábrica de Shorts / Projeto Mercadoria**.

O objetivo deste diretório é fornecer documentação modular, executável e inequívoca para que qualquer agente de IA ou desenvolvedor consiga compreender, operar, evoluir e testar cada elo da produção audiovisual automatizada.

---

## 🎯 Filosofia Editorial Central

> **"A imagem não pode apenas acompanhar o que está sendo dito. Ela precisa ajudar a dizer."**

O projeto constrói ensaios audiovisuais curtos (60–90 segundos) baseados em uma contradição deliberada:
1. **Forma:** Estética de mercado, finanças, produtividade, riqueza e empreendedorismo.
2. **Conteúdo:** Análise materialista da mercadoria, do trabalho, da fábrica e das relações sociais de produção.

Nossa regra fundamental é:
- **Automatizar decisões repetitivas sem automatizar o olhar editorial.**

---

## 📚 Mapa de Agentes e Documentos

| Documento | Papel / Especialidade | Missão Principal |
| :--- | :--- | :--- |
| [AGENTS.md](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/AGENTS.md) | **Guia Mestre de Entrada (Raiz)** | Roteamento rápido de arquivos, comandos essenciais e economia de tokens para agentes. |
| [PIPELINES_AND_GUIDELINES.md](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/agents/PIPELINES_AND_GUIDELINES.md) | **Mapas de Pipelines & Diretrizes** | Referência técnica completa: fluxos, schemas JSON, deduplicação, Safe Area e Quality Gate. |
| [PIPELINE_WORKFLOW.md](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/agents/PIPELINE_WORKFLOW.md) | **Orquestração Geral** | Sequenciamento visual ponta a ponta e contratos entre etapas. |
| [01_DIRECTOR_AGENT.md](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/agents/01_DIRECTOR_AGENT.md) | **Scene Director** | Segmentação por frase, classificação retórica, geração de queries concretas e humor seco. |
| [02_MEDIA_RANKER_AGENT.md](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/agents/02_MEDIA_RANKER_AGENT.md) | **Media Ranker & Dedup** | Busca multimídia, eliminação de loops/cadeados, score semântico e diversidade visual. |
| [03_TYPOGRAPHY_AGENT.md](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/agents/03_TYPOGRAPHY_AGENT.md) | **Typography & Graphic Engine** | 3 níveis tipográficos (TITLE, EMPHASIS, CAPTION) e respeito à Safe Area 9:16 vertical. |
| [04_AUDIO_MASTERING_AGENT.md](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/agents/04_AUDIO_MASTERING_AGENT.md) | **Audio Mastering** | Voz a -14 LUFS EBU R128, compressão vocal, ducking dinâmico da trilha e silêncios reflexivos. |
| [05_ASSEMBLY_QA_AGENT.md](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/agents/05_ASSEMBLY_QA_AGENT.md) | **Assembly & Quality Control** | Construção do timeline (`AssemblyPlan`), pré-visualização, aprovação humana e exportação. |

---

## ⚡ Regras de Ouro para Qualquer Agente

1. **Narração é Sagrada:** O texto da narração (`narration`) nunca pode ser reescrito, resumido ou alucinado. Ele deve ser uma fatia literal do roteiro aprovado pelo humano.
2. **Proibição de Buscas Abstratas:** Nunca busque `"economy"`, `"market"`, `"wealth"` ou `"value"`. Sempre busque objetos e ações visíveis: `"t-shirt price tag"`, `"garment factory sewing machine"`, `"lithium mining truck"`.
3. **Zero Loops Visuais Involuntários:** O mesmo asset jamais deve aparecer duas vezes no mesmo vídeo, exceto quando for expressamente marcado como retorno narrativo (`intentional_callback = true`).
4. **Respeito à Safe Area:** Nenhum texto de impacto ou legenda pode ficar no topo (< 250px) ou na base (< 350px) em vídeos verticais 9:16.
5. **Voz Dominante:** A voz deve ser consistente, inteligível e calibrada a -14 LUFS integrados. A trilha sonora deve baixar automaticamente quando a voz fala.
