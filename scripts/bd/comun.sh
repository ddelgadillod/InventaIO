# InventAI/o — Funciones comunes de los scripts de la base (INV-34). Se carga con `source`.
#
# psql, pg_dump y pg_restore corren dentro de postgres:16-alpine, la misma versión
# mayor de la base, así que no hace falta instalarlos (B7 de docs/INV-34-requerimientos.md).
# La conexión va por las variables estándar PGHOST, PGPORT, PGUSER, PGPASSWORD y
# PGDATABASE, que pasan al contenedor como entorno: la clave nunca queda en la línea
# de comandos. BD_RED dice a qué red se une el contenedor:
#   container:<nombre o id>  el de la base (local: container:inventaio-db, con PGHOST=localhost)
#   host                     el CI, con la base como servicio en localhost
#   (vacía)                  una base con nombre en la red, como RDS

RAIZ=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
IMAGEN_PG=${IMAGEN_PG:-postgres:16-alpine}
# Sin los NOTICE de «already exists, skipping» que init.sql da en cada pasada
export PGOPTIONS=${PGOPTIONS:--c client_min_messages=warning}

# pg <herramienta> [argumentos...]: la entrada estándar llega a la herramienta
pg() {
    local red=()
    [[ -n "${BD_RED:-}" ]] && red=(--network "$BD_RED")
    docker run --rm -i "${red[@]}" \
        -e PGHOST -e PGPORT -e PGUSER -e PGPASSWORD -e PGDATABASE -e PGOPTIONS \
        "$IMAGEN_PG" "$@"
}

# pg_en <carpeta> <herramienta> [argumentos...]: como pg, con la carpeta montada en
# /volcado y el usuario actual, para que los archivos no queden de root. pg_dump y
# pg_restore leen y escriben archivos y no tuberías: con una tubería, el volcado no
# guarda dónde empieza cada tabla y pg_restore no puede reordenarlas
pg_en() {
    local carpeta=$1 red=()
    shift
    [[ -n "${BD_RED:-}" ]] && red=(--network "$BD_RED")
    docker run --rm -i "${red[@]}" --user "$(id -u):$(id -g)" -v "$carpeta":/volcado \
        -e PGHOST -e PGPORT -e PGUSER -e PGPASSWORD -e PGDATABASE -e PGOPTIONS \
        "$IMAGEN_PG" "$@"
}

# psql sin ~/.psqlrc, que se detiene en el primer error
pg_sql() {
    pg psql -X -q -v ON_ERROR_STOP=1 "$@"
}

fallar() {
    echo "ERROR: $*" >&2
    exit 2
}

# Comprueba que haya conexión antes de empezar, con un mensaje que no muestra la clave
exigir_conexion() {
    [[ -n "${PGDATABASE:-}" ]] || fallar "falta PGDATABASE (y PGHOST, PGUSER, PGPASSWORD; ver database/README.md)"
    pg_sql -A -t -c 'SELECT 1' >/dev/null || fallar "no hay conexión con la base ${PGDATABASE} en ${PGHOST:-?}"
}

# huella <archivo> [detalle]: escribe la huella de la base actual (sección 5 de los
# requerimientos). Con «detalle», los valores en lugar del md5; ese archivo no se sube
huella() {
    local salida=$1 detalle=0 informe
    [[ "${2:-}" == detalle ]] && detalle=1
    pg_sql -A -t -F '|' -v detalle="$detalle" -f - < "$RAIZ/scripts/bd/huella.sql" > "$salida" \
        || fallar "no se pudo sacar la huella de ${PGDATABASE}"
    # H10: el informe de test-dw-real.SQL sin las líneas de tiempo. Sin ON_ERROR_STOP: un
    # error del informe también es parte de la huella y debe repetirse igual en el destino
    informe=$(pg psql -X -f - < "$RAIZ/database/test-dw-real.SQL" 2>&1 | grep -v '^Time: ') \
        || fallar "no se pudo correr test-dw-real.SQL en ${PGDATABASE}"
    if [[ $detalle == 1 ]]; then
        printf 'H10 informe test-dw-real|\n%s\n' "$informe" >> "$salida"
    else
        printf 'H10 informe test-dw-real|%s\n' "$(printf '%s' "$informe" | md5sum | cut -d' ' -f1)" >> "$salida"
    fi
}
