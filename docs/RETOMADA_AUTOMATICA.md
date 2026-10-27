# Produções salvas e retomada por cota

A Fábrica salva `production_job.json` com roteiro e configurações, `voice_plan.json` com a direção original e um recibo por áudio. Os recibos verificam texto falado, voz, velocidade e hash do arquivo. Cenas concluídas não consomem outra chamada TTS na retomada. Alterações de roteiro/configuração exigem outro projeto.

Quando a síntese retorna erro de cota, a produção fica `waiting_quota` e a próxima tentativa é marcada para 24 horas após o erro. Cada novo bloqueio de cota adia outras 24 horas. A voz não é trocada. Falhas não relacionadas a cota ficam `failed`, sem repetição automática. Resultados reprovados no Quality Gate ficam `needs_review`, sem render forçado. Um bloqueio de arquivo impede execução simultânea da mesma produção.

## Instalação local Linux

Execute `.venv/bin/python scripts/install_resume_timer.py`. Instala serviço e timer systemd do usuário, verificando a fila a cada minuto. A aba pode ficar fechada; o computador precisa estar ligado, conectado e com a sessão do usuário ativa. Quando o serviço retorna, trabalhos vencidos são processados. Não liga nem acorda o computador. O instalador não ativa faturamento nem troca chaves.

Consultar: `systemctl --user status fabrica-resume.timer`. Logs: `journalctl --user -u fabrica-resume.service`. Desativar: `systemctl --user disable --now fabrica-resume.timer`. O cancelamento de uma produção pendente está disponível na página Produções salvas.

A retomada preserva direção e síntese. Se houver queda durante busca/montagem, essas etapas podem ser refeitas, reaproveitando caches existentes. Áudios só são reutilizados com recibo válido; resultados inválidos são gerados novamente. Após reinício inesperado, jobs `running` voltam ao pipeline sob o mesmo bloqueio exclusivo.

## Produção recuperada em 27/10/2026

`bermudas_1793101514`: 12 de 14 cenas, voz Fenrir, 66,65 s de áudio parcial. Os arquivos existentes foram decodificados e receberam recibos correspondentes ao roteiro e kit salvos. Agendada para 28/10/2026 às 08:48 (Brasília). Pacote em `entrega_parcial/`: MP3 contínuo, 12 MP3s por cena e roteiro. Não há vídeo parcial, pois a busca de imagens ainda não ocorreu.

Validação: 14 testes de retomada/cota, incluindo relógio simulado, bloqueio concorrente, mudança de roteiro, corrupção de áudio, cancelamento e retomada somente da voz ausente; AppTest da tela sem exceções. Não houve espera real de 24 horas nem nova chamada paga na validação.
