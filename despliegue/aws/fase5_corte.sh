#!/usr/bin/env bash
# InventAI/o — Fase 5: corte del staging de compose al de k3s (docs/INFRA-k3s-serverless-requerimientos.md). En AWS
# CloudShell (us-east-2), desde la raíz del repositorio en la rama develop:
#   bash despliegue/aws/fase5_corte.sh              # el corte
#   bash despliegue/aws/fase5_corte.sh --revertir   # la vuelta atrás
#
# El corte:
#   1. actualiza el documento de Session Manager inventaio-desplegar (inventaio-desplegar.json): en una máquina con k3s
#      corre scripts/desplegar.sh, y en una de compose scripts/desplegar_staging.sh. Sirve para las dos;
#   2. la máquina de compose (Name=inventaio-staging) pasa a Ambiente=staging-entregado. Deja de recibir despliegues y
#      queda con la versión entregada a evaluación, encendida y con su dirección (P21);
#   3. dice lo que sigue: OpenTofu le pone Ambiente=staging a la máquina nueva y URL_PUBLICA pasa a CloudFront.
# Mientras no corra el paso 3, ninguna máquina lleva Ambiente=staging: un despliegue en ese momento falla sin tocar nada.
#
# La vuelta atrás devuelve Ambiente=staging a la máquina de compose. Antes, la nueva vuelve a staging-k3s con:
#   bash despliegue/aws/tofu.sh staging apply -var etiqueta_ambiente=staging-k3s
# Es idempotente. No muestra el número de la cuenta ni los identificadores de las máquinas.
set -euo pipefail

REGION=us-east-2
DOCUMENTO=inventaio-desplegar
DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
DOC_JSON=$DIR/inventaio-desplegar.json
export AWS_PAGER=""

fallar() { echo "ERROR: $*" >&2; exit 2; }
paso() { printf '\n== %s\n' "$*"; }

revertir=0
case ${1:-} in
    "") ;;
    --revertir) revertir=1 ;;
    *) fallar "uso: fase5_corte.sh [--revertir]" ;;
esac
command -v jq >/dev/null || fallar "falta jq (CloudShell lo trae)"
jq -e . "$DOC_JSON" >/dev/null || fallar "$DOC_JSON no es JSON válido"

# maquinas: nombre, etiqueta Ambiente y estado de las máquinas del proyecto, sin sus identificadores
maquinas() {
    aws ec2 describe-instances --region "$REGION" \
        --filters Name=tag:Proyecto,Values=inventaio Name=instance-state-name,Values=pending,running,stopping,stopped \
        --query 'Reservations[].Instances[].[Tags[?Key==`Name`]|[0].Value, Tags[?Key==`Ambiente`]|[0].Value, State.Name]' \
        --output text | sort | awk '{ printf "  %-26s Ambiente=%-20s %s\n", $1, $2, $3 }'
}

compose=$(aws ec2 describe-instances --region "$REGION" \
    --filters Name=tag:Name,Values=inventaio-staging Name=instance-state-name,Values=pending,running,stopping,stopped \
    --query 'Reservations[].Instances[].InstanceId' --output text)
[[ $(wc -w <<<"$compose") -eq 1 ]] || fallar "se esperaba una sola máquina inventaio-staging (la de compose)"

if [[ $revertir == 1 ]]; then
    paso "Vuelta atrás: la máquina de compose recibe otra vez los despliegues"
    nueva=$(aws ec2 describe-instances --region "$REGION" \
        --filters Name=tag:Name,Values=inventaio-staging-k3s Name=tag:Ambiente,Values=staging \
        Name=instance-state-name,Values=pending,running,stopping,stopped \
        --query 'Reservations[].Instances[].InstanceId' --output text)
    [[ -z $nueva ]] || fallar "la máquina nueva todavía lleva Ambiente=staging: primero tofu.sh staging apply -var etiqueta_ambiente=staging-k3s"
    aws ec2 create-tags --region "$REGION" --resources "$compose" --tags Key=Ambiente,Value=staging
    paso "Máquinas del proyecto"
    maquinas
    echo
    echo "En GitHub, URL_PUBLICA del entorno «staging» vuelve a https://inventaio-staging.duckdns.org"
    exit 0
fi

paso "1. Documento $DOCUMENTO: elige el script según la máquina"
if version=$(aws ssm update-document --region "$REGION" --name "$DOCUMENTO" --content "file://$DOC_JSON" \
        --document-format JSON --document-version '$LATEST' \
        --query DocumentDescription.DocumentVersion --output text 2>&1); then
    aws ssm update-document-default-version --region "$REGION" --name "$DOCUMENTO" --document-version "$version" >/dev/null
    echo "Actualizado: versión $version"
elif grep -q DuplicateDocumentContent <<<"$version"; then
    echo "Ya estaba al día"
else
    echo "$version" | sed -E 's/[0-9]{12}/<cuenta>/g' >&2
    fallar "no se pudo actualizar el documento"
fi

paso "2. La máquina de compose queda con la versión entregada"
aws ec2 create-tags --region "$REGION" --resources "$compose" --tags Key=Ambiente,Value=staging-entregado
echo "Ambiente=staging-entregado: ya no recibe despliegues; sigue encendida y con inventaio-staging.duckdns.org"

paso "Máquinas del proyecto"
maquinas

paso "3. Lo que sigue"
cat <<'EOF'
  a. La máquina nueva pasa a Ambiente=staging (el repositorio ya lo trae por defecto):
       bash despliegue/aws/tofu.sh staging plan      # 1 to add, 1 to change, 1 to destroy: la etiqueta y la alarma de créditos
       bash despliegue/aws/tofu.sh staging apply
  b. En GitHub → Settings → Environments → staging → Environment variables: URL_PUBLICA = la url_publica de
       bash despliegue/aws/tofu.sh staging output -raw url_publica
EOF
