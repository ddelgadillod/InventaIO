#!/usr/bin/env bash
# InventAI/o — Despliegue en k3s por tag, con migración, humo y vuelta automática (docs/INFRA-k3s-serverless-
# requerimientos.md). Es la versión de Kubernetes de scripts/desplegar_staging.sh (compose), con el mismo contrato:
#
#   bash scripts/desplegar.sh <tag>                 # despliega y corre el humo; si falla, vuelve solo al tag anterior
#   bash scripts/desplegar.sh <tag> --primera-vez   # sin humo: todavía no hay bodega ni usuarios (guía, «Primer despliegue»)
#   bash scripts/desplegar.sh --reversa             # vuelve al tag anterior, con humo
#
# <tag> es una etiqueta de las imágenes en GHCR: sha-xxxxxxx (un commit de develop o main), vX.Y.Z o vX.Y.Z-rc.N.
# Sale con 0 si el tag quedó desplegado (y el humo pasó), con 1 si falló y volvió al anterior, y con 2 si se detuvo
# antes de tocar lo que corre. Lo llama el documento de Session Manager «inventaio-desplegar» como ec2-user.
#
# En la máquina, todo vive en /opt/inventaio (INVENTAIO_BASE):
#   repo/                        el clon público, sin credenciales
#   versiones/<tag>/             los archivos del tag (k8s, database, scripts, VERSION), con git archive
#   versiones/<tag>/render/      la kustomization de este ambiente con los tags fijados (la escribe este script)
#   estado/ambiente              staging o produccion (lo escribe despliegue/preparar_k3s.sh)
#   estado/actual, anterior      los tags desplegados; también en Parameter Store, para reconstruir la máquina
#
# Lo que no vive en el repositorio sale de Parameter Store (/inventaio/<ambiente>/…), con el rol de la máquina:
#   postgres-password, jwt-secret-key, origen-secreto   el Secret «inventaio-secretos». Si faltan la primera vez, se
#                                                       generan aquí y se guardan cifrados: no salen de AWS
#   dominio-origen                                      el nombre del origen, para Caddy y Let's Encrypt
#   url-publica                                         la URL de CloudFront, donde corre el humo
#   humo-email, humo-clave                              la cuenta de las pruebas de humo
#   rds-endpoint                                        solo producción: el endpoint de RDS
set -euo pipefail

BASE=${INVENTAIO_BASE:-/opt/inventaio}
REPO=$BASE/repo
ESTADO=$BASE/estado
REGION=${AWS_REGION:-us-east-2}
NS=inventaio
KUBECTL=${KUBECTL:-kubectl}
REGISTRO=ghcr.io/ddelgadillod
SERVICIOS=(api ml-service nlp-agent web)
if [[ -z ${KUBECONFIG:-} ]]; then
    if [[ -r $HOME/.kube/config ]]; then export KUBECONFIG=$HOME/.kube/config; else export KUBECONFIG=/etc/rancher/k3s/k3s.yaml; fi
fi

fallar() { echo "ERROR: $*" >&2; exit 2; }
paso() { echo "== $*"; }
leer_estado() { cat "$ESTADO/$1" 2>/dev/null || true; }

AMBIENTE=${INVENTAIO_AMBIENTE:-$(leer_estado ambiente)}
[[ $AMBIENTE == staging || $AMBIENTE == produccion ]] \
    || fallar "no se sabe el ambiente: falta $ESTADO/ambiente (staging o produccion; lo escribe preparar_k3s.sh)"

# ── Parameter Store ─────────────────────────────────

# param <nombre>: el valor de /inventaio/<ambiente>/<nombre>, o vacío si no existe
param() {
    aws ssm get-parameter --region "$REGION" --with-decryption --name "/inventaio/$AMBIENTE/$1" \
        --query Parameter.Value --output text 2>/dev/null || true
}

guardar_param() {
    aws ssm put-parameter --region "$REGION" --name "/inventaio/$AMBIENTE/$1" --type "$2" --value "$3" --overwrite \
        >/dev/null || echo "AVISO: no se pudo guardar /inventaio/$AMBIENTE/$1 en Parameter Store"
}

# secreto <nombre>: el valor de Parameter Store; si no existe, lo genera y lo guarda cifrado sin sobrescribir
secreto() {
    local valor
    valor=$(param "$1")
    if [[ -z $valor ]]; then
        valor=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
        aws ssm put-parameter --region "$REGION" --name "/inventaio/$AMBIENTE/$1" --type SecureString \
            --value "$valor" >/dev/null || fallar "no se pudo guardar el secreto nuevo $1 en Parameter Store"
        echo "Generado /inventaio/$AMBIENTE/$1 (no sale de AWS)" >&2
    fi
    printf '%s' "$valor"
}

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
    [[ $TAG =~ ^(sha-[0-9a-f]{7}|v[0-9]+\.[0-9]+\.[0-9]+(-rc\.[0-9]+)?)$ ]] || fallar "$TAG no es sha-xxxxxxx ni vX.Y.Z"
    DIR=$BASE/versiones/$TAG
    git -C "$REPO" fetch --quiet --tags origin || fallar "no se pudo actualizar $REPO"
    COMMIT=$(commit_de "$TAG") || fallar "$TAG no es un commit ni una etiqueta de $REPO"
    if [[ ! -d $DIR/k8s ]]; then
        rm -rf "$DIR.tmp" && mkdir -p "$DIR.tmp"
        git -C "$REPO" archive "$COMMIT" k8s database scripts VERSION | tar -x -C "$DIR.tmp" \
            || fallar "$TAG no trae k8s/: es anterior a la migración a Kubernetes"
        rm -rf "$DIR" && mv "$DIR.tmp" "$DIR"
    fi
}

