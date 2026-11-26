# INV-82 · Análisis de ventas en Vera y montos de la bodega sin IVA · Requerimientos

| Campo | Valor |
| --- | --- |
| Jira | INV-82 «Vera no compara periodos entre años ni arma consultas compuestas, y la bodega mezcla ventas con y sin IVA» · Error · Sprint 8 · Release 4 · vence el 4-dic |
| Depende de | La bodega al 30-sep-2026 (INV-63, decisión 43) y el staging en k3s (INV-69) |
| Alimenta a | La primera versión de producción, v4.0.0-rc.1 (7-dic), y las pruebas con usuarios (INV-38, 8 al 10-dic) |
| Rama | `fix/INV-82-analisis-ventas`, desde `develop` (`b53ca34`) |

Revisión del 26 de noviembre de 2026 contra `develop`, la bodega local y el staging en k3s. El usuario reportó la falla al probar Vera y
tomó ese día las decisiones D1 a D7 en dos formularios. Las demás son técnicas. Las cifras del negocio de la revisión quedan en Jira y en
`evidencias/`, que no se publica: aquí solo van proporciones de filas y la estructura de los datos.

## 1. El error

Con preguntas como «ventas por sucursal en los septiembre de los últimos 3 años» o «en qué mes se vendió más arroz de 500 g, sumados»,
Vera responde con un solo periodo y afirma que no hay datos de años anteriores, aunque la bodega tiene ventas desde 2022. Al revisarlo
apareció además que los montos de la bodega no son comparables entre años: unas ventas incluyen el IVA y otras no.

Uso esperado después del arreglo: consultas compuestas (por año, mes, sucursal, categoría o producto, con filtros) que Vera presenta
ordenadas y con una conclusión, con márgenes correctos en todas las pantallas.

## 2. Hallazgos

