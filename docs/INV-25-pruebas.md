# INV-25 · Set de pruebas

Cómo validar INV-25 antes del merge a `develop`, en tres niveles: las pruebas
de pytest, los scripts de Release 1 y la colección de Postman con los 48
casos de abajo. Las cifras salen de la bodega real (foto al 2025-12-31); la
especificación está en [`INV-25-requerimientos.md`](INV-25-requerimientos.md)
y la implementación en [`INV-25-homologacion.md`](INV-25-homologacion.md).

## 0. Antes de empezar

- En la rama `feature/INV-25-homologacion-api`, con `postgres`, `ml-service` y
  `api` arriba (`docker compose up -d --build ml-service api`).
- Los usuarios de prueba cargados en `app.usuarios`, todos con la clave
  `admin123`:

| Usuario | Rol | Ubicación |
| --- | --- | --- |
| `gerente@inventaio.co` | `gerente` | Todas |
| `admin.principal@inventaio.co` | `admin_sucursal` | PRINCIPAL (1) |
| `admin.norte@inventaio.co` | `admin_sucursal` | LA 21 (2) |
| `bodega@inventaio.co` | `admin_bodega` | Todas |

Comprobación rápida: `curl -s http://localhost:8000/api/health` responde
`{"status":"ok",...}`.

## 1. Pytest, dentro del contenedor

```powershell
docker exec inventaio-api python -m pytest -m "not integracion"   # unitarias, unos 3 s
docker exec inventaio-api python -m pytest -m integracion         # contra la bodega real, unos 60 s
docker exec inventaio-api python -m pytest --cov=consulta --cov=inventario --cov=alertas --cov=reportes --cov=core.ubicaciones --cov=ml
```

Esperado: 131 pruebas pasan (107 unitarias y 24 de integración) y la
cobertura de los módulos tocados queda entre 98 % y 100 %. Si las de
integración salen como `skipped`, faltan los usuarios de prueba o la bodega.

## 2. Scripts de Release 1, desde Ubuntu (WSL)

```bash
cd /mnt/c/Users/diego/OneDrive/Documentos/Maestria/InventaIO
for s in consulta inventario alertas reportes recomendaciones; do bash api/tests/test_$s.sh; done
```

| Script | Esperado |
| --- | --- |
| `test_consulta.sh` | 37 de 37 |
| `test_inventario.sh` | 47 de 47 |
| `test_alertas.sh` | 39 de 39 |
| `test_reportes.sh` | 55 de 55 |
| `test_recomendaciones.sh` (INV-23) | 54 de 54 |

`test_auth.sh` no se corre: cambia contraseñas. Si un script falla con
`$'\r'`, quitarle los CRLF: `sed -i 's/\r$//' api/tests/test_<script>.sh`.

## 3. Postman

Los archivos están en `api/tests/postman/`:

| Archivo | Para qué |
| --- | --- |
| `INV-25.postman_collection.json` | Los 48 casos de la sección 4, con sus verificaciones. Es la que se corre para validar |
| `inventaio-core-api.openapi.yml` | El OpenAPI del Core API completo, para explorar los endpoints a mano |
| `exportar_openapi.py` | Regenera el YAML cuando cambie la API |

### Colección de casos

1. En Postman: **Import** → arrastrar `INV-25.postman_collection.json`.
2. En la colección, **Run** (Collection Runner) → **Run InventaIO · INV-25…**,
   con el orden por defecto: CP-29 compara contra la respuesta de CP-28.
3. Esperado: 53 peticiones (48 casos, el health y 4 logins), 182
   verificaciones y 0 fallas, en unos 45 s. CP-47 tarda unos 25 s si la
   caché de recomendaciones está vacía.

Los tokens se obtienen solos: la carpeta "00 Preparación" inicia sesión con
los cuatro usuarios, y si se corre un caso suelto, el script de la colección
lo hace antes. Si la API no está en `localhost:8000`, cambiar la variable
`baseUrl` de la colección.

La misma colección corre desde la terminal con Newman (Node.js):

```powershell
npx newman run api/tests/postman/INV-25.postman_collection.json --timeout-request 120000
```

### OpenAPI en YAML

1. **Import** → `inventaio-core-api.openapi.yml` → **View Import Settings**:
   - *Folder organization*: **Tags** (una carpeta por módulo).
   - *Parameter generation*: **Example** (llena los parámetros con datos reales: arroz P3937, PRINCIPAL).
   - *Enable optional parameters*: **apagado** (los filtros quedan desactivados; se activan a mano).
2. Correr **Auth → Iniciar sesión**, copiar el `access_token` y crear en la
   colección la variable `bearerToken` con ese valor. Vence a los 30 minutos.
