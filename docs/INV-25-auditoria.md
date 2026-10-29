# INV-25 · Auditoría del Core API contra la bodega real (Fase 1)

Auditoría del 2026-10-01, hecha antes de tocar código. Se recorrieron en vivo
los 23 endpoints del Core API (`api/`, puerto 8000) con un usuario de cada rol,
se leyeron sus routers y esquemas, y se corrieron los scripts de prueba de
Release 1 que no escriben en la base. La bodega es la real de INV-60/61 (foto
de inventario al 2025-12-31, ventas 2022–2025) con los usuarios de prueba.

Los requerimientos de la Fase 2, con las decisiones tomadas a partir de esta
auditoría, están en [`INV-25-requerimientos.md`](INV-25-requerimientos.md).

## Cómo se auditó

| Qué | Cómo |
| --- | --- |
| Endpoints | Cada GET con `gerente`, `admin.principal` (`admin_sucursal`, PRINCIPAL) y `bodega` (`admin_bodega`, BODEGA_CENTRAL), con y sin `sucursal_id`. Código HTTP, tiempo y un resumen de la respuesta |
| Errores 500 | La excepción en los logs del contenedor `inventaio-api` |
| Datos | Consultas de solo lectura a `dw.*`: nulos, centinelas, stock negativo, relación producto–proveedor |
| Pruebas de Release 1 | `test_consulta.sh`, `test_inventario.sh`, `test_alertas.sh` y `test_reportes.sh`. `test_auth.sh` no se corrió: cambia contraseñas |
| Frontend | Qué endpoints llama `frontend/src/api/client.js` y con qué parámetros |

`PATCH /api/auth/password` se revisó solo leyendo el código, porque escribe en
la base.

## Resultado por endpoint

**Compatible**: responde bien con los datos reales y con los tres roles.
**Requiere ajuste**: falla, devuelve datos incorrectos o contradice la regla de
permisos. **Obsoleto**: ninguno; los proveedores son ficticios (B13 de INV-21),
pero los endpoints siguen teniendo sentido.

