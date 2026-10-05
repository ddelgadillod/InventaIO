# INV-26 · Fix previo · Requerimientos: ventas por producto, base del frontend y adaptación de la app a la bodega real

Versión del 2026-10-04, con las decisiones G1–G9, H1–H5 y J1–J5 tomadas sobre
el borrador y revisada contra el código y la bodega real (foto al 2025-12-31).
Es el primer entregable de INV-26: se integra a `develop` **antes** de las
vistas de predicciones (INV-26) y de recomendaciones (INV-27).

El objetivo es que la app quede funcional sobre los endpoints actuales del
Core API y que quede trazada la ruta para lo que falta: cada endpoint tiene una
pantalla que lo consume o un destino reportado, y las vistas siguientes solo
agregan su página, su entrada en la lista de rutas y sus pruebas, sin tocar la
base y sin dejar deuda técnica (G8).

## Resumen

El frontend de Release 1 (Dashboard, Inventario, Alertas) se construyó contra
la bodega simulada: tiene supuestos que la bodega real ya no cumple, consume 12
de los 28 endpoints del Core API y no tiene nada de lo construido en Sprint 4
y 5. El Core API, además, no tiene lo que la vista de predicciones necesita.
Este fix cubre cuatro cosas:

1. Un endpoint de ventas por producto en el Core API, que hoy no existe (A1).
2. La base compartida del frontend (A2): errores con código HTTP, funciones de
   la API, selector de sucursales por tipo, `useSucursal` corregido, Vitest y
   lo que las vistas reutilizan: rutas por rol, un hook para las consultas a la
   API desde las páginas, estados en pantalla, formato, etiquetas y utilidades
   de prueba.
3. La adaptación de la app a la bodega real y a esa base (A3), con el detalle
   de inventario y el cambio de contraseña, que usan endpoints que ya existen.
4. La ruta sin deuda técnica (A4): matriz endpoint → pantalla → historia,
   reglas, guía para agregar una vista y la historia nueva de reportes.

Los datos siguen saliendo de la bodega a través del Core API. A2 y A3 cambian
cómo el navegador los pide y los muestra.

| Campo | Valor |
| --- | --- |
| Tipo | Fix previo dentro de INV-26, no una historia nueva en Jira |
| Puntos | Sin cambios: se cubre con los 8 SP de INV-26 (F3; INV-27 sigue en 8; INV-24 sigue en Sprint 5) |
| Épica | E9 ML Dashboard |
| Sprint | Sprint 5 (21 sep – 10 oct) |
| Rama | `feature/INV-26-fix-base`, integrada a `develop` antes de las vistas |
| Depende de | INV-25 (homologación del Core API y `POST /api/ml/predict`) e INV-23 |
| Desbloquea a | La vista de predicciones (INV-26), la de recomendaciones (INV-27) y la historia nueva de reportes (J1) |

**Dentro del alcance**

- `GET /api/consulta/productos/{id_producto}/ventas` y sus pruebas (A1).
- La base compartida del frontend (A2), con Vitest y Testing Library.
- Dashboard, Inventario y Alertas adaptados a la bodega real y a la base; detalle de inventario; cambio de contraseña (A3).
- La matriz de trazabilidad, las reglas sin deuda y la guía del frontend (A4).
- El cierre de pendientes y deuda técnica de la adenda (K1–K10): higiene del repo, Node 22 y CI, versiones mayores del frontend, ajustes de inventario, alertas y el KPI en riesgo, la vista de reportes de ventas y el seed de usuarios (A5 a A11).

**Fuera del alcance**

- Las páginas `Predicciones` (INV-26) y `Recomendaciones` (INV-27), y sus entradas en `RUTAS`.
- Una página de proveedores, mientras los proveedores sean simulados (J3).
- Una vista de la lista completa de la Bodega para el `admin_sucursal` (G6).
- La página de Login, que no cambia.
- Lint del frontend y pipeline (INV-24), y pruebas end-to-end.
- Cambios a los contratos de `ml_service` y de los endpoints de INV-23 e INV-25.
- Una serie diaria de ventas por producto: el endpoint solo entrega ventanas de 15 días hábiles.

## Qué cambió frente al borrador

| Tema | Borrador | Ahora | Por qué |
| --- | --- | --- | --- |
| Ejemplo de respuesta | Una ventana del 1 al 31 de diciembre | Ventanas de unos 15 días de calendario, con valores reales | En diciembre de 2025 los 31 días tuvieron ventas: 15 días hábiles son 15 días |
| Fuente | "Ventas netas de devoluciones" | Ventas **sin** devoluciones | La vista excluye las devoluciones (1.351 filas, 5.420 unidades), no las resta |
| Historia corta (regla 4) | Se devuelven las ventanas que haya | Siempre las pedidas, con ceros (G1) | Hay 1.362 días hábiles, 90 ventanas; el máximo es 24 |
| `fecha_fin` | Sin definir | El último día hábil de la red | Queda alineada con `fecha_features` de `predict` |
| La Bodega en A1 | 422 para todos | 403 para el `admin_sucursal` (R1 de INV-25) y 422 para los demás | La regla de permisos de INV-25 se revisa primero |
| `dias_habiles` por ventana | En cada ventana | Se quita | Con G1 todas tienen 15 |
| Identificadores (F5) | Por nombre en predicción y recomendaciones | Por id en predicción y ventas (G2) | `predict` acepta `id_producto` e `id_sucursal`, y el permiso del `admin_sucursal` compara el id |
| Nombre de la sucursal propia | Se traduce con la lista | Sale de `/auth/me` (`sucursal_nombre`) | Ya viene en el perfil |
| Timeout | 120 s | 130 s (G4) | Con 120 s el frontend corta justo cuando el Core API responde 504 con su mensaje |
| Petición cancelada | Sin regla | Se ignora, no se muestra como error | Las páginas muestran todo error que reciben |
| Pendiente 1 (`predict` por id) | Abierto | Resuelto: sí admite el id | Verificado contra la API: P1632 en PRINCIPAL por ids da q50 3.366,01; un id ajeno da 403 |
| Suficiencia del fix | Sin criterio | App funcional sobre los endpoints actuales y ruta trazada sin deuda (G8) | Que el arreglo de las vistas sea suave |
| Base para las vistas | No estaba | A2.9 a A2.12 (G9) | Rutas sin guarda por rol, consultas a la API repetidas en cada página, estados y pruebas que cada vista tendría que armar |
| Páginas de Release 1 (F2) | Dos ajustes: etiqueta de alertas y columna `stock_bodega` | Adaptación completa a la bodega real y a la base (A3) | Categorías de la bodega simulada, cobertura centinela, 4.452 alertas en una página, Dashboard con la Bodega y errores que se pierden |
| Dashboard | Fuera del alcance | Dentro: vista de Bodega (H1) y `admin_bodega` con Dashboard (H2) | Con la Bodega elegida muestra ventas en $0 y gráficas vacías |
| Endpoints sin pantalla | Sin revisar | Matriz de los 28 endpoints; 9 sin consumidor, cada uno con destino (J1–J4, A4) | Que ninguna funcionalidad quede sin reportar ni código sin uso |
| Cobertura (F6) | "En lo que cambia" | Por archivo, sobre la base y las páginas (H5) | La cobertura se mide por archivo, y las páginas se reescriben |
| Unidad del producto | `unidad_medida` en el histórico | `unidad` ("unidad" o "kg", de `se_vende_por_kilo`) en el histórico y en todos los productos (J5) | `unidad_medida` es la de la presentación: el arroz \*500 GR tiene `g` y la papa, que se vende por kilo, `unidad` |

