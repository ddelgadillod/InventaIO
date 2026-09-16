# INV-60 — Compatibilidad entre el dataset real (ETL ventas2) y el dataset simulado (InventaIO)

Documenta la comparación entre `ventas_tidy.csv` (INV-61, este repo) y el
esquema estrella + datos que carga el pipeline de
[InventaIO](https://github.com/ddelgadillod/InventaIO)
(`database/init.sql` + `etl/paso_01..04`). Por ahora el foco es **solo
datos** — la reconciliación de API/frontend/auth queda fuera de alcance
de este documento, registrada como pendiente al final.

## Veredicto

**La compatibilidad es de esquema (forma de las tablas), no de datos.**
El dataset que hoy carga InventaIO a `dw.*` no es una muestra real de la
operación — es el dataset público de Kaggle *Corporación Favorita
Grocery Sales Forecasting* (una cadena ecuatoriana, 2013–2017)
remapeado con nombres y precios colombianos ficticios. No hay ningún
puente real entre sus ~200 productos sintéticos y el catálogo real de
Siigo, ni traslape de fechas entre su rango (2013–2017) y el nuestro
(2023–2025). Intentar "fusionar" ambos datasets a nivel de fila no
tiene sentido — lo único reconciliable es la estructura de las tablas,
para que la carga real (INV-61 → INV-60) reemplace en bloque los datos
sintéticos, no los combine con ellos.

Fuente de esta caracterización: `docs/confluence-bodega-datos.html` del
repo InventaIO lo confirma explícitamente: *"Los datos combinan
registros reales del dataset Corporación Favorita Grocery Sales
Forecasting (Kaggle) con datos sintéticos complementarios... Rango
temporal ~4 años (datos Favorita 2013–2017, adaptados)"*.

## Qué es realmente el dataset "simulado" (`etl/paso_01..04` de InventaIO)

1. **`paso_01_transformar.py`**: toma `train.csv`/`items.csv`/`stores.csv`
   de Favorita, elige al azar (semilla fija 42) 3 tiendas ecuatorianas y
   ~200 productos balanceados en 15 categorías, y las mapea a
   "Sucursal Principal/Norte/Sur". Aplica un factor de corrección para
   forzar que Principal tenga ~5x el volumen de las otras dos — es una
   restricción de diseño impuesta, no una medición.
2. **`paso_02_sinteticos.py`**: inventa precios/costos/márgenes por
   categoría (rangos COP hardcodeados), 10 proveedores ficticios, y
   genera `fact_inventario` con una simulación de random walk
   (demanda promedio observada × parámetros de cobertura, con reposición
   cuando el stock cruza el punto de reorden). **Ver nota abajo — este
   método sí es reutilizable como precedente para nuestra propia
   simulación de inventario.**
3. **`paso_04_cargar.py`**: el nombre de cada producto cargado es
   literalmente `f"{categoria} - Item {codigo_item}"` — no hay nombres
   de producto reales en ningún punto del pipeline simulado.

## Comparación esquema por esquema

### `dim_tiempo`
- Convención de `dia_semana` distinta: InventaIO usa `0=lunes...6=domingo`
  (`.dt.weekday`); nuestro `dia_semana_num` usa ISO `1=lunes...7=domingo`.
  Hay que elegir un único estándar antes de cargar (recomendado: ISO,
  ya en uso en nuestro ETL).
- InventaIO agrega `es_quincena` y `temporada` (navidad/escolar/semana
  santa/vacaciones/halloween/black_friday/regular), que nuestro ETL
  todavía no calcula — extensión pendiente si se quiere paridad de
  features de calendario.
- **Festivos — validado cruzando ambas implementaciones**: comparé
  `festivos_colombia_2022_2026.csv` (librería `holidays`, la que usa
  nuestro ETL) contra `generar_festivos_colombia()` de
  `etl/config.py` de InventaIO (algoritmo propio, independiente) para
  el rango 2022–2025 (traslape entre ambos): **las 71 fechas coinciden
  exactamente**, cero discrepancias de fecha. Solo difiere el texto del
  nombre (p.ej. `"Día de los Reyes Magos (observado)"` vs `"Día de los
  Reyes Magos"`, `"La Asunción"` vs `"Asunción de la Virgen"`) — es
  cosmético, no afecta ningún join (las cargas unen por `fecha`, no por
  nombre), pero vale la pena unificar el texto si ambos sistemas van a
  convivir.

### `dim_sucursal`
- InventaIO: 3 sucursales ficticias. **Inconsistencia interna detectada
  en su propio repo**: `database/init.sql` las siembra en
  `Cali/Palmira/Tuluá` (Valle del Cauca), pero `etl/config.py`
  (`SUCURSALES`) las define en ciudades genéricas `Centro/Norte/Sur` —
  dos fuentes de verdad distintas para el mismo dato dentro de su propio
  proyecto.
- Real (INV-61): 3 sucursales físicas identificadas por el crosswalk
  `terminal_pos→sucursal`: `PRINCIPAL`, `LA 21`, `GLORIETA` — sin
  ciudad conocida (el reporte Siigo no la trae).
- Coincide el **conteo** (3 sucursales) pero no los nombres ni la
  geografía. `factor_volumen=5.0` para Principal en InventaIO es un
  parámetro de diseño forzado, no algo medido — con el dato real ya se
  puede calcular la proporción real de volumen entre `PRINCIPAL`,
  `LA 21` y `GLORIETA` en vez de asumir 5x.

### `dim_producto`
- **Incompatibilidad estructural real**: `codigo_item INTEGER NOT NULL
  UNIQUE` en el DDL de InventaIO. Los códigos reales de Siigo son
  alfanuméricos (`P841`, `P31`, `P4`) — no calzan en una columna
  `INTEGER`. Hay que migrar la columna a `VARCHAR` antes de cargar dato
  real (rompe la carga simulada actual, que sí depende de que
  `item_nbr` de Favorita sea numérico).
- El catálogo completo (~200 productos, familia/categoría/es_perecedero/
  precio_base/costo_base/margen_pct) es sintético de punta a punta, sin
  ninguna correspondencia con el catálogo real. Estos campos
  (`familia`, `categoria`, `es_perecedero`) tampoco existen en el
  reporte Siigo — para el catálogo real habría que clasificarlos a mano
  o con reglas antes de poder poblar `dim_producto` con datos reales.

### `dim_proveedor`
- 10 proveedores 100% ficticios. Los reportes de venta Siigo no traen
  ninguna información de proveedor por línea — esta dimensión está
  fuera del alcance de lo que el ETL de ventas puede producir; si se
  quiere llenar con datos reales hace falta una fuente distinta (compras
  o maestro de proveedores), no las ventas.

### `fact_ventas`
- Grano compatible: producto × sucursal × tiempo en ambos.
- Diferencias de columnas a mapear:
  - `valor_venta` (nuestro, agregado) → `valor_total` (InventaIO);
    `valor_unitario` no existe en el dato real y habría que derivarlo
    (`valor_venta / cantidad`), con el riesgo de que en filas Formato
    B/C/D `cantidad`/`valor_venta` ya vienen agregados por día, no por
    unidad vendida individual.
  - `es_devolucion` (booleano, InventaIO) vs. nuestras columnas
    separadas `cant_devolucion`/`valor_devolucion` que conviven en la
    misma fila que la venta (Formato B agregado) o aparecen en su
    propia sección `***DEVOLUCIONES` (Formato C) — decisión pendiente
    de si las devoluciones se expanden a filas propias con
    `es_devolucion=true` para calzar el modelo de InventaIO, respetando
    la decisión ya tomada en INV-61 de tratarlas como señal separada,
    no neteada.
  - `en_promocion` no existe en el dato real (Siigo no lo reporta por
    línea).
  - `id_proveedor` no tiene equivalente real (ver `dim_proveedor`
    arriba) — quedaría `NULL` (la columna ya es nullable en el DDL).

### `fact_inventario`
- Mismo problema que ya documentamos en INV-61: **no existe una fuente
  real de inventario**, ni en nuestros datos ni — a pesar del nombre —
  en los de InventaIO, que también son 100% simulados.
- Lo rescatable: el método de simulación de InventaIO (`stock_minimo =
  demanda_diaria × 3 días`, `stock_maximo = demanda_diaria × 30 días`,
  `punto_reorden = demanda_diaria × 7 días`, más una caminata aleatoria
  día a día con reposición al cruzar el punto de reorden) es un
  precedente concreto y reutilizable para la simulación de inventario
  que se planteó para las 3 sucursales reales — se puede adaptar
  reemplazando su `demanda_diaria` sintética por la demanda real
  promedio de `ventas_tidy.csv` por (`codigo_producto`, `sucursal`).
  Nota: su cálculo de `demanda_diaria` divide la suma de ventas entre
  el número de *días con venta registrada*, no entre todos los días del
  calendario — es un sesgo al alza que conviene no repetir sin más al
  adaptarlo (ver `docs/INV-14-recomendaciones-eda.md`, ventana activa
  por producto×sucursal).

## Resumen de incompatibilidades por severidad

| Elemento | Severidad | Tipo |
|---|---|---|
| Rango temporal sin traslape (2013–2017 vs 2023–2025) | Crítica | Datos — no se puede fusionar, solo reemplazar |
| Catálogo de productos sin correspondencia real | Crítica | Datos — requiere reemplazo completo del catálogo |
| `codigo_item INTEGER` vs códigos alfanuméricos reales | Alta | Esquema — requiere migración de columna |
| Convención `dia_semana` (0–6 vs ISO 1–7) | Media | Esquema — requiere decisión de estándar único |
| Nombres/geografía de `dim_sucursal` ficticios | Media | Datos — requiere reemplazo de seed |
| `dim_proveedor` sin fuente real | Media | Alcance — necesita fuente de datos distinta |
| Mapeo `valor_venta`→`valor_total`/`valor_unitario` | Baja | Esquema — mapeo directo, con caveat de agregación |
| Nombre de festivos (texto, no fecha) | Baja | Cosmético — validado sin impacto funcional |

## Fuera de alcance de este documento

- Reconciliación de API (`api/`), frontend (`frontend/`) y autenticación
  (`app.usuarios`) del repo InventaIO — se aborda en una siguiente
  etapa, una vez el modelo de datos esté decidido.
- Decisión de negocio sobre si el dataset Favorita se conserva como
  fixture de desarrollo/demo (para probar la app sin esperar el
  histórico completo real) o se descarta por completo una vez haya
  carga real — este documento solo deja registrada la evidencia de que
  **no son datos combinables**, la decisión de qué hacer con el fixture
  es de producto.