| # | Hallazgo | Consecuencia |
| --- | --- | --- |
| H1 | `historial_ventas` (`nlp_agent/herramientas/catalogo.py`) acepta un solo `periodo` por consulta. El modelo pidió septiembre de 2026 agrupado por año y recibió una fila | «El mismo mes en varios años» no se puede pedir. Hace falta una consulta que repita el periodo en varios años (D3) |
| H2 | Con `agrupacion=mes` y sin `periodo` ni `dias`, la herramienta pide los últimos 30 días, o sea un mes. La serie completa solo existe por trimestre o por año | «En qué mes se vendió más» ve un solo mes |
| H3 | La herramienta filtra por un producto o por una categoría. «Todos los arroces de 500 g sumados» terminó en una consulta por producto, cada una de un mes | Hace falta un grupo de productos por búsqueda (D3) |
| H4 | La respuesta al modelo trae el periodo consultado, pero no desde cuándo hay datos. Con una sola fila, el modelo concluye que «no hay información histórica» | La herramienta dice desde cuándo hay datos, y el verificador rechaza esa afirmación cuando es falsa |
| H5 | Las filas de la tabla y de la gráfica son las últimas 10 (`MAX_FILAS`), y las conclusiones (el mejor mes, quién gana) las saca el modelo de esas filas | Las conclusiones las calcula el código sobre todas las filas (D3) |
| H6 | El bucle reconoce una llamada escrita como texto solo si llega entre las etiquetas de apertura y de cierre (`LLAMADA_EN_TEXTO` en `nlp_agent/agente/bucle.py`). En la conversación del usuario el modelo omitió la de apertura, y el JSON de la llamada llegó al usuario como respuesta; el verificador no lo frenó porque no trae cifras | El reconocimiento acepta la llamada sin la etiqueta de apertura, y una respuesta que es una llamada nunca se muestra |
| H7 | La etiqueta de la tabla muestra el valor interno de la agrupación («Historial de ventas · anio») y no dice el periodo | Las etiquetas dicen «por año» y el periodo |
| H8 | La búsqueda de productos busca la palabra más larga tal como se escribió. «arrox» no encuentra nada | Búsqueda tolerante a errores de escritura (D5) |
| H9 | El catálogo del agente tiene 14 herramientas, el tope de la decisión 47 | El análisis amplía `historial_ventas` en lugar de sumar una herramienta (D3) |
| H10 | El reporte del punto de venta trae, por fila, la venta, el costo, el IVA y la utilidad. En las filas con IVA, la utilidad es venta − costo − IVA en los archivos de ene-abr 2022 y de 2023 a 2025 (del 99,9 % al 100 % de las filas con IVA de cada año), y venta − costo en los de may-oct 2022 y de 2026 (el 100 %). Cada archivo es de un solo tipo | La venta del reporte incluye el IVA en unos archivos y no en otros. La regla de la utilidad dice cuál, sin suponer nada (D1) |
| H11 | La bodega calcula margen = venta − costo (`api/reportes/router.py`, `api/consulta/router.py`). En los archivos con IVA, ese margen incluye el IVA cobrado. Medido como utilidad sobre la venta sin IVA, el margen real es estable todos los años | Los márgenes de las pantallas, de los reportes y de Vera salen inflados en los años con IVA, y las ventas no se comparan con la misma base entre años |
| H12 | `database/init.sql` documenta (INV-60) que `valor_total` incluye el IVA. Eso vale para los archivos con IVA, no para los de may-oct 2022 ni los de 2026 | El comentario y `docs/INV-60-notas-migracion-dw.md` se actualizan con la regla nueva |
| H13 | Del orden de 500 líneas de venta de 2022-2026 (la mayoría de 2026) traen un costo de más de 3 veces el precio, con la utilidad y la rentabilidad del reporte coherentes con ese costo. Vienen así del punto de venta: los mismos productos tienen meses con costos normales | Restan margen a meses y sucursales enteros. Se imputan y se marcan (D2) |
| H14 | `precio_base` y `costo_base` de `dw.dim_producto` salen de la última venta de cada producto (`etl_real/construir_dim_producto.py`). Hoy mezclan bases con y sin IVA, y unos productos toman un costo de H13: el catálogo queda con productos de margen negativo | El catálogo toma la última venta con costo válido, sin IVA (D1, D2). El inventario valorizado, que usa `precio_base`, cambia de base |
| H15 | El pronóstico solo usa unidades (`ml_service/prediccion/servicio.py`) | El arreglo no toca el modelo. La serie diaria de unidades debe quedar idéntica |
| H16 | Los hechos del conjunto de 61 preguntas (v1) son los de la bodega al 31-dic-2025, con la base de montos de entonces. Staging opera al 30-sep-2026 | La regresión del agente necesita decidir contra qué bodega y con qué hechos se mide (sección 7) |

## 3. Decisiones

