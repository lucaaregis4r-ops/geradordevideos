#!/usr/bin/env bash
# ==============================================================================
# Fábrica de Shorts e Bermudas — Inicializador do Programa no Navegador
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

mkdir -p "$DIR/storage"

URL="http://localhost:8501"

abrir_navegador() {
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$URL" >/dev/null 2>&1 &
    elif command -v google-chrome >/dev/null 2>&1; then
        google-chrome "$URL" >/dev/null 2>&1 &
    elif command -v firefox >/dev/null 2>&1; then
        firefox "$URL" >/dev/null 2>&1 &
    fi
}

# Se o servidor já estiver em execução, apenas abre uma nova aba no navegador
if curl -s --head "$URL" >/dev/null 2>&1; then
    abrir_navegador
    exit 0
fi

# Abre o navegador automaticamente assim que o servidor responder
(
    for i in {1..30}; do
        if curl -s --head "$URL" >/dev/null 2>&1; then
            abrir_navegador
            exit 0
        fi
        sleep 0.5
    done
    abrir_navegador
) &

# Inicia o servidor Streamlit
exec "$DIR/.venv/bin/streamlit" run "$DIR/webui/Main.py" \
    --server.port 8501 \
    --server.headless true \
    --browser.gatherUsageStats false
