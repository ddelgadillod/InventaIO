#!/usr/bin/env bash
# InventAI/o — Verificación de la cuenta de AWS antes de crear la infraestructura de k3s y los servicios serverless
# (fase 0 de docs/INFRA-k3s-serverless-requerimientos.md).
#
# Solo lee: listados, descripciones, cuotas y simulaciones de EC2 con --dry-run, que no crean nada ni cobran.
# Se corre en AWS CloudShell, abierto en la región us-east-2 (Ohio), con el usuario de la consola:
#   bash verificar_cuenta.sh
#
# Imprime solo el nombre de cada prueba y su resultado. Nunca muestra el número de la cuenta, ARN, IP ni nombres de
# recursos, así que la salida se puede copiar tal cual.
#
# Resultados:
#   OK                              la llamada funcionó
#   OK (se permitiría)              la simulación de EC2 dice que crear el recurso estaría permitido
#   BLOQUEADO por la organización   lo niega una política de la organización de AWS (SCP), como pasó con Bedrock
#   SIN PERMISO del usuario         lo niega la política de IAM del usuario de la consola
#   SERVICIO NO ACTIVADO            el servicio pide activarse o suscribirse en la cuenta
#   ERROR (<código>)                otro error; el código basta para diagnosticarlo
#
# Una lectura que funciona no garantiza que crear también funcione (una política podría negar solo la creación). Por
# eso EC2 se prueba con --dry-run, y lo demás se confirma al aplicar la infraestructura.
set -uo pipefail

REGION=${REGION:-us-east-2}
GLOBAL=us-east-1      # CloudFront, su certificado (ACM) y las métricas de los chequeos de Route 53 viven aquí
export AWS_PAGER=""

