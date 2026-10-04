#!/bin/bash
# ============================================================
# InventAI/o — Consulta (Catálogos) Test Script (curl)
# INV-008: Módulo Consulta de catálogos y proveedores
# INV-25: homologado con la bodega real (códigos de texto, ubicaciones
# reales, proveedores desde dw.producto_proveedor)
# Run: bash tests/test_consulta.sh
# Requires: curl, jq, API on localhost:8000, DB populated
# ============================================================

BASE="http://localhost:8000/api"
PASS=0
FAIL=0

green() { echo -e "\033[32m✅ $1\033[0m"; PASS=$((PASS+1)); }
red() { echo -e "\033[31m❌ $1\033[0m"; FAIL=$((FAIL+1)); }
header() { echo -e "\n\033[1;34m══ $1 ══\033[0m"; }

# ── Login to get token ───────────────────────────────
TOKEN=$(curl -s -X POST $BASE/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"gerente@inventaio.co","password":"admin123"}' | jq -r '.access_token')

if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
  echo -e "\033[31m❌ Could not login. Is the API running?\033[0m"
  exit 1
fi
echo -e "\033[32m✅ Login OK — token obtained\033[0m"

AUTH="Authorization: Bearer $TOKEN"

# ══════════════════════════════════════════════════════
# PRODUCTOS
# ══════════════════════════════════════════════════════
header "GET /consulta/productos (paginado)"

# Test 1: Lista default
RESP=$(curl -s "$BASE/consulta/productos" -H "$AUTH")
TOTAL=$(echo $RESP | jq '.total')
ITEMS=$(echo $RESP | jq '.items | length')
PAGE=$(echo $RESP | jq '.page')
[ "$TOTAL" -gt 0 ] && green "Productos total=$TOTAL" || red "Productos total=0"
[ "$PAGE" = "1" ] && green "Pagina default=1" || red "Pagina=$PAGE"
[ "$ITEMS" -le 20 ] && green "Page size <= 20 ($ITEMS items)" || red "Page size > 20"

# Test 2: Paginación page 2
RESP2=$(curl -s "$BASE/consulta/productos?page=2&page_size=5" -H "$AUTH")
ITEMS2=$(echo $RESP2 | jq '.items | length')
PAGE2=$(echo $RESP2 | jq '.page')
[ "$PAGE2" = "2" ] && green "Pagina 2 OK" || red "Pagina 2 failed"
[ "$ITEMS2" -le 5 ] && green "Page size=5 respected ($ITEMS2)" || red "Page size not respected"

# Test 3: Filtro por categoría
CAT=$(echo $RESP | jq -r '.items[0].categoria')
RESP_CAT=$(curl -s -G "$BASE/consulta/productos" --data-urlencode "categoria=$CAT" -H "$AUTH")
TOTAL_CAT=$(echo $RESP_CAT | jq '.total')
FIRST_CAT=$(echo $RESP_CAT | jq -r '.items[0].categoria')
[ "$FIRST_CAT" = "$CAT" ] && green "Filtro categoria=$CAT ($TOTAL_CAT items)" || red "Filtro categoria failed"

# Test 4: Filtro perecedero
RESP_PER=$(curl -s "$BASE/consulta/productos?perecedero=true" -H "$AUTH")
TOTAL_PER=$(echo $RESP_PER | jq '.total')
ALL_PER=$(echo $RESP_PER | jq '[.items[].es_perecedero] | all')
[ "$ALL_PER" = "true" ] && green "Filtro perecedero=true ($TOTAL_PER)" || red "Filtro perecedero failed"

# Test 5: Búsqueda por nombre
RESP_BUSQ=$(curl -s "$BASE/consulta/productos?busqueda=ARROZ" -H "$AUTH")
TOTAL_BUSQ=$(echo $RESP_BUSQ | jq '.total')
[ "$TOTAL_BUSQ" -gt 0 ] && green "Busqueda 'ARROZ' → $TOTAL_BUSQ resultados" || red "Busqueda sin resultados"

# Test 6: Sin autenticación
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/consulta/productos")
[ "$STATUS" = "403" ] || [ "$STATUS" = "401" ] && green "Sin token → $STATUS" || red "Sin token → $STATUS"

# Test 7: Campos del item
HAS_FIELDS=$(echo $RESP | jq '.items[0] | has("id_producto") and has("codigo_item") and has("nombre") and has("categoria") and has("precio_base") and has("iva_pct")')
[ "$HAS_FIELDS" = "true" ] && green "Campos producto completos" || red "Faltan campos en producto"

# Test 7b: codigo_item es texto (INV-25: P1632, 00008)
TIPO_COD=$(echo $RESP | jq -r '[.items[].codigo_item | type] | unique | join(",")')
[ "$TIPO_COD" = "string" ] && green "codigo_item como texto" || red "codigo_item tipo=$TIPO_COD"

# ══════════════════════════════════════════════════════
header "GET /consulta/productos/:id (detalle)"

