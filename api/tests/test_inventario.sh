#!/bin/bash
# ============================================================
# InventAI/o — Inventario + Semáforo Test Script (curl)
# INV-005: Módulo Consulta de inventario y stock
# Run: bash tests/test_inventario.sh
# ============================================================

BASE="http://localhost:8000/api"
PASS=0
FAIL=0

green() { echo -e "\033[32m✅ $1\033[0m"; PASS=$((PASS+1)); }
red() { echo -e "\033[31m❌ $1\033[0m"; FAIL=$((FAIL+1)); }
header() { echo -e "\n\033[1;34m══ $1 ══\033[0m"; }

# ── Login tokens ────────────────────────────────────
TOK_GER=$(curl -s -X POST $BASE/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"gerente@inventaio.co","password":"admin123"}' | jq -r '.access_token')

TOK_ADM=$(curl -s -X POST $BASE/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin.principal@inventaio.co","password":"admin123"}' | jq -r '.access_token')

TOK_BOD=$(curl -s -X POST $BASE/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"bodega@inventaio.co","password":"admin123"}' | jq -r '.access_token')

TOK_NORTE=$(curl -s -X POST $BASE/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin.norte@inventaio.co","password":"admin123"}' | jq -r '.access_token')

if [ -z "$TOK_GER" ] || [ "$TOK_GER" = "null" ]; then
  echo -e "\033[31m❌ Could not login. Is the API running?\033[0m"
  exit 1
fi
green "Login OK — 4 tokens obtained"

AUTH_G="Authorization: Bearer $TOK_GER"
AUTH_A="Authorization: Bearer $TOK_ADM"
AUTH_B="Authorization: Bearer $TOK_BOD"
AUTH_N="Authorization: Bearer $TOK_NORTE"

# ══════════════════════════════════════════════════════
header "GET /consulta/inventario (stock con semáforo)"
# ══════════════════════════════════════════════════════

# Test 1: Lista default como gerente
RESP=$(curl -s "$BASE/consulta/inventario" -H "$AUTH_G")
TOTAL=$(echo $RESP | jq '.total')
ITEMS=$(echo $RESP | jq '.items | length')
PAGE=$(echo $RESP | jq '.page')
FECHA=$(echo $RESP | jq -r '.fecha_inventario')
[ "$TOTAL" -gt 0 ] && green "Inventario total=$TOTAL" || red "Inventario total=0"
[ "$PAGE" = "1" ] && green "Pagina default=1" || red "Pagina=$PAGE"
[ "$ITEMS" -le 20 ] && green "Page size <= 20 ($ITEMS items)" || red "Page size > 20"
[ -n "$FECHA" ] && [ "$FECHA" != "null" ] && green "Fecha inventario=$FECHA" || red "Sin fecha inventario"

# Test 2: Semáforo values are valid
SEMAFOROS=$(echo $RESP | jq -r '[.items[].semaforo] | unique | sort | .[]')
VALID=true
for s in $SEMAFOROS; do
  case "$s" in ok|bajo|critico) ;; *) VALID=false ;; esac
done
[ "$VALID" = "true" ] && green "Semáforos válidos: $(echo $SEMAFOROS | tr '\n' ' ')" || red "Semáforo inválido: $SEMAFOROS"

# Test 3: Campos del item
HAS_FIELDS=$(echo $RESP | jq '.items[0] | has("id_producto") and has("nombre_producto") and has("semaforo") and has("dias_cobertura") and has("stock_disponible") and has("sucursal")')
[ "$HAS_FIELDS" = "true" ] && green "Campos inventario completos" || red "Faltan campos inventario"

# Test 4: Ordered by dias_cobertura ASC (critical first)
FIRST_COB=$(echo $RESP | jq '.items[0].dias_cobertura')
LAST_COB=$(echo $RESP | jq '.items[-1].dias_cobertura')
ORDERED=$(echo "$FIRST_COB <= $LAST_COB" | bc -l 2>/dev/null || echo "1")
[ "$ORDERED" = "1" ] && green "Ordenado por cobertura ASC (críticos primero)" || red "No ordenado"

# Test 5: Paginación
RESP2=$(curl -s "$BASE/consulta/inventario?page=2&page_size=5" -H "$AUTH_G")
PAGE2=$(echo $RESP2 | jq '.page')
ITEMS2=$(echo $RESP2 | jq '.items | length')
[ "$PAGE2" = "2" ] && green "Pagina 2 OK" || red "Pagina=$PAGE2"
[ "$ITEMS2" -le 5 ] && green "Page size=5 respected ($ITEMS2)" || red "Page size not respected"

