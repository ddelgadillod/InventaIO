#!/usr/bin/env bash
# InventAI/o — Despliegue del staging por tag, con pruebas de humo y reversa (INV-34, B18 y B19).
#
# Corre en la instancia, como ec2-user, desde Session Manager (docs/INV-34-guia-staging.md):
#   DOMINIO=staging.inventaio.<dominio> bash scripts/desplegar_staging.sh <tag> --primera-vez
#   bash scripts/desplegar_staging.sh <tag>              # despliega y corre el humo; si falla, vuelve al anterior
#   bash scripts/desplegar_staging.sh --reversa          # vuelve al tag anterior, con humo
#   bash scripts/desplegar_staging.sh --configurar-humo  # la cuenta de las pruebas de humo
#
# <tag> es una etiqueta de las imágenes en GHCR: sha-xxxxxxx (un commit de develop o main) o vX.Y.Z.
# Con DOMINIO=… o BUCKET_VOLCADOS=… delante, también los cambia en .env.prod.
#
# Todo vive en /opt/inventaio (INVENTAIO_BASE):
#   repo/                           el clon público, sin credenciales: de aquí sale cada versión
#   versiones/<tag>/                los archivos de ese tag (compose, Caddyfile, base, scripts), con git archive
#   estado/.env.prod                secretos generados aquí la primera vez, que no salen de la instancia (C7)
#   estado/humo.env                 la cuenta de las pruebas de humo
#   estado/actual, estado/anterior  los tags desplegados
# El proyecto de Compose es siempre inventaio-prod, así que la base y los certificados sobreviven a cada versión.
# Sale con 0 si el tag quedó desplegado (y el humo pasó), con 1 si falló y volvió al anterior, y con 2 si se
# detuvo antes de tocar lo que corre.
set -euo pipefail

BASE=${INVENTAIO_BASE:-/opt/inventaio}
REPO=$BASE/repo
ESTADO=$BASE/estado
ENV_PROD=$ESTADO/.env.prod
HUMO_ENV=$ESTADO/humo.env
CUENTA_HUMO=gerente@inventaio.co
CA_EXTRA=${HUMO_CA:-}          # solo en la prueba local: la CA interna de Caddy, para DOMINIO=localhost

fallar() { echo "ERROR: $*" >&2; exit 2; }
paso() { echo "== $*"; }
valor_env() { sed -n "s/^$1=//p" "$ENV_PROD" | tail -n 1; }
leer_estado() { cat "$ESTADO/$1" 2>/dev/null || true; }
secreto() { python3 -c 'import secrets; print(secrets.token_urlsafe(48))'; }

# ── Versión: los archivos del tag ───────────────────

commit_de() {
    case $1 in
        sha-*) git -C "$REPO" rev-parse --verify --quiet "${1#sha-}^{commit}" ;;
        v*.*.*) git -C "$REPO" rev-parse --verify --quiet "refs/tags/$1^{commit}" ;;
        *) return 1 ;;
    esac
}

# Deja en DIR y COMMIT la carpeta y el commit del tag
preparar_version() {
    TAG=$1
    DIR=$BASE/versiones/$TAG
    git -C "$REPO" fetch --quiet --tags origin || fallar "no se pudo actualizar $REPO"
    COMMIT=$(commit_de "$TAG") || fallar "$TAG no es sha-xxxxxxx ni vX.Y.Z de un commit de $REPO"
    if [[ ! -d $DIR ]]; then
        rm -rf "$DIR.tmp" && mkdir -p "$DIR.tmp"
        git -C "$REPO" archive "$COMMIT" docker-compose.prod.yml .env.prod.example VERSION database despliegue scripts \
            | tar -x -C "$DIR.tmp" || fallar "$TAG no tiene los archivos del despliegue (¿es anterior a INV-34?)"
        mv "$DIR.tmp" "$DIR"
    fi
    grep -q '^  caddy:' "$DIR/docker-compose.prod.yml" || fallar "$TAG es anterior a INV-34: su compose no trae Caddy"
}

