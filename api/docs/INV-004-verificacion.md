# INV-004: Módulo Auth — Guía de Verificación

## Prerrequisitos

- Docker Compose levantado (PostgreSQL + Redis)
- ETL ejecutado (tabla `app.usuarios` con 5 usuarios seed)
- Python 3.11+ con pip

## Estructura de archivos creados

```
api/
├── main.py                  # App FastAPI, monta el router de auth
├── requirements.txt         # Dependencias Python
├── core/
│   ├── __init__.py
│   ├── config.py            # Settings desde .env (DB, Redis, JWT)
│   ├── database.py          # SQLAlchemy engine + get_db dependency
│   └── security.py          # JWT create/decode + bcrypt hash/verify
├── models/
│   ├── __init__.py
│   └── usuario.py           # SQLAlchemy model → app.usuarios
├── schemas/
│   ├── __init__.py
│   └── auth.py              # Pydantic: LoginRequest, TokenResponse, etc.
├── auth/
│   ├── __init__.py
│   ├── dependencies.py      # get_current_user + require_role()
│   └── router.py            # 5 endpoints de auth
├── scripts/
│   └── reset_passwords.py   # Resetea passwords seed a bcrypt válidos
└── tests/
    ├── __init__.py
    └── test_auth.sh          # 22 tests con curl + jq
```

## Qué hace cada archivo

### `core/config.py`
Lee variables de entorno (o `.env`) para configurar la conexión a PostgreSQL, Redis y los parámetros JWT (secret key, algoritmo, tiempos de expiración). Usa `pydantic-settings` para validación automática.

### `core/database.py`
Crea el engine de SQLAlchemy y la función `get_db()` que es una dependencia de FastAPI — cada request recibe una sesión de DB que se cierra automáticamente al terminar.

### `core/security.py`
Dos funciones de password (`hash_password`, `verify_password`) usando bcrypt via passlib, y tres de JWT (`create_access_token`, `create_refresh_token`, `decode_token`) usando python-jose. Los tokens llevan un campo `type` ("access" o "refresh") para distinguirlos.

### `models/usuario.py`
Mapeo SQLAlchemy de la tabla `app.usuarios` que ya existe en PostgreSQL (creada por `init.sql`). No crea la tabla — solo la lee.

### `schemas/auth.py`
Modelos Pydantic para validar requests y serializar responses:
- `LoginRequest`: email + password
- `RefreshRequest`: refresh_token
- `PasswordChangeRequest`: current_password + new_password (mín 8 chars)
- `TokenResponse`: access_token + refresh_token + token_type
- `UserProfile`: datos del usuario (incluyendo nombre de sucursal)
- `MessageResponse`: mensaje genérico

### `auth/dependencies.py`
Dos dependencias reutilizables:
- `get_current_user`: extrae Bearer token del header, decodifica JWT, busca usuario en DB, valida que esté activo. Retorna el objeto `Usuario` o lanza 401/403.
- `require_role(["gerente", "admin_sucursal"])`: factory que retorna una dependencia que verifica el rol del usuario. Se usa como `Depends(require_role(["gerente"]))` en cualquier endpoint futuro.

### `auth/router.py`
5 endpoints:

| Método | Ruta | Qué hace |
|--------|------|----------|
| `POST` | `/api/auth/login` | Recibe email + password, valida contra `app.usuarios`, retorna access_token (30 min) + refresh_token (7 días) |
| `POST` | `/api/auth/refresh` | Recibe refresh_token, lo invalida (blacklist), genera nuevos tokens |
| `POST` | `/api/auth/logout` | Recibe refresh_token + access_token en header, blacklistea el refresh |
| `GET` | `/api/auth/me` | Retorna perfil del usuario autenticado (incluye nombre_sucursal de dim_sucursal) |
| `PATCH` | `/api/auth/password` | Valida contraseña actual, actualiza hash con la nueva |

### `scripts/reset_passwords.py`
El ETL cargó hashes placeholder (`$2b$12$LJ3L5xH...`) que no corresponden a ninguna contraseña real. Este script actualiza todos los usuarios con un hash bcrypt válido para la contraseña `admin123`.

## Paso a paso para verificar

### 1. Instalar dependencias

```bash
cd api
pip install -r requirements.txt
```

### 2. Resetear passwords de usuarios seed

```bash
python scripts/reset_passwords.py
```

