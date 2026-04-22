#!/bin/bash
# ============================================================
# InventAI/o — Alertas Test Script (curl)
# INV-007: Módulo Alertas automáticas
# Run: sed -i 's/\r$//' tests/test_alertas.sh && bash tests/test_alertas.sh
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
header "GET /alertas (alertas activas)"
# ══════════════════════════════════════════════════════

# Test 1: Lista default como gerente
RESP=$(curl -s "$BASE/alertas" -H "$AUTH_G")
TOTAL=$(echo $RESP | jq '.total')
FECHA=$(echo $RESP | jq -r '.fecha_inventario')
HAS_ITEMS=$(echo $RESP | jq 'has("items") and has("total") and has("fecha_inventario")')
[ "$HAS_ITEMS" = "true" ] && green "Estructura response OK" || red "Estructura inválida"
[ "$TOTAL" -ge 0 ] && green "Total alertas=$TOTAL" || red "Total inválido"
[ -n "$FECHA" ] && [ "$FECHA" != "null" ] && green "Fecha inventario=$FECHA" || red "Sin fecha"

# Test 2: Campos de cada alerta
if [ "$TOTAL" -gt 0 ]; then
  FIELDS=$(echo $RESP | jq '.items[0] | has("id_producto") and has("nombre_producto") and has("tipo") and has("urgencia") and has("valor") and has("umbral") and has("detalle") and has("sucursal")')
  [ "$FIELDS" = "true" ] && green "Campos alerta completos" || red "Faltan campos"
else
  green "Sin alertas (campos skip)"
fi

# Test 3: Urgencias válidas
if [ "$TOTAL" -gt 0 ]; then
  URGENCIAS=$(echo $RESP | jq -r '[.items[].urgencia] | unique | .[]')
  VALID=true
  for u in $URGENCIAS; do
    case "$u" in critica|alta|media) ;; *) VALID=false ;; esac
  done
  [ "$VALID" = "true" ] && green "Urgencias válidas: $(echo $URGENCIAS | tr '\n' ' ')" || red "Urgencia inválida"
else
  green "Sin alertas (urgencias skip)"
fi

# Test 4: Tipos válidos
if [ "$TOTAL" -gt 0 ]; then
  TIPOS=$(echo $RESP | jq -r '[.items[].tipo] | unique | .[]')
  VALID=true
  for t in $TIPOS; do
    case "$t" in stock_critico|stock_bajo|sin_movimiento|rotacion_baja) ;; *) VALID=false ;; esac
  done
  [ "$VALID" = "true" ] && green "Tipos válidos: $(echo $TIPOS | tr '\n' ' ')" || red "Tipo inválido"
else
  green "Sin alertas (tipos skip)"
fi

# Test 5: Ordered by urgencia (critica first)
if [ "$TOTAL" -gt 1 ]; then
  FIRST_URG=$(echo $RESP | jq -r '.items[0].urgencia')
  LAST_URG=$(echo $RESP | jq -r '.items[-1].urgencia')
  # critica=0, alta=1, media=2 — first should be <= last
  case "$FIRST_URG" in critica) FIRST_ORD=0 ;; alta) FIRST_ORD=1 ;; media) FIRST_ORD=2 ;; esac
  case "$LAST_URG" in critica) LAST_ORD=0 ;; alta) LAST_ORD=1 ;; media) LAST_ORD=2 ;; esac
  [ "$FIRST_ORD" -le "$LAST_ORD" ] && green "Ordenado por urgencia (críticas primero)" || red "No ordenado"
else
  green "Ordenamiento skip (<=1 alerta)"
fi

# Test 6: Sin token → 401/403
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/alertas")
[ "$STATUS" = "403" ] || [ "$STATUS" = "401" ] && green "Sin token → $STATUS" || red "Sin token → $STATUS"

# ══════════════════════════════════════════════════════
header "Filtros por tipo"
# ══════════════════════════════════════════════════════

# Test 7: Filtro tipo=stock_critico
RESP_SC=$(curl -s "$BASE/alertas?tipo=stock_critico" -H "$AUTH_G")
TOTAL_SC=$(echo $RESP_SC | jq '.total')
if [ "$TOTAL_SC" -gt 0 ]; then
  ALL_SC=$(echo $RESP_SC | jq '[.items[].tipo] | all(. == "stock_critico")')
  [ "$ALL_SC" = "true" ] && green "Filtro stock_critico ($TOTAL_SC)" || red "Filtro stock_critico failed"
else
  green "Filtro stock_critico: 0 alertas (OK)"
fi

# Test 8: Filtro tipo=stock_bajo
RESP_SB=$(curl -s "$BASE/alertas?tipo=stock_bajo" -H "$AUTH_G")
TOTAL_SB=$(echo $RESP_SB | jq '.total')
if [ "$TOTAL_SB" -gt 0 ]; then
  ALL_SB=$(echo $RESP_SB | jq '[.items[].tipo] | all(. == "stock_bajo")')
  [ "$ALL_SB" = "true" ] && green "Filtro stock_bajo ($TOTAL_SB)" || red "Filtro stock_bajo failed"
