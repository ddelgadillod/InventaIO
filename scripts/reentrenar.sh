#!/usr/bin/env bash
# InventAI/o — Reentrenamiento programado de los modelos de pronóstico (INV-62). Lo dispara el temporizador de
# systemd de usuario (scripts/instalar_reentrenamiento.sh); también se puede correr a mano.
#
# Configuración en ~/.config/inventaio/reentrenamiento.env (la crea el instalador):
#   REENTRENAMIENTO_DW     carpeta del DW en CSV con los datos al día (salida del ETL)
#   REENTRENAMIENTO_REPO   repositorio con los modelos vigentes en models/ (por defecto, el de este script)
#   REENTRENAMIENTO_BASE   rama desde la que se crea la rama del candidato (por defecto develop)
#   PYTHON                 intérprete con lightgbm y mlflow (por defecto ~/venvs/inventaio/bin/python)
# Arranca MLflow si no corre. Sale con el código del reentrenamiento: 0 (sin datos nuevos, rechazado o promovible),
# 1 (error) o 2 (MLflow no responde); con 1 o 2 la unidad de systemd queda en «failed».
set -euo pipefail

CONFIG="${REENTRENAMIENTO_CONFIG:-$HOME/.config/inventaio/reentrenamiento.env}"
# shellcheck disable=SC1090
[[ -f "$CONFIG" ]] && source "$CONFIG"
RAIZ=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPO="${REENTRENAMIENTO_REPO:-$RAIZ}"
BASE="${REENTRENAMIENTO_BASE:-develop}"
PYTHON="${PYTHON:-$HOME/venvs/inventaio/bin/python}"
REGISTROS="${REENTRENAMIENTO_REGISTROS:-$HOME/.local/state/inventaio/reentrenamiento}"
: "${REENTRENAMIENTO_DW:?falta REENTRENAMIENTO_DW en $CONFIG}"
export MLFLOW_TRACKING_URI="${MLFLOW_TRACKING_URI:-http://127.0.0.1:5000}" MLFLOW_DISABLE_AGENT_HINT=1 PYTHONUNBUFFERED=1

mkdir -p "$REGISTROS"
REGISTRO="$REGISTROS/$(date +%Y%m%d-%H%M).log"
{ ls -1t "$REGISTROS"/*.log 2>/dev/null || true; } | tail -n +13 | xargs -r rm --      # se conservan los 12 últimos registros

{
  echo "== reentrenamiento $(date -Is) · repo $REPO · DW $REENTRENAMIENTO_DW"
  bash "$RAIZ/scripts/mlflow_wsl.sh" iniciar || echo "MLflow no arrancó: el reentrenamiento fallará de forma visible"
} 2>&1 | tee -a "$REGISTRO"

set +e
"$PYTHON" "$RAIZ/notebooks/reentrenar_nivel1.py" --dw "$REENTRENAMIENTO_DW" --repo "$REPO" --base "$BASE" 2>&1 | tee -a "$REGISTRO"
codigo=${PIPESTATUS[0]}
set -e
echo "== fin $(date -Is) · código $codigo · registro $REGISTRO" | tee -a "$REGISTRO"
exit "$codigo"
