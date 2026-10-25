# Sprint 2 — pesquisa assistida e recuperação (primeira entrega)

O sprint de presets visuais por canal foi concluído. Esta é a primeira entrega do sprint seguinte, focada em recuperar mídia sem repetir TTS, direção ou render.

## Implementado

- Review Studio → Etapa 2 → **Recuperar cenas pendentes**: diagnóstico por plano, distinção entre arquivo ausente, rejeição, imagem provisória, revisão humana e material revisado.
- Rodadas de 1 a 20 planos (padrão 3), apenas para mídia ausente/rejeitada/provisória. Material existente aguardando revisão não é substituído automaticamente.
- Reservas de assets já usados e bloqueio dos rejeitados durante a nova busca; validações existentes de arquivo, relevância, resolução e duplicação continuam ativas.
- Duração proporcional por beat: uma tomada de 3 unidades em uma cena com 5 unidades e 10 segundos de áudio pesquisa um trecho de 6 segundos.
- Persistência após cada plano: uma falha posterior não perde o que foi recuperado. Repetir a rodada pula as mídias já encontradas e ainda aguardando revisão.
- Verificação de alteração externa do projeto durante a busca; não sobrescreve silenciosamente uma edição percebida antes do checkpoint.
- Histórico da rodada em `recovery_report.json`, com diagnóstico e tentativas por fonte. Exceções brutas de provedores não são exibidas no relatório.
- Edição explícita das consultas concretas por plano, uma por linha, e painel de candidatos para comparar descrição, fonte e relevância. A narração aprovada não é editada.

## Como usar

Escolha o projeto no Review Studio, abra Etapa 2 e confira as pendências. Ajuste buscas concretas se necessário, execute uma rodada e revise visualmente o que foi encontrado. A seleção automática é provisória e não substitui a aprovação de pertinência. Depois, valide o Quality Gate e renderize a revisão.

## Validação e limites

Seis testes offline passaram e cobrem preservação da narração, áudio, cenas aprovadas, duração por beat, retomada, erro do provedor, detecção de edição concorrente e ocultação de detalhes sensíveis de erros. Não foi feita uma recuperação em rede sobre os projetos do usuário: os vídeos anteriores permanecem intactos.

Ainda pendentes do sprint: acervo curado ampliado, benchmark humano de 30 cenas, sugestões assistidas de novas consultas e comparação visual de candidatos lado a lado. A rodada não garante encontrar uma mídia para toda ação específica. As rotas antigas de refazer a busca de todas as cenas continuam disponíveis e têm escopo diferente desta recuperação seletiva.

A tela de recuperação e os campos de consulta também foram verificados com Streamlit AppTest. O diagnóstico foi executado em modo somente leitura sobre o projeto de 79 segundos, identificando cenas 10 e 13 sem mídia e cinco rejeições por relevância em cada uma.