else
  green "Filtro stock_bajo: 0 alertas (OK)"
fi

# Test 9: Filtro tipo=sin_movimiento
RESP_SM=$(curl -s "$BASE/alertas?tipo=sin_movimiento" -H "$AUTH_G")
TOTAL_SM=$(echo $RESP_SM | jq '.total')
[ "$TOTAL_SM" -ge 0 ] && green "Filtro sin_movimiento ($TOTAL_SM)" || red "Filtro sin_movimiento failed"

# Test 10: Filtro tipo=rotacion_baja
RESP_RB=$(curl -s "$BASE/alertas?tipo=rotacion_baja" -H "$AUTH_G")
TOTAL_RB=$(echo $RESP_RB | jq '.total')
[ "$TOTAL_RB" -ge 0 ] && green "Filtro rotacion_baja ($TOTAL_RB)" || red "Filtro rotacion_baja failed"

# Test 11: Tipo inválido → 400
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/alertas?tipo=invalido" -H "$AUTH_G")
[ "$STATUS" = "400" ] && green "Tipo inválido → 400" || red "Tipo inválido → $STATUS"

# ══════════════════════════════════════════════════════
header "Filtros por urgencia"
# ══════════════════════════════════════════════════════

# Test 12: Filtro urgencia=critica
RESP_UC=$(curl -s "$BASE/alertas?urgencia=critica" -H "$AUTH_G")
if [ "$(echo $RESP_UC | jq '.total')" -gt 0 ]; then
  ALL_UC=$(echo $RESP_UC | jq '[.items[].urgencia] | all(. == "critica")')
  [ "$ALL_UC" = "true" ] && green "Filtro urgencia=critica OK" || red "Filtro urgencia failed"
else
  green "Filtro urgencia=critica: 0 (OK)"
fi

# Test 13: Filtro urgencia=alta
RESP_UA=$(curl -s "$BASE/alertas?urgencia=alta" -H "$AUTH_G")
if [ "$(echo $RESP_UA | jq '.total')" -gt 0 ]; then
  ALL_UA=$(echo $RESP_UA | jq '[.items[].urgencia] | all(. == "alta")')
  [ "$ALL_UA" = "true" ] && green "Filtro urgencia=alta OK" || red "Filtro urgencia=alta failed"
else
  green "Filtro urgencia=alta: 0 (OK)"
fi

# Test 14: Filtro urgencia=media
RESP_UM=$(curl -s "$BASE/alertas?urgencia=media" -H "$AUTH_G")
[ "$(echo $RESP_UM | jq '.total')" -ge 0 ] && green "Filtro urgencia=media OK" || red "Filtro urgencia=media failed"

# Test 15: Urgencia inválida → 400
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/alertas?urgencia=extrema" -H "$AUTH_G")
[ "$STATUS" = "400" ] && green "Urgencia inválida → 400" || red "Urgencia inválida → $STATUS"

# ══════════════════════════════════════════════════════
header "RBAC — Filtrado por sucursal"
# ══════════════════════════════════════════════════════

# Test 16: Admin sucursal ve solo su sucursal
RESP_ADM=$(curl -s "$BASE/alertas" -H "$AUTH_A")
if [ "$(echo $RESP_ADM | jq '.total')" -gt 0 ]; then
  SUCS_ADM=$(echo $RESP_ADM | jq '[.items[].id_sucursal] | unique | length')
  [ "$SUCS_ADM" = "1" ] && green "RBAC: admin ve 1 sucursal en alertas" || red "Admin ve $SUCS_ADM sucursales"
else
  green "RBAC: admin sin alertas (OK)"
fi

# Test 17: Admin bodega ve solo su sucursal
RESP_BOD=$(curl -s "$BASE/alertas" -H "$AUTH_B")
if [ "$(echo $RESP_BOD | jq '.total')" -gt 0 ]; then
  SUCS_BOD=$(echo $RESP_BOD | jq '[.items[].id_sucursal] | unique | length')
  [ "$SUCS_BOD" = "1" ] && green "RBAC: bodega ve 1 sucursal" || red "Bodega ve $SUCS_BOD sucursales"
else
  green "RBAC: bodega sin alertas (OK)"
fi

# Test 18: Gerente ve múltiples sucursales
RESP_GER=$(curl -s "$BASE/alertas" -H "$AUTH_G")
if [ "$(echo $RESP_GER | jq '.total')" -gt 0 ]; then
  SUCS_GER=$(echo $RESP_GER | jq '[.items[].id_sucursal] | unique | length')
  [ "$SUCS_GER" -ge 1 ] && green "Gerente ve $SUCS_GER sucursales" || red "Gerente ve 0 sucursales"
else
  green "Gerente: sin alertas (OK)"
fi

# Test 19: Gerente filtra por sucursal_id
RESP_SUC=$(curl -s "$BASE/alertas?sucursal_id=1" -H "$AUTH_G")
if [ "$(echo $RESP_SUC | jq '.total')" -gt 0 ]; then
  ALL_SUC=$(echo $RESP_SUC | jq '[.items[].id_sucursal] | all(. == 1)')
  [ "$ALL_SUC" = "true" ] && green "Gerente filtro sucursal_id=1 OK" || red "Filtro sucursal failed"
