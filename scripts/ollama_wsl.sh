#!/bin/bash
# ============================================================
# InventAI/o — Ollama nativo en WSL (INV-30, decisiones N6, W1 y W2)
# Arranca, detiene o revisa Ollama instalado sin sudo en ~/.local/ollama.
# Escucha solo en 127.0.0.1: WSL reenvía ese puerto al 127.0.0.1 de Windows, que es
# adonde Docker Desktop manda host.docker.internal, y así los contenedores lo
# alcanzan sin exponerlo a ninguna red. Con 0.0.0.0, Ollama escucha en [::] y WSL
# solo lo reenvía por ::1, que Docker no usa (medido el 16-oct).
# Uso: bash scripts/ollama_wsl.sh [iniciar|detener|estado]
# ============================================================
set -euo pipefail

OLLAMA_DIR="${OLLAMA_DIR:-$HOME/.local/ollama}"
BIN="$OLLAMA_DIR/bin/ollama"
LOG="$OLLAMA_DIR/serve.log"
PUERTO=11434

export OLLAMA_HOST="127.0.0.1:$PUERTO"
export OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-1}"            # un modelo local atiende una petición a la vez
export OLLAMA_MAX_LOADED_MODELS="${OLLAMA_MAX_LOADED_MODELS:-1}"  # 8 GB de VRAM: un modelo cargado a la vez
export OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:-30m}"
export OLLAMA_NO_CLOUD=1                                          # D22: sin los modelos «cloud» de Ollama, que corren en servidores externos

vivo() { curl -s -m 3 "http://localhost:$PUERTO/api/version" >/dev/null; }
proceso() { pgrep -f "$BIN serve" >/dev/null; }

case "${1:-estado}" in
  iniciar)
    # Si se está cerrando (un `detener` reciente, que descarga el modelo de la GPU),
    # esperar a que termine: si no, parece vivo y después no queda ninguno
    for _ in $(seq 1 20); do proceso && ! vivo || break; sleep 1; done
    if vivo; then echo "Ollama ya está corriendo"; exit 0; fi
    [ -x "$BIN" ] || { echo "No está $BIN: ver docs/NLP-AGENT.md (instalación)"; exit 1; }
    nohup "$BIN" serve >>"$LOG" 2>&1 &
    for _ in $(seq 1 30); do vivo && break; sleep 1; done
    vivo || { echo "Ollama no respondió en 30 s; revisar $LOG"; exit 1; }
    echo "Ollama $(curl -s "http://localhost:$PUERTO/api/version" | sed 's/.*"version":"\([^"]*\)".*/\1/') en el puerto $PUERTO (registro: $LOG)"
    grep -E "inference compute|library=" "$LOG" | tail -2 || true
    ;;
  detener)
    if ! proceso; then echo "Ollama no estaba corriendo"; exit 0; fi
    pkill -f "$BIN serve"
    # Esperar a que termine de verdad (libera la VRAM y el puerto); a los 20 s, forzar
    for _ in $(seq 1 20); do proceso || break; sleep 1; done
    if proceso; then pkill -9 -f "$BIN serve"; sleep 1; fi
    echo "Ollama detenido"
    ;;
  estado)
    if vivo; then
      echo "Ollama corriendo en el puerto $PUERTO"
      "$BIN" list
      "$BIN" ps
    else
      echo "Ollama detenido"
    fi
    ;;
  *)
    echo "Uso: $0 [iniciar|detener|estado]"; exit 2
    ;;
esac
