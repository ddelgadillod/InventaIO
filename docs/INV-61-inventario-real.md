# INV-61 — Inventario físico real y datos faltantes de 2023

Registra lo que se incorporó a `etl_real/` al reemplazar
`simular_fact_inventario.py` por el inventario físico real
(`data/raw_real/inventario/inventarioooo.xlsx`, corte 2025-12-31) y al
completar los reportes de ventas de 2023 que faltaban en el repo
`ventas2` (insumo de `data/raw_real/ventas_tidy.csv`). No cubre las
notebooks de EDA/feature engineering ni el modelo baseline — eso queda
en `docs/INV-14-eda-resumen.md`, `docs/INV-15-feature-engineering.md` y
`docs/INV-17-modelo-baseline.md`.

## 1. Datos faltantes de 2023 (en `ventas2`, insumo de este repo)

`ventas_tidy.csv` pasó de ~1,5M a **1.716.107 registros** al agregar los
reportes de marzo-abril y noviembre-diciembre de 2023 que faltaban.
**Los huecos de calendario de noviembre y diciembre de 2023 quedaron
cerrados por completo** (antes 100% hueco, ahora cobertura completa) —
el único bloque grande de hueco que queda es dentro de `en fe 2023.xlsx`
(2 al 21 de febrero, 23 días), un hueco genuino de origen, no un archivo
faltante. Efecto para InventaIO: los términos de calendario/estacionalidad
que se calculan en la etapa de EDA (INV-14) ahora tienen 3
observaciones-año (2023, 2024, 2025) en vez de 2.

33 productos nuevos aparecieron en el catálogo por los meses agregados
(5.852 → 5.885 códigos antes de la validación de inventario de abajo).

## 2. Inventario real (`data/raw_real/inventario/inventarioooo.xlsx`)

Conteo físico por ítem x bodega a corte **2025-12-31** (una sola fecha,
no una serie diaria). Columnas: `Referencia` (código), `Detalle`
(nombre), `Bodega`, `Cantidad`. 11.371 filas crudas (una fila de totales
al final, descartada por no ser un registro).

### Mapeo de bodega → sucursal (`etl_real/validar_inventario.py`,
`etl_real/construir_fact_inventario_real.py`)

| Bodega en el Excel | Sucursal en el DW | Nota |
|---|---|---|
| `ALMACEN PRINCIPAL` | `PRINCIPAL` | sucursal física real |
| `ALMACEN LA GLORIETA` | `GLORIETA` | sucursal física real |
| `ALMACEN LA 21` | `LA 21` | sucursal física real |
| `BODEGA PRINCIPAL` | **`BODEGA_CENTRAL`** (fila nueva en `dim_sucursal.csv`) | acopio central — el producto existe pero no se ha movilizado a ninguna sucursal. **No es la sucursal PRINCIPAL** aunque el nombre se parezca |
| cualquier otra bodega (ej. `ALMACEN SABOYA`, 1 fila) | — | fuera de las 3 sucursales + bodega central conocidas, queda en `data/processed_real/inventario_ubicaciones_excluidas.csv`, fuera de `fact_inventario.csv` |

`BODEGA_CENTRAL` no vende directo al público — no tiene `factor_volumen`
ni `volumen_real_cop` en `dim_sucursal.csv` (igual que `SIN_SUCURSAL`).

### Doble validación pedida por el negocio (`etl_real/validar_inventario.py`)

1. **Ítems de ventas sin inventario → eliminados del catálogo.** ~1.471
   códigos con historial de venta no aparecen en el inventario de
   diciembre 2025 (de 5.885 productos del catálogo completo). Se
   agregan a `etl_real/productos_excluidos.csv` con motivo
   `sin_inventario_dic2025` — a diferencia de `ancheta_no_recurrente`
   (que solo excluye de `fact_ventas` y deja el producto en
   `dim_producto.csv` como referencia), estos se **eliminan por
   completo** del catálogo (`dim_producto.csv`: 5.885 → ~4.414 filas),
   por pedido explícito del negocio. Los códigos que ya estaban
   excluidos como Anchetas conservan ese motivo original — no se
   duplica la fila (`validar_inventario.fusionar_exclusiones()`,
   cubierto por `tests/test_etl_real.py`).
2. **Ítems de inventario sin ninguna venta en el histórico → documentados
   y excluidos de `fact_inventario`.** ~193 códigos del inventario nunca
   aparecen en `ventas_tidy.csv` — violan la expectativa "todo lo que
   está en inventario debería existir en ventas". Quedan en
   `data/processed_real/productos_inventario_sin_ventas.csv` (código,
   nombre, cantidad total) y fuera de `fact_inventario.csv` porque no
   hay una fila válida de `dim_producto` para el FK (no se inventa una).

### `fact_inventario.csv` real (`etl_real/construir_fact_inventario_real.py`)

~11.035 filas (antes: ~9,6M filas simuladas por
`simular_fact_inventario.py`, que se deja en el repo como referencia
histórica, ya no forma parte de la cadena de construcción) — una fila
por `(codigo_item, sucursal)` con registro real en el Excel, fecha fija
`2025-12-31`. `stock_disponible` es 100% real, incluyendo filas con
cantidad negativa (backorder/descuadre del sistema del negocio — no se
corrigen a 0 sin evidencia de error de captura).
`stock_minimo`/`stock_maximo`/`punto_reorden`/`dias_cobertura` son NOT
NULL en el DDL pero no vienen en el Excel: se derivan con la fórmula de
política ya existente (`config.INVENTARIO_PARAMS`), aplicada a la tasa
de demanda real observada en `fact_ventas.csv` — aproximación de
política documentada, no dato real. Para `BODEGA_CENTRAL` (sin demanda
propia por sucursal) se usa como proxy la demanda total de la empresa
para ese producto. `dias_cobertura` usa el centinela `999.0` cuando la
demanda observada en esa sucursal puntual es 0.

## Verificación de esta corrida

```bash
pytest etl_real/tests/
```

Recuentos esperados (comparar contra la salida real de
`construir_dim_producto.py`/`construir_fact_inventario_real.py` en este
checkout — pueden variar levemente si el catálogo de `ventas2` cambió
desde que se escribió este documento):

- `dim_producto.csv`: ~4.414 productos (tras las dos pasadas)
- `fact_inventario.csv`: ~11.035 filas
- `productos_excluidos.csv`: 37 (`ancheta_no_recurrente`) + ~1.471
  (`sin_inventario_dic2025`), sin códigos duplicados entre motivos

## Pendiente / fuera de alcance de esta HU

- Revisión manual del negocio para los productos nuevos del catálogo sin
  clasificación validada (`data/processed_real/productos_nuevos_pendiente_revision.csv`).
- Confirmar con el negocio la ubicación `ALMACEN SABOYA` (¿4ª ubicación
  real que falta mapear, o error de captura?).
- Confirmar si los productos eliminados por `sin_inventario_dic2025`
  deben quedar eliminados permanentemente o son temporada/pausados.
- Si en el futuro se consigue una serie de inventario con más de una
  fecha (no solo un corte anual), reevaluar el diagnóstico de "Nivel 2
  supervisado" en la etapa de feature engineering (INV-15).
- EDA, feature engineering y modelo baseline sobre este dato: HU INV-14,
  INV-15, INV-17 respectivamente (fuera de alcance de esta HU de ETL).
