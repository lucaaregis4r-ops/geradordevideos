# Presets visuais por canal

Pesquisa e implementação em 24/10/2026. Este passo antecipa os filtros previstos no sprint 3, conforme a prioridade do usuário; a recuperação assistida de buscas do sprint 2 continua pendente.

## Referências verificadas

- [FFmpeg — filtros](https://ffmpeg.org/ffmpeg-filters.html): `eq`, `colorbalance`, `noise`, `vignette` e `lut3d`. A instalação local oferece esses filtros. É a base escolhida para a primeira versão, sem acrescentar um motor de renderização.
- [Shotcut](https://github.com/mltframework/shotcut): editor aberto com interface de filtros; referência de organização de controles e edição não destrutiva.
- [frei0r](https://github.com/dyne/frei0r): coleção de plugins de efeitos de vídeo, referência para expansões. Não foi instalada nem incorporada ao código.

Os presets desta implementação são combinações próprias de parâmetros do FFmpeg. Não foram copiados LUTs, código ou pacotes de efeitos desses repositórios. LUTs externos, transições animadas, marca d'água e normalização automática de fontes HDR não estão incluídos neste passo.

## Uso

1. Abra **Identidade**. Escolha **Criar novo preset** ou importe a identidade anterior.
2. Preencha canal e nome da variação, por exemplo `Mercadoria · Documental suave`.
3. Escolha estilo documental, quente, frio ou arquivo; regule intensidade, granulação e bordas. “Original” desativa a correção de cor; textura e bordas continuam independentes.
4. Envie um vídeo de teste e gere a comparação de três segundos, sem áudio. As duas prévias usam o mesmo trecho. Mudanças nos controles exigem gerar outra comparação.
5. Salve. Para variar um preset existente, marque **Salvar como novo preset**. Desmarque apenas para atualizar aquele preset.
6. Na página principal, marque **Aplicar identidade salva** e escolha **Canal / preset de identidade**.

Cada preset inclui filtro, cor dos textos, voz, velocidade e trilha. A produção guarda uma cópia de todos esses valores. Alterações no preset não mudam os projetos existentes. O usuário escolhe o preset em cada produção; não há agendamento automático de vários canais.

## Processamento e limites

O filtro é aplicado à mídia, após animar fotos e antes de compor textos. Cartelas gráficas são preservadas. Tanto a produção inicial quanto a renderização de revisão usam o mesmo processamento. O trecho é recortado uma vez, e os offsets são zerados para impedir corte duplo. A narração continua vindo dos arquivos TTS originais.

O cache inclui preset, intensidade, textura, bordas, fonte, data de modificação e intervalo. Arquivos são gravados atomicamente e só reutilizados após a verificação de duração. Estilo original com intensidade/textura/bordas zeradas não exige recodificação adicional. Os demais estilos acrescentam uma passagem de vídeo ao render.

A aplicação uniforme de um tratamento cria recorrência visual, mas não iguala automaticamente imagens com iluminação/exposição diferentes. A primeira versão é pensada para material SDR comum; faça a comparação antes de aplicar efeitos fortes. O tratamento “arquivo” é apenas estético, não transforma imagens atuais em registros históricos.

## Validação

24 testes distintos passaram entre `test_brand_looks.py` (9) e `test_sprint_identity.py` (15): execução real de todos os estilos em FFmpeg, duração e dimensões, bypass com intensidade zero, cache, rejeição de trechos truncados, isolamento entre canais e preservação da cópia por projeto. Streamlit AppTest verificou carregamento do editor e troca de dois presets com estilos diferentes. Ruff E9/F821, compilação e diff também passaram. Prévia em 540×960 no máximo; ela serve para avaliar o estilo, não para inspecionar detalhes da exportação final.
