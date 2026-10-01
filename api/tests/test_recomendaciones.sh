#!/bin/bash
# ============================================================
# InventAI/o — Recomendaciones Test Script (curl)
# INV-23: GET /api/ml/recomendaciones/{compras,transferencias}
# Valores esperados con los datos 2022-2025 (foto al 2025-12-31).
# Necesita api, ml-service, postgres y los usuarios de prueba.
# Run: bash api/tests/test_recomendaciones.sh
# ============================================================

BASE="http://localhost:8000/api"
ML="http://localhost:8001/api"
REC="$BASE/ml/recomendaciones"
PASS=0
FAIL=0

green() { echo -e "\033[32m✅ $1\033[0m"; PASS=$((PASS+1)); }
red() { echo -e "\033[31m❌ $1\033[0m"; FAIL=$((FAIL+1)); }
header() { echo -e "\n\033[1;34m══ $1 ══\033[0m"; }

# check "descripción" "obtenido" "esperado"
check() {
  if [ "$2" = "$3" ]; then green "$1 = $2"; else red "$1: obtenido $2, esperado $3"; fi
}
codigo() { curl -s -o /dev/null -w "%{http_code}" "$@"; }
login() {
  curl -s -X POST "$BASE/auth/login" -H "Content-Type: application/json" \
    -d "{\"email\":\"$1@inventaio.co\",\"password\":\"admin123\"}" | jq -r '.access_token'
}

# ── Login tokens ────────────────────────────────────
TOK_GER=$(login gerente)
TOK_NORTE=$(login admin.norte)
TOK_SUR=$(login admin.sur)
TOK_BOD=$(login bodega)

if [ -z "$TOK_GER" ] || [ "$TOK_GER" = "null" ]; then
  echo -e "\033[31m❌ No se pudo iniciar sesión. ¿Está arriba la API y aplicado el seed de usuarios?\033[0m"
  exit 1
fi
green "Login OK — 4 tokens"

AUTH_G="Authorization: Bearer $TOK_GER"
AUTH_N="Authorization: Bearer $TOK_NORTE"
AUTH_S="Authorization: Bearer $TOK_SUR"
AUTH_B="Authorization: Bearer $TOK_BOD"

# ══════════════════════════════════════════════════════
header "ml-service: /api/health trae la clave de la caché"
# ══════════════════════════════════════════════════════
H=$(curl -s "$ML/health")
check "health.status" "$(echo "$H" | jq -r '.status')" "ok"
check "health.fecha_inventario" "$(echo "$H" | jq -r '.fecha_inventario')" "2025-12-31"
check "health.politicas" "$(echo "$H" | jq -c '[.politicas.inv21.version, .politicas.inv22.version]')" "[1,1]"

# ══════════════════════════════════════════════════════
header "Autenticación"
# ══════════════════════════════════════════════════════
check "Sin token" "$(codigo "$REC/compras")" "403"
check "Token inválido" "$(codigo "$REC/compras" -H "Authorization: Bearer no-es-un-jwt")" "401"

# ══════════════════════════════════════════════════════
header "Calentar la caché (la primera llamada tarda unos 20 s por endpoint)"
# ══════════════════════════════════════════════════════
T1=$(curl -s -o /dev/null -w "%{time_total}" "$REC/compras?incluir_detalle=false" -H "$AUTH_G")
T2=$(curl -s -o /dev/null -w "%{time_total}" "$REC/transferencias" -H "$AUTH_G")
echo "  compras: ${T1}s · transferencias: ${T2}s"

# ══════════════════════════════════════════════════════
header "Compras"
# ══════════════════════════════════════════════════════

