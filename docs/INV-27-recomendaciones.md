# INV-27 · Vista de recomendaciones

La página **Recomendaciones** (`/recomendaciones`) muestra las compras a
proveedor de INV-21 y los traslados entre ubicaciones de INV-22, que el Core API
entrega con filtros (INV-23). Tiene el calendario de pedidos, el resumen, los
bloques de cubrir con traslado y de alertas, y la exportación a CSV. La ven los
tres roles: el gerente y el `admin_bodega` eligen la ubicación, también la Bodega
Central; el `admin_sucursal` ve solo la suya.

La especificación, con las correcciones C1–C15 y las decisiones V1–V14, está en
[`INV-26-27-requerimientos.md`](INV-26-27-requerimientos.md) (Fase C). Este
documento dice cómo quedó implementada, qué se ajustó al implementarla y cómo se
verificó. La base que reutiliza es la del fix de INV-26
([`INV-26-fix.md`](INV-26-fix.md)) y la de Predicciones
([`INV-26-predicciones.md`](INV-26-predicciones.md)).

## Qué se entregó

| Pieza | Archivo | Qué hace |
| --- | --- | --- |
| Página | `frontend/src/pages/Recomendaciones.jsx` | Pestañas, filtros, contexto, calendario, resumen, tablas paginadas, avisos, estados y exportación |
| Ruta | `frontend/src/rutas.js` | `/recomendaciones` para los tres roles, con la página `lazy` |
| CSV (V12) | `frontend/src/utils/csv.js` | `aCSV(columnas, filas)` y `descargarCSV(nombre, texto)`: UTF-8 con BOM, `;`, coma decimal, sin separador de miles, fechas ISO y campos escapados |
| Etiquetas (V7) | `frontend/src/utils/etiquetas.js` | `GRUPOS_PEDIDO`, `TIPOS_DESTINO`, `MOTIVOS_COMPRA`, `TIPOS_ALERTA_RECOMENDACION` y `ACCIONES_ALERTA`, incluida la acción `ninguna`. Las urgencias (`URGENCIAS_RECOMENDACION`) y `etiquetaDe` llegaron con INV-26 |
| Tiempo de espera (C15) | `frontend/src/api/client.js` | Las consultas de ML esperan 130 s también cuando llegan desde `useConsulta` |

No cambia el Core API ni `ml_service`.

## Cómo funciona la vista

**Consultas.** Solo se consulta la pestaña abierta: la primera consulta calcula
las recomendaciones de toda la red y tarda entre 20 y 40 s; las siguientes salen
de la caché del Core API en menos de un segundo. Las compras se piden con
`incluirDetalle: false` (737 KB en vez de 1,19 MB) y las transferencias sin el
balance. Cambiar un filtro cancela la consulta en curso (`useConsulta`). La
espera la muestra `Cargando`, que a los 5 s avisa: "La primera consulta calcula
las recomendaciones de toda la red: tarda cerca de 30 s.".

**Filtros.**
- **Sucursal.** El selector muestra "Bodega Central", pero la llamada lleva el nombre canónico, `BODEGA_CENTRAL` (V2). Al `admin_sucursal` no se le muestra el selector ni se le manda la sucursal: la API le aplica la suya (`filtros_aplicados.sucursal_por_rol`).
- **Categoría:** la lista de `getCategorias`, en orden alfabético.
- **Urgencia:** Urgente, Alta y Normal; en Transferencias, también Vigilancia (C14).
- **Búsqueda local:** por nombre o código, sin distinguir mayúsculas ni tildes. Filtra todas las listas de la pestaña.

**Lo que se ve.**
- **Contexto:** la ubicación (o "Toda la red"), la fecha de la foto, cuándo se calculó y las versiones de las políticas. Compras muestra INV-21 e INV-22; transferencias, la de INV-22.
- **Calendario de pedidos,** en Compras: para cada grupo, el pedido, la llegada a la Bodega y a la sucursal, el pedido siguiente y hasta cuándo cubre, más el plazo del proveedor.
- **Resumen:** unidades y kilos siempre por separado, con `fmtCantidadConUnidad`. En Compras, con una sucursal física, una quinta tarjeta: la necesidad vía la Bodega.
- **Compras a proveedor:** las columnas de la Fase C, sin proveedor.
  - La columna "Llega" muestra la llegada a la sucursal y, en las líneas de la Bodega, debajo, la llegada a la Bodega (V13).
  - Con una sucursal física se agrega "Necesidad de la sucursal".
  - Si hay líneas de la Bodega, el aviso: "La urgencia y los días se calculan desde {sucursal}; la cantidad es la de toda la compra a la Bodega.".
