# database/ — Esquema estrella y verificación

| Archivo | Qué es |
|---|---|
| `init.sql` | DDL del esquema estrella (`dw.*` + `app.*`). Migrado en INV-60 para el dataset real (Siigo, desde 2022) — cada cambio respecto a la versión original (pensada para el dataset simulado Favorita) queda comentado inline: `codigo_item` alfanumérico, `dia_semana` en convención ISO, `es_puente_festivo` nueva, `ciudad`/`departamento`/`factor_volumen` de `dim_sucursal` ya no tienen un seed ficticio. Sin `INSERT` de sucursales — las carga `etl_real/cargar_postgres.py` desde datos reales. INV-20: marcas de calendario comercial y atributos de producto que usa el modelo, tabla puente `producto_proveedor`, vista `dw.v_ventas_diarias_netas` (la que lee `ml_service`) y una sección de migraciones: se puede correr sobre una base existente sin borrar datos. INV-22: marcas de logística `requiere_frio` y `se_vende_por_kilo` en `dim_producto` (no son features del modelo). |
| `test-dw.SQL` | Verificación post-carga del dataset **simulado** (Favorita) — pensada para correr contra esa carga original. Sigue vigente si alguna vez se vuelve a cargar ese fixture. |
| `test-dw-real.SQL` | Verificación post-carga del dataset **real** — mismo patrón que `test-dw.SQL`, validando lo que corresponde a datos reales: `dim_tiempo` desde 2022 y más allá de la última venta (hasta 2027), festivos y cierres programados, las sucursales reales (PRINCIPAL, LA 21, GLORIETA, `SIN_SUCURSAL`, `BODEGA_CENTRAL`), `codigo_item` alfanumérico, la taxonomía de categoría, atributos de producto, `producto_proveedor`, la vista de ventas diarias y la integridad referencial. |
| `datos-sinteticos.sql` | Datos inventados y deterministas para las ocho tablas de `dw` (INV-34). Los usa `scripts/bd/probar.sh` en el CI para probar el traslado sin la bodega real. Se niega a correr si `dw` ya tiene filas. |

## Uso

```bash
psql "$DATABASE_URL" -f database/init.sql
# ... cargar datos (ver etl/README.md o etl_real/README.md según el dataset) ...
psql "$DATABASE_URL" -f database/test-dw-real.SQL    # si cargaste el dataset real
psql "$DATABASE_URL" -f database/test-dw.SQL         # si cargaste el dataset simulado
```

## Migración y traslado a la nube (INV-34)

`init.sql` es idempotente, así que es el paso de migración de cada despliegue. La bodega viaja a staging como un volcado de `dw` con su huella, y en el destino se valida contra esa huella. El esquema `app` y los usuarios no viajan: allá los crean `init.sql` y `python -m scripts.seed_usuarios --nube`. Diseño y decisiones: `docs/INV-34-requerimientos.md`.

| Script (`scripts/bd/`) | Qué hace |
|---|---|
| `migrar.sh` | Aplica `init.sql` |
| `volcar.sh [CARPETA]` | Vuelca `dw` y saca su huella; por defecto en `~/inventaio-volcados/AAAAMMDD-HHMM` |
| `subir_volcado.py CARPETA --bucket B` | Sube el volcado al bucket de traslado, con el perfil `inventaio-volcados` (`--simular` solo comprueba) |
| `restaurar.sh CARPETA` | Restaura solo los datos de `dw`; se niega (código 3) si ya hay filas |
| `validar.sh CARPETA` | Compara la huella del destino con la del origen: «PASÓ» (0) o «NO PASÓ» (1), sin mostrar valores |
| `probar.sh [--origen BASE]` | Todo lo anterior, de punta a punta, en bases temporales que borra al terminar |

Los scripts corren `psql`, `pg_dump` y `pg_restore` dentro de `postgres:16-alpine` y se conectan con las variables `PG*`. Contra la base del stack local:

```bash
export BD_RED=container:inventaio-db PGHOST=localhost PGUSER=inventaio_user PGDATABASE=inventaio
export PGPASSWORD=...                                # la de tu .env
bash scripts/bd/probar.sh --origen inventaio         # prueba con la bodega real (unos 8 min)
bash scripts/bd/volcar.sh                            # el volcado para staging
```
