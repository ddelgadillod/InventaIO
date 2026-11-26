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
#   con datos sintéticos, también app   el usuario de prueba llega igual (INCLUIR_APP=1)
#   alterar una fila y validar          debe fallar (código 1)
#   recargar sobre la base con datos    se niega si un usuario cambiaría de sucursal, sin tocar nada (código 2);
#                                       si no, reemplaza la bodega, conserva los usuarios y su respaldo vuelve atrás
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
    # Un usuario de prueba, para que también viaje app (INCLUIR_APP=1, como el traslado entre staging)
    paso 0 "usuario sintético en app" en "$ORIGEN" pg_sql -c \
        "INSERT INTO app.usuarios (email, password_hash, nombre, rol) VALUES ('prueba@ejemplo.com', 'sin-clave', 'Prueba', 'gerente')"
    export INCLUIR_APP=1
fi

paso 0 "volcado de dw y huella del origen" en "$ORIGEN" bash "$RAIZ/scripts/bd/volcar.sh" "$TMP/volcado"
echo "      volcado: $(du -h "$TMP/volcado/dw.dump" | cut -f1)"
crear_base "$DESTINO" >/dev/null
paso 0 "restauración en una base nueva" en "$DESTINO" bash "$RAIZ/scripts/bd/restaurar.sh" "$TMP/volcado"
paso 0 "validación del destino" en "$DESTINO" bash "$RAIZ/scripts/bd/validar.sh" "$TMP/volcado"
sed 's/^/      /' "$TMP/salida.txt"
usuarios() {
    en "$1" pg_sql -A -t -c "SELECT count(*) || ' ' || string_agg(email || ':' || password_hash || ':' || coalesce(id_sucursal::text, '-'), ',' ORDER BY email) FROM app.usuarios"
}
if [[ ${INCLUIR_APP:-0} == 1 ]]; then
    paso 0 "los usuarios de app llegaron iguales" test "$(usuarios "$ORIGEN")" = "$(usuarios "$DESTINO")"
fi
paso 0 "init.sql sobre la base con datos" en "$DESTINO" bash "$RAIZ/scripts/bd/migrar.sh"
paso 0 "validación después de migrar" en "$DESTINO" bash "$RAIZ/scripts/bd/validar.sh" "$TMP/volcado"
paso 3 "restaurar sobre una base con filas se niega" en "$DESTINO" bash "$RAIZ/scripts/bd/restaurar.sh" "$TMP/volcado"
paso 0 "una fila alterada en el destino" en "$DESTINO" pg_sql -c \
    "UPDATE dw.fact_ventas SET cantidad = cantidad + 1 WHERE id = (SELECT min(id) FROM dw.fact_ventas)"
paso 1 "la validación detecta la fila alterada" en "$DESTINO" bash "$RAIZ/scripts/bd/validar.sh" "$TMP/volcado"
sed 's/^/      /' "$TMP/salida.txt" | grep -v 'detalle está en'

# Recarga sobre una base con datos (recargar.sh, INV-82): con un volcado solo de dw, como el que sube volcar.sh
mkdir "$TMP/solo-dw"
cp "$TMP/volcado/dw.dump" "$TMP/volcado/dw.dump.sha256" "$TMP/volcado/huella.txt" "$TMP/solo-dw/"
foto() {   # los datos de dw y app del destino, sin las líneas \restrict
    en "$DESTINO" pg pg_dump --data-only --no-owner --no-privileges -n dw -n app | grep -v '^\\\(un\)\?restrict ' | md5sum
}
paso 0 "un usuario con sucursal en el destino" en "$DESTINO" pg_sql -c \
    "INSERT INTO app.usuarios (email, password_hash, nombre, rol, id_sucursal)
     SELECT 'staging@ejemplo.com', 'otra-clave', 'Staging', 'admin_sucursal', min(id_sucursal) FROM dw.dim_sucursal"
paso 0 "su sucursal cambia de código en el destino" en "$DESTINO" pg_sql -c \
    "UPDATE dw.dim_sucursal SET codigo_tienda = codigo_tienda + 1000
     WHERE id_sucursal = (SELECT id_sucursal FROM app.usuarios WHERE email = 'staging@ejemplo.com')"
antes=$(foto)
paso 2 "recargar se niega si un usuario quedaría en otra sucursal" \
    en "$DESTINO" bash "$RAIZ/scripts/bd/recargar.sh" "$TMP/solo-dw"
motivo=$(cat "$TMP/salida.txt")
paso 0 "la negativa es por esa sucursal" grep -q "quedaría en otra sucursal" <<< "$motivo"
paso 0 "la base quedó como estaba" test "$antes" = "$(foto)"
# Un app.dump que pg_restore no puede leer: el COMMIT no llega y la transacción se deshace con dw ya vaciada
mkdir "$TMP/roto"
cp "$TMP/solo-dw"/* "$TMP/roto/"
echo "no es un volcado" > "$TMP/roto/app.dump"
(cd "$TMP/roto" && sha256sum app.dump > app.dump.sha256)
paso 2 "recargar con un volcado que falla a mitad" en "$DESTINO" bash "$RAIZ/scripts/bd/recargar.sh" "$TMP/roto"
paso 0 "la base quedó como estaba otra vez" test "$antes" = "$(foto)"
paso 0 "la sucursal vuelve a su código" en "$DESTINO" pg_sql -c \
    "UPDATE dw.dim_sucursal SET codigo_tienda = codigo_tienda - 1000
     WHERE id_sucursal = (SELECT id_sucursal FROM app.usuarios WHERE email = 'staging@ejemplo.com')"
usuarios_antes=$(usuarios "$DESTINO")
paso 0 "recargar la bodega sobre la base con datos" en "$DESTINO" bash "$RAIZ/scripts/bd/recargar.sh" "$TMP/solo-dw"
respaldo=$(sed -n 's/^Respaldo de la base actual en \(.*\) ([0-9]* s).*/\1/p' "$TMP/salida.txt")
paso 0 "validación después de recargar: la fila alterada volvió" \
    en "$DESTINO" bash "$RAIZ/scripts/bd/validar.sh" "$TMP/volcado"
paso 0 "los usuarios del destino siguen iguales" test "$usuarios_antes" = "$(usuarios "$DESTINO")"
paso 0 "recargar con el respaldo vuelve a la base anterior" \
    en "$DESTINO" bash "$RAIZ/scripts/bd/recargar.sh" "$respaldo"
paso 1 "la validación ve otra vez la fila alterada" en "$DESTINO" bash "$RAIZ/scripts/bd/validar.sh" "$TMP/volcado"
paso 0 "y los usuarios siguen iguales" test "$usuarios_antes" = "$(usuarios "$DESTINO")"
echo "Mecanismo de migración probado"
