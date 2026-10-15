#!/bin/bash
# ============================================================
# InventAI/o — Alertas con IA Test Script (curl)
# INV-28: GET /api/alertas/ml contra la bodega real (foto al 2025-12-31).
# Casos y cifras: docs/INV-28-requerimientos.md (P-01 a P-15).
# La primera llamada tras reiniciar el Core API tarda 20 a 40 s.
# Run: bash api/tests/test_alertas_ml.sh
# ============================================================

BASE="http://localhost:8000/api"
PASS=0
FAIL=0

green() { echo -e "\033[32m✅ $1\033[0m"; PASS=$((PASS+1)); }
red() { echo -e "\033[31m❌ $1\033[0m"; FAIL=$((FAIL+1)); }
header() { echo -e "\n\033[1;34m══ $1 ══\033[0m"; }
check() { [ "$2" = "$3" ] && green "$1" || red "$1: esperado $3, llegó $2"; }

login() {
  curl -s -X POST $BASE/auth/login -H "Content-Type: application/json" \
    -d "{\"email\":\"$1@inventaio.co\",\"password\":\"admin123\"}" | jq -r '.access_token'
}

TOK_GER=$(login gerente)
TOK_NORTE=$(login admin.norte)
if [ -z "$TOK_GER" ] || [ "$TOK_GER" = "null" ]; then
  echo -e "\033[31m❌ Could not login. Is the API running?\033[0m"
  exit 1
fi
green "Login OK — 2 tokens obtained"
AUTH_G="Authorization: Bearer $TOK_GER"
AUTH_N="Authorization: Bearer $TOK_NORTE"
URL="$BASE/alertas/ml"

# ══════════════════════════════════════════════════════
header "Cifras de la foto (gerente)"
# ══════════════════════════════════════════════════════
RESP=$(curl -s -m 180 "$URL" -H "$AUTH_G")
check "Estructura (items, total, resumen, fecha, políticas, calculado_en)" \
  "$(echo "$RESP" | jq 'has("items") and has("total") and has("resumen") and has("fecha_inventario") and has("politicas") and has("calculado_en")')" "true"
check "P-09 riesgo y sobrestock" "$(echo "$RESP" | jq -c '[.resumen.riesgo_desabastecimiento_ml, .resumen.sobrestock_previsto_ml]')" "[866,721]"
check "P-09 críticas, altas y medias" "$(echo "$RESP" | jq -c '[.resumen.critica, .resumen.alta, .resumen.media]')" "[483,383,721]"
check "P-09 origen ambos y ml" "$(echo "$RESP" | jq -c '[.resumen.ambos, .resumen.ml]')" "[395,1192]"
check "Foto del 2025-12-31" "$(echo "$RESP" | jq -r '.fecha_inventario')" "2025-12-31"
check "P-08 sin filas de la Bodega" "$(echo "$RESP" | jq '[.items[] | select(.tipo_ubicacion != "sucursal")] | length')" "0"
check "Orden: críticas primero" "$(echo "$RESP" | jq -r '.items[0].urgencia')" "critica"
check "P-07 traslado nombrado en 100 riesgos" "$(echo "$RESP" | jq '[.items[] | select(.detalle | contains("traslado sugerido"))] | length')" "100"

par() { echo "$RESP" | jq -c --arg c "$1" --arg s "$2" "[.items[] | select(.codigo_item == \$c and .sucursal == \$s) | $3]"; }

# ══════════════════════════════════════════════════════
header "Casos con productos reales"
# ══════════════════════════════════════════════════════
check "P-01 HUEVOS P1632 en PRINCIPAL: crítica, ambos" "$(par P1632 PRINCIPAL '[.tipo, .urgencia, .origen]')" '[["riesgo_desabastecimiento_ml","critica","ambos"]]'
check "P-02 BLQ CLOROX 00037 en PRINCIPAL: crítica, ml" "$(par 00037 PRINCIPAL '[.urgencia, .origen, .stock]')" '[["critica","ml",0.0]]'
check "P-03 CHOCOLAT JET 00002 en LA 21: sin alerta (q50 < 1)" "$(par 00002 'LA 21' '.tipo')" '[]'
check "P-04 AGUA CRISTAL 00008 en LA 21: sin alerta (stock -1)" "$(par 00008 'LA 21' '.tipo')" '[]'
check "P-05 CONDIMENTO EL TIZON 01108 en GLORIETA: sobrestock" "$(par 01108 GLORIETA '[.tipo, .urgencia, .valor]')" '[["sobrestock_previsto_ml","media",22.0]]'
check "P-15 HUEVOS P1632 en LA 21: alta en el borde (V11)" "$(par P1632 'LA 21' '[.urgencia, .valor]')" '[["alta",5.0]]'

