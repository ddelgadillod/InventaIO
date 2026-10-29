# INV-25 — Homologación del Core API con la bodega real

Los endpoints del Core API construidos en Release 1 contra la bodega simulada
ya funcionan con la bodega real de INV-60/61. Se arreglaron los cuatro que
daban 500, se unificó la regla de permisos, la Bodega Central se distingue de
las sucursales y el pronóstico quedó en el Swagger del Core API con la misma
autenticación.

La auditoría está en [`INV-25-auditoria.md`](INV-25-auditoria.md), y la
especificación, con las decisiones D1–D10 y las reglas R1–R6, en
[`INV-25-requerimientos.md`](INV-25-requerimientos.md). Este documento dice
cómo quedó implementado y qué dio con los datos reales.

## Regla de permisos por ubicación

`api/core/ubicaciones.py` decide qué ubicación filtra cada usuario según el
tipo de dato. La usan inventario, alertas y reportes; antes cada router tenía
su propia regla, y se contradecían.

| Rol | Stock (inventario) | Alertas | Ventas y KPIs (reportes) |
| --- | --- | --- | --- |
| `gerente`, `admin_bodega` | Todas; con `sucursal_id`, esa | Todas; con `sucursal_id`, esa | Todas; con `sucursal_id`, esa |
| `admin_sucursal` | La suya; la Bodega con su `sucursal_id`; otra, 403 | Solo la suya; la Bodega u otra, 403 | Solo la suya; la Bodega u otra, 403 |

Un `sucursal_id` inexistente o el de SIN_SUCURSAL da 422 con la lista de los
válidos (R2).

## Cambios por endpoint

| Endpoint | Antes | Ahora |
| --- | --- | --- |
| `GET /api/consulta/productos` | 500 | 4.449 productos; `codigo_item` como texto (`P1632`, `00008`) |
| `GET /api/consulta/productos/{id}` | 500, o el código sin ceros | El código como texto; `proveedores` de `dw.producto_proveedor` (P1632 → Lácteos del Cauca Ltda.) |
| `GET /api/consulta/sucursales` | 500 | 4 ubicaciones con su `tipo`, sin SIN_SUCURSAL; `ciudad`, `departamento` y `factor_volumen` pueden ser nulos |
| `GET /api/consulta/proveedores/{id}` | 500 | Sus productos de `dw.producto_proveedor` (Distribuidora Valle, 1.978) |
| `GET /api/consulta/inventario` | `admin_sucursal` no veía la Bodega; los demás `sucursal_id` se ignoraban en silencio | Regla de permisos; cada fila trae `tipo_ubicacion` y `stock_bodega` |
| `GET /api/consulta/inventario/detalle` | `admin_bodega` recibía 403 fuera de la Bodega | Regla de permisos; `tipo_ubicacion` y `stock_bodega` |
| `GET /api/consulta/inventario/resumen` | Ignoraba el `sucursal_id` que envía el frontend | Lo acepta; `tipo_ubicacion` por ubicación |
| `GET /api/consulta/inventario/valorizado` | Sin filtro | Acepta `sucursal_id`; `tipo_ubicacion` por grupo |
| `GET /api/alertas` | 1.415 "sin movimiento" de la Bodega; stock negativo como "stock crítico" | Reglas de D4; tipo nuevo `inconsistencia_inventario`; `tipo_ubicacion` |
| `GET /api/alertas/resumen` | Ignoraba `sucursal_id` | Lo acepta; `por_tipo` con la clave nueva; `tipo_ubicacion` por ubicación |
| `GET /api/reportes/*` (6) | `admin_bodega` los veía vacíos; `sucursal_id` solo para el gerente | Regla de permisos: `admin_bodega` ve y filtra todo |
| `GET /api/reportes/tendencias` | Ignoraba `dias` | Sin `fecha_inicio`, empieza `dias` días antes de `fecha_fin` (30 por defecto) |
| `POST /api/ml/predict` (nuevo) | Solo en `ml_service`, sin autenticación | En el Core API, con token y permisos |

`stock_bodega` es el stock de la Bodega Central para el mismo producto y fecha:
0 si la Bodega no tiene fila de ese producto y nulo en las filas de la propia
Bodega (R3).

## Alertas (D4)

