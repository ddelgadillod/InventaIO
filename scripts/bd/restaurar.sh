#!/usr/bin/env bash
# InventAI/o — Restaura un volcado de dw en una base (INV-34, B6).
#
# 1. Comprueba la suma SHA-256 del volcado.
# 2. Aplica migrar.sh: el esquema lo crea init.sql, nunca el volcado.
# 3. Se niega a seguir si alguna tabla de dw tiene filas (sale con 3): recargar
#    staging es recrear la base (docs/INV-34-requerimientos.md, B6).
# 4. Restaura solo los datos, en una sola transacción, sin dueños ni permisos y sin
#    desactivar triggers, para que también sirva con el usuario de RDS.
#   bash scripts/bd/restaurar.sh CARPETA
set -euo pipefail
source "$(dirname "$0")/comun.sh"

[[ $# -eq 1 && -d "$1" ]] || fallar "uso: restaurar.sh CARPETA (la que dejó volcar.sh)"
CARPETA=$(cd "$1" && pwd)
(cd "$CARPETA" && sha256sum --quiet -c dw.dump.sha256) || fallar "el volcado no coincide con su suma SHA-256"

exigir_conexion
"$RAIZ/scripts/bd/migrar.sh" >/dev/null

# Una sola consulta que dice si alguna tabla de dw tiene al menos una fila. psql sale
# con 3 cuando falla un script, así que su error se lleva al 2 para no confundirlo
con_filas=$(pg_sql -A -t <<'SQL'
SELECT 'SELECT ' || coalesce(string_agg(format('EXISTS (SELECT 1 FROM %I.%I)', n.nspname, c.relname), ' OR '), 'false')
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'dw' AND c.relkind = 'r'
\gexec
SQL
) || fallar "no se pudo revisar si dw tiene filas en ${PGDATABASE}"
if [[ "$con_filas" == t ]]; then
    echo "NO SE RESTAURÓ: dw ya tiene filas en ${PGDATABASE}. Para recargar, recrear la base." >&2
    exit 3
fi

inicio=$(date +%s)
pg_en "$CARPETA" pg_restore --data-only --single-transaction --no-owner --no-privileges \
    -n dw -d "$PGDATABASE" /volcado/dw.dump || fallar "pg_restore no terminó; la transacción se deshizo"
echo "Datos de dw restaurados en ${PGDATABASE} en $(( $(date +%s) - inicio )) s"