3. Probar cualquier endpoint, activando los filtros que hagan falta.

No correr la carpeta **Auth** con el Runner: **Cambiar contraseña** le cambia
la clave al usuario del token, como `test_auth.sh`, y **Cerrar sesión** invalida
el token.

Para regenerar el YAML después de cambiar la API:

```powershell
docker exec inventaio-api python -m tests.postman.exportar_openapi
```

## 4. Casos de prueba

Cada caso es una petición de la colección con el mismo identificador. "admin
PRINCIPAL" y "admin LA 21" son `admin_sucursal`; "bodega" es `admin_bodega`.

### Consulta (D5, D6, D7)

| Caso | Usuario | Petición | Esperado |
| --- | --- | --- | --- |
| CP-01 | admin PRINCIPAL | `GET /api/consulta/productos?page_size=100` | 200; 4.449 productos; `codigo_item` es texto en todos |
| CP-02 | gerente | `GET /api/consulta/productos/3814` | 200; `codigo_item` = `00008` |
| CP-03 | gerente | `GET /api/consulta/productos/91` | 200; `P1632` con el proveedor Lácteos del Cauca Ltda. |
| CP-04 | gerente | `GET /api/consulta/proveedores/1` | 200; Distribuidora Valle S.A.S. con 1.978 productos |
| CP-05 | bodega | `GET /api/consulta/sucursales` | 200; PRINCIPAL, LA 21, GLORIETA y BODEGA_CENTRAL con su `tipo`; sin SIN_SUCURSAL; acepta nulos |

### Inventario (D1, D2, D6, R1, R3)

| Caso | Usuario | Petición | Esperado |
| --- | --- | --- | --- |
| CP-06 | gerente | `GET /api/consulta/inventario?page_size=100` | 200; 11.101 filas; `tipo_ubicacion` correcto y `stock_bodega` nulo solo en la Bodega |
| CP-07 | admin PRINCIPAL | `GET /api/consulta/inventario?page_size=100` | 200; 4.046 filas, todas de PRINCIPAL, con `stock_bodega` |
| CP-08 | admin PRINCIPAL | `GET /api/consulta/inventario?sucursal_id=5` | 200; 1.973 filas de la Bodega, `bodega_central` |
| CP-09 | admin PRINCIPAL | `GET /api/consulta/inventario?sucursal_id=2` | 403 "Solo puede consultar su sucursal (PRINCIPAL)" |
| CP-10 | admin LA 21 | `GET /api/consulta/inventario` | 200; 1.888 filas, todas de LA 21 |
| CP-11 | admin PRINCIPAL | `GET /api/consulta/inventario/detalle?id_producto=171&id_sucursal=1` | 200; arroz P3937: stock 556, cobertura 5,3 días, Bodega 4.024 |
| CP-12 | admin PRINCIPAL | `GET /api/consulta/inventario/detalle?id_producto=171&id_sucursal=5` | 200; `bodega_central`, stock 4.024, `stock_bodega` nulo |
| CP-13 | admin PRINCIPAL | `GET /api/consulta/inventario/detalle?id_producto=91&id_sucursal=1` | 200; huevos P1632 con `stock_bodega` 0 (la Bodega no tiene fila) |
| CP-14 | bodega | `GET /api/consulta/inventario/detalle?id_producto=91&id_sucursal=1` | 200 (antes 403); PRINCIPAL, stock 489 |
| CP-15 | bodega | `GET /api/consulta/inventario/resumen` | 200; 4 ubicaciones y 11.101 filas |
| CP-16 | gerente | `GET /api/consulta/inventario/resumen?sucursal_id=2` | 200; solo LA 21, 1.888 filas (antes 11.101) |
| CP-17 | admin PRINCIPAL | `GET /api/consulta/inventario/resumen?sucursal_id=5` | 200; 1.973 filas de la Bodega |
| CP-18 | gerente | `GET /api/consulta/inventario/valorizado?sucursal_id=1` | 200; 350.588.181,35, solo filas `sucursal` |

### Alertas (D2, D4, R1, R4)

