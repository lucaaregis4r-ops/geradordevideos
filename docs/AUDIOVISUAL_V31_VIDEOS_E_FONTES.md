# V3.1 — filmagens reais e novas fontes

## O que mudou

A recuperação consulta vídeos verticais **e horizontais** antes do fallback fotográfico. O filtro técnico reserva espaço para filmagens: fotos verticais já não eliminam vídeos horizontais antes da avaliação semântica. Entre candidatos com pertinência suficiente, a intenção de vídeo prioriza filmagens com duração adequada. A ordem original de popularidade do provedor é reordenada pela descrição antes do limite de candidatos: um rack de rede não deve ocupar a vaga de roupas apenas por conter “rack”. Esse sinal de recuperação não concede aprovação visual.

Fotos do cache local permanecem fotos até a montagem; não são transformadas em MP4 durante a busca nem contadas como filmagens. O Review Studio mostra a proporção de tempo com vídeo, usando uma meta editorial de 65%, e oferece busca de vídeos por beat, importação de link do Mixkit e diagnóstico das tentativas por fonte. Trocar uma cena invalida sua aprovação e não inicia TTS/render enquanto o usuário compara candidatos.

O enquadramento `fit` preserva o conteúdo horizontal sobre fundo desfocado. Composição de texto e renderizador usam o mesmo filtro. A composição agora recorta somente o intervalo necessário e reinicia o intervalo do clipe derivado, evitando aplicar o deslocamento duas vezes. Foi corrigido o `shortest=1` da sobreposição PNG, que podia reduzir uma filmagem a um quadro. As chaves de cache mudaram para não reutilizar resultados antigos.

## Fontes

| Fonte | Integração | Situação nesta execução |
|---|---|---|
| Pixabay vídeo | API existente, recuperação horizontal ampliada | Busca e downloads reais conferidos |
| Mixkit | Descoberta em HTML público + resolução individual | Busca, licença livre e download real conferidos |
| Pexels vídeo | API existente | Sem chave configurada no ambiente |
| Coverr | Novo adaptador editorial sobre o cliente API existente | Sem chave configurada; contrato testável, sem smoke autenticado |
| Wikimedia Commons | API de vídeo já integrada | Continua disponível; não é fonte do novo exemplo |
| Archive / Prelinger | Busca histórica explícita | Não é usado para substituir cenas contemporâneas |

O Mixkit permite consulta de páginas públicas em seu robots.txt, mas seus termos proíbem download em massa. O adaptador limita a descoberta a uma página e cinco candidatos por consulta, espaça requisições, guarda HTML por 24 horas, respeita robots.txt e aceita somente redirecionamentos no mesmo domínio. Não usa login, CAPTCHA, proxies de evasão, sitemaps para coleta em massa nem URLs HD inventadas.

Um item só é resolvido para download quando a página indica `videoFree`; qualquer indicação `videoRestricted` vence um JSON-LD contraditório. Isso foi observado em itens de costura: o campo estruturado dizia Free enquanto a licença visível era Restricted. O link de download vem do botão/modal publicado. URLs de previews não são promovidas a arquivos liberados. Alterações de HTML/licença podem exigir atualização do adaptador; falhas permanecem pendentes, sem substituir a seleção por material fabricado.

Configuração opcional no bloco `[app]`: `editorial_mixkit_enabled = false` desliga a descoberta. Coverr usa `coverr_api_keys` já existente. Não foram adicionadas credenciais ao Git.

Referências consultadas: [Mixkit Terms](https://mixkit.co/terms/), [Mixkit Licenses](https://mixkit.co/license/), [Mixkit robots.txt](https://mixkit.co/robots.txt), [Coverr API](https://api.coverr.co/docs/), [Pexels API](https://www.pexels.com/api/documentation/).

## Evidência e limites

O projeto local `mercadoria_v31_videos` preserva as nove narrações do exemplo anterior, com onze segmentos. A seleção foi conferida visualmente nesta execução: roupas, celular, café, loja de roupas, algodão, oficina de costura, transporte e compra. O algodão permanece foto porque as amostras de vídeo encontradas eram outras plantas. O exemplo usa vídeos de Pixabay e Mixkit; não demonstra avaliação semântica automática perfeita. A aprovação contextual continua necessária.

As regressões cobrem preservação dos candidatos de vídeo, cache sem contaminação entre beats, busca horizontal, ordenação antes do limite, fotos locais, limites e licenças do parser Mixkit, intervalo/duração/enquadramento com texto e render nativo de áudio por beat. Testes antigos que esperavam sucesso com mídias inexistentes tiveram seus fixtures corrigidos; os protótipos que dependem de busca/TTS reais não foram usados como suíte offline.

Resultado verificado: **72,42% do tempo com filmagem**, MP4 de **36,337333 s** para **36,264 s** de áudio decodificado, 1080×1920. O gate e a inspeção da exportação passaram sem mídias ausentes, repetições involuntárias, placeholders, erros de área segura ou duração. Foram inspecionados 18 quadros ao longo da exportação, além das amostras dos candidatos. O arquivo local é `storage/projects/mercadoria_v31_videos/mercadoria_v31_videos.mp4`.

Validação de código: 31 testes de recuperação/revisão/regressão audiovisual passaram na rodada final, incluindo render FFmpeg com texto e áudio MP3 por beat. Uma rodada mais ampla teve 77 aprovações e um fixture antigo de mídia inexistente reprovado; o fixture foi corrigido e o caso passou na rodada final. Ruff F821/E9 e checagem de diff passaram. A suíte completa e o smoke autenticado de Coverr não foram executados.

A rodada adicional de fontes/importação passou com 21 testes, incluindo a troca de mídia sem iniciar síntese/render. A cópia final do MP4 foi conferida por SHA-256 contra o arquivo aprovado; as nove narrações foram comparadas literalmente com a versão anterior.
