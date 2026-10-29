# ML Service — campos de entrada y salida

Referencia del contrato HTTP de `ml_service` (versión 1.3.0): qué recibe y qué
devuelve cada endpoint, campo por campo. Está pensada para quien consume el
servicio (`api/`, frontend, dashboard). Las decisiones de diseño y los
algoritmos están en [`INV-20-ml-service.md`](INV-20-ml-service.md) (predicción),
[`INV-22-transferencias.md`](INV-22-transferencias.md) (transferencias) e
[`INV-21-compras.md`](INV-21-compras.md) (compras).

| Endpoint | Para qué |
| --- | --- |
| `GET /api/health` | Estado del servicio, de los modelos y de la conexión a la bodega |
| `POST /api/predict` | Demanda de un producto en una sucursal para los próximos 15 días hábiles |
| `POST /api/transferencias` | Traslados sugeridos desde la Bodega Central y entre sucursales, y déficit neto para compras |
| `POST /api/compras` | Compras sugeridas a proveedor para lo que los traslados no cubren |

Documentación interactiva (se genera del código): http://localhost:8001/api/docs
y http://localhost:8001/api/redoc. El esquema OpenAPI está en `/api/openapi.json`.

## Convenciones

- **JSON en UTF-8** en la petición y en la respuesta (`Content-Type: application/json`).
- **Productos y sucursales por clave de negocio.** El producto es su `codigo_item`
  (`"P1632"`, `"00875"`) y la sucursal es su nombre (`"PRINCIPAL"`, `"LA 21"`,
  `"GLORIETA"`, `"BODEGA_CENTRAL"`). Los códigos numéricos van **como texto,
  con sus ceros**: `"00070"`, no `70`.
- **Sucursales físicas.** Los modelos solo conocen PRINCIPAL, LA 21 y
  GLORIETA (tipos `principal` y `estandar` en `dw.dim_sucursal`). La Bodega
  Central no tiene pronóstico: solo despacha.
- **Días hábiles.** En la historia son los días con al menos una venta en el
  negocio. Después del último dato son los de `dw.dim_tiempo`, sin los cierres
  programados (1 de enero y Viernes Santo). El horizonte siempre es de 15 días hábiles.
- **Cantidades** en la unidad de venta del producto: unidades o, si el producto
  se vende por kilo, kilos. `/api/transferencias` lo dice en el campo `unidad`.
  `/api/predict` no lo dice, y su `interpretacion` siempre escribe "unidades".
- **Redondeo.** Pronósticos y déficits llevan 2 decimales, días hasta agotarse
  1 decimal, y las cantidades a trasladar son enteras.
- **Fechas** en formato ISO `AAAA-MM-DD`.
- **Campos nulos.** Un campo que no aplica llega como `null`, no se omite. Las
  excepciones son `balance` en `/api/transferencias`, que desaparece con
  `incluir_balance: false`, y `detalle` en `/api/compras`, que desaparece con
  `incluir_detalle: false`.

### Formato de los errores

Hay dos formatos, según quién detecta el error:

```json
// 1. El servicio rechaza la petición (404, 409, 503 y algunos 422): detail es un texto
{"detail": "Producto no encontrado en la bodega: NOEXISTE"}

// 2. El cuerpo no cumple el esquema (422 de validación): detail es una lista
{"detail": [{"type": "too_short", "loc": ["body", "productos"],
             "msg": "List should have at least 1 item after validation, not 0",
             "input": [], "ctx": {"field_type": "List", "min_length": 1, "actual_length": 0}}]}
```

En el segundo formato, `loc` indica el campo con problema y `type` el tipo de error
(`missing`, `too_short`, `list_type`, `bool_parsing`, `int_parsing`,
`json_invalid`, `value_error`...).

---

## GET /api/health

No recibe parámetros y responde siempre **200**, aunque la bodega esté caída.
Para saber si el servicio puede atender peticiones, hay que mirar `status`.

| Campo | Tipo | Significado |
| --- | --- | --- |
| `status` | `"ok"` \| `"degradado"` | `degradado` si no hay conexión a Postgres. En ese caso `/api/predict` y `/api/transferencias` responden 503 |
| `service` | string | Siempre `"inventaio-ml-service"` |
| `modelos_cargados` | lista de string | Ramas del modelo cargadas al arrancar: `intermitente`, `suave_no_perecedero`, `suave_perecedero`. Si falta un modelo, el servicio no arranca |
| `bodega` | `"ok"` \| `"sin conexión"` | Resultado de un `SELECT 1` contra Postgres |
| `fecha_inventario` | fecha (`"AAAA-MM-DD"`) o `null` | La foto que usan `/api/transferencias` y `/api/compras`. `null` sin conexión a la bodega o con `dw.fact_inventario` vacía |
| `politicas` | objeto | `{"inv21": {version, fecha}, "inv22": {version, fecha}}`: las políticas cargadas al arrancar |

