#!/bin/bash
# ============================================================
# InventAI/o — Auth Module Test Script (curl)
# Run: bash tests/test_auth.sh
# Requires: curl, jq
# Pre-requisite: API running on localhost:8000
# ============================================================

BASE="http://localhost:8000/api"
PASS=0
FAIL=0

green() { echo -e "\033[32m✅ $1\033[0m"; PASS=$((PASS+1)); }
red() { echo -e "\033[31m❌ $1\033[0m"; FAIL=$((FAIL+1)); }
header() { echo -e "\n\033[1;34m══ $1 ══\033[0m"; }

# ── Health check ─────────────────────────────────────
header "HEALTH CHECK"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" $BASE/health)
[ "$STATUS" = "200" ] && green "GET /health → 200" || red "GET /health → $STATUS (expected 200)"

# ── LOGIN ────────────────────────────────────────────
header "POST /auth/login"

# Test 1: Login exitoso como gerente
RESPONSE=$(curl -s -X POST $BASE/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"gerente@inventaio.co","password":"admin123"}')

ACCESS=$(echo $RESPONSE | jq -r '.access_token // empty')
REFRESH=$(echo $RESPONSE | jq -r '.refresh_token // empty')

if [ -n "$ACCESS" ] && [ -n "$REFRESH" ]; then
  green "Login gerente → access_token + refresh_token"
else
  red "Login gerente → no tokens received: $RESPONSE"
fi

# Test 2: Login con contraseña incorrecta
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST $BASE/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"gerente@inventaio.co","password":"wrongpass"}')
[ "$STATUS" = "401" ] && green "Login wrong password → 401" || red "Login wrong password → $STATUS (expected 401)"

# Test 3: Login con email inexistente
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST $BASE/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"noexiste@inventaio.co","password":"admin123"}')
[ "$STATUS" = "401" ] && green "Login unknown email → 401" || red "Login unknown email → $STATUS (expected 401)"

# Test 4: Login como admin_sucursal
RESP_ADMIN=$(curl -s -X POST $BASE/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin.principal@inventaio.co","password":"admin123"}')
ACCESS_ADMIN=$(echo $RESP_ADMIN | jq -r '.access_token // empty')
[ -n "$ACCESS_ADMIN" ] && green "Login admin_sucursal → OK" || red "Login admin_sucursal → failed"

# Test 5: Login como admin_bodega
RESP_BODEGA=$(curl -s -X POST $BASE/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"bodega@inventaio.co","password":"admin123"}')
ACCESS_BODEGA=$(echo $RESP_BODEGA | jq -r '.access_token // empty')
[ -n "$ACCESS_BODEGA" ] && green "Login admin_bodega → OK" || red "Login admin_bodega → failed"

# ── GET /auth/me ─────────────────────────────────────
header "GET /auth/me"

# Test 6: Perfil del gerente
ME=$(curl -s $BASE/auth/me -H "Authorization: Bearer $ACCESS")
ROL=$(echo $ME | jq -r '.rol // empty')
NOMBRE=$(echo $ME | jq -r '.nombre // empty')
EMAIL_ME=$(echo $ME | jq -r '.email // empty')

[ "$ROL" = "gerente" ] && green "GET /me rol → gerente" || red "GET /me rol → $ROL (expected gerente)"
[ "$EMAIL_ME" = "gerente@inventaio.co" ] && green "GET /me email → correct" || red "GET /me email → $EMAIL_ME"
[ -n "$NOMBRE" ] && green "GET /me nombre → $NOMBRE" || red "GET /me nombre → empty"

# Test 7: Perfil del admin_sucursal (tiene sucursal asignada)
ME_ADMIN=$(curl -s $BASE/auth/me -H "Authorization: Bearer $ACCESS_ADMIN")
SUC=$(echo $ME_ADMIN | jq -r '.sucursal_nombre // empty')
[ -n "$SUC" ] && green "GET /me admin has sucursal → $SUC" || red "GET /me admin sucursal → empty"

# Test 8: Sin token
STATUS=$(curl -s -o /dev/null -w "%{http_code}" $BASE/auth/me)
[ "$STATUS" = "403" ] || [ "$STATUS" = "401" ] && green "GET /me no token → $STATUS" || red "GET /me no token → $STATUS (expected 401/403)"

# Test 9: Token inválido
STATUS=$(curl -s -o /dev/null -w "%{http_code}" $BASE/auth/me \
  -H "Authorization: Bearer invalid.token.here")
[ "$STATUS" = "401" ] && green "GET /me invalid token → 401" || red "GET /me invalid token → $STATUS"

# ── POST /auth/refresh ───────────────────────────────
header "POST /auth/refresh"

# Test 10: Refresh token válido
RESP_REFRESH=$(curl -s -X POST $BASE/auth/refresh \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\":\"$REFRESH\"}")
NEW_ACCESS=$(echo $RESP_REFRESH | jq -r '.access_token // empty')
NEW_REFRESH=$(echo $RESP_REFRESH | jq -r '.refresh_token // empty')
[ -n "$NEW_ACCESS" ] && green "Refresh → new access_token" || red "Refresh → no access_token: $RESP_REFRESH"

# Test 11: Refresh token ya usado (blacklisted)
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST $BASE/auth/refresh \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\":\"$REFRESH\"}")
[ "$STATUS" = "401" ] && green "Refresh reused token → 401 (blacklisted)" || red "Refresh reused → $STATUS (expected 401)"