| # | Decisión | Origen |
| --- | --- | --- |
| D1 | Toda la bodega guarda la venta sin IVA, como el reporte actual del punto de venta. El ETL decide por archivo, con la regla de la utilidad (H10): si las filas con IVA del archivo cumplen utilidad = venta − costo − IVA, la venta guardada es venta − IVA; si cumplen utilidad = venta − costo, se guarda tal cual. Un archivo con filas de los dos tipos detiene el ETL. Se recarga la bodega en local y en staging | Usuario, 26-nov |
| D2 | Una línea con costo de más de 3 veces su precio se imputa: su costo pasa a ser su venta por la razón costo/venta mediana del mismo producto en sus líneas válidas (si no tiene, la de su categoría). La línea queda marcada (`costo_imputado`) y la lista va al negocio, fuera del repositorio, para corregirla en el punto de venta. El costo base del catálogo sale de la última venta con costo válido | Usuario, 26-nov |
| D3 | `historial_ventas` pasa a ser la herramienta de análisis, sin sumar herramientas: medidas (unidades, venta, margen y porcentaje de margen), una o dos dimensiones (año, trimestre, mes, sucursal, categoría o producto), filtros (un periodo, el mismo periodo en varios años, una sucursal, una categoría o un grupo de productos por búsqueda), orden, límite y comparación con el año anterior. Un endpoint nuevo del Core API agrupa con dimensiones y medidas fijas y con los permisos por rol; el modelo no escribe SQL (decisión 30). El código calcula las conclusiones | Usuario, 26-nov |
| D4 | La respuesta de análisis va con la conclusión primero (de una a tres frases), después la tabla y la gráfica ordenadas y al final la fecha de los datos | Usuario, 26-nov |
| D5 | La búsqueda de productos tolera errores de escritura: solo cuando la búsqueda normal no encuentra nada, corrige las palabras que no existen en el catálogo, y Vera dice qué buscó | Usuario, 26-nov |
| D6 | Todo va en INV-82, en el Sprint 8: primero los datos y su recarga, después el Core API y Vera, con su evaluación | Usuario, 26-nov |
| D7 | Se mantiene el tope de 14 herramientas (decisión 47) | Usuario, 26-nov |
| T1 | La marca de costo imputado es una columna nueva, `dw.fact_ventas.costo_imputado` (booleana, falso por defecto), que `database/init.sql` agrega con `ADD COLUMN IF NOT EXISTS`. La migración de cada despliegue la crea antes de la recarga | Técnica (D2) |
| T2 | El IVA no se guarda aparte: con la venta sin IVA, margen = venta − costo vuelve a ser el margen real, y las consultas del Core API no cambian | Técnica (D1) |
| T3 | El endpoint de análisis es `GET /api/reportes/ventas/analisis`, con la caché de lecturas (INV-41, D5) como los demás reportes | Técnica (D3) |
| T4 | La tolerancia a errores de escritura vive en el Core API, como un parámetro opcional `tolerante` de `/api/consulta/productos`, para que la web no cambie de comportamiento. El vocabulario son las palabras de los nombres del catálogo, en memoria y con la versión de los datos de la caché de lecturas | Técnica (D5) |
| T5 | Los nombres internos de los parámetros se conservan (`historial_ventas`, `agrupacion`, `dias`, `periodo`, `producto`, `sucursal`, `categoria`), para que los conjuntos de evaluación anteriores sigan valiendo | Técnica (D3, H16) |

## 4. Diseño

### 4.1 ETL: venta sin IVA (`etl_real/construir_fact_ventas.py`)

- Primera pasada por `ventas_tidy.csv`: por cada `archivo_origen`, cuenta sus filas con IVA (valor_iva > 0) que cumplen cada regla, con
  una tolerancia de 1 peso. El archivo es «con IVA» o «sin IVA» si al menos el 99 % de sus filas con IVA cumple una regla. Si no, el ETL
  se detiene y nombra el archivo.
- Segunda pasada: en los archivos con IVA, `valor_total = |valor_venta| − |valor_iva|`; en los demás, como hasta hoy. `valor_unitario`
  se recalcula sobre el valor nuevo. Las devoluciones siguen la misma regla de su archivo.
- `construir_dim_producto.py` aplica la misma regla a `precio_base` y a `iva_pct`, que pasa a ser el IVA sobre la venta sin IVA.
- El resumen del ETL imprime cuántos archivos y filas hay de cada tipo, sin montos.

### 4.2 ETL: costos imputados (D2)

- Una línea es imputable si su venta es mayor que 0 y su costo es mayor que 3 veces su venta. Las líneas con venta 0 (obsequios) no se
  imputan.
- La razón de referencia es la mediana de costo/venta de las líneas válidas del mismo producto, con la venta ya sin IVA. Sin líneas
  válidas, la de su categoría; sin categoría, la de toda la bodega.
- `costo_total = valor_total × razón` y `costo_unitario` se recalcula. La línea queda con `costo_imputado = true`.
- `dim_producto.costo_base` sale de la última venta con costo no imputado.
- La lista para el negocio (código, nombre, sucursal, fecha, cantidad, venta, costo del reporte) va a
  `data/processed_real/<salida>/costos_imputados.csv`, que git ignora.

### 4.3 Recarga (D1, D6)

