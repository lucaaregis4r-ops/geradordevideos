# Pesquisa assistida, comparação e acervo — entrega de 25/10/2026

## Entregue

- **Review Studio / Etapa 2:** sugestões lexicais concretas por plano, com consulta original e explicação. Seleção explícita antes de aplicar; limite de cinco consultas e respeito aos elementos proibidos. Não usa API de IA nem inventa reformulações para assuntos que não conhece.
- **Comparação lado a lado:** escolha até dois candidatos e carregue os arquivos para assistir antes de trocar. A comparação não altera seleção, narração, áudio nem aprovação. Download apenas quando solicitado; mídias bloqueadas continuam impedidas pelo downloader existente.
- **Acervo reutilizável:** mídia revisada com direitos definidos pode ser guardada com descrição observada e etiquetas. Autoria, licença, origem e hash perceptual são mantidos. Termos compostos das etiquetas são indexados corretamente; a mídia continua sujeita à avaliação contextual e à deduplicação em cada produção.
- **Laboratório de mídias:** 30 casos de café, varejo, confecção, logística e tecnologia; buscas isoladas das produções; revisão humana em três critérios (objeto, ação e enquadramento). Avaliações versionadas e exportáveis; nova avaliação da mesma pessoa sobre o mesmo candidato não infla a contagem.

## Acervo inicial e limitações

Nos quatro projetos examinados havia 22 seleções marcadas como revisadas, mas apenas uma tinha direitos registrados como permitidos. Ela foi inspecionada visualmente e indexada: `mixkit_43935`, uma xícara preta com café fumegante, pires e grãos de café. As demais não foram promovidas ao acervo com direitos inventados. Nenhum vídeo de produção foi alterado.

Os 30 casos estão preparados, mas **não foram avaliados por pessoas durante este sprint**. O painel começa em zero, e buscar um candidato não cria uma nota humana. Não há percentual comprovado de melhoria de relevância nem garantia de cobertura total. Ampliar o acervo para dezenas de mídias e concluir a avaliação humana continuam sendo etapas de curadoria, não resultados já obtidos.

## Validação

17 testes focados passaram (pesquisa assistida e recuperação), cobrindo preservação da ação nas sugestões, exclusões, consultas abstratas, isolamento das produções, histórico de avaliações, indexação, proveniência e restrições do acervo. Streamlit AppTest carregou Review Studio, selecionou dois candidatos e abriu o laboratório com 30 casos, sem exceções. Compilação, Ruff E9/F821 e diff também foram verificados.

## Caminho na interface

Review Studio → Etapa 2 → plano visual → **Sugestões de buscas**, **Comparar dois candidatos lado a lado** ou **Guardar mídia aprovada no acervo**.

Menu lateral → **Laboratorio de Midias** → escolher caso → pesquisar → carregar candidato → assistir → registrar os três critérios com o nome do avaliador.