## Decisiones acordadas

| Código | Tema | Decisión |
| --- | --- | --- |
| F1 | Histórico | Endpoint nuevo en el Core API, como fix de INV-26 |
| F3 | Puntos | Sin cambios; el fix se cubre con los 8 SP de INV-26 |
| F4 | Orden | Se integra a `develop` antes de empezar las vistas |
| F7 | Rutas y menú | Las vistas no se agregan aquí: cada una agrega su entrada en `RUTAS` |
| G1 | Ventanas | Calendario de días hábiles de la red, como el modelo: los días sin venta cuentan 0, también antes de la primera venta. Siempre se devuelven las ventanas pedidas |
| G2 | Identificadores | Pronóstico e histórico por `id_producto` e `id_sucursal`, como Release 1. Solo las recomendaciones (INV-27) van por nombre de sucursal. Reemplaza F5 |
| G3 | Histórico sin `sucursal_id` | 422 para `gerente` y `admin_bodega`; el `admin_sucursal` usa la suya |
| G4 | Tiempos | `timeoutMs` de 130 s en el frontend y `timeout`/`proxyTimeout` de 130 s en el proxy de Vite. Una petición cancelada a propósito se ignora |
| G6 | La Bodega en Inventario para el `admin_sucursal` | Solo la columna `stock_bodega` y el distintivo de la Bodega, sin selector |
| G8 | Prioridad y suficiencia | El fix va antes de las vistas y entra completo (A1 a A4). La app queda funcional sobre los endpoints actuales, y cada vista solo agrega su página, su entrada en `RUTAS` y sus pruebas |
| G9 | Base para las vistas | Rutas por configuración con guarda por rol (A2.9), `useConsulta` (A2.10), estados, formato y etiquetas (A2.11) y utilidades de prueba (A2.12) |
| H1 | Dashboard con la Bodega | Vista de Bodega: sin tarjetas ni gráficas de ventas, con una nota de que la Bodega no vende; muestra stock valorizado, productos en riesgo, semáforo y alertas. Reemplaza G7 |
| H2 | `admin_bodega` y el Dashboard | Lo ve como el gerente, con el selector, y entra por defecto a él |
| H3 | Stock negativo y cobertura centinela en Inventario | Estados propios: stock < 0 se muestra como "Inconsistencia" con cobertura "—"; cobertura 999 como "Sin ventas". El filtro y los conteos del semáforo siguen como la API. El centinela es exactamente 999 (demanda observada 0); las 76 filas con cobertura mayor que 999 son reales y se muestran con su valor |
| H4 | Muchas alertas | Paginación en el navegador, 50 por página, sin cambiar la API; distintivo "Bodega" en las alertas de la Bodega |
| H5 | Cobertura | ≥ 80 % sobre la base (`src/api/`, `src/hooks/`, `src/utils/`, `src/components/`, `src/rutas.js`) y sobre Dashboard, Inventario y Alertas. Login queda fuera porque no cambia. Reemplaza G5 y F6 |
| J1 | Reportes de ventas | Historia nueva "Vista de reportes de ventas" (A4.4). Este fix quita `getDistribucionCategorias` de `client.js`, que no tiene uso; la historia la vuelve a agregar con su página y sus pruebas |
| J2 | Detalle de inventario | En este fix: panel de detalle al elegir una fila de Inventario (A3.6) |
| J3 | Proveedores | Solo en el detalle de inventario. Sin página de proveedores mientras sean simulados; queda en la matriz como decisión |
| J4 | Cambio de contraseña | En este fix: opción en el menú del usuario (A3.7) |
| J5 | Unidad de venta | Campo `unidad` ("unidad" o "kg", como en `ml_service`) en el histórico (reemplaza `unidad_medida`) y, de forma aditiva, en todas las respuestas de producto. El detalle de inventario la muestra en la descripción del producto |

## Punto de partida

Verificado contra el código y la API con la bodega real.

| Pieza | Estado actual | Qué falla o falta |
| --- | --- | --- |
| Historia de ventas por producto | No existe en el Core API. `/reportes/*` agrega por sucursal o categoría | La vista de predicciones no tiene con qué dibujar el histórico |
| Endpoints sin pantalla | El frontend consume 12 de los 28 endpoints | 9 no tienen consumidor ni destino: los 4 de reportes de ventas y valorizado, el detalle de inventario y de producto, los 2 de proveedores y el cambio de contraseña. `getDistribucionCategorias` está en `client.js` sin uso |
| `client.js` | `apiFetch` lanza `new Error(err.detail)` | Pierde el código HTTP: no distingue 400, 403, 409, 422 ni 504. El `detail` de un 422 de validación es una lista y se muestra "[object Object]" |
| `client.js` | Solo funciones de auth, sucursales, reportes, inventario y alertas | No hay funciones de productos, categorías, detalle, contraseña, pronóstico ni recomendaciones |
| Peticiones lentas | `fetch` sin timeout | La primera consulta de recomendaciones tarda 22–36 s en frío |
| `useSucursal` | Lee `user.sucursal_id` | `/auth/me` devuelve `id_sucursal` y `sucursal_nombre`: un `admin_sucursal` no envía su sucursal y depende de que el backend se la aplique |
| `SucursalSelector` | Lista lo que devuelve `/consulta/sucursales` (4, con la Bodega como "BODEGA_CENTRAL") y silencia los errores | No avisa si la carga falla y cada página la vuelve a pedir |
| Rutas y menú | `App.jsx` filtra el menú por rol, pero no las rutas | Cualquier rol entra a cualquier página por URL; cada vista tendría que tocar el menú y las rutas por separado |
| Consultas a la API desde las páginas | Cada página repite `useEffect`, `setLoading` y `.catch(console.error)` | No hay cancelación ni protección contra respuestas fuera de orden. Un error en una de las 5 consultas del Dashboard tumba la página; Inventario y Alertas descartan los errores y quedan vacías sin avisar |
| Estados y formato | El spinner y el error se escriben en cada página; `fmt` vive dentro del Dashboard | Las vistas necesitan errores por código (403, 404, 409, 504), aviso de espera larga y números con formato |
| Dashboard | Selector con la Bodega; "Ventas hoy"; claves crudas en el widget de alertas; sin entrada para `admin_bodega` | Con la Bodega elegida, ventas en $0 y tendencia y top que desaparecen (solo stock valorizado, 356 M, y en riesgo, 686, tienen datos). "Hoy" es en realidad el 2025-12-31. El widget muestra "stock critico". `admin_bodega` no lo ve, aunque INV-25 ya le dio reportes con datos |
| Inventario | Lista fija de 15 categorías de la bodega simulada; cobertura con `toFixed(1)`; sin detalle | 2 categorías ya no existen y faltan 20 de las 33 reales (Licores, Arroz, Aceites…). Las 317 filas con el centinela 999 (demanda observada 0) se ven como "999.0d" y las 220 con stock negativo como cobertura negativa (por ejemplo, −347,4 d) y "Crítico". No muestra `stock_bodega` ni `tipo_ubicacion`, y no hay forma de ver el detalle de un producto |
| Alertas | `TIPO_LABEL` y el filtro no conocen `inconsistencia_inventario`; pinta todas las alertas | Se ve el nombre crudo y no se puede filtrar. El gerente recibe 4.452 alertas (1,4 MB) en una sola lista, sin distinguir las de la Bodega |
| Cuenta | Sin pantalla de cambio de contraseña | Los usuarios no pueden cambiar `admin123` desde la app |
| Pruebas del frontend | `package.json` sin Vitest, Jest ni Testing Library (Vite 5.4) | Los DoD de INV-26 e INV-27 piden cobertura ≥ 80 % y hoy no se puede medir |