`fecha_inventario` y `politicas` se agregaron en INV-23: el Core API arma con
ellos la clave de su caché de recomendaciones (ver
[`INV-23-recomendaciones.md`](INV-23-recomendaciones.md)).

```json
{"status": "ok", "service": "inventaio-ml-service",
 "modelos_cargados": ["intermitente", "suave_no_perecedero", "suave_perecedero"], "bodega": "ok",
 "fecha_inventario": "2025-12-31",
 "politicas": {"inv21": {"version": 1, "fecha": "2026-09-30"}, "inv22": {"version": 1, "fecha": "2026-09-30"}}}
```

---

## POST /api/predict

Pronostica la demanda **acumulada** de un producto en una sucursal física para
los próximos 15 días hábiles. Las features se calculan en cada petición con los
datos de la bodega.

### Entrada

| Campo | Tipo | Obligatorio | Significado |
| --- | --- | --- | --- |
| `producto_id` | string | Este o `id_producto` | Código de negocio del producto (`codigo_item`), p. ej. `"P1632"` |
| `id_producto` | entero | Este o `producto_id` | `dw.dim_producto.id_producto`, el `SERIAL` que usa `api/` |
| `sucursal_id` | string | Este o `id_sucursal` | Nombre exacto de la sucursal: `"PRINCIPAL"`, `"LA 21"` o `"GLORIETA"` |
| `id_sucursal` | entero | Este o `sucursal_id` | `dw.dim_sucursal.id_sucursal` |
| `horizonte` | entero | Sí | Días hábiles del pronóstico. Solo se acepta `15` |
| `fecha_corte` | fecha | No | Fecha de los datos con que se predice. Por defecto es el último día con ventas en la bodega. Una fecha anterior reproduce lo que el modelo habría dicho ese día |

Si llegan el código y el id, manda el código (`producto_id` sobre
`id_producto`, `sucursal_id` sobre `id_sucursal`).

### Salida (200)

| Campo | Tipo | Significado |
| --- | --- | --- |
| `producto_id` | string | `codigo_item` del producto. Llega aunque la petición haya usado `id_producto` |
| `id_producto` | entero | `id_producto` del producto |
| `sucursal_id` | string | Nombre de la sucursal |
| `id_sucursal` | entero | `id_sucursal` de la sucursal |
| `horizonte_dias` | entero | El horizonte pedido (15) |
| `rama` | string | Modelo que hizo el pronóstico, según el patrón de venta del par (ver tabla de ramas) |
| `prediccion_q50` | número | **Mediana** de la demanda acumulada en los 15 días hábiles: la mitad de las veces se vende menos y la otra mitad más. Es la cifra central del pronóstico |
| `intervalo_confianza.limite_inferior` | número | Siempre `0.0`. No hay un modelo para el cuantil bajo |
| `intervalo_confianza.limite_superior` | número | Cuantil de negocio (qα) de la demanda acumulada. Con `alpha_negocio` 0,893 es una cobertura con margen de seguridad. Con 0,167 es un cuantil bajo, **menor que el q50** a propósito |
| `intervalo_confianza.alpha_negocio` | número | Cuantil que representa `limite_superior`. Se calculó con los costos de faltante y sobrante validados por el negocio |
| `interpretacion` | string | Frase corta en lenguaje directo, generada con reglas fijas a partir de los números anteriores (no es un modelo de lenguaje) |
| `fecha_features` | fecha | Fecha de los datos con que se calculó el pronóstico: el último día hábil en o antes de `fecha_corte` (o del último dato) |
| `modelo_entrenado_en` | string (fecha y hora ISO) o `null` | Cuándo se generaron los modelos (`fecha_generacion` de `models/nivel1_metadata.json`) |

**Ramas del modelo**

| `rama` | Cuándo | `alpha_negocio` | Cómo leer `limite_superior` |
| --- | --- | --- | --- |
| `intermitente` | Todo patrón de venta que no es suave: esporádico, errático o con muchos días sin venta (98,6 % de los pares del catálogo) | 0,893 | Cobertura recomendada, por encima del q50 |
| `suave_no_perecedero` | Venta frecuente y regular (ADI y CV² bajo sus cortes) y el producto no es perecedero | 0,893 | Cobertura recomendada, por encima del q50 |
| `suave_perecedero` | Venta frecuente y regular y el producto es perecedero | 0,167 | Cuantil bajo para evitar merma. **No es una cota de reposición** (la `interpretacion` lo advierte) |

### Códigos de respuesta