| Tipo | Regla | Gerente | `admin_sucursal` PRINCIPAL |
| --- | --- | --- | --- |
| `inconsistencia_inventario` (nuevo, `critica`) | Stock negativo, con cualquier cobertura | 220 | 95 |
| `stock_critico` (`critica`) | Cobertura < 3 días y stock ≥ 0 | 1.114 (Bodega 592) | 202 |
| `stock_bajo` (`alta`) | Cobertura de 3 a 7 días | 386 | 138 |
| `sin_movimiento` (`media`) | Stock > 0 y 0 ventas en 30 días; solo sucursales | 2.453 | 865 |
| `rotacion_baja` (`media`) | Ventas < 20 % del promedio; solo sucursales | 279 | 8 |
| **Total** | | **4.452** (antes 5.849) | **1.308** (antes 1.307) |

PRINCIPAL sube en uno porque una fila con stock negativo y cobertura 999 no
generaba ninguna alerta y ahora es `inconsistencia_inventario` (R4). Las
inconsistencias salen primero entre las críticas, porque su `valor` es el stock
negativo.

## Pronóstico en el Core API (D8)

```powershell
$t = (Invoke-RestMethod http://localhost:8000/api/auth/login -Method Post -ContentType "application/json" `
  -Body '{"email":"admin.principal@inventaio.co","password":"admin123"}').access_token
Invoke-RestMethod http://localhost:8000/api/ml/predict -Method Post -ContentType "application/json" `
  -Headers @{Authorization = "Bearer $t"} -Body '{"producto_id": "P1632", "sucursal_id": "PRINCIPAL", "horizonte": 15}'
