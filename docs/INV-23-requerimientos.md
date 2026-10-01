# INV-23 · Requerimientos de los endpoints de recomendaciones (Core API)

Versión del 2026-09-30. Reemplaza el borrador del mismo día: el borrador se
probó contra el código y las respuestas reales de `ml_service`, y las
decisiones C1–C6 se acordaron antes de implementar. Los pendientes del final
no bloquean.

## Resumen

INV-23 expone en el **Core API** (`api/`, puerto 8000) dos endpoints GET que
leen las recomendaciones de INV-21 e INV-22 en `ml_service`, las filtran por
sucursal, categoría y urgencia y les agregan el nombre y la categoría del
producto. Así el frontend no conoce el contrato POST de `ml_service` ni hace
el cruce con el catálogo.

**Historia de usuario.** Como desarrollador, quiero endpoints GET que expongan las recomendaciones de compras y transferencias con filtros, para consumirlas desde el frontend sin que cada pantalla tenga que llamar directo a `ml_service` ni conocer su contrato POST.

| Campo | Valor |
| --- | --- |
| Prioridad | Highest |
| Puntos | 5 |
| Épica | E7 Recomendación |
| Sprint | Sprint 5 (21 sep – 10 oct) · etiqueta momento-ii |
| Depende de | INV-21 (`POST /api/compras`) e INV-22 (`POST /api/transferencias`). De INV-25 toma solo el cliente hacia `ml_service`, que se construye aquí (C5) |
| Alimenta a | INV-27 (vista de recomendaciones en el dashboard) e INV-32 (tool-calling del agente NLP) |

**Dentro del alcance**

- `GET /api/ml/recomendaciones/compras`, sobre `POST /api/compras`.
- `GET /api/ml/recomendaciones/transferencias`, sobre `POST /api/transferencias`.
- Nombre y categoría del producto (`dw.dim_producto`) en cada fila.
- Filtros combinables `sucursal`, `categoria` y `urgencia`, con los permisos por rol del Core API.
- Resumen propio, recalculado sobre lo filtrado.
- Caché en memoria del resultado de `ml_service`.
- Cliente HTTP mínimo del Core API hacia `ml_service` y su configuración en Docker Compose.
- Dos campos nuevos en `GET /api/health` de `ml_service`, que la caché necesita.

**Fuera del alcance**

- Cualquier cálculo de recomendación: lo hacen INV-21 e INV-22. Aquí solo se filtra, se enriquece y se resume.
- Paginación y exportación a CSV (la exportación es de INV-27).
- El proxy genérico `/api/ml/*` hacia `predict`, `transferencias` y `compras` (INV-25).
- Cambios a los contratos de `/api/predict`, `/api/transferencias` y `/api/compras`.
- Ajustar las demás rutas del Core API a la bodega real.

## Punto de partida

Cifras con la foto al 2025-12-31 y el catálogo completo.

| Pieza | Estado actual | Uso en INV-23 |
| --- | --- | --- |
| `POST /api/compras` (INV-21) | 19–22 s; 1,0 MB con detalle. 1.340 líneas, 277 productos en `cubrir_con_traslado`, 220 alertas | Fuente del endpoint de compras |
| `POST /api/transferencias` (INV-22) | 21 s sin balance y 36 s con balance (5,2 MB). 119 traslados, 11.710 filas de balance y 2.982 alertas (2.762 `sin_pronostico`) | Fuente del endpoint de transferencias |
| `GET /api/health` de `ml_service` | Estado, modelos y conexión a la bodega. No dice la fecha de la foto ni la versión de las políticas | Se le agregan esos dos datos (C3) |
| Core API, autenticación | JWT con `HTTPBearer`. Sin token responde 403 y con token inválido, 401. `admin_sucursal` ve solo su sucursal (`api/inventario/router.py`) | Misma regla (C1) |
| Core API → `ml_service` | No existe: ni `ML_SERVICE_URL`, ni cliente, ni la variable en Compose. La ruta `/api/ml/` de INV-25 no está en el repo | Se construye el cliente mínimo (C5) |
| Pruebas del Core API | Solo scripts con curl (`api/tests/*.sh`) que necesitan usuarios. No hay pytest | Se monta pytest para esta historia |
| `app.usuarios` | Vacía en la base local desde la migración a la bodega real | Hay que aplicar el seed de usuarios de prueba antes de verificar |
| `dw.dim_producto` | 4.449 productos, 33 categorías. `nombre` y `categoria` no son nulos. Los 4.419 productos de las respuestas tienen fila | Nombre y categoría de cada fila |
| `dw.dim_sucursal` | PRINCIPAL, LA 21, GLORIETA, BODEGA_CENTRAL y SIN_SUCURSAL | Valores válidos de `sucursal` (sin SIN_SUCURSAL) |

## Qué cambió frente al borrador

