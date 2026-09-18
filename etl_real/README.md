# etl_real/ — Pipeline de construcción del DW con datos reales (INV-60)

Construye las 7 tablas del esquema estrella (`database/init.sql`) a partir
de datos **reales** de ventas POS (Siigo, 2023-2025), reemplazando el
dataset simulado que carga `etl/` (Kaggle Corporación Favorita,
2013-2017 — ver `docs/INV-60-compatibilidad-datos.md` para el porqué no
se pueden fusionar).

No depende de ningún otro repo en tiempo de ejecución: `calendario_utils.py`
duplica a propósito las 2 funciones de festivos que necesitaba de
`parse_ventas_dir.py` (repo `ventas2`) — ver su docstring.

## Requisitos

Librería estándar de Python 3.11+ para la mayoría de los scripts
(`construir_dim_tiempo.py`, `construir_dim_sucursal.py`,
`clasificar_productos.py`, `construir_dim_producto.py`,
`simular_*.py`, `construir_dim_evento.py`, `construir_fact_ventas.py`).
Dos excepciones necesitan `pandas`/`openpyxl` para leer el Excel de
inventario (INV-61):

```bash
pip install pandas openpyxl
```

- `validar_inventario.py`
- `construir_fact_inventario_real.py`

Y `cargar_postgres.py` (el paso de carga a Postgres) necesita:

```bash
pip install psycopg2-binary
```

## Insumos de entrada

Cuatro archivos que produce/mantiene el repo `ventas2`, no versionados
aquí (regla `*.csv`/`*.xlsx` del `.gitignore`) — cópialos o
symlink-éalos a `data/raw_real/` antes de correr nada:

```bash
mkdir -p data/raw_real/inventario
cp /ruta/a/ventas2/festivos_colombia_2022_2026.csv data/raw_real/
cp /ruta/a/ventas2/terminal_sucursal.csv data/raw_real/
ln -s /ruta/a/ventas2/ventas_tidy.csv data/raw_real/ventas_tidy.csv
cp /ruta/a/ventas2/inventario/inventarioooo.xlsx data/raw_real/inventario/
```

Rutas configurables por variable de entorno si no siguen esta convención:
`VENTAS_TIDY_CSV`, `FESTIVOS_CSV`, `TERMINAL_SUCURSAL_CSV`,
`INVENTARIO_XLSX` (ver `config.py`) — este último, INV-61, es el
inventario físico real (foto a corte 2025-12-31), no una serie diaria.

## Archivos de decisión de negocio (sí versionados)

A diferencia de los insumos de arriba, estos 3 CSV **sí están en git**
(excepción explícita en `.gitignore` a la regla `*.csv` general) porque no
son datos regenerables — son decisiones tomadas producto por producto:

| Archivo | Contenido | Cobertura |
|---|---|---|
| `categoria_manual_override.csv` | Clasificación de categoría **definitiva**, revisada por el negocio producto por producto | 5.852 de 5.852 (100% del catálogo) |
| `correccion_heuristica.csv` | Correcciones puntuales a colisiones de keyword detectadas en auditoría (ej. "MOLIDA" pensada para carne también atrapaba "linaza molida") — hoy redundante frente al override, queda como capa de respaldo para catálogo nuevo que no haya pasado por revisión manual | 346 productos |
| `productos_excluidos.csv` | Productos excluidos, con su `motivo`. Dos motivos hoy: `ancheta_no_recurrente` (37 canastas navideñas, cada una un código único que no se repite — solo se excluyen de `fact_ventas`, siguen en `dim_producto.csv` como referencia) y **`sin_inventario_dic2025`** (INV-61 — productos sin registro en el inventario real de diciembre 2025, se **eliminan del catálogo por completo**, ver más abajo) | 37 + ~1.471 productos |

`clasificar_productos.py` usa estas 3 fuentes en ese orden de prioridad
sobre la heurística de palabras clave (`config.CATEGORIA_KEYWORDS`), que
solo aplica a catálogo nuevo no cubierto por ninguna de las tres.

## Cómo correr (orden obligatorio)

`construir_dim_producto.py` corre **dos veces**: la primera pasada
produce el catálogo completo que `validar_inventario.py` necesita para
la doble validación; la segunda (tras `validar_inventario.py`) excluye
del catálogo los productos sin inventario real (INV-61).

