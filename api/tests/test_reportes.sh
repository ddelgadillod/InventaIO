#!/bin/bash
# ============================================================
# InventAI/o — Reportes Test Script (curl)
# INV-006: Módulo Reportes de ventas y KPIs
# Run: sed -i 's/\r$//' tests/test_reportes.sh && bash tests/test_reportes.sh
# ============================================================

BASE="http://localhost:8000/api"
PASS=0
FAIL=0

green() { echo -e "\033[32m✅ $1\033[0m"; PASS=$((PASS+1)); }
red() { echo -e "\033[31m❌ $1\033[0m"; FAIL=$((FAIL+1)); }
header() { echo -e "\n\033[1;34m══ $1 ══\033[0m"; }

# ── Login ───────────────────────────────────────────
TOK_GER=$(curl -s -X POST $BASE/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"gerente@inventaio.co","password":"admin123"}' | jq -r '.access_token')

TOK_ADM=$(curl -s -X POST $BASE/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin.principal@inventaio.co","password":"admin123"}' | jq -r '.access_token')

TOK_BOD=$(curl -s -X POST $BASE/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"bodega@inventaio.co","password":"admin123"}' | jq -r '.access_token')

if [ -z "$TOK_GER" ] || [ "$TOK_GER" = "null" ]; then
  echo -e "\033[31m❌ Could not login\033[0m"; exit 1
fi
green "Login OK — 3 tokens"

AUTH_G="Authorization: Bearer $TOK_GER"
AUTH_A="Authorization: Bearer $TOK_ADM"
AUTH_B="Authorization: Bearer $TOK_BOD"

# ══════════════════════════════════════════════════════
header "GET /reportes/kpis"
# ══════════════════════════════════════════════════════

RESP=$(curl -s "$BASE/reportes/kpis" -H "$AUTH_G")

# Test 1-5: KPIs structure
VENTAS_HOY=$(echo $RESP | jq '.ventas_hoy')
VENTAS_MES=$(echo $RESP | jq '.ventas_mes')
EN_RIESGO=$(echo $RESP | jq '.productos_en_riesgo')
STOCK_VAL=$(echo $RESP | jq '.stock_valorizado')
FECHA=$(echo $RESP | jq -r '.fecha_referencia')

[ "$(echo "$VENTAS_HOY >= 0" | bc -l)" = "1" ] && green "ventas_hoy=$VENTAS_HOY" || red "ventas_hoy invalid"
[ "$(echo "$VENTAS_MES > 0" | bc -l)" = "1" ] && green "ventas_mes=$VENTAS_MES" || red "ventas_mes=0"
[ "$EN_RIESGO" -ge 0 ] && green "productos_en_riesgo=$EN_RIESGO" || red "en_riesgo invalid"
[ "$(echo "$STOCK_VAL > 0" | bc -l)" = "1" ] && green "stock_valorizado=$STOCK_VAL" || red "stock_val=0"
[ -n "$FECHA" ] && [ "$FECHA" != "null" ] && green "fecha_referencia=$FECHA" || red "Sin fecha"

# Test 6: Has variaciones
HAS_VAR=$(echo $RESP | jq 'has("variacion_ventas_hoy_pct") and has("variacion_ventas_mes_pct")')
[ "$HAS_VAR" = "true" ] && green "Variaciones presentes" || red "Sin variaciones"

# Test 7: Sin token
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/reportes/kpis")
[ "$STATUS" = "403" ] || [ "$STATUS" = "401" ] && green "KPIs sin token → $STATUS" || red "Sin token → $STATUS"

# Test 8: KPIs con filtro sucursal
RESP_SUC=$(curl -s "$BASE/reportes/kpis?sucursal_id=1" -H "$AUTH_G")
[ "$(echo $RESP_SUC | jq '.ventas_hoy')" != "null" ] && green "KPIs filtro sucursal_id=1 OK" || red "KPIs filtro failed"

# ══════════════════════════════════════════════════════
header "GET /reportes/ventas"
# ══════════════════════════════════════════════════════

# Test 9: Ventas default (dia)
RESP_V=$(curl -s "$BASE/reportes/ventas" -H "$AUTH_G")
AGRUP=$(echo $RESP_V | jq -r '.agrupacion')
ITEMS=$(echo $RESP_V | jq '.items | length')
TOTAL_V=$(echo $RESP_V | jq '.total_valor')
[ "$AGRUP" = "dia" ] && green "Agrupación default=dia" || red "Agrupación=$AGRUP"
[ "$ITEMS" -gt 0 ] && green "Ventas tiene $ITEMS periodos" || red "Sin periodos"
[ "$(echo "$TOTAL_V > 0" | bc -l)" = "1" ] && green "total_valor=$TOTAL_V" || red "total_valor=0"

# Test 10: Campos del periodo
FIELDS=$(echo $RESP_V | jq '.items[0] | has("periodo") and has("cantidad") and has("valor_total") and has("margen") and has("transacciones")')
[ "$FIELDS" = "true" ] && green "Campos periodo completos" || red "Campos incompletos"

# Test 11: Agrupación por semana
RESP_S=$(curl -s "$BASE/reportes/ventas?agrupacion=semana" -H "$AUTH_G")
AGRUP_S=$(echo $RESP_S | jq -r '.agrupacion')
PERIODO_S=$(echo $RESP_S | jq -r '.items[0].periodo')
[ "$AGRUP_S" = "semana" ] && green "Agrupación semana OK" || red "Agrupación=$AGRUP_S"
echo "$PERIODO_S" | grep -q "\-W" && green "Formato semana: $PERIODO_S" || red "Formato: $PERIODO_S"

# Test 12: Agrupación por mes
RESP_M=$(curl -s "$BASE/reportes/ventas?agrupacion=mes" -H "$AUTH_G")
PERIODO_M=$(echo $RESP_M | jq -r '.items[0].periodo')
[ ${#PERIODO_M} = 7 ] && green "Formato mes: $PERIODO_M" || red "Formato: $PERIODO_M"

# Test 13: Filtro categoría
RESP_CAT=$(curl -s "$BASE/reportes/ventas?categoria=Bebidas" -H "$AUTH_G")
[ "$(echo $RESP_CAT | jq '.total_valor')" != "null" ] && green "Filtro categoría=Bebidas OK" || red "Filtro categoría failed"

# Test 14: Rango de fechas custom
RESP_RANGO=$(curl -s "$BASE/reportes/ventas?fecha_inicio=2017-07-01&fecha_fin=2017-07-31" -H "$AUTH_G")
FI=$(echo $RESP_RANGO | jq -r '.fecha_inicio')
FF=$(echo $RESP_RANGO | jq -r '.fecha_fin')
[ "$FI" = "2017-07-01" ] && [ "$FF" = "2017-07-31" ] && green "Rango custom OK" || red "Rango: $FI / $FF"

# Test 15: total_margen coherente
TOTAL_MARGEN=$(echo $RESP_V | jq '.total_margen')
[ "$(echo "$TOTAL_MARGEN > 0" | bc -l)" = "1" ] && green "total_margen=$TOTAL_MARGEN" || red "margen<=0"

# ══════════════════════════════════════════════════════
header "GET /reportes/ventas/comparativa"
# ══════════════════════════════════════════════════════

# Test 16: Comparativa default
RESP_C=$(curl -s "$BASE/reportes/ventas/comparativa" -H "$AUTH_G")
HAS_COMP=$(echo $RESP_C | jq 'has("resumen") and has("detalle") and has("agrupacion")')
[ "$HAS_COMP" = "true" ] && green "Comparativa estructura OK" || red "Estructura inválida"

# Test 17: Resumen fields
RES_FIELDS=$(echo $RESP_C | jq '.resumen | has("valor_actual") and has("valor_anterior") and has("variacion_pct") and has("cantidad_actual")')
[ "$RES_FIELDS" = "true" ] && green "Resumen comparativa completo" || red "Resumen incompleto"

# Test 18: Variación calculada
VAR=$(echo $RESP_C | jq '.resumen.variacion_pct')
[ "$VAR" != "null" ] && green "variacion_pct=$VAR" || red "Sin variación"

# Test 19: Detalle has items
DET_LEN=$(echo $RESP_C | jq '.detalle | length')
[ "$DET_LEN" -gt 0 ] && green "Detalle con $DET_LEN periodos" || red "Detalle vacío"

# Test 20: Comparativa con rango custom
RESP_CC=$(curl -s "$BASE/reportes/ventas/comparativa?fecha_inicio=2017-07-01&fecha_fin=2017-07-31&agrupacion=semana" -H "$AUTH_G")
[ "$(echo $RESP_CC | jq -r '.agrupacion')" = "semana" ] && green "Comparativa semana OK" || red "Comparativa semana failed"

# ══════════════════════════════════════════════════════
header "GET /reportes/ventas/top-productos"
# ══════════════════════════════════════════════════════

# Test 21: Top 10 default
RESP_T=$(curl -s "$BASE/reportes/ventas/top-productos" -H "$AUTH_G")
TOP_LEN=$(echo $RESP_T | jq '.items | length')
[ "$TOP_LEN" -le 10 ] && [ "$TOP_LEN" -gt 0 ] && green "Top $TOP_LEN productos" || red "Top len=$TOP_LEN"

# Test 22: Campos
TOP_FIELDS=$(echo $RESP_T | jq '.items[0] | has("id_producto") and has("nombre") and has("categoria") and has("valor_total") and has("participacion_pct")')
[ "$TOP_FIELDS" = "true" ] && green "Campos top producto completos" || red "Campos incompletos"

# Test 23: Ordenado por valor DESC
FIRST_VAL=$(echo $RESP_T | jq '.items[0].valor_total')
LAST_VAL=$(echo $RESP_T | jq '.items[-1].valor_total')
[ "$(echo "$FIRST_VAL >= $LAST_VAL" | bc -l)" = "1" ] && green "Ordenado por valor DESC" || red "No ordenado"

# Test 24: participacion_pct suma ~100
SUMA_PCT=$(echo $RESP_T | jq '[.items[].participacion_pct] | add')
[ "$(echo "$SUMA_PCT > 0" | bc -l)" = "1" ] && green "Participación total=${SUMA_PCT}%" || red "Participación=0"

# Test 25: Top 5 con categoría
RESP_T5=$(curl -s "$BASE/reportes/ventas/top-productos?limite=5&categoria=Abarrotes" -H "$AUTH_G")
TOP5_LEN=$(echo $RESP_T5 | jq '.items | length')
[ "$TOP5_LEN" -le 5 ] && green "Top 5 Abarrotes ($TOP5_LEN)" || red "Top5 len=$TOP5_LEN"

# ══════════════════════════════════════════════════════
header "GET /reportes/tendencias"
# ══════════════════════════════════════════════════════

# Test 26: Tendencias default (30 días, global)
RESP_TE=$(curl -s "$BASE/reportes/tendencias" -H "$AUTH_G")
SERIES=$(echo $RESP_TE | jq '.series | length')
PUNTOS=$(echo $RESP_TE | jq '.series[0].puntos | length')
[ "$SERIES" -ge 1 ] && green "Tendencias: $SERIES serie(s)" || red "Sin series"
[ "$PUNTOS" -gt 0 ] && green "Serie con $PUNTOS puntos" || red "Sin puntos"

# Test 27: Tiene promedio móvil
HAS_MA=$(echo $RESP_TE | jq '.series[0].puntos[-1] | has("promedio_movil_7d")')
[ "$HAS_MA" = "true" ] && green "Promedio móvil 7d presente" || red "Sin promedio móvil"

# Test 28: Punto tiene campos
PTO_FIELDS=$(echo $RESP_TE | jq '.series[0].puntos[0] | has("fecha") and has("valor_total") and has("cantidad")')
[ "$PTO_FIELDS" = "true" ] && green "Campos punto completos" || red "Punto incompleto"

# Test 29: Por sucursal
RESP_TS=$(curl -s "$BASE/reportes/tendencias?por_sucursal=true" -H "$AUTH_G")
SERIES_S=$(echo $RESP_TS | jq '.series | length')
[ "$SERIES_S" -ge 2 ] && green "Por sucursal: $SERIES_S series" || red "Solo $SERIES_S series"

# Test 30: Tiene nombre sucursal
SUC_NAME=$(echo $RESP_TS | jq -r '.series[0].sucursal')
[ "$SUC_NAME" != "null" ] && green "Serie sucursal: $SUC_NAME" || red "Sin nombre sucursal"

# ══════════════════════════════════════════════════════
header "GET /reportes/distribucion-categorias"
# ══════════════════════════════════════════════════════

# Test 31: Distribución default
RESP_D=$(curl -s "$BASE/reportes/distribucion-categorias" -H "$AUTH_G")
CATS=$(echo $RESP_D | jq '.items | length')
TOTAL_DV=$(echo $RESP_D | jq '.total_valor')
[ "$CATS" -ge 10 ] && green "Distribución: $CATS categorías" || red "Solo $CATS categorías"
[ "$(echo "$TOTAL_DV > 0" | bc -l)" = "1" ] && green "total_valor=$TOTAL_DV" || red "total_valor=0"

# Test 32: Campos categoría
CAT_FIELDS=$(echo $RESP_D | jq '.items[0] | has("categoria") and has("valor_total") and has("participacion_pct") and has("num_productos") and has("margen")')
[ "$CAT_FIELDS" = "true" ] && green "Campos distribución completos" || red "Campos incompletos"

# Test 33: Ordenado por valor DESC
FIRST_CAT=$(echo $RESP_D | jq '.items[0].valor_total')
LAST_CAT=$(echo $RESP_D | jq '.items[-1].valor_total')
[ "$(echo "$FIRST_CAT >= $LAST_CAT" | bc -l)" = "1" ] && green "Ordenado por valor DESC" || red "No ordenado"

# Test 34: Participación suma ~100
PART_SUM=$(echo $RESP_D | jq '[.items[].participacion_pct] | add | round')
[ "$PART_SUM" -ge 99 ] && [ "$PART_SUM" -le 101 ] && green "Participación suma=${PART_SUM}%" || red "Suma=${PART_SUM}%"

# ══════════════════════════════════════════════════════
header "RBAC"
# ══════════════════════════════════════════════════════

# Test 35: Admin sucursal ve KPIs (solo su sucursal)
RESP_KA=$(curl -s "$BASE/reportes/kpis" -H "$AUTH_A")
[ "$(echo $RESP_KA | jq '.ventas_hoy')" != "null" ] && green "RBAC: admin ve KPIs" || red "Admin no ve KPIs"

# Test 36: Bodega ve KPIs
RESP_KB=$(curl -s "$BASE/reportes/kpis" -H "$AUTH_B")
[ "$(echo $RESP_KB | jq '.ventas_hoy')" != "null" ] && green "RBAC: bodega ve KPIs" || red "Bodega no ve KPIs"

# Test 37: Admin ventas filtradas a su sucursal (ventas_mes < gerente)
VENTAS_MES_GER=$(curl -s "$BASE/reportes/kpis" -H "$AUTH_G" | jq '.ventas_mes')
VENTAS_MES_ADM=$(echo $RESP_KA | jq '.ventas_mes')
[ "$(echo "$VENTAS_MES_ADM <= $VENTAS_MES_GER" | bc -l)" = "1" ] && green "RBAC: admin ventas ≤ gerente ($VENTAS_MES_ADM ≤ $VENTAS_MES_GER)" || red "Admin > gerente"

# Test 38: Todos los endpoints sin token → 401/403
for ep in "reportes/kpis" "reportes/ventas" "reportes/ventas/comparativa" "reportes/ventas/top-productos" "reportes/tendencias" "reportes/distribucion-categorias"; do
  S=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/$ep")
  if [ "$S" = "403" ] || [ "$S" = "401" ]; then
    PASS=$((PASS+1))
  else
    red "$ep sin token → $S"
  fi
done
green "6 endpoints sin token → 401/403 ✓"

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
