# Como usar as diretrizes de roteiro

1. Copie `docs/PROMPT_ROTEIRISTA_FABRICA.md` para a IA que escreve seus roteiros.
2. Substitua a última linha pelo tema, público, tom e fatos de referência.
3. Cole a resposta completa no campo de roteiro da Fábrica. Conserve a primeira linha `# ROTEIRO FÁBRICA V1`.
4. Confira a prévia da narração antes de produzir. No Review Studio, confira as mídias e sua correspondência com as falas.

O prompt e um botão para carregar um exemplo ficam na tela principal, em **Preparar um roteiro na sua IA**. O exemplo completo está em `docs/exemplos/roteiro_caneca_fabrica_v1.md`: 12 cenas e 172 palavras faladas. É um exemplo de sintaxe e argumento, não uma promessa de que cada filmagem estará disponível.

## O que o formato controla

Cada `## CENA 01` define um plano, preservando a fala em `NARRAÇÃO`, a descrição e as buscas dentro de `IMAGEM`, e o texto gráfico em `TEXTO`. `TIPO` aceita `video` ou `imagem`. `BUSCAS` contém três a cinco alternativas separadas por `|`; o prompt pede três. `EVITAR` conserva exclusões por plano e filtra correspondências explícitas na descrição/tags originais dos resultados. Esse filtro não substitui inspeção visual de conteúdo não descrito.

A leitura direta conserva os planos, buscas e textos aprovados. Não usa uma chamada de IA para refazer uma decupagem já explícita. Campos faltantes, numeração fora de ordem, buscas abstratas ou textos gráficos muito longos produzem mensagens de correção. Roteiros sem o cabeçalho continuam usando o diretor existente.

As durações iniciais são estimativas; o áudio medido continua determinando a montagem. A proporção de filmagem, a pertinência dos assets, os direitos de uso e a aprovação do Quality Gate continuam dependendo dos arquivos selecionados e da revisão. Não há novas chaves, modelos ou serviços pagos configurados por este formato.

Verificação: 27 testes direcionados passaram; uma regressão nativa de render foi excluída por esta alteração tratar do roteiro e da recuperação, sem alterar o renderizador. Os casos cobrem o exemplo completo sem chamada ao diretor de IA, fidelidade literal, campos inválidos, tipo de mídia, exclusões por metadados e compatibilidade do extrator. Ruff F821/E9 e checagem do diff passaram.

## Atualização de uma instância já aberta

Após atualizar módulos do programa, reinicie o processo Streamlit. Reexecutar apenas a página pode conservar referências antigas de módulos Python já importados. Isso foi observado numa instância iniciada antes da atualização: a interface reconhecia o cabeçalho V1, mas a versão antiga do extrator ainda incluía IMAGEM/BUSCAS na narração. O mesmo arquivo passou em processo novo com 14 cenas e 167 palavras faladas. A tela principal recupera o texto bruto do último roteiro enviado após reiniciar o servidor, e a prévia permite conferir a extração antes de produzir.
