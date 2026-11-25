#!/usr/bin/env bash
# InventAI/o — Corre el guion de carga de INV-41 (docs/INV-41-requerimientos.md, sección 4.4) desde el equipo de
# desarrollo y guarda el resumen de k6 en evidencias/inv41/, que no se publica. Desde la raíz del repositorio:
#   bash pruebas/carga/correr.sh lectura 10
#   bash pruebas/carga/correr.sh lectura 20
#   bash pruebas/carga/correr.sh lectura escalera
#   bash pruebas/carga/correr.sh vera
#   bash pruebas/carga/correr.sh recorrido          # una vuelta, para el escaneo pasivo de ZAP
# Variables: BASE_URL (por defecto, el staging en CloudFront), CLAVES (por defecto ~/.config/inventaio/
# claves-staging.json), DURACION y PAUSA (ver inventaio.js), K6 (por defecto, k6 del PATH o ~/.local/bin/k6) y las de proxy (HTTPS_PROXY) para ZAP.
#
# Al final imprime la hora de inicio y de fin en UTC, que es lo que pide metricas_ec2.sh en CloudShell.
set -euo pipefail

RAIZ=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
ESCENARIO=${1:-lectura}
PERFIL=${2:-10}
CLAVES=${CLAVES:-$HOME/.config/inventaio/claves-staging.json}
K6=${K6:-$(command -v k6 || echo "$HOME/.local/bin/k6")}
SALIDA=$RAIZ/evidencias/inv41

fallar() { echo "ERROR: $*" >&2; exit 2; }

[[ -x $K6 ]] || fallar "no está k6: ver pruebas/carga/README.md"
[[ -r $CLAVES ]] || fallar "no está el archivo de claves $CLAVES"
case $ESCENARIO in
    lectura) [[ $PERFIL =~ ^([0-9]+|escalera)$ ]] || fallar "PERFIL es un número o escalera" ;;
    vera | recorrido) PERFIL=- ;;
    *) fallar "uso: correr.sh lectura|vera|recorrido [10|20|escalera]" ;;
esac

mkdir -p "$SALIDA"
nombre=k6-$ESCENARIO${PERFIL/#-/}-$(date +%Y%m%d-%H%M)
inicio=$(date -u +%Y-%m-%dT%H:%M:%SZ)
estado=0
variables=(-e "ESCENARIO=$ESCENARIO" -e "PERFIL=$PERFIL" -e "CLAVES=$CLAVES" -e "ZAP=${ZAP:-0}")
[[ -n ${BASE_URL:-} ]] && variables+=(-e "BASE_URL=$BASE_URL")
[[ -n ${DURACION:-} ]] && variables+=(-e "DURACION=$DURACION")
[[ -n ${PAUSA:-} ]] && variables+=(-e "PAUSA=$PAUSA")
"$K6" run --quiet "${variables[@]}" \
    --summary-export "$SALIDA/$nombre.json" \
    "$RAIZ/pruebas/carga/inventaio.js" | tee "$SALIDA/$nombre.txt" || estado=$?
fin=$(date -u +%Y-%m-%dT%H:%M:%SZ)

echo
echo "Resumen: evidencias/inv41/$nombre.json y .txt"
echo "Para las métricas de la EC2, en CloudShell: bash pruebas/carga/metricas_ec2.sh $inicio $fin"
# k6 sale con 99 si algún umbral no se cumplió: es un resultado, no una falla del script
exit "$estado"
