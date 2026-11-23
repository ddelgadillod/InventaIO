#!/usr/bin/env bash
# InventAI/o — Paso de migración: aplica database/init.sql (INV-34, B1).
#
# init.sql es idempotente: crea lo que falta y no toca lo que existe, así que se corre
# en cada despliegue, sobre una base vacía o con datos. El job base-de-datos del CI
# prueba que siga siéndolo. La conexión va por las variables PG* y BD_RED
# (scripts/bd/comun.sh). Sale con 0 si aplicó y con 2 si hubo un error.
#   bash scripts/bd/migrar.sh
set -euo pipefail
source "$(dirname "$0")/comun.sh"

exigir_conexion
pg_sql -f - < "$RAIZ/database/init.sql" || fallar "init.sql no se aplicó en ${PGDATABASE}"
echo "Esquema al día en ${PGDATABASE}"