| Código | Cuándo | `detail` (ejemplo) |
| --- | --- | --- |
| 200 | Pronóstico calculado | — |
| 404 | El producto no existe | `Producto no encontrado en la bodega: NOEXISTE` |
| 404 | La sucursal no existe | `Sucursal no encontrada en la bodega: MARTE` |
| 404 | El par no tiene historia suficiente: menos de 30 días con venta o menos de 30 días hábiles de historia | `No hay historia suficiente para producto_id=00070, sucursal_id=GLORIETA: 20 días con venta hasta 2025-12-31 (el modelo exige al menos 30)` |
| 422 | `horizonte` distinto de 15 | `Los modelos solo predicen demanda acumulada a 15 días hábiles -- horizonte=30 no está soportado sin reentrenar.` |
| 422 | Sucursal no física (`BODEGA_CENTRAL`, `SIN_SUCURSAL`) | `La sucursal BODEGA_CENTRAL (bodega_central) no es una sucursal física: ...` |
| 422 | `fecha_corte` posterior al último dato | `fecha_corte=2027-01-01 es posterior al último dato de la bodega (2025-12-31).` |
| 422 | Falta el producto o la sucursal, o un campo tiene un tipo inválido | Formato de validación (lista), p. ej. `indicar producto_id (codigo_item) o id_producto` |
| 503 | Bodega caída o vacía, o `dim_tiempo` sin días suficientes para el horizonte | `Bodega de datos no disponible: ...` |

### Ejemplos

```json
// Petición
{"producto_id": "P1632", "sucursal_id": "PRINCIPAL", "horizonte": 15}
// Petición equivalente, por id y con fecha de corte
{"id_producto": 91, "id_sucursal": 1, "horizonte": 15, "fecha_corte": "2025-06-30"}

// Respuesta (rama intermitente)
{"producto_id": "P1632", "id_producto": 91, "sucursal_id": "PRINCIPAL", "id_sucursal": 1,
 "horizonte_dias": 15, "rama": "intermitente", "prediccion_q50": 3366.01,
 "intervalo_confianza": {"limite_inferior": 0.0, "limite_superior": 4608.72, "alpha_negocio": 0.893},
 "interpretacion": "Demanda intermitente. Proyección: 3.366 unidades en 15 días hábiles. Cobertura recomendada: hasta 4.609 unidades.",
 "fecha_features": "2025-12-31", "modelo_entrenado_en": "2026-09-25T01:30:56.264497+00:00"}

// Respuesta (rama suave_perecedero): el límite superior queda por debajo del q50
{"producto_id": "P1632", "sucursal_id": "GLORIETA", "rama": "suave_perecedero", "prediccion_q50": 3871.25,
 "intervalo_confianza": {"limite_inferior": 0.0, "limite_superior": 3094.03, "alpha_negocio": 0.167},
 "interpretacion": "Demanda estable, producto perecedero. Proyección: 3.871 unidades en 15 días hábiles. El límite superior no incluye margen de seguridad: el modelo evita sobre-stock para reducir merma. No usar como cota de reposición.", "...": "..."}
```

---

## POST /api/transferencias

Recomienda traslados de stock desde la Bodega Central y entre sucursales
físicas **antes** de comprar a proveedor. Parte de la foto de inventario más
reciente (`dw.fact_inventario`) y del mismo pronóstico de `/api/predict`. Las
reglas salen del archivo de políticas versionado
(`ml_service/transferencias/politicas_inv22.json`).

### Entrada

Los dos campos son opcionales. El cuerpo `{}` procesa todo el catálogo.

| Campo | Tipo | Por defecto | Significado |
| --- | --- | --- | --- |
| `productos` | lista de string (al menos uno) | Todo el catálogo | Códigos `codigo_item` a procesar. Sin la lista se procesan todos los productos con fila en la foto (unos 4.400, alrededor de 20 s). Un código que no existe va a `no_encontrados`, sin error. Un código repetido se procesa una vez |
| `incluir_balance` | booleano | `true` | Con `false` la respuesta no trae `balance`. Conviene para el catálogo completo si solo se necesitan los traslados |

### Salida (200): nivel superior

| Campo | Tipo | Significado |
| --- | --- | --- |
| `fecha_inventario` | fecha | Fecha de la foto de `dw.fact_inventario` que se usó (la más reciente) |
| `fecha_pronostico` | fecha | Fecha de los datos del pronóstico: el último día hábil en o antes de la foto |
| `horizonte_dias` | entero | 15 |
| `politicas.version` | entero | Versión del archivo de políticas que se usó |
| `politicas.fecha` | fecha | Fecha de esa versión |
| `traslados` | lista | Los traslados sugeridos (ver abajo), del más urgente al menos urgente |
| `balance` | lista | Una fila por producto y ubicación (ver abajo). No viene con `incluir_balance: false` |
| `alertas` | lista | Stock negativo y pares sin pronóstico (ver abajo) |
| `no_encontrados` | lista de string | Códigos pedidos que no existen en `dw.dim_producto`, sin repetir y en el orden de la petición |
| `resumen` | objeto | Totales de la corrida (ver abajo) |

