#!/usr/bin/env bash
# InventAI/o — La pila de pruebas local: la foto de la bodega al 31-dic-2025 (INV-82 e INV-72).
#
# Las pruebas de integración del Core API, las colecciones de Postman y la regresión de 61 preguntas del agente esperan
# la foto de la configuración por defecto del ETL: ventas 2022-2025 e inventario al 31-dic-2025, con la venta sin IVA
# desde INV-82. La base local de operación (`inventaio`) tiene otra foto (la de data/processed_real), así que la de
# pruebas vive en su propia base y con su propia API y su propio ML Service, sin tocar los de docker compose:
#   construir  corre el ETL por defecto en una carpeta aparte (FOTO) y lo carga en la base BD; no rehace una base que
#              ya tenga la bodega
#   levantar   crea inventaio-ml-dic2025 (127.0.0.1:8013) e inventaio-api-dic2025 (127.0.0.1:8012) con la configuración de los
#              contenedores de compose, que deben estar corriendo, y siembra los usuarios de prueba
#   quitar     borra esos dos contenedores (la base y la carpeta quedan)
#   estado     muestra los contenedores y la salud de la API
# Los montos en pesos esperados no están en el repositorio: se pasan con INVENTAIO_ESPERAS (ver docs/CI-CD.md).
#   bash scripts/bd/pila_pruebas.sh construir|levantar|quitar|estado
set -euo pipefail
RAIZ=$(cd "$(dirname "$0")/../.." && pwd)
FOTO=${FOTO:-$RAIZ/data/processed_real/dic2025_sin_iva}
BD=${BD:-inventaio_dic2025}
PUERTO=${PUERTO:-8012}
PUERTO_ML=${PUERTO_ML:-8013}
RED=${RED:-inventaio_default}
ML=inventaio-ml-dic2025
API=inventaio-api-dic2025
PY=${PY:-$HOME/venvs/inventaio/bin/python}

fallar() { echo "ERROR: $*" >&2; exit 2; }
psql_bd() { docker exec -i inventaio-db psql -U "${POSTGRES_USER:-inventaio_user}" -v ON_ERROR_STOP=1 -qAt "$@"; }

construir() {
    if [[ ! -s $FOTO/fact_ventas.csv ]]; then
        echo "ETL por defecto (foto al 31-dic-2025) en $FOTO"
        mkdir -p "$FOTO"
        (
            cd "$RAIZ/etl_real"
            export ETL_SALIDA_DIR=$FOTO
            for paso in construir_dim_tiempo.py construir_dim_sucursal.py clasificar_productos.py \
                        "construir_dim_producto.py --completo" validar_inventario.py construir_dim_producto.py \
                        simular_proveedores.py construir_dim_evento.py construir_fact_ventas.py \
                        construir_fact_inventario_real.py; do
                echo "  $paso"
                # shellcheck disable=SC2086
                "$PY" $paso >/dev/null
            done
            # El ETL deja la lista de excluidos en etl_real (versionada): la copia va con la foto y el repositorio
            # vuelve a su versión
            cp productos_excluidos.csv "$FOTO/productos_excluidos.csv"
            git -C "$RAIZ" checkout -- etl_real/productos_excluidos.csv
        )
    else
        echo "La foto ya está en $FOTO"
    fi
    if [[ $(psql_bd -d postgres -c "SELECT 1 FROM pg_database WHERE datname = '$BD'") != 1 ]]; then
        psql_bd -d postgres -c "CREATE DATABASE $BD"
    fi
    psql_bd -d "$BD" < "$RAIZ/database/init.sql" 2>&1 | grep -v "already exists" || true
    if [[ $(psql_bd -d "$BD" -c "SELECT COUNT(*) > 0 FROM dw.fact_ventas") == t ]]; then
        echo "La base $BD ya tiene la bodega: no se rehace (para empezar de cero, quitar la pila y borrar la base)"
        return
    fi
    (
        cd "$RAIZ/etl_real"
        set -a && source "$RAIZ/.env" && set +a
        export DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:5432/$BD" ETL_SALIDA_DIR=$FOTO
        "$PY" cargar_postgres.py | tail -5
    )
}

entorno_de() {    # entorno_de <contenedor> <patrón de variables>: las variables de ese contenedor, sin imprimirlas
    docker inspect "$1" --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E "^($2)=" \
        | sed "s/^POSTGRES_DB=.*/POSTGRES_DB=$BD/"
}

levantar() {
    for c in inventaio-db inventaio-api inventaio-ml-service; do
        [[ $(docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null) == true ]] || fallar "$c no está corriendo (docker compose up -d)"
    done
    [[ $(psql_bd -d postgres -c "SELECT 1 FROM pg_database WHERE datname = '$BD'") == 1 ]] || fallar "falta la base $BD: construir primero"
    local tmp
    tmp=$(umask 077 && mktemp -d)
    trap 'rm -rf "$tmp"' RETURN
    { entorno_de inventaio-ml-service "POSTGRES_[A-Z]+|ENTORNO|MODELOS_DIR"; echo "FECHA_OPERACION=2025-12-31"; } > "$tmp/ml.env"
    { entorno_de inventaio-api "POSTGRES_[A-Z]+|ENTORNO|REDIS_[A-Z]+|NLP_AGENT_URL"
      echo "ML_SERVICE_URL=http://$ML:8001"; echo "CACHE_LECTURAS_S=0"; } > "$tmp/api.env"
    docker rm -f "$ML" "$API" >/dev/null 2>&1 || true
    docker run -d --name "$ML" --network "$RED" -p "127.0.0.1:$PUERTO_ML:8001" --env-file "$tmp/ml.env" \
        -v "$RAIZ/models:/app/models:ro" \
        inventaio-ml-service uvicorn main:app --host 0.0.0.0 --port 8001 >/dev/null
    docker run -d --name "$API" --network "$RED" -p "127.0.0.1:$PUERTO:8000" --env-file "$tmp/api.env" \
        -v "$RAIZ/api:/app" inventaio-api uvicorn main:app --host 0.0.0.0 --port 8000 >/dev/null
    for _ in $(seq 1 60); do
        curl -sf --max-time 3 "http://127.0.0.1:$PUERTO/api/health" >/dev/null && break
        sleep 2
    done
    curl -sf --max-time 3 "http://127.0.0.1:$PUERTO/api/health" >/dev/null || fallar "la API de pruebas no responde en $PUERTO"
    docker exec "$API" python -m scripts.seed_usuarios >/dev/null 2>&1 || fallar "no se pudieron sembrar los usuarios de prueba"
    echo "Pila de pruebas lista: API en http://127.0.0.1:$PUERTO y ML Service en http://127.0.0.1:$PUERTO_ML (base $BD)"
}

quitar() {
    docker rm -f "$ML" "$API" >/dev/null 2>&1 || true
    echo "Contenedores $API y $ML quitados; la base $BD y la foto en $FOTO quedan"
}

estado() {
    docker ps -a --filter "name=$ML" --filter "name=$API" --format '{{.Names}}: {{.Status}}'
    curl -s --max-time 5 "http://127.0.0.1:$PUERTO/api/health" || echo "la API de pruebas no responde en $PUERTO"
    echo
}

case ${1:-} in
    construir|levantar|quitar|estado) "$1" ;;
    *) fallar "uso: pila_pruebas.sh construir|levantar|quitar|estado" ;;
esac