## A1 · Endpoint de ventas por producto

`GET /api/consulta/productos/{id_producto}/ventas`, en `api/consulta/router.py`,
con su esquema en `api/schemas/consulta.py`. Devuelve las ventas de un producto
en una sucursal física, en **ventanas de 15 días hábiles**, para compararlas
contra el pronóstico acumulado a 15 días de `POST /api/ml/predict`.

**Parámetros**

| Parámetro | Tipo | Regla |
| --- | --- | --- |
| `id_producto` | ruta, entero | 404 si no existe |
| `sucursal_id` | query, entero | Obligatorio para `gerente` y `admin_bodega` (G3); el `admin_sucursal` usa la suya si no lo envía. Se resuelve con `resolver_sucursal(..., VENTAS)` de `core/ubicaciones.py` |
| `ventanas` | query, entero 1–24 | Por defecto 8 |

**Reglas**

1. La fuente es `dw.v_ventas_diarias_netas` (`codigo_item`, `sucursal`, `fecha`, `unidades`): las ventas diarias sin devoluciones y con cantidad positiva, la misma vista que lee el modelo.
2. Día hábil es una fecha con alguna venta en la red, como `SQL_HABILES` de `ml_service`: 1.362 días entre el 2022-01-02 y el 2025-12-31. La consulta tarda unos 35 ms; no necesita caché.
3. `fecha_fin` es el último día hábil de la red (2025-12-31), el mismo `fecha_features` que devuelve `predict` sin `fecha_corte`. La última ventana termina ahí y las demás retroceden de 15 en 15 días hábiles, sin solaparse.
4. Cada ventana suma las `unidades` de sus 15 días hábiles. Los días sin venta cuentan 0, también antes de la primera venta del producto (G1). Siempre se devuelven las ventanas pedidas, en orden cronológico: la historia alcanza para 90.
5. Solo sucursales físicas: la Bodega Central no vende.

**Respuesta** (valores reales, con `ventanas=3`)

```json
{
  "id_producto": 91, "codigo_item": "P1632", "nombre_producto": "HUEVOS *UND",
  "categoria": "Huevos", "unidad": "unidad",
  "id_sucursal": 1, "sucursal": "PRINCIPAL",
  "horizonte_dias_habiles": 15, "fecha_fin": "2025-12-31",
  "ventanas": [
    {"desde": "2025-11-17", "hasta": "2025-12-01", "unidades": 2426.0},
    {"desde": "2025-12-02", "hasta": "2025-12-16", "unidades": 3522.0},
    {"desde": "2025-12-17", "hasta": "2025-12-31", "unidades": 4608.0}
  ]
}
```

Con las 8 ventanas por defecto, la primera empieza el 2025-09-02.

**Errores**

Se valida primero la sucursal (422 y 403, en el orden de INV-25) y después el
producto (404).

| Código | Cuándo |
| --- | --- |
| 401 | Token inválido o vencido |
| 403 | Sin token; `admin_sucursal` pidiendo otra sucursal o la Bodega ("…; la Bodega Central, solo en el stock") |
| 404 | `id_producto` inexistente |
| 422 | `gerente` o `admin_bodega` sin `sucursal_id`, con la lista de las sucursales físicas; sucursal inexistente o SIN_SUCURSAL, para todos (R2 de INV-25); la Bodega Central para `gerente` o `admin_bodega` ("no vende"); `ventanas` fuera de 1–24 |

## A2 · Base compartida del frontend

| # | Cambio | Archivo |
| --- | --- | --- |
| A2.1 | `ApiError` con `status` y `detail`. El `detail` de un 422 de validación (lista) se convierte en texto legible. `message` sigue siendo el `detail`, así que `err.message` no cambia de significado. Una petición cancelada a propósito lanza un error marcado como cancelado, que las páginas y hooks ignoran; un timeout lanza `ApiError` marcado como timeout | `src/api/client.js` |
| A2.2 | Funciones nuevas, cada una con su consumidor en la matriz (A4.1): `getCategorias`, `getInventarioDetalle`, `getProducto` y `cambiarPassword` (las usa A3); `getProductos`, `getVentasProducto` y `predecir` (INV-26, con `id_producto` e `id_sucursal`, G2); `getRecomendacionesCompras` y `getRecomendacionesTransferencias` (INV-27, con `sucursal` por nombre). Se quita `getDistribucionCategorias` (J1) | `src/api/client.js` |
| A2.3 | `timeoutMs` opcional con `AbortController` (130 s en pronóstico y recomendaciones, G4) y `clave` opcional: una petición nueva con la misma clave cancela la anterior | `src/api/client.js` |
| A2.4 | Proxy de desarrollo con `timeout` y `proxyTimeout` de 130 s (G4) | `vite.config.js` |
| A2.5 | `useSucursales()`: carga una sola vez `/consulta/sucursales` aunque lo usen varios componentes, y ofrece `porId`, `porNombre` y `fisicas` | `src/hooks/useSucursales.js` (nuevo) |
| A2.6 | `useSucursal`: lee `user.id_sucursal` y devuelve también `sucursalNombre` (el `sucursal_nombre` de `/auth/me` para el `admin_sucursal`; el de la lista para lo que elijan `gerente` y `admin_bodega`) y el tipo de la ubicación elegida | `src/hooks/useSucursal.js` |
| A2.7 | `SucursalSelector`: usa `useSucursales`, recibe la prop `incluirBodega` (por defecto `true`), muestra la Bodega como "Bodega Central" y avisa si la carga falla | `src/components/SucursalSelector.jsx` |
| A2.8 | Vitest (versión compatible con Vite 5.4), Testing Library y jsdom, con los scripts `test` y `test:cov` y la cobertura de H5 | `package.json`, `vite.config.js` |
| A2.9 | Rutas por configuración: una sola lista `RUTAS` (path, etiqueta, icono, roles, página) alimenta el menú y las rutas. Una guarda por rol devuelve a su página de inicio a quien no tiene el rol. Las vistas agregan una entrada cada una | `src/rutas.js` (nuevo), `src/components/GuardaRol.jsx` (nuevo), `App.jsx` |
| A2.10 | `useConsulta(fn, deps, {timeoutMs, activo})`: llama a una función de `client.js` (`fn` recibe `{signal, timeoutMs}` y lo pasa) y devuelve `datos`, `cargando`, `error` y `recargar`. Cuando cambian los filtros cancela la consulta anterior, ignora la cancelada y nunca deja en pantalla una respuesta vieja. `activo: false` no consulta | `src/hooks/useConsulta.js` (nuevo) |
| A2.11 | Estados, formato y etiquetas: `Cargando` (spinner, con un aviso de espera larga después de unos segundos), `MensajeError` (el `detail` del Core API en los 4xx, que ya viene en español, y textos fijos para 502, 503, 504, timeout y error de red), `EstadoConsulta` (cargando, error con "Reintentar" o los datos de una consulta), `DistintivoBodega`, `formato.js` (números con separador de miles, moneda corta como la del Dashboard y fechas) y `etiquetas.js` (tipos y urgencias de alerta, estados de inventario y nombres de ubicación) | `src/components/Cargando.jsx`, `src/components/MensajeError.jsx`, `src/utils/formato.js`, `src/utils/etiquetas.js` (nuevos) |
| A2.12 | Utilidades de prueba: setup de jest-dom, `renderConUsuario(ui, usuario)` con el contexto de sesión y un router en memoria, usuarios de ejemplo de los tres roles con la forma de `/auth/me`, y `simularApi` (respuestas por método y ruta, con código y demora). `AuthContext` se exporta para poder inyectar el usuario | `src/test/setup.js`, `src/test/utils.jsx` (nuevos), `src/api/AuthContext.jsx` |

