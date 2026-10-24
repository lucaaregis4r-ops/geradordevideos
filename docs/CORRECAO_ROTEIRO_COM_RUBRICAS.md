# Roteiro com imagens e narração

O roteiro salvo em `bermudas_1792873497` reproduziu a falha `Narration does not match approved script literally`. O extrator anterior removia o rótulo `IMAGEM`, mas conservava sua descrição como fala; também mantinha blocos `TEXTO NA TELA`, valores de tela e continuações de rubricas. O diretor recebia uma narração contaminada e a validação reprovava a saída.

A extração agora acompanha blocos IMAGEM/NARRAÇÃO/TEXTO, reconhece limites de cenas e conserva as palavras e a pontuação faladas. Roteiros simples continuam aceitos. O roteiro bruto segue como referência visual separada no prompt; somente a narração limpa é autorizada como fala. Se o modelo alterar, omitir ou acrescentar narração, o diretor refaz a segmentação com o texto original usando regras locais, mantendo o validador estrito.

A tela principal oferece a prévia “Conferir a narração que será falada”. Alterações apenas nas rubricas geram uma nova versão imutável, mantendo o hash da narração quando a fala não muda.

Verificação: o roteiro real salvo passou pela extração e pelo diretor local (14 cenas), com validação literal aprovada e extração idempotente. O arquivo de entrada termina em “E assim uma”; esse trecho incompleto foi preservado. Não foi produzida uma nova exportação nesta correção.

Testes direcionados: 12 aprovados, 2 excluídos. Um excluído usa Gemini real; o outro é um teste legado que exige cinco cenas e uma piada literal de barril de petróleo, comportamento removido anteriormente. A primeira rodada o executou e confirmou essa incompatibilidade preexistente. As novas regressões cobrem blocos completos, texto simples entre cenas, alteração/omissão do modelo, observações visuais no prompt e versionamento de rubricas. Ruff F821/E9 e diff check aprovados.