compose() { INVENTAIO_TAG=$TAG docker compose -f "$DIR/docker-compose.prod.yml" --env-file "$ENV_PROD" "$@"; }

# ── .env.prod ───────────────────────────────────────

# La primera vez, desde la plantilla del tag, con secretos aleatorios (C7). Si ya existe, no cambia los secretos
generar_env() {
    [[ -e $ENV_PROD ]] && return 0
    [[ -n ${DOMINIO:-} ]] || fallar "la primera vez hace falta DOMINIO=… delante del comando"
    (umask 077 && sed -e "s|^POSTGRES_PASSWORD=$|POSTGRES_PASSWORD=$(secreto)|" \
                      -e "s|^JWT_SECRET_KEY=$|JWT_SECRET_KEY=$(secreto)|" \
                      "$DIR/.env.prod.example" > "$ENV_PROD")
    echo "Generado $ENV_PROD (solo lo lee ec2-user)"
}

# DOMINIO=… y BUCKET_VOLCADOS=… delante del comando pasan a .env.prod
actualizar_env() {
    local var valor
    for var in DOMINIO BUCKET_VOLCADOS; do
        valor=${!var:-}
        [[ -z $valor ]] && continue
        [[ $valor =~ ^[a-z0-9][a-z0-9.-]*$ ]] || fallar "$var no válido: solo minúsculas, números, puntos y guiones"
        if [[ $(valor_env "$var") != "$valor" ]]; then
            sed -i "s|^$var=.*|$var=$valor|" "$ENV_PROD"
            echo "$var=$valor en .env.prod"
        fi
    done
    [[ -n $(valor_env DOMINIO) ]] || fallar "falta DOMINIO en $ENV_PROD"
}

# ── Despliegue ──────────────────────────────────────

migrar() {
    local id
    id=$(compose ps -q postgres)
    BD_RED=container:$id PGHOST=localhost PGPORT=5432 PGUSER=$(valor_env POSTGRES_USER) \
        PGPASSWORD=$(valor_env POSTGRES_PASSWORD) PGDATABASE=$(valor_env POSTGRES_DB) \
        bash "$DIR/scripts/bd/migrar.sh"
}

# Las imágenes se bajan antes de tocar nada: si falta alguna, lo que corre sigue igual (sale con 2).
# Después, cada paso devuelve 1 si falla, para que quien llama vuelva al tag anterior
desplegar() {
    preparar_version "$1"
    paso "Imágenes de $TAG ($COMMIT)"
    compose pull --quiet || fallar "no se pudieron bajar las imágenes de $TAG: ¿terminó el workflow «Imágenes»?"
    paso "Base de datos y migración"
    compose up -d --wait postgres || return 1
    migrar || return 1
    paso "Servicios"
    compose up -d --wait --wait-timeout 300 --remove-orphans || { compose ps; return 1; }
}

# Caddy pide el certificado al arrancar si aún no lo tiene: espera hasta 2 minutos a que HTTPS responda
esperar_https() {
    local dominio i
    dominio=$(valor_env DOMINIO)
    for i in $(seq 24); do
        curl -sS -o /dev/null --max-time 5 ${CA_EXTRA:+--cacert "$CA_EXTRA"} "https://$dominio/" 2>/dev/null && return 0
        sleep 5
    done
    echo "https://$dominio no responde con un certificado válido: revisa el DNS y 'docker logs inventaio-prod-caddy-1'"
    return 1
}

humo() {
    [[ -s $HUMO_ENV ]] || { echo "Falta la cuenta de humo: bash scripts/desplegar_staging.sh --configurar-humo"; return 1; }
    paso "Pruebas de humo"
    esperar_https || return 1
    python3 "$DIR/scripts/humo_staging.py" "https://$(valor_env DOMINIO)" --credenciales "$HUMO_ENV" \
        --version "$(tr -d '[:space:]' < "$DIR/VERSION")" --commit "$COMMIT" ${CA_EXTRA:+--ca "$CA_EXTRA"}
}

