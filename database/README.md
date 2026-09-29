# database/ — Esquema estrella y verificación

| Archivo | Qué es |
|---|---|
| `init.sql` | DDL del esquema estrella (`dw.*` + `app.*`). Migrado en INV-60 para el dataset real (Siigo, desde 2022) — cada cambio respecto a la versión original (pensada para el dataset simulado Favorita) queda comentado inline: `codigo_item` alfanumérico, `dia_semana` en convención ISO, `es_puente_festivo` nueva, `ciudad`/`departamento`/`factor_volumen` de `dim_sucursal` ya no tienen un seed ficticio. Sin `INSERT` de sucursales — las carga `etl_real/cargar_postgres.py` desde datos reales. INV-20: marcas de calendario comercial y atributos de producto que usa el modelo, tabla puente `producto_proveedor`, vista `dw.v_ventas_diarias_netas` (la que lee `ml_service`) y una sección de migraciones: se puede correr sobre una base existente sin borrar datos. |
| `test-dw.SQL` | Verificación post-carga del dataset **simulado** (Favorita) — pensada para correr contra esa carga original. Sigue vigente si alguna vez se vuelve a cargar ese fixture. |
| `test-dw-real.SQL` | Verificación post-carga del dataset **real** — mismo patrón que `test-dw.SQL`, validando lo que corresponde a datos reales: `dim_tiempo` desde 2022 y más allá de la última venta (hasta 2027), festivos y cierres programados, las sucursales reales (PRINCIPAL, LA 21, GLORIETA, `SIN_SUCURSAL`, `BODEGA_CENTRAL`), `codigo_item` alfanumérico, la taxonomía de categoría, atributos de producto, `producto_proveedor`, la vista de ventas diarias y la integridad referencial. |

## Uso

```bash
psql "$DATABASE_URL" -f database/init.sql
# ... cargar datos (ver etl/README.md o etl_real/README.md según el dataset) ...
psql "$DATABASE_URL" -f database/test-dw-real.SQL    # si cargaste el dataset real
psql "$DATABASE_URL" -f database/test-dw.SQL         # si cargaste el dataset simulado
```