# Test 8: Detalle producto existente
FIRST_ID=$(echo $RESP | jq '.items[0].id_producto')
RESP_DET=$(curl -s "$BASE/consulta/productos/$FIRST_ID" -H "$AUTH")
DET_ID=$(echo $RESP_DET | jq '.id_producto')
HAS_PROVS=$(echo $RESP_DET | jq 'has("proveedores")')
[ "$DET_ID" = "$FIRST_ID" ] && green "Detalle producto $FIRST_ID OK" || red "Detalle producto failed"
[ "$HAS_PROVS" = "true" ] && green "Incluye proveedores" || red "No incluye proveedores"

# Test 8b: Huevos (id 91) y agua (id 3814) con su código y su proveedor real (INV-25)
HUEVOS=$(curl -s "$BASE/consulta/productos/91" -H "$AUTH" | jq -c '[.codigo_item, .proveedores]')
[ "$HUEVOS" = '["P1632",["Lácteos del Cauca Ltda."]]' ] && green "P1632 con su proveedor de producto_proveedor" || red "P1632: $HUEVOS"
AGUA=$(curl -s "$BASE/consulta/productos/3814" -H "$AUTH" | jq -r '.codigo_item')
[ "$AGUA" = "00008" ] && green "00008 conserva los ceros" || red "Código del agua=$AGUA"

# Test 9: Producto inexistente
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/consulta/productos/99999" -H "$AUTH")
[ "$STATUS" = "404" ] && green "Producto 99999 → 404" || red "Producto 99999 → $STATUS"

# ══════════════════════════════════════════════════════
header "GET /consulta/sucursales"

# Test 10: Listar ubicaciones (INV-25: sin SIN_SUCURSAL)
RESP_SUC=$(curl -s "$BASE/consulta/sucursales" -H "$AUTH")
TOTAL_SUC=$(echo $RESP_SUC | jq '.total')
[ "$TOTAL_SUC" = "4" ] && green "Sucursales total=4" || red "Sucursales total=$TOTAL_SUC"

# Test 11: Ubicaciones y tipos reales
SUCS=$(echo $RESP_SUC | jq -c '[.items[] | [.nombre, .tipo]]')
[ "$SUCS" = '[["PRINCIPAL","principal"],["LA 21","estandar"],["GLORIETA","estandar"],["BODEGA_CENTRAL","bodega_central"]]' ] \
  && green "PRINCIPAL, LA 21, GLORIETA y BODEGA_CENTRAL con su tipo" || red "Ubicaciones=$SUCS"

# Test 12: Campos sucursal (ciudad y departamento pueden ser nulos)
HAS_FIELDS_S=$(echo $RESP_SUC | jq '.items[0] | has("id_sucursal") and has("ciudad") and has("tipo") and has("factor_volumen")')
[ "$HAS_FIELDS_S" = "true" ] && green "Campos sucursal completos" || red "Faltan campos sucursal"

# Test 13: Factor volumen PRINCIPAL = 4.5; la Bodega no tiene
FACTOR=$(echo $RESP_SUC | jq -c '[.items[] | select(.nombre=="PRINCIPAL" or .nombre=="BODEGA_CENTRAL") | .factor_volumen]')
[ "$FACTOR" = "[4.5,null]" ] && green "Factor volumen PRINCIPAL=4.5, Bodega nulo" || red "Factor volumen=$FACTOR"

# Test 14: Sin auth
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/consulta/sucursales")
[ "$STATUS" = "403" ] || [ "$STATUS" = "401" ] && green "Sucursales sin token → $STATUS" || red "Sucursales sin token → $STATUS"

# ══════════════════════════════════════════════════════
header "GET /consulta/proveedores"

# Test 15: Listar proveedores
RESP_PROV=$(curl -s "$BASE/consulta/proveedores" -H "$AUTH")
TOTAL_PROV=$(echo $RESP_PROV | jq '.total')
[ "$TOTAL_PROV" = "10" ] && green "Proveedores total=10" || red "Proveedores total=$TOTAL_PROV"

# Test 16: Tiene lead_time_dias
HAS_LT=$(echo $RESP_PROV | jq '.items[0] | has("lead_time_dias")')
[ "$HAS_LT" = "true" ] && green "Incluye lead_time_dias" || red "Sin lead_time_dias"

# Test 17: Lead times en rango 3-15
MIN_LT=$(echo $RESP_PROV | jq '[.items[].lead_time_dias] | min')
MAX_LT=$(echo $RESP_PROV | jq '[.items[].lead_time_dias] | max')
[ "$MIN_LT" -ge 3 ] && [ "$MAX_LT" -le 15 ] && green "Lead times en rango 3-15 ($MIN_LT-$MAX_LT)" || red "Lead times fuera de rango $MIN_LT-$MAX_LT"

# Test 18: Tiene categorias como array
FIRST_CATS=$(echo $RESP_PROV | jq '.items[0].categorias | type')
[ "$FIRST_CATS" = '"array"' ] && green "Categorias como array" || red "Categorias no es array"

# Test 19: Tiene calificación
HAS_CAL=$(echo $RESP_PROV | jq '.items[0] | has("calificacion")')
[ "$HAS_CAL" = "true" ] && green "Incluye calificacion" || red "Sin calificacion"