# Que las cuatro imágenes del tag existan en GHCR antes de tocar nada (paquetes públicos: token anónimo)
exigir_imagenes() {
    local servicio token
    for servicio in "${SERVICIOS[@]}"; do
        token=$(curl -fsS --max-time 20 "https://ghcr.io/token?scope=repository:ddelgadillod/inventaio-$servicio:pull" \
            | python3 -c 'import json, sys; print(json.load(sys.stdin)["token"])') \
            || fallar "no se pudo consultar GHCR"
        curl -fsS --max-time 20 -o /dev/null -I -H "Authorization: Bearer $token" \
            -H "Accept: application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.docker.distribution.manifest.v2+json" \
            "https://ghcr.io/v2/ddelgadillod/inventaio-$servicio/manifests/$TAG" \
            || fallar "no está la imagen inventaio-$servicio:$TAG en GHCR: ¿terminó el workflow «Imágenes»?"
    done
}

# ── Lo que no vive en el repositorio ────────────────

# El espacio de nombres, el Secret y el esquema del tag. No reinicia nada: los pods leen el Secret al arrancar
preparar_cluster() {
    local postgres jwt origen
    $KUBECTL apply -f "$DIR/k8s/base/namespace.yaml" >/dev/null || fallar "kubectl no llega al clúster"
    # Fuera de la sustitución de procesos: ahí un error no detendría el script
    postgres=$(secreto postgres-password)
    jwt=$(secreto jwt-secret-key)
    origen=$(secreto origen-secreto)
    [[ -n $postgres && -n $jwt && -n $origen ]] || fallar "un secreto de Parameter Store quedó vacío"
    # Por un archivo y no por la línea de comandos: los valores no quedan en la lista de procesos
    $KUBECTL create secret generic inventaio-secretos -n "$NS" --dry-run=client -o yaml --from-env-file=<(
        printf 'POSTGRES_PASSWORD=%s\nJWT_SECRET_KEY=%s\nORIGEN_SECRETO=%s\n' "$postgres" "$jwt" "$origen"
    ) | $KUBECTL apply -f - >/dev/null || fallar "no se pudo crear el Secret inventaio-secretos"
    $KUBECTL create configmap inventaio-esquema -n "$NS" --dry-run=client -o yaml \
        --from-file=01-init.sql="$DIR/database/init.sql" | $KUBECTL apply -f - >/dev/null \
        || fallar "no se pudo crear el ConfigMap del esquema"
}

# render <tag>: la kustomization del ambiente con las imágenes del tag y lo que sale de Parameter Store
render() {
    local tag=$1 dir=$BASE/versiones/$1 dominio rds servicio
    dominio=$(param dominio-origen)
    [[ -n $dominio ]] || fallar "falta /inventaio/$AMBIENTE/dominio-origen en Parameter Store"
    mkdir -p "$dir/render"
    {
        echo "apiVersion: kustomize.config.k8s.io/v1beta1"
        echo "kind: Kustomization"
        echo "resources:"
        echo "  - ../k8s/overlays/$AMBIENTE"
        echo "images:"
        for servicio in "${SERVICIOS[@]}"; do
            echo "  - name: $REGISTRO/inventaio-$servicio"
            echo "    newTag: $tag"
        done
        echo "configMapGenerator:"
        echo "  - name: inventaio-config"
        echo "    behavior: merge"
        echo "    literals:"
        echo "      - DOMINIO=$dominio"
        if [[ $AMBIENTE == produccion ]]; then
            rds=$(param rds-endpoint)
            [[ -n $rds ]] || fallar "falta /inventaio/produccion/rds-endpoint en Parameter Store"
            echo "patches:"
            echo "  - target: {kind: Service, name: postgres}"
            echo "    patch: |-"
            echo "      - op: replace"
            echo "        path: /spec/externalName"
            echo "        value: $rds"
        fi
    } > "$dir/render/kustomization.yaml"
    $KUBECTL kustomize "$dir/render" >/dev/null || fallar "la kustomization de $tag no se genera"
}

# ── Despliegue ──────────────────────────────────────