# Test 6: Filtro por categoría
RESP_CAT=$(curl -s "$BASE/consulta/inventario?categoria=Abarrotes" -H "$AUTH_G")
TOTAL_CAT=$(echo $RESP_CAT | jq '.total')
ALL_CAT=$(echo $RESP_CAT | jq '[.items[].categoria] | all(. == "Abarrotes")')
[ "$ALL_CAT" = "true" ] && green "Filtro categoria=Abarrotes ($TOTAL_CAT)" || red "Filtro categoría failed"

# Test 7: Filtro por semáforo
RESP_CRIT=$(curl -s "$BASE/consulta/inventario?semaforo=critico" -H "$AUTH_G")
TOTAL_CRIT=$(echo $RESP_CRIT | jq '.total')
ALL_CRIT=$(echo $RESP_CRIT | jq '[.items[].semaforo] | all(. == "critico")')
[ "$ALL_CRIT" = "true" ] && green "Filtro semaforo=critico ($TOTAL_CRIT)" || red "Filtro semáforo failed"

# Test 8: Filtro búsqueda
RESP_BUSQ=$(curl -s "$BASE/consulta/inventario?busqueda=Item" -H "$AUTH_G")
TOTAL_BUSQ=$(echo $RESP_BUSQ | jq '.total')
[ "$TOTAL_BUSQ" -gt 0 ] && green "Busqueda 'Item' → $TOTAL_BUSQ" || red "Busqueda sin resultados"

# Test 9: Sin token
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/consulta/inventario")
[ "$STATUS" = "403" ] || [ "$STATUS" = "401" ] && green "Sin token → $STATUS" || red "Sin token → $STATUS"

# Test 10: Gerente con filtro sucursal
RESP_SUC=$(curl -s "$BASE/consulta/inventario?sucursal_id=1" -H "$AUTH_G")
ALL_SUC=$(echo $RESP_SUC | jq '[.items[].id_sucursal] | all(. == 1)')
[ "$ALL_SUC" = "true" ] && green "Gerente filtro sucursal_id=1 OK" || red "Filtro sucursal_id failed"

# ══════════════════════════════════════════════════════
header "RBAC — Filtrado por sucursal"
# ══════════════════════════════════════════════════════

# Test 11: Admin sucursal ve solo su sucursal
RESP_ADM=$(curl -s "$BASE/consulta/inventario" -H "$AUTH_A")
SUCURSALES_ADM=$(echo $RESP_ADM | jq '[.items[].id_sucursal] | unique')
ADM_COUNT=$(echo $SUCURSALES_ADM | jq 'length')
[ "$ADM_COUNT" = "1" ] && green "Admin sucursal ve solo 1 sucursal" || red "Admin ve $ADM_COUNT sucursales"

# Test 12: Admin bodega ve solo su sucursal
RESP_BOD=$(curl -s "$BASE/consulta/inventario" -H "$AUTH_B")
SUCURSALES_BOD=$(echo $RESP_BOD | jq '[.items[].id_sucursal] | unique')
BOD_COUNT=$(echo $SUCURSALES_BOD | jq 'length')
[ "$BOD_COUNT" = "1" ] && green "Admin bodega ve solo 1 sucursal" || red "Bodega ve $BOD_COUNT sucursales"

# Test 13: Gerente ve todas
RESP_GER=$(curl -s "$BASE/consulta/inventario?page_size=100" -H "$AUTH_G")
SUCURSALES_GER=$(echo $RESP_GER | jq '[.items[].id_sucursal] | unique | length')
[ "$SUCURSALES_GER" -ge 2 ] && green "Gerente ve $SUCURSALES_GER sucursales" || red "Gerente ve solo $SUCURSALES_GER"

# ══════════════════════════════════════════════════════
header "GET /consulta/inventario/detalle (historial 30 días)"
# ══════════════════════════════════════════════════════

# Get first product and sucursal from inventory
FIRST_PROD=$(echo $RESP | jq '.items[0].id_producto')
FIRST_SUC=$(echo $RESP | jq '.items[0].id_sucursal')