### `traslados[]`: un movimiento sugerido de un origen a un destino

| Campo | Tipo | Significado |
| --- | --- | --- |
| `producto_id` | string | `codigo_item` del producto |
| `origen` | string | De dónde sale: `BODEGA_CENTRAL` o una sucursal con excedente. Siempre se usa primero la Bodega |
| `destino` | string | A qué sucursal llega. Nunca es la Bodega Central |
| `cantidad` | entero | Cantidad a mover, redondeada hacia abajo y nunca menor que el mínimo (6). En kilos ya tiene descontado el 10 % de pérdida |
| `unidad` | `"unidad"` \| `"kg"` | `kg` si el producto se vende por kilo (`dim_producto.se_vende_por_kilo`) |
| `urgencia` | `"urgente"` \| `"alta"` \| `"normal"` \| `"vigilancia"` | La urgencia del **destino**, según los días que le quedan (ver tabla de urgencia) |
| `dias_hasta_agotarse` | número o `null` | Días hábiles hasta que el destino se quede sin stock si no recibe el traslado: stock ÷ (q50 ÷ 15). `null` si el destino está en vigilancia |
| `fecha_llegada` | fecha | Cuándo llega el traslado: 2 días hábiles después de la foto, o el siguiente día fijo de salida si las políticas los definen |
| `dias_habiles_llegada` | entero | Días hábiles entre la foto y la llegada |
| `llega_tarde` | booleano | `true` si el destino se agota antes de que llegue el traslado (`dias_hasta_agotarse` menor que `dias_habiles_llegada`). El traslado se sugiere igual |

**Urgencia**

| Valor | Regla (días hábiles hasta agotarse) |
| --- | --- |
| `urgente` | 5 o menos |
| `alta` | Más de 5 y hasta 10 |
| `normal` | Más de 10 |
| `vigilancia` | El q50 de la sucursal es 0: no se espera venta, así que no se calcula |

Los umbrales (5 y 10) se ajustan en el archivo de políticas.

### `balance[]`: la situación de un producto en una ubicación

Hay una fila por producto y ubicación. La Bodega Central aparece si tiene fila
en la foto. Una sucursal física aparece si tiene fila en la foto o pronóstico.
Una sucursal sin fila en la foto pero con pronóstico cuenta con stock 0.

| Campo | Tipo | Significado |
| --- | --- | --- |
| `producto_id` | string | `codigo_item` del producto |
| `sucursal` | string | Nombre de la ubicación, incluida `BODEGA_CENTRAL` |
| `tipo_ubicacion` | `"bodega_central"` \| `"sucursal"` | Tipo de ubicación |
| `rama` | string o `null` | Rama del modelo que pronosticó (como en `/api/predict`). `null` en la Bodega y en los pares sin pronóstico |
| `stock` | número | `stock_disponible` en la foto. Es 0 si la ubicación no tiene fila y puede ser negativo (ver `estado`) |
| `q50` | número o `null` | Mediana de la demanda en los 15 días hábiles. Es el mismo valor que devuelve `/api/predict` |
| `limite_superior` | número o `null` | Cuantil de negocio qα, igual al `limite_superior` de `/api/predict` |
| `objetivo` | número o `null` | Stock al que se busca llevar la sucursal: su q50 |
| `maximo` | número o `null` | Tope de stock antes de considerarlo excedente: max(qα × (1 + margen), q50). El margen es 0,50 en no perecederos y 0,25 en perecederos |
| `excedente` | número o `null` | Lo que la ubicación puede ceder: stock − max(máximo, 2) en una sucursal y todo el stock positivo en la Bodega. Nunca es negativo |
| `excedente_sin_destino` | número o `null` | Parte del excedente que no se envió y se queda en el origen: excedente − enviado |
| `deficit` | número o `null` | Lo que le falta para llegar al objetivo: max(0, q50 − stock). Con stock negativo, el stock se toma como 0 |
| `deficit_vigilancia` | número o `null` | Solo en `vigilancia`: lo que podría recibir si sobra, max(0, qα − stock). No se compra |
| `recibido` | entero | Total que llega en los traslados sugeridos |
| `enviado` | entero | Total que sale en los traslados sugeridos |
| `deficit_neto` | número o `null` | max(0, déficit − recibido): lo que queda por **comprar a proveedor**. Es la entrada de INV-21 |
| `estado` | string | Papel de la ubicación en el reparto (ver tabla de estados) |
| `urgencia` | string o `null` | Igual que en `traslados`, calculada sobre el stock actual (el negativo cuenta como 0) |
| `dias_hasta_agotarse` | número o `null` | stock ÷ (q50 ÷ 15), en días hábiles. `null` si el q50 es 0 o no hay pronóstico |
| `unidad` | `"unidad"` \| `"kg"` | Unidad de todas las cantidades de la fila |