# ══════════════════════════════════════════════════════
header "Filtros y paginación"
# ══════════════════════════════════════════════════════
check "tipo=sobrestock_previsto_ml" "$(curl -s "$URL?tipo=sobrestock_previsto_ml" -H "$AUTH_G" | jq '.total')" "721"
check "urgencia=critica" "$(curl -s "$URL?urgencia=critica" -H "$AUTH_G" | jq '.total')" "483"
check "origen=ambos" "$(curl -s "$URL?origen=ambos" -H "$AUTH_G" | jq '.total')" "395"
check "sucursal_id=3 (GLORIETA)" "$(curl -s "$URL?sucursal_id=3" -H "$AUTH_G" | jq -c '[.total, ([.items[].sucursal] | unique)]')" '[462,["GLORIETA"]]'
check "Página 2 de 32 con 50 filas" "$(curl -s "$URL?page=2&page_size=50" -H "$AUTH_G" | jq -c '[.page, .pages, (.items | length)]')" "[2,32,50]"
check "P-08 la Bodega pedida: 0 alertas" "$(curl -s "$URL?sucursal_id=5" -H "$AUTH_G" | jq '.total')" "0"

# ══════════════════════════════════════════════════════
header "Permisos y validación"
# ══════════════════════════════════════════════════════
RESP_N=$(curl -s "$URL" -H "$AUTH_N")
check "P-10 admin.norte: solo LA 21" "$(echo "$RESP_N" | jq -c '[.items[].sucursal] | unique')" '["LA 21"]'
check "P-10 admin.norte: 183 de riesgo y 137 de sobrestock" "$(echo "$RESP_N" | jq -c '[.resumen.riesgo_desabastecimiento_ml, .resumen.sobrestock_previsto_ml]')" "[183,137]"
check "P-10 admin.norte pide PRINCIPAL: 403" "$(curl -s -o /dev/null -w '%{http_code}' "$URL?sucursal_id=1" -H "$AUTH_N")" "403"
check "admin.norte pide la Bodega: 403" "$(curl -s -o /dev/null -w '%{http_code}' "$URL?sucursal_id=5" -H "$AUTH_N")" "403"
check "P-11 tipo de reglas: 422" "$(curl -s -o /dev/null -w '%{http_code}' "$URL?tipo=stock_bajo" -H "$AUTH_G")" "422"
check "sucursal_id inexistente: 422" "$(curl -s -o /dev/null -w '%{http_code}' "$URL?sucursal_id=99" -H "$AUTH_G")" "422"
check "P-12 sin token: 403" "$(curl -s -o /dev/null -w '%{http_code}' "$URL")" "403"

# ══════════════════════════════════════════════════════
header "Regresión de las alertas por reglas (P-14)"
# ══════════════════════════════════════════════════════
REGLAS=$(curl -s -w '\n%{time_total}' "$BASE/alertas" -H "$AUTH_G")
check "/alertas: 4.452 y sin campo origen" "$(echo "$REGLAS" | head -1 | jq -c '[.total, (.items[0] | has("origen"))]')" "[4452,false]"
SEG=$(echo "$REGLAS" | tail -1)
awk "BEGIN {exit !($SEG < 1)}" && green "/alertas en ${SEG} s (< 1 s)" || red "/alertas tardó ${SEG} s"
check "/alertas/resumen: 4.452" "$(curl -s "$BASE/alertas/resumen" -H "$AUTH_G" | jq '.global_.total')" "4452"

# ══════════════════════════════════════════════════════
header "RESUMEN"
TOTAL_TESTS=$((PASS + FAIL))
echo -e "\n  Total: $TOTAL_TESTS tests"
echo -e "  \033[32m✅ Passed: $PASS\033[0m"
echo -e "  \033[31m❌ Failed: $FAIL\033[0m"

if [ $FAIL -eq 0 ]; then
  echo -e "\n\033[32m🎉 ALL TESTS PASSED\033[0m\n"
else
  echo -e "\n\033[31m⚠️  $FAIL TEST(S) FAILED\033[0m\n"
  exit 1
fi
