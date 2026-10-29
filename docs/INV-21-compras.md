# INV-21 — Recomendación de compras a proveedor

`POST /api/compras` en `ml_service` recomienda compras a proveedor para lo que
las transferencias de INV-22 no alcanzan a cubrir. Parte del balance de
`recomendar_transferencias`, calculado en el mismo proceso: stock, traslados
sugeridos y pronóstico por producto y sucursal. Compra cuando el stock no
alcanza hasta que llegue el pedido siguiente.

La especificación, con las decisiones B1–B13 y por qué se apartan del
bosquejo, está en [`INV-21-requerimientos.md`](INV-21-requerimientos.md). Este
documento dice cómo quedó implementado y qué dio con los datos reales. El
contrato campo por campo está en [`ML-SERVICE-API.md`](ML-SERVICE-API.md).

## Cómo se usa

```powershell
# unos productos
Invoke-RestMethod http://localhost:8001/api/compras -Method Post -ContentType "application/json" `
  -Body '{"productos": ["P1632", "00380", "P3937"]}'

# todo el catálogo de la foto, sin el cálculo por sucursal (unos 20 s)
Invoke-RestMethod http://localhost:8001/api/compras -Method Post -ContentType "application/json" `
  -Body '{"incluir_detalle": false}'
```

| Campo de la petición | Regla |
| --- | --- |
| `productos` | Lista de `codigo_item` (al menos uno). Sin la lista se procesan todos los productos con fila en la foto. Un código que no existe va a `no_encontrados` |
| `incluir_detalle` | `true` por defecto. Con `false` las líneas no traen el cálculo por sucursal |

| Código | Cuándo |
| --- | --- |
| 200 | Recomendación calculada |
| 409 | La foto de inventario es posterior a la última venta cargada (la regla P8 de INV-22) |
| 422 | El cuerpo no cumple el esquema |
| 503 | Bodega no disponible o vacía, o `dim_tiempo` no alcanza para el pedido siguiente |

La respuesta trae `calendario` (las fechas de cada grupo de pedido), `compras`,
`cubrir_con_traslado`, `alertas`, `no_encontrados`, `resumen` y la versión de
las políticas de INV-21 y de INV-22.

**Función pública.** `compras.motor.recomendar_compras(bodega, modelos,
politicas, politicas_traslados, productos=None)`. `modelos` puede ser el
`ModeloLoader` o el `PronosticadorNivel1` de `app.state`.

## Archivo de políticas

`ml_service/compras/politicas_inv21.json`, versionado y validado al arrancar,
como el de INV-22: si no es válido, el servicio no arranca. Ruta configurable
con `POLITICAS_COMPRAS_PATH`.

| Campo | Valor | Qué controla | ¿Ajustable? |
| --- | --- | --- | --- |
| `version`, `fecha` | 1, 2026-09-30 | Trazabilidad; salen en la respuesta | Sí (subir al cambiar algo) |
| `horizonte_modelo_dias` | 15 | El horizonte de los modelos | No (solo 15) |
| `lead_time_dias` | 5 | B1: días hábiles entre el pedido y su llegada | Sí (pendiente 1) |
| `calendario_pedidos.quincenal.dias_mes` | `[2, 16]` | B2: días fijos del mes, del 1 al 28 | Sí |
| `calendario_pedidos.semanal.dias_semana` | `["martes"]` | B2: días fijos de la semana, con o sin tilde | Sí |
| `grupo_semanal` | perecedero, requiere_frio | B7: qué marcas piden cada semana. Puede quedar vacía o con una sola | Sí |
| `destino_directo` | perecedero, requiere_frio | B8: van directo a la sucursal | No: A3 y A5 de INV-22 |
| `minimo_linea` | 1 | B6: cantidad mínima de una línea; las menores se suben a este valor | Sí (pendiente 4) |
| `urgencia.urgente_dias`, `alta_dias` | 5, 10 | B12, en días hábiles hasta agotarse | Sí |
| `punto_pedido`, `nivel`, `redondeo` | q50, max_qalfa_q50, arriba | B4, B5, B6 | No |
| `bodega.descontar_sobrante` | true | B9 | No |
| `stock_negativo`, `q50_cero`, `sin_pronostico` | alerta y compra si hay pronóstico; sin compra; sin compra | B10, B11 | No |

Igual que en INV-22, los textos nombran la regla implementada y otro valor se
rechaza al arrancar, para que un cambio en el JSON no parezca aplicado cuando
no lo está.

## Cómo quedó

`recomendar_compras` llama a `recomendar_transferencias` con los mismos
productos, calcula el calendario una vez (`compras/calendario.py`), lee las
marcas de los productos en una consulta más y resuelve cada producto con
`planificar_compras_producto`, que no hace I/O. El catálogo completo usa 11
consultas: las 10 de INV-22 más las marcas.

**Calendario** (`compras/calendario.py`). Para cada combinación de grupo y ruta:

1. Pedido actual: la primera fecha fija en o después de la foto. Si cae en un día no hábil, pasa al siguiente.
2. Llegada: `lead_time_dias` días hábiles después. Por la Bodega, la sucursal lo recibe con la regla de llegada de los traslados de INV-22 (hoy, 2 días hábiles más).
3. Pedido siguiente y su llegada a la sucursal (`cubre_hasta`).
4. P = días hábiles desde la foto hasta `cubre_hasta`.

Los días hábiles son los del modelo y de INV-22: en la historia, los días con
venta; después del último dato, los de `dim_tiempo` sin cierre programado.

**Por producto** (`compras/motor.py`):

1. Grupo y ruta por sus marcas: perecedero o con frío va semanal y directo; lo demás, quincenal y por la Bodega.
2. Cada fila de stock negativo del balance genera la alerta `posible_inconsistencia_inventario`.
3. En cada sucursal con q50 > 0 se calculan posición, punto de pedido, nivel y necesidad con las fórmulas de la especificación.
4. Directo: una línea por sucursal. Por la Bodega: una línea con la suma, menos el sobrante de la Bodega. Si el sobrante alcanza, el producto va a `cubrir_con_traslado`.

```text
posición     = max(stock, 0) + recibido
punto_pedido = q50(15) × P / 15
nivel        = max(qα(15), q50(15)) × P / 15
compra si posición < punto_pedido;  necesidad = nivel − posición;  cantidad = ⌈necesidad⌉
```

### Decisiones de implementación

Donde la especificación deja margen, se decidió así. Cada punto tiene su prueba.

| Tema | Decisión | Por qué |
| --- | --- | --- |
| Urgencia de una línea de la Bodega | La de la sucursal más urgente; `llega_tarde` si alguna llega tarde; `motivo` `stock_negativo` si alguna compró con stock negativo | La línea resume varias sucursales; el detalle trae cada una |
| Sobrante de la Bodega | El `excedente_sin_destino` de INV-22 (stock − enviado). En kilos, × 0,9 por la pérdida del traslado. Con stock negativo en la Bodega, 0 | Es lo que queda después de los traslados sugeridos (P15) |
| Frío o perecederos que ya están en la Bodega | No se descuentan: la compra va directo a la sucursal | La Bodega solo los despacha por traslado de INV-22, que ya los considera |
| Alertas | Solo stock negativo. Los pares sin pronóstico no se repiten como alerta; se cuentan en `resumen.pares_sin_pronostico` | Son 2.762 y su detalle ya está en `/api/transferencias` |
| Días del mes | Del 1 al 28 | Existen en todos los meses |
| `grupo_semanal` | Configurable: vacío, solo perecederos o solo frío. `destino_directo` no | La frecuencia es del negocio; la ruta la fijan A3 y A5 |
| Fecha fija que cae en cierre | Pasa al siguiente día hábil, y el pedido siguiente se busca después de ese día | B2 |

Campos agregados a la respuesta frente al ejemplo de la especificación: en
`calendario`, `tipo_destino`, `fecha_llegada_sucursal` y `dias_hasta_llegada`;
en las líneas, `fecha_llegada_sucursal`; en `detalle`, `llega_tarde` y
`motivo`; en `cubrir_con_traslado`, `urgencia`, `dias_hasta_agotarse` y
`detalle`.

## Frío en Congelados

`requiere_frio` ahora también es verdadero en la categoría Congelados
(`CATEGORIAS_FRIO_ADICIONALES` en `etl_real/config.py`). A diferencia de los
refrigerados, aquí no se aplican las palabras de producto estable: "HELADO
CONO CHOCORRAMO" contiene CONO, que es palabra estable por los pasabocas, y
es un helado. Los palos para paletas (P431) quedan sin frío por override en
`etl_real/overrides_requiere_frio.csv`. `es_refrigerado` no cambia, así que la
paridad del modelo (INV-20) se mantiene.

| Resultado (datos 2022-2025) | Antes | Ahora |
| --- | --- | --- |
| Productos con frío | 305 | 329 |
| Con frío y stock en la Bodega | 0 | 1 (papa precocida 02276, 2 unidades) |
| Traslados de INV-22 en el catálogo | 119 | 119: el cambio no altera ningún traslado con esta foto |

`database/test-dw-real.SQL` verifica los conteos nuevos. La lista para el
negocio (`revision_marcas_logistica.csv`) ahora incluye los congelados: 610
productos.

## Resultados con los datos reales (foto al 2025-12-31)

Catálogo completo, con Docker Compose local (`postgres` + `ml-service`). Son
exactamente las cifras de la simulación previa de la especificación.

| Métrica | Valor |
| --- | --- |
| Productos | 4.419 |
| Líneas de compra | 1.340: 449 directas a sucursal y 891 para la Bodega |
| Cantidad | 41.952 unidades y 3.169 kg |
| Urgencia | 585 urgentes, 255 altas, 500 normales; 784 llegan tarde |
| Por stock negativo | 103 líneas (116 pares con compra urgente) |
| Cubiertos por el sobrante de la Bodega | 277 productos |
| Alertas | 220: 116 con compra urgente, 89 en sucursales y 15 en la Bodega solo para verificar el conteo |
| Pares sin pronóstico | 2.762 |
| Consultas y tiempo | 11 consultas; 19 s por HTTP en Docker (unos 24 s en las pruebas, que cuentan consultas) |

**Calendario de la foto.** El quincenal pide el 2 de enero, llega el 7 a la
Bodega y el 9 a la sucursal, y cubre 22 días hábiles hasta el 23. El semanal
pide el martes 6, llega el 11 y cubre 17 hasta el 18.

**Escenarios verificados** (prueba `test_ejemplos_de_la_especificacion`):

| Producto | Resultado |
| --- | --- |
| Huevos (P1632) | Compra directa semanal: 4.735 a PRINCIPAL, 4.047 a GLORIETA y 1.251 a LA 21. En PRINCIPAL alcanza para 2,2 días: urgente y llega tarde |
| Durazno María José (00380) | Las sucursales necesitan 101,28 hasta el 23 de enero; la Bodega tiene 49: compra 53 para la Bodega (alta, llega tarde en LA 21) |
| Arroz Zulia (P3937) | Necesita 2.494,93; la Bodega tiene 2.757: sin compra, en `cubrir_con_traslado` |
| P4650 | Stock −70 en LA 21 con q50 15,68: alerta `compra_urgente`; compra 92 para la Bodega |

## Pruebas

| Suite | Qué cubre |
| --- | --- |
| `tests/test_compras_motor.py` | Los casos de la tabla de la especificación (salvo los dos de calendario), la línea de la Bodega con varias sucursales, el resumen y los códigos desconocidos |
| `tests/test_compras_calendario.py` | Fechas de pedido y llegada, plazo P, cierres, foto en día de pedido, fechas fijas que cruzan de mes, calendario insuficiente |
| `tests/test_compras_router.py` | 200, sin detalle, catálogo, 409, 422, 503 (bodega caída y calendario), OpenAPI y la validación del archivo de políticas |
| `tests/test_compras_integracion.py` (marca `bodega`) | Catálogo completo (consultas y tiempo), rutas por marca, cada línea recalculada desde el balance de INV-22, alertas contra las filas negativas y los ejemplos de la especificación |
| `etl_real/tests/test_etl_real.py` | Frío en Congelados, sin palabras estables, override y el override versionado de P431 |

Resultados de esta entrega:
- `ml_service`: 187 pasan y 1 se salta (`test_paridad_matriz.py`, que necesita la matriz de entrenamiento, igual que antes). Las 124 pruebas que existían siguen pasando.
- Cobertura de `ml_service`: 98 %. `compras/`: 99 % solo con las unitarias; `compras/motor.py`, 100 %.
- `etl_real`: 64 pruebas OK (2 se saltan, como antes).
- `database/test-dw-real.SQL` sin ningún `NO CUMPLE`.
- `/api/predict` y `/api/transferencias` responden igual en Docker (P1632 en PRINCIPAL 3.366,01 / 4.608,72; P3937 572 y 695 desde la Bodega).

## Criterios de aceptación

| # | Dónde se verifica |
| --- | --- |
| 1 | `test_la_posicion_incluye_lo_recibido…`, `test_cada_linea_sale_del_balance…` (real) |
| 2 | `test_perecedero_va_directo…`, `test_frio_no_perecedero…`, `test_clasificar…`, `test_perecederos_y_frio_nunca…` (real) |
| 3 | `test_fecha_fija_en_cierre…`, `test_foto_en_dia_de_pedido…`, `test_planes_con_las_politicas_del_repo` |
| 4 | `test_planes_con_las_politicas_del_repo`, `test_perecederos_semanales_y_frio_quincenal_directo` |
| 5 | `test_alcanza…`, `test_cubre_15_dias…`, `test_perecedero_con_qalfa…`, `test_kilos_redondea…`, `test_minimo_por_linea…` |
| 6 | `test_seco_en_dos_sucursales…`, `test_sobrante_suficiente…`, `test_sobrante_parcial…`, `test_kilos_en_la_bodega…` |
| 7 | `test_q50_cero…`, `test_sin_pronostico…` |
| 8 | `test_stock_negativo_con_pronostico…`, `test_stock_negativo_sin_pronostico…`, `test_alertas_son_las_filas_negativas…` (real) |
| 9 | `test_llega_tarde_y_orden_por_urgencia`, `test_linea_de_la_bodega_toma_la_sucursal_mas_urgente` |
| 10 | `test_cambiar_el_lead_time…`, `test_politicas_invalidas_se_rechazan`, `test_catalogo_resumen_y_politicas` |
| 11 | `test_congelados_…` y `test_override_…` en `etl_real`; `test-dw-real.SQL` (329 con frío, 1 en la Bodega) |
| 12 | Las 124 pruebas existentes pasan; `/api/predict` y `/api/transferencias` iguales en Docker |

## Limitaciones y pendientes

- **Foto única.** Con la foto al 2025-12-31, la historia valida la regla, no la operación diaria.
- **Sin pedidos en tránsito.** Si se corre dos veces antes de que llegue la compra, la recomienda dos veces. Debe correrse en las fechas de pedido.
- **Muchas compras llegan tarde** (784 de 1.340): son pares que ya están casi sin stock. Se marcan, no se bloquean.
- **Plazos distintos de 15 días.** 17 y 22 días se derivan escalando q50 y qα por la tasa diaria; la compra queda algo por arriba.
- **Pendientes de confirmar 1 a 5** de la especificación: corren con su valor por defecto y se ajustan en el JSON o en los overrides.
- **Entrega al negocio.** La lista de los 24 congelados con frío va en `revision_marcas_logistica.csv` para revisión.