**Estados y campos que llegan con valor**

| `estado` | Significado | Campos con valor (el resto llega en `null`) |
| --- | --- | --- |
| `bodega` | Bodega Central con stock ≥ 0: todo su stock puede salir | `stock`, `excedente`, `excedente_sin_destino`, `enviado` |
| `origen` | La sucursal tiene más que su máximo y puede enviar | Todos, salvo `deficit_vigilancia`. `excedente` es mayor que 0 y `deficit` es 0 |
| `destino` | La sucursal tiene menos que su objetivo y necesita recibir | Todos, salvo `deficit_vigilancia`. `excedente` es 0 y `deficit` es mayor que 0 |
| `equilibrio` | Está entre el objetivo y el máximo: no envía ni recibe | Todos, salvo `deficit_vigilancia`. `excedente` y `deficit` son 0 |
| `vigilancia` | Su q50 es 0: no envía y solo recibe si sobra. En perecederos, ni eso | `rama`, `q50` (0), `limite_superior`, `objetivo` (0), `deficit` (0), `deficit_vigilancia`, `recibido`, `deficit_neto` (0), `urgencia` (`vigilancia`) |
| `sin_pronostico` | El par no tiene historia suficiente: no participa y su stock no se cuenta como excedente. Genera una alerta | Solo `stock` |
| `stock_negativo` | La foto tiene stock negativo (error de conteo): no envía ni recibe. Genera una alerta | En una sucursal con pronóstico: `rama`, `q50`, `limite_superior`, `objetivo`, `deficit` (= q50, con el stock tomado como 0), `deficit_neto`, `urgencia` y `dias_hasta_agotarse` (0, así que la urgencia es `urgente`; si el q50 es 0, `vigilancia` y sin días). En la Bodega o sin pronóstico: solo `stock` |

`recibido` y `enviado` son siempre enteros, 0 si no aplican.

### `alertas[]`: casos que requieren atención y no generan traslados

| Campo | Tipo | Significado |
| --- | --- | --- |
| `producto_id` | string | `codigo_item` del producto |
| `sucursal` | string | Ubicación de la alerta (puede ser `BODEGA_CENTRAL`) |
| `tipo` | `"stock_negativo"` \| `"sin_pronostico"` | `stock_negativo`: la foto tiene stock menor que 0. `sin_pronostico`: la fila de la foto no tiene pronóstico |
| `stock` | número o `null` | Stock de la foto |
| `accion` | `"pedido_urgente"` \| `"ninguna"` | `pedido_urgente` en `stock_negativo`: compras debe cubrir el déficit completo. `ninguna` en `sin_pronostico` |
| `detalle` | string | Explicación en texto. En `sin_pronostico` dice el motivo, p. ej. `(25 días con venta hasta 2025-12-31 (el modelo exige al menos 30))` o `(sin ventas del producto en LA 21)` |

Solo generan alerta los pares con fila en la foto. Un par sin fila y sin
pronóstico no aparece en ningún lado, porque el negocio no lo maneja.

### `resumen`: totales de la corrida

| Campo | Tipo | Significado |
| --- | --- | --- |
| `productos` | entero | Productos procesados, sin contar `no_encontrados` ni repetidos |
| `traslados` | entero | Número de traslados sugeridos |
| `cantidad_trasladada` | entero | Suma de `cantidad` de los traslados. **Suma unidades y kilos juntos**: para separarlos hay que agrupar por `unidad` |
| `deficit_total` | número | Suma de `deficit` del balance, antes de los traslados |
| `deficit_neto` | número | Suma de `deficit_neto`: lo que sigue faltando después de los traslados y pasa a compras |
| `excedente_sin_destino` | número | Suma de `excedente_sin_destino`, incluida la Bodega |
| `alertas` | entero | Número de alertas |

`resumen` se calcula igual con `incluir_balance: false`.

### Códigos de respuesta

| Código | Cuándo | `detail` (ejemplo) |
| --- | --- | --- |
| 200 | Recomendación calculada, incluso si no sale ningún traslado | — |
| 409 | La foto de inventario es posterior a la última venta cargada: el pronóstico no tendría las ventas de esos días | `La foto de inventario (2026-01-05) es posterior a la última venta cargada (2025-12-31): faltan las ventas de 5 día(s). ...` |
| 422 | El cuerpo no cumple el esquema: lista vacía, `productos` que no es lista, `incluir_balance` no booleano o JSON mal formado | Formato de validación (lista) |
| 503 | Bodega caída, sin inventario cargado o con `dim_tiempo` insuficiente | `Bodega de datos no disponible: ...` |

### Ejemplo (arroz P3937, foto al 2025-12-31)