# C1: sin filtros, los totales de ml_service
R=$(curl -s "$REC/compras?incluir_detalle=false" -H "$AUTH_G")
check "C1 líneas [total, directas, Bodega]" "$(echo "$R" | jq -c '[.resumen.lineas, .resumen.lineas_sucursal, .resumen.lineas_bodega]')" "[1340,449,891]"
check "C1 cantidad" "$(echo "$R" | jq -c '.resumen.cantidad')" '{"unidad":41952,"kg":3169}'
check "C1 [cubiertos, alertas, productos]" "$(echo "$R" | jq -c '[.resumen.cubiertos_por_bodega, .resumen.alertas, .resumen.productos]')" "[277,220,1411]"
check "C1 sin detalle" "$(echo "$R" | jq '[.compras[] | has("detalle")] | any')" "false"
check "C1 00008 sin filtro es urgente" "$(echo "$R" | jq -r '.compras[] | select(.producto_id=="00008") | .urgencia')" "urgente"

# C2: con detalle por defecto
R=$(curl -s "$REC/compras" -H "$AUTH_G")
check "C2 con detalle" "$(echo "$R" | jq '[.compras[] | has("detalle")] | all')" "true"

# C3: PRINCIPAL, con la vista desde la sucursal
R=$(curl -s "$REC/compras?sucursal=PRINCIPAL&incluir_detalle=false" -H "$AUTH_G")
check "C3 líneas [total, directas, Bodega]" "$(echo "$R" | jq -c '[.resumen.lineas, .resumen.lineas_sucursal, .resumen.lineas_bodega]')" "[814,164,650]"
check "C3 necesidad vía Bodega" "$(echo "$R" | jq '.resumen.necesidad_via_bodega.unidad')" "19637.39"
check "C3 [cubiertos, alertas]" "$(echo "$R" | jq -c '[.resumen.cubiertos_por_bodega, .resumen.alertas]')" "[172,95]"
check "C3 P1632" "$(echo "$R" | jq -c '.compras[] | select(.producto_id=="P1632") | [.nombre_producto, .categoria, .cantidad]')" '["HUEVOS *UND","Huevos",4735]'
check "C3 00008 desde PRINCIPAL" "$(echo "$R" | jq -c '.compras[] | select(.producto_id=="00008") | [.urgencia, .necesidad_sucursal, .cantidad, .necesidad]')" '["normal",36.95,47,46.86]'

# C4: PRINCIPAL + urgente (la urgencia no filtra las alertas)
R=$(curl -s "$REC/compras?sucursal=PRINCIPAL&urgencia=urgente&incluir_detalle=false" -H "$AUTH_G")
check "C4 líneas [total, directas, Bodega]" "$(echo "$R" | jq -c '[.resumen.lineas, .resumen.lineas_sucursal, .resumen.lineas_bodega]')" "[296,64,232]"
check "C4 [cubiertos, alertas]" "$(echo "$R" | jq -c '[.resumen.cubiertos_por_bodega, .resumen.alertas]')" "[27,95]"

# C5: categoría sin mayúsculas ni acentos
R=$(curl -s "$REC/compras?categoria=lacteos&incluir_detalle=false" -H "$AUTH_G")
check "C5 categoría aplicada" "$(echo "$R" | jq -r '.filtros_aplicados.categoria')" "Lácteos"
check "C5 líneas [total, directas, Bodega]" "$(echo "$R" | jq -c '[.resumen.lineas, .resumen.lineas_sucursal, .resumen.lineas_bodega]')" "[215,200,15]"
check "C5 [unidades, cubiertos, alertas]" "$(echo "$R" | jq -c '[.resumen.cantidad.unidad, .resumen.cubiertos_por_bodega, .resumen.alertas]')" "[2743,2,26]"

# C6: los tres filtros
R=$(curl -s "$REC/compras?sucursal=glorieta&categoria=ARROZ&urgencia=urgente&incluir_detalle=false" -H "$AUTH_G")
check "C6 GLORIETA + arroz + urgente" "$(echo "$R" | jq -c '[.compras[] | [.producto_id, .cantidad]]')" '[["P1938",4],["P4570",20]]'