## A3 · Adaptación de la app a la bodega real

| # | Cambio | Archivo |
| --- | --- | --- |
| A3.1 | Las tres páginas usan `useConsulta`, `Cargando`, `MensajeError`, `formato.js` y `etiquetas.js`. Los errores se muestran en vez de perderse, y una búsqueda o un filtro nuevo nunca queda pisado por una respuesta vieja | `src/pages/Dashboard.jsx`, `Inventario.jsx`, `Alertas.jsx` |
| A3.2 | **Dashboard.** Cada bloque (KPIs, tendencia, semáforo, top, alertas) carga y falla por separado: un error no tumba la página. "Ventas del día" y "Ventas del mes" con la fecha de la foto ("31 dic 2025") en vez de "hoy". El widget de alertas usa las etiquetas, incluida "Inconsistencia de inventario". Con la Bodega elegida, vista de Bodega (H1): no se piden ni se muestran las ventas, y se ven stock valorizado, productos en riesgo, semáforo, alertas y la nota "La Bodega Central no vende" | `src/pages/Dashboard.jsx` |
| A3.3 | **`admin_bodega` con Dashboard** (H2): la entrada de `RUTAS` del Dashboard admite los tres roles y todos entran a él por defecto | `src/rutas.js` |
| A3.4 | **Inventario.** Las categorías salen de `/consulta/categorias` (33) en vez de la lista fija. Estados propios (H3): stock < 0 se muestra como "Inconsistencia" con cobertura "—", y la cobertura 999 como "Sin ventas". Columna "Stock Bodega" (`stock_bodega`, "—" si es nulo) y distintivo en las filas de la Bodega (G6). Stock con separador de miles | `src/pages/Inventario.jsx` |
| A3.5 | **Alertas.** `inconsistencia_inventario` con su etiqueta y en el filtro de tipos (el estilo crítico ya lo da su urgencia). Distintivo "Bodega" en las alertas de la Bodega. Paginación en el navegador, 50 por página (H4); los conteos siguen saliendo del resumen | `src/pages/Alertas.jsx` |
| A3.6 | **Detalle de inventario** (J2, J3). Al elegir una fila de Inventario se abre un panel con `inventario/detalle` y `productos/{id}`: stock, mínimo, máximo, punto de reorden, cobertura (con los estados de H3), stock de la Bodega, categoría y proveedor. La descripción del producto dice su código y cómo se vende (J5); los productos por kilo llevan un decimal. Con una sola foto, el historial se muestra como un valor con su fecha, no como gráfica. Sigue la regla de permisos de INV-25: el `admin_sucursal` ve su sucursal y la Bodega | `src/components/DetalleInventario.jsx` (nuevo), `src/pages/Inventario.jsx` |
| A3.7 | **Cambio de contraseña** (J4). Opción "Cambiar contraseña" en el menú del usuario, con contraseña actual, nueva y su confirmación. Valida en el navegador que la nueva tenga al menos 8 caracteres y coincida con la confirmación, y muestra los mensajes del Core API (400 si la actual es incorrecta o la nueva es igual; 422 de validación) y el de éxito | `src/components/CambiarPassword.jsx` (nuevo), `App.jsx` |

## A4 · Ruta sin deuda técnica

### A4.1 Matriz endpoint → pantalla → historia

Los 28 endpoints del Core API (27 de hoy y el de A1). Queda en
`frontend/README.md` como documento vivo: cada historia que consuma o agregue
un endpoint la actualiza.

| Endpoint | Función de `client.js` | Pantalla | Dónde |
| --- | --- | --- | --- |
| `POST /api/auth/login` | `login` | Login | Release 1, sin cambios |
| `POST /api/auth/refresh` | interna de `apiFetch` | Todas | Release 1, sin cambios |
| `POST /api/auth/logout` | `logout` | Menú del usuario | Release 1, sin cambios |
| `GET /api/auth/me` | `getProfile` | Sesión | Este fix (A2.6) |
| `PATCH /api/auth/password` | `cambiarPassword` | Menú del usuario | Este fix (A3.7, J4) |
| `GET /api/consulta/productos` | `getProductos` | Predicciones | INV-26 |
| `GET /api/consulta/productos/{id}` | `getProducto` | Detalle de inventario | Este fix (A3.6, J2) |
| `GET /api/consulta/productos/{id}/ventas` | `getVentasProducto` | Predicciones | Endpoint en este fix (A1); pantalla en INV-26 |
| `GET /api/consulta/sucursales` | `getSucursales` (vía `useSucursales`) | Selector de todas las páginas | Este fix (A2.5) |
| `GET /api/consulta/proveedores` | — | — | No se consume: proveedores simulados (J3) |
| `GET /api/consulta/proveedores/{id}` | — | — | No se consume: proveedores simulados (J3) |
| `GET /api/consulta/categorias` | `getCategorias` | Inventario; Recomendaciones | Este fix (A3.4); INV-27 |
| `GET /api/consulta/inventario` | `getInventario` | Inventario | Este fix (A3.4) |
| `GET /api/consulta/inventario/detalle` | `getInventarioDetalle` | Detalle de inventario | Este fix (A3.6, J2) |
| `GET /api/consulta/inventario/resumen` | `getInventarioResumen` | Dashboard | Este fix (A3.2) |
| `GET /api/consulta/inventario/valorizado` | — | — | Historia de reportes (J1) |
| `GET /api/alertas` | `getAlertas` | Alertas | Este fix (A3.5) |
| `GET /api/alertas/resumen` | `getAlertasResumen` | Dashboard, Alertas | Este fix (A3.2, A3.5) |
| `GET /api/reportes/kpis` | `getKPIs` | Dashboard | Este fix (A3.2) |
| `GET /api/reportes/ventas` | — | — | Historia de reportes (J1) |
| `GET /api/reportes/ventas/comparativa` | — | — | Historia de reportes (J1) |
| `GET /api/reportes/ventas/top-productos` | `getTopProductos` | Dashboard | Este fix (A3.2) |
| `GET /api/reportes/tendencias` | `getVentasTendencia` | Dashboard | Este fix (A3.2); `por_sucursal` en la historia de reportes (J1) |
| `GET /api/reportes/distribucion-categorias` | se quita `getDistribucionCategorias` | — | Historia de reportes (J1) |
| `GET /api/ml/recomendaciones/compras` | `getRecomendacionesCompras` | Recomendaciones | INV-27 |
| `GET /api/ml/recomendaciones/transferencias` | `getRecomendacionesTransferencias` | Recomendaciones | INV-27 |
| `POST /api/ml/predict` | `predecir` | Predicciones | INV-26 |
| `GET /api/health` | — | — | Infraestructura, sin pantalla |