| Endpoint | Estado | Evidencia | Causa |
| --- | --- | --- | --- |
| `POST /api/auth/login` | Compatible | Los 5 usuarios inician sesión. En cada login el log muestra `AttributeError: module 'bcrypt' has no attribute '__about__'`: es un aviso de `passlib` 1.7.4 con `bcrypt` 4.x, sin efecto | — |
| `POST /api/auth/refresh`, `/logout` | Compatible | No dependen de la bodega. La lista de tokens revocados vive en memoria y se pierde al reiniciar | — |
| `GET /api/auth/me` | Compatible | Resuelve la sucursal: `admin_sucursal` → PRINCIPAL (1), `admin_bodega` → BODEGA_CENTRAL (5), `gerente` → sin sucursal | — |
| `PATCH /api/auth/password` | Compatible | Solo usa `app.usuarios` (revisión de código) | — |
| `GET /api/consulta/productos` | **Requiere ajuste** | 500 con cualquier rol: `ProductoItem.codigo_item` es entero y 2.786 de los 4.449 códigos son texto (`P1632`, `P547`) | A |
| `GET /api/consulta/productos/{id}` | **Requiere ajuste** | 500 para los códigos de texto (`/productos/91`, P1632). Con los numéricos se pierden los ceros: `/productos/3814` devuelve `codigo_item` 8 en vez de `00008`. Los proveedores se buscan por categoría | A, E |
| `GET /api/consulta/sucursales` | **Requiere ajuste** | 500: `ciudad` y `departamento` son nulos en las 5 sucursales, y `factor_volumen` en BODEGA_CENTRAL y SIN_SUCURSAL (`float(None)`). Es lo que llena el selector de sucursal del frontend | A |
| `GET /api/consulta/proveedores` | Compatible | 10 proveedores | — |
| `GET /api/consulta/proveedores/{id}` | **Requiere ajuste** | 500 al armar sus productos con el mismo `ProductoItem`. Sus productos salen por categoría | A, E |
| `GET /api/consulta/categorias` | Compatible | 33 categorías | — |
| `GET /api/consulta/inventario` | **Requiere ajuste** | 11.101 filas en 4 ubicaciones con el gerente y con `admin_bodega`. Un `admin_sucursal` no puede ver la Bodega: su `sucursal_id` se ignora en silencio (`?sucursal_id=5` y `?sucursal_id=2` devuelven igual las 4.046 filas de PRINCIPAL). Las filas no dicen si la ubicación es la Bodega | B |
| `GET /api/consulta/inventario/detalle` | **Requiere ajuste** | `admin_bodega` ve PRINCIPAL en la lista, pero aquí recibe 403 (`id_sucursal=1`). El historial de 30 días trae un solo punto: hay una sola foto | B, G |
| `GET /api/consulta/inventario/resumen` | **Requiere ajuste** | No acepta `sucursal_id`, aunque el frontend lo envía: con el selector, el gerente ve siempre el total (11.101) | F |
| `GET /api/consulta/inventario/valorizado` | Compatible | 958,8 millones en 130 grupos (sucursal × categoría); PRINCIPAL 350,6 millones | — |
| `GET /api/alertas` | **Requiere ajuste** | 5.849 alertas con el gerente. 1.415 de las 3.868 "sin movimiento" son de la Bodega, que no vende. 607 "stock crítico" son de la Bodega, cuya cobertura el ETL calcula contra la demanda de toda la red. Las filas con stock negativo salen como "stock crítico" (202), o sin alerta si su cobertura es el centinela 999 (18) | C, D |
| `GET /api/alertas/resumen` | **Requiere ajuste** | Los mismos conteos (`por_tipo`: crítico 1.316, bajo 386, sin movimiento 3.868, rotación baja 279), y tampoco acepta `sucursal_id` aunque el frontend lo envía | C, D, F |
| `GET /api/reportes/kpis` | **Requiere ajuste** | Gerente: ventas del 2025-12-31 56,8 millones; del mes, 737,9 millones; 1.702 productos en riesgo. Con `bodega@` las ventas son 0: se le filtra a BODEGA_CENTRAL, que no vende | B |
| `GET /api/reportes/ventas` | **Requiere ajuste** | Gerente: 31 días de diciembre, 737,9 millones; `admin_sucursal`: 471,8 millones. Con `bodega@`, vacío | B |
| `GET /api/reportes/ventas/comparativa` | **Requiere ajuste** | Gerente: +50,1 % frente al periodo anterior. Con `bodega@`, todo en 0 | B |
| `GET /api/reportes/ventas/top-productos` | **Requiere ajuste** | Gerente: VINO SANSON, GALL CARAVANA, VINO CARIÑOSO. Con `bodega@`, vacío | B |
| `GET /api/reportes/tendencias` | **Requiere ajuste** | Por sucursal: 3 series de 31 días. Con `bodega@`, vacío. El frontend envía `dias`, que se ignora | B, F |
| `GET /api/reportes/distribucion-categorias` | **Requiere ajuste** | 32 categorías con venta en diciembre. Con `bodega@`, vacío | B |
| `GET /api/health` | Compatible | — | — |
| `GET /api/ml/recomendaciones/*` (INV-23) | Compatible | Construidos sobre la bodega real. Un `admin_sucursal` que pide BODEGA_CENTRAL recibe 403 (C1) | — |

Los tiempos son buenos: menos de 0,7 s en todos los casos (alertas, la más
lenta, entre 0,4 y 0,66 s).

**Totales:** de los 23 endpoints del Core API anteriores a INV-23, 14 requieren
ajuste y 9 son compatibles. Ninguno es obsoleto.

## Causas

