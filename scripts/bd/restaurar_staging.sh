#!/usr/bin/env bash
# InventAI/o — Baja un volcado del bucket, lo restaura en la base del staging y lo valida (INV-34, B22).
#
# En la instancia, como ec2-user, después del primer despliegue (docs/INV-34-guia-staging.md, §9):
#   bash scripts/bd/restaurar_staging.sh 20261112-0930      # la carpeta con fecha que creó volcar.sh
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

[[ $# -eq 1 && $1 =~ ^[A-Za-z0-9._-]+$ ]] || fallar "uso: restaurar_staging.sh CARPETA (p. ej. 20261112-0930)"
[[ -r $ENV_PROD ]] || fallar "no está $ENV_PROD: primero el despliegue con --primera-vez"
actual=$(cat "$BASE/estado/actual" 2>/dev/null) || fallar "no hay un tag desplegado"
RAIZ=$BASE/versiones/$actual
bucket=$(valor_env BUCKET_VOLCADOS)
[[ -n $bucket ]] || fallar "falta BUCKET_VOLCADOS en .env.prod: BUCKET_VOLCADOS=… bash scripts/desplegar_staging.sh $actual"

carpeta=$BASE/volcados/$1
mkdir -p "$carpeta"
echo "== Volcado s3://$bucket/volcados/$1/"
for archivo in dw.dump dw.dump.sha256 huella.txt; do
    aws s3 cp --only-show-errors --region "$REGION" "s3://$bucket/volcados/$1/$archivo" "$carpeta/$archivo" \
        || fallar "no se pudo bajar $archivo: revisa la carpeta y el permiso s3:GetObject del rol"
done

id=$(docker ps -q --filter label=com.docker.compose.project=inventaio-prod --filter label=com.docker.compose.service=postgres)
[[ -n $id ]] || fallar "la base de inventaio-prod no está corriendo"
export BD_RED=container:$id PGHOST=localhost PGPORT=5432
PGUSER=$(valor_env POSTGRES_USER) PGPASSWORD=$(valor_env POSTGRES_PASSWORD) PGDATABASE=$(valor_env POSTGRES_DB)
export PGUSER PGPASSWORD PGDATABASE

echo "== Restauración ($actual)"
inicio=$SECONDS
bash "$RAIZ/scripts/bd/restaurar.sh" "$carpeta"
echo "Restaurada en $((SECONDS - inicio)) s"
echo "== Validación"
bash "$RAIZ/scripts/bd/validar.sh" "$carpeta"