# Test 20: Ordenados por calificación DESC
CAL1=$(echo $RESP_PROV | jq '.items[0].calificacion')
CAL_LAST=$(echo $RESP_PROV | jq '.items[-1].calificacion')
ORDERED=$(echo "$CAL1 >= $CAL_LAST" | bc -l 2>/dev/null || echo "1")
[ "$ORDERED" = "1" ] && green "Ordenados por calificacion DESC" || red "No ordenados por calificacion"

# ══════════════════════════════════════════════════════
header "GET /consulta/proveedores/:id (detalle)"

# Test 21: Detalle proveedor existente
FIRST_PROV_ID=$(echo $RESP_PROV | jq '.items[0].id_proveedor')
RESP_PROV_DET=$(curl -s "$BASE/consulta/proveedores/$FIRST_PROV_ID" -H "$AUTH")
DET_PROV_ID=$(echo $RESP_PROV_DET | jq '.id_proveedor')
HAS_PRODS=$(echo $RESP_PROV_DET | jq 'has("productos") and has("total_productos")')
[ "$DET_PROV_ID" = "$FIRST_PROV_ID" ] && green "Detalle proveedor $FIRST_PROV_ID OK" || red "Detalle proveedor failed"
[ "$HAS_PRODS" = "true" ] && green "Incluye productos y total_productos" || red "Sin productos en detalle"

# Test 22: Productos del proveedor según dw.producto_proveedor (INV-25)
PROV1=$(curl -s "$BASE/consulta/proveedores/1" -H "$AUTH" | jq -c '[.razon_social, .total_productos, (.productos | length)]')
[ "$PROV1" = '["Distribuidora Valle S.A.S.",1978,1978]' ] && green "Proveedor 1 con 1978 productos" || red "Proveedor 1=$PROV1"

# Test 23: Proveedor inexistente
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/consulta/proveedores/99999" -H "$AUTH")
[ "$STATUS" = "404" ] && green "Proveedor 99999 → 404" || red "Proveedor 99999 → $STATUS"

# ══════════════════════════════════════════════════════
header "GET /consulta/categorias"

# Test 24: Listar categorías
RESP_CAT=$(curl -s "$BASE/consulta/categorias" -H "$AUTH")
TOTAL_CATS=$(echo $RESP_CAT | jq '.total')
[ "$TOTAL_CATS" -ge 10 ] && green "Categorias total=$TOTAL_CATS (≥10)" || red "Categorias total=$TOTAL_CATS (<10)"

# Test 25: Campos categoría
HAS_FIELDS_C=$(echo $RESP_CAT | jq '.items[0] | has("categoria") and has("total_productos") and has("perecederos") and has("no_perecederos")')
[ "$HAS_FIELDS_C" = "true" ] && green "Campos categoria completos" || red "Faltan campos categoria"

# Test 26: Suma de perecederos + no_perecederos = total
FIRST_TOTAL=$(echo $RESP_CAT | jq '.items[0].total_productos')
FIRST_P=$(echo $RESP_CAT | jq '.items[0].perecederos')
FIRST_NP=$(echo $RESP_CAT | jq '.items[0].no_perecederos')
SUM=$((FIRST_P + FIRST_NP))
[ "$SUM" = "$FIRST_TOTAL" ] && green "perecederos + no_perecederos = total ($SUM=$FIRST_TOTAL)" || red "Suma no cuadra $SUM ≠ $FIRST_TOTAL"

# Test 27: Sin auth
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/consulta/categorias")
[ "$STATUS" = "403" ] || [ "$STATUS" = "401" ] && green "Categorias sin token → $STATUS" || red "Categorias sin token → $STATUS"

# ══════════════════════════════════════════════════════
header "RBAC — Todos los roles acceden (solo lectura)"

for USER_EMAIL in "admin.principal@inventaio.co" "bodega@inventaio.co"; do
  TOK=$(curl -s -X POST $BASE/auth/login \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$USER_EMAIL\",\"password\":\"admin123\"}" | jq -r '.access_token')
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/consulta/productos" \
    -H "Authorization: Bearer $TOK")
  ROL=$(curl -s "$BASE/auth/me" -H "Authorization: Bearer $TOK" | jq -r '.rol')
  [ "$STATUS" = "200" ] && green "RBAC: $ROL ($USER_EMAIL) → 200" || red "RBAC: $ROL → $STATUS"
done

# ══════════════════════════════════════════════════════
header "RESUMEN"
TOTAL=$((PASS + FAIL))
echo -e "\n  Total: $TOTAL tests"
echo -e "  \033[32m✅ Passed: $PASS\033[0m"
echo -e "  \033[31m❌ Failed: $FAIL\033[0m"

if [ $FAIL -eq 0 ]; then
  echo -e "\n\033[32m🎉 ALL TESTS PASSED\033[0m\n"
else
  echo -e "\n\033[31m⚠️  $FAIL TEST(S) FAILED\033[0m\n"
  exit 1
fi