```json
// Petición
{"productos": ["P3937", "NOEXISTE"]}

// Respuesta (balance abreviado a dos filas)
{
  "fecha_inventario": "2025-12-31", "fecha_pronostico": "2025-12-31", "horizonte_dias": 15,
  "politicas": {"version": 1, "fecha": "2026-09-30"},
  "traslados": [
    {"producto_id": "P3937", "origen": "BODEGA_CENTRAL", "destino": "GLORIETA", "cantidad": 572, "unidad": "unidad",
     "urgencia": "urgente", "dias_hasta_agotarse": 4.6, "fecha_llegada": "2026-01-03", "dias_habiles_llegada": 2,
     "llega_tarde": false},
    {"producto_id": "P3937", "origen": "BODEGA_CENTRAL", "destino": "PRINCIPAL", "cantidad": 695, "unidad": "unidad",
     "urgencia": "alta", "dias_hasta_agotarse": 6.7, "fecha_llegada": "2026-01-03", "dias_habiles_llegada": 2,
     "llega_tarde": false}
  ],
  "balance": [
    {"producto_id": "P3937", "sucursal": "BODEGA_CENTRAL", "tipo_ubicacion": "bodega_central", "rama": null,
     "stock": 4024.0, "q50": null, "limite_superior": null, "objetivo": null, "maximo": null,
     "excedente": 4024.0, "excedente_sin_destino": 2757.0, "deficit": null, "deficit_vigilancia": null,
     "recibido": 0, "enviado": 1267, "deficit_neto": null, "estado": "bodega", "urgencia": null,
     "dias_hasta_agotarse": null, "unidad": "unidad"},
    {"producto_id": "P3937", "sucursal": "GLORIETA", "tipo_ubicacion": "sucursal", "rama": "intermitente",
     "stock": 256.0, "q50": 828.19, "limite_superior": 1458.95, "objetivo": 828.19, "maximo": 2188.42,
     "excedente": 0.0, "excedente_sin_destino": 0.0, "deficit": 572.19, "deficit_vigilancia": null,
     "recibido": 572, "enviado": 0, "deficit_neto": 0.19, "estado": "destino", "urgencia": "urgente",
     "dias_hasta_agotarse": 4.6, "unidad": "unidad"}
  ],
  "alertas": [],
  "no_encontrados": ["NOEXISTE"],
  "resumen": {"productos": 1, "traslados": 2, "cantidad_trasladada": 1267, "deficit_total": 1267.44,
              "deficit_neto": 0.44, "excedente_sin_destino": 2757.0, "alertas": 0}
}
```

Cómo se lee: la Bodega tiene 4.024 unidades de sobra. GLORIETA se agota en
4,6 días hábiles (urgente) y le faltan 572,19 para llegar a su mediana, así que
recibe 572. PRINCIPAL recibe 695. A compras solo pasan 0,44 unidades
(`deficit_neto`), y en la Bodega quedan 2.757.

---

## POST /api/compras

Recomienda compras a proveedor **después** de los traslados de
`/api/transferencias`, que corre por dentro con los mismos productos. Compra
cuando el stock, contando lo que llega por traslado, no alcanza, a la mediana,
hasta que llegue el pedido siguiente. En ese caso compra hasta el cuantil de
negocio de ese plazo. Las reglas salen de
`ml_service/compras/politicas_inv21.json`.

**Grupos y rutas.** Perecederos y productos con frío se piden cada martes,
directo a la sucursal (grupo `semanal`). Lo demás se pide los días 2 y 16 de
cada mes para la Bodega Central (grupo `quincenal`), en una línea por producto
que descuenta lo que la Bodega ya tiene.

### Entrada

Los dos campos son opcionales; `{}` procesa todo el catálogo (alrededor de 20 s).

| Campo | Tipo | Por defecto | Significado |
| --- | --- | --- | --- |
| `productos` | lista de string (al menos uno) | Todo el catálogo | Igual que en `/api/transferencias` |
| `incluir_detalle` | booleano | `true` | Con `false` las líneas de `compras` y `cubrir_con_traslado` no traen `detalle` |

### Salida (200): nivel superior

| Campo | Tipo | Significado |
| --- | --- | --- |
| `fecha_inventario`, `fecha_pronostico` | fecha | Como en `/api/transferencias` |
| `lead_time_dias` | entero | Días hábiles entre el pedido y su llegada (5) |
| `politicas.inv21`, `politicas.inv22` | objeto | Versión y fecha de los archivos de políticas de compras y de traslados |
| `calendario` | lista | Las fechas de cada grupo y ruta (ver abajo) |
| `compras` | lista | Las líneas de compra, de la más urgente a la menos urgente |
| `cubrir_con_traslado` | lista | Productos que necesitan reposición pero la Bodega ya la tiene: no se compran |
| `alertas` | lista | Stock negativo en la foto |
| `no_encontrados` | lista de string | Como en `/api/transferencias` |
| `resumen` | objeto | Totales de la corrida |

### `calendario[]`: fechas de un grupo por una ruta

