# INV-26 · Vista de predicciones

La página **Predicciones** (`/predicciones`) muestra la demanda prevista de un
producto en una sucursal física a 15 días hábiles, junto a sus 8 ventanas de
historia y su stock. La ven los tres roles: el gerente y el `admin_bodega`
eligen la sucursal, y el `admin_sucursal` queda fijo en la suya.

La especificación, con las correcciones C1–C13 y las decisiones V1–V14, está en
[`INV-26-27-requerimientos.md`](INV-26-27-requerimientos.md) (Fase B). Este
documento dice cómo quedó implementada, qué se ajustó al implementarla y cómo
se verificó. La base que reutiliza (cliente, `useConsulta`, estados, formato,
selector, rutas) es la del fix previo, en [`INV-26-fix.md`](INV-26-fix.md).

## Qué se entregó

| Pieza | Archivo | Qué hace |
| --- | --- | --- |
| Página | `frontend/src/pages/Predicciones.jsx` | Buscador, selector, tarjetas del pronóstico y del inventario, gráfica y estados |
| Ruta | `frontend/src/rutas.js` | `/predicciones` para los tres roles, con la página `lazy` |
| Riesgo según el pronóstico (V5) | `frontend/src/utils/riesgo.js` | `calcularRiesgo(stock, q50)` → `{ nivel, dias }` |
| Barras de la gráfica | `frontend/src/utils/graficas.js` | `barrasPronostico(ventanas, q50, horizonte)`: ventanas en orden y el pronóstico al final |
| Cantidad con su unidad (V8) | `frontend/src/utils/formato.js` | `fmtCantidadConUnidad`: "3.366 unidades", "1 unidad", "135,7 kg", con la regla de `texto_cantidad` del Core API. `fmtDecimal` acepta los decimales: el α sale "0,893" |
| Etiquetas (V7) | `frontend/src/utils/etiquetas.js` | `URGENCIAS_RECOMENDACION`, `RIESGOS_PRONOSTICO`, `RAMAS_MODELO` y `etiquetaDe(etiquetas, valor)`, que muestra legible un valor sin etiqueta. `etiquetaTipoAlerta` la usa |
| Selector (V10) | `frontend/src/components/SucursalSelector.jsx` | Prop `opcionVacia`, por defecto "Todas las sucursales". Predicciones pasa "Elegir sucursal" e `incluirBodega={false}` |
| Búsqueda por código (V11) | `api/consulta/router.py` | `GET /api/consulta/productos?busqueda=` busca también en `codigo_item` (sin distinguir mayúsculas). Mismos parámetros y misma respuesta |

Las etiquetas de INV-27 que todavía no usa ninguna pantalla (grupos, motivos,
tipos y acciones de las alertas de INV-21, 22 y 23) entran con INV-27.

## Cómo funciona la vista

**Selección.** El buscador espera 300 ms después de la última tecla y pide 20
productos a `getProductos`. Encuentra por nombre, familia o código, y cada
resultado muestra nombre, código y categoría. Si hay más de 20, lo dice al pie
("Se muestran 20 de 71 productos: escriba más para acotar."). Esc cierra la
lista. Al elegir un producto, el buscador se limpia y el producto queda bajo
él, con su código, su categoría, cómo se vende y la sucursal.

**Consultas.** Con el producto y la sucursal elegidos, se lanzan tres
`useConsulta` en paralelo, con `activo: false` mientras falte alguno:

| Consulta | Función | Para qué |
| --- | --- | --- |
| Pronóstico | `predecir({ idProducto, idSucursal })` | q50, límite de negocio y su α, rama, interpretación y fechas |
| Ventas | `getVentasProducto(id, { sucursalId, ventanas: 8 })` | Las 8 ventanas de 15 días hábiles |
| Inventario | `getInventarioDetalle(id, sucursalId)` | Stock, cobertura, semáforo y fecha de la foto |

Cada bloque muestra su carga y su error por separado, con `EstadoConsulta`:
un 404 del pronóstico no esconde el stock ni las ventanas. Cambiar el producto
o la sucursal cancela las consultas en curso.

**Dos lecturas del riesgo (V5).** Van en bloques rotulados aparte:

- **"Riesgo según el pronóstico"**, en el bloque del pronóstico: días hábiles hasta agotarse = stock / (q50 / 15), redondeados a un decimal, con los umbrales de INV-21 (urgente ≤ 5, alta ≤ 10). Con q50 = 0, "Sin demanda prevista"; con stock negativo, "Inconsistencia de inventario". No suma los traslados en camino.
- **"Cobertura del inventario"**, en el bloque del inventario: `dias_cobertura` del ETL con `textoCobertura` y el estado del semáforo con `ESTADOS_INVENTARIO`, como en Inventario.

El estado se lee siempre en texto ("Urgente", "✕ Crítico"); el color lo acompaña.

