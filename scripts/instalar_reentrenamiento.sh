#!/usr/bin/env bash
# InventAI/o — Instala el temporizador semanal del reentrenamiento (INV-62) como unidad de systemd de usuario.
#   bash scripts/instalar_reentrenamiento.sh RUTA_DW      instala o actualiza y habilita el temporizador
#   bash scripts/instalar_reentrenamiento.sh --quitar     lo deshabilita y borra las unidades
# Las unidades apuntan al repositorio desde el que se corre este script. La configuración queda en
# ~/.config/inventaio/reentrenamiento.env y no se sobrescribe si ya existe.
set -euo pipefail
RAIZ=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
UNIDADES="$HOME/.config/systemd/user"
CONFIG="$HOME/.config/inventaio/reentrenamiento.env"

if [[ "${1:-}" == "--quitar" ]]; then
  systemctl --user disable --now inventaio-reentrenamiento.timer 2>/dev/null || true
  rm -f "$UNIDADES/inventaio-reentrenamiento.service" "$UNIDADES/inventaio-reentrenamiento.timer"
  systemctl --user daemon-reload
  echo "Temporizador del reentrenamiento quitado (la configuración $CONFIG se conserva)"
  exit 0
fi

DW="${1:?uso: bash scripts/instalar_reentrenamiento.sh RUTA_DW}"
[[ -f "$DW/fact_ventas.csv" ]] || { echo "No hay fact_ventas.csv en $DW"; exit 1; }
mkdir -p "$UNIDADES" "$(dirname "$CONFIG")"
for u in service timer; do
  sed "s|@REPO@|$RAIZ|g" "$RAIZ/despliegue/systemd/inventaio-reentrenamiento.$u" > "$UNIDADES/inventaio-reentrenamiento.$u"
done
if [[ ! -f "$CONFIG" ]]; then
  printf 'REENTRENAMIENTO_DW=%s\nREENTRENAMIENTO_REPO=%s\nREENTRENAMIENTO_BASE=develop\n' "$(cd "$DW" && pwd)" "$RAIZ" > "$CONFIG"
fi
systemctl --user daemon-reload
systemctl --user enable --now inventaio-reentrenamiento.timer
systemctl --user list-timers inventaio-reentrenamiento.timer --no-pager
echo "Configuración: $CONFIG · registros: ~/.local/state/inventaio/reentrenamiento · journal: journalctl --user -u inventaio-reentrenamiento"