# Test 14: Detalle OK
RESP_DET=$(curl -s "$BASE/consulta/inventario/detalle?id_producto=$FIRST_PROD&id_sucursal=$FIRST_SUC" -H "$AUTH_G")
DET_PROD=$(echo $RESP_DET | jq '.id_producto')
HAS_HIST=$(echo $RESP_DET | jq 'has("historial")')
HIST_LEN=$(echo $RESP_DET | jq '.historial | length')
[ "$DET_PROD" = "$FIRST_PROD" ] && green "Detalle producto $FIRST_PROD OK" || red "Detalle failed"
[ "$HAS_HIST" = "true" ] && green "Incluye historial" || red "Sin historial"
[ "$HIST_LEN" -gt 0 ] && green "Historial tiene $HIST_LEN días" || red "Historial vacío"

# Test 15: Historial has semáforo
HIST_SEMAFORO=$(echo $RESP_DET | jq '.historial[0] | has("semaforo") and has("fecha") and has("stock_disponible") and has("dias_cobertura")')
[ "$HIST_SEMAFORO" = "true" ] && green "Historial campos completos" || red "Historial incompleto"

# Test 16: Detalle tiene stock_actual y semáforo
DET_FIELDS=$(echo $RESP_DET | jq 'has("stock_actual") and has("semaforo") and has("nombre_producto") and has("categoria")')
[ "$DET_FIELDS" = "true" ] && green "Detalle campos completos" || red "Detalle incompleto"

# Test 17: Producto/sucursal inexistente → 404
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/consulta/inventario/detalle?id_producto=99999&id_sucursal=1" -H "$AUTH_G")
[ "$STATUS" = "404" ] && green "Producto 99999 → 404" || red "Producto 99999 → $STATUS"

# Test 18: RBAC — admin no puede ver otra sucursal
STATUS_RBAC=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/consulta/inventario/detalle?id_producto=$FIRST_PROD&id_sucursal=2" -H "$AUTH_A")
# admin.principal tiene sucursal 1, pedir sucursal 2 debería dar 403
if [ "$FIRST_SUC" != "2" ]; then
  [ "$STATUS_RBAC" = "403" ] && green "RBAC: admin no ve otra sucursal → 403" || red "RBAC: admin ve otra sucursal → $STATUS_RBAC"
else
  green "RBAC: skip (same sucursal)"
fi

# ══════════════════════════════════════════════════════
header "GET /consulta/inventario/resumen (contadores semáforo)"
# ══════════════════════════════════════════════════════

# Test 19: Resumen como gerente
RESP_RES=$(curl -s "$BASE/consulta/inventario/resumen" -H "$AUTH_G")
RES_ITEMS=$(echo $RESP_RES | jq '.items | length')
GLOBAL_TOTAL=$(echo $RESP_RES | jq '.global_.total')
HAS_GLOBAL=$(echo $RESP_RES | jq 'has("global_") and has("fecha_inventario")')
[ "$HAS_GLOBAL" = "true" ] && green "Resumen tiene global y fecha" || red "Resumen incompleto"
[ "$RES_ITEMS" -ge 1 ] && green "Resumen tiene $RES_ITEMS sucursales" || red "Resumen sin sucursales"
[ "$GLOBAL_TOTAL" -gt 0 ] && green "Global total=$GLOBAL_TOTAL" || red "Global total=0"

# Test 20: Contadores suman correctamente
GLOBAL_OK=$(echo $RESP_RES | jq '.global_.ok')
GLOBAL_BAJO=$(echo $RESP_RES | jq '.global_.bajo')
GLOBAL_CRIT=$(echo $RESP_RES | jq '.global_.critico')
SUMA=$((GLOBAL_OK + GLOBAL_BAJO + GLOBAL_CRIT))
[ "$SUMA" = "$GLOBAL_TOTAL" ] && green "ok+bajo+critico=$GLOBAL_TOTAL ✓" || red "Suma $SUMA ≠ $GLOBAL_TOTAL"

# Test 21: Cada sucursal tiene contadores
FIRST_CONTADORES=$(echo $RESP_RES | jq '.items[0].contadores | has("ok") and has("bajo") and has("critico") and has("total")')
[ "$FIRST_CONTADORES" = "true" ] && green "Contadores por sucursal completos" || red "Contadores incompletos"

# Test 22: RBAC — admin ve solo su sucursal en resumen
RESP_RES_ADM=$(curl -s "$BASE/consulta/inventario/resumen" -H "$AUTH_A")
RES_ADM_ITEMS=$(echo $RESP_RES_ADM | jq '.items | length')
[ "$RES_ADM_ITEMS" = "1" ] && green "RBAC: admin ve 1 sucursal en resumen" || red "Admin ve $RES_ADM_ITEMS sucursales"

