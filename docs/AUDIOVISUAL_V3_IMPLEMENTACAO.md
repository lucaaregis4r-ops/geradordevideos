# Implementação audiovisual V3

Base auditada: `670cd3f50bb9bb57506f8b9372a5748efb6a4bfe`.

## Caso reproduzido e causas comprovadas

A produção local `bermudas_1792786738` contém `scenes.json`, `assembly_plan.json`, storyboard e exportação. O FFprobe mediu **48,241333 s** na exportação, contra **36,48 s** na montagem. A cena 006 tinha três beats, todos com `local_path` vazio: dois `editorial_crop` e um `standard`. O código antigo fabricava esses candidatos com score 0,95. A fábrica preparava fatias de áudio, mas passava o áudio integral da cena a cada segmento.

A inspeção dos arquivos selecionados encontrou:

| Cena | Fala / intenção | Conteúdo observado | Diagnóstico |
|---|---|---|---|
| 001 | origem do valor | dólares | metáfora genérica, exige revisão |
| 002 | camiseta de R$80 | alfaiate cortando tecido | trabalho pertinente ao tema, não evidencia a etiqueta |
| 003 | celular | cruz luminosa | material sem relação com o objeto |
| 004 | café | xícara de café | relação visual pertinente |
| 005 | número em objetos | paisagem e céu | material sem relação com preços |
| 006 | algodão, máquina, transporte | três componentes sem arquivo | material da cena não chegou aos beats |
| 007 | trabalho | máquina de costura | relação visual pertinente |
| 008 | só vê o preço | guarda-chuvas decorativos | material sem relação com etiqueta |
| 009 | história humana desaparece | fósforo/fumaça | metáfora não sustentada pela seleção |

A consulta era incorporada à pontuação semântica como se descrevesse o conteúdo. A simplificação por primeira palavra piorava a recuperação. A origem precisa da chamada que promoveu o preview antigo não pode ser determinada somente pelos manifestos; o gate salvo estava reprovado e havia exportação. Foram encontrados atalhos na fábrica, no re-render e na troca de mídia da interface.

## Mudanças

- Busca e validação independentes para todos os beats, inclusive cena com um único beat. `standard` e tratamentos de recorte não fabricam componentes vazios. Sem candidato válido, a seleção fica pendente.
- Queries preservam objeto e ação; removida a redução arbitrária à primeira palavra. Descrição original e tags são separadas da consulta. Scores anteriores sem contexto não são aceitos como evidência.
- Avaliação multimodal opcional via `RelevanceEvaluator`: três quadros, contexto, versão, cache e orçamento de chamadas. Nenhum serviço pago é ativado implicitamente. Sem avaliação visual, a aprovação de pertinência acontece na revisão.
- Contrato `SearchRequest` / `SearchResult`, capacidades, isolamento dos provedores, até três buscas concorrentes, timeout de busca, cache em memória (24h para resultados, 15min para vazios), diagnóstico de credenciais/timeout/429 e backoff. Wrappers reutilizam os clientes Pexels/Pixabay.
- Commons vídeo/derivados e Archive/Prelinger. Archive somente para busca explicitamente histórica (`visual_type=archive`), para não substituir cenas contemporâneas por filmes antigos. NASA/LOC são opt-in em `editorial_archive_providers`.
- Índice de cortes FFmpeg, escolha de intervalo dentro do plano, resolução útil após recorte e opção de enquadramento com margens. Nenhuma nova dependência de detecção de cenas.
- Intervalos e enquadramentos chegam ao `VideoProject` e participam da chave de cache. Mudança de intervalo invalida vídeo e montagem, preservando áudio e cenas intactas. Composição/overlays também têm identidade por mídia e parâmetros.
- Áudio medido prevalece, inclusive em humor. Fatias WAV por beat são efetivamente enviadas ao renderizador. Soma e contiguidade da timeline são verificadas.
- Gate exige arquivo local, dimensões e intervalo, inclui scores zero e o pior beat e mede a geometria do overlay renderizado. Re-render e troca de mídia passam pelo gate atual.
- Exportação real passa por FFprobe/decodificação/detecção de preto/duração; `render_audit.json` distingue preview de exportação aprovada e liga a aprovação ao hash da revisão.
- Review Studio conserva o plano revisado, permite aprovação/rejeição, troca, busca e importação por beat. Rejeição bloqueia o mesmo asset na nova busca. Mudança de intenção invalida aprovação.
- Importador curado: `python -m app.services.media_ranker.import_curated manifest.json`. Proveniência, direitos e intervalos são registrados; direitos desconhecidos não viram licença presumida.

