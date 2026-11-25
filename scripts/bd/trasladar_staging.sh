#!/usr/bin/env bash
# InventAI/o — Primera mitad del traslado de la base de staging de compose a k3s (fase 4 del plan de staging en k3s:
# docs/INFRA-k3s-serverless-requerimientos.md). En la máquina de compose, como ec2-user, desde Session Manager:
#   bash /opt/inventaio/repo/scripts/bd/trasladar_staging.sh
#
# Vuelca dw y también app (usuarios con sus claves, la cuenta de humo y la configuración de alertas: INCLUIR_APP=1 de
# volcar.sh) desde la base de compose, con la conexión de .env.prod, y sube el volcado, sus sumas y la huella a
# s3://<BUCKET_VOLCADOS>/volcados/traslado-<fecha>/ con el rol de la máquina. La huella con valores
# (huella-detalle.txt) no se sube. No cambia nada de lo que corre. Al final imprime la carpeta, que es lo que recibe
# restaurar_staging.sh en la máquina nueva.
set -euo pipefail

BASE=${INVENTAIO_BASE:-/opt/inventaio}
ENV_PROD=$BASE/estado/.env.prod
REGION=${AWS_REGION:-us-east-2}

fallar() { echo "ERROR: $*" >&2; exit 2; }
valor_env() { sed -n "s/^$1=//p" "$ENV_PROD" | tail -n 1; }

[[ -r $ENV_PROD ]] || fallar "no está $ENV_PROD: esto corre en la máquina de compose"
bucket=$(valor_env BUCKET_VOLCADOS)
[[ -n $bucket ]] || fallar "falta BUCKET_VOLCADOS en .env.prod"
id=$(docker ps -q --filter label=com.docker.compose.project=inventaio-prod --filter label=com.docker.compose.service=postgres)
[[ -n $id ]] || fallar "la base de inventaio-prod no está corriendo"

nombre=traslado-$(date +%Y%m%d-%H%M)
carpeta=$BASE/volcados/$nombre
export BD_RED=container:$id PGHOST=localhost PGPORT=5432 INCLUIR_APP=1
PGUSER=$(valor_env POSTGRES_USER) PGPASSWORD=$(valor_env POSTGRES_PASSWORD) PGDATABASE=$(valor_env POSTGRES_DB)
export PGUSER PGPASSWORD PGDATABASE

echo "== Volcado de dw y app"
inicio=$SECONDS
bash "$BASE/repo/scripts/bd/volcar.sh" "$carpeta" >/dev/null
echo "Volcado en $((SECONDS - inicio)) s: dw $(du -h "$carpeta/dw.dump" | cut -f1), app $(du -h "$carpeta/app.dump" | cut -f1)"

echo "== Subida a s3://…/volcados/$nombre/"
for archivo in dw.dump dw.dump.sha256 app.dump app.dump.sha256 huella.txt; do
    aws s3 cp --only-show-errors --region "$REGION" "$carpeta/$archivo" "s3://$bucket/volcados/$nombre/$archivo" \
        || fallar "no se pudo subir $archivo: revisa el permiso s3:PutObject del rol (infra/, fase 4)"
done
echo "Listo. En la máquina nueva: bash /opt/inventaio/repo/scripts/bd/restaurar_staging.sh $nombre"
