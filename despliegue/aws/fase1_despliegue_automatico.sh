#!/usr/bin/env bash
# InventAI/o — Fase 1: lo mínimo en AWS para el despliegue automático a staging
# (docs/INFRA-k3s-serverless-requerimientos.md). Crea o actualiza, sin tocar lo que corre:
#   1. el presupuesto mensual «inventaio-mensual», con avisos por correo al 50, 80 y 100 % del gasto real y al 100 %
#      del pronóstico;
#   2. el proveedor OIDC de GitHub Actions;
#   3. el rol inventaio-gha-staging, en el que solo confía el entorno «staging» de este repositorio, y que solo puede
#      mandar el documento de despliegue a las máquinas con la etiqueta Ambiente=staging y leer su resultado;
#   4. el documento de Session Manager inventaio-desplegar (inventaio-desplegar.json, en la misma carpeta);
#   5. las etiquetas Proyecto=inventaio y Ambiente=staging en la instancia inventaio-staging (Ambiente, solo si no
#      tiene: después del corte de la fase 5 lleva staging-entregado).
#
# Es idempotente: se puede correr otra vez. Se corre en AWS CloudShell (us-east-2), con este archivo e
# inventaio-desplegar.json en la misma carpeta:
#   bash fase1_despliegue_automatico.sh                       # pregunta el correo
#   CORREO=… PRESUPUESTO_USD=100 bash fase1_despliegue_automatico.sh
#
# Al final muestra el ARN del rol, que va en el secreto AWS_ROL_DESPLIEGUE del entorno «staging» de GitHub. No lo
# pegues en el chat: contiene el número de la cuenta.
set -euo pipefail

REGION=${REGION:-us-east-2}
REPO_GITHUB=ddelgadillod/InventaIO
ENTORNO=staging
ROL=inventaio-gha-staging
DOCUMENTO=inventaio-desplegar
PRESUPUESTO=inventaio-mensual
PRESUPUESTO_USD=${PRESUPUESTO_USD:-100}
OIDC=token.actions.githubusercontent.com
DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
DOC_JSON=$DIR/inventaio-desplegar.json
export AWS_PAGER=""

paso() { printf '\n== %s\n' "$*"; }
fallar() { echo "ERROR: $*" >&2; exit 2; }

command -v jq >/dev/null || fallar "falta jq (CloudShell lo trae)"
[[ -f $DOC_JSON ]] || fallar "falta $DOC_JSON: súbelo a la misma carpeta que este script"
jq -e . "$DOC_JSON" >/dev/null || fallar "$DOC_JSON no es JSON válido"
[[ -n ${CORREO:-} ]] || read -r -p "Correo para los avisos del presupuesto: " CORREO
[[ $CORREO =~ ^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$ ]] || fallar "correo no válido"
[[ $PRESUPUESTO_USD =~ ^[0-9]+$ ]] || fallar "PRESUPUESTO_USD debe ser un número entero"
CUENTA=$(aws sts get-caller-identity --query Account --output text)

# ── 1. Presupuesto ──────────────────────────────────

paso "1. Presupuesto mensual de US\$$PRESUPUESTO_USD con avisos por correo"
presupuesto=$(jq -n --arg nombre "$PRESUPUESTO" --arg monto "$PRESUPUESTO_USD" \
    '{BudgetName: $nombre, BudgetLimit: {Amount: $monto, Unit: "USD"}, TimeUnit: "MONTHLY", BudgetType: "COST"}')