1. Se juntan `data/raw_real/ventas_tidy.csv` (2022-2025) y `~/ventas2/salida_2026/ventas_tidy_2026.csv` (2026), que tienen el mismo
   encabezado, en un `ventas_tidy` de la operación, fuera de git.
2. ETL con `INVENTARIO_FECHA=2026-09-30`, la foto de esa fecha y `ETL_SALIDA_DIR=data/processed_real/operacion_2026-09-30`, como en
   INV-63 (sección 7 de `docs/INV-63-holdout-2026.md`).
3. Comprobaciones antes de cargar:
   - las unidades por día y producto quedan idénticas a las de la bodega actual (H15);
   - el margen por mes queda sin saltos entre archivos con IVA y sin IVA.
4. `cargar_postgres.py` en local, con respaldo previo. Reinicio del Core API, del servicio de predicción y del agente.
5. Staging: `scripts/bd/volcar.sh`, `scripts/bd/subir_volcado.py` y, en la máquina, `scripts/bd/restaurar_staging.sh --recargar`
   (decisión 38), después del despliegue que trae la columna nueva (T1). El usuario corre el paso de la máquina.
   - `restaurar.sh` se niega si la bodega tiene filas, y recrear la base borraría los usuarios del staging. Por decisión del usuario del
     26-nov, la recarga los conserva: `scripts/bd/recargar.sh` respalda dw y app en la máquina, y en una sola transacción vacía los dos
     esquemas, carga el volcado y repone los mismos usuarios.
   - Antes de confirmar, comprueba que cada usuario siga en la misma sucursal. Si algo falla, la base queda como estaba.
   - `scripts/bd/probar.sh` (job «Base de datos» del CI) y `k8s/probar_k3d.sh` prueban la negativa, la falla a mitad, la recarga y la
     vuelta con el respaldo.

### 4.4 Core API: análisis de ventas (T3)

`GET /api/reportes/ventas/analisis`:

| Parámetro | Qué es |
| --- | --- |
| `dimensiones` | Una o dos, de `anio`, `trimestre`, `mes` (AAAA-MM), `sucursal`, `categoria` y `producto` |
| `fecha_inicio`, `fecha_fin` | El rango; por defecto, toda la historia |
| `meses` | Meses del año (1 a 12), para «el mismo mes en varios años» |
| `anios` | Años, para limitar el rango a años concretos |
| `sucursal_id` | Una sucursal, con la regla de permisos de siempre (decisión 13) |
| `categoria` | Una categoría |
| `productos` | Códigos de producto, hasta 50, para sumar un grupo |
| `orden`, `limite` | Por `valor`, `cantidad`, `margen`, `margen_pct` o el orden natural de las dimensiones; hasta 200 filas |

- Responde las filas con sus dimensiones, unidades, venta, costo, margen y porcentaje de margen. También trae los totales, cuántas filas
  hubo antes del límite, `datos_desde` y `datos_hasta`, y si las unidades mezclan kilos y unidades.
- Las dimensiones y las medidas son una lista fija en el código. Los valores van como parámetros, y la sucursal pasa por
  `filtro_sucursal`.
- Un administrador de sucursal ve solo su sucursal, también con la dimensión `sucursal`.

### 4.5 Core API: búsqueda tolerante (T4)

- `GET /api/consulta/productos?busqueda=…&tolerante=true`: si la búsqueda no encuentra nada, cada palabra que no está en el vocabulario
  se cambia por la más parecida, si el parecido es de al menos 0,8 (`difflib`). Luego se busca otra vez.
- La respuesta trae `busqueda_corregida` cuando corrigió algo. Sin `tolerante`, nada cambia.

### 4.6 Agente: la herramienta de análisis (D3, D4, T5)

Parámetros nuevos de `historial_ventas`, además de los de hoy:

