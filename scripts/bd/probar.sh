#!/usr/bin/env bash
# InventAI/o — Prueba el mecanismo de migración de la base, de punta a punta (INV-34, B12).
#
#   bash scripts/bd/probar.sh                     con datos sintéticos (lo que corre el CI)
#   bash scripts/bd/probar.sh --origen inventaio  con la bodega real de esa base, en local
#
# Con datos sintéticos crea una base de origen temporal, le aplica init.sql dos veces
# (el esquema no debe cambiar) y carga database/datos-sinteticos.sql. Con --origen, el
# origen es esa base y solo se lee. Después, en una base de destino temporal:
#   volcar, restaurar y validar         debe pasar
#   migrar sobre los datos y validar    debe seguir pasando
#   restaurar otra vez                  debe negarse (código 3)
#   alterar una fila y validar          debe fallar (código 1)
# Al terminar borra las bases y el volcado temporales. Imprime solo resultados y
# tiempos, nunca valores de la bodega. La conexión va por las variables PG* y BD_RED
# (scripts/bd/comun.sh); el usuario debe poder crear bases.
set -euo pipefail
source "$(dirname "$0")/comun.sh"

ORIGEN_REAL=""
if [[ "${1:-}" == --origen ]]; then
    ORIGEN_REAL=${2:?falta el nombre de la base de origen}
fi
SUFIJO=$$
ORIGEN=${ORIGEN_REAL:-bd_prueba_origen_$SUFIJO}
DESTINO=bd_prueba_destino_$SUFIJO
ADMIN=${BD_ADMIN:-postgres}   # la base desde la que se crean y borran las temporales
TMP=$(mktemp -d)

en() {   # en <base> <comando...>: corre el comando con PGDATABASE=<base>
    local base=$1
    shift
    PGDATABASE=$base "$@"
}
crear_base() { en "$ADMIN" pg_sql -c "CREATE DATABASE $1"; }
borrar_base() { en "$ADMIN" pg_sql -c "DROP DATABASE IF EXISTS $1" || true; }
limpiar() {
    borrar_base "$DESTINO"
    [[ -n "$ORIGEN_REAL" ]] || borrar_base "$ORIGEN"
    rm -rf "$TMP"
}
trap limpiar EXIT

# paso <código esperado> <descripción> <comando...>
paso() {
    local esperado=$1 descripcion=$2 inicio codigo
    shift 2
    inicio=$(date +%s)
    set +e
    "$@" > "$TMP/salida.txt" 2>&1
    codigo=$?
    set -e
    if [[ $codigo -ne $esperado ]]; then
        echo "FALLA $descripcion: salió con $codigo y se esperaba $esperado"
        sed 's/^/      /' "$TMP/salida.txt"
        exit 1
    fi
    echo "ok    $descripcion ($(( $(date +%s) - inicio )) s)"
}

esquema() {   # el esquema de dw y app, sin las líneas \restrict, que cambian en cada volcado
    en "$1" pg pg_dump --schema-only --no-owner --no-privileges -n dw -n app | grep -v '^\\\(un\)\?restrict '
}

if [[ -z "$ORIGEN_REAL" ]]; then
    crear_base "$ORIGEN" >/dev/null
    paso 0 "init.sql desde cero" en "$ORIGEN" bash "$RAIZ/scripts/bd/migrar.sh"
    esquema "$ORIGEN" > "$TMP/esquema-1.sql"
    paso 0 "init.sql otra vez encima" en "$ORIGEN" bash "$RAIZ/scripts/bd/migrar.sh"
    esquema "$ORIGEN" > "$TMP/esquema-2.sql"
    paso 0 "el esquema no cambió con la segunda pasada" diff -q "$TMP/esquema-1.sql" "$TMP/esquema-2.sql"
    paso 0 "datos sintéticos cargados" en "$ORIGEN" pg_sql -f - < "$RAIZ/database/datos-sinteticos.sql"
fi

paso 0 "volcado de dw y huella del origen" en "$ORIGEN" bash "$RAIZ/scripts/bd/volcar.sh" "$TMP/volcado"
echo "      volcado: $(du -h "$TMP/volcado/dw.dump" | cut -f1)"
crear_base "$DESTINO" >/dev/null
paso 0 "restauración en una base nueva" en "$DESTINO" bash "$RAIZ/scripts/bd/restaurar.sh" "$TMP/volcado"
paso 0 "validación del destino" en "$DESTINO" bash "$RAIZ/scripts/bd/validar.sh" "$TMP/volcado"
sed 's/^/      /' "$TMP/salida.txt"
paso 0 "init.sql sobre la base con datos" en "$DESTINO" bash "$RAIZ/scripts/bd/migrar.sh"
paso 0 "validación después de migrar" en "$DESTINO" bash "$RAIZ/scripts/bd/validar.sh" "$TMP/volcado"
paso 3 "restaurar sobre una base con filas se niega" en "$DESTINO" bash "$RAIZ/scripts/bd/restaurar.sh" "$TMP/volcado"
paso 0 "una fila alterada en el destino" en "$DESTINO" pg_sql -c \
    "UPDATE dw.fact_ventas SET cantidad = cantidad + 1 WHERE id = (SELECT min(id) FROM dw.fact_ventas)"
paso 1 "la validación detecta la fila alterada" en "$DESTINO" bash "$RAIZ/scripts/bd/validar.sh" "$TMP/volcado"
sed 's/^/      /' "$TMP/salida.txt" | grep -v 'detalle está en'
echo "Mecanismo de migración probado"