avisos=$(jq -n --arg correo "$CORREO" '
    [ [50, "ACTUAL"], [80, "ACTUAL"], [100, "ACTUAL"], [100, "FORECASTED"] ]
    | map({Notification: {NotificationType: .[1], ComparisonOperator: "GREATER_THAN", Threshold: .[0],
                          ThresholdType: "PERCENTAGE"},
           Subscribers: [{SubscriptionType: "EMAIL", Address: $correo}]})')
if aws budgets describe-budget --region us-east-1 --account-id "$CUENTA" --budget-name "$PRESUPUESTO" >/dev/null 2>&1; then
    aws budgets update-budget --region us-east-1 --account-id "$CUENTA" --new-budget "$presupuesto"
    echo "Ya existía: se actualizó el monto; los avisos quedan como estaban"
else
    aws budgets create-budget --region us-east-1 --account-id "$CUENTA" --budget "$presupuesto" \
        --notifications-with-subscribers "$avisos"
    echo "Creado, con avisos al 50, 80 y 100 % del gasto real y al 100 % del pronóstico"
fi

# ── 2. Proveedor OIDC de GitHub ─────────────────────

paso "2. Proveedor OIDC de GitHub Actions"
ARN_OIDC=arn:aws:iam::$CUENTA:oidc-provider/$OIDC
if aws iam get-open-id-connect-provider --open-id-connect-provider-arn "$ARN_OIDC" >/dev/null 2>&1; then
    aws iam add-client-id-to-open-id-connect-provider --open-id-connect-provider-arn "$ARN_OIDC" \
        --client-id sts.amazonaws.com >/dev/null 2>&1 || true
    echo "Ya existía"
else
    # Las huellas ya no se usan para GitHub (IAM confía en su autoridad de certificados), pero la API las acepta
    aws iam create-open-id-connect-provider --url "https://$OIDC" --client-id-list sts.amazonaws.com \
        --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 1c58a3a8518e8759bf075b76b750d4f2df264fcd \
        --tags Key=Proyecto,Value=inventaio >/dev/null
    echo "Creado"
fi

# ── 3. Rol de GitHub para staging ───────────────────

paso "3. Rol $ROL"
confianza=$(jq -n --arg proveedor "$ARN_OIDC" --arg sub "repo:$REPO_GITHUB:environment:$ENTORNO" --arg oidc "$OIDC" '
    {Version: "2012-10-17",
     Statement: [{Effect: "Allow", Principal: {Federated: $proveedor}, Action: "sts:AssumeRoleWithWebIdentity",
                  Condition: {StringEquals: {($oidc + ":aud"): "sts.amazonaws.com", ($oidc + ":sub"): $sub}}}]}')
permisos=$(jq -n --arg region "$REGION" --arg cuenta "$CUENTA" --arg documento "$DOCUMENTO" --arg ambiente "$ENTORNO" '
    {Version: "2012-10-17",
     Statement: [
       {Sid: "DocumentoDeDespliegue", Effect: "Allow", Action: "ssm:SendCommand",
        Resource: "arn:aws:ssm:\($region):\($cuenta):document/\($documento)"},
       {Sid: "SoloMaquinasDelAmbiente", Effect: "Allow", Action: "ssm:SendCommand",
        Resource: "arn:aws:ec2:\($region):\($cuenta):instance/*",
        Condition: {StringEquals: {"ssm:resourceTag/Ambiente": $ambiente}}},
       {Sid: "LeerElResultado", Effect: "Allow", Action: ["ssm:GetCommandInvocation", "ssm:ListCommandInvocations"],
        Resource: "*"},
       {Sid: "EstadoDeLaMaquina", Effect: "Allow", Action: "ec2:DescribeInstances", Resource: "*"}]}')
if aws iam get-role --role-name "$ROL" >/dev/null 2>&1; then
    aws iam update-assume-role-policy --role-name "$ROL" --policy-document "$confianza"
    echo "Ya existía: confianza actualizada"
else
    aws iam create-role --role-name "$ROL" --assume-role-policy-document "$confianza" --max-session-duration 3600 \
        --description "InventAI/o: GitHub Actions despliega en staging por Session Manager" \
        --tags Key=Proyecto,Value=inventaio Key=Ambiente,Value=$ENTORNO >/dev/null
    echo "Creado"
fi
aws iam put-role-policy --role-name "$ROL" --policy-name desplegar --policy-document "$permisos"
echo "Permisos al día: el documento $DOCUMENTO, solo en máquinas con Ambiente=$ENTORNO"

# ── 4. Documento de Session Manager ─────────────────

paso "4. Documento $DOCUMENTO"
if aws ssm describe-document --region "$REGION" --name "$DOCUMENTO" >/dev/null 2>&1; then
    if version=$(aws ssm update-document --region "$REGION" --name "$DOCUMENTO" --content "file://$DOC_JSON" \
            --document-format JSON --document-version '$LATEST' \
            --query DocumentDescription.DocumentVersion --output text 2>&1); then
        aws ssm update-document-default-version --region "$REGION" --name "$DOCUMENTO" \
            --document-version "$version" >/dev/null
        echo "Actualizado: versión $version"
    elif grep -q DuplicateDocumentContent <<<"$version"; then
        echo "Sin cambios"
    else
        echo "$version" >&2
        fallar "no se pudo actualizar el documento"
    fi
else
    aws ssm create-document --region "$REGION" --name "$DOCUMENTO" --document-type Command --document-format JSON \
        --content "file://$DOC_JSON" --tags Key=Proyecto,Value=inventaio >/dev/null
    echo "Creado"
fi

# ── 5. Etiquetas de la instancia ────────────────────

paso "5. Etiquetas de la instancia inventaio-staging"
ids=$(aws ec2 describe-instances --region "$REGION" \
    --filters Name=tag:Name,Values=inventaio-staging Name=instance-state-name,Values=pending,running,stopping,stopped \
    --query 'Reservations[].Instances[].InstanceId' --output text)
[[ $(wc -w <<<"$ids") -eq 1 ]] || fallar "se esperaba una sola instancia inventaio-staging y hay $(wc -w <<<"$ids")"
# Solo si todavía no tiene Ambiente: después del corte (fase5_corte.sh) lleva staging-entregado y debe seguir así
actual=$(aws ec2 describe-tags --region "$REGION" --filters "Name=resource-id,Values=$ids" Name=key,Values=Ambiente \
    --query 'Tags[0].Value' --output text)
if [[ -z $actual || $actual == None ]]; then
    aws ec2 create-tags --region "$REGION" --resources "$ids" --tags Key=Proyecto,Value=inventaio Key=Ambiente,Value=$ENTORNO
    echo "Proyecto=inventaio y Ambiente=$ENTORNO"
else
    aws ec2 create-tags --region "$REGION" --resources "$ids" --tags Key=Proyecto,Value=inventaio
    echo "Proyecto=inventaio; conserva Ambiente=$actual"
fi

# ── Resultado ───────────────────────────────────────

paso "Listo"
cat <<EOF
Falta un paso en GitHub: Settings → Environments → staging → Environment secrets → Add secret
  Nombre: AWS_ROL_DESPLIEGUE
  Valor:  arn:aws:iam::$CUENTA:role/$ROL
No pegues el valor en el chat: contiene el número de la cuenta.
Los avisos del presupuesto llegan directo a $CORREO, sin confirmar la suscripción.
EOF