| Campo | Tipo | Significado |
| --- | --- | --- |
| `grupo` | `"quincenal"` \| `"semanal"` | Días 2 y 16 del mes, o cada martes |
| `tipo_destino` | `"bodega_central"` \| `"sucursal"` | A la Bodega o directo a la sucursal |
| `fecha_pedido` | fecha | Cuándo sale el pedido: la primera fecha fija en o después de la foto (si cae en cierre, el siguiente día hábil) |
| `fecha_llegada` | fecha | Llegada al destino de la compra: `lead_time_dias` días hábiles después del pedido |
| `fecha_llegada_sucursal` | fecha | Llegada a la sucursal. Por la Bodega, con el traslado de INV-22 (2 días hábiles más) |
| `pedido_siguiente` | fecha | El pedido que sigue al actual |
| `cubre_hasta` | fecha | Cuándo llega a la sucursal el pedido siguiente: hasta ahí debe alcanzar lo que se compra hoy |
| `dias_cubiertos` | entero | Plazo P en días hábiles desde la foto hasta `cubre_hasta` |
| `dias_hasta_llegada` | entero | Días hábiles desde la foto hasta `fecha_llegada_sucursal` |

Con la foto al 2025-12-31: el quincenal pide el 2 de enero (llega el 7 a la
Bodega y el 9 a la sucursal) y cubre 22 días hábiles, hasta el 23. El semanal
pide el martes 6 (llega el 11) y cubre 17, hasta el 18.

### `compras[]`: una línea de compra

| Campo | Tipo | Significado |
| --- | --- | --- |
| `producto_id` | string | `codigo_item` del producto |
| `destino` | string | La sucursal (perecederos y frío) o `BODEGA_CENTRAL` (lo demás) |
| `tipo_destino` | `"sucursal"` \| `"bodega_central"` | Ruta de la compra |
| `grupo` | `"semanal"` \| `"quincenal"` | Grupo de pedido del producto |
| `cantidad` | entero | Cantidad a comprar, redondeada hacia arriba (unidad o kg). En la Bodega, `necesidad` menos `sobrante_bodega` |
| `unidad` | `"unidad"` \| `"kg"` | Unidad de la cantidad |
| `urgencia` | `"urgente"` \| `"alta"` \| `"normal"` | La de la sucursal más urgente de la línea: ≤ 5, ≤ 10 o más días hábiles hasta agotarse |
| `dias_hasta_agotarse` | número | Los de esa sucursal, con el stock después de traslados |
| `fecha_pedido`, `fecha_llegada`, `fecha_llegada_sucursal` | fecha | Las del plan de su grupo y ruta |
| `llega_tarde` | booleano | Alguna sucursal se agota antes de que le llegue la compra. Se compra igual |
| `necesidad` | número | Suma de lo que necesitan las sucursales, antes de descontar la Bodega |
| `sobrante_bodega` | número o `null` | Lo que la Bodega ya tenía y se descontó (en kilos, con 10 % de pérdida por el traslado). `null` en las compras directas |
| `motivo` | `"reposicion"` \| `"stock_negativo"` | `stock_negativo` si alguna sucursal compró con su stock negativo tomado como 0 |
| `detalle` | lista | El cálculo por sucursal (ver abajo). No viene con `incluir_detalle: false` |

### `detalle[]`: el cálculo de una sucursal

| Campo | Tipo | Significado |
| --- | --- | --- |
| `sucursal` | string | Sucursal física |
| `posicion` | número | max(stock, 0) + lo recibido en los traslados sugeridos |
| `q50`, `limite_superior` | número | Pronóstico a 15 días hábiles (los de `/api/predict`) |
| `punto_pedido` | número | q50 × P / 15. Se compra porque la posición quedó por debajo |
| `nivel` | número | max(qα, q50) × P / 15. Hasta aquí se compra |
| `necesidad` | número | nivel − posición |
| `dias_hasta_agotarse` | número | posición ÷ (q50 ÷ 15), en días hábiles |
| `urgencia`, `llega_tarde`, `motivo` | | Como en la línea, para esta sucursal |

### `cubrir_con_traslado[]`

Productos secos que necesitan reposición, pero el sobrante de la Bodega
alcanza. No se compran: los cubre un traslado de INV-22 cuando la sucursal
quede bajo su mediana.

| Campo | Tipo | Significado |
| --- | --- | --- |
| `producto_id`, `unidad` | string | Producto y unidad |
| `necesidad` | número | Suma de lo que necesitan las sucursales |
| `sobrante_bodega` | número | Lo que la Bodega tiene disponible, mayor o igual que la necesidad |
| `urgencia`, `dias_hasta_agotarse` | | De la sucursal más urgente |
| `detalle` | lista | Como en `compras` |

### `alertas[]`

