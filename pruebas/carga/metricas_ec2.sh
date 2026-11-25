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

# Todas las horas de las cuatro series: la CPU de EC2 llega cada 5 minutos sin el monitoreo detallado, y la memoria
# y el disco del agente cada minuto
{
    for m in cpu memoria disco creditos; do sed "s/^/$m /" <<<"${series[$m]}"; done
} | awk 'NF == 3 { v[$2, $1] = $3; h[$2] = 1 }
    END {
        printf "%-6s %8s %10s %8s %10s\n", "UTC", "CPU %", "Memoria %", "Disco %", "Créditos"
        n = asorti(h, horas)
        for (i = 1; i <= n; i++) {
            t = horas[i]; printf "%-6s", t
            split("cpu memoria disco creditos", ms, " ")
            for (k = 1; k <= 4; k++) {
                ancho = (k == 2 || k == 4) ? 10 : 8
                if ((t, ms[k]) in v) printf " %*.1f", ancho, v[t, ms[k]]; else printf " %*s", ancho, "-"
            }
            printf "\n"
        }
    }'
echo "La CPU de EC2 es el máximo de cada tramo de 5 minutos."

echo
for m in cpu memoria disco creditos; do
    awk -v m="$m" 'NF==2 { s+=$2; n++; if ($2>x) x=$2 } END {
        if (n) printf "%-9s promedio %6.1f   máximo %6.1f   (%d minutos)\n", m, s/n, x, n
        else printf "%-9s sin datos en ese tramo\n", m }' <<<"${series[$m]}"
done
