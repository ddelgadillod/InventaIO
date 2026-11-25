#!/usr/bin/env bash
# InventAI/o — OWASP ZAP baseline contra staging (INV-41, docs/INV-41-requerimientos.md, sección 4.5). Escaneo pasivo:
# la araña tradicional y la AJAX recorren la web pública sin sesión, y ZAP revisa cada respuesta sin atacar. Desde la
# raíz del repositorio:
#   bash pruebas/seguridad/zap_baseline.sh
# Variables: BASE_URL (por defecto, el staging en CloudFront) y MINUTOS de araña (por defecto 3).
#
# Deja el reporte HTML y JSON en evidencias/inv41/, que no se publica, y resume las alertas por riesgo. La API con
# sesión la cubre zap_api_pasivo.sh.
set -euo pipefail

# ZAP estable del 3-nov-2026, fijado por su huella (índice multiplataforma)
IMAGEN=ghcr.io/zaproxy/zaproxy@sha256:9624669db72f54d86c4b46a7064518bd9bf79d8c61a4c31befa9923489f328af
RAIZ=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
BASE=${BASE_URL:-https://d32ramysc8c7pj.cloudfront.net}
SALIDA=$RAIZ/evidencias/inv41
nombre=zap-baseline-$(date +%Y%m%d-%H%M)

mkdir -p "$SALIDA"
estado=0
# -j: araña AJAX, que entiende la aplicación de una página; -a: también las reglas pasivas alfa;
# -I: un aviso no es un error del script; el resultado se lee en el reporte
docker run --rm -u "$(id -u):$(id -g)" -v "$SALIDA:/zap/wrk:rw" "$IMAGEN" \
    zap-baseline.py -t "$BASE" -j -a -I -m "${MINUTOS:-3}" \
    -r "$nombre.html" -J "$nombre.json" || estado=$?

[[ -s $SALIDA/$nombre.json ]] || { echo "ERROR: ZAP no dejó reporte (salida $estado)" >&2; exit 2; }
echo
echo "Reporte: evidencias/inv41/$nombre.html y .json"
python3 "$RAIZ/pruebas/seguridad/resumen_zap.py" "$SALIDA/$nombre.json"