ok=0; negado=0; errores=0
# Relleno por caracteres y no por bytes, para que las tildes no corran la columna
fila() { local n=${#1}; printf '  %s%*s %s\n' "$1" $((n < 60 ? 60 - n : 0)) '' "$2"; }
seccion() { printf '\n%s\n' "$1"; }

# Clasifica el error de la CLI sin mostrar su texto. Devuelve 2 si es una negación y 1 si es otro error
clasificar() {
    local salida=$1 codigo
    if grep -qi 'service control polic' <<<"$salida"; then echo "BLOQUEADO por la organización"; return 2; fi
    if grep -qiE 'AccessDenied|UnauthorizedOperation|not authorized' <<<"$salida"; then echo "SIN PERMISO del usuario"; return 2; fi
    if grep -qiE 'OptInRequired|SubscriptionRequired|not subscribed' <<<"$salida"; then echo "SERVICIO NO ACTIVADO"; return 2; fi
    codigo=$(grep -oE 'An error occurred \([A-Za-z0-9.]+\)' <<<"$salida" | head -n 1 | sed -E 's/.*\((.*)\)/\1/')
    echo "ERROR (${codigo:-sin código})"
    return 1
}

contar() {
    local rc=$1
    if [[ $rc -eq 0 ]]; then ok=$((ok + 1)); elif [[ $rc -eq 2 ]]; then negado=$((negado + 1)); else errores=$((errores + 1)); fi
}

# leer "nombre" comando…: corre una lectura y muestra solo si funcionó
leer() {
    local nombre=$1 salida resultado rc
    shift
    if salida=$("$@" 2>&1 >/dev/null); then
        fila "$nombre" "OK"; contar 0
    else
        resultado=$(clasificar "$salida"); rc=$?
        fila "$nombre" "$resultado"; contar "$rc"
    fi
}

# simular "nombre" comando…: EC2 con --dry-run; «DryRunOperation» quiere decir que estaría permitido
simular() {
    local nombre=$1 salida resultado rc
    shift
    salida=$("$@" --dry-run 2>&1 >/dev/null)
    if grep -q 'DryRunOperation' <<<"$salida"; then
        fila "$nombre" "OK (se permitiría)"; contar 0
    else
        resultado=$(clasificar "$salida"); rc=$?
        fila "$nombre" "$resultado"; contar "$rc"
    fi
}

# valor "nombre" comando…: muestra un valor no sensible (un número, un estado o una versión)
valor() {
    local nombre=$1 salida resultado rc
    shift
    if salida=$("$@" 2>&1); then
        fila "$nombre" "${salida:-vacío}"; contar 0
    else
        resultado=$(clasificar "$salida"); rc=$?
        fila "$nombre" "$resultado"; contar "$rc"
    fi
}

echo "InventAI/o · verificación de la cuenta · región $REGION · $(date '+%Y-%m-%d %H:%M')"

seccion "Identidad"
if arn=$(aws sts get-caller-identity --query Arn --output text 2>/dev/null); then
    if [[ $arn == *":root" ]]; then
        fila "Tipo de usuario" "RAÍZ (conviene un usuario de IAM o de Identity Center)"
    else
        fila "Tipo de usuario" "usuario de IAM o rol"
    fi
    cuenta=$(aws sts get-caller-identity --query Account --output text)
    contar 0
else
    fila "Tipo de usuario" "ERROR: CloudShell no tiene credenciales"
    exit 1
fi
valor "Plan de la cuenta (FREE o PAID; si la CLI lo trae)" aws freetier get-account-plan-state --region "$GLOBAL" \
    --query accountPlanType --output text

seccion "EC2 (simulaciones: no crean nada)"
ami=$(aws ssm get-parameter --region "$REGION" --query Parameter.Value --output text \
    --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 2>/dev/null || true)
if [[ -n $ami ]]; then
    simular "Lanzar una t3.medium con Amazon Linux 2023" aws ec2 run-instances --region "$REGION" \
        --image-id "$ami" --instance-type t3.medium --count 1
    simular "Lanzar una t3.large (por si la medición la pide)" aws ec2 run-instances --region "$REGION" \
        --image-id "$ami" --instance-type t3.large --count 1
else
    fila "Imagen de Amazon Linux 2023" "ERROR (no se pudo leer el parámetro público)"; contar 1
fi
simular "Reservar una IP elástica" aws ec2 allocate-address --region "$REGION" --domain vpc
simular "Crear un grupo de seguridad" aws ec2 create-security-group --region "$REGION" \
    --group-name inventaio-verificacion --description "Verificacion sin crear"
valor "Estado del staging actual" aws ec2 describe-instances --region "$REGION" \
    --filters Name=tag:Name,Values=inventaio-staging --query 'Reservations[].Instances[].State.Name' --output text
valor "Cuota de vCPU On-Demand estándar (hacen falta 8)" aws service-quotas get-service-quota --region "$REGION" \
    --service-code ec2 --quota-code L-1216C47A --query Quota.Value --output text
valor "Cuota de IP elásticas (hacen falta 3)" aws service-quotas get-service-quota --region "$REGION" \
    --service-code ec2 --quota-code L-0263D0A3 --query Quota.Value --output text
valor "IP elásticas en uso" aws ec2 describe-addresses --region "$REGION" --query 'length(Addresses)' --output text
valor "Hay VPC por defecto (True o vacío)" aws ec2 describe-vpcs --region "$REGION" \
    --filters Name=is-default,Values=true --query 'Vpcs[].IsDefault' --output text
valor "Entradas de la lista de CloudFront para el origen" aws ec2 describe-managed-prefix-lists --region "$REGION" \
    --filters Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing \
    --query 'PrefixLists[0].MaxEntries' --output text
valor "Reglas de entrada por grupo de seguridad (cuota)" aws service-quotas get-service-quota --region "$REGION" \
    --service-code vpc --quota-code L-0EA8095F --query Quota.Value --output text
leer "Instantáneas automáticas del disco (DLM)" aws dlm get-lifecycle-policies --region "$REGION"

seccion "IAM"
leer "Listar proveedores OIDC" aws iam list-open-id-connect-providers
valor "Proveedor OIDC de GitHub ya creado (1 = sí, 0 = no)" aws iam list-open-id-connect-providers \
    --query "length(OpenIDConnectProviderList[?contains(Arn, 'token.actions.githubusercontent.com')])" --output text
leer "Rol de la instancia de staging (inventaio-staging-ec2)" aws iam get-role --role-name inventaio-staging-ec2
leer "Listar roles" aws iam list-roles --max-items 1

seccion "Session Manager y Parameter Store"
valor "Máquinas administradas por Session Manager" aws ssm describe-instance-information --region "$REGION" \
    --query 'length(InstanceInformationList)' --output text
leer "Documentos propios de Session Manager" aws ssm list-documents --region "$REGION" \
    --filters Key=Owner,Values=Self --max-results 1
leer "Parameter Store" aws ssm describe-parameters --region "$REGION" --max-results 1

seccion "S3, CloudFront y certificados"
leer "Listar buckets de S3" aws s3api list-buckets --max-buckets 1
leer "CloudFront: distribuciones" aws cloudfront list-distributions --max-items 1
leer "CloudFront: políticas de cabeceras" aws cloudfront list-response-headers-policies --type managed --max-items 1
leer "CloudFront: control de acceso al origen" aws cloudfront list-origin-access-controls --max-items 1
leer "Certificados (ACM) en us-east-1" aws acm list-certificates --region "$GLOBAL" --max-items 1

seccion "Route 53"
leer "Chequeos de salud" aws route53 list-health-checks --max-items 1
leer "Zonas de DNS" aws route53 list-hosted-zones --max-items 1

seccion "Monitoreo, avisos y horarios"
leer "CloudWatch: alarmas en $REGION" aws cloudwatch describe-alarms --region "$REGION" --max-records 1
leer "CloudWatch: alarmas en $GLOBAL" aws cloudwatch describe-alarms --region "$GLOBAL" --max-records 1
leer "CloudWatch Logs" aws logs describe-log-groups --region "$REGION" --limit 1
leer "SNS: temas" aws sns list-topics --region "$REGION"
leer "EventBridge Scheduler" aws scheduler list-schedules --region "$REGION" --max-results 1
valor "Presupuestos de AWS Budgets" aws budgets describe-budgets --region "$GLOBAL" --account-id "$cuenta" \
    --query 'length(Budgets || `[]`)' --output text

seccion "RDS"
leer "Listar bases de RDS" aws rds describe-db-instances --region "$REGION" --max-records 20
valor "PostgreSQL 16 en db.t4g.micro (versión más reciente)" aws rds describe-orderable-db-instance-options \
    --region "$REGION" --engine postgres --db-instance-class db.t4g.micro \
    --query "max(OrderableDBInstanceOptions[?starts_with(EngineVersion, '16.')].EngineVersion)" --output text

printf '\nResumen: %d OK · %d negadas · %d errores\n' "$ok" "$negado" "$errores"
echo "Copia esta salida completa en el chat: no contiene datos de la cuenta."