registrar() {
    local actual
    actual=$(leer_estado actual)
    [[ -n $actual && $actual != "$1" ]] && echo "$actual" > "$ESTADO/anterior"
    echo "$1" > "$ESTADO/actual"
    # Sin las imágenes de otros tags: el disco es de 30 GB. Una reversa las vuelve a bajar
    docker image prune -af >/dev/null
}

# ── Comandos ────────────────────────────────────────

configurar_humo() {
    local email clave
    read -r -p "Email de la cuenta de humo [$CUENTA_HUMO]: " email
    read -r -s -p "Clave (no se muestra): " clave
    echo
    [[ -n $clave ]] || fallar "clave vacía"
    (umask 077 && printf 'HUMO_EMAIL=%s\nHUMO_CLAVE=%s\n' "${email:-$CUENTA_HUMO}" "$clave" > "$HUMO_ENV")
    echo "Guardada en $HUMO_ENV (solo la lee ec2-user)"
}

primera_vez() {
    preparar_version "$1"
    generar_env
    actualizar_env
    desplegar "$1" || fallar "el primer despliegue de $1 no quedó sano"
    registrar "$1"
    esperar_https || true
    cat <<EOF
Desplegado $1 en https://$(valor_env DOMINIO), sin pruebas de humo porque aún no hay bodega ni usuarios.
Sigue la guía: restaurar la bodega (§9), crear los usuarios y la cuenta de humo (§10) y desplegar con humo (§11).
EOF
}

desplegar_con_humo() {
    local tag=$1 anterior
    [[ -e $ENV_PROD ]] || fallar "no hay $ENV_PROD: el primer despliegue va con --primera-vez"
    actualizar_env
    anterior=$(leer_estado actual)
    if desplegar "$tag" && humo; then
        registrar "$tag"
        echo "Desplegado $tag en https://$(valor_env DOMINIO)"
        return 0
    fi
    echo "Falló el despliegue de $tag"
    if [[ -n $anterior && $anterior != "$tag" ]]; then
        paso "Vuelta a $anterior"
        if desplegar "$anterior" && humo; then
            echo "Quedó $anterior, como antes"
        else
            echo "ATENCIÓN: $anterior tampoco pasó el humo"
        fi
    fi
    exit 1
}

reversa() {
    local actual anterior
    actual=$(leer_estado actual)
    anterior=$(leer_estado anterior)
    [[ -n $anterior ]] || fallar "no hay un tag anterior en $ESTADO/anterior"
    paso "Reversa de $actual a $anterior"
    if desplegar "$anterior" && humo; then
        echo "$anterior" > "$ESTADO/actual"
        echo "$actual" > "$ESTADO/anterior"
        echo "Quedó $anterior. Para volver: bash scripts/desplegar_staging.sh $actual"
        return 0
    fi
    echo "La reversa a $anterior no pasó el humo"
    exit 1
}

# ── Inicio ──────────────────────────────────────────

[[ -d $REPO/.git ]] || fallar "no está $REPO (guía, §7)"
docker info >/dev/null 2>&1 || fallar "sin acceso a Docker: ¿corriste preparar_instancia.sh y entraste otra vez con 'sudo su - ec2-user'?"
mkdir -p "$BASE/versiones" "$ESTADO" && chmod 700 "$ESTADO"
exec 9> "$ESTADO/.bloqueo"
flock -n 9 || fallar "hay otro despliegue en curso"

case "${1:-} ${2:-}" in
    "--configurar-humo ") configurar_humo ;;
    "--reversa ") reversa ;;
    sha-*" --primera-vez" | v*" --primera-vez") primera_vez "$1" ;;
    sha-*" " | v*" ") desplegar_con_humo "$1" ;;
    *) sed -n '5,8p' "$0" | sed 's/^# *//' >&2; exit 2 ;;
esac