**Gráfica.**
- Barras azules sólidas: las 8 ventanas, rotuladas con la fecha en que terminan.
- Una barra clara de borde punteado: el pronóstico, rotulado "Pronóstico IA".
- Una línea naranja punteada: el cuantil de negocio.
- Una línea verde: el stock.
- Sin bandas ni sombreado (V4).
- Debajo, en texto, el valor de cada línea. En los perecederos (α < 0,5), la aclaración de que el cuantil queda bajo la mediana y no es una cota de reposición.

## Ajustes frente a los requerimientos

| # | Tema | Qué se hizo y por qué |
| --- | --- | --- |
| 1 | Unidad (C1) | Se toma del producto elegido (`unidad` de `getProductos`), que es la misma de `getVentasProducto` y está disponible antes de las tres consultas |
| 2 | Fecha de la foto (C2) | El último punto de `historial`, que viene en orden ascendente; hoy tiene uno solo |
| 3 | Días redondeados (V5) | Se comparan los días como se ven. HUEVOS en LA 21 da 525 / (1.567 / 15) = 5,03: sin redondear sería "5,0 días hábiles · Alta", una contradicción en pantalla. Ahora es "Urgente". INV-21 compara sin redondear, pero tampoco usa el mismo stock (suma los traslados en camino) |
| 4 | Sin pronóstico | Con un 404 o un error de `predict`, la gráfica no tiene barra de pronóstico ni la nombra en la leyenda, y el subtítulo no dice "y el pronóstico la sigue" (salió en la validación de pantallas, H-07) |
| 5 | Nota del cuantil bajo | Se muestra con α < 0,5, que es lo que la hace cierta, y no por el nombre de la rama |
| 6 | Leyenda | El texto va en gris: con el color claro de la barra del pronóstico no se leía |
| 7 | Riesgo sin stock | El riesgo necesita el stock del detalle de inventario, que llega unos 0,3 s después del pronóstico: mientras tanto la tarjeta dice "Esperando el stock de la foto…", y si el detalle falla (un producto sin inventario en la sucursal da 404), "Necesita el stock de la foto de inventario" |
| 8 | Pie de la búsqueda | Con más de 20 resultados, la lista muestra unos 8 y el pie "Se muestran 20 de 71 productos: escriba más para acotar." solo se veía al desplazarla. Ahora queda fijo al fondo (corrida de la sección 13, H-02) |
| 9 | Tooltip | El valor del pronóstico salía en el azul claro de su barra y casi no se leía: el texto de los tooltips va en gris oscuro, como la leyenda (corrida de la sección 13, H-03) |

## Datos reales

Foto y features al 2025-12-31. Son los valores del bloque H de la guía de pantallas.

| Caso | Producto y sucursal | Pronóstico | Riesgo según el pronóstico | Inventario |
| --- | --- | --- | --- | --- |
| Urgente | HUEVOS \*UND (P1632) en PRINCIPAL | 3.366 unidades; límite 4.609 (α = 0,893); demanda intermitente | 2,2 días hábiles, Urgente | 489 unidades; 2,9 d, ✕ Crítico |
| Las lecturas difieren | ARROZ ZULIA \*500 GR (P3937) en PRINCIPAL | 1.251 unidades; límite 1.660; demanda estable | 6,7 días hábiles, Alta | 556 unidades; 5,3 d, ⚠ Bajo |
| Perecedero | HUEVOS \*UND en GLORIETA | 3.871 unidades; límite 3.094 (α = 0,167), bajo la mediana | 1,3 días hábiles, Urgente | 341 unidades; 1,3 d, ✕ Crítico |
| Por kilo | PAPA PASTUSA \*KL (P1814) en PRINCIPAL | 135,7 kg; límite 199,7 kg | 8,5 días hábiles, Alta | 77,1 kg; 6,3 d, ⚠ Bajo |
| Días redondeados | HUEVOS \*UND en LA 21 | 1.567 unidades; límite 1.253 (α = 0,167) | 5,0 días hábiles, Urgente | 525 unidades; 6,6 d, ⚠ Bajo |
| Historia insuficiente | FRIJOL CARGAMANTO (02458) en PRINCIPAL | 404 con su `detail`; las 8 ventanas en 0 | — | 38 unidades; Sin ventas, ✓ OK |

Con la Bodega, `predict` responde 422, y con una sucursal ajena, 403. La
página no los provoca: el selector no ofrece la Bodega y el `admin_sucursal`
no elige.

## Pruebas

**Frontend (Vitest).** 180 pruebas en 21 archivos (25 nuevas):

