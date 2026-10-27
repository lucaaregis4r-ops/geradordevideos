# Plano: produções completas e identidade audiovisual

## Diagnóstico em 24/10/2026

Inspeção dos planos e auditorias locais, sem alterar as produções anteriores:
- `bermudas_1792877114`: 79,296 s, 14 cenas; cenas 10 e 13 sem mídia. Procuravam reposição de pacotes de café e leitura do pacote no caixa. Os cinco candidatos de cada cena tinham relevância 0,55 e foram rejeitados. O modo preview ignorou a falha de cobertura; o arquivo passou na checagem técnica, mas `publishable=false`.
- `bermudas_1792581521`: plano de 165,4 s e 31 segmentos, com 16 assets provisórios. Isso não equivale a cobertura editorial válida.
- O orçamento global de 45 s por cena podia eliminar as buscas alternativas depois de uma primeira consulta lenta.
- A seleção de voz da Fábrica era independente do motor legado, escondendo Gemini e usando um identificador incorreto para Thalita.

## Sprint 1 — cobertura, escolha de voz e editor inicial (implementado)

1. Bloquear ausência de mídia, placeholders, duplicação, resolução, timeline e safe area mesmo em preview. Prévia editorial continua opcional, desligada por padrão; não equivale a aprovação para publicação.
2. Salvar `readiness.json` com cenas pendentes, narração e buscas. Mostrar a tabela na página principal após uma produção bloqueada. Storyboard e plano ficam disponíveis para correção.
3. Executar até cinco consultas distintas por cena, sem deixar a primeira consumir o orçamento das alternativas; manter timeout/backoff por fonte. Incluir vocabulário concreto de café/embalagens/prateleira/caixa na correspondência bilíngue, sem transformar metadados em aprovação visual.
4. Unificar as opções de voz: catálogo Edge português consultado ao vivo (3 brasileiras, 2 portuguesas) e vozes Gemini do motor existente. Audicionar no Voice Studio ou no editor. Gemini usa a chave existente e sua cota; disponibilidade real depende da conta/modelo. Não foi efetuada síntese paga durante a validação deste sprint. O motor Gemini atual não aplica o controle de velocidade.
5. Nova página **Identidade**: cor de destaque com prévia tipográfica, voz, velocidade Edge, upload opcional de música e volume. Persistência local e cópia imutável por produção. A opção **Aplicar identidade salva** na página principal aplica esses campos; projetos anteriores não são alterados.
6. Trilha incorporada com ducking na produção e na renderização de revisão; falha na aplicação é reportada, em vez de desaparecer silenciosamente. Cores integram a chave de cache dos overlays.

Aceite: testes de bloqueio, cobertura, alternativas de consulta, persistência de kit, cor/safe area, catálogo/roteamento de voz, e mixagem local com FFmpeg. Não promete encontrar imagens adequadas para qualquer ação específica; pendências exigem seleção no Review Studio.

## Sprint 2 — busca assistida e recuperação de cenas

- Painel por cena: consultas usadas, fonte, candidatos, rejeições e falhas de download.
- Rebuscar somente as pendências, preservando narração, áudio e seleções aprovadas.
- Consultas alternativas editáveis e propostas de aproximação visual que exigem aprovação humana quando mudam a ação descrita.
- Ampliar acervo próprio licenciado para café, varejo, confecção e logística; indexar tomadas.
- Benchmark humano de 30 cenas, incluindo ações difíceis. Medir cobertura real e relevância por cena, não só quantidade de resultados.
- Retomada de tarefas longas e comparação de candidatos lado a lado.

## Sprint 3 — kit de marca completo e acabamento

- Filtros leves de cor/exposição com antes/depois, aplicados às imagens antes da tipografia; cache por versão do kit.
- Logo, fontes licenciadas, cartelas e posições validadas na safe area.
- Biblioteca de trilhas com autoria/licença, pontos de entrada, fades e intensidade por ato.
- Versões nomeadas de kits, aplicação deliberada a projetos existentes e revisão antes de exportar.
- Testes de regressão visual, loudness e inteligibilidade em vídeos de 60, 180 e 600 segundos.

## Onde colocar a música

**Na Fábrica:** envie um arquivo que possa usar e desative “Produzir sem trilha musical”. O áudio é incorporado ao MP4 e recebe ducking. Útil para uma identidade sonora consistente.

**Ao publicar:** deixe a produção sem trilha para adicionar música no editor da plataforma. O arquivo da Fábrica mantém a narração. Escolha um dos fluxos para evitar duas músicas sobrepostas. Este sprint não publica nem consulta bibliotecas das plataformas.

## Operação

Após atualizar módulos Python, reinicie o processo Streamlit para carregar o código novo. Apenas recarregar a aba pode manter serviços antigos em memória. Os vídeos já produzidos não são reparados automaticamente por esta atualização.

## Validação do sprint

43 testes distintos passaram entre `test_sprint_identity.py`, `test_audiovisual_v3.py`, `test_factory_screenplay.py` e `test_screenplay_narration.py`. Incluem mixagem real de dois segundos com FFmpeg e preservação da duração, além de roteamento Gemini simulado sem consumir a API. As páginas Identidade e Voice Studio passaram no Streamlit AppTest e o editor foi conferido no navegador. Compilação Python, Ruff E9/F821 e diff sem erros de whitespace. Isso não substitui uma avaliação humana de um novo vídeo longo nem mede a qualidade subjetiva das vozes Gemini.