| Campo | Tipo | Significado |
| --- | --- | --- |
| `producto_id`, `sucursal` | string | Par con stock negativo en la foto (la sucursal puede ser `BODEGA_CENTRAL`) |
| `tipo` | `"posible_inconsistencia_inventario"` | Siempre este valor |
| `stock` | número | El stock negativo |
| `accion` | `"compra_urgente"` \| `"verificar_conteo"` | `compra_urgente` si el par tiene pronóstico con q50 > 0: se compra con stock 0. Si no, solo verificar el conteo |
| `detalle` | string | Explicación en texto |

### `resumen`

| Campo | Tipo | Significado |
| --- | --- | --- |
| `productos` | entero | Productos procesados |
| `lineas`, `lineas_sucursal`, `lineas_bodega` | entero | Líneas de compra, en total y por ruta |
| `cantidad.unidad`, `cantidad.kg` | entero | Suma de cantidades, **separada por unidad** |
| `cubiertos_por_bodega` | entero | Productos en `cubrir_con_traslado` |
| `alertas` | entero | Número de alertas |
| `pares_sin_pronostico` | entero | Pares que no compran por falta de pronóstico. El detalle está en las alertas de `/api/transferencias` |

### Códigos de respuesta

Los mismos de `/api/transferencias`: 409 si la foto es posterior a la última
venta, 422 si el cuerpo no cumple el esquema y 503 si la bodega no está
disponible o `dim_tiempo` no alcanza para el pedido siguiente.

### Ejemplo (foto al 2025-12-31)

```json
// Petición
{"productos": ["P1632", "00380", "P3937"], "incluir_detalle": false}

// Respuesta (compras abreviadas a dos de sus cuatro líneas; faltan P1632 en GLORIETA y en LA 21)
{
  "fecha_inventario": "2025-12-31", "fecha_pronostico": "2025-12-31", "lead_time_dias": 5,
  "politicas": {"inv21": {"version": 1, "fecha": "2026-09-30"}, "inv22": {"version": 1, "fecha": "2026-09-30"}},
  "calendario": [
    {"grupo": "quincenal", "tipo_destino": "bodega_central", "fecha_pedido": "2026-01-02",
     "fecha_llegada": "2026-01-07", "fecha_llegada_sucursal": "2026-01-09", "pedido_siguiente": "2026-01-16",
     "cubre_hasta": "2026-01-23", "dias_cubiertos": 22, "dias_hasta_llegada": 8},
    {"grupo": "semanal", "tipo_destino": "sucursal", "fecha_pedido": "2026-01-06",
     "fecha_llegada": "2026-01-11", "fecha_llegada_sucursal": "2026-01-11", "pedido_siguiente": "2026-01-13",
     "cubre_hasta": "2026-01-18", "dias_cubiertos": 17, "dias_hasta_llegada": 10}
  ],
  "compras": [
    {"producto_id": "P1632", "destino": "PRINCIPAL", "tipo_destino": "sucursal", "grupo": "semanal",
     "cantidad": 4735, "unidad": "unidad", "urgencia": "urgente", "dias_hasta_agotarse": 2.2,
     "fecha_pedido": "2026-01-06", "fecha_llegada": "2026-01-11", "fecha_llegada_sucursal": "2026-01-11",
     "llega_tarde": true, "necesidad": 4734.22, "sobrante_bodega": null, "motivo": "reposicion"},
    {"producto_id": "00380", "destino": "BODEGA_CENTRAL", "tipo_destino": "bodega_central", "grupo": "quincenal",
     "cantidad": 53, "unidad": "unidad", "urgencia": "alta", "dias_hasta_agotarse": 5.7,
     "fecha_pedido": "2026-01-02", "fecha_llegada": "2026-01-07", "fecha_llegada_sucursal": "2026-01-09",
     "llega_tarde": true, "necesidad": 101.28, "sobrante_bodega": 49.0, "motivo": "reposicion"}
  ],
  "cubrir_con_traslado": [
    {"producto_id": "P3937", "necesidad": 2494.93, "sobrante_bodega": 2757.0, "unidad": "unidad",
     "urgencia": "normal", "dias_hasta_agotarse": 15.0}
  ],
  "alertas": [],
  "no_encontrados": [],
  "resumen": {"productos": 3, "lineas": 4, "lineas_sucursal": 3, "lineas_bodega": 1,
              "cantidad": {"unidad": 10086, "kg": 0}, "cubiertos_por_bodega": 1, "alertas": 0,
              "pares_sin_pronostico": 0}
}
```

Cómo se lee: los huevos en PRINCIPAL alcanzan para 2,2 días y el pedido llega
en 10, así que la compra es urgente y llega tarde. Del durazno, las sucursales
necesitan 101,28 hasta el 23 de enero; la Bodega tiene 49, así que se compran
53. El arroz necesita 2.494,93, pero la Bodega tiene 2.757: no se compra.