| Archivo | Pruebas | Qué cubre |
| --- | --- | --- |
| `pages/Predicciones.test.jsx` | 14 | Selector sin "Todas las sucursales" ni la Bodega, búsqueda con espera y por código, sin resultados y con más de 20, Esc, HUEVOS, ARROZ, GLORIETA, PAPA, el 404 del pronóstico, q50 = 0 y stock negativo, sin inventario en la sucursal (404 del detalle), el stock que todavía no llega, 503 con "Reintentar", `admin_sucursal`, cambio de producto con la consulta anterior cancelada |
| `utils/riesgo.test.js` | 6 | Los pares reales, los umbrales, el redondeo, sin demanda y stock negativo |
| `utils/graficas.test.js` | +2 | Orden, rótulos y pronóstico al final; sin pronóstico |
| `utils/formato.test.js` | +2 | `fmtCantidadConUnidad`, `fmtDecimal` con 3 decimales y `etiquetaDe` |
| `components/SucursalSelector.test.jsx` | +1 | `opcionVacia` |

`npm run test:cov` deja 97,83 % de líneas, 97,14 % de sentencias, 95,56 % de
ramas y 93,12 % de funciones sobre `coverage.include`, que ahora incluye
`Predicciones.jsx` (94,82 % de líneas; lo que falta son las funciones de
formato que recharts llama al dibujar, que en jsdom no dibuja). `npm run build` y `npm audit --omit=dev`,
sin observaciones.

**Core API.**
- 210 pruebas: 154 unitarias y 56 de integración, 3 nuevas: `test_busqueda_por_codigo` con `P1632` y `p1632`, y `test_busqueda_por_nombre_y_familia_sin_cambios`.
- `consulta/router.py` queda al 100 % de cobertura.
- `test_consulta.sh` da 38 de 38, con la búsqueda por código (Test 5b).
- `ruff` no da observaciones.

**Pantallas.** El bloque H de [`INV-26-pruebas-pantallas.md`](INV-26-pruebas-pantallas.md),
con 9 casos, se recorrió con Playwright (Chromium) sobre la app y el Core API
reales con los tres roles: 9 de 9 OK. La gráfica se comprobó por su geometría:
la línea del cuantil a la altura de la ventana más alta en HUEVOS, bajo el tope
del pronóstico en el perecedero, ventanas en 0 y ninguna banda. También se
comprobaron los tooltips. A 390 px de ancho la página no desborda.

La corrida de la sección 13 de la guía, con 23 casos, se ejecutó con Playwright y 39 capturas: 23 de 23 OK.
Repite el bloque H y la regresión de lo que tocó INV-26 en otras pantallas: menú, selector, nombres de alertas,
decimales de la cobertura y la tendencia de Reportes. La auditoría de las capturas encontró los ajustes 8 y 9,
que se corrigieron antes de repetir la corrida completa.

## Criterios de aceptación

| # | Criterio | Dónde se verifica |
| --- | --- | --- |
| 1 | Predicción, 8 ventanas, stock e interpretación en una pantalla | H-03; prueba de HUEVOS |
| 2 | Sin sombreado ni intervalo; el límite como referencia con su α | H-03 y H-05 (geometría); `barrasPronostico` |
| 3 | Sin selector de horizonte; "15 días hábiles" | H-01; primera prueba de la página |
| 4 | Cobertura y riesgo por separado, con su unidad, incluidos q50 = 0 y stock negativo | H-04; `riesgo.test.js`; prueba de q50 = 0 y stock negativo |
| 5 | Cantidades con la unidad del producto | H-06; prueba de PAPA |
| 6 | Sin la Bodega ni "Todas las sucursales"; `admin_sucursal` sin selector | H-01, H-08 y H-09; pruebas del selector y de `admin_sucursal` |
| 7 | Fecha de la foto y de las features | H-03; prueba de HUEVOS |
| 8 | El riesgo en texto, no solo en color | Insignias "Urgente", "Alta", "✕ Crítico" (H-03, H-04) |
| 9 | Búsqueda por nombre y por código | H-02; prueba de búsqueda; `test_busqueda_por_codigo` |
| 10 | En `RUTAS` para los tres roles, `lazy` | `rutas.test.jsx`, `App.test.jsx`; el build la separa (`Predicciones-*.js`, 11 kB) |
| 11 | Solo funciones de `client.js` y la base del fix | La página importa `predecir`, `getProductos`, `getVentasProducto` y `getInventarioDetalle`; formatos y rótulos salen de `formato.js` y `etiquetas.js` |

## Limitaciones

- **Foto única.** El stock y el pronóstico son al 2025-12-31; la página muestra las dos fechas.
- **Casi todo es intermitente.** El 98,6 % de los pares lo es: muchas ventanas valen 0 o casi 0. Es lo esperado.
- **El riesgo de la vista no es el de INV-21.** No suma los traslados en camino, y redondea los días antes de comparar. INV-27 muestra la urgencia de INV-21 tal como llega.
- **Primera consulta de `ml_service` en frío.** `Cargando` avisa a los 5 s ("Calculando el pronóstico…"); el cliente espera hasta 130 s.
