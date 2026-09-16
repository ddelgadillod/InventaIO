# INV-60 — Notas de la migración del DW simulado al DW real

Registra lo que se ejecutó para construir el DW real (`etl_real/`) que
reemplaza el dataset simulado de InventaIO, con las cifras reales de la
corrida y cada decisión tomada. Ver también
`docs/INV-60-compatibilidad-datos.md` (diagnóstico previo) y el plan
aprobado en esta sesión.

## Actualización — clasificación de categoría definitiva

Las cifras de la sección siguiente son de la primera corrida (heurística
por palabras clave, ~60% del catálogo en "Abarrotes" por defecto). Desde
entonces la clasificación de categoría pasó por varias iteraciones hasta
llegar a una **versión definitiva revisada por el negocio, producto por
producto** (5.852 de 5.852, sin ningún default):

1. `etl_real/categoria_manual_override.csv` — la clasificación definitiva
   completa (fuente de verdad; `regla_aplicada = "revision_manual"`).
2. `etl_real/correccion_heuristica.csv` — 346 correcciones puntuales a
   colisiones de keyword encontradas auditando corridas previas (ej.
   "MOLIDA" pensada para carne también atrapaba "linaza molida"; "CAFE"
   cayendo en Bebidas en vez de la categoría nueva "Café y sustitutos").
   Hoy redundante frente a (1) porque el override ya cubre el 100% del
   catálogo, pero se deja como capa de respaldo para catálogo nuevo que
   aparezca en corridas futuras sin pasar por revisión manual.
3. **Taxonomía ampliada**: `config.CATEGORIAS_OBJETIVO` pasó de las 15
   categorías genéricas heredadas de InventaIO/Favorita a 35 categorías
   reales (Confitería, Condimentos, Aceites y sustitutos, Café y
   sustitutos, Licores, Mascotas, Medicamentos, Salsas y aderezos, etc.).
   "Delicatessen" se retiró (nunca tuvo match real); "Otros" es nueva,
   para cargos que no son mercancía.
4. **Exclusión de productos no recurrentes** (`etl_real/productos_excluidos.csv`,
   decisión validada con el negocio): 37 productos de la categoría
   "Anchetas" se excluyen de `fact_ventas`/`fact_inventario` -- cada
   "ANCHETA NAVIDEÑA 2025-18" es un código único por canasta armada esa
   temporada, nunca se repite, no es un SKU comparable para pronóstico de
   demanda. Quedan registrados en `fact_ventas_excluidos.csv` (no se
   pierden en silencio) y siguen en `dim_producto.csv` como referencia de
   catálogo. Se evaluaron también 3 productos con nombre "XXX"/"X" --
   dos de ellos (`AGUA XXX`, 872 días de venta en 3 años; `X`, 145 días)
   tienen patrón de venta real y sostenido y **no se excluyeron**; solo
   uno (`XXXXXXXXXXXXXXXX`, 8 filas sueltas, valor insignificante) se
   habría considerado ruido, pero tampoco se excluyó a pedido del
   negocio -- decisión: no tocar ningún "XXX" por nombre solo.

Cifras finales tras estos cambios: **1.603.811 filas en `fact_ventas.csv`**
(1.604.324 del ETL, menos 513 filas de las 37 Anchetas excluidas),
**9.642.247 filas en `fact_inventario.csv`** (13.474 pares
producto×sucursal, ya sin las Anchetas). El resto de las tablas
(`dim_tiempo`, `dim_sucursal`, `dim_evento`) no cambiaron.

## Corrida original (cifras heredadas, ya no vigentes en categoría/exclusión)

## Qué se construyó

Directorio `etl_real/` en este repo, un script por tabla del esquema estrella,
todos leyendo `ventas_tidy.csv` (o los CSV intermedios del paso
anterior) y escribiendo a `data/processed_real/`:

