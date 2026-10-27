# Cota de voz Gemini — 25/10/2026

A produção `bermudas_1792936250` gerou as cenas 1–4 com a voz Orus. Na quinta, o provedor respondeu HTTP 429, limite de requisições por minuto, e indicou espera de aproximadamente 41 segundos. Não houve arquivo da cena 5; o pipeline confundiu ausência de síntese com falha de masterização.

O cliente agora respeita o intervalo indicado pelo provedor, com margem de dois segundos, até três novas tentativas e no máximo 180 segundos de espera acumulada por chamada. A interface da Fábrica informa a espera e a cena. Cotas diárias, limite zero e intervalos excessivos encerram com orientação explícita. A voz não é trocada automaticamente.

A Fábrica verifica a existência de áudio antes de masterizar e distingue falha de geração de falha no processamento. Os quatro áudios existentes não foram apagados. Esta correção não acrescenta retomada automática de produções antigas; uma nova produção pelo formulário ainda começa do início.

Validação: simulação de 429 com RetryInfo, intervalo decimal, cota diária/zero, espera excessiva, tentativas esgotadas, erro sem relação com cota, propagação pelo dispatcher Gemini e regressões existentes de exportação/transcrição. Não foi executada uma nova produção completa nem consumida cota real para esses testes.