Al cerrar el fix: 16 endpoints con pantalla (12 de Release 1 y 4 nuevos), 5
que consumen INV-26 e INV-27, 4 en la historia de reportes, 2 de proveedores
sin consumir por decisión (J3) y el health. Ninguno queda sin destino.

### A4.2 Reglas sin deuda técnica

1. Toda función de `client.js` tiene una pantalla que la usa y pruebas. La única excepción son las de INV-26 e INV-27 (A2.2), que entran con pruebas y las consume la vista siguiente.
2. Ningún dato que viene de la bodega se escribe fijo en el código: categorías, sucursales y tipos se piden al Core API.
3. Una sola implementación de cada cosa: consultas (`useConsulta`), errores (`ApiError` y `MensajeError`), formato (`formato.js`), etiquetas (`etiquetas.js`), sucursales (`useSucursales`) y rutas (`RUTAS`). El `fmt` del Dashboard se reemplaza por `formato.js`.
4. Todo endpoint aparece en la matriz con su consumidor o su destino. Una funcionalidad nueva o requerida se reporta en la matriz y en su historia antes de implementarse.
5. Lo nuevo o tocado queda con pruebas, con la cobertura de H5.

### A4.3 Guía del frontend

`frontend/README.md` (nuevo) con:
- la estructura de carpetas y las convenciones de A4.2;
- cómo agregar una vista: función en `client.js` con su prueba, entrada en `RUTAS` con sus roles, página con `useConsulta`, `Cargando` y `MensajeError`, pruebas con `renderConUsuario` y `simularApi`, y actualizar la matriz;
- cómo correr la app y las pruebas;
- la matriz de A4.1.

### A4.4 Vista de reportes de ventas (J1)

Se pensó como historia nueva; con la adenda (K5–K7) se implementa en este fix,
en el bloque A9.

## Adenda · Cierre de pendientes y deuda técnica (K1–K10)

El 2026-10-05 se decidió resolver dentro de este fix los pendientes que iban a
reportarse y la deuda que había quedado como limitación, para no dejar tareas
sueltas. Esta adenda traza la ruta.

### Decisiones

| Código | Tema | Decisión |
| --- | --- | --- |
| K1 | `INV-26-27-requerimientos.md` | Se quita la referencia: estos requerimientos son autosuficientes y las vistas tendrán su propio documento |
| K2 | Alertas | Paginación en la API: `page` y `page_size` opcionales en `GET /api/alertas`; sin ellos responde como hoy (compatible con INV-25). Reemplaza H4 |
| K3 | Semáforo de inventario | La API agrega el estado `inconsistencia` (stock < 0) en la lista, el filtro, el detalle y los conteos del resumen. Reemplaza la parte de presentación de H3 |
| K4 | CI del frontend | Node 22, `npm run test:cov` y `npm audit --omit=dev --audit-level=high` en el job del frontend. El lint sigue en INV-24 |
| K5 | Roles de la vista de reportes | Los tres, con la regla de INV-25. Con la Bodega elegida solo se ve el valorizado |
| K6 | Bloques de la vista | Los cuatro: ventas y comparativa, distribución por categorías, valorizado del inventario y tendencia por sucursal |
| K7 | Período | Por defecto el mes de la última venta; atajos de mes, trimestre, año y toda la historia, y rango libre; agrupación, categoría y ubicación |
| K8 | Seed de usuarios de prueba | Versionado en `api/scripts/seed_usuarios.py`, idempotente; lo corre el usuario |
| K9 | KPI "En riesgo" | Cuenta los tramos bajo y crítico del semáforo, con la misma regla de K3 (`core/semaforo.py`): 1.500 en vez de 1.702. Las 202 filas con stock negativo y cobertura menor a 7 días dejan de contar: tienen su tramo y su alerta. Reemplaza el pendiente 2 de INV-25 ("como hoy") |
| K10 | Paleta de Tailwind 4 | Se deja la de v4: `red-500`, `red-600` y `green-500` algo más vivos; los colores de la marca no cambian |

K9 y K10 se decidieron al cerrar A11. Con K1–K10 dejan de existir los pendientes por reportar: el punto 1 se hace en
A9, los puntos 2 y 3 en A6 y A7, el 4 lo resuelve K1 y el 5 se hace en A8.

### Ruta

| Fase | Bloque | Contenido | Por qué en ese orden |
| --- | --- | --- | --- |
| 1 | A5 · Higiene | `.gitattributes` con `*.sh text eol=lf` (los `.sh` dejan de quedar en CRLF tras cada merge); las pruebas de `ml_service` leen `MODELOS_DIR` si está definida; se borra la carpeta vacía `frontend/src/{pages,components,api,assets}` | Cambios chicos que evitan tropiezos en las fases siguientes |
| 2 | A6 · Plataforma | Node 22 en el CI, con `test:cov` y `npm audit` (K4); `engines` `>=22.12` y `.nvmrc` 22 | Las versiones mayores de A7 lo exigen (Vitest 5: Node ≥ 22.12) |
| 3 | A7 · Versiones mayores | Una por una, con pruebas, build y `npm audit` después de cada una: React Router 6 → 7 (imports a `react-router`; desaparecen los avisos de v7); Vite 5 → 8 con `@vitejs/plugin-react` 6 y Vitest 3 → 5 con su cobertura; Tailwind 3 → 4 (configuración a CSS con `@theme`, plugin `@tailwindcss/vite`, sin `autoprefixer` ni `postcss.config.js`; herramienta oficial de migración y revisión visual con la guía de pantallas) | La vista nueva se construye sobre el stack final; Tailwind al final porque es el de más riesgo visual |
| 4 | A8 · Ajustes de funcionalidad | `unidad` en la lista de inventario (la tabla muestra el decimal de los productos por kilo); paginación de alertas en la API (K2); estado `inconsistencia` en el semáforo (K3) | Cierran las limitaciones de las pantallas que ya existen |
| 5 | A9 · Vista de reportes | La página nueva (K5–K7) | Usa la base, el stack y los ajustes anteriores |
| 6 | A10 · Seed | `api/scripts/seed_usuarios.py` (K8) | Independiente; cierra el pendiente 3 de INV-25 |
| 7 | A11 · Cierre | Matriz sin endpoints sin destino; guía de pantallas, colecciones de Postman y scripts al día con las cifras nuevas; `npm audit` en 0; documentación | Que no quede nada suelto |
| 8 | Commits | Uno por fase, más el de build (Dockerfiles, `.dockerignore`, `npm audit fix`) y merge a `develop` | Cuando el usuario valide |

### A7 · Versiones objetivo

| Paquete | De | A | Notas |
| --- | --- | --- | --- |
| `react-router-dom` | 6.30.6 | `react-router` 7 | Requiere Node ≥ 20 y React ≥ 18; sigue con React 18 |
| `vite` | 5.4.21 | 8 | Node ≥ 20.19 o ≥ 22.12; cambia el empaquetador interno. Se repite la prueba del proxy con 40 s |
| `@vitejs/plugin-react` | 4.7.0 | 6 | La que pide Vite 8 |
| `vitest`, `@vitest/coverage-v8` | 3.2.7 | 5 | Node ≥ 22.12; Vite 6.4, 7 u 8 |
| `tailwindcss` | 3.4 | 4 | Navegadores: Chrome 111, Safari 16.4 y Firefox 128 o superiores |