# C7: combinación válida sin filas
check "C7 Anchetas + urgente (HTTP)" "$(codigo "$REC/compras?categoria=Anchetas&urgencia=urgente" -H "$AUTH_G")" "200"
R=$(curl -s "$REC/compras?categoria=Anchetas&urgencia=urgente" -H "$AUTH_G")
check "C7 [líneas, cubiertos, alertas]" "$(echo "$R" | jq -c '[.resumen.lineas, .resumen.cubiertos_por_bodega, .resumen.alertas]')" "[0,0,0]"

# C8: la Bodega
R=$(curl -s "$REC/compras?sucursal=BODEGA_CENTRAL&incluir_detalle=false" -H "$AUTH_G")
check "C8 Bodega [líneas, unidades, cubiertos, alertas]" "$(echo "$R" | jq -c '[.resumen.lineas, .resumen.cantidad.unidad, .resumen.cubiertos_por_bodega, .resumen.alertas]')" "[891,27098,277,15]"

# C9: parámetros inválidos
check "C9 sucursal Norte" "$(codigo "$REC/compras?sucursal=Norte" -H "$AUTH_G")" "422"
check "C9 SIN_SUCURSAL" "$(codigo "$REC/compras?sucursal=SIN_SUCURSAL" -H "$AUTH_G")" "422"
check "C9 categoría Abarrotes" "$(codigo "$REC/compras?categoria=Abarrotes" -H "$AUTH_G")" "422"
check "C9 urgencia vigilancia en compras" "$(codigo "$REC/compras?urgencia=vigilancia" -H "$AUTH_G")" "422"

# ══════════════════════════════════════════════════════
header "Transferencias"
# ══════════════════════════════════════════════════════

# T1: sin filtros, sin balance
R=$(curl -s "$REC/transferencias" -H "$AUTH_G")
check "T1 sin balance" "$(echo "$R" | jq 'has("balance")')" "false"
check "T1 [traslados, filas de balance, productos]" "$(echo "$R" | jq -c '[.resumen.traslados, .resumen.filas_balance, .resumen.productos]')" "[119,11710,4419]"
check "T1 cantidad trasladada" "$(echo "$R" | jq -c '.resumen.cantidad_trasladada')" '{"unidad":4623,"kg":0}'
check "T1 déficit total (unidades + kg)" "$(echo "$R" | jq '(.resumen.deficit_total.unidad + .resumen.deficit_total.kg) * 100 | round / 100')" "20677.18"
check "T1 [alertas listadas, sin pronóstico contadas]" "$(echo "$R" | jq -c '[.resumen.alertas, .resumen.alertas_sin_pronostico]')" "[220,2762]"
check "T1 solo se listan stock_negativo" "$(echo "$R" | jq -c '[.alertas[].tipo] | unique')" '["stock_negativo"]'

# T2: con balance
R=$(curl -s "$REC/transferencias?incluir_balance=true" -H "$AUTH_G")
check "T2 [filas de balance, alertas]" "$(echo "$R" | jq -c '[(.balance | length), (.alertas | length)]')" "[11710,2982]"

# T3: LA 21, por origen o destino
R=$(curl -s "$REC/transferencias?sucursal=LA%2021" -H "$AUTH_G")
check "T3 [traslados, alertas, sin pronóstico]" "$(echo "$R" | jq -c '[.resumen.traslados, .resumen.alertas, .resumen.alertas_sin_pronostico]')" "[10,40,697]"
check "T3 [llegan a LA 21, salen de LA 21]" "$(echo "$R" | jq -c '[([.traslados[] | select(.destino=="LA 21")] | length), ([.traslados[] | select(.origen=="LA 21")] | length)]')" "[8,2]"

# T4: la Bodega
R=$(curl -s "$REC/transferencias?sucursal=BODEGA_CENTRAL" -H "$AUTH_G")
check "T4 Bodega [traslados, unidades, filas, alertas]" "$(echo "$R" | jq -c '[.resumen.traslados, .resumen.cantidad_trasladada.unidad, .resumen.filas_balance, .resumen.alertas]')" "[109,4479,1973,15]"