| Hallazgo | Evidencia | Decisión |
| --- | --- | --- |
| El borrador no habla de autenticación ni de permisos | Todo el Core API exige token, y el administrador de sucursal solo ve la suya | C1 |
| Filtrar compras solo por `destino` esconde casi toda la necesidad de una sucursal | PRINCIPAL: 164 líneas directas, pero su necesidad también está en 650 líneas de la Bodega y en 172 productos de `cubrir_con_traslado` | C2, R1 |
| Cada llamada recalcula el catálogo completo | 20–36 s por llamada, también con filtros | C3 |
| Volumen de transferencias | 11.710 filas de balance (5,2 MB, 6,8 MB enriquecido); 2.762 de las 2.982 alertas son `sin_pronostico`, sin acción | C4 |
| La dependencia de INV-25 no existe en el repo | No hay cliente, URL ni ruta `/api/ml/` | C5 |
| Los ejemplos quitaban campos que el frontend necesita | Sin `fecha_inventario` no se puede decir de qué día es la foto | C6 |
| Los ejemplos tenían nombres y categorías inventados | P1632 es "HUEVOS *UND" (Huevos); P3937, "ARROZ ZULIA *500 GR" (Arroz; no existe la categoría "Abarrotes"); P4650, "VASO TUC 7 OZ *UND" (Hogar). P0001 y P0002 no existen | Ejemplos de este documento, con datos reales |
| La urgencia no es igual en todas las listas | En transferencias también hay `vigilancia` (44 filas de balance) y es nula en 4.805 filas (la Bodega y los pares sin pronóstico). Las alertas no tienen urgencia | R2 |
| Un error de digitación daría una respuesta vacía sin aviso | `sucursal=Principal`, o `categoria=Lacteos` contra "Lácteos" | R3 |
| El resumen de `ml_service` no se puede recalcular tal cual | `pares_sin_pronostico` es solo un conteo, y `cantidad_trasladada` suma unidades con kilos | R4 |
| No se decía qué hacer si `ml_service` falla | 409 (foto sin ventas), 503, caído, lento | R5 |
| Producto sin fila en `dim_producto` | No ocurre: `ml_service` solo devuelve productos que están en `dim_producto` (0 de 4.419) | R6 |

## Decisiones acordadas

| Código | Tema | Decisión |
| --- | --- | --- |
| C1 | Permisos | Se exige token. El gerente y `admin_bodega` ven todo y pueden filtrar por cualquier sucursal. A `admin_sucursal` se le aplica siempre su sucursal: sin el parámetro, se usa la suya; con otra, 403 |
| C2 | Filtro `sucursal` en compras | `sucursal=X` devuelve las líneas directas a X y las líneas de la Bodega donde X participa, con el detalle recortado a X. El resumen separa lo que se compra para X de lo que X necesita a través de la Bodega |
| C3 | Caché | En memoria del Core API. La clave es el endpoint, la fecha de la foto y las versiones de las políticas de INV-21 e INV-22. Se calcula una vez y los filtros se aplican sobre el resultado guardado |
| C4 | Volumen | Parámetro `incluir_balance`, `false` por defecto. Sin balance, las alertas `sin_pronostico` no se listan pero se cuentan en el resumen |
| C5 | Cliente hacia `ml_service` | INV-23 crea el cliente mínimo: `ML_SERVICE_URL`, `httpx` con timeout de 120 s, traducción de errores y la variable en Docker Compose. INV-25 lo reutiliza |
| C6 | Campos | Todos los campos de `ml_service`, más `nombre_producto` y `categoria` en cada fila y `filtros_aplicados`. Resumen propio. En compras, `incluir_detalle` (`true` por defecto), como en `ml_service` |

**Reglas que se desprenden** (se propusieron en la revisión del borrador)

| Código | Regla |
| --- | --- |
| R1 | **Vista desde la sucursal.** En compras, con `sucursal=X` (sucursal física), una línea de la Bodega o un producto de `cubrir_con_traslado` donde X participa se muestra desde X: `detalle` solo con X, y `urgencia`, `dias_hasta_agotarse`, `llega_tarde` y `motivo` de X. `cantidad`, `necesidad` y `sobrante_bodega` siguen siendo los de toda la compra. El campo nuevo `necesidad_sucursal` dice cuánto de la necesidad es de X |
| R2 | **Urgencia.** Valores válidos: `urgente`, `alta` y `normal` en compras; además `vigilancia` en transferencias. Se filtra por coincidencia exacta; las filas con urgencia nula no pasan el filtro. **El filtro de urgencia no se aplica a las alertas**: no tienen urgencia y se muestran según sucursal y categoría |
| R3 | **Valores desconocidos.** `sucursal` y `categoria` se comparan sin distinguir mayúsculas, acentos ni espacios de los extremos (`lacteos` y ` LÁCTEOS ` dan "Lácteos"). Un valor que no existe en la bodega, o SIN_SUCURSAL, responde 422. Una combinación válida sin filas responde 200 con las listas vacías y el resumen en cero |
| R4 | **Resumen propio.** Se calcula solo con las filas que pasan los filtros. Las cantidades van separadas por unidad (`{unidad, kg}`) para no sumar unidades con kilos. Sin filtros, cada total coincide con el de `ml_service` (sumando `unidad` y `kg` donde `ml_service` los mezcla) |
| R5 | **Errores de `ml_service`.** Se traducen con la tabla de "Errores". Una respuesta con error no se guarda en la caché |
| R6 | **Producto sin fila en `dim_producto`.** `nombre_producto` y `categoria` van en `null`, sin romper la respuesta. Con el filtro `categoria`, esa fila no pasa |