- **Traslados:** origen y destino (la Bodega con su marca), cantidad, urgencia, días hasta agotarse, llegada con los días hábiles y "Llega tarde".
- **Debajo:**
  - "Cubrir con traslado desde la Bodega", solo en Compras.
  - "Alertas de inventario", en las dos pestañas. Las dos inconsistencias, `posible_inconsistencia_inventario` de compras y `stock_negativo` de traslados, llevan el mismo rótulo, "Inconsistencia de inventario".
  - En Transferencias, una nota cuenta los pares sin pronóstico (acción "ninguna"), que solo llegan con el balance.
- **Paginación** en el cliente: 50 filas en las tablas principales, como Alertas, y 10 en los bloques de debajo. El orden es el de la API (por urgencia).
- **Exportación:** un botón por pestaña sobre todas las filas que pasan los filtros y la búsqueda.
  - Columnas: las de la tabla, con la unidad en su propia columna, más la foto de inventario y la fecha del cálculo.
  - Nombre del archivo: `recomendaciones-{compras|transferencias}[-{sucursal}]-{fecha}.csv`.

**Errores.** Los resuelve `EstadoConsulta`, siempre con "Reintentar":
- 409, 403 y 422 muestran el `detail` de la API.
- 503, 504, el timeout y la falta de conexión muestran su texto fijo.

## Ajustes frente a los requerimientos

| # | Tema | Qué se hizo y por qué |
| --- | --- | --- |
| 1 | Vigilancia (C14) | Compras rechaza `urgencia=vigilancia` con un 422. El filtro la ofrece solo en Transferencias, y al pasar a Compras vuelve a "Todas las urgencias" |
| 2 | Tiempo de espera (C15) | `conTimeoutML` hacía `{ timeoutMs: 130 s, ...op }`, y el `timeoutMs: undefined` que pasa `useConsulta` lo anulaba. Afectaba también a Predicciones. Ahora es `op.timeoutMs ?? 130 s`, con una prueba que falla sin el arreglo |
| 3 | Una pestaña a la vez | Solo se consulta la pestaña abierta, para no lanzar juntas dos cargas en frío de 20 a 40 s |
| 4 | Bloques de debajo | 10 filas por página: con 50, la página pasaba de 9.000 px |
| 5 | Búsqueda | Busca también por código (como V11 en Predicciones) y filtra todas las listas de la pestaña |
| 6 | Vista desde la sucursal | Se decide con la ubicación que aplicó la API (`filtros_aplicados.sucursal`) y su tipo, así que vale también para el `admin_sucursal` |

## Datos reales

Foto al 2025-12-31. Son los valores del bloque I de la guía de pantallas.

| Vista | Compras | Transferencias |
| --- | --- | --- |
| Toda la red | 1.340 líneas (449 a sucursales, 891 a la Bodega); 41.952 unidades y 3.169,0 kg; 277 cubiertos por la Bodega; 220 alertas | 119 traslados; 4.623 unidades; déficit neto 14.150 unidades y 1.904,7 kg; 220 alertas y 2.762 pares sin pronóstico |
| PRINCIPAL | 814 líneas (164 y 650); 30.375 unidades y 1.072,0 kg; 172 cubiertos; 95 alertas; necesidad vía la Bodega 19.637 unidades | 89 traslados; 95 alertas; 980 pares sin pronóstico |
| Bodega Central | 891 líneas, todas a la Bodega; 27.098 unidades; 15 alertas | — |
| PRINCIPAL, Lácteos, urgente | 29 líneas (27 y 2); 470 unidades; 4 alertas; necesidad vía la Bodega 14 unidades | — |
| Urgencia en traslados | — | Urgente 42; vigilancia 0 (las alertas siguen en 220) |

## Pruebas

**Frontend (Vitest).** 204 pruebas en 23 archivos (24 nuevas):