```

Mismo cuerpo y misma respuesta que `POST /api/predict` de `ml_service`
(P1632 en PRINCIPAL: q50 3.366,01 y límite superior 4.608,72). Un
`admin_sucursal` solo pronostica su sucursal (403). Los 404 y 422 de
`ml_service` pasan con su `detail` (historia insuficiente, la Bodega no es
sucursal física); los demás errores se traducen como en INV-23 (503, 504 y
502). Está en el Swagger del Core API, bajo "Pronóstico", con el mismo
esquema de autenticación que el resto.

## Decisiones de implementación

Donde la especificación deja margen, se decidió así. Cada punto tiene su prueba.

| Tema | Decisión | Por qué |
| --- | --- | --- |
| Detalle de inventario con una ubicación inexistente | 422, como todo `sucursal_id` inválido (antes 404) | Una sola regla (R2) |
| `admin_sucursal` sin sucursal física (sin asignar, SIN_SUCURSAL o la Bodega) | 403 "El usuario no tiene una sucursal asignada" | No hay una sucursal válida que aplicarle |
| Orden de las validaciones | La ubicación inexistente (422) se revisa antes que el permiso (403) | Un error de digitación se informa como tal |
| Mensaje del 403 para la Bodega en alertas y reportes | "Solo puede consultar su sucursal (X); la Bodega Central, solo en el stock" | Dice qué sí puede ver |
| `tipo` inválido en alertas | Sigue respondiendo 400, como en Release 1 | No cambiar el contrato sin necesidad |
| Pronóstico de `admin_sucursal` | Compara el nombre exacto, como `ml_service`; sin sucursal en el cuerpo, 403 | `ml_service` exige el nombre exacto; sin sucursal no hay a quién aplicarle el permiso |
| `dias` en tendencias | Entre 1 y 366 | Un año como máximo: la serie es diaria |
| `categorias` del proveedor | Sigue saliendo de `dim_proveedor` | Es un dato del proveedor (ficticio); la relación con productos es la que cambió |

## Cambios de contrato

| Cambio | Efecto en el frontend |
| --- | --- |
| `codigo_item` entero → texto | Ninguno: no usa productos ni proveedores |
| `ciudad`, `departamento` y `factor_volumen` pueden ser nulos | El selector de sucursal vuelve a cargar (antes recibía 500) |
| `/sucursales` sin SIN_SUCURSAL | El selector muestra 4 ubicaciones |
| Alerta `inconsistencia_inventario` y la Bodega sin `sin_movimiento` | La página de alertas muestra el tipo nuevo con su nombre crudo hasta que se le agregue la etiqueta |
| 403 y 422 donde antes se ignoraba el filtro | Ninguno: un `admin_sucursal` no envía `sucursal_id` y el selector solo ofrece ubicaciones válidas |

Lo demás es aditivo: `tipo_ubicacion`, `stock_bodega`, `sucursal_id` en los
resúmenes y el valorizado, `dias` en tendencias y `POST /api/ml/predict`.

## Pruebas

El set de pruebas para validar, con la colección de Postman y la tabla de los
48 casos, está en [`INV-25-pruebas.md`](INV-25-pruebas.md).

Dentro del contenedor `api`:

```powershell
docker exec inventaio-api python -m pytest -m "not integracion"   # unitarias, unos 3 s
docker exec inventaio-api python -m pytest -m integracion         # contra la bodega real, unos 60 s
docker exec inventaio-api python -m pytest --cov=consulta --cov=inventario --cov=alertas --cov=reportes --cov=core.ubicaciones --cov=ml
```

| Archivo | Pruebas | Qué cubre |
| --- | --- | --- |
| `test_ubicaciones.py` | 23 | La regla de permisos con los tres roles y los tres tipos de dato, sin base |
| `test_prediccion.py` | 19 | El pronóstico con `ml_service` falso: permisos, errores que pasan tal cual, traducción de los demás y Swagger |
| `test_homologacion_integracion.py` | 19 | Cada endpoint ajustado contra la bodega real con los usuarios de prueba: las cifras de "Resultados esperados", la regla de permisos, D4, `stock_bodega`, el pronóstico real y la regresión de lo que no cambió |

Resultado del Core API completo, con INV-23: 131 pruebas pasan (107
unitarias y 24 de integración). Cobertura del 99 % sobre los módulos tocados:
`consulta` 100 %, `inventario` 99 %, `alertas` 99 %, `reportes` 98 %,
`core/ubicaciones.py` 100 % y `ml/` 100 %. `ruff`, sin observaciones.

**Scripts de Release 1**, actualizados a los datos y las reglas nuevas (desde
Ubuntu, `bash api/tests/<script>.sh`):

| Script | Antes de INV-25 | Ahora |
| --- | --- | --- |
| `test_consulta.sh` | 17 de 34 fallan | 37 de 37 |
| `test_inventario.sh` | 2 de 40 fallan | 47 de 47 |
| `test_alertas.sh` | 1 de 34 falla | 39 de 39 |
| `test_reportes.sh` | 50 de 50 (no revisaba al usuario de bodega) | 55 de 55 |
| `test_recomendaciones.sh` (INV-23) | 54 de 54 | 54 de 54 |

`test_auth.sh` no cambió y no se corrió: modifica contraseñas.

**Frontend.** Se repitieron las llamadas de `frontend/src/api/client.js` con
los tres roles y cada opción del selector de sucursal (todas, 1, 2, 3 y 5):
las 110 llamadas responden 200.

## Criterios de aceptación

| # | Criterio | Dónde se verifica |
| --- | --- | --- |
| 1–3 | Auditoría completa, con evidencia y en `docs/` | `INV-25-auditoria.md` |
| 4 | Los 14 endpoints ajustados responden bien con la bodega real | `test_homologacion_integracion.py` y los 4 scripts |
| 5 | Una sola regla de permisos | `test_ubicaciones.py`, `test_admin_sucursal_*` y `test_admin_bodega_*` de integración |
| 6 | `admin_sucursal` ve el stock de la Bodega y no sus alertas | `test_admin_sucursal_ve_su_inventario_y_el_stock_de_la_bodega`, `test_admin_sucursal_solo_ve_sus_alertas` |
| 7 | `tipo_ubicacion` en inventario y alertas; `tipo` en `/sucursales` | `test_inventario_trae_tipo_ubicacion_y_stock_bodega`, `test_sucursales_sin_sin_sucursal_y_con_nulos` |
| 8 | Alertas según D4 | `test_alertas_con_las_reglas_de_d4`, Tests 31–33 de `test_alertas.sh` |
| 9 | Proveedores desde `producto_proveedor` | `test_detalle_de_producto_y_de_proveedor_desde_producto_proveedor` |
| 10 | Pronóstico en el Swagger con la misma autenticación | `test_openapi_documenta_predict_con_el_esquema_de_auth`, `test_predict_con_ml_service_real` |
| 11 | El frontend no pierde funcionalidad | Las 110 llamadas del frontend responden 200 |
| 12 | INV-23 y `ml_service` sin cambios | Las pruebas de INV-23 y `test_recomendaciones.sh` siguen pasando; `ml_service` no se tocó |

## Limitaciones y pendientes

- **El frontend no cambió** (D9). Muestra el tipo `inconsistencia_inventario` con su nombre crudo, `useSucursal` sigue leyendo `user.sucursal_id` y no hay una vista para el stock de la Bodega de un `admin_sucursal`. Quedan para INV-27 o la Fase 4 del plan privado.
- **`ml_service` sigue publicado** en el puerto 8001 sin autenticación: el pronóstico por el Core API no cierra esa puerta (riesgo para Release 3).
- **La cobertura de la Bodega** en las alertas sigue siendo la del ETL, contra la demanda de las tres sucursales (pendiente 1 de la especificación).
- **Foto única.** El historial de 30 días del detalle trae un solo punto.
- **Usuarios de prueba.** Las pruebas de integración y los scripts necesitan el seed de usuarios en la base local, que no está en el repo.
