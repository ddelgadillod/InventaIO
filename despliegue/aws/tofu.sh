#!/usr/bin/env bash
# InventAI/o — OpenTofu desde AWS CloudShell para infra/<ambiente> (P10 y P11 del plan de staging en k3s con servicios
# serverless: docs/INFRA-k3s-serverless-requerimientos.md). Desde la raíz del repositorio clonado en CloudShell:
#   bash despliegue/aws/tofu.sh staging plan
#   bash despliegue/aws/tofu.sh staging apply
#   bash despliegue/aws/tofu.sh staging output
#
# La primera vez:
#   1. instala OpenTofu en ~/.local/bin, fijado por versión y SHA-256 (CloudShell conserva el directorio personal);
#   2. crea el bucket del estado, inventaio-tofu-<número de la cuenta>: cifrado, con versiones, sin acceso público y
#      solo por TLS. El bloqueo es nativo de S3 (use_lockfile), sin DynamoDB;
#   3. inicializa infra/<ambiente> con ese bucket.
# Después solo corre «tofu <comando>» en infra/<ambiente>. Las variables que no van en el repositorio (el correo de
# las alarmas y el bucket de volcados) se ponen en infra/<ambiente>/privado.auto.tfvars, que git ignora (infra/README.md).
set -euo pipefail

TOFU_VERSION=1.13.9         # 5-nov-2026
TOFU_SHA256=bc44eb6b06446ba83bd4072114891987f590f66cca712737a7f1147c50c539ce
REGION=us-east-2
RAIZ=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
export AWS_PAGER=""

fallar() { echo "ERROR: $*" >&2; exit 2; }
[[ $# -ge 2 ]] || fallar "uso: tofu.sh <staging|produccion> <plan|apply|output|…> [argumentos de tofu]"
AMBIENTE=$1
shift
DIR=$RAIZ/infra/$AMBIENTE
[[ -d $DIR ]] || fallar "no existe infra/$AMBIENTE (¿estás en la rama develop?)"
# Los proveedores van en /tmp: el de AWS ocupa unos 800 MB y el directorio personal de CloudShell tiene 1 GB (H33).
# /tmp se borra al cerrar la sesión y init los vuelve a bajar (~150 MB). El estado está en S3 y el bloqueo en el repo
export TF_DATA_DIR=${TF_DATA_DIR:-/tmp/inventaio-tofu/$AMBIENTE}

# ── OpenTofu ────────────────────────────────────────

TOFU=$HOME/.local/bin/tofu
if [[ ! -x $TOFU || $("$TOFU" version -json 2>/dev/null | jq -r .terraform_version 2>/dev/null) != "$TOFU_VERSION" ]]; then
    echo "== Instalando OpenTofu $TOFU_VERSION en ~/.local/bin"
    tmp=$(mktemp -d)
    curl -fsSL --retry 3 -o "$tmp/tofu.zip" \
        "https://github.com/opentofu/opentofu/releases/download/v$TOFU_VERSION/tofu_${TOFU_VERSION}_linux_amd64.zip"
    echo "$TOFU_SHA256  $tmp/tofu.zip" | sha256sum -c --quiet \
        || { rm -rf "$tmp"; fallar "la descarga de OpenTofu no coincide con su SHA-256"; }
    unzip -q -o "$tmp/tofu.zip" tofu -d "$tmp"
    install -D -m 755 "$tmp/tofu" "$TOFU"
    rm -rf "$tmp"
fi

# ── Bucket del estado ───────────────────────────────

CUENTA=$(aws sts get-caller-identity --query Account --output text)
BUCKET=inventaio-tofu-$CUENTA
if ! aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
    echo "== Creando el bucket del estado"
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
        --create-bucket-configuration LocationConstraint="$REGION" >/dev/null
    aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
        BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
    aws s3api put-bucket-versioning --bucket "$BUCKET" --versioning-configuration Status=Enabled
    aws s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration \
        '{"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}, "BucketKeyEnabled": true}]}'
    aws s3api put-bucket-policy --bucket "$BUCKET" --policy "$(jq -n --arg b "$BUCKET" '{
        Version: "2012-10-17",
        Statement: [{Sid: "SoloTLS", Effect: "Deny", Principal: "*", Action: "s3:*",
                     Resource: ["arn:aws:s3:::\($b)", "arn:aws:s3:::\($b)/*"],
                     Condition: {Bool: {"aws:SecureTransport": "false"}}}]}')"
    aws s3api put-bucket-tagging --bucket "$BUCKET" --tagging 'TagSet=[{Key=Proyecto,Value=inventaio}]'
fi

# ── OpenTofu en infra/<ambiente> ────────────────────

# Con -reconfigure cada vez: el bucket no va en el repositorio, así que no queda guardado en otra parte
"$TOFU" -chdir="$DIR" init -input=false -reconfigure -lockfile=readonly -backend-config="bucket=$BUCKET" >/dev/null \
    || { "$TOFU" -chdir="$DIR" init -input=false -reconfigure -lockfile=readonly -backend-config="bucket=$BUCKET"; exit 2; }
exec "$TOFU" -chdir="$DIR" "$@"
