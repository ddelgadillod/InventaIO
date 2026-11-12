#!/usr/bin/env bash
# InventAI/o — Valida una migración: compara la huella de la base con la del origen (INV-34, B8).
#
# Saca la huella de la base a la que apuntan las variables PG* y la compara, línea por
# línea, con CARPETA/huella.txt (la que dejó volcar.sh en el origen). La huella del
# destino queda en la carpeta (huella-destino.txt); si algo difiere, también su detalle
# (huella-destino-detalle.txt). Ninguna se sube. En la salida solo van los nombres de las
# comprobaciones, nunca sus valores, porque los registros del CI son públicos.
# Sale con 0 si todo coincide, con 1 si algo difiere y con 2 si hubo un error.
#   bash scripts/bd/validar.sh CARPETA
set -euo pipefail
source "$(dirname "$0")/comun.sh"

[[ $# -eq 1 && -f "$1/huella.txt" ]] || fallar "uso: validar.sh CARPETA (con la huella.txt del origen)"
CARPETA=$(cd "$1" && pwd)

exigir_conexion
inicio=$(date +%s)
huella "$CARPETA/huella-destino.txt"

# Compara por nombre: lo que falta en un lado también es una diferencia. H8 además debe
# decir «al dia» en el destino, aunque el origen también estuviera atrasado
difieren=$(awk -F'|' '
    NR == FNR { origen[$1] = $2; next }
    { destino[$1] = $2 }
    END {
        for (n in origen) if (!(n in destino) || destino[n] != origen[n]) print n
        for (n in destino) {
            if (!(n in origen)) print n
            else if (n ~ /^H8 / && destino[n] != "al dia" && destino[n] == origen[n]) print n
        }
    }' "$CARPETA/huella.txt" "$CARPETA/huella-destino.txt" | sort)
total=$(wc -l < "$CARPETA/huella.txt")

if [[ -z "$difieren" ]]; then
    echo "PASÓ: ${total} comprobaciones iguales al origen ($(( $(date +%s) - inicio )) s)"
    exit 0
fi
huella "$CARPETA/huella-destino-detalle.txt" detalle
segundos=$(( $(date +%s) - inicio ))
echo "NO PASÓ: $(printf '%s\n' "$difieren" | wc -l) de ${total} comprobaciones difieren (${segundos} s):"
sed 's/^/  /' <<< "$difieren"
echo "El detalle está en $CARPETA/huella-destino-detalle.txt; compáralo con huella-detalle.txt del origen."
exit 1
