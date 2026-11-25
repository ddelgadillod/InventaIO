#!/usr/bin/env bash
# InventAI/o — Métricas de la máquina de staging durante una corrida de carga de INV-41 (docs/INV-41-requerimientos.md,
# T7). En AWS CloudShell (us-east-2), con las horas en UTC que imprime correr.sh:
#   bash pruebas/carga/metricas_ec2.sh 2026-11-25T20:00:00Z 2026-11-25T20:06:00Z
# Imprime, minuto a minuto, la CPU, la memoria, el disco y los créditos de CPU que se cobraron, y al final el
# promedio y el máximo de cada uno. Solo porcentajes: no muestra el número de la cuenta ni el de la máquina.
set -euo pipefail

REGION=us-east-2
NOMBRE=${NOMBRE:-inventaio-staging-k3s}
export AWS_PAGER=""

fallar() { echo "ERROR: $*" >&2; exit 2; }
[[ $# -eq 2 ]] || fallar "uso: metricas_ec2.sh INICIO FIN (UTC, por ejemplo 2026-11-25T20:00:00Z)"
inicio=$1 fin=$2
command -v jq >/dev/null || fallar "falta jq (CloudShell lo trae)"

id=$(aws ec2 describe-instances --region "$REGION" \
    --filters "Name=tag:Name,Values=$NOMBRE" Name=instance-state-name,Values=running \
    --query 'Reservations[].Instances[].InstanceId' --output text)
[[ $(wc -w <<<"$id") -eq 1 ]] || fallar "se esperaba una sola máquina $NOMBRE encendida"

# metrica ESPACIO NOMBRE ESTADISTICA [dimensiones extra]: «hora valor» por minuto
metrica() {
    local espacio=$1 nombre=$2 estadistica=$3; shift 3
    aws cloudwatch get-metric-statistics --region "$REGION" --namespace "$espacio" --metric-name "$nombre" \
        --dimensions "Name=InstanceId,Value=$id" "$@" --start-time "$inicio" --end-time "$fin" \
        --period 60 --statistics "$estadistica" --output json |
        jq -r --arg e "$estadistica" '.Datapoints | sort_by(.Timestamp)[] | "\(.Timestamp[11:16]) \(.[$e])"'
}

declare -A series
series[cpu]=$(metrica AWS/EC2 CPUUtilization Maximum)
series[memoria]=$(metrica CWAgent mem_used_percent Maximum)
series[disco]=$(metrica CWAgent disk_used_percent Maximum)
series[creditos]=$(metrica AWS/EC2 CPUSurplusCreditsCharged Sum)

printf '%-6s %8s %10s %8s %10s\n' "UTC" "CPU %" "Memoria %" "Disco %" "Créditos"
join -a1 -e- -o auto <(echo "${series[cpu]}") <(echo "${series[memoria]}") |
    join -a1 -e- -o auto - <(echo "${series[disco]}") |
    join -a1 -e- -o auto - <(echo "${series[creditos]}") |
    awk '{ printf "%-6s %8s %10s %8s %10s\n", $1, $2, $3, $4, $5 }'

echo
for m in cpu memoria disco creditos; do
    awk -v m="$m" 'NF==2 { s+=$2; n++; if ($2>x) x=$2 } END {
        if (n) printf "%-9s promedio %6.1f   máximo %6.1f   (%d minutos)\n", m, s/n, x, n
        else printf "%-9s sin datos en ese tramo\n", m }' <<<"${series[$m]}"
done
