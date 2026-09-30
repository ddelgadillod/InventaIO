# INV-22 — Recomendación de transferencias entre sucursales

`POST /api/transferencias` en `ml_service` recomienda traslados de stock desde
la Bodega Central y entre sucursales físicas antes de comprar a proveedor. Usa
la foto de inventario (`dw.fact_inventario`, hoy al 2025-12-31) y el pronóstico
a 15 días hábiles de `/api/predict`, calculado con el mismo código y en el
mismo proceso. Entrega a INV-21 el déficit neto por producto y sucursal, y las
alertas.

La especificación completa, con decisiones, políticas y criterios, está en
[`INV-22-requerimientos.md`](INV-22-requerimientos.md). Este documento dice
cómo quedó implementado, qué se interpretó y qué dio con los datos reales.

## Cómo se usa

```powershell
# un producto (o varios)
Invoke-RestMethod http://localhost:8001/api/transferencias -Method Post -ContentType "application/json" `
  -Body '{"productos": ["P1632", "P3937"]}'

# todo el catálogo de la foto, sin el balance por par (unos 20 s)
Invoke-RestMethod http://localhost:8001/api/transferencias -Method Post -ContentType "application/json" `
  -Body '{"incluir_balance": false}'
```

| Campo de la petición | Regla |
| --- | --- |
| `productos` | Lista de `codigo_item` (al menos uno). Sin la lista se procesan todos los productos con fila en la foto. Un código que no existe va a `no_encontrados` |
| `incluir_balance` | `true` por defecto. Con `false` la respuesta no trae `balance` |

| Código | Cuándo |
| --- | --- |
| 200 | Recomendación calculada |
| 409 | La foto de inventario es posterior a la última venta cargada (P8); el detalle dice cuántos días faltan |
| 422 | El cuerpo no cumple el esquema |
| 503 | Bodega no disponible, bodega vacía o calendario insuficiente |

La respuesta trae `fecha_inventario`, `fecha_pronostico`, `horizonte_dias`,
`politicas` (versión y fecha del archivo usado), `traslados`, `balance`,
`alertas`, `no_encontrados` y `resumen`. Cada campo está explicado en
[`ML-SERVICE-API.md`](ML-SERVICE-API.md) y en http://localhost:8001/api/docs.

**Para INV-21.** La función pública es
`transferencias.motor.recomendar_transferencias(bodega, modelos, politicas, productos=None)`.
`modelos` puede ser el `ModeloLoader` de `app.state.modelo_loader`. INV-21 toma
`balance[].deficit_neto` y `alertas` sin recalcular traslados, y descuenta
todos los traslados sugeridos (P15).

## Archivo de políticas

`ml_service/transferencias/politicas_inv22.json`, versionado. Se valida al
arrancar el servicio: si no es válido, el servicio no arranca. La respuesta
dice qué `version` se usó. Ruta configurable con `POLITICAS_TRANSFERENCIAS_PATH`.

Hay dos tipos de campos:

- **Números que se ajustan sin tocar código.** Son las respuestas a los pendientes de confirmar.
- **Textos que nombran la regla implementada.** Hoy cada uno admite un solo
  valor, y otro valor se rechaza al arrancar porque exigiría código nuevo.
  Eso evita que un cambio en el JSON parezca aplicado cuando no lo está.

| Campo | Valor | Qué controla | ¿Ajustable? |
| --- | --- | --- | --- |
| `version`, `fecha` | 1, 2026-09-30 | Trazabilidad; salen en la respuesta | Sí (subir al cambiar algo) |
| `horizonte_dias` | 15 | A1. Debe coincidir con los modelos | No (solo 15) |
| `stock_maximo.margen_perecedero` | 0,25 | P1: máximo = qα × 1,25 en perecederos | Sí (pendiente 1) |
| `stock_maximo.margen_no_perecedero` | 0,50 | P1: máximo = qα × 1,50 en no perecederos | Sí (pendiente 1) |
| `stock_maximo.unidades_exhibicion` | 2 | P1: lo que conserva el origen | Sí |
| `reserva_bodega` | 0 | P3: lo que la Bodega no despacha | Sí |
| `cantidades.minimo` | 6 | P11: traslado mínimo (unidades o kg) | Sí (pendiente 4) |
| `cantidades.descuento_kilos` | 0,10 | Q9: pérdida descontada antes de trasladar kilos | Sí |
| `urgencia.urgente_dias`, `alta_dias` | 5, 10 | P13, en días hábiles hasta agotarse | Sí |
| `traslado.dias_semana` | `[]` | Q7: días fijos de salida, p. ej. `["martes", "viernes"]` (con o sin tilde) | Sí (pendiente 3) |
| `traslado.dias_habiles_si_no_hay_dias_fijos` | 2 | P13: tiempo de traslado sin días fijos | Sí |
| `objetivo_destino` | `q50` | P2 | No |
| `perecederos` | directo, solo con venta | P4 | No |
| `frio` | directo, no entra a la Bodega | P5, A3 | No |
| `sin_pronostico`, `stock_negativo`, `foto_sin_ventas` | excluir, como_cero, bloquear | P6, P7, P8 | No |
| `reparticion` | nivelar_cobertura, desempate q50 | P9 | No |
| `origenes` | bodega_primero | P10 | No |
| `excedente_sin_destino` | se_queda | P12 | No |
| `urgencia.llega_tarde` | trasladar_y_marcar | P13 | No |
| `q50_cero` | solo_sobrante | P14 (pendiente 2) | No |
| `compras_descuenta` | sugeridos | P15 | No |

## Cómo quedó el algoritmo

`recomendar_transferencias` lee la bodega por lotes: 10 consultas para todo el
catálogo, nunca una por par. Después pronostica todos los pares producto ×
sucursal física en un lote y resuelve cada producto con `planificar_producto`,
que no hace I/O. Por producto:

1. **Clasifica cada ubicación.**
   - Bodega: todo su stock positivo es excedente.
   - Stock negativo: alerta `pedido_urgente`.
   - Sin pronóstico: alerta `sin_pronostico`.
   - q50 = 0: vigilancia.
   - Resto: origen (sobre el máximo), destino (bajo el objetivo) o equilibrio.
2. **Reparte** el excedente de los orígenes entre los destinos (P9).
3. **Asigna orígenes** a lo que recibe cada destino (P10). Atiende primero al
   de menor cobertura y arma traslados de al menos el mínimo (P11).
4. **Lleva el sobrante** a los pares en vigilancia que no son perecederos, de
   mayor a menor límite superior (P14).
5. **Calcula urgencia y llegada** (P13) y arma el balance y las alertas.

Las fórmulas son las de la especificación:
objetivo = q50; máximo = max(qα × (1 + margen), q50);
excedente = max(0, stock − max(máximo, 2)); déficit = max(0, q50 − stock).
Las cantidades se redondean hacia abajo, y en kilos se multiplican antes por 0,9.

### Interpretaciones de la especificación

Donde la especificación deja margen, se decidió así. Cada punto tiene su prueba.

| Tema | Decisión | Por qué |
| --- | --- | --- |
| Nivelación y mínimo de 6 | El reparto va unidad por unidad al destino de menor cobertura, pero un destino entra con un primer bloque de 6 | Repartir de a una unidad deja traslados de 3 + 3 que después se descartan (P11), y así no se movería nada. Con el bloque, "Desempate" y "Nivelación" salen como pide la tabla de casos |
| Destino con déficit menor al mínimo | No entra al reparto; su déficit queda en el neto | Ningún traslado válido podría llegarle |
| Origen con menos del mínimo disponible | No despacha; su excedente se queda (P12) | Mismo motivo |
| Resto menor al mínimo | Si un destino necesita 10 y la Bodega tiene 7, salen 7 y los 3 restantes no se piden a otro origen | Pasos 8 y 9 literales: sería un traslado de 3 |
| Par sin fila en la foto y sin pronóstico | No aparece en el balance ni en las alertas | Son pares que el negocio no maneja. Las alertas `sin_pronostico` son solo de filas reales de la foto |
| Par sin fila en la foto con pronóstico | Stock 0, puede ser destino | Paso 4 |
| Vigilancia (q50 = 0) | `deficit` 0 y `deficit_neto` 0; lo que puede recibir va aparte, en `deficit_vigilancia` = qα − stock | Q5: INV-21 no compra para cubrir una mediana en cero |
| Stock negativo | No da ni recibe. `deficit` = q50 con el stock tomado como 0, y urgencia sobre stock 0 | P7: así llega a INV-21 como pedido urgente |
| Bodega con stock negativo | Alerta `stock_negativo` y no despacha | A4, paso 3 |
| Días hábiles de llegada | Los de la historia y, después del último dato, los de `dim_tiempo` que no son cierre programado (1 de enero, Viernes Santo). Es el mismo calendario del modelo | Con la foto al 2025-12-31, la llegada es el 2026-01-03 |
| `llega_tarde` | Días hasta agotarse < días hábiles de llegada | "El agotamiento ocurre antes": el mismo día no cuenta como tarde |

Campos agregados a la respuesta, además de los de la especificación: en los
traslados, `dias_habiles_llegada`; en el balance, `tipo_ubicacion`, `enviado`,
`excedente_sin_destino` (P12) y `deficit_vigilancia`; en las alertas,
`detalle`; en el resumen, `excedente_sin_destino`.

### El pronóstico es el de /api/predict

El cálculo de `POST /api/predict` se extrajo a `prediccion/servicio.py`
(`pronosticar_par`), y el router lo usa con el mismo contrato y los mismos
errores. El catálogo completo usa `pronosticar_lote`: las mismas features y
una predicción por rama del modelo en vez de una por par. `motor.predecir` es
`motor.predecir_lote` aplicado a una fila, así que los dos caminos no pueden
divergir. Las pruebas lo verifican:

- con paquetes falsos de los cuatro tipos de modelo;
- con los modelos reales sobre la bodega falsa;
- con 200 pares reales de las tres ramas;
- con 15 pares del balance real contra `/api/predict` por HTTP.

## Marcas de logística en `dw.dim_producto`

Dos columnas nuevas que **no** son features del modelo. Las cinco columnas del
modelo no cambian, así que la paridad de INV-20 se mantiene.

| Columna | Regla | Resultado (2022-2025, sin overrides) | Override del negocio |
| --- | --- | --- | --- |
| `requiere_frio` | `es_refrigerado` (por categoría) y el nombre no tiene una palabra de producto estable (`PALABRAS_PRODUCTO_ESTABLE` en `etl_real/config.py`, palabra completa, singular o plural) | 305 de los 429 refrigerados; 124 quedan sin frío | `etl_real/overrides_requiere_frio.csv` |
| `se_vende_por_kilo` | La mitad o más de sus líneas de venta (cantidad > 0) tienen decimales | 64 productos | `etl_real/overrides_por_kilo.csv` |

La lista de palabras estables parte de las cinco acordadas (ATUN, SARDINA, EN
POLVO, CALDO, RICOSTILLA). Se completó revisando los 429 refrigerados, empezando
por los 35 que tienen stock en la Bodega. Se agregaron enlatados, leche larga
vida, leche en polvo y condensada, salsas, pasabocas y café instantáneo.

Con la regla, **ninguno de los 35 queda con frío**: son atún, sardinas,
Ricostilla, leches en polvo (Fortileche, El Rodeo, Toning), salchichas en lata,
salsa para carnes y Lechera. Es coherente con A3: si la Bodega no tiene frío,
lo que guarda no lo necesita.

Para "por kilo" la separación en los datos es limpia: 63 productos venden con
decimales en más del 90 % de sus líneas y 119 en menos del 10 %. Así que el
umbral del 50 % no es ambiguo.

Los overrides (`codigo_item`, marca, `motivo`) mandan sobre la regla. Aceptan
`true/false`, `1/0` o `si/no`. Un valor inválido o un código repetido detienen
el ETL.

**Lista para el negocio.** `construir_dim_producto.py` escribe
`data/processed_real/revision_marcas_logistica.csv`. Tiene 588 productos: los
refrigerados por categoría, los marcados por kilo y los que tienen alguna venta
con decimales. Cada uno trae la marca, de dónde sale (regla, palabra que la
decidió u override) y la fracción de líneas con decimales. Los cambios que pida
el negocio van a los CSV de overrides, no al código.

Para aplicar las marcas en una bodega existente:
1. Correr `construir_dim_producto.py`.
2. Aplicar `database/init.sql`. Su migración agrega las columnas sin borrar datos.
3. Correr `cargar_postgres.py`.

`database/test-dw-real.SQL` reporta los conteos y los productos con frío en la Bodega.

## Resultados con los datos reales (foto al 2025-12-31)

Catálogo completo, con Docker Compose local (`postgres` + `ml-service`):

| Métrica | Valor |
| --- | --- |
| Productos con fila en la foto | 4.419 |
| Traslados sugeridos | 119 (4.623 unidades): 109 desde la Bodega y 10 entre sucursales |
| Destinos | PRINCIPAL 88, GLORIETA 23, LA 21 8 |
| Urgencia | 42 urgentes, 59 altas, 18 normales; 16 llegan tarde |
| Déficit total → neto | 20.677 → 16.054 (lo que va a INV-21) |
| Excedente que se queda (P12) | 77.082 |
| Alertas | 220 `stock_negativo` y 2.762 `sin_pronostico` (la especificación estimaba unas 2.700) |
| Consultas a la bodega | 10 |
| Tiempo | 18 s en las pruebas y 20 s por HTTP en Docker |

Pocos traslados es lo esperado: el 98,6 % de los pares son intermitentes, el
objetivo es la mediana y el mínimo es 6 (riesgo documentado en la
especificación). Ningún traslado en kilos salió con esta foto.

**Rendimiento.** La primera versión pronosticaba par por par y tardaba 80 s.
Dos cambios la dejaron en 18 s con exactamente el mismo resultado:
- Guardar el factor de calendario, que es el mismo para todos los pares de una fecha.
- Predecir por lote.

**Escenario verificado a mano: arroz Zulia \*500 g (P3937).**

| Ubicación | Stock | q50 | Límite sup. | Máximo | Déficit | Recibe | Días hasta agotarse |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BODEGA_CENTRAL | 4.024 | — | — | — | — | envía 1.267 | — |
| GLORIETA | 256 | 828,19 | 1.458,95 | 2.188,42 | 572,19 | 572 | 256 / (828,19 / 15) = 4,6 → urgente |
| PRINCIPAL | 556 | 1.251,25 | 1.659,64 | 2.489,46 | 695,25 | 695 | 556 / (1.251,25 / 15) = 6,7 → alta |
| LA 21 | 240 | 121,84 | 199,84 | 299,76 | 0 | 0 | 29,5 → equilibrio |

La Bodega alcanza para todo, así que cada destino recibe su déficit redondeado
hacia abajo. GLORIETA, con menos cobertura, se atiende primero. El déficit neto
es 0,19 y 0,25. Los q50 coinciden con `/api/predict`, y el máximo de PRINCIPAL
es 1.659,64 × 1,5 (no perecedero). La prueba
`test_escenario_real_de_la_bodega_a_una_sucursal` recalcula así el traslado
más grande desde la Bodega.

**Huevos (P1632)**, el ejemplo de la especificación: las tres sucursales son
destino y no hay excedente en ningún lado. No hay traslados, y los déficits
(2.877, 1.042 y 3.530) pasan completos a INV-21.

## Pruebas

| Suite | Qué cubre |
| --- | --- |
| `tests/test_transferencias_motor.py` | Los 17 casos de la tabla de la especificación y los bordes: urgencia, márgenes, orden de orígenes, mínimos, llegada con días fijos, catálogo, lote contra par con modelos reales |
| `tests/test_transferencias_router.py` | 200, sin balance, 409, 422, 503 (bodega caída y calendario), OpenAPI y la validación del archivo de políticas |
| `tests/test_transferencias_integracion.py` (marca `bodega`) | Catálogo completo (consultas y tiempo), q50 contra `/api/predict`, stock contra `fact_inventario`, alertas contra las filas negativas, escenario Bodega → sucursal, lote contra par en 200 pares reales, ventas por lote |
| `tests/test_motor.py` | `predecir_lote` fila a fila contra `predecir` en los cuatro tipos de paquete |
| `etl_real/tests/test_etl_real.py` | Regla y overrides de las dos marcas, palabra completa y plural, fracción de líneas con decimales, columnas en `dim_producto.csv` |

```bash
cd ml_service
pytest                 # todo; las de integración se saltan sin Postgres
pytest -m "not bodega" # solo unitarias
pytest -m bodega       # integración (POSTGRES_HOST=localhost)
pytest --cov=.         # cobertura
cd ../etl_real && python -m unittest discover -s tests
```

Resultados de esta entrega:
- `ml_service`: 124 pasan y 1 se salta. La que se salta es `test_paridad_matriz.py`,
  que necesita `data/processed_real/matriz_as_of.parquet`, igual que antes de
  INV-22. Las 53 pruebas que existían siguen pasando (criterio 13).
- Cobertura de `ml_service`: 98 % con integración y 92 % solo con las
  unitarias; `transferencias/motor.py`, 100 %.
- `etl_real`: 60 pruebas OK (2 se saltan por no estar los artefactos de los notebooks).

## Criterios de aceptación

| # | Dónde se verifica |
| --- | --- |
| 1 | `test_excedente_sin_deficit…`, `test_deficit_sin_excedente…`, `test_margen_de_perecederos…`, `test_maximo_nunca_menor…` |
| 2 | `test_bodega_primero…`, `test_frio_sale_de_la_bodega…`, `test_perecedero_solo_hacia…`, `test_nada_entra_a_la_bodega…` (real) |
| 3 | `test_perecedero_solo_hacia_sucursales_con_q50_positivo` |
| 4 | `test_frio_sale_de_la_bodega_y_nunca_entra` |
| 5 | `test_desempate…`, `test_nivelacion…`, `test_empate_exacto…` |
| 6 | `test_kilos…`, `test_minimo_de_6…` (dos casos), `test_un_resto_menor_al_minimo…` |
| 7 | `test_urgencia_por_dias_hasta_agotarse` (4 bordes), `test_llega_tarde…` |
| 8 | `test_intermitente_con_q50_cero…` (dos casos), `test_q50_cero_no_es_origen…` |
| 9 | `test_stock_negativo…`, `test_sin_pronostico…`, `test_stock_del_balance_coincide…` (real) |
| 10 | `test_respuesta_expone_deficit_recibido_neto_y_politicas`, router |
| 11 | `test_foto_mas_nueva_que_las_ventas…`, `test_foto_sin_ventas_da_409` |
| 12 | `test_cambiar_el_margen_en_el_json…`, `test_politicas_invalidas_se_rechazan` |
| 13 | Las 53 pruebas existentes pasan. `/api/predict` responde igual en Docker: el ejemplo de `docs/AMBIENTE-DESARROLLO.md` (3366,01 / 4608,72) y 13 casos más, válidos y de error |

## Limitaciones y pendientes

- **Foto única.** Con la foto al 2025-12-31, la historia valida el algoritmo, no la
  operación diaria. Cuando llegue una foto nueva sin sus ventas, el endpoint
  responde 409 hasta que se carguen.
- **Pendientes de confirmar 1 a 5.** Corren con sus valores por defecto. Se
  ajustan en el JSON o en los overrides sin tocar código.
- **Entrega al negocio.** Falta entregarle `revision_marcas_logistica.csv` para revisión (DoD).
- **Restos menores al mínimo.** Un resto menor al mínimo no se completa desde
  un segundo origen, aunque ese origen tenga de sobra (ver interpretaciones).
  Si el negocio lo pide, se puede mejorar sin cambiar el contrato.
- **Columnas heredadas.** `stock_minimo`, `stock_maximo`, `punto_reorden` y
  `dias_cobertura` de `fact_inventario` no se usan.