`jsdom` y Testing Library se actualizan solo si las versiones nuevas de Vitest lo
piden o si `npm audit` los marca. Meta: `npm audit` sin vulnerabilidades.

### A8 · Ajustes de funcionalidad

**Unidad en la lista de inventario.** `InventarioItem` agrega `unidad` ("unidad"
o "kg"), como los productos (J5). La tabla muestra un decimal en los productos
por kilo: la papa P1814 en PRINCIPAL pasa de "77" a "77,1".

**Paginación de alertas (K2).** `GET /api/alertas` acepta `page` (≥ 1) y
`page_size` (1–500), opcionales. Con ellos, la respuesta agrega `page`,
`page_size` y `pages`, y trae solo esa página; sin ellos, responde como hoy. La
página de Alertas pide de a 50: unos 16 KB en vez de 1,4 MB. Los conteos siguen
saliendo del resumen.

**Estado de inconsistencia (K3).** El semáforo de inventario es `inconsistencia`
cuando el stock es negativo, antes de mirar la cobertura. Cambia en la lista,
el filtro `semaforo=inconsistencia`, el detalle y los contadores del resumen
(clave nueva `inconsistencia`). Con la foto al 2025-12-31:

| Estado | Hoy | Con K3 |
| --- | --- | --- |
| OK | 9.399 | 9.381 (las 18 con stock negativo y cobertura 999 dejan de ser OK) |
| Bajo | 386 | 386 |
| Crítico | 1.316 | 1.114, igual a las alertas de stock crítico |
| Inconsistencia | — | 220, igual a las alertas de inconsistencia |

La barra del Dashboard gana un cuarto tramo y el filtro de Inventario la opción
"◆ Inconsistencia". Con K9, el KPI "En riesgo" pasa a ser bajo + crítico, con la
misma regla:

| Ubicación | Antes (cobertura < 7 días) | Con K9 (bajo + crítico) |
| --- | --- | --- |
| Toda la red | 1.702 | 1.500 |
| PRINCIPAL | 434 | 340 |
| LA 21 | 238 | 207 |
| GLORIETA | 344 | 282 |
| Bodega Central | 686 | 671 |

Se actualizan las pruebas, los scripts y las colecciones de INV-25 que comparen
conteos del semáforo o el KPI.

### A9 · Vista de reportes de ventas

Ruta `/reportes`, entrada "Reportes" en `RUTAS` para los tres roles (K5).

| Bloque | Endpoint | Qué muestra |
| --- | --- | --- |
| Ventas | `/reportes/ventas` | Valor, margen, cantidad y transacciones del período, y la gráfica por día, semana o mes |
| Comparativa | `/reportes/ventas/comparativa` | Valor y cantidad contra el período anterior equivalente, con la variación; no aplica con "toda la historia" |
| Distribución por categorías | `/reportes/distribucion-categorias` | Participación de cada categoría en el valor vendido |
| Tendencia por sucursal | `/reportes/tendencias?por_sucursal=true` | Una serie por sucursal |
| Valorizado del inventario | `/consulta/inventario/valorizado` | Valor del stock por categoría y ubicación, a la fecha de la foto (no depende del período) |

**Filtros (K7).** El período por defecto es el mes de la última venta
(diciembre de 2025). Hay atajos de mes, trimestre, año y toda la historia, y un
rango libre. La agrupación se elige por defecto según el atajo: día para el
mes, semana para el trimestre y mes para el año y para toda la historia. Hay
además filtros de categoría y de ubicación, esta última con el selector de
siempre; el `admin_sucursal` queda fijo en su sucursal. Con la Bodega elegida
solo se ve el valorizado, con la nota "La Bodega Central no vende".

**Cambios aditivos en el Core API**, para que los filtros apliquen igual en
todos los bloques y los atajos no fijen fechas en el código:
- `/reportes/ventas/comparativa` y `/reportes/tendencias` aceptan `categoria`, como `/reportes/ventas`.
- `/reportes/ventas` agrega `datos_desde` y `datos_hasta`: la primera y la última fecha con ventas.

### A10 · Seed de usuarios de prueba (K8)

`api/scripts/seed_usuarios.py` crea o restablece, por email, los cinco usuarios
de prueba con la clave `admin123` y su ubicación, buscada por nombre en
`dw.dim_sucursal`:

| Usuario | Nombre | Rol | Ubicación |
| --- | --- | --- | --- |
| `gerente@inventaio.co` | Carlos Martínez | gerente | — |
| `admin.principal@inventaio.co` | Laura Gómez | admin_sucursal | PRINCIPAL |
| `admin.norte@inventaio.co` | Andrés Rivera | admin_sucursal | LA 21 |
| `admin.sur@inventaio.co` | María Torres | admin_sucursal | GLORIETA |
| `bodega@inventaio.co` | Diego Sánchez | admin_bodega | BODEGA_CENTRAL |

Se corre con `docker exec inventaio-api python -m scripts.seed_usuarios`. Sirve
también para devolver las claves a `admin123` después de probar el cambio de
contraseña. Es solo para desarrollo.

### Criterios de aceptación de la adenda

22. Los `.sh` quedan en LF tras un checkout o un merge, y las pruebas de `ml_service` corren con `MODELOS_DIR`.
23. El CI usa Node 22 y corre `test:cov` y `npm audit --omit=dev --audit-level=high` en el frontend.
24. El frontend corre con React Router 7, Vite 8, Vitest 5 y Tailwind 4, sin cambios visuales no buscados (guía de pantallas), y `npm audit` no reporta vulnerabilidades.
25. La lista de inventario trae `unidad` y la tabla muestra el decimal de los productos por kilo.
26. `GET /api/alertas` pagina con `page` y `page_size`, sin romper a quien no los envía; la página de Alertas pide de a 50.
27. El semáforo distingue `inconsistencia` en la lista, el filtro, el detalle y el resumen, con los conteos de la tabla de A8, y el KPI "En riesgo" es igual a bajo + crítico en cada ubicación (K9).
28. La vista de reportes muestra los cinco bloques con los filtros de K7, respeta los permisos y, con la Bodega, solo muestra el valorizado.
29. `seed_usuarios.py` deja los cinco usuarios con `admin123`, y correrlo dos veces da el mismo resultado.
30. La matriz no tiene endpoints sin destino: solo los dos de proveedores (J3) y el health quedan sin pantalla, por decisión.

## Criterios de aceptación