# migrar <tag>: el Job de migración del tag, con su esquema. Antes de actualizar los servicios, como en compose
migrar() {
    local nombre estado
    nombre=migracion-$(tr '.' '-' <<< "$1")
    $KUBECTL delete job -n "$NS" "$nombre" --ignore-not-found >/dev/null
    sed "s/__NOMBRE__/$nombre/" "$DIR/k8s/plantillas/migracion.yaml" | $KUBECTL apply -f - >/dev/null || return 1
    for _ in $(seq 60); do
        estado=$($KUBECTL get job -n "$NS" "$nombre" -o jsonpath='{.status.succeeded}/{.status.failed}' 2>/dev/null || true)
        case $estado in
            1/*) echo "Esquema al día"; return 0 ;;
            */1) $KUBECTL logs -n "$NS" "job/$nombre" --tail=20 || true; echo "La migración falló"; return 1 ;;
        esac
        sleep 5
    done
    echo "La migración no terminó en 5 minutos"
    return 1
}

hay_base_lista() {
    [[ $AMBIENTE == produccion ]] && return 0
    [[ $($KUBECTL get statefulset -n "$NS" postgres -o jsonpath='{.status.readyReplicas}' 2>/dev/null || true) == 1 ]]
}

esperar_servicios() {
    local d
    if [[ $AMBIENTE != produccion ]]; then
        $KUBECTL rollout status -n "$NS" statefulset/postgres --timeout=300s || return 1
    fi
    for d in redis api nlp-agent web caddy; do
        $KUBECTL rollout status -n "$NS" "deployment/$d" --timeout=300s || return 1
    done
    # Carga los modelos: hasta 10 minutos
    $KUBECTL rollout status -n "$NS" deployment/ml-service --timeout=600s || return 1
}

# desplegar <tag>: devuelve 1 si algo falla después de empezar a tocar lo que corre
desplegar() {
    preparar_version "$1"
    paso "Imágenes de $TAG ($COMMIT) en GHCR"
    exigir_imagenes
    paso "Secret, esquema y kustomization de $AMBIENTE"
    preparar_cluster
    render "$TAG"
    # Con la base ya en marcha, la migración va antes de los servicios nuevos. La primera vez, Postgres crea el esquema
    # al arrancar (docker-entrypoint-initdb.d) y la migración corre después, sin cambios
    local migrada=0
    if hay_base_lista; then
        paso "Migración"
        migrar "$TAG" || return 1
        migrada=1
    fi
    paso "Servicios"
    $KUBECTL apply -k "$DIR/render" >/dev/null || return 1
    esperar_servicios || { $KUBECTL get pods -n "$NS"; return 1; }
    if [[ $migrada == 0 ]]; then
        paso "Migración"
        migrar "$TAG" || return 1
    fi
}

humo() {
    local url credenciales rc
    url=$(param url-publica)
    [[ -n $url ]] || { echo "Falta /inventaio/$AMBIENTE/url-publica en Parameter Store"; return 1; }
    credenciales=$(mktemp "$ESTADO/humo.XXXXXX")
    chmod 600 "$credenciales"
    printf 'HUMO_EMAIL=%s\nHUMO_CLAVE=%s\n' "$(param humo-email)" "$(param humo-clave)" > "$credenciales"
    paso "Pruebas de humo en $url"
    rc=0
    python3 "$DIR/scripts/humo_staging.py" "$url" --credenciales "$credenciales" \
        --version "$(tr -d '[:space:]' < "$DIR/VERSION")" --commit "$COMMIT" || rc=$?
    rm -f "$credenciales"
    return $rc
}

registrar() {
    local actual
    actual=$(leer_estado actual)
    if [[ -n $actual && $actual != "$1" ]]; then
        echo "$actual" > "$ESTADO/anterior"
        guardar_param tag-anterior String "$actual"
    fi
    echo "$1" > "$ESTADO/actual"
    guardar_param tag-actual String "$1"
}

# ── Comandos ────────────────────────────────────────

desplegar_con_humo() {
    local tag=$1 anterior
    anterior=$(leer_estado actual)
    if desplegar "$tag" && humo; then
        registrar "$tag"
        echo "Desplegado $tag en $AMBIENTE"
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

primera_vez() {
    desplegar "$1" || fallar "el primer despliegue de $1 no quedó sano"
    registrar "$1"
    cat <<EOF
Desplegado $1 en $AMBIENTE, sin pruebas de humo porque aún no hay bodega ni usuarios.
Sigue la guía: restaurar la bodega, crear los usuarios y la cuenta de humo, y desplegar con humo.
EOF
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
        guardar_param tag-actual String "$anterior"
        guardar_param tag-anterior String "$actual"
        echo "Quedó $anterior. Para volver: bash scripts/desplegar.sh $actual"
    else
        echo "ATENCIÓN: $anterior no pasó el humo"
        exit 1
    fi
}

mkdir -p "$BASE/versiones" "$ESTADO"
case ${1:-} in
    --reversa) reversa ;;
    sha-*|v*)
        if [[ ${2:-} == --primera-vez ]]; then primera_vez "$1"; else desplegar_con_humo "$1"; fi ;;
    *) fallar "uso: desplegar.sh <tag> [--primera-vez] | --reversa" ;;
esac