## Contrato de los endpoints

Ambos endpoints viven en `api/ml/router.py`, bajo la etiqueta "Recomendaciones"
del Swagger del Core API (http://localhost:8000/api/docs).

### Común a los dos

**Autenticación.** Encabezado `Authorization: Bearer <access_token>`, el de
`POST /api/auth/login`.

| Rol | Sin `sucursal` | Con `sucursal=X` |
| --- | --- | --- |
| `gerente` | Todo | X |
| `admin_bodega` | Todo | X |
| `admin_sucursal` | Su sucursal | X si es la suya; si no, 403 |

**Parámetros comunes** (query, todos opcionales, combinables con AND)

| Parámetro | Tipo | Regla |
| --- | --- | --- |
| `sucursal` | texto | PRINCIPAL, LA 21, GLORIETA o BODEGA_CENTRAL, normalizado (R3). En la URL, `LA%2021` |
| `categoria` | texto | Una de las 33 categorías de `dim_producto`, normalizada (R3) |
| `urgencia` | `urgente` \| `alta` \| `normal` (en transferencias, también `vigilancia`) | Coincidencia exacta; no se aplica a las alertas (R2) |

**Campos que agrega el Core API** a la respuesta de `ml_service`

| Campo | Dónde | Significado |
| --- | --- | --- |
| `nombre_producto`, `categoria` | Cada fila de `compras`, `cubrir_con_traslado`, `alertas`, `traslados` y `balance` (no dentro de `detalle`) | De `dw.dim_producto`; `null` si no hay fila (R6) |
| `necesidad_sucursal` | Filas de `compras` y `cubrir_con_traslado` | Parte de la necesidad que es de la sucursal filtrada (R1). `null` sin filtro de sucursal física |
| `filtros_aplicados` | Raíz | `{sucursal, sucursal_por_rol, categoria, urgencia}` con los valores canónicos usados, o `null`. `sucursal_por_rol` es `true` si la sucursal la puso el rol del usuario |
| `calculado_en` | Raíz | Cuándo se pidió el resultado a `ml_service` (ISO 8601). Si viene de la caché, es la hora del cálculo original |

**Errores**

| Código | Cuándo |
| --- | --- |
| 401 | Token inválido o vencido |
| 403 | Sin token (así responde hoy `HTTPBearer`), `admin_sucursal` pidiendo otra sucursal o sin sucursal asignada |
| 409 | `ml_service` responde 409: la foto es posterior a la última venta cargada. Se reenvía su `detail` |
| 422 | Parámetro inválido: sucursal o categoría desconocida, urgencia fuera de la lista, booleano mal escrito |
| 502 | `ml_service` responde un error inesperado (otro 4xx, o un 5xx distinto de 503) |
| 503 | `ml_service` no acepta la conexión, su `/api/health` dice `degradado` o responde 503 (bodega no disponible) |
| 504 | `ml_service` no responde en `ML_SERVICE_TIMEOUT_SEGUNDOS` (120 s) |

### `GET /api/ml/recomendaciones/compras`

Llama a `POST /api/compras` sin lista de productos y con detalle, y guarda el
resultado en la caché.

**Parámetro propio:** `incluir_detalle` (booleano, `true` por defecto). Con
`false`, las filas de `compras` y `cubrir_con_traslado` no traen `detalle`.

**Qué filtra cada parámetro**

| Lista | `sucursal=X` (física) | `sucursal=BODEGA_CENTRAL` | `categoria` | `urgencia` |
| --- | --- | --- | --- | --- |
| `compras` | Directas a X, más las de la Bodega donde X participa, vistas desde X (R1) | Solo las líneas de la Bodega, con detalle completo | Sí | Sí; con X, la urgencia de X |
| `cubrir_con_traslado` | Los productos donde X participa, vistos desde X (R1) | Todos | Sí | Sí |
| `alertas` | `sucursal` = X | `sucursal` = BODEGA_CENTRAL | Sí | No (R2) |

`fecha_inventario`, `fecha_pronostico`, `lead_time_dias`, `politicas` y
`calendario` pasan sin cambios. `no_encontrados` siempre llega vacía, porque el
GET no recibe lista de productos.

**Resumen**

| Campo | Cálculo sobre las filas devueltas |
| --- | --- |
| `productos` | Productos distintos en `compras` y `cubrir_con_traslado` |
| `lineas`, `lineas_sucursal`, `lineas_bodega` | Líneas de `compras`: todas, directas y para la Bodega |
| `cantidad` | `{unidad, kg}`: suma de `cantidad` de todas las líneas |
| `cantidad_directa` | `{unidad, kg}`: suma de las líneas directas a sucursal |
| `cantidad_bodega` | `{unidad, kg}`: suma de las líneas para la Bodega (la compra completa, aunque X sea solo una parte) |
| `necesidad_via_bodega` | `{unidad, kg}`: con `sucursal=X` física, suma de `necesidad_sucursal` de las líneas de la Bodega. `null` en otro caso |
| `cubiertos_por_bodega` | Filas de `cubrir_con_traslado` |
| `alertas` | Filas de `alertas` |

**Ejemplo** con datos reales, como gerente:
`GET /api/ml/recomendaciones/compras?sucursal=PRINCIPAL&incluir_detalle=false`.
Se muestran dos de las 814 líneas, una de las 172 filas de `cubrir_con_traslado`
y una de las 95 alertas; `calendario` está abreviado y `calculado_en` es ilustrativo.

```json
{
  "fecha_inventario": "2025-12-31",
  "fecha_pronostico": "2025-12-31",
  "lead_time_dias": 5,
  "politicas": {"inv21": {"version": 1, "fecha": "2026-09-30"},
                "inv22": {"version": 1, "fecha": "2026-09-30"}},
  "calendario": [
    {"grupo": "quincenal", "tipo_destino": "bodega_central", "fecha_pedido": "2026-01-02", "fecha_llegada": "2026-01-07",
     "fecha_llegada_sucursal": "2026-01-09", "pedido_siguiente": "2026-01-16", "cubre_hasta": "2026-01-23",
     "dias_cubiertos": 22, "dias_hasta_llegada": 8},
    {"grupo": "semanal", "tipo_destino": "sucursal", "...": "..."}
  ],
  "compras": [
    {"producto_id": "P1632", "nombre_producto": "HUEVOS *UND", "categoria": "Huevos",
     "destino": "PRINCIPAL", "tipo_destino": "sucursal", "grupo": "semanal",
     "cantidad": 4735, "unidad": "unidad", "urgencia": "urgente", "dias_hasta_agotarse": 2.2,
     "fecha_pedido": "2026-01-06", "fecha_llegada": "2026-01-11", "fecha_llegada_sucursal": "2026-01-11",
     "llega_tarde": true, "necesidad": 4734.22, "necesidad_sucursal": 4734.22,
     "sobrante_bodega": null, "motivo": "reposicion"},
    {"producto_id": "00008", "nombre_producto": "AGUA CRISTAL LITRO SPORT", "categoria": "Bebidas",
     "destino": "BODEGA_CENTRAL", "tipo_destino": "bodega_central", "grupo": "quincenal",
     "cantidad": 47, "unidad": "unidad", "urgencia": "normal", "dias_hasta_agotarse": 10.5,
     "fecha_pedido": "2026-01-02", "fecha_llegada": "2026-01-07", "fecha_llegada_sucursal": "2026-01-09",
     "llega_tarde": false, "necesidad": 46.86, "necesidad_sucursal": 36.95,
     "sobrante_bodega": 0.0, "motivo": "reposicion"}
  ],
  "cubrir_con_traslado": [
    {"producto_id": "P3937", "nombre_producto": "ARROZ ZULIA *500 GR", "categoria": "Arroz",
     "necesidad": 2494.93, "necesidad_sucursal": 1183.14, "sobrante_bodega": 2757.0, "unidad": "unidad",
     "urgencia": "normal", "dias_hasta_agotarse": 15.0}
  ],
  "alertas": [
    {"producto_id": "00046", "nombre_producto": "SOFLAN SUAVITEL 2*970 ML", "categoria": "Aseo hogar",
     "sucursal": "PRINCIPAL", "tipo": "posible_inconsistencia_inventario", "stock": -1.0,
     "accion": "compra_urgente",
     "detalle": "Stock negativo en la foto: verificar el conteo. Se compra con el stock tomado como 0."}
  ],
  "no_encontrados": [],
  "resumen": {"productos": 986, "lineas": 814, "lineas_sucursal": 164, "lineas_bodega": 650,
              "cantidad": {"unidad": 30375, "kg": 1072}, "cantidad_directa": {"unidad": 6939, "kg": 1072},
              "cantidad_bodega": {"unidad": 23436, "kg": 0}, "necesidad_via_bodega": {"unidad": 19637.39, "kg": 0},
              "cubiertos_por_bodega": 172, "alertas": 95},
  "filtros_aplicados": {"sucursal": "PRINCIPAL", "sucursal_por_rol": false, "categoria": null, "urgencia": null},
  "calculado_en": "2026-10-01T14:15:02Z"
}
```

La línea de 00008 muestra la vista desde la sucursal (R1). En `ml_service`, la
compra de la Bodega es **urgente**, con 0 días: LA 21 tiene stock −1 y compra
con el stock tomado como 0. Desde PRINCIPAL la misma compra es **normal**: a
PRINCIPAL le quedan 10,5 días y de los 46,86 que se compran le tocan 36,95.
Con la foto actual, 70 líneas de la Bodega cambian de urgencia al mirarlas
desde PRINCIPAL.

### `GET /api/ml/recomendaciones/transferencias`

Llama a `POST /api/transferencias` sin lista de productos y con balance, y
guarda el resultado en la caché.

**Parámetro propio:** `incluir_balance` (booleano, `false` por defecto, C4).
Con `false` no viene `balance` y las alertas `sin_pronostico` no se listan;
el resumen las cuenta igual.

**Qué filtra cada parámetro**

| Lista | `sucursal=X` | `categoria` | `urgencia` |
| --- | --- | --- | --- |
| `traslados` | `origen` = X o `destino` = X | Sí | Sí |
| `balance` | `sucursal` = X | Sí | Sí; las filas con urgencia nula quedan fuera |
| `alertas` | `sucursal` = X | Sí | No (R2) |

`fecha_inventario`, `fecha_pronostico`, `horizonte_dias` y `politicas` pasan
sin cambios. `no_encontrados` siempre llega vacía.

**Resumen**

| Campo | Cálculo sobre las filas que pasan los filtros |
| --- | --- |
| `productos` | Productos distintos en `traslados` y `balance` (aunque el balance no se liste) |
| `traslados` | Filas de `traslados` |
| `cantidad_trasladada` | `{unidad, kg}`: suma de `cantidad` de los traslados |
| `filas_balance` | Filas del balance, se listen o no |
| `deficit_total`, `deficit_neto`, `excedente_sin_destino` | `{unidad, kg}`: suma de esos campos del balance |
| `alertas` | Filas de `alertas` que se listan |
| `alertas_stock_negativo`, `alertas_sin_pronostico` | Conteo de cada tipo, se listen o no |

**Ejemplo** con datos reales, como gerente:
`GET /api/ml/recomendaciones/transferencias?sucursal=LA%2021`. Se muestra uno de
los 10 traslados y una de las 40 alertas.

```json
{
  "fecha_inventario": "2025-12-31",
  "fecha_pronostico": "2025-12-31",
  "horizonte_dias": 15,
  "politicas": {"version": 1, "fecha": "2026-09-30"},
  "traslados": [
    {"producto_id": "P4003", "nombre_producto": "GELATINAS FRUIT JELLY UND", "categoria": "Repostería",
     "origen": "GLORIETA", "destino": "LA 21", "cantidad": 16, "unidad": "unidad", "urgencia": "urgente",
     "dias_hasta_agotarse": 2.7, "fecha_llegada": "2026-01-03", "dias_habiles_llegada": 2, "llega_tarde": false}
  ],
  "alertas": [
    {"producto_id": "00008", "nombre_producto": "AGUA CRISTAL LITRO SPORT", "categoria": "Bebidas",
     "sucursal": "LA 21", "tipo": "stock_negativo", "stock": -1.0, "accion": "pedido_urgente",
     "detalle": "Stock negativo en la foto: verificar el conteo. No se traslada y para el pedido se toma como 0."}
  ],
  "no_encontrados": [],
  "resumen": {"productos": 2073, "traslados": 10, "cantidad_trasladada": {"unidad": 150, "kg": 0},
              "filas_balance": 2073, "deficit_total": {"unidad": 2344.81, "kg": 1075.07},
              "deficit_neto": {"unidad": 2232.81, "kg": 1075.07},
              "excedente_sin_destino": {"unidad": 4396.82, "kg": 0.73},
              "alertas": 40, "alertas_stock_negativo": 40, "alertas_sin_pronostico": 697},
  "filtros_aplicados": {"sucursal": "LA 21", "sucursal_por_rol": false, "categoria": null, "urgencia": null},
  "calculado_en": "2026-10-01T14:15:40Z"
}
```

Con `incluir_balance=true` llega además `balance`. Por ejemplo, la fila de
P4003 en LA 21: stock 8, q50 45,23, déficit 37,23, recibe 16 de GLORIETA,
déficit neto 21,23, estado `destino` y urgencia `urgente`. También se listan
las 697 alertas `sin_pronostico` de LA 21.

## Caché (C3)

1. En cada petición, el Core API consulta `GET /api/health` de `ml_service`. Es una llamada rápida y devuelve la fecha de la foto y las versiones de las políticas.
2. La clave es `(endpoint, fecha_inventario, versión INV-21, versión INV-22)`. Si la clave está en la caché y no venció `ML_CACHE_TTL_SEGUNDOS`, se filtra sobre lo guardado.
3. Si no está, se llama al POST completo, se enriquece con `dim_producto` y se guarda. Un candado por clave hace que las peticiones simultáneas esperen un solo cálculo.
4. Una respuesta con error no se guarda. Si `health` falla o dice `degradado`, la petición responde 503.

El TTL, de 6 horas por defecto, cubre lo que la clave no ve: por ejemplo, un
modelo reentrenado sin cambiar la foto ni las políticas. La caché vive en el
proceso del Core API, así que un reinicio (o un `--reload` en desarrollo) la
vacía.

**Cambio en `ml_service`.** `GET /api/health` agrega dos campos y no cambia
los que ya tiene:

| Campo | Tipo | Significado |
| --- | --- | --- |
| `fecha_inventario` | fecha o `null` | La foto que usan `/api/transferencias` y `/api/compras`; `null` sin conexión a la bodega |
| `politicas` | objeto | `{"inv21": {version, fecha}, "inv22": {version, fecha}}`, las cargadas al arrancar |

## Cliente hacia `ml_service` (C5)

| Configuración (`api/core/config.py`) | Por defecto | En Docker Compose |
| --- | --- | --- |
| `ML_SERVICE_URL` | `http://localhost:8001` | `http://ml-service:8001` |
| `ML_SERVICE_TIMEOUT_SEGUNDOS` | 120 | — |
| `ML_CACHE_TTL_SEGUNDOS` | 21600 (6 h) | — |

En `docker-compose.yml`, el servicio `api` recibe `ML_SERVICE_URL` y espera a
que `ml-service` esté sano (`depends_on` con `service_healthy`).

## Criterios de aceptación

Reemplazan los nueve del borrador.

1. `GET /api/ml/recomendaciones/compras` devuelve todos los campos de `POST /api/compras` del catálogo completo, más `nombre_producto` y `categoria` en cada fila, `filtros_aplicados`, `calculado_en` y su propio `resumen` (C6).
2. `GET /api/ml/recomendaciones/transferencias` hace lo mismo sobre `POST /api/transferencias`. El balance solo llega con `incluir_balance=true`; las alertas `sin_pronostico` solo se listan en ese caso y siempre se cuentan (C4).
3. Los dos exigen token y aplican los permisos por rol de C1.
4. En compras, `sucursal=X` devuelve las líneas directas y las de la Bodega donde X participa, vistas desde X, con `necesidad_sucursal` (C2, R1).
5. En transferencias, `sucursal=X` filtra los traslados por origen o destino, y el balance y las alertas por sucursal.
6. `categoria` y `sucursal` se normalizan; un valor desconocido responde 422 y una combinación válida sin filas, 200 con listas vacías (R3).
7. `urgencia` filtra por coincidencia exacta con los valores de cada endpoint y no se aplica a las alertas (R2).
8. Los filtros son opcionales y se combinan con AND. Sin filtros, las listas son las de `ml_service` y cada total del resumen coincide con el suyo (R4).
9. El resumen cuadra con las filas devueltas en todos los casos (R4).
10. La caché sigue C3: con la caché caliente, una segunda llamada no consulta los POST de `ml_service` y tarda menos de 1 s; si cambia la foto o una versión de políticas, recalcula.
11. Los errores de `ml_service` se traducen según la tabla de errores y no se guardan en la caché (R5).
12. `ml_service` solo cambia en `/api/health`, con dos campos nuevos. `/api/predict`, `/api/transferencias` y `/api/compras` no cambian y sus pruebas siguen pasando.
13. El Swagger del Core API documenta los dos endpoints, sus parámetros opcionales con los valores permitidos y los campos de la respuesta.

## Casos de prueba y Definition of Done

Las pruebas unitarias (nuevas, con pytest en `api/tests/`) no usan ni Postgres
ni `ml_service`. Reemplazan el usuario autenticado y el catálogo con
dependencias de prueba, y `ml_service` con un transporte falso de `httpx`
que devuelve respuestas con la forma real. La cobertura mínima es 80 % sobre
`api/ml/`.

| Caso | Resultado esperado |
| --- | --- |
| Sin filtros | Las listas de `ml_service` con nombre y categoría; resumen igual al suyo |
| Sin token / token inválido | 403 / 401 |
| `admin_sucursal` sin `sucursal` | Su sucursal; `sucursal_por_rol = true` |
| `admin_sucursal` con su sucursal / con otra | 200 / 403 |
| `gerente` y `admin_bodega` con cualquier sucursal | 200 |
| Compras con `sucursal=X` | Directas a X y líneas de la Bodega donde X participa; detalle solo con X; urgencia y `necesidad_sucursal` de X |
| Compras con `sucursal=BODEGA_CENTRAL` | Solo líneas de la Bodega, con detalle completo; todo `cubrir_con_traslado` |
| Línea de la Bodega más urgente en otra sucursal | Con `sucursal=X`, la urgencia es la de X; sin filtro, la de la línea |
| Transferencias con `sucursal=X` | Traslados con X como origen o destino |
| `categoria=lacteos` y `categoria= LÁCTEOS ` | Ambos filtran "Lácteos" |
| `sucursal=la 21` | Filtra LA 21 |
| Sucursal o categoría desconocida, SIN_SUCURSAL | 422 |
| `urgencia=vigilancia` en compras / en transferencias | 422 / filtra |
| `urgencia` con alertas | Las alertas no se filtran por urgencia |
| Balance con urgencia nula y filtro de urgencia | La fila no pasa |
| Los tres filtros juntos | Intersección (AND) |
| Combinación válida sin filas | 200, listas vacías y resumen en cero |
| `incluir_detalle=false` | Sin `detalle` en compras ni en `cubrir_con_traslado`; los filtros por sucursal funcionan igual |
| `incluir_balance=false` / `true` | Sin balance y sin alertas `sin_pronostico` listadas, pero contadas / con ambas |
| Kilos | Las cantidades en kg van a `kg` del resumen, nunca a `unidad` |
| Producto sin fila en `dim_producto` | `nombre_producto` y `categoria` en `null`; no pasa el filtro `categoria` |
| Caché: dos llamadas | Un solo POST a `ml_service` |
| Caché: otra fecha de foto u otra versión de políticas | Nuevo POST |
| Caché: peticiones simultáneas | Un solo POST |
| `ml_service` responde 409 / 503 / 500 | 409 con su detalle / 503 / 502; nada se guarda |
| `ml_service` caído / lento / `health` degradado | 503 / 504 / 503 |

**Integración** (marca `integracion`; se salta si no hay `ml_service` ni Postgres)

- Las cifras de "Resultados esperados", con `ml_service` y la bodega reales.
- P1632 llega como "HUEVOS *UND" y 00008, desde PRINCIPAL, como `normal` y `necesidad_sucursal` 36,95.
- La segunda llamada con la caché caliente tarda menos de 1 s.

**Definition of Done**

- [ ] Cumple los 13 criterios de aceptación.
- [ ] Pruebas unitarias con cobertura ≥ 80 % en `api/ml/`, incluidos los casos de la tabla.
- [ ] Pruebas de `ml_service` pasando, con la de `/api/health` actualizada.
- [ ] Autorrevisión documentada en el commit o PR.
- [ ] `docs/INV-23-recomendaciones.md` con la implementación; `docs/ML-SERVICE-API.md` con los campos nuevos de `/api/health`.
- [ ] Integrado en `develop`.
- [ ] Verificado con Docker Compose local (`postgres`, `ml-service` y `api`), con los usuarios de prueba.
- [ ] Swagger verificado contra una llamada real a `ml_service`.
- [ ] Resumen filtrado cuadrado con las filas devueltas en al menos dos escenarios.
- [ ] Sin bugs bloqueantes.

## Resultados esperados con los datos reales

Calculados con un prototipo de los filtros sobre las respuestas reales de
`ml_service` (foto al 2025-12-31). La implementación debe confirmarlos.

**Compras**

| Consulta | Resultado |
| --- | --- |
| Sin filtros | 1.340 líneas (449 directas, 891 para la Bodega); 41.952 unidades y 3.169 kg; 277 en `cubrir_con_traslado`; 220 alertas; 1.411 productos |
| `sucursal=PRINCIPAL` | 814 líneas (164 + 650); necesidad vía Bodega 19.637,39 unidades; 172 en `cubrir_con_traslado`; 95 alertas |
| `sucursal=LA 21` | 337 líneas (126 + 211); 55 en `cubrir_con_traslado`; 40 alertas |
| `sucursal=GLORIETA` | 562 líneas (159 + 403); 111 en `cubrir_con_traslado`; 70 alertas |
| `sucursal=BODEGA_CENTRAL` | 891 líneas (27.098 unidades); 277 en `cubrir_con_traslado`; 15 alertas |
| `sucursal=PRINCIPAL&urgencia=urgente` | 296 líneas (64 + 232); 27 en `cubrir_con_traslado`; 95 alertas (la urgencia no las filtra) |
| `categoria=lacteos` | Lácteos: 215 líneas (200 + 15), 2.743 unidades; 2 en `cubrir_con_traslado`; 26 alertas |
| `sucursal=GLORIETA&categoria=arroz&urgencia=urgente` | 2 líneas de la Bodega: P1938 (4) y P4570 (20) |
| `categoria=Anchetas&urgencia=urgente` | 200, todo vacío y resumen en cero |

**Transferencias**

| Consulta | Resultado |
| --- | --- |
| Sin filtros | 119 traslados (4.623 unidades); 11.710 filas de balance; déficit 18.772,5 unidades + 1.904,68 kg (= 20.677,18 de `ml_service`); 220 alertas listadas y 2.762 `sin_pronostico` contadas; 4.419 productos |
| `sucursal=LA 21` | 10 traslados (150 unidades): 8 llegan a LA 21 (5 desde la Bodega y 3 desde otras sucursales) y 2 salen de LA 21 hacia PRINCIPAL; 2.073 filas de balance; 40 alertas; 697 `sin_pronostico` |
| `sucursal=BODEGA_CENTRAL` | 109 traslados (4.479 unidades); 1.973 filas de balance; 15 alertas |
| `categoria=arroz` | 12 traslados (2.382 unidades), entre ellos P3937: 572 a GLORIETA y 695 a PRINCIPAL |
| `urgencia=vigilancia&incluir_balance=true` | 0 traslados y 44 filas de balance |

**Tamaño de las respuestas** (enriquecidas): transferencias sin balance, 0,1 MB;
con balance, 6,8 MB, o 1,3 MB filtrada por LA 21; compras de PRINCIPAL con
detalle, 0,7 MB.

## Pendientes de confirmar

Ninguno bloquea el desarrollo.

| # | Pregunta | Valor por defecto mientras tanto |
| --- | --- | --- |
| 1 | ¿Filtro por producto, para el agente NLP (INV-32)? | No en esta historia |
| 2 | ¿Filtro por rama de demanda? | No; se agrega si el dashboard lo pide |
| 3 | ¿Refrescar la caché a mano (por ejemplo, un endpoint para el gerente)? | No; se refresca sola con una foto o políticas nuevas, con el TTL o reiniciando la API |
| 4 | ¿Paginación? | No; los tamaños medidos son manejables, salvo el balance completo, que es opcional |

## Ambiente de desarrollo

1. Crear la rama desde `develop` actualizado: `git checkout -b feature/INV-23-recomendaciones`.
2. Usuarios de prueba: aplicar el seed de usuarios en la base local (`app.usuarios` está vacía) y comprobar el login de los 5.
3. Levantar con `docker compose up -d --build ml-service api`.
4. Pruebas:
   - `docker compose exec api pytest --cov=ml` (unitarias);
   - `docker compose exec api pytest -m integracion`;
   - en `ml_service/`, `pytest` (incluida la de `/api/health`).
5. Probar con un token:

   ```
   $t = (Invoke-RestMethod http://localhost:8000/api/auth/login -Method Post -ContentType "application/json" -Body '{"email":"gerente@inventaio.co","password":"admin123"}').access_token
   Invoke-RestMethod "http://localhost:8000/api/ml/recomendaciones/compras?sucursal=PRINCIPAL&incluir_detalle=false" -Headers @{Authorization="Bearer $t"}
   ```
6. Comprobar que `/api/predict`, `/api/transferencias` y `/api/compras` responden igual que antes.

**Archivos a crear o tocar**

| Archivo | Cambio |
| --- | --- |
| `api/ml/cliente.py` (nuevo) | Llamadas a `ml_service` y traducción de errores (C5, R5) |
| `api/ml/cache.py` (nuevo) | Caché en memoria con clave, TTL y candado (C3) |
| `api/ml/catalogo.py` (nuevo) | Productos, categorías y sucursales de `dw` |
| `api/ml/filtros.py` (nuevo) | Filtros, vista desde la sucursal y resumen; funciones puras, sin I/O |
| `api/ml/router.py` (nuevo) | Los dos GET y los permisos por rol (C1) |
| `api/schemas/recomendaciones.py` (nuevo) | Esquemas Pydantic de las respuestas |
| `api/core/config.py`, `api/main.py` | Configuración y registro del router |
| `api/requirements.txt` | `pytest-cov` |
| `api/tests/conftest.py`, `api/tests/test_recomendaciones_*.py` (nuevos) | Pruebas unitarias y de integración |
| `docker-compose.yml` | `ML_SERVICE_URL` y `depends_on` del servicio `api` |
| `ml_service/main.py` y su prueba | `fecha_inventario` y `politicas` en `/api/health` |
| `docs/INV-23-recomendaciones.md` (nuevo), `docs/ML-SERVICE-API.md`, `docs/AMBIENTE-DESARROLLO.md` | Documentación |

El CI no cambia: sigue corriendo ruff sobre `api/` y el build del frontend.

## Riesgos y limitaciones

- **Primera llamada lenta.** Con la caché vacía, compras tarda unos 22 s y transferencias unos 36 s (con balance, que se pide siempre para poder resumir). Pasa después de cada reinicio de la API y cuando cambia la foto. El frontend debe esperar al menos 60 s.
- **Caché por proceso.** Con varios workers, cada uno tendría la suya. Hoy la API corre con un solo proceso.
- **Memoria.** La caché guarda las dos respuestas completas enriquecidas (unos 8 MB en JSON, varias veces eso como objetos de Python).
- **Vista desde la sucursal.** Una misma compra de la Bodega puede verse urgente sin filtro y normal desde una sucursal (70 líneas en PRINCIPAL). El dashboard debe explicar que la urgencia es la de la sucursal filtrada.
- **Contratos acoplados.** Si cambia el contrato de `ml_service`, hay que ajustar los esquemas del Core API. Las pruebas de integración lo detectan.
- **Resto del Core API.** Otras rutas del Core API todavía asumen la bodega simulada. No se tocan aquí, pero conviven en el mismo Swagger.