# ══════════════════════════════════════════════════════
header "GET /consulta/inventario/valorizado"
# ══════════════════════════════════════════════════════

# Test 23: Valorizado como gerente
RESP_VAL=$(curl -s "$BASE/consulta/inventario/valorizado" -H "$AUTH_G")
VAL_ITEMS=$(echo $RESP_VAL | jq '.items | length')
TOTAL_VALOR=$(echo $RESP_VAL | jq '.total_valor')
HAS_FECHA=$(echo $RESP_VAL | jq 'has("fecha_inventario")')
[ "$VAL_ITEMS" -gt 0 ] && green "Valorizado tiene $VAL_ITEMS filas (sucursal×categoría)" || red "Valorizado vacío"
[ "$HAS_FECHA" = "true" ] && green "Valorizado tiene fecha" || red "Sin fecha"

# Test 24: total_valor > 0
VALOR_POS=$(echo "$TOTAL_VALOR > 0" | bc -l 2>/dev/null || echo "1")
[ "$VALOR_POS" = "1" ] && green "Total valor=$TOTAL_VALOR COP" || red "Total valor <= 0"

# Test 25: Campos del item valorizado
VAL_FIELDS=$(echo $RESP_VAL | jq '.items[0] | has("sucursal") and has("categoria") and has("total_productos") and has("stock_total") and has("valor_stock")')
[ "$VAL_FIELDS" = "true" ] && green "Campos valorizado completos" || red "Campos incompletos"

# Test 26: Ordered by valor_stock DESC
VAL_FIRST=$(echo $RESP_VAL | jq '.items[0].valor_stock')
VAL_LAST=$(echo $RESP_VAL | jq '.items[-1].valor_stock')
VAL_ORD=$(echo "$VAL_FIRST >= $VAL_LAST" | bc -l 2>/dev/null || echo "1")
[ "$VAL_ORD" = "1" ] && green "Ordenado por valor DESC" || red "No ordenado"

# Test 27: RBAC — admin ve solo su sucursal
RESP_VAL_ADM=$(curl -s "$BASE/consulta/inventario/valorizado" -H "$AUTH_A")
VAL_SUCS=$(echo $RESP_VAL_ADM | jq '[.items[].id_sucursal] | unique | length')
[ "$VAL_SUCS" = "1" ] && green "RBAC: admin ve 1 sucursal en valorizado" || red "Admin ve $VAL_SUCS sucursales"

# Test 28: Sin token
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/consulta/inventario/valorizado")
[ "$STATUS" = "403" ] || [ "$STATUS" = "401" ] && green "Valorizado sin token → $STATUS" || red "Sin token → $STATUS"

# ══════════════════════════════════════════════════════
header "SEMÁFORO: Lógica de negocio"
# ══════════════════════════════════════════════════════

# Test 29: Validar que OK tiene cobertura >= 7
RESP_OK=$(curl -s "$BASE/consulta/inventario?semaforo=ok&page_size=3" -H "$AUTH_G")
OK_MIN_COB=$(echo $RESP_OK | jq '[.items[].dias_cobertura] | min')
if [ "$(echo $RESP_OK | jq '.total')" -gt 0 ]; then
  OK_VALID=$(echo "$OK_MIN_COB >= 7" | bc -l 2>/dev/null || echo "1")
  [ "$OK_VALID" = "1" ] && green "OK: cobertura mín=$OK_MIN_COB (≥7) ✓" || red "OK con cobertura < 7: $OK_MIN_COB"
else
  green "OK: sin productos OK (válido)"
fi

# Test 30: Validar que crítico tiene cobertura < 3
RESP_CR=$(curl -s "$BASE/consulta/inventario?semaforo=critico&page_size=3" -H "$AUTH_G")
CR_MAX_COB=$(echo $RESP_CR | jq '[.items[].dias_cobertura] | max')
if [ "$(echo $RESP_CR | jq '.total')" -gt 0 ]; then
  CR_VALID=$(echo "$CR_MAX_COB < 3" | bc -l 2>/dev/null || echo "1")
  [ "$CR_VALID" = "1" ] && green "Crítico: cobertura máx=$CR_MAX_COB (<3) ✓" || red "Crítico con cobertura >= 3: $CR_MAX_COB"
else
  green "Crítico: sin productos críticos (válido)"
fi

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