| Parámetro | Qué es |
| --- | --- |
| `por` | Una o dos dimensiones; `agrupacion` sigue valiendo y equivale a `por=[agrupacion]` |
| `anios` | De 2 a 5: el `periodo` (o el año en curso) repetido en los últimos N años |
| `grupo` | Con `producto`: suma todos los productos que coinciden con la búsqueda, en lugar de pedir cuál |
| `orden`, `limite` | Como en el Core API |
| `comparar` | Agrega a cada fila la variación frente al mismo periodo del año anterior |

- **Al modelo le llegan las filas ordenadas y unas `conclusiones` armadas por el código:**
  - el total;
  - la fila con más y con menos venta, unidades y margen, con su participación;
  - la variación del primer al último año, y año contra año si `por` incluye el año;
  - con dos dimensiones, el máximo de cada valor de la segunda;
  - desde cuándo hay datos y, con un grupo, cuántos productos entraron y cuáles son los primeros.
- **Tabla y gráfica:**
  - las filas se ordenan según el pedido;
  - año × sucursal va en barras agrupadas (una serie por sucursal), una serie mensual en líneas, y una sola dimensión que no es tiempo en
    barras horizontales ordenadas;
  - la gráfica lleva todas las filas, no solo las 10 de la tabla.
- **Etiquetas:** «Ventas por año», «Ventas por sucursal y año · septiembre de 2024 a 2026», con el periodo en palabras.
- **El prompt** pide empezar por la conclusión con las cifras de `conclusiones`, de una a tres frases, y no repetir la tabla.

### 4.7 Agente: bucle y verificador

- `llamadas_en_texto` acepta una o varias llamadas con o sin la etiqueta de apertura, y el JSON solo, si todo el texto es eso.
- Si en la última ronda (sin herramientas) el modelo vuelve a escribir una llamada, no se muestra: va la respuesta de respaldo con lo
  consultado.
- Regla nueva del verificador: si la respuesta dice que no hay datos de años o meses anteriores, o que solo hay datos de un periodo, y la
  herramienta informó datos desde antes, se pide la corrección con la fecha desde la que hay datos.

### 4.8 Agente: búsqueda tolerante (D5)

`Contexto.buscar_productos` pasa `tolerante=true` al Core API. Si llega `busqueda_corregida`, la herramienta lo dice al modelo («se buscó
«arroz»»), y la respuesta lo menciona.

## 5. Criterios de aceptación

| # | Criterio | Cómo se comprueba |
| --- | --- | --- |
| 1 (M) | Toda la bodega guarda la venta sin IVA, y el margen mensual de 2022 a 2026 queda sin saltos por el formato del reporte | Pruebas del ETL con los dos tipos de archivo y el de filas mezcladas. En la recarga, el margen por mes y las unidades idénticas |
| 2 (M) | Los costos de más de 3 veces el precio quedan imputados y marcados, y el catálogo no tiene márgenes negativos por ellos. La lista para el negocio queda fuera del repositorio | Pruebas del ETL. En la bodega, ninguna línea con costo de más de 3 veces su venta sin la marca |
| 3 (M) | La bodega queda recargada en local y en staging, validada por su huella | `validar.sh` en staging y la huella del volcado |
| 4 (M) | Vera responde las consultas compuestas de un conjunto de preguntas congelado antes de medir, con la conclusión primero y las cifras 100 % respaldadas | Conjunto `inv82` en staging (sección 7) |
| 5 (M) | Una llamada escrita como texto nunca llega al usuario, y la afirmación de que no hay datos de años anteriores, cuando sí los hay, se corrige antes de mostrar | Pruebas del bucle y del verificador |
| 6 (M) | Se cumple la regla de adopción del agente (decisión 51) | Sección 7 |
| 7 (S) | Una búsqueda con un error de escritura de una letra encuentra el producto, y Vera dice qué buscó | Pruebas del Core API y una pregunta del conjunto `inv82` |

## 6. Casos de prueba automáticos