Salida esperada:
```
Resetting all seed user passwords to 'admin123'
Bcrypt hash: $2b$12$...
Updated 5 users

Users ready for login:
  gerente@inventaio.co              Carlos Martínez      gerente
  admin.principal@inventaio.co      Laura Gómez          admin_sucursal
  admin.norte@inventaio.co          Andrés Rivera        admin_sucursal
  admin.sur@inventaio.co            María Torres         admin_sucursal
  bodega@inventaio.co               Diego Sánchez        admin_bodega

Password for all: admin123
```

### 3. Levantar la API

```bash
cd api
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Salida esperada:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Started reloader process
```

### 4. Verificar Swagger

Abrir en navegador: http://localhost:8000/api/docs

Debe mostrar:
- Sección **Auth** con 5 endpoints
- Sección **Health** con 1 endpoint
- Cada endpoint con esquemas de request/response documentados
- Botón "Authorize" para probar con Bearer token

### 5. Ejecutar tests automatizados

En otra terminal:

```bash
cd api
bash tests/test_auth.sh
```

Salida esperada (22 tests):
```
══ HEALTH CHECK ══
✅ GET /health → 200

══ POST /auth/login ══
✅ Login gerente → access_token + refresh_token
✅ Login wrong password → 401
✅ Login unknown email → 401
✅ Login admin_sucursal → OK
✅ Login admin_bodega → OK

══ GET /auth/me ══
✅ GET /me rol → gerente
✅ GET /me email → correct
✅ GET /me nombre → Carlos Martínez
✅ GET /me admin has sucursal → Sucursal Principal
✅ GET /me no token → 403
✅ GET /me invalid token → 401

══ POST /auth/refresh ══
✅ Refresh → new access_token
✅ Refresh reused token → 401 (blacklisted)
✅ Refresh with access_token → 401

══ PATCH /auth/password ══
✅ Change password → 200
✅ Login with new password → OK
✅ Login old password → 401
✅ Change wrong current → 400
✅ Change same password → 400

══ POST /auth/logout ══
✅ Logout → 200
✅ Refresh after logout → 401

══ RBAC (Role-Based Access Control) ══
✅ RBAC: gerente@inventaio.co → rol=gerente
✅ RBAC: admin.principal@inventaio.co → rol=admin_sucursal
✅ RBAC: bodega@inventaio.co → rol=admin_bodega

══ RESUMEN ══
  Total: 22 tests
  ✅ Passed: 22
  ❌ Failed: 0

🎉 ALL TESTS PASSED
```

### 6. Tests manuales rápidos con curl

```bash
# Login
curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"gerente@inventaio.co","password":"admin123"}' | jq .

# Usar el access_token retornado
TOKEN="<pegar access_token aquí>"

# Ver perfil
curl -s http://localhost:8000/api/auth/me \
  -H "Authorization: Bearer $TOKEN" | jq .

# Cambiar contraseña
curl -s -X PATCH http://localhost:8000/api/auth/password \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"current_password":"admin123","new_password":"nuevaClave456"}' | jq .
```

## Mapeo de Criterios de Aceptación

| CA | Descripción | Verificación |
|----|-------------|-------------|
| 1 | `POST /api/auth/login` retorna access + refresh | Tests 1, 4, 5 |
| 2 | `POST /api/auth/refresh` renueva tokens | Tests 10, 11, 12 |
| 3 | `POST /api/auth/logout` invalida sesión | Tests 18, 19 |
| 4 | `GET /api/auth/me` retorna perfil | Tests 6, 7, 8, 9 |
| 5 | `PATCH /api/auth/password` cambia contraseña | Tests 13, 14, 15, 16, 17 |
| 6 | Tres roles: gerente, admin_sucursal, admin_bodega | Tests 20-22 |
| 7 | `require_role()` reutilizable | `auth/dependencies.py` línea 52 |
| 8 | Passwords bcrypt, tokens con expiración configurable | `core/security.py`, `core/config.py` |
| 9 | Autenticación contra `app.usuarios` existente | `auth/router.py` línea 41 |
| 10 | Documentación OpenAPI/Swagger | http://localhost:8000/api/docs |

## Notas técnicas

- Los access tokens expiran en 30 minutos (configurable via `ACCESS_TOKEN_EXPIRE_MINUTES`)
- Los refresh tokens expiran en 7 días (configurable via `REFRESH_TOKEN_EXPIRE_DAYS`)
- El blacklist de tokens es in-memory (se pierde al reiniciar). En producción se migrará a Redis
- Los passwords se hashean con bcrypt (factor de costo 12, por defecto de passlib)
- La dependencia `require_role()` está lista para usarse en INV-005, INV-006, INV-007, INV-008
- El endpoint `/me` hace un JOIN implícito con `dim_sucursal` para retornar `sucursal_nombre`
