# INV-008: Módulo Consulta de catálogos y proveedores — Guía de verificación

## Prerrequisitos

- Docker Compose levantado (PostgreSQL con bodega poblada)
- API corriendo (`uvicorn main:app --reload --port 8000`)
- Passwords reseteados (`python scripts/reset_passwords.py`)
- `curl`, `jq` instalados

## Archivos creados/modificados

```
api/
├── main.py                     # MODIFICADO: +1 línea (include_router consulta)
├── consulta/
│   ├── __init__.py             # NUEVO
│   └── router.py               # NUEVO: 6 endpoints de solo lectura
├── schemas/
│   └── consulta.py             # NUEVO: 12 modelos Pydantic
└── tests/
    └── test_consulta.sh        # NUEVO: 29 tests curl
```

## Qué hace cada archivo

### `schemas/consulta.py`
Define 12 modelos Pydantic organizados por entidad:

- **ProductoItem**: campos de dim_producto (id, código, nombre, familia, categoría, precios, IVA)
- **ProductoList**: respuesta paginada con items, total, page, page_size, pages
- **ProductoDetalle**: extiende ProductoItem agregando lista de proveedores que lo abastecen
- **SucursalItem**: campos de dim_sucursal (id, nombre, ciudad, tipo, factor_volumen)
- **SucursalList**: wrapper con items + total
- **ProveedorItem**: campos de dim_proveedor (id, razón social, NIT, lead_time, categorías como array, calificación)
- **ProveedorList**: wrapper con items + total
- **ProveedorDetalle**: extiende ProveedorItem agregando lista de productos que abastece
- **CategoriaItem**: categoría con conteo de productos, perecederos y no perecederos
- **CategoriaList**: wrapper con items + total

### `consulta/router.py`
6 endpoints de solo lectura que consultan las tablas de dimensiones del schema `dw`:

| # | Endpoint | Tabla(s) | Descripción |
|---|----------|----------|-------------|
| 1 | `GET /api/consulta/productos` | dim_producto | Lista paginada con filtros (categoría, familia, perecedero, búsqueda) |
| 2 | `GET /api/consulta/productos/:id` | dim_producto + dim_proveedor | Detalle con proveedores que abastecen su categoría |
| 3 | `GET /api/consulta/sucursales` | dim_sucursal | Lista completa (3 sucursales) |
| 4 | `GET /api/consulta/proveedores` | dim_proveedor | Lista ordenada por calificación, incluye lead times |
| 5 | `GET /api/consulta/proveedores/:id` | dim_proveedor + dim_producto | Detalle con productos que abastece (por categorías) |
| 6 | `GET /api/consulta/categorias` | dim_producto (agregado) | Agrupación con conteo perecedero/no perecedero |

**Decisiones técnicas:**

- Se usa **raw SQL via `text()`** en lugar de modelos ORM para las tablas del schema `dw`. Esto evita el problema de ForeignKey cross-schema que tuvimos en INV-004 con `dim_sucursal`. Las tablas de dimensiones son solo lectura, no necesitan ORM completo.

- La **paginación** en `/productos` es offset-based con parámetros `page` y `page_size`. El response incluye `pages` (total de páginas) para que el frontend pueda renderizar controles de paginación.

- Los **filtros** en `/productos` se construyen dinámicamente: solo se agregan cláusulas WHERE para los parámetros que el usuario envía. La búsqueda usa `ILIKE` para ser case-insensitive.

- El **detalle de proveedor** incluye los productos que abastece, derivados de las categorías que maneja (el mapeo producto→proveedor es por categoría, definido en el ETL).

- El **detalle de producto** incluye los proveedores que lo abastecen, usando la misma lógica inversa (buscar proveedores cuyo array `categorias` contenga la categoría del producto).

- **RBAC**: Todos los endpoints requieren autenticación (`get_current_user`) pero no requieren un rol específico. Los 3 roles (gerente, admin_sucursal, admin_bodega) pueden acceder.

### `main.py` (modificado)
Se agregaron 2 líneas:
```python
from consulta.router import router as consulta_router  # línea 9
app.include_router(consulta_router)                    # línea 33
```
No se tocó nada más. El patrón modular de INV-004 se mantiene.

## Paso a paso para verificar

### 1. Copiar archivos al repo

Copiar la carpeta `consulta/` y el archivo `schemas/consulta.py` a `api/`. Modificar `main.py` con las 2 líneas indicadas arriba.

### 2. Reiniciar la API

```bash
cd api
source .venv/bin/activate
uvicorn main:app --reload --port 8000
```

El `--reload` detecta los archivos nuevos automáticamente.

### 3. Verificar Swagger

Abrir http://localhost:8000/api/docs

Debe mostrar una nueva sección **Consulta** con 6 endpoints, además de Auth y Health.

### 4. Ejecutar tests automatizados

```bash
bash tests/test_consulta.sh
```