## Operação

1. Dirigir o roteiro no Review Studio existente.
2. Buscar mídias; inspecionar cada plano e seus candidatos. Falhas são pendências, não fundos decorativos.
3. Aprovar pertinência somente após conferir o conteúdo. Usar troca/importação ou refazer busca quando inadequado.
4. Renderizar o plano atual. A aprovação é reavaliada, e o resultado passa pela verificação da exportação.

Não é necessário configurar uma nova API de IA. Pexels precisa de credencial quando escolhido; outras fontes continuam disponíveis. Os diagnósticos não incluem segredos.

## Verificação e limites

- Baseline original: seis testes unitários passaram, sem cobertura para os defeitos acima.
- Nova regressão nativa: quatro segundos de áudio distribuídos em dois planos resultam em quatro segundos exportados; remover a mídia de um beat bloqueia re-render, mesmo com montagem salva anteriormente aprovada.
- Testes offline cobrem queries por beat, downloads/validação, ausência de fallback, evidência semântica, MIME de Commons, ausência de derivado Archive, estados de provedores, cache por intervalo e integridade literal da narração.
- Smoke de busca autenticada/publica: Pexels sem credencial; Pixabay vazio para `sewing machine fabric` em retrato; Commons e Archive retornaram metadados. Esse teste isolado não comprova relevância nem download de todos os retornos.
- Europeana/Coverr continuam condicionados à confirmação de acesso/conta conforme o plano. Mixkit permanece importação manual; não foi criado scraper.
- NASA/LOC precisam de validação operacional com itens escolhidos antes de declarar disponibilidade em produção. O callback multimodal precisa de adaptador do provedor desejado para avaliação automática; revisão manual já funciona.
- As metas de 80 planos curados e benchmark humano de 30 beats dependem de curadoria real. Não são preenchidas com exemplos inventados nem declaradas atingidas por testes de código.

Referências de contratos: [Commons TimedMediaHandler](https://www.mediawiki.org/wiki/Extension:TimedMediaHandler/API), [Archive metadata](https://archive.org/developers/md-read.html), [NASA images API](https://images.nasa.gov/docs/images.nasa.gov_api_docs.pdf), [LOC API](https://www.loc.gov/apis/json-and-yaml/requests/).

## Resultado da reprodução corrigida

A produção `mercadoria_v3_verificacao` conserva literalmente as nove narrações originais, com onze segmentos (algodão, costura e transporte separados). O áudio decodificado mede **36,264 s**; o MP4 exportado mede **36,338667 s**, dentro da tolerância de encapsulamento. A duração anterior de 36,48 s incluía preenchimento do MP3. O verificador decodificou o arquivo inteiro e não encontrou erros de duração, formato ou trechos pretos. Foram inspecionados visualmente 18 quadros amostrados a cada dois segundos.

Gate: zero mídias ausentes, zero duplicatas involuntárias, zero placeholders, zero erros de safe area e resolução. A etiqueta final é um callback explícito. A seleção foi conferida visualmente nesta execução; o score associado não representa um benchmark de precisão automática. O limite de dois materiais por criador também é aplicado a planos importados no gate.

O exemplo utiliza principalmente fotos pertinentes e um vídeo, portanto **não atinge a meta de predominância de vídeo do plano**. Ele comprova a correção de montagem, áudio e revisão; a curadoria para elevar o movimento e a qualidade editorial continua necessária. Os arquivos locais estão em `storage/projects/mercadoria_v3_verificacao/` e não são versionados.

Validação de código: conjunto editorial de 44 testes aprovado; conjunto de render/provedores/direção com 66 aprovações e um timeout de CLI, aprovado na repetição isolada. Mais 20 testes de direção/beats, 13 regressões offline e a regressão nativa de áudio MP3 por beat passaram. Compilação e Ruff para erros de sintaxe/nomes indefinidos passaram. Não foi executada a suíte completa do repositório.