| Caso | Dónde |
| --- | --- |
| Archivo con IVA: la venta guardada es venta − IVA y el margen es la utilidad del reporte | `etl_real/tests/` |
| Archivo sin IVA: la venta queda igual | Igual |
| Archivo con filas de los dos tipos: el ETL se detiene y nombra el archivo | Igual |
| Línea con costo de más de 3 veces su venta: costo imputado con la mediana del producto, de su categoría o de la bodega, y la marca | Igual |
| Línea con venta 0: no se imputa | Igual |
| Catálogo: el precio base sale sin IVA y el costo base de la última venta válida | Igual |
| Análisis: cada dimensión y cada par, el mismo mes en varios años, un grupo de productos, el orden y el límite | `api/tests/` |
| Análisis: un administrador de sucursal no ve otra sucursal, tampoco con la dimensión `sucursal`; una dimensión o un orden fuera de la lista dan 422 | Igual |
| Búsqueda tolerante: corrige una letra, no toca palabras que existen y sin `tolerante` no corrige | Igual |
| Herramienta: conclusiones (máximos, mínimos, participación, variación), orden, gráfica según las dimensiones, grupo de productos y etiquetas | `nlp_agent/tests/` |
| Bucle: una llamada sin etiqueta de apertura se ejecuta; en la última ronda no se muestra | Igual |
| Verificador: «no hay datos de años anteriores» con datos desde antes pide corrección; con datos solo del periodo, no | Igual |

## 7. Evaluación del agente

- **Conjunto `inv82`**, congelado y versionado antes de medir, con su huella. Tiene unas 15 preguntas, entre ellas:
  - el mismo mes en varios años por sucursal;
  - el mejor y el peor mes de un producto y de un grupo;
  - un grupo de productos sumado;
  - la comparación con el año anterior;
  - el ranking de sucursales o categorías de un periodo;
  - un error de escritura;
  - un administrador de sucursal que pide otra sucursal;
  - un control que la herramienta no debe responder.
- Los hechos de `inv82` salen de la bodega recargada al 30-sep-2026 y quedan fuera del repositorio, como los del v1. Se corre contra
  staging con Qwen3-32B en Bedrock, 3 corridas por pregunta.
- **Regresión (decisión 51):** el conjunto v1 califica contra la bodega al 31-dic-2025, con la base de montos de entonces (H16). Antes de
  medir se decide, con un formulario, contra qué bodega corre y cómo se rehacen los hechos de montos que cambian con D1. Las
  equivalencias que hagan falta por los parámetros nuevos se declaran por escrito antes de medir.

## 8. Ruta de implementación

1. **Datos:** ETL (D1, D2), la columna nueva (T1) y sus pruebas. Recarga local y comprobaciones. Pull Request a `develop`; al
   desplegarse, el volcado y la recarga de staging.
2. **Core API:** el análisis (T3) y la búsqueda tolerante (T4), con sus pruebas y el OpenAPI. Pull Request.
3. **Agente:** la herramienta de análisis, el bucle, el verificador, el prompt y las etiquetas, con sus pruebas, y el conjunto `inv82`
   congelado. Pull Request.
4. **Evaluación en staging** y documentación: guía de uso, glosario (margen sin IVA), notas de INV-60 y decisiones en Confluence. Pull
   Request.

## 9. Riesgos

- **Las cifras de ventas de 2022-2025 bajan** al quitarles el IVA. Lo que se haya mostrado o documentado con la base anterior (guías,
  presentaciones) ya no coincide; las guías se anotan.
- **El costo imputado es una estimación.** Mientras el negocio no corrija esos costos en el punto de venta, el margen de esas líneas es el
  típico del producto, no el real. La marca permite contarlas y excluirlas si hiciera falta.
- **Tiempo:** el arreglo toca cuatro piezas y la bodega antes del 4-dic, en paralelo con producción (INV-69). Los datos van primero porque
  afectan a todas las pantallas; si el agente no pasa su evaluación a tiempo, la versión de producción sale con los datos arreglados y el
  agente anterior.
- **Recarga de staging:** el volcado necesita la columna nueva en el destino (T1), así que va después del despliegue del primer Pull
  Request.
