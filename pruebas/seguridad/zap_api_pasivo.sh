#!/usr/bin/env bash
# InventAI/o — Escaneo pasivo de la API con sesión (INV-41, docs/INV-41-requerimientos.md, D1 y sección 4.5). ZAP corre
# como proxy en este equipo; el recorrido de k6 (login, cada pantalla, renovar y cerrar sesión) pasa por él, y ZAP
# revisa cada respuesta sin atacar. Desde la raíz del repositorio:
#   bash pruebas/seguridad/zap_api_pasivo.sh
# Necesita k6 y el archivo de claves, como pruebas/carga/correr.sh. Deja el reporte en evidencias/inv41/.
set -euo pipefail

IMAGEN=ghcr.io/zaproxy/zaproxy@sha256:9624669db72f54d86c4b46a7064518bd9bf79d8c61a4c31befa9923489f328af
RAIZ=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
SALIDA=$RAIZ/evidencias/inv41
PUERTO=${PUERTO:-8090}
ZAP_API=http://127.0.0.1:$PUERTO
CONTENEDOR=inventaio-zap-pasivo
nombre=zap-api-pasivo-$(date +%Y%m%d-%H%M)

fallar() { echo "ERROR: $*" >&2; exit 2; }
mkdir -p "$SALIDA"

docker rm -f "$CONTENEDOR" >/dev/null 2>&1 || true
trap 'docker rm -f "$CONTENEDOR" >/dev/null 2>&1 || true' EXIT
# La API de ZAP sin llave, pero solo en 127.0.0.1 de este equipo
docker run -d --name "$CONTENEDOR" -p "127.0.0.1:$PUERTO:8090" "$IMAGEN" \
    zap.sh -daemon -host 0.0.0.0 -port 8090 -config api.disablekey=true \
    -config api.addrs.addr.name='.*' -config api.addrs.addr.regex=true >/dev/null

echo "== Esperando a ZAP"
for _ in $(seq 60); do curl -sf "$ZAP_API/JSON/core/view/version/" >/dev/null && break; sleep 3; done
curl -sf "$ZAP_API/JSON/core/view/version/" | python3 -c 'import json,sys; print("ZAP", json.load(sys.stdin)["version"])' ||
    fallar "ZAP no arrancó"

echo "== Recorrido de k6 a través de ZAP"
HTTPS_PROXY=http://127.0.0.1:$PUERTO HTTP_PROXY=http://127.0.0.1:$PUERTO ZAP=1 \
    bash "$RAIZ/pruebas/carga/correr.sh" recorrido >/dev/null || fallar "el recorrido de k6 falló"
vistos=$(curl -sf "$ZAP_API/JSON/core/view/numberOfMessages/?baseurl=" | python3 -c 'import json,sys; print(json.load(sys.stdin)["numberOfMessages"])')
echo "ZAP vio $vistos respuestas"
[[ $vistos -gt 0 ]] || fallar "el tráfico no pasó por ZAP"

echo "== Escaneo pasivo"
for _ in $(seq 100); do
    quedan=$(curl -sf "$ZAP_API/JSON/pscan/view/recordsToScan/" | python3 -c 'import json,sys; print(json.load(sys.stdin)["recordsToScan"])')
    [[ $quedan == 0 ]] && break
    sleep 3
done

curl -sf "$ZAP_API/OTHER/core/other/jsonreport/" -o "$SALIDA/$nombre.json"
curl -sf "$ZAP_API/OTHER/core/other/htmlreport/" -o "$SALIDA/$nombre.html"
echo
echo "Reporte: evidencias/inv41/$nombre.html y .json"
python3 "$RAIZ/pruebas/seguridad/resumen_zap.py" "$SALIDA/$nombre.json"