# Test 12: Refresh con access_token (wrong type)
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST $BASE/auth/refresh \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\":\"$NEW_ACCESS\"}")
[ "$STATUS" = "401" ] && green "Refresh with access_token → 401" || red "Refresh with access_token → $STATUS"

# Actualizar token de trabajo
ACCESS="$NEW_ACCESS"
REFRESH="$NEW_REFRESH"

# ── PATCH /auth/password ─────────────────────────────
header "PATCH /auth/password"

# Test 13: Cambiar contraseña exitosamente
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH $BASE/auth/password \
  -H "Authorization: Bearer $ACCESS" \
  -H "Content-Type: application/json" \
  -d '{"current_password":"admin123","new_password":"newSecure456"}')
[ "$STATUS" = "200" ] && green "Change password → 200" || red "Change password → $STATUS"

# Test 14: Login con nueva contraseña
RESP_NEW=$(curl -s -X POST $BASE/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"gerente@inventaio.co","password":"newSecure456"}')
TOKEN_NEW=$(echo $RESP_NEW | jq -r '.access_token // empty')
[ -n "$TOKEN_NEW" ] && green "Login with new password → OK" || red "Login with new password → failed"

# Test 15: Login con vieja contraseña falla
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST $BASE/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"gerente@inventaio.co","password":"admin123"}')
[ "$STATUS" = "401" ] && green "Login old password → 401" || red "Login old password → $STATUS"

# Test 16: Cambiar con contraseña actual incorrecta
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH $BASE/auth/password \
  -H "Authorization: Bearer $TOKEN_NEW" \
  -H "Content-Type: application/json" \
  -d '{"current_password":"wrongcurrent","new_password":"anotherPass789"}')
[ "$STATUS" = "400" ] && green "Change wrong current → 400" || red "Change wrong current → $STATUS"

# Test 17: Nueva contraseña igual a la actual
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH $BASE/auth/password \
  -H "Authorization: Bearer $TOKEN_NEW" \
  -H "Content-Type: application/json" \
  -d '{"current_password":"newSecure456","new_password":"newSecure456"}')
[ "$STATUS" = "400" ] && green "Change same password → 400" || red "Change same password → $STATUS"

# Restaurar contraseña original para siguientes tests
curl -s -X PATCH $BASE/auth/password \
  -H "Authorization: Bearer $TOKEN_NEW" \
  -H "Content-Type: application/json" \
  -d '{"current_password":"newSecure456","new_password":"admin123"}' > /dev/null

# ── POST /auth/logout ────────────────────────────────
header "POST /auth/logout"

# Login fresco para logout test
RESP_LOGOUT=$(curl -s -X POST $BASE/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"gerente@inventaio.co","password":"admin123"}')
ACC_LOGOUT=$(echo $RESP_LOGOUT | jq -r '.access_token')
REF_LOGOUT=$(echo $RESP_LOGOUT | jq -r '.refresh_token')

# Test 18: Logout exitoso
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST $BASE/auth/logout \
  -H "Authorization: Bearer $ACC_LOGOUT" \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\":\"$REF_LOGOUT\"}")
[ "$STATUS" = "200" ] && green "Logout → 200" || red "Logout → $STATUS"

# Test 19: Refresh después de logout falla
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST $BASE/auth/refresh \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\":\"$REF_LOGOUT\"}")
[ "$STATUS" = "401" ] && green "Refresh after logout → 401" || red "Refresh after logout → $STATUS"

# ── RBAC ─────────────────────────────────────────────
header "RBAC (Role-Based Access Control)"

# Test 20: Verificar que cada rol tiene la información correcta
for USER_EMAIL in "gerente@inventaio.co" "admin.principal@inventaio.co" "bodega@inventaio.co"; do
  RESP=$(curl -s -X POST $BASE/auth/login \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$USER_EMAIL\",\"password\":\"admin123\"}")
  TOK=$(echo $RESP | jq -r '.access_token')
  ROLE=$(curl -s $BASE/auth/me -H "Authorization: Bearer $TOK" | jq -r '.rol')
  [ -n "$ROLE" ] && green "RBAC: $USER_EMAIL → rol=$ROLE" || red "RBAC: $USER_EMAIL → no role"
done

# ── RESUMEN ──────────────────────────────────────────
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