# T5: categoría arroz
R=$(curl -s "$REC/transferencias?categoria=arroz" -H "$AUTH_G")
check "T5 P3937" "$(echo "$R" | jq -c '[.traslados[] | select(.producto_id=="P3937") | [.destino, .cantidad]] | sort')" '[["GLORIETA",572],["PRINCIPAL",695]]'

# T6: vigilancia, solo en transferencias
R=$(curl -s "$REC/transferencias?urgencia=vigilancia&incluir_balance=true" -H "$AUTH_G")
check "T6 vigilancia [traslados, filas de balance]" "$(echo "$R" | jq -c '[(.traslados | length), (.balance | length)]')" "[0,44]"
check "T6 urgencia media" "$(codigo "$REC/transferencias?urgencia=media" -H "$AUTH_G")" "422"

# ══════════════════════════════════════════════════════
header "Permisos por rol"
# ══════════════════════════════════════════════════════
R=$(curl -s "$REC/compras?incluir_detalle=false" -H "$AUTH_N")
check "P1 admin.norte sin sucursal" "$(echo "$R" | jq -c '[.filtros_aplicados.sucursal, .filtros_aplicados.sucursal_por_rol, .resumen.lineas]')" '["LA 21",true,337]'
check "P2 admin.norte pide PRINCIPAL" "$(codigo "$REC/compras?sucursal=PRINCIPAL" -H "$AUTH_N")" "403"
check "P3 admin.norte pide la suya ('la 21')" "$(codigo "$REC/compras?sucursal=la%2021" -H "$AUTH_N")" "200"
R=$(curl -s "$REC/transferencias" -H "$AUTH_S")
check "P4 admin.sur en transferencias" "$(echo "$R" | jq -c '[.filtros_aplicados.sucursal, .filtros_aplicados.sucursal_por_rol]')" '["GLORIETA",true]'
R=$(curl -s "$REC/compras?incluir_detalle=false" -H "$AUTH_B")
check "P5 bodega (admin_bodega) ve todo" "$(echo "$R" | jq -c '[.filtros_aplicados.sucursal, .resumen.lineas]')" "[null,1340]"
check "P6 gerente pide GLORIETA" "$(codigo "$REC/compras?sucursal=GLORIETA" -H "$AUTH_G")" "200"

# ══════════════════════════════════════════════════════
header "Caché"
# ══════════════════════════════════════════════════════
A=$(curl -s "$REC/compras?sucursal=GLORIETA&incluir_detalle=false" -H "$AUTH_G" | jq -r '.calculado_en')
B=$(curl -s "$REC/compras?categoria=Bebidas&incluir_detalle=false" -H "$AUTH_G" | jq -r '.calculado_en')
check "K1 mismo calculado_en con otros filtros" "$A" "$B"
T=$(curl -s -o /dev/null -w "%{time_total}" "$REC/compras?sucursal=LA%2021" -H "$AUTH_G")
awk "BEGIN{exit !($T < 1)}" && green "K2 caché caliente en ${T}s (< 1 s)" || red "K2 caché caliente tardó ${T}s"

# ══════════════════════════════════════════════════════
header "Regresión de ml-service"
# ══════════════════════════════════════════════════════
R=$(curl -s -X POST "$ML/predict" -H "Content-Type: application/json" \
  -d '{"producto_id":"P1632","sucursal_id":"PRINCIPAL","horizonte":15}')
check "R1 predict P1632 PRINCIPAL q50" "$(echo "$R" | jq '.prediccion_q50')" "3366.01"
R=$(curl -s -X POST "$ML/transferencias" -H "Content-Type: application/json" -d '{"productos":["P3937"]}')
check "R2 transferencias P3937" "$(echo "$R" | jq -c '[.traslados[] | [.destino, .cantidad]] | sort')" '[["GLORIETA",572],["PRINCIPAL",695]]'
R=$(curl -s -X POST "$ML/compras" -H "Content-Type: application/json" -d '{"productos":["P1632"]}')
check "R3 compras P1632 PRINCIPAL" "$(echo "$R" | jq '.compras[] | select(.destino=="PRINCIPAL") | .cantidad')" "4735"

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
