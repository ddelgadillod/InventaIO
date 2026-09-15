# INV-60 — Tutorial: migrar el DW simulado al DW real

Guía paso a paso para reemplazar el dataset simulado (Kaggle Favorita,
2013-2017) por el dataset real de ventas POS (Siigo, 2023-2025) en el
esquema estrella de InventaIO. Contexto completo en
`docs/INV-60-compatibilidad-datos.md` (por qué no se puede fusionar) y
`docs/INV-60-notas-migracion-dw.md` (qué se decidió y qué dio la corrida).

El pipeline vive en `etl_real/` (paralelo a `etl/`, que sigue siendo el
pipeline del dataset Favorita/sintético — no se borró, sigue disponible
como referencia histórica). `etl_real/` no depende de ningún otro repo
en tiempo de ejecución: solo necesita que le acerques 3 archivos de
entrada.

## Prerrequisitos

- Python 3.11+ con `psycopg2-binary` si vas a cargar a Postgres
  (`etl_real/` en sí no necesita pandas ni ninguna otra dependencia,
  solo librería estándar).
- Un Postgres 16 accesible (local o remoto) para el paso final de
  carga — no hace falta para generar los CSV.
- Los 3 archivos de entrada, producidos por el repo
  [ventas2](../../ventas2) (o el que sea la fuente del ETL de ventas
  real en tu entorno):
  - `ventas_tidy.csv` (salida de `parse_ventas_dir.py`, INV-61)
  - `festivos_colombia_2022_2026.csv`
  - `terminal_sucursal.csv`

## Paso 1 — Poner los insumos en `data/raw_real/`

```bash
mkdir -p data/raw_real
cp /ruta/a/ventas2/festivos_colombia_2022_2026.csv data/raw_real/
cp /ruta/a/ventas2/terminal_sucursal.csv data/raw_real/

# ventas_tidy.csv puede pesar varios cientos de MB -- symlink en vez de
# copiar si ventas2 vive en la misma máquina:
ln -s /ruta/a/ventas2/ventas_tidy.csv data/raw_real/ventas_tidy.csv
# o, si prefieres una copia física:
# cp /ruta/a/ventas2/ventas_tidy.csv data/raw_real/
```

`data/raw_real/` (igual que `data/raw/` y `data/processed/` del
pipeline Favorita) está excluido de git por la regla `*.csv` del
`.gitignore` — no hace falta tocarlo, ya cubre estos archivos también.

Si tus rutas no siguen esta convención, cada script acepta override por
variable de entorno: `VENTAS_TIDY_CSV`, `FESTIVOS_CSV`,
`TERMINAL_SUCURSAL_CSV` (ver `etl_real/config.py`).

## Paso 2 — Generar las tablas del DW

Orden obligatorio (cada paso depende del CSV que produce el anterior):

```bash
cd etl_real
python construir_dim_tiempo.py       # dim_tiempo.csv
python construir_dim_sucursal.py     # dim_sucursal.csv
python clasificar_productos.py       # clasificacion_productos.csv (heurística, revisar)
python construir_dim_producto.py     # dim_producto.csv
python simular_proveedores.py        # dim_proveedor.csv + producto_proveedor.csv
python construir_dim_evento.py       # dim_evento.csv
python construir_fact_ventas.py      # fact_ventas.csv
python simular_fact_inventario.py    # fact_inventario.csv (tarda varios minutos, ~10M filas)
```

Todo queda en `data/processed_real/` (distinto de `data/processed/`,
que es del pipeline Favorita — no se mezclan). Cada script imprime sus
propias cifras de control (conteos, advertencias) al terminar.

**Antes de seguir al paso 3**, revisa la salida de
`clasificar_productos.py`: en la corrida de referencia, un 60% del
catálogo cayó en la categoría por defecto (`Abarrotes`) porque la
heurística de palabras clave (`etl_real/config.py::CATEGORIA_KEYWORDS`)
está pensada para categorías de supermercado y el catálogo real puede
traer líneas de producto que no calzan ahí (ej. electrónica). Si tu
corrida da un porcentaje similar, vale la pena ampliar
`CATEGORIA_KEYWORDS` con categorías propias del negocio antes de cargar
a producción — no es obligatorio para que el pipeline funcione, pero sí
para que `dim_producto.categoria` sea útil.

## Paso 3 — Aplicar el DDL migrado

`database/init.sql` ya tiene los cambios de INV-60 aplicados
(`codigo_item` como texto, `dia_semana` en convención ISO, sin seed
ficticio de sucursales, columna `es_puente_festivo` nueva — cada cambio
está comentado inline en el archivo). Es el único DDL — no hay un
archivo de migración separado.

```bash
psql "$DATABASE_URL" -f database/init.sql
```

Si la base ya existía con el esquema viejo (`codigo_item INTEGER`),
vas a necesitar migrar esa columna a mano antes de que el `CREATE TABLE
IF NOT EXISTS` no alcance a corregirla — en una base nueva no aplica.

## Paso 4 — Cargar a Postgres

```bash
pip install psycopg2-binary
DATABASE_URL=postgresql://usuario:clave@host:5432/inventaio \
    python etl_real/cargar_postgres.py
```

Esto **trunca todas las tablas `dw.*`** (reemplazo total del dataset
simulado, no fusión — ver `docs/INV-60-compatibilidad-datos.md`) y
carga las 7 tablas en orden (dimensiones primero, luego los hechos
resolviendo FKs por lookup). Imprime un reporte final con conteos por
tabla.

No se ejecutó en esta sesión de trabajo por no haber Postgres
disponible en el entorno de desarrollo — pruébalo primero contra una
base de prueba antes de correrlo contra producción.

## Verificación rápida post-carga

```sql
-- Debe dar 3 sucursales reales + SIN_SUCURSAL, no las ficticias de Favorita
SELECT nombre FROM dw.dim_sucursal;

-- Debe estar en el rango 2023-2025, no 2013-2017
SELECT MIN(fecha), MAX(fecha) FROM dw.dim_tiempo;

-- codigo_item debe aceptar valores alfanuméricos
SELECT codigo_item FROM dw.dim_producto WHERE codigo_item ~ '^[A-Z]' LIMIT 5;
```

## Qué queda pendiente después de esto

- Revisión de negocio de `clasificacion_productos.csv` (ver Paso 2).
- Reconciliación de API/frontend/`app.usuarios` contra el nuevo
  contrato de datos (fuera de alcance de INV-60) — en particular, la
  API/frontend puede asumir la convención `dia_semana` 0-6 vieja o los
  3 nombres de sucursal ficticios; hay que revisar `api/` y
  `frontend/src/` contra los cambios de este documento antes de
  exponerlo a usuarios reales.
- Decisión de negocio sobre qué hacer con el dataset Favorita: se deja
  de cargar aquí, pero el pipeline (`etl/paso_01..04.py`) no se borró
  por si sirve como fixture de desarrollo en otro ambiente.
