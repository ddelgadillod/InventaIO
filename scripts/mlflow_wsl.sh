#!/bin/bash
# ============================================================
# InventAI/o — Servidor MLflow local en WSL (INV-31, trazabilidad del agente)
# Registra las corridas del arnés del agente (conjuntos v0 y v1 y lo que siga).
# Solo en 127.0.0.1: los runs del modo real guardan respuestas con datos reales
# (D22, N9), así que el servidor no se expone a ninguna red ni a servicios externos.
# Base en SQLite y artefactos en ~/.local/mlflow (fuera del repositorio).
# Requiere mlflow en el entorno local: pip install -r nlp_agent/requirements-evaluacion.txt
# Uso: bash scripts/mlflow_wsl.sh [iniciar|detener|estado]
# Los runs se registran con MLFLOW_TRACKING_URI=http://127.0.0.1:5000 (docs/NLP-AGENT.md).
# ============================================================
set -euo pipefail

MLFLOW_DIR="${MLFLOW_DIR:-$HOME/.local/mlflow}"
PYTHON="${PYTHON:-$HOME/venvs/inventaio/bin/python}"
LOG="$MLFLOW_DIR/servidor.log"
PUERTO="${MLFLOW_PUERTO:-5000}"
PATRON="mlflow server --host 127.0.0.1 --port $PUERTO"
export MLFLOW_DISABLE_AGENT_HINT=1

vivo() { curl -s -m 3 "http://127.0.0.1:$PUERTO/health" >/dev/null; }
proceso() { pgrep -f "$PATRON" >/dev/null; }

case "${1:-estado}" in
  iniciar)
    if vivo; then echo "MLflow ya está corriendo en http://127.0.0.1:$PUERTO"; exit 0; fi
    "$PYTHON" -c "import mlflow" 2>/dev/null || { echo "Falta mlflow: pip install -r nlp_agent/requirements-evaluacion.txt"; exit 1; }
    mkdir -p "$MLFLOW_DIR/artefactos"
    # --serve-artifacts: los clientes suben los artefactos por HTTP, sin ver la carpeta
    nohup "$PYTHON" -m mlflow server --host 127.0.0.1 --port "$PUERTO" \
      --backend-store-uri "sqlite:///$MLFLOW_DIR/mlflow.db" \
      --artifacts-destination "$MLFLOW_DIR/artefactos" --serve-artifacts --workers 1 >>"$LOG" 2>&1 &
    for _ in $(seq 1 60); do vivo && break; sleep 1; done
    vivo || { echo "MLflow no respondió en 60 s; revisar $LOG"; exit 1; }
    echo "MLflow $("$PYTHON" -c 'import mlflow; print(mlflow.__version__)') en http://127.0.0.1:$PUERTO (datos: $MLFLOW_DIR; registro: $LOG)"
    ;;
  detener)
    if ! proceso; then echo "MLflow no estaba corriendo"; exit 0; fi
    pkill -f "$PATRON"
    for _ in $(seq 1 20); do proceso || break; sleep 1; done
    if proceso; then pkill -9 -f "$PATRON"; sleep 1; fi
    echo "MLflow detenido"
    ;;
  estado)
    if vivo; then echo "MLflow corriendo en http://127.0.0.1:$PUERTO (datos: $MLFLOW_DIR)"; else echo "MLflow detenido"; fi
    ;;
  *)
    echo "Uso: $0 [iniciar|detener|estado]"; exit 2
    ;;
esac
