#!/usr/bin/env bash
# InventAI/o — Recarga la bodega de una base que ya tiene datos, sin perder sus usuarios (INV-82).
#
# restaurar.sh se niega si dw tiene filas. Esto es lo que se usa en su lugar cuando la bodega cambia (por ejemplo, el
# ETL de INV-82 con la venta sin IVA) y el staging debe seguir con sus cuentas, sus claves y la cuenta de humo:
# 1. Comprueba la suma SHA-256 del volcado y aplica migrar.sh (el esquema lo crea init.sql, nunca el volcado).
# 2. Respalda la base actual, dw y app, en una carpeta hermana con el formato de volcar.sh (respaldo-AAAAMMDD-HHMMSS-pid,
#    con su huella): para volver atrás, `recargar.sh <esa carpeta>`.
# 3. En una sola transacción: vacía dw y app, restaura los datos del volcado y repone app. Si la carpeta trae app.dump
#    (volcar.sh con INCLUIR_APP=1, o un respaldo), repone ese; si no, el de la base actual. En el segundo caso, antes de
#    confirmar comprueba que cada usuario siga en la misma sucursal (los id de dw.dim_sucursal no cambiaron). Si algo
#    falla, la transacción se deshace y la base queda como estaba.
# Después se valida con validar.sh, como una restauración. Sale con 0 si recargó y con 2 si hubo un error.
#   bash scripts/bd/recargar.sh CARPETA
set -euo pipefail
source "$(dirname "$0")/comun.sh"

[[ $# -eq 1 && -f "$1/dw.dump" && -f "$1/huella.txt" ]] || fallar "uso: recargar.sh CARPETA (la que dejó volcar.sh)"
CARPETA=$(cd "$1" && pwd)
(cd "$CARPETA" && sha256sum --quiet -c dw.dump.sha256) || fallar "el volcado no coincide con su suma SHA-256"
if [[ -f "$CARPETA/app.dump" ]]; then
    (cd "$CARPETA" && sha256sum --quiet -c app.dump.sha256) || fallar "app.dump no coincide con su suma SHA-256"
fi

exigir_conexion
"$RAIZ/scripts/bd/migrar.sh" >/dev/null

RESPALDO=$(dirname "$CARPETA")/respaldo-$(date +%Y%m%d-%H%M%S)-$$
mkdir "$RESPALDO" || fallar "no se pudo crear la carpeta del respaldo $RESPALDO"
inicio=$(date +%s)
for esquema in dw app; do
    pg_en "$RESPALDO" pg_dump -Fc --no-owner --no-privileges -n "$esquema" -f "/volcado/$esquema.dump" \
        || fallar "no se pudo respaldar $esquema; la base no se tocó"
done
(cd "$RESPALDO" && sha256sum dw.dump > dw.dump.sha256 && sha256sum app.dump > app.dump.sha256)
huella "$RESPALDO/huella.txt"
echo "Respaldo de la base actual en $RESPALDO ($(( $(date +%s) - inicio )) s); para volver: recargar.sh con esa carpeta"

# La carga va en una carpeta aparte, con el volcado, el app que se repone y las dos partes de SQL propias
CARGA=$(mktemp -d)
trap 'rm -rf "$CARGA"' EXIT
cp "$CARPETA/dw.dump" "$CARGA/dw.dump"
if [[ -f "$CARPETA/app.dump" ]]; then
    cp "$CARPETA/app.dump" "$CARGA/app.dump"
    origen_app="el de la carpeta"
else
    cp "$RESPALDO/app.dump" "$CARGA/app.dump"
    origen_app="el de la base actual"
fi

cat > "$CARGA/antes.sql" <<'SQL'
BEGIN;
CREATE TEMP TABLE sucursales_antes AS SELECT id_sucursal, codigo_tienda FROM dw.dim_sucursal;
-- Un solo TRUNCATE con todas las tablas de dw y app: las llaves entre ellas no piden CASCADE. Si otra tabla fuera de
-- estos esquemas apuntara a una de ellas, falla y no se vacía nada
DO $$
DECLARE
    tablas text;
BEGIN
    SELECT string_agg(format('%I.%I', n.nspname, c.relname), ', ') INTO tablas
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname IN ('dw', 'app') AND c.relkind = 'r';
    EXECUTE 'TRUNCATE TABLE ' || tablas;
END
$$;
SQL
if [[ ! -f "$CARPETA/app.dump" ]]; then
    cat > "$CARGA/despues.sql" <<'SQL'
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM app.usuarios u
        JOIN pg_temp.sucursales_antes a ON a.id_sucursal = u.id_sucursal
        LEFT JOIN dw.dim_sucursal d ON d.id_sucursal = u.id_sucursal
        WHERE d.codigo_tienda IS DISTINCT FROM a.codigo_tienda
    ) THEN
        RAISE EXCEPTION 'Un usuario quedaría en otra sucursal: los id de dw.dim_sucursal del volcado no son los de la base';
    END IF;
END
$$;
SQL
else
    : > "$CARGA/despues.sql"
fi

inicio=$(date +%s)
# pg_restore escribe el SQL de los datos (COPY y setval de las secuencias) y psql lo aplica entre el BEGIN de antes.sql
# y un COMMIT que solo se escribe si los dos pg_restore terminaron: si uno falla, psql llega al final sin COMMIT y la
# transacción se deshace al cerrar la sesión. Con pipefail, ese fallo también sale del comando
pg_en "$CARGA" sh -c 'set -eo pipefail
    { cat /volcado/antes.sql
      pg_restore --data-only --no-owner --no-privileges -n dw -f - /volcado/dw.dump || exit 1
      pg_restore --data-only --no-owner --no-privileges -n app -f - /volcado/app.dump || exit 1
      cat /volcado/despues.sql
      echo "COMMIT;"; } | psql -X -q -v ON_ERROR_STOP=1 -f -' \
    || fallar "la recarga no terminó; la transacción se deshizo y la base quedó como estaba (respaldo en $RESPALDO)"
echo "Bodega recargada en ${PGDATABASE} en $(( $(date +%s) - inicio )) s, con los usuarios de app de $origen_app"