| Script | Tabla/salida | Filas generadas |
|---|---|---|
| `construir_dim_tiempo.py` | `dim_tiempo.csv` | 1.095 fechas (2023-01-02 → 2025-12-31) |
| `construir_dim_sucursal.py` | `dim_sucursal.csv` | 4 (3 reales + SIN_SUCURSAL) |
| `clasificar_productos.py` | `clasificacion_productos.csv` | 5.853 productos |
| `construir_dim_producto.py` | `dim_producto.csv` | 5.853 productos |
| `simular_proveedores.py` | `dim_proveedor.csv` + `producto_proveedor.csv` | 10 proveedores |
| `construir_dim_evento.py` | `dim_evento.csv` | 52 festivos |
| `construir_fact_ventas.py` | `fact_ventas.csv` | 1.651.292 filas |
| `simular_fact_inventario.py` | `fact_inventario.csv` | 9.663.426 filas (13.524 pares producto×sucursal) |
| `schema_dw.sql` | DDL de migración sobre `database/init.sql` de InventaIO | — |
| `cargar_postgres.py` | loader parametrizado por `DATABASE_URL` | no ejecutado aquí (sin Postgres en este entorno) |

Orden de ejecución (cada script depende del CSV que produce el
anterior): `construir_dim_tiempo.py` → `construir_dim_sucursal.py` →
`clasificar_productos.py` → `construir_dim_producto.py` →
`simular_proveedores.py` → `construir_dim_evento.py` →
`construir_fact_ventas.py` → `simular_fact_inventario.py`.

Los CSV de `data/processed_real/` **no se versionan en git** (mismo criterio que
`ventas_tidy.csv`: son artefactos regenerables, no código) — se
regeneran corriendo los scripts en orden, o se copian directo al
servidor donde se vaya a levantar Postgres.

## Decisiones y hallazgos de esta corrida

### `dim_tiempo`
Rango real 2023-01-02 a 2025-12-31 (no 2013-2017 de Favorita). Convención
`dia_semana` ISO (1=lunes...7=domingo). Se agregó `es_puente_festivo`
como columna nueva respecto al `init.sql` original de InventaIO (el ETL
real ya la calculaba por venta; se sube a nivel de fecha para no
perderla). `es_quincena`/`temporada` con la misma lógica de
`clasificar_temporada()` de InventaIO, aplicada a fechas reales.

### `dim_sucursal`
Nombres reales del crosswalk de INV-61 (`PRINCIPAL`, `LA 21`,
`GLORIETA`), no los ficticios de InventaIO. Se agregó una 4ª fila
`SIN_SUCURSAL` para las ventas de terminal `FV2` (facturación
electrónica sin punto de venta) — así `fact_ventas` nunca pierde esas
filas por falta de FK. `factor_volumen` calculado del valor de venta
real (no forzado a 5.0 como en InventaIO):

| Sucursal | factor_volumen | Volumen real (COP) |
|---|---|---|
| PRINCIPAL | 4.56 | $9.943.262.218 |
| GLORIETA | 2.06 | $4.478.726.481 |
| LA 21 | 1.00 (base) | $2.178.939.665 |
| SIN_SUCURSAL | — | $37.174.291 |

`ciudad`/`departamento` quedan vacíos — no hay dato real disponible (a
diferencia de InventaIO, que inventaba Cali/Palmira/Tuluá). El DDL se
migró a nullable para estas dos columnas.

### Clasificación de productos (`categoria`/`familia`/`es_perecedero`/`unidad_medida`)
**Heurística de palabras clave sobre `nombre_producto` — best-effort
explícito, no una clasificación validada por negocio.** El reporte
Siigo no trae ninguna de estas columnas. Resultado de la corrida:
**60% de los 5.853 productos (3.511) no calzó ninguna regla y cayó al
default `Abarrotes`** — es una tasa de cobertura baja, y probablemente
refleja que el catálogo real incluye categorías fuera de las 15
"de abarrotes" heredadas de InventaIO/Favorita (el negocio tiene
terminales de "Electrónica" en las 3 sucursales, por ejemplo, que no
tiene categoría propia en este vocabulario). **Pendiente explícito**:
revisar con negocio si hace falta ampliar `CATEGORIA_KEYWORDS` en
`etl_real/config.py` con categorías propias del catálogo real (electrónica,
ferretería, etc.) en vez de forzar todo a las categorías de un
supermercado genérico. Distribución completa en
`data/processed_real/clasificacion_productos.csv` (columna `regla_aplicada` deja
trazable qué keyword exacta clasificó cada producto).