1. El endpoint cumple el contrato, los permisos y los errores de A1.
2. Para P1632 en PRINCIPAL, la última ventana (2025-12-17 a 2025-12-31) da 4.608 unidades y la anterior 3.522, iguales a la suma a mano sobre `v_ventas_diarias_netas`.
3. `ApiError` expone el código HTTP en 400, 403, 409, 422 y 504, y el `detail` de un 422 de validación es legible.
4. Existen las funciones de A2.2 y construyen bien sus parámetros: ids en pronóstico e histórico, `sucursal` por nombre en recomendaciones; `getDistribucionCategorias` ya no está.
5. Una petición con `timeoutMs` se cancela al vencer; una nueva con la misma clave cancela la anterior, y la cancelada no se muestra como error.
6. El proxy de Vite declara 130 s y no corta una respuesta de 40 s.
7. `useSucursal` devuelve el `id_sucursal` y el nombre de un `admin_sucursal`.
8. `SucursalSelector` con `incluirBodega={false}` no lista la Bodega, la muestra como "Bodega Central" cuando la incluye y avisa si falla la carga.
9. El menú y las rutas salen de `RUTAS`; un rol sin permiso que entra por URL vuelve a su página de inicio.
10. `useConsulta` nunca deja en pantalla la respuesta de un filtro anterior, no reporta como error una consulta cancelada y no consulta con `activo: false`.
11. `MensajeError` muestra el `detail` en los 4xx y un texto claro en 502, 503, 504, timeout y error de red; `Cargando` muestra el aviso de espera larga; `formato.js` y `etiquetas.js` cubren lo que usan las páginas.
12. Las utilidades de prueba renderizan una página con cada rol y simulan la API sin preparación adicional.
13. Dashboard: un bloque que falla no tumba la página; las ventas se rotulan con la fecha de la foto; el widget de alertas usa las etiquetas; con la Bodega elegida muestra la vista de Bodega sin pedir ventas; `admin_bodega` lo ve y entra a él por defecto.
14. Inventario: ofrece las 33 categorías reales; muestra "Inconsistencia" con cobertura "—" en el stock negativo y "Sin ventas" en la cobertura 999; muestra `stock_bodega` ("—" cuando es nulo) y el distintivo de la Bodega.
15. Alertas: muestra y filtra "Inconsistencia de inventario", marca las alertas de la Bodega y pagina de a 50.
16. El detalle de inventario muestra stock, mínimo, máximo, punto de reorden, cobertura, stock de la Bodega, categoría, proveedor y la unidad de venta, con el historial como valor y no como gráfica.
17. El cambio de contraseña funciona desde el menú y muestra los mensajes de validación, los del Core API (400 y 422) y el de éxito.
18. La matriz de A4.1 está en `frontend/README.md` y coincide con el código: cada función de `client.js` tiene su consumidor y cada endpoint su destino.
19. `frontend/README.md` tiene las convenciones y la guía para agregar una vista.
20. `npm run test` y `npm run test:cov` funcionan, con cobertura ≥ 80 % sobre la base y las tres páginas (H5).
21. No hay regresión: Dashboard, Inventario y Alertas funcionan con los tres roles y cada opción del selector, `npm run build` pasa, y siguen pasando las pruebas del Core API, los scripts de Release 1 y la colección de Postman de INV-25.

## Casos de prueba

**Backend (pytest)**

| Caso | Esperado |
| --- | --- |
| `gerente` con una sucursal física | 200 |
| `gerente` sin `sucursal_id` | 422 con la lista de sucursales físicas |
| `admin_bodega` con PRINCIPAL | 200 |
| `admin_sucursal` sin `sucursal_id` / con la suya | 200, su sucursal |
| `admin_sucursal` con otra sucursal o con la Bodega | 403 |
| `gerente` con la Bodega | 422 ("no vende") |
| Sucursal inexistente o SIN_SUCURSAL | 422 |
| `id_producto` inexistente | 404 |
| `ventanas` en 0 o en 25 | 422 |
| Sin `ventanas` | 8 ventanas, de 2025-09-02 a 2025-12-31 |
| Ventanas consecutivas | Cada una empieza el día hábil siguiente al fin de la anterior |
| Producto sin ventas en la sucursal | 200, todas las ventanas en 0 |
| Producto que se vende por kilo (PAPA PASTUSA \*KL) | `unidad` "kg", en el histórico y en `/consulta/productos` |
| Integración, P1632 en PRINCIPAL | 4.608 y 3.522 en las dos últimas, iguales a la suma a mano |

**Frontend (Vitest): base**

| Caso | Esperado |
| --- | --- |
| Respuesta 400, 403, 409, 422 o 504 | `ApiError` con el `status` correcto |
| 422 de validación con lista de errores | `detail` legible, no `[object Object]` |
| `predecir({idProducto: 91, idSucursal: 1})` | El cuerpo lleva `id_producto`, `id_sucursal` y `horizonte: 15` |
| `getRecomendacionesCompras({sucursal: "LA 21"})` | La URL lleva `sucursal=LA+21` o `LA%2021` |
| Petición con `timeoutMs` que vence | Se aborta y lanza `ApiError` marcado como timeout |
| Dos peticiones seguidas con la misma clave | Se cancela la primera y no se reporta como error |
| `useSucursal` con `admin_sucursal` | Devuelve `id_sucursal` y `sucursalNombre` |
| `useSucursales` | Una sola llamada a `/consulta/sucursales`, aunque lo usen varios componentes |
| Selector con `incluirBodega={false}` / con la Bodega | No la lista / la muestra como "Bodega Central" |
| Fallo al cargar sucursales | Mensaje visible |
| Menú con cada rol | Solo las entradas de `RUTAS` que admiten el rol |
| Rol sin permiso que entra por URL | Vuelve a su página de inicio |
| `useConsulta`: el filtro cambia antes de que llegue la respuesta | Se muestra solo la del filtro nuevo |
| `useConsulta` con `activo: false` | No llama a la API |
| `useConsulta` con un 404 | `error.status` 404 y `cargando` en falso |
| `MensajeError` con 404 de historia insuficiente / con 504 | El `detail` de `ml_service` / el texto fijo de tiempo agotado |
| `Cargando` pasada la espera | Aparece el aviso de espera larga |
| `formato.js` | `4608` → "4.608"; moneda corta igual a la del Dashboard |

**Frontend (Vitest): páginas**

| Caso | Esperado |
| --- | --- |
| Dashboard con un bloque que responde 500 | Ese bloque muestra el error; los demás se ven |
| Dashboard con la Bodega elegida | Sin tarjetas de ventas, con stock valorizado, en riesgo y la nota; no llama a los endpoints de ventas |
| Dashboard con `admin_bodega` | Se ve y es su página de inicio |
| Dashboard, widget de alertas | "Inconsistencia de inventario", no la clave cruda |
| Inventario, filtro de categorías | Las categorías de `/consulta/categorias` |
| Inventario con stock negativo / con cobertura 999 | "Inconsistencia" y "—" / "Sin ventas" |
| Inventario con `stock_bodega` nulo | Se ve "—"; las filas de la Bodega llevan el distintivo |
| Inventario: búsqueda que cambia antes de la respuesta | Solo se ven los resultados de la última |
| Detalle de inventario | Panel con los datos de la fila, el stock de la Bodega, el proveedor y la unidad de venta |
| Detalle de un producto por kilo | "Se vende por kilo (kg)" y cantidades con un decimal |
| Detalle de inventario con error (404 o 403) | El mensaje del Core API dentro del panel |
| Alertas con `inconsistencia_inventario` | Etiqueta "Inconsistencia de inventario" y opción en el filtro |
| Alertas con 120 alertas | 3 páginas de 50, 50 y 20 |
| Alertas de la Bodega | Llevan el distintivo "Bodega" |
| Cambio de contraseña con confirmación distinta o de menos de 8 caracteres | Mensaje de validación, sin llamar a la API |
| Cambio de contraseña con 400 del Core API | "La contraseña actual es incorrecta" |
| Cambio de contraseña exitoso | Mensaje de éxito |
| Cada página con los tres roles | Renderiza sin errores con la API simulada |