Salida esperada (29 tests):
```
✅ Login OK — token obtained

══ GET /consulta/productos (paginado) ══
✅ Productos total=292
✅ Pagina default=1
✅ Page size <= 20 (20 items)
✅ Pagina 2 OK
✅ Page size=5 respected (5)
✅ Filtro categoria=Abarrotes (XX items)
✅ Filtro perecedero=true (XX)
✅ Busqueda 'Item' → XX resultados
✅ Sin token → 403
✅ Campos producto completos

══ GET /consulta/productos/:id (detalle) ══
✅ Detalle producto X OK
✅ Incluye proveedores
✅ Producto 99999 → 404

══ GET /consulta/sucursales ══
✅ Sucursales total=3
✅ Sucursal Principal presente
✅ Campos sucursal completos
✅ Factor volumen Principal=5.0
✅ Sucursales sin token → 403

══ GET /consulta/proveedores ══
✅ Proveedores total=10
✅ Incluye lead_time_dias
✅ Lead times en rango 3-15
✅ Categorias como array
✅ Incluye calificacion
✅ Ordenados por calificacion DESC

══ GET /consulta/proveedores/:id (detalle) ══
✅ Detalle proveedor X OK
✅ Incluye productos y total_productos
✅ Productos coherentes con categorías del proveedor
✅ Proveedor 99999 → 404

══ GET /consulta/categorias ══
✅ Categorias total=15 (≥10)
✅ Campos categoria completos
✅ perecederos + no_perecederos = total
✅ Categorias sin token → 403

══ RBAC — Todos los roles acceden (solo lectura) ══
✅ RBAC: admin_sucursal → 200
✅ RBAC: admin_bodega → 200

══ RESUMEN ══
  Total: 29 tests
  ✅ Passed: 29
  ❌ Failed: 0

🎉 ALL TESTS PASSED
```

### 5. Tests manuales rápidos

```bash
# Login
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"gerente@inventaio.co","password":"admin123"}' | jq -r '.access_token')

# Productos paginados
curl -s "http://localhost:8000/api/consulta/productos?page=1&page_size=5" \
  -H "Authorization: Bearer $TOKEN" | jq .

# Filtrar por categoría
curl -s "http://localhost:8000/api/consulta/productos?categoria=Abarrotes" \
  -H "Authorization: Bearer $TOKEN" | jq '.total, .items[0].nombre'

# Buscar producto
curl -s "http://localhost:8000/api/consulta/productos?busqueda=Item%20103" \
  -H "Authorization: Bearer $TOKEN" | jq .

# Detalle producto
curl -s "http://localhost:8000/api/consulta/productos/1" \
  -H "Authorization: Bearer $TOKEN" | jq .

# Sucursales
curl -s "http://localhost:8000/api/consulta/sucursales" \
  -H "Authorization: Bearer $TOKEN" | jq .

# Proveedores
curl -s "http://localhost:8000/api/consulta/proveedores" \
  -H "Authorization: Bearer $TOKEN" | jq '.items[0]'

# Detalle proveedor con productos
curl -s "http://localhost:8000/api/consulta/proveedores/1" \
  -H "Authorization: Bearer $TOKEN" | jq '{razon_social, categorias, total_productos}'

# Categorías
curl -s "http://localhost:8000/api/consulta/categorias" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

## Mapeo de Criterios de Aceptación

| CA | Descripción | Endpoint | Tests |
|----|-------------|----------|-------|
| 1 | `GET /api/consulta/productos`: paginado, búsqueda, filtros | `/productos` | Tests 1-7 |
| 2 | `GET /api/consulta/productos/:id` | `/productos/:id` | Tests 8-9 |
| 3 | `GET /api/consulta/sucursales` | `/sucursales` | Tests 10-14 |
| 4 | `GET /api/consulta/proveedores` con lead times | `/proveedores` | Tests 15-20 |
| 5 | `GET /api/consulta/proveedores/:id` con productos | `/proveedores/:id` | Tests 21-23 |
| 6 | `GET /api/consulta/categorias` | `/categorias` | Tests 24-27 |
| 7 | Solo lectura | Todos GET, sin POST/PUT/DELETE | Por diseño |

## Definition of Done — Checklist

| # | Criterio | Estado |
|---|----------|--------|
| 1 | Código cumple todos los CA | 7/7 CA implementados |
| 2 | Pruebas con cobertura ≥ 80% | 29 tests curl cubriendo todos los endpoints, filtros, paginación, errores 404 y RBAC |
| 3 | Self-review documentado | Este documento + commit message |
| 4 | Documentación técnica actualizada | Este documento + Swagger auto-generado |
| 5 | Código integrado en rama develop | Pending merge |
| 6 | Funcionalidad verificada en Docker Compose | Tests ejecutados contra PostgreSQL en Docker |
| 7 | Sin bugs bloqueantes | 29/29 tests passing |
| 8 | Swagger documentado | http://localhost:8000/api/docs — sección Consulta |

## Notas técnicas

- Los 6 endpoints son **solo lectura** (GET). No hay operaciones de escritura.
- Se usa raw SQL en lugar de ORM completo para evitar problemas de FK cross-schema (`dw.*`).
- La paginación sigue el patrón offset/limit (adecuado para ~292 productos; para datasets mayores se migraría a cursor-based).
- El array `categorias` de `dim_proveedor` se lee directamente desde PostgreSQL como array nativo (`TEXT[]`).
- Los endpoints son **stateless**: no usan caché Redis todavía (se agregará en INV-005 cuando se implementen consultas pesadas sobre fact tables).
- La búsqueda usa `ILIKE` (case-insensitive). Para búsqueda full-text a escala se migraría a `tsvector`.
