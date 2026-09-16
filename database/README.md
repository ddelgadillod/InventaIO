# database/ — Esquema estrella y verificación

| Archivo | Qué es |
|---|---|
| `init.sql` | DDL del esquema estrella (`dw.*` + `app.*`). Migrado en INV-60 para el dataset real (Siigo, 2023-2025) — cada cambio respecto a la versión original (pensada para el dataset simulado Favorita) queda comentado inline: `codigo_item` alfanumérico, `dia_semana` en convención ISO, `es_puente_festivo` nueva, `ciudad`/`departamento`/`factor_volumen` de `dim_sucursal` ya no tienen un seed ficticio. Sin `INSERT` de sucursales — las carga `etl_real/cargar_postgres.py` desde datos reales. |
| `test-dw.SQL` | Verificación post-carga del dataset **simulado** (Favorita) — pensada para correr contra esa carga original. Sigue vigente si alguna vez se vuelve a cargar ese fixture. |
| `test-dw-real.SQL` | Verificación post-carga del dataset **real** (INV-60) — mismo patrón que `test-dw.SQL`, pero validando lo que corresponde a datos reales: rango de fechas 2023-2025 (no 2013-2017), las 3 sucursales reales + `SIN_SUCURSAL` (no las ficticias), `codigo_item` alfanumérico, la taxonomía de categoría de 35 valores, y que `fact_ventas`/`fact_inventario` no incluyan los productos de `etl_real/productos_excluidos.csv`. |

## Uso

```bash
psql "$DATABASE_URL" -f database/init.sql
# ... cargar datos (ver etl/README.md o etl_real/README.md según el dataset) ...
psql "$DATABASE_URL" -f database/test-dw-real.SQL    # si cargaste el dataset real
psql "$DATABASE_URL" -f database/test-dw.SQL         # si cargaste el dataset simulado
```