else
  green "Gerente filtro suc_id=1: 0 alertas (OK)"
fi

# ══════════════════════════════════════════════════════
header "GET /alertas/resumen (contadores)"
# ══════════════════════════════════════════════════════

# Test 20: Resumen como gerente
RESP_RES=$(curl -s "$BASE/alertas/resumen" -H "$AUTH_G")
HAS_STRUCT=$(echo $RESP_RES | jq 'has("global_") and has("items") and has("por_tipo") and has("fecha_inventario")')
[ "$HAS_STRUCT" = "true" ] && green "Resumen estructura OK" || red "Resumen estructura inválida"

# Test 21: Global counters add up
G_CRIT=$(echo $RESP_RES | jq '.global_.critica')
G_ALTA=$(echo $RESP_RES | jq '.global_.alta')
G_MEDIA=$(echo $RESP_RES | jq '.global_.media')
G_TOTAL=$(echo $RESP_RES | jq '.global_.total')
SUMA=$((G_CRIT + G_ALTA + G_MEDIA))
[ "$SUMA" = "$G_TOTAL" ] && green "Global: critica+alta+media=$G_TOTAL ✓" || red "Suma $SUMA ≠ $G_TOTAL"

# Test 22: por_tipo has 4 keys
POR_TIPO_KEYS=$(echo $RESP_RES | jq '.por_tipo | keys | length')
[ "$POR_TIPO_KEYS" = "4" ] && green "por_tipo tiene 4 tipos" || red "por_tipo tiene $POR_TIPO_KEYS"

# Test 23: por_tipo keys are correct
HAS_TIPOS=$(echo $RESP_RES | jq '.por_tipo | has("stock_critico") and has("stock_bajo") and has("sin_movimiento") and has("rotacion_baja")')
[ "$HAS_TIPOS" = "true" ] && green "por_tipo keys correctas" || red "por_tipo keys incorrectas"

# Test 24: por_tipo sum equals global total
PT_SUM=$(echo $RESP_RES | jq '[.por_tipo[]] | add')
[ "$PT_SUM" = "$G_TOTAL" ] && green "por_tipo sum=$G_TOTAL ✓" || red "por_tipo sum=$PT_SUM ≠ $G_TOTAL"

# Test 25: Per-sucursal items
RES_ITEMS=$(echo $RESP_RES | jq '.items | length')
[ "$RES_ITEMS" -ge 1 ] && green "Resumen tiene $RES_ITEMS sucursales" || red "Sin sucursales en resumen"

# Test 26: Per-sucursal has contadores
if [ "$RES_ITEMS" -ge 1 ]; then
  SUC_FIELDS=$(echo $RESP_RES | jq '.items[0] | has("sucursal") and has("id_sucursal") and has("contadores")')
  [ "$SUC_FIELDS" = "true" ] && green "Sucursal fields OK" || red "Sucursal fields incompletos"
  SUC_CONT=$(echo $RESP_RES | jq '.items[0].contadores | has("critica") and has("alta") and has("media") and has("total")')
  [ "$SUC_CONT" = "true" ] && green "Contadores sucursal OK" || red "Contadores incompletos"
else
  green "Contadores skip (0 items)"
  green "Contadores skip (0 items)"
fi

# Test 27: RBAC — admin ve solo su sucursal en resumen
RESP_RES_ADM=$(curl -s "$BASE/alertas/resumen" -H "$AUTH_A")
RES_ADM_ITEMS=$(echo $RESP_RES_ADM | jq '.items | length')
[ "$RES_ADM_ITEMS" -le 1 ] && green "RBAC: admin ve ≤1 sucursal en resumen" || red "Admin ve $RES_ADM_ITEMS"

# Test 28: Resumen sin token
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/alertas/resumen")
[ "$STATUS" = "403" ] || [ "$STATUS" = "401" ] && green "Resumen sin token → $STATUS" || red "Sin token → $STATUS"

# ══════════════════════════════════════════════════════
header "Coherencia alertas vs resumen"
# ══════════════════════════════════════════════════════

# Test 29: Total alertas == resumen global total
ALERTAS_TOTAL=$(curl -s "$BASE/alertas" -H "$AUTH_G" | jq '.total')
RESUMEN_TOTAL=$(echo $RESP_RES | jq '.global_.total')
[ "$ALERTAS_TOTAL" = "$RESUMEN_TOTAL" ] && green "Alertas total=$ALERTAS_TOTAL == resumen total ✓" || red "Alertas $ALERTAS_TOTAL ≠ resumen $RESUMEN_TOTAL"

# Test 30: Contadores por tipo match filtered counts
SC_FROM_RES=$(echo $RESP_RES | jq '.por_tipo.stock_critico')
SC_FROM_FILTER=$(curl -s "$BASE/alertas?tipo=stock_critico" -H "$AUTH_G" | jq '.total')
[ "$SC_FROM_RES" = "$SC_FROM_FILTER" ] && green "stock_critico: resumen=$SC_FROM_RES == filtro=$SC_FROM_FILTER ✓" || red "stock_critico mismatch"

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
