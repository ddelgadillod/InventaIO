#!/usr/bin/env bash
# InventAI/o — Vuelca la bodega (esquema dw) y saca su huella (INV-34, B5 y B10).
#
# Deja en la carpeta (por defecto ~/inventaio-volcados/AAAAMMDD-HHMM):
#   dw.dump             el volcado, en formato comprimido de pg_dump
#   dw.dump.sha256      su suma, para comprobarlo antes de restaurar
#   huella.txt          la huella del origen (scripts/bd/huella.sql), lo que se compara
#   huella-detalle.txt  los valores de cada comprobación: se queda aquí, no se sube
# Solo viaja dw: app (usuarios) la crea init.sql en el destino y los usuarios se crean
# allá con seed_usuarios --nube. Imprime la ruta de la carpeta.
#   bash scripts/bd/volcar.sh [CARPETA]
set -euo pipefail
source "$(dirname "$0")/comun.sh"

CARPETA=${1:-$HOME/inventaio-volcados/$(date +%Y%m%d-%H%M)}
if [[ -e "$CARPETA" && -n "$(ls -A "$CARPETA" 2>/dev/null)" ]]; then
    fallar "la carpeta $CARPETA ya existe y no está vacía"
fi
mkdir -p "$CARPETA"
CARPETA=$(cd "$CARPETA" && pwd)

exigir_conexion
pg_en "$CARPETA" pg_dump -Fc --no-owner --no-privileges -n dw -f /volcado/dw.dump \
    || fallar "pg_dump no terminó"
(cd "$CARPETA" && sha256sum dw.dump > dw.dump.sha256)
huella "$CARPETA/huella.txt"
huella "$CARPETA/huella-detalle.txt" detalle
echo "$CARPETA"