## Definition of Done

- [ ] Cumple los 21 criterios de aceptación.
- [ ] Pruebas de pytest y de Vitest, con cobertura ≥ 80 % sobre lo nuevo del backend y sobre el alcance de H5.
- [ ] Autorrevisión documentada en el commit o PR.
- [ ] Swagger del Core API con el endpoint nuevo; `docs/INV-26-fix.md` con A1 a A4; `frontend/README.md` con la guía y la matriz.
- [ ] Cumple los criterios 22 a 30 de la adenda: sin pendientes por reportar.
- [ ] Integrado en `develop` antes de empezar las vistas, con A1 a A4 completos (G8).
- [ ] Verificado en Docker Compose local con los tres roles y cada opción del selector.
- [ ] Sin bugs bloqueantes.

## Riesgos y limitaciones

- **Puntos.** El fix creció (endpoint, base, adaptación de la app, detalle, contraseña, ruta y la adenda con las versiones mayores y la vista de reportes) y se sigue cubriendo con los 8 SP de INV-26 (F3).
- **Tailwind 4.** Es el cambio con más riesgo visual: se revisan todas las pantallas con la guía, y deja de dar soporte a navegadores anteriores a Chrome 111, Safari 16.4 y Firefox 128.
- **Vite 8.** Cambia el empaquetador interno; se verifican el build, el servidor de desarrollo y el proxy de 130 s.
- **Contrato del semáforo (K3).** Los conteos de crítico y OK de INV-25 cambian; se actualizan sus pruebas, scripts y colecciones en el mismo fix.
- **Red inestable.** Las actualizaciones descargan muchos paquetes: se usan reintentos de npm (`--fetch-retries`).
- **Proveedores simulados.** El detalle de inventario muestra el proveedor de `producto_proveedor`, que es simulado (J3).
- **Contraseñas de prueba.** Las pruebas de integración, los scripts y la colección de Postman usan `admin123`: quien pruebe el cambio de contraseña a mano debe volver a dejarla.
- **Nombres de sucursal.** Con G2 solo las recomendaciones dependen del nombre: un cambio de nombres en la bodega rompería ese filtro.
- **Sin lint.** `package.json` no tiene script de lint; lo resuelve INV-24.
- **Foto única.** Con una sola foto, el historial de stock trae un punto: el detalle lo muestra como valor, no como serie.
- **Productos nuevos.** Con G1, un producto que empezó a venderse hace poco muestra ventanas en 0 antes de su primera venta, como lo ve el modelo.

## Pendientes de confirmar

| # | Pregunta | Valor por defecto mientras tanto |
| --- | --- | --- |
| 1 | ¿`getVentasProducto` necesita más adelante una serie diaria? | No; ventanas de 15 días hábiles |

La paleta de Tailwind 4 quedó decidida en K10.

La referencia a `INV-26-27-requerimientos.md` se quitó (K1), y la vista de
reportes ya no es una historia aparte (K5–K7).

## Ambiente de desarrollo

1. Rama desde `develop` actualizado: `feature/INV-26-fix-base` (creada).
2. Usuarios de prueba cargados con el seed (A10): `docker exec inventaio-api python -m scripts.seed_usuarios`, clave `admin123`.
3. `docker compose up -d ml-service api` (`--build` solo si cambió un `requirements.txt` o un `Dockerfile`); para el frontend, `npm install` y `npm run dev` en `frontend/`.
4. Pruebas: `docker exec inventaio-api python -m pytest` y, en `frontend/`, `npm run test`.
5. Verificar a mano Dashboard, Inventario (con el detalle) y Alertas con `gerente@inventaio.co`, `admin.principal@inventaio.co` y `bodega@inventaio.co`, con cada opción del selector. El cambio de contraseña, con un usuario y volviendo a dejar `admin123`.

**Archivos a crear o tocar**

| Archivo | Cambio |
| --- | --- |
| `api/consulta/router.py` y `api/schemas/consulta.py` | Endpoint y esquema de ventas por producto (A1) |
| `api/tests/test_ventas_producto*.py` (nuevos) | Pruebas de A1 |
| `api/tests/postman/INV-26-fix.postman_collection.json` (nuevo) | Casos de A1 y de la unidad (J5) para Postman |
| `frontend/src/api/client.js` | A2.1 a A2.3 |
| `frontend/vite.config.js`, `frontend/package.json` | A2.4 y A2.8 |
| `frontend/src/hooks/useSucursales.js` (nuevo), `useSucursal.js` | A2.5 y A2.6 |
| `frontend/src/components/SucursalSelector.jsx` | A2.7 |
| `frontend/src/rutas.js`, `components/GuardaRol.jsx` (nuevos), `App.jsx` | A2.9, A3.3 y A3.7 |
| `frontend/src/hooks/useConsulta.js` (nuevo) | A2.10 |
| `frontend/src/components/Cargando.jsx`, `MensajeError.jsx`, `EstadoConsulta.jsx`, `DistintivoBodega.jsx`, `utils/formato.js`, `utils/etiquetas.js` (nuevos) | A2.11 |
| `frontend/.gitignore` (nuevo) | `dist/` y `coverage/`, que generan el build y la cobertura |
| `frontend/src/test/setup.js`, `test/utils.jsx` (nuevos), `api/AuthContext.jsx` | A2.12 |
| `frontend/src/pages/Dashboard.jsx`, `Inventario.jsx`, `Alertas.jsx` | A3.1, A3.2, A3.4 y A3.5 |
| `frontend/src/components/DetalleInventario.jsx`, `CambiarPassword.jsx` (nuevos) | A3.6 y A3.7 |
| `frontend/src/**/*.test.js(x)` (nuevos) | Pruebas de Vitest |
| `frontend/README.md` (nuevo) | A4.1 a A4.3 |
| `docs/INV-26-fix.md` (nuevo) | Documentación |
| `.gitattributes` (nuevo), `ml_service/tests/conftest.py` | A5 |
| `.github/workflows/ci.yml`, `frontend/.nvmrc` (nuevo) | A6 |
| `frontend/package.json`, `package-lock.json`, `vite.config.js`, `src/index.css`, `main.jsx`, `App.jsx`; se borran `tailwind.config.js` y `postcss.config.js` | A7 |
| `api/core/semaforo.py` (nuevo), `api/inventario/router.py`, `api/schemas/inventario.py`, `api/reportes/router.py` (KPI, K9), `api/alertas/router.py`, `api/schemas/alertas.py`, `api/tests/test_inventario.sh`; `Dashboard.jsx`, `Inventario.jsx`, `Alertas.jsx` | A8 |
| `api/reportes/router.py`, `api/schemas/reportes.py`; `frontend/src/pages/Reportes.jsx`, `utils/periodos.js` (nuevos), `rutas.js`, `client.js` | A9 |
| `api/scripts/seed_usuarios.py` (nuevo); se borra `api/scripts/reset_passwords.py` | A10 |
| `api/tests/test_inv26_ajustes_integracion.py`, `test_seed_usuarios.py` (nuevos), colección de Postman y OpenAPI | Pruebas de la adenda |
| `api/Dockerfile`, `ml_service/Dockerfile`, `api/.dockerignore`, `ml_service/.dockerignore` (nuevos) | Build de las imágenes con la red lenta |
