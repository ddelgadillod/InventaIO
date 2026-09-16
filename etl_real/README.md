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

Solo librería estándar de Python 3.11+ para generar los CSV
(`construir_*.py`, `clasificar_productos.py`, `simular_*.py`). Únicamente
`cargar_postgres.py` (el paso de carga a Postgres) necesita una
dependencia externa:

```bash
pip install psycopg2-binary
```

## Insumos de entrada

Tres archivos que produce el ETL real de ventas (repo `ventas2`), no
versionados aquí (regla `*.csv` del `.gitignore`) — cópialos o
symlink-éalos a `data/raw_real/` antes de correr nada:

```bash
mkdir -p data/raw_real
cp /ruta/a/ventas2/festivos_colombia_2022_2026.csv data/raw_real/
cp /ruta/a/ventas2/terminal_sucursal.csv data/raw_real/
ln -s /ruta/a/ventas2/ventas_tidy.csv data/raw_real/ventas_tidy.csv
```

Rutas configurables por variable de entorno si no siguen esta convención:
`VENTAS_TIDY_CSV`, `FESTIVOS_CSV`, `TERMINAL_SUCURSAL_CSV` (ver `config.py`).

## Archivos de decisión de negocio (sí versionados)

A diferencia de los insumos de arriba, estos 3 CSV **sí están en git**
(excepción explícita en `.gitignore` a la regla `*.csv` general) porque no
son datos regenerables — son decisiones tomadas producto por producto:

| Archivo | Contenido | Cobertura |
|---|---|---|
| `categoria_manual_override.csv` | Clasificación de categoría **definitiva**, revisada por el negocio producto por producto | 5.852 de 5.852 (100% del catálogo) |
| `correccion_heuristica.csv` | Correcciones puntuales a colisiones de keyword detectadas en auditoría (ej. "MOLIDA" pensada para carne también atrapaba "linaza molida") — hoy redundante frente al override, queda como capa de respaldo para catálogo nuevo que no haya pasado por revisión manual | 346 productos |
| `productos_excluidos.csv` | Productos que no son SKU recurrentes comparables, excluidos de `fact_ventas`/`fact_inventario` (nunca de `dim_producto`, que los conserva como referencia) — hoy: las 37 "Anchetas" navideñas, cada una un código único por canasta armada esa temporada que no se repite | 37 productos |

`clasificar_productos.py` usa estas 3 fuentes en ese orden de prioridad
sobre la heurística de palabras clave (`config.CATEGORIA_KEYWORDS`), que
solo aplica a catálogo nuevo no cubierto por ninguna de las tres.

## Cómo correr (orden obligatorio)

```bash
python construir_dim_tiempo.py       # dim_tiempo.csv
python construir_dim_sucursal.py     # dim_sucursal.csv
python clasificar_productos.py       # clasificacion_productos.csv
python construir_dim_producto.py     # dim_producto.csv
python simular_proveedores.py        # dim_proveedor.csv + producto_proveedor.csv
python construir_dim_evento.py       # dim_evento.csv
python construir_fact_ventas.py      # fact_ventas.csv (+ fact_ventas_excluidos.csv)
python simular_fact_inventario.py    # fact_inventario.csv (tarda varios minutos, ~10M filas)
```

Todo queda en `data/processed_real/` (distinto de `data/processed/`, que
es del pipeline Favorita — no se mezclan).

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