### `dim_producto`
`codigo_item` migrado de `INTEGER` a `VARCHAR(20)` (códigos reales
alfanuméricos). `nombre` = el observado en la venta más reciente por
código (18 códigos tenían más de un nombre distinto en el histórico —
variaciones de empaque/gramaje, en algún caso reuso real del código).
**`precio_base`/`costo_base` se derivan de la última venta real
observada, no se inventan** (a diferencia de InventaIO). `iva_pct` se
calcula de la misma fila; los 0 productos sin ninguna venta con
`cantidad>0` habrían quedado con el default `19.00` del DDL (no aplicó
en esta corrida, todos los 5.853 productos tenían al menos una venta
válida).

No se resolvió en este paso la reconciliación de códigos entre el
esquema numérico (2.306 códigos, principalmente 2023) y el
alfanumérico (3.547 códigos, principalmente 2024-2025) — sigue
pendiente en `docs/INV-14-recomendaciones-eda.md`. Un mismo producto
físico que cambió de esquema aparece hoy como dos filas de
`dim_producto`.

### `dim_proveedor`
10 proveedores ficticios (mismo patrón que InventaIO), asignados por
categoría **real** clasificada arriba, no por las categorías de
Favorita. Sigue sin existir una fuente real de proveedores en los
reportes de venta — si se necesita dato real, hace falta una fuente de
compras/maestro de proveedores, no las ventas.

### `fact_ventas`
**Hallazgo de esta corrida, no anticipado en el diagnóstico previo**:
`valor_venta` en el dato real **incluye IVA** (verificado:
`valor_venta - valor_iva - costo == utilidad` reportada por Siigo, en
una muestra de 6 filas de Formato B). En la carga sintética de
InventaIO, `valor_total` era precio de lista **sin** IVA (nunca se le
sumaba el impuesto). Mismo nombre de columna en el esquema, semántica
distinta según el origen de carga — documentado también como
comentario inline en `database/init.sql`. Quien construya reportes/KPIs
sobre `fact_ventas.valor_total` debe saber que, a partir de esta carga,
esa cifra es bruta (con impuesto), no neta.

Mapeo aplicado (verificado, 0 filas descartadas de las 1.651.292):
`es_devolucion = cantidad < 0`, `cantidad`/`valor_total`/`costo_total` =
valores absolutos, `valor_unitario`/`costo_unitario` derivados
dividiendo por `cantidad` (0 filas con `cantidad==0` en esta corrida),
`en_promocion = FALSE` (no existe en el dato real), `id_proveedor` del
mapeo de `simular_proveedores.py`.

### `fact_inventario`
Mismo método de InventaIO (`stock_min/max/punto_reorden` proporcional a
`demanda_diaria`, camino aleatorio con reposición), con las dos
correcciones de `docs/INV-14-recomendaciones-eda.md` ya aplicadas:
`demanda_diaria` se divide entre todos los días de la ventana activa
(no solo los días con venta), y la grilla solo cubre esa ventana (no el
rango global de 3 años) — así no se inventa stock de un producto en una
sucursal donde nunca se vendió. Resultado: 13.524 pares
producto×sucursal con ventas reales, 9.663.426 filas de inventario
simulado (`SIN_SUCURSAL` excluido — no es una ubicación física).

**Sigue siendo 100% simulado** — no hay fuente real de inventario, ni
aquí ni (pese al nombre) en el propio InventaIO. Cualquier alerta de
desabastecimiento construida sobre esta tabla debe presentarse como tal,
no como inventario reportado.

## Verificación pendiente antes de cargar a producción

- Revisión de negocio de la clasificación de categorías (60% en el
  default es alto — ver arriba).
- Confirmar con `psql` contra un Postgres real que `database/init.sql`
  aplica sin errores y que `etl_real/cargar_postgres.py` carga correctamente
  (no se pudo probar en este entorno, no hay Postgres disponible).
- Decisión de negocio pendiente (fuera de este documento): qué hacer
  con el dataset Favorita una vez cargado el real — conservarlo como
  fixture de desarrollo en otra base, o descartarlo por completo.