| Archivo | Pruebas | Qué cubre |
| --- | --- | --- |
| `pages/Recomendaciones.test.jsx` | 18 | Compras de la red con contexto, calendario, resumen y columnas, sin proveedor. Bodega con `BODEGA_CENTRAL`. Sucursal, categoría y urgencia en la llamada. Aviso y necesidad desde una sucursal física, y sin aviso cuando no hay líneas de la Bodega. Cubrir con traslado y alertas con el mismo rótulo. Transferencias y vigilancia solo ahí. Búsqueda y paginación. Exportación con todas las filas filtradas, desde una sucursal y en las dos pestañas. Lista vacía. Valores sin etiqueta. Cancelación al cambiar un filtro. 409, 503 y 504 con "Reintentar". `admin_sucursal` y `admin_bodega` |
| `utils/csv.test.js` | 5 | Números con coma y sin miles, vacíos, sí/no, fechas ISO, escape de `;`, comillas y saltos de línea, BOM y CRLF, y la descarga |
| `api/client.test.js` | +1 | El tiempo de espera de ML con el `timeoutMs: undefined` de `useConsulta` |

`npm run test:cov` deja 98,28 % de líneas, 97,64 % de sentencias, 96,32 % de
ramas y 94,89 % de funciones sobre `coverage.include`, que ahora incluye
`Recomendaciones.jsx` (100 %). `npm run build` separa la página
(`Recomendaciones-*.js`, 18 kB) y `npm audit --omit=dev` no da hallazgos.

**Pantallas.** La corrida de la sección 15 de la guía
([`INV-26-pruebas-pantallas.md`](INV-26-pruebas-pantallas.md)) cubre el bloque I y
la regresión del menú y del pronóstico: 17 casos. Se ejecutó con Playwright sobre la
app y el Core API reales, con los tres roles. Antes se reinició el Core API para la
carga en frío, que tardó 20 s. Resultado: 17 de 17 OK, con 26 capturas y el CSV
descargado.

El CSV se revisó byte a byte: BOM, 30 líneas, `;`, coma decimal y sin separador de
miles. La auditoría de las capturas solo pidió un ajuste del script. Falta abrir el
CSV en Excel, que lo hace una persona (Definition of Done).

## Criterios de aceptación

| # | Criterio | Dónde se verifica |
| --- | --- | --- |
| 1 | Compras con sus columnas, sin proveedor, con cubrir con traslado y alertas | I-01, I-02; primera prueba de la página |
| 2 | Transferencias con origen, destino, cantidad, urgencia, llegada y llega tarde | I-07; prueba de transferencias |
| 3 | Filtros combinados con el nombre canónico (V2) | I-03 a I-05; pruebas de la Bodega y de los tres filtros |
| 4 | El aviso de la vista desde la sucursal | I-03, I-05, I-09; pruebas del aviso |
| 5 | Foto, cálculo, políticas y calendario | I-01, I-07 |
| 6 | Unidades y kilos por separado | Tarjetas de I-01, I-03, I-07; prueba del resumen |
| 7 | Carga en frío con aviso, cancelación al cambiar un filtro y errores con `MensajeError` | I-01 en frío; pruebas de cancelación y de 409, 503 y 504 |
| 8 | Exportación con los filtros, todas las filas y el formato de V12 | I-06; pruebas de exportación y de `csv.js`. Falta abrirlo en Excel |
| 9 | `admin_sucursal` ve solo lo suyo y no elige la Bodega | I-09; prueba de `admin_sucursal` |
| 10 | Rótulos desde `etiquetas.js` | La página no tiene rótulos fijos de urgencia, grupo, motivo, tipo o acción; prueba de valores sin etiqueta |
| 11 | En `RUTAS` para los tres roles, `lazy` | `rutas.test.jsx`, `App.test.jsx`, A-02, A-05, A-06; el build la separa |

## Limitaciones

- **Excel.** El CSV sigue la configuración de Colombia (V12). Un Excel con otra configuración puede abrirlo en una sola columna; se abre con "Datos → Desde texto/CSV".
- **Sin balance.** Los pares sin pronóstico solo se cuentan; el balance completo (6,4 MB) no se carga.
- **Sin paginación en la API.** Compras de toda la red trae 1.340 líneas (737 KB): la página las pagina y las busca en el cliente.
- **Primera consulta lenta.** Entre 20 y 40 s después de cada reinicio del Core API o de una foto nueva. En producción, Nginx espera 135 s (`frontend/nginx.conf`, después de INV-27): más que el cliente y que el Core API.
- **Foto única.** Las recomendaciones son a la foto del 2025-12-31; la página lo dice en el contexto.