```bash
python construir_dim_tiempo.py             # dim_tiempo.csv
python construir_dim_sucursal.py           # dim_sucursal.csv (incluye BODEGA_CENTRAL)
python clasificar_productos.py             # clasificacion_productos.csv
python construir_dim_producto.py           # pasada 1: catálogo completo
python validar_inventario.py               # doble validación contra el inventario real
python construir_dim_producto.py           # pasada 2: catálogo final, dim_producto.csv
python simular_proveedores.py              # dim_proveedor.csv + producto_proveedor.csv
python construir_dim_evento.py             # dim_evento.csv
python construir_fact_ventas.py            # fact_ventas.csv (+ fact_ventas_excluidos.csv)
python construir_fact_inventario_real.py   # fact_inventario.csv, foto real a 2025-12-31
```

Todo queda en `data/processed_real/` (distinto de `data/processed/`, que
es del pipeline Favorita — no se mezclan).

`simular_fact_inventario.py` (camino aleatorio con reposición, serie
diaria completa) se deja en el repo como referencia histórica —
**ya no forma parte de la cadena de construcción**, la reemplazó
`construir_fact_inventario_real.py`.

### Inventario real y doble validación (INV-61)

`data/raw_real/inventario/inventarioooo.xlsx` es una foto física del
inventario a corte **2025-12-31** (no una serie diaria) por
`(codigo_item, bodega)`. Mapeo de bodega del Excel a `sucursal` del DW:

| Bodega en el Excel | Sucursal en el DW | Nota |
|---|---|---|
| `ALMACEN PRINCIPAL` | `PRINCIPAL` | sucursal física real |
| `ALMACEN LA GLORIETA` | `GLORIETA` | sucursal física real |
| `ALMACEN LA 21` | `LA 21` | sucursal física real |
| `BODEGA PRINCIPAL` | **`BODEGA_CENTRAL`** | acopio central — el producto existe pero no se ha movilizado a ninguna sucursal. **No es la sucursal PRINCIPAL** aunque el nombre se parezca |
| cualquier otra bodega | — | fuera del mapeo conocido, queda en `data/processed_real/inventario_ubicaciones_excluidas.csv`, no entra a `fact_inventario.csv` |

`validar_inventario.py` aplica dos validaciones pedidas por el negocio:

1. Ítems de **ventas sin inventario** → eliminados de `dim_producto.csv`
   (motivo `sin_inventario_dic2025` en `productos_excluidos.csv`).
2. Ítems de **inventario sin ninguna venta** en el histórico → documentados
   en `data/processed_real/productos_inventario_sin_ventas.csv`, excluidos
   de `fact_inventario.csv` (no hay FK válido en `dim_producto`).

Ver `docs/INV-61-inventario-real.md` para las cifras exactas de esta
corrida.

## Cargar a Postgres

```bash
psql "$DATABASE_URL" -f ../database/init.sql       # esquema ya migrado para datos reales
pip install psycopg2-binary
DATABASE_URL=postgresql://usuario:clave@host:5432/inventaio python cargar_postgres.py
```

Trunca todas las tablas `dw.*` y recarga — **reemplazo total del dataset
simulado, no fusión** (ver `docs/INV-60-compatibilidad-datos.md`).

## Pruebas

```bash
python -m unittest discover -s tests -v
```

`tests/test_etl_real.py` cubre las funciones puras (sin necesitar
Postgres ni los CSV completos de producción): clasificación por keyword,
carga de los 3 CSV de override, cálculo de festivos/puentes, cobertura
completa de `categoria_manual_override.csv` contra `CATEGORIAS_OBJETIVO`.
Para validar la carga completa en una base real, corre
`database/test-dw-real.SQL` después de `cargar_postgres.py` (mismo
patrón que `database/test-dw.SQL` usa para el dataset simulado).

## Qué queda pendiente

Ver `docs/INV-60-tutorial-migracion.md` (tutorial paso a paso completo,
con verificación post-carga) y `docs/INV-60-notas-migracion-dw.md`
(decisiones y cifras de cada corrida). Reconciliación de `api/` y
`frontend/` contra este contrato de datos: fuera de alcance de INV-60.
