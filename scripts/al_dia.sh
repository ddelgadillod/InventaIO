#!/usr/bin/env bash
# InventAI/o — Al encender, la máquina se pone al día con develop (P16 del plan de staging en k3s:
# docs/INFRA-k3s-serverless-requerimientos.md). De noche staging está apagado y el workflow «Desplegar» solo avisa que
# no desplegó, aunque la web en S3 sí quede al día; a las 7:00 la máquina despliega el último commit de develop.
#
# Lo corre el servicio inventaio-al-dia (despliegue/systemd/inventaio-al-dia.service, que instala preparar_k3s.sh en
# staging) como ec2-user al arrancar. A mano: bash /opt/inventaio/repo/scripts/al_dia.sh
# Sale como scripts/desplegar.sh (0, 1 o 2), o con 0 si ya estaba al día o todavía no hubo un primer despliegue.
set -euo pipefail

BASE=${INVENTAIO_BASE:-/opt/inventaio}
REPOSITORIO=ddelgadillod/InventaIO

[[ -s $BASE/estado/actual ]] || { echo "Todavía no hay un primer despliegue (desplegar.sh <tag> --primera-vez)"; exit 0; }
actual=$(cat "$BASE/estado/actual")

# Hasta 5 minutos para la red y para k3s
for _ in $(seq 60); do
    curl -fsS --max-time 5 -o /dev/null https://api.github.com && kubectl get --raw /readyz >/dev/null 2>&1 && break
    sleep 5
done

commit=$(curl -fsS --max-time 20 "https://api.github.com/repos/$REPOSITORIO/commits/develop" \
    | python3 -c 'import json, sys; print(json.load(sys.stdin)["sha"][:7])') \
    || { echo "No se pudo leer el último commit de develop"; exit 2; }
tag=sha-$commit
if [[ $tag == "$actual" ]]; then
    echo "Al día: $actual"
    exit 0
fi

echo "En la máquina está $actual y develop va en $tag"
# Como el documento de Session Manager: el clon al día y el despliegue con humo. Si las imágenes de ese commit todavía
# no están en GHCR (el workflow «Imágenes» sigue corriendo), desplegar.sh se detiene sin tocar nada
git -C "$BASE/repo" pull --ff-only --quiet || { echo "No se pudo actualizar el clon"; exit 2; }
exec bash "$BASE/repo/scripts/desplegar.sh" "$tag"