| Caso | Usuario | Petición | Esperado |
| --- | --- | --- | --- |
| CP-19 | gerente | `GET /api/alertas/resumen` | 200; 4.452: inconsistencia 220, crítico 1.114, bajo 386, sin movimiento 2.453, rotación baja 279 |
| CP-20 | gerente | `GET /api/alertas?tipo=inconsistencia_inventario` | 200; 220, todas con stock negativo y urgencia `critica` |
| CP-21 | gerente | `GET /api/alertas?tipo=stock_critico` | 200; 1.114, ninguna negativa, 592 de la Bodega |
| CP-22 | bodega | `GET /api/alertas?sucursal_id=5` | 200; solo inconsistencia, stock crítico y stock bajo |
| CP-23 | admin PRINCIPAL | `GET /api/alertas/resumen` | 200; 1.308 de PRINCIPAL: 95, 202, 138, 865 y 8 |
| CP-24 | admin PRINCIPAL | `GET /api/alertas?sucursal_id=5` | 403 "…; la Bodega Central, solo en el stock" |
| CP-25 | admin PRINCIPAL | `GET /api/alertas/resumen?sucursal_id=3` | 403 |
| CP-26 | gerente | `GET /api/alertas/resumen?sucursal_id=3` | 200; solo GLORIETA |
| CP-27 | gerente | `GET /api/alertas?tipo=no_existe` | 400, como en Release 1 |

### Reportes (D1, R1, R6)

| Caso | Usuario | Petición | Esperado |
| --- | --- | --- | --- |
| CP-28 | gerente | `GET /api/reportes/kpis` | 200; ventas del mes 737.879.055,35 |
| CP-29 | bodega | `GET /api/reportes/kpis` | 200; iguales a los del gerente (antes vacíos) |
| CP-30 | bodega | `GET /api/reportes/ventas` | 200; 737.879.055,35 |
| CP-31 | bodega | `GET /api/reportes/ventas?sucursal_id=1` | 200; 471.756.931,58 |
| CP-32 | admin PRINCIPAL | `GET /api/reportes/ventas` | 200; 471.756.931,58 |
| CP-33 | admin PRINCIPAL | `GET /api/reportes/kpis?sucursal_id=5` | 403 "…; la Bodega Central, solo en el stock" |
| CP-34 | admin PRINCIPAL | `GET /api/reportes/tendencias?sucursal_id=3` | 403 |
| CP-35 | gerente | `GET /api/reportes/tendencias?dias=7` | 200; empieza el 2025-12-24, 8 puntos |
| CP-36 | gerente | `GET /api/reportes/tendencias` | 200; empieza el 2025-12-01 |

### `sucursal_id` inválido (R2, D7)

| Caso | Usuario | Petición | Esperado |
| --- | --- | --- | --- |
| CP-37 | gerente | `GET /api/consulta/inventario?sucursal_id=4` | 422 con la lista de válidos: 1, 2, 3 y 5 |
| CP-38 | gerente | `GET /api/alertas?sucursal_id=99` | 422 |
| CP-39 | gerente | `GET /api/reportes/kpis?sucursal_id=4` | 422 (antes, ventas de SIN_SUCURSAL) |
| CP-40 | gerente | `GET /api/consulta/inventario/detalle?id_producto=171&id_sucursal=99` | 422 (antes 404) |

### Pronóstico (D8, R5)

Cuerpo base: `{"producto_id": "P1632", "sucursal_id": "PRINCIPAL", "horizonte": 15}`.

| Caso | Usuario | Petición | Esperado |
| --- | --- | --- | --- |
| CP-41 | admin PRINCIPAL | `POST /api/ml/predict` | 200; q50 3.366,01, límite superior 4.608,72, rama `intermitente` |
| CP-42 | admin PRINCIPAL | `POST /api/ml/predict` con GLORIETA | 403 "Solo puede pronosticar su sucursal (PRINCIPAL)" |
| CP-43 | gerente | `POST /api/ml/predict` con BODEGA_CENTRAL | 422 de `ml_service`: "no es una sucursal física" |
| CP-44 | gerente | `POST /api/ml/predict` con `00070` en GLORIETA | 404 de `ml_service`: historia insuficiente |
| CP-45 | sin token | `POST /api/ml/predict` | 403 "Not authenticated" |
| CP-46 | sin token | `GET /api/openapi.json` | `predict` bajo "Pronóstico", con `HTTPBearer` |

### Regresión de INV-23 (D3)

| Caso | Usuario | Petición | Esperado |
| --- | --- | --- | --- |
| CP-47 | admin LA 21 | `GET /api/ml/recomendaciones/compras?incluir_detalle=false` | 200; LA 21 por su rol, 337 líneas |
| CP-48 | admin PRINCIPAL | `GET /api/ml/recomendaciones/compras?sucursal=BODEGA_CENTRAL` | 403, sin cambios |

## 5. Revisión en el Swagger

En http://localhost:8000/api/docs: **Authorize** con un `access_token`, y en
la sección **Pronóstico**, `POST /api/ml/predict` → **Try it out** con el
cuerpo base de la sección 4. Responde como CP-41 si el token es del gerente o
de admin PRINCIPAL.
Las recomendaciones de INV-23 aparecen junto a los demás endpoints.