| Causa | Qué pasa | Endpoints |
| --- | --- | --- |
| **A. Esquemas** | `codigo_item` entero (ahora es texto) y `ciudad`, `departamento` y `factor_volumen` obligatorios (ahora nulos) | 4 con error 500 |
| **B. Permisos inconsistentes** | `admin_bodega` ve todo en inventario y alertas, solo la Bodega en reportes y recibe 403 en el detalle. Un `admin_sucursal` que pide otra ubicación es ignorado en silencio, salvo en el detalle (403) | inventario, detalle, los 6 reportes |
| **C. La Bodega en las alertas** | No vende, así que todo su stock sale "sin movimiento" (1.415). Su cobertura se mide contra la demanda de las tres sucursales (aproximación explícita del ETL) | alertas, resumen |
| **D. Stock negativo** | 220 filas: 202 salen como "stock crítico" con cobertura negativa, y 18 (cobertura centinela 999) no generan ninguna alerta. INV-21 e INV-22 las tratan como posible inconsistencia | alertas, resumen |
| **E. Proveedores por categoría** | La API cruza producto y proveedor por categoría: solo 2.540 de 4.449 productos tienen alguno, y la categoría "Abarrotes" de un proveedor no existe en el catálogo. La bodega real tiene `dw.producto_proveedor`, con un proveedor por producto | productos/{id}, proveedores/{id} |
| **F. Filtros que la API ignora** | El frontend envía `sucursal_id` a los dos resúmenes y `dias` a tendencias; la API no los recibe | 3 |
| **G. Foto única** | `fact_inventario` tiene una sola fecha, así que el historial de 30 días trae un punto. Es un límite del dato, no del código | detalle |

## Pruebas de Release 1 contra la bodega real

| Script | Resultado | Por qué fallan |
| --- | --- | --- |
| `test_consulta.sh` | 17 pasan, 17 fallan | Los 500 de la causa A |
| `test_inventario.sh` | 38 pasan, 2 fallan | Esperan que `admin_bodega` vea una sola sucursal, y buscan productos llamados "Item" (nombres del dataset simulado) |
| `test_alertas.sh` | 33 pasan, 1 falla | La misma expectativa sobre `admin_bodega` |
| `test_reportes.sh` | 50 pasan | No revisan los reportes de `admin_bodega` |

Los scripts de Release 1 esperaban que `admin_bodega` viera solo su sucursal,
pero el código de inventario y alertas le da la visión global (los comentarios
`← agregar admin_bodega` lo muestran). La regla nunca estuvo homologada.

## Frontend

No es objeto de esta historia (D9), pero se revisó qué consume:

| Hallazgo | Efecto hoy |
| --- | --- |
| Llama a `/auth/*`, `/consulta/sucursales`, `/consulta/inventario` (lista y resumen), `/alertas` (lista y resumen) y 4 reportes (`kpis`, `tendencias`, `top-productos`, `distribucion-categorias`) | No usa productos, proveedores, categorías, el detalle ni el valorizado de inventario, ni los reportes `ventas` y `comparativa` |
| `useSucursal` lee `user.sucursal_id`, pero `/auth/me` devuelve `id_sucursal` | Un `admin_sucursal` no envía su sucursal; el backend la aplica igual por permisos |
| El selector lista lo que devuelve `/consulta/sucursales` | Hoy queda solo con "Todas" (el endpoint da 500). Al arreglarlo mostraría SIN_SUCURSAL y la Bodega |
| `admin_bodega` no tiene Dashboard en el menú | Los reportes vacíos de la causa B no se ven en pantalla |
| Los dos resúmenes y tendencias envían parámetros que la API ignora (causa F) | El selector no filtra esos widgets |

## Fuera de la API, para tener en cuenta

- `ml_service` publica el puerto 8001 sin autenticación, y su Swagger está aparte del Core API.
- El secreto JWT es el de desarrollo y CORS acepta cualquier origen. Es aceptable en local, no para un despliegue.

## Datos de referencia

| Dato | Valor |
| --- | --- |
| Ubicaciones | PRINCIPAL (1), LA 21 (2), GLORIETA (3), SIN_SUCURSAL (4, sin terminal), BODEGA_CENTRAL (5) |
| Inventario (foto 2025-12-31) | 11.101 filas: PRINCIPAL 4.046, GLORIETA 3.194, BODEGA_CENTRAL 1.973, LA 21 1.888. SIN_SUCURSAL no tiene inventario |
| Stock negativo | 220 filas: PRINCIPAL 95, GLORIETA 70, LA 21 40, BODEGA_CENTRAL 15 |
| Ventas | 2.056.210 filas de 2022-01-02 a 2025-12-31. SIN_SUCURSAL tiene 3.513 (hasta 2025-09-06); la Bodega, ninguna |
| Productos | 4.449; 1.663 con código numérico y 2.786 con código de texto. `clase` es nula en todos |
| Proveedores | 10, ficticios (INV-60). `producto_proveedor`: 4.449 filas, un proveedor por producto |
