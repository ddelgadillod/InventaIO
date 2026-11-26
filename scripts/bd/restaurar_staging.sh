#!/usr/bin/env bash
# InventAI/o — Baja un volcado del bucket, lo restaura en la base del staging y lo valida (INV-34, B22).
#
# En la instancia, como ec2-user, después del primer despliegue (docs/INV-34-guia-staging.md, §9):
#   bash scripts/bd/restaurar_staging.sh 20261112-0930      # la carpeta con fecha que creó volcar.sh
#
# En una máquina con k3s (la que preparó despliegue/preparar_k3s.sh, que escribe estado/ambiente) hace lo mismo en el
# PostgreSQL del clúster: el bucket sale de Parameter Store (/inventaio/<ambiente>/bucket-volcados), restaurar.sh y
# validar.sh corren en el pod de herramientas (BD_POD) y al final reinicia el Core API y el ML Service, para que no
# sirvan nada calculado con la base vacía. Si la carpeta trae app.dump (trasladar_staging.sh), también restaura app:
#   bash scripts/bd/restaurar_staging.sh traslado-20261201-0900
#
# Con --recargar, sobre una base que ya tiene datos, corre recargar.sh en lugar de restaurar.sh (INV-82): respalda dw y
# app en /opt/inventaio/volcados/respaldo-…, reemplaza la bodega en una sola transacción y conserva los usuarios.
# Conviene correr el script del tag desplegado, que es el que trae recargar.sh:
#   bash /opt/inventaio/versiones/$(cat /opt/inventaio/estado/actual)/scripts/bd/restaurar_staging.sh --recargar 20261126-0900
# Para volver atrás, la carpeta del respaldo, que se lee de la máquina y no del bucket: --recargar respaldo-…
#
# Baja dw.dump, su suma y su huella de s3://<BUCKET_VOLCADOS>/volcados/<carpeta>/ con el rol de la instancia
# (s3:GetObject, sin llaves) a /opt/inventaio/volcados/<carpeta>/. Luego corre restaurar.sh y validar.sh del
# tag desplegado contra el contenedor de la base, con la conexión de .env.prod. Sale como ellos: 0 si quedó
# restaurada y la huella coincide, 1 si no coincide, 2 por un error y 3 si dw ya tenía filas (recargar es
# recrear la base: guía, §15).
set -euo pipefail

BASE=${INVENTAIO_BASE:-/opt/inventaio}
ENV_PROD=$BASE/estado/.env.prod
REGION=${AWS_REGION:-us-east-2}   # la del bucket y el staging (D-R3)

fallar() { echo "ERROR: $*" >&2; exit 2; }
valor_env() { sed -n "s/^$1=//p" "$ENV_PROD" | tail -n 1; }

PASO=restaurar
if [[ ${1:-} == --recargar ]]; then
    PASO=recargar
    shift
fi
[[ $# -eq 1 && $1 =~ ^[A-Za-z0-9._-]+$ ]] || fallar "uso: restaurar_staging.sh [--recargar] CARPETA (p. ej. 20261112-0930)"
actual=$(cat "$BASE/estado/actual" 2>/dev/null) || fallar "no hay un tag desplegado"
RAIZ=$BASE/versiones/$actual
[[ -f $RAIZ/scripts/bd/$PASO.sh ]] || fallar "el tag $actual no trae scripts/bd/$PASO.sh: despliega uno más nuevo"
if [[ -r $BASE/estado/ambiente ]]; then
    modo=k3s
    ambiente=$(cat "$BASE/estado/ambiente")
    bucket=$(aws ssm get-parameter --region "$REGION" --name "/inventaio/$ambiente/bucket-volcados" \
        --query Parameter.Value --output text 2>/dev/null) || bucket=""
    [[ -n $bucket ]] || fallar "falta /inventaio/$ambiente/bucket-volcados en Parameter Store (lo crea infra/)"
else
    modo=compose
    [[ -r $ENV_PROD ]] || fallar "no está $ENV_PROD: primero el despliegue con --primera-vez"
    bucket=$(valor_env BUCKET_VOLCADOS)
    [[ -n $bucket ]] || fallar "falta BUCKET_VOLCADOS en .env.prod: BUCKET_VOLCADOS=… bash scripts/desplegar_staging.sh $actual"
fi

carpeta=$BASE/volcados/$1
if [[ $1 == respaldo-* ]]; then
    # Un respaldo que dejó recargar.sh en esta máquina: no está en el bucket
    [[ $PASO == recargar && -f $carpeta/dw.dump && -f $carpeta/app.dump ]] \
        || fallar "un respaldo se repone con --recargar, y $carpeta debe tener dw.dump y app.dump"
    echo "== Respaldo local $carpeta"
else
    mkdir -p "$carpeta"
    echo "== Volcado s3://…/volcados/$1/"
    for archivo in dw.dump dw.dump.sha256 huella.txt; do
        aws s3 cp --only-show-errors --region "$REGION" "s3://$bucket/volcados/$1/$archivo" "$carpeta/$archivo" \
            || fallar "no se pudo bajar $archivo: revisa la carpeta y el permiso s3:GetObject del rol"
    done
    # app viaja solo en el traslado entre staging (trasladar_staging.sh)
    if aws s3 ls --region "$REGION" "s3://$bucket/volcados/$1/app.dump" >/dev/null 2>&1; then
        for archivo in app.dump app.dump.sha256; do
            aws s3 cp --only-show-errors --region "$REGION" "s3://$bucket/volcados/$1/$archivo" "$carpeta/$archivo" \
                || fallar "no se pudo bajar $archivo"
        done
        echo "Trae app: también se restauran los usuarios"
    fi
fi

if [[ $modo == k3s ]]; then
    # shellcheck source=/dev/null
    source "$RAIZ/scripts/bd/comun.sh"
    herramientas_k8s "$RAIZ/k8s/plantillas/bd-herramientas.yaml"
    echo "== Paso $PASO ($actual, en k3s)"
    inicio=$SECONDS
    bash "$RAIZ/scripts/bd/$PASO.sh" "$carpeta"
    echo "Listo en $((SECONDS - inicio)) s"
    echo "== Validación"
    bash "$RAIZ/scripts/bd/validar.sh" "$carpeta"
    echo "== Reinicio del Core API y el ML Service"
    $KUBECTL rollout restart -n "$BD_NAMESPACE" deployment/api deployment/ml-service >/dev/null
    $KUBECTL rollout status -n "$BD_NAMESPACE" deployment/api --timeout=300s >/dev/null
    $KUBECTL rollout status -n "$BD_NAMESPACE" deployment/ml-service --timeout=600s >/dev/null
    echo "Listos"
    exit 0
fi

id=$(docker ps -q --filter label=com.docker.compose.project=inventaio-prod --filter label=com.docker.compose.service=postgres)
[[ -n $id ]] || fallar "la base de inventaio-prod no está corriendo"
export BD_RED=container:$id PGHOST=localhost PGPORT=5432
PGUSER=$(valor_env POSTGRES_USER) PGPASSWORD=$(valor_env POSTGRES_PASSWORD) PGDATABASE=$(valor_env POSTGRES_DB)
export PGUSER PGPASSWORD PGDATABASE

echo "== Paso $PASO ($actual)"
inicio=$SECONDS
bash "$RAIZ/scripts/bd/$PASO.sh" "$carpeta"
echo "Listo en $((SECONDS - inicio)) s"
echo "== Validación"
bash "$RAIZ/scripts/bd/validar.sh" "$carpeta"
