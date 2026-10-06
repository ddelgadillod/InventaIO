# INV-26 · INV-27 · Requerimientos de las vistas de predicciones y recomendaciones

Versión del 2026-10-06, revisada el mismo día contra el código de `develop`
(merge `7e47770`), el Core API y la bodega real (foto al 2025-12-31) y Jira.
Reemplaza el borrador del 4 de octubre. La revisión corrigió nombres de campos,
cifras y ejemplos, y agregó las decisiones V10 a V14 (ver "Revisión contra el
código y los datos").

## Resumen

El fix previo dejó la base lista: las dos vistas **solo agregan su página, su
entrada en `RUTAS`, sus etiquetas, sus pruebas y su documentación** (G8 del
fix). Ya no incluyen funciones de API, rutas, manejo de errores, estados de
carga, formato ni utilidades de prueba: eso existe, está probado y se reutiliza.
Las únicas piezas de base que cambian son dos ajustes pequeños que salieron de
la revisión: una prop del selector de sucursal (V10) y la búsqueda de productos
por código en el Core API (V11).

- **INV-26 (Fase B):** página `Predicciones`.
- **INV-27 (Fase C):** página `Recomendaciones`.

| Campo | INV-26 | INV-27 |
| --- | --- | --- |
| Jira | "Vista de predicciones en dashboard", En curso | "Vista de recomendaciones compra/transferencias", En curso |
| Prioridad | Highest | Highest |
| Puntos | 8 (el campo de Jira está vacío) | 8 (el campo de Jira está vacío) |
| Épica | E9 ML Dashboard (INV-54) | E9 ML Dashboard (INV-54) |
| Sprint | Sprint 5 (21 sep – 10 oct) | Sprint 5 (21 sep – 10 oct) |
| Depende de | Fix previo (en `develop`), INV-20 e INV-25 | Fix previo (en `develop`), INV-21, INV-22 e INV-23 |
| Alimenta a | INV-28 (alertas ML), INV-35 (chat UI) y la demo (INV-43) | INV-28 e INV-32 (tool-calling) |
| Rama | `feature/INV-26-predicciones` | `feature/INV-27-recomendaciones` |

Las dos historias son independientes, pero van una después de la otra (V14):
INV-26 se integra a `develop` e INV-27 arranca desde ahí.

**Dentro del alcance**

- `src/pages/Predicciones.jsx` y `src/pages/Recomendaciones.jsx`, cada una con su entrada en `RUTAS` y sus pruebas.
- Etiquetas nuevas en `src/utils/etiquetas.js` para los valores de INV-21, INV-22 e INV-23 que aún no existen allí (V7).
- La regla de riesgo según el pronóstico (`calcularRiesgo`) y la exportación a CSV, cada una en `src/utils/` con su prueba.
- La prop `opcionVacia` de `SucursalSelector` (V10) y la búsqueda por `codigo_item` en `GET /api/consulta/productos` (V11).
- Agregar las páginas nuevas a la cobertura (`coverage.include` de `vite.config.js`).
- Actualizar la matriz de `frontend/README.md`, documentar cada vista y ampliar la guía de pantallas con un bloque por vista.

**Fuera del alcance**

- Funciones de `client.js`, `useConsulta`, `EstadoConsulta`, rutas y utilidades de prueba: ya existen.
- Pronóstico a otro horizonte que no sea 15 días hábiles.
- Serie diaria por producto, comparación de varios productos y exportación de predicciones.
- Aprobar o ejecutar compras y traslados (historia posterior).
- `incluir_balance` de transferencias en pantalla: el balance completo pesa 6,4 MB.
- Cambios al Dashboard y a Reportes, y cambios de contrato (parámetros o forma de las respuestas) de `ml_service` y del Core API. V11 amplía el criterio de búsqueda sin cambiar el contrato.
- Lint del frontend (INV-24), pruebas end-to-end automatizadas en el CI y el timeout de Nginx en producción (INV-34 e INV-36).

## Lo que entregó el fix y las vistas reutilizan

| Pieza del fix | Dónde | Cómo la usan las vistas |
| --- | --- | --- |
| `predecir({ idProducto, idSucursal })` | `src/api/client.js` | Predicciones. Manda `horizonte: 15`; la respuesta no trae la unidad (ver C1) |
| `getVentasProducto(idProducto, { sucursalId, ventanas })` | `src/api/client.js` | Predicciones. `GET /api/consulta/productos/{id}/ventas`: trae `unidad` y las ventanas (`desde`, `hasta`, `unidades`) |
| `getProductos({ busqueda, categoria, page, pageSize })`, `getInventarioDetalle(idProducto, idSucursal)` | `src/api/client.js` | Predicciones |
| `getRecomendacionesCompras({ sucursal, categoria, urgencia, incluirDetalle })` y `getRecomendacionesTransferencias({ sucursal, categoria, urgencia, incluirBalance })` | `src/api/client.js` | Recomendaciones. `sucursal` va por **nombre** |
| `getCategorias`, `TIMEOUT_ML_MS` (130 s), `ApiError` con `status` y `detail` | `src/api/client.js` | Ambas |
| `useConsulta(fn, deps, { timeoutMs, activo })` | `src/hooks/useConsulta.js` | Ambas. Devuelve `{ datos, cargando, error, recargar }`; cancela la consulta anterior, ignora la cancelada y no deja una respuesta vieja. `activo: false` no consulta |
| `EstadoConsulta`, `Cargando` (con aviso de espera larga), `MensajeError`, `DistintivoBodega` | `src/components/` | Ambas. Los 4xx muestran el `detail`; 502, 503, 504, timeout y red tienen texto fijo. `EstadoConsulta` ofrece "Reintentar" con cualquier error |
| `useSucursales()` (`porId`, `porNombre`, `fisicas`), `useSucursal()` (`sucursalId`, `sucursalNombre`, `setSucursalId`, `rawSucursalId`, `esBodega`, `showSelector`), `SucursalSelector` con `incluirBodega` | `src/hooks/`, `src/components/` | Ambas. `sucursalNombre` ya es el nombre canónico ("BODEGA_CENTRAL", "PRINCIPAL") |
| `fmtCantidad(n, unidad)`, `fmtConteo`, `fmtNumero`, `fmtDecimal`, `fmtFecha`, `fmtMonedaCorta` | `src/utils/formato.js` | Ambas: es-CO, kilos con decimales, nunca una cantidad redondeada a 0 |
| `ESTADOS_INVENTARIO`, `textoCobertura`, `COBERTURA_SIN_VENTAS`, `nombreUbicacion`, `TIPOS_ALERTA`, `URGENCIAS`, `BODEGA` | `src/utils/etiquetas.js` | Ambas, y se amplía (V7) |
| `RUTAS` con `roles` y página `lazy`, `GuardaRol` | `src/rutas.js` | Cada vista agrega una entrada |
| `renderConUsuario`, `simularApi`, `USUARIOS` | `src/test/utils.jsx` | Pruebas de ambas |
| Vitest con umbral de 80 % (líneas, funciones, ramas y sentencias) sobre `coverage.include` | `vite.config.js` | Las páginas nuevas hay que agregarlas al `include` |
| Matriz endpoint → pantalla y guía "cómo agregar una vista" | `frontend/README.md` | Se actualiza con cada vista |

## Revisión contra el código y los datos

Lo que el borrador decía bien quedó confirmado:
- Firmas de `client.js`, de `useConsulta` y del selector.
- Comportamiento real de la API: la Bodega da 422 en `predict` y una sucursal ajena 403. En recomendaciones, "Bodega Central" da 422 con la lista de válidas, y "principal" o "la 21" se normalizan.
- Cifras:
  - 1.340 líneas de compras: 585 urgentes, 255 altas, 500 normales y 784 que llegan tarde.
  - El 98,6 % de los pares es intermitente.
  - El balance pesa 6,4 MB.
- Las ventas son sin devoluciones (`NOT es_devolucion AND cantidad > 0`, aunque la vista se llame `v_ventas_diarias_netas`).
- Los grupos de pedido: semanal los martes, quincenal el 2 y el 16.
- El texto del aviso de vista desde la sucursal.

Lo que se corrigió:

| # | Tema | Corrección |
| --- | --- | --- |
| C1 | Unidad en Predicciones | `predict` no trae `unidad`; se toma del producto elegido en la búsqueda (`unidad` de `getProductos`, la misma que trae `getVentasProducto`) |
| C2 | Detalle de inventario | No trae unidad ni fecha: la fecha de la foto es la del último punto del `historial` (viene en orden ascendente; hoy tiene uno solo) y el estado sale de `semaforo` |
| C3 | Ventanas | Campos `desde`, `hasta` y `unidades` (también en los productos por kilo); la ventana se rotula con `hasta` |
| C4 | Prueba de riesgo | "Stock 556 y q50 3.366" mezclaba ARROZ ZULIA y HUEVOS. Se usan pares reales (ver Fase B) |
| C5 | Unidad de los días (V5) | Los días del pronóstico son **hábiles**; los del semáforo salen de la demanda observada del ETL. Cada lectura lleva su unidad |
| C6 | "Reintentar" | `EstadoConsulta` lo ofrece con cualquier error, no solo con 503 y 504 |
| C7 | Llegada de las compras a la Bodega | Esas líneas traen `fecha_llegada` (a la Bodega) y `fecha_llegada_sucursal` (dos días después). Ver V13 |
| C8 | Resumen y calendario | Nombres reales de los campos (ver Fase C) |
| C9 | Transferencias | La lista se llama `traslados` y trae `dias_habiles_llegada`. `vigilancia` existe en el esquema, pero hoy no aparece en los datos |
| C10 | Alertas | Compras: `posible_inconsistencia_inventario` con `compra_urgente` o `verificar_conteo`. Transferencias: `stock_negativo` con `pedido_urgente`. `sin_pronostico` (acción `ninguna`) solo llega con el balance; sin él, se cuenta. El filtro de urgencia no filtra las alertas |
| C11 | Tiempos y pesos | Compras: 31,7 s en frío, 0,06 s con caché, 1,19 MB con detalle y 737 KB sin él. Transferencias: 21,2 s en frío y 99 KB |
| C12 | Búsqueda de productos | Busca en el nombre y la familia, no en el código ("P1632" da 0). Ver V11 |
| C13 | Selector en Predicciones | `SucursalSelector` siempre ofrece "Todas las sucursales", que no sirve para un pronóstico. Ver V10 |

## Decisiones

| Código | Tema | Decisión |
| --- | --- | --- |
| V1 | Alcance | Cada historia entrega página, entrada en `RUTAS`, etiquetas nuevas, pruebas, documentación, la matriz del README y su bloque de la guía de pantallas. Fuera de V10 y V11, nada de base nueva |
| V2 | Identificadores | Predicciones: ids. Recomendaciones: el **nombre canónico** de `dim_sucursal` (`useSucursal().sucursalNombre`, por ejemplo "BODEGA_CENTRAL"), nunca el rótulo "Bodega Central" de `nombreUbicacion`. INV-23 normaliza mayúsculas, acentos y espacios de los extremos, no el guion bajo |
| V3 | Horizonte | Fijo en 15 días hábiles, sin selector |
| V4 | Límite de negocio | Referencia con su α; nunca intervalo ni sombreado. En perecederos (α = 0,167) queda bajo la mediana |
| V5 | Riesgo | Dos lecturas **rotuladas por separado**. "Cobertura del inventario": la del semáforo de Inventario, con `dias_cobertura`, `ESTADOS_INVENTARIO` y `textoCobertura`. "Riesgo según el pronóstico": días hábiles = stock / (q50 / 15); urgente ≤ 5, alta ≤ 10, normal (los umbrales de las políticas de INV-21). Los días se redondean a un decimal antes de compararlos, para que el valor y la etiqueta coincidan (HUEVOS en LA 21: 5,03 se ve "5,0" y es urgente). Con q50 = 0, "Sin demanda prevista"; con stock negativo, "Inconsistencia de inventario". La vista no suma los traslados en camino, como sí hace INV-21 |
| V6 | Roles | Los tres roles en `RUTAS`. `admin_sucursal` queda fijo en su sucursal; `admin_bodega` usa las dos vistas como el gerente. La Bodega no se elige en Predicciones |
| V7 | Etiquetas | Se amplían en `etiquetas.js`, sin módulos paralelos: urgencias de recomendaciones, grupos, motivos, ramas del modelo y los tipos y acciones de las alertas de INV-21, 22 y 23, incluida la acción `ninguna` |
| V8 | Cantidades | `fmtCantidad(n, unidad)` en las tablas y `fmtCantidadConUnidad(n, unidad)` ("3.366 unidades", "135,7 kg"; la regla de `texto_cantidad` del Core API, agregada en INV-26) en las tarjetas; en el CSV, el formato de V12 |
| V9 | Cobertura | `Predicciones.jsx` y `Recomendaciones.jsx` entran a `coverage.include` |
| V10 | Selector en Predicciones | `SucursalSelector` recibe `opcionVacia` (por defecto "Todas las sucursales"). Predicciones pasa "Elegir sucursal" e `incluirBodega={false}`. Las demás páginas no cambian |
| V11 | Búsqueda por código | `GET /api/consulta/productos` busca también en `codigo_item`. Mismos parámetros y misma respuesta: no cambia el contrato. Lleva su prueba y la descripción del parámetro al día |
| V12 | CSV | UTF-8 con BOM; separador `;`; decimales con coma, sin separador de miles ("77,1", "3366"); fechas ISO; la unidad en su propia columna. Es lo que Excel con la configuración de Colombia lee como número |
| V13 | Llegada en Compras | La columna "Llega" muestra `fecha_llegada_sucursal`. En las líneas de la Bodega se agrega debajo "a la Bodega: {fecha_llegada}" |
| V14 | Orden | INV-26 primero, integrada a `develop`; INV-27 después, desde `develop` |

**Por qué V5.** El semáforo del Dashboard y de Inventario sale de `dias_cobertura`
del ETL, con cortes en 3 y 7 días. El pronóstico de INV-21 usa 5 y 10 días
hábiles sobre q50. Para un mismo producto pueden no coincidir. ARROZ ZULIA en
PRINCIPAL tiene una cobertura de 5,3 d, que es "Bajo" en el semáforo; su
pronóstico de 1.251 unidades en 15 días hábiles le da 6,7 días hábiles, que es
"Alta". Mostrar una sola lectura escondería esa diferencia; mostrar las dos con
su rótulo la explica.

## Fase B · INV-26 · Vista de predicciones

Página `src/pages/Predicciones.jsx`, ruta `/predicciones`. Historia: *como
gerente, quiero ver la demanda prevista de un producto en una sucursal junto a
su historia y su stock, para planificar el abastecimiento.*

**Selección**
- Producto con búsqueda (`getProductos({ busqueda, pageSize: 20 })`, 300 ms de espera), que encuentra por nombre, familia o código (V11). Cada resultado muestra el nombre y el `codigo_item`.
- Sucursal con `SucursalSelector` (`incluirBodega={false}`, `opcionVacia="Elegir sucursal"`, V10). Un `admin_sucursal` no ve el selector y usa `useSucursal().sucursalId`.
- Con los dos elegidos se lanzan tres `useConsulta`: `predecir`, `getVentasProducto` con 8 ventanas y `getInventarioDetalle`. Mientras falte alguno, van con `activo: false`.

**Gráfico** (`recharts`)

- Barras sólidas: las 8 ventanas de 15 días hábiles, rotuladas con su `hasta`. Son siempre 8; las anteriores a la primera venta del producto valen 0 (G1), y eso no significa que se vendió 0.
- Una barra final, punteada: el pronóstico q50 a 15 días hábiles, con la insignia "IA". La última ventana termina en `fecha_fin`, la misma `fecha_features` de `predict`, así que el pronóstico sigue a la historia.
- Una línea horizontal con el límite de negocio, rotulada "Cuantil de negocio (α = …)". En perecederos lleva la nota de que es un cuantil bajo y no una cota de reposición.
- Una línea con el stock actual.
- Sin bandas ni sombreado. Las ventas son sin devoluciones.

**Tarjetas**

| Tarjeta | Contenido |
| --- | --- |
| Demanda prevista | `prediccion_q50` con la `unidad` del producto (C1), a 15 días hábiles |
| Límite de negocio | `intervalo_confianza.limite_superior` y su `alpha_negocio` |
| Stock actual | `stock_actual` del detalle y la fecha de la foto (el último punto del `historial`, C2) |
| Cobertura del inventario | `textoCobertura(dias_cobertura, stock_actual)` y el estado `semaforo` con `ESTADOS_INVENTARIO` (V5) |
| Riesgo según el pronóstico | Días hábiles hasta agotarse y su etiqueta (V5) |
| Rama del modelo | Intermitente, suave no perecedero o suave perecedero (V7) |
| Interpretación | El texto `interpretacion` tal como llega: la API ya escribe las cantidades en la unidad de venta y con separador de miles |
| Trazabilidad | `fecha_features` y `modelo_entrenado_en` |

**Estados.** Los errores y la carga los resuelven `EstadoConsulta`, `Cargando` y
`MensajeError`; la página solo agrega lo propio:

| Situación | Qué se muestra |
| --- | --- |
| Falta el producto o la sucursal | Mensaje de ayuda |
| 404 de `predict` (historia insuficiente) | El `detail`, más el stock y las ventanas, que sí llegan |
| Las 8 ventanas en 0 | Aviso: el producto no vendió en esta sucursal en ese período |
| 403, 422, 502, 503, 504, timeout | El mensaje de `MensajeError`, con "Reintentar" |

**Datos reales para las pruebas y la guía** (foto y features al 2025-12-31)

| Caso | Producto y sucursal | Valores |
| --- | --- | --- |
| Urgente | HUEVOS \*UND (P1632, id 91) en PRINCIPAL | Rama intermitente, q50 3.366,01, límite 4.608,72 (α 0,893), stock 489, cobertura 2,9 d "Crítico"; riesgo 489 / (3.366,01 / 15) = 2,2 días hábiles, urgente |
| Las dos lecturas difieren | ARROZ ZULIA \*500 GR (P3937, id 171) en PRINCIPAL | Suave no perecedero, q50 1.251,25, límite 1.659,64; stock 556, cobertura 5,3 d "Bajo"; riesgo 6,7 días hábiles, alta |
| Perecedero | HUEVOS \*UND en GLORIETA | Suave perecedero, q50 3.871,25, límite 3.094,03 (α 0,167), bajo la mediana |
| Por kilo | PAPA PASTUSA \*KL (P1814) en PRINCIPAL | q50 135,68 kg ("135,7 kg"), stock 77,1 kg |
| Historia insuficiente | FRIJOL CARGAMANTO GRANOS (id 3367) en PRINCIPAL | 404: "No hay historia suficiente para producto_id=02458, sucursal_id=PRINCIPAL: 0 días con venta hasta 2025-12-31 (el modelo exige al menos 30)"; las 8 ventanas en 0 |
| Bodega | Cualquier producto con id_sucursal 5 | 422: "La sucursal BODEGA_CENTRAL (bodega_central) no es una sucursal física…" |
| Sucursal ajena | `admin.principal` pide GLORIETA | 403: "Solo puede pronosticar su sucursal (PRINCIPAL)" |

**Criterios de aceptación**

1. Se puede elegir un producto y una sucursal física y ver, en una pantalla, la predicción, las 8 ventanas, el stock y la interpretación.
2. El gráfico no usa sombreado ni muestra un intervalo; el límite aparece como referencia con su α.
3. No hay selector de horizonte; el texto dice "15 días hábiles".
4. La cobertura del inventario y el riesgo según el pronóstico se muestran por separado, con su rótulo y su unidad de días (V5), incluidos q50 = 0 y el stock negativo.
5. Las cantidades salen con `fmtCantidadConUnidad` y la unidad del producto (kg o unidad).
6. La Bodega Central no se puede elegir y el selector no ofrece "Todas las sucursales" (V10). Un `admin_sucursal` no ve el selector.
7. Se muestran la fecha de la foto de inventario y la de las features.
8. El estado de riesgo se comunica con texto y no solo con color.
9. La búsqueda encuentra un producto por nombre y por código (V11).
10. La página está en `RUTAS` para los tres roles y se descarga al entrar (`lazy`).
11. Usa solo funciones de `client.js` y los componentes y hooks del fix; no agrega funciones de API ni formatos propios.

**Pruebas (Vitest, con `renderConUsuario`, `simularApi` y `USUARIOS`)**

| Caso | Esperado |
| --- | --- |
| `calcularRiesgo(489, 3366.01)` | Urgente, 2,2 días hábiles |
| `calcularRiesgo(556, 1251.25)` | Alta, 6,7 días hábiles |
| `calcularRiesgo` con q50 = 0 | "Sin demanda prevista", no urgente |
| `calcularRiesgo` con stock negativo | Inconsistencia de inventario |
| Cobertura 999 en el detalle | "Sin ventas" en la cobertura del inventario |
| Ventanas de la API | Se transforman en los datos del gráfico, en orden, siempre 8, rotuladas con `hasta` |
| Perecedero (α = 0,167) | Aparece la nota de cuantil bajo |
| Producto por kilo | La demanda y el stock salen en kg con decimales |
| 404 de `predict` | El `detail`, con el stock y las ventanas |
| Las 8 ventanas en 0 | Aviso de que no vendió |
| `admin_sucursal` | Sin selector; usa su sucursal |
| Selector | Ofrece "Elegir sucursal" y las sucursales físicas, sin "Todas las sucursales" ni la Bodega |
| Búsqueda | Espera 300 ms, pide 20 resultados y muestra nombre y código |
| Cambio de producto antes de que responda el anterior | Se ignora la respuesta vieja |
| `SucursalSelector` con `opcionVacia` | Muestra ese texto; sin la prop, "Todas las sucursales" |
| Core API: búsqueda por código | `busqueda=P1632` encuentra HUEVOS \*UND |

## Fase C · INV-27 · Vista de recomendaciones

Página `src/pages/Recomendaciones.jsx`, ruta `/recomendaciones`. Historia:
*como gerente, quiero ver las compras y los traslados recomendados, filtrarlos
y exportarlos, para decidir el abastecimiento.* Consume
`getRecomendacionesCompras` (con `incluirDetalle: false`) y
`getRecomendacionesTransferencias` (con `incluirBalance: false`).

**Filtros**
- **Sucursal:** el selector muestra "Bodega Central", pero la llamada lleva el nombre canónico (V2). BODEGA_CENTRAL es válida aquí para el gerente y `admin_bodega`; `admin_sucursal` queda fijo y la API se lo aplica sola (`filtros_aplicados.sucursal_por_rol`).
- **Categoría:** las de `getCategorias`, en orden alfabético, como en Inventario.
- **Urgencia:** `urgente`, `alta` o `normal`; en transferencias, también `vigilancia`. El filtro de urgencia no filtra las alertas (C10).
- **Búsqueda local** por nombre.

**Encabezado de contexto**

- `fecha_inventario`, `calculado_en` y las versiones de las políticas. Compras trae `politicas.inv21` y `politicas.inv22` (versión y fecha); transferencias, `politicas.version` y `politicas.fecha`.
- El calendario de pedidos (`calendario`). Para cada grupo muestra el pedido, la llegada a la Bodega y a la sucursal, el pedido siguiente y hasta cuándo cubre:

  | Grupo | Destino | Pedido | Llega | Llega a la sucursal | Siguiente | Cubre hasta |
  | --- | --- | --- | --- | --- | --- | --- |
  | Quincenal | Bodega | 2 ene 2026 | 7 ene | 9 ene | 16 ene | 23 ene (22 días) |
  | Semanal | Sucursal | 6 ene 2026 | 11 ene | 11 ene | 13 ene | 18 ene (17 días) |

- Las tarjetas del resumen.
  - **Compras:** `lineas` (con `lineas_sucursal` y `lineas_bodega`), `cantidad` en unidades y en kilos por separado, `cantidad_directa` y `cantidad_bodega`, `cubiertos_por_bodega` y `alertas`. Con una sucursal física filtrada, también `necesidad_via_bodega`.
  - **Transferencias:** `traslados`, `cantidad_trasladada`, `deficit_neto` y `alertas`, más `alertas_sin_pronostico` como conteo.

**Pestaña Compras** (`compras`, 1.340 líneas sin filtros)

| Columna | Origen |
| --- | --- |
| Producto | `nombre_producto` y `producto_id` |
| Destino | `destino` y `tipo_destino`, con `DistintivoBodega` cuando es la Bodega |
| Grupo | `grupo`: semanal (martes) o quincenal (2 y 16) |
| Cantidad | `cantidad` con `fmtCantidad` según `unidad` |
| Urgencia | `urgencia`, con texto |
| Días hasta agotarse | `dias_hasta_agotarse` (días hábiles) |
| Pedido | `fecha_pedido` con `fmtFecha` |
| Llega | `fecha_llegada_sucursal`; en las líneas de la Bodega, debajo "a la Bodega: {fecha_llegada}" (V13) |
| Llega tarde | Insignia si `llega_tarde` |
| Motivo | `reposicion` o `stock_negativo` |
| Necesidad de la sucursal | `necesidad_sucursal`, solo con una sucursal física filtrada |

No hay columna de proveedor. Debajo van dos bloques:
- **Cubrir con traslado** (`cubrir_con_traslado`, 277 sin filtros): producto, necesidad, sobrante de la Bodega, unidad y urgencia.
- **Alertas de inconsistencia de inventario** (`alertas`, 220): producto, sucursal, stock y acción.

Las alertas de compras se llaman `posible_inconsistencia_inventario` y las de
la página Alertas (INV-25), `inconsistencia_inventario`. Es el mismo concepto y
en pantalla lleva el mismo rótulo, "Inconsistencia de inventario".

**Aviso de vista desde la sucursal.** Con una sucursal física filtrada y líneas
de la Bodega en pantalla: *"La urgencia y los días se calculan desde {sucursal};
la cantidad es la de toda la compra a la Bodega."* Con PRINCIPAL son 814 líneas,
650 de ellas de la Bodega.

**Pestaña Transferencias** (`traslados`, 119 líneas sin filtros)
- **Columnas:** producto, origen, destino, cantidad y unidad, urgencia, días hasta agotarse, llegada (`fecha_llegada` y `dias_habiles_llegada`) y `llega_tarde`.
- **Debajo:** el resumen y las alertas (`stock_negativo`, con la acción `pedido_urgente`).
- El balance no se carga.

**Etiquetas nuevas en `etiquetas.js` (V7).** `URGENCIAS` hoy tiene las de las
alertas de INV-25 (`critica`, `alta`, `media`); las recomendaciones usan otras:

| Campo | Valores a etiquetar |
| --- | --- |
| `urgencia` de recomendaciones y riesgo del pronóstico | `urgente`, `alta`, `normal`, `vigilancia` |
| `grupo` | `semanal` (martes), `quincenal` (2 y 16) |
| `motivo` | `reposicion`, `stock_negativo` |
| `tipo` de alerta de INV-21, 22 y 23 | `posible_inconsistencia_inventario`, `stock_negativo` (los dos: "Inconsistencia de inventario"), `sin_pronostico` |
| `accion` de alerta | `compra_urgente`, `verificar_conteo`, `pedido_urgente`, `ninguna` |
| `rama` del modelo (INV-26) | `intermitente`, `suave_no_perecedero`, `suave_perecedero` |

**Carga y volumen**

- La primera consulta tarda unos 32 s en compras y 21 s en transferencias. `Cargando` ya avisa de la espera larga y el cliente espera hasta 130 s; con la caché del Core API caliente, cada filtro responde en unos 60 ms.
- Si un filtro cambia mientras hay una consulta en curso, `useConsulta` cancela la anterior.
- Paginación y orden en el cliente, 50 filas por página, como Alertas. El orden inicial es el de la API (por urgencia). El Core API no pagina estos endpoints.
- Errores: el 409 muestra su `detail` ("La foto de inventario (…) es posterior a la última venta cargada…"); 503 y 504, su texto fijo; 403 y 422, su mensaje. Todos con "Reintentar" (C6).

**Exportación a CSV**

- Un botón por pestaña, sobre **todas** las filas que pasan los filtros y la búsqueda, no solo la página visible.
- El formato de V12: UTF-8 con BOM, `;`, decimales con coma, sin separador de miles y fechas ISO.
- Las columnas de la tabla más `fecha_inventario` y `calculado_en`. La unidad va en su propia columna: nunca se suman unidades con kilos.
- Los campos con `;`, comillas o saltos de línea se escapan con comillas dobles.

**Criterios de aceptación**

1. Compras muestra las columnas de la tabla, sin proveedor, con `cubrir_con_traslado` y las alertas de inconsistencia.
2. Transferencias muestra origen, destino, cantidad, urgencia, llegada y `llega_tarde`.
3. Los filtros se combinan y la llamada lleva `sucursal` con el nombre canónico (V2), `categoria` y `urgencia`.
4. Con una sucursal física filtrada y líneas de la Bodega, se muestra el aviso de vista desde la sucursal.
5. Se ven la fecha de la foto, `calculado_en`, las versiones de las políticas y el calendario de pedidos.
6. El resumen y las cantidades separan unidades y kilos, con `fmtCantidad`.
7. La carga en frío usa `Cargando`, la consulta anterior se cancela al cambiar un filtro y los errores 409, 503 y 504 se muestran con `MensajeError`.
8. La exportación respeta los filtros, abarca todas las filas y Excel la abre con los números como números (V12).
9. `admin_sucursal` ve solo lo suyo y no puede elegir la Bodega.
10. Los rótulos de urgencia, grupo, motivo y alertas salen de `etiquetas.js`, sin textos fijos en la página.
11. La página está en `RUTAS` para los tres roles y se descarga al entrar (`lazy`).

**Pruebas (Vitest, con `renderConUsuario`, `simularApi` y `USUARIOS`)**

| Caso | Esperado |
| --- | --- |
| Elegir la Bodega en el selector | La llamada lleva `sucursal=BODEGA_CENTRAL`, no "Bodega Central" |
| Elegir sucursal, categoría y urgencia | La llamada lleva los tres parámetros |
| Compras de la respuesta de INV-23 | Se muestran las columnas y no existe la de proveedor |
| Línea de la Bodega | "Llega" con la fecha de la sucursal y debajo la de la Bodega |
| Sucursal física con línea de la Bodega | Aparece el aviso |
| Resumen con `unidad` y `kg` | Se muestran por separado, con `fmtCantidad` |
| Alertas `posible_inconsistencia_inventario` y `stock_negativo` | Rótulo "Inconsistencia de inventario" |
| Valor de urgencia, motivo o acción sin etiqueta | No rompe la página |
| Lista vacía | "Sin resultados", no un error |
| Cambio rápido de filtros | Se cancela la consulta anterior |
| 409, 503 y 504 | El mensaje de cada uno, con "Reintentar" |
| CSV | Empieza con BOM, usa `;` y coma decimal, escapa `;`, comillas y saltos de línea, trae `unidad` y todas las filas filtradas |
| `admin_sucursal` | Selector fijo y sin la Bodega |

## Orden de ejecución

| Paso | Qué | Rama |
| --- | --- | --- |
| 1 | Estos requerimientos; V10, V11 y Predicciones, con su entrada en `RUTAS`, sus etiquetas, sus pruebas, la matriz del README, `docs/INV-26-predicciones.md` y su bloque de la guía | `feature/INV-26-predicciones` |
| 2 | Integrar INV-26 a `develop` | — |
| 3 | Recomendaciones, con sus etiquetas, el CSV, su entrada en `RUTAS`, sus pruebas, la matriz, `docs/INV-27-recomendaciones.md` y su bloque de la guía | `feature/INV-27-recomendaciones`, desde `develop` |
| 4 | Integrar INV-27 a `develop` | — |

## Definition of Done

**Cada historia**

- [ ] Cumple sus criterios de aceptación.
- [ ] Pruebas de Vitest con el umbral de 80 % en líneas, funciones, ramas y sentencias, con la página agregada a `coverage.include`.
- [ ] `npm run test:cov`, `npm run build` y `npm audit` (0 vulnerabilidades) pasan, como en el CI.
- [ ] La matriz de `frontend/README.md` apunta a la pantalla que consume las funciones de INV-26 o INV-27.
- [ ] Sin funciones de API, formatos ni rótulos propios que ya existan en `client.js`, `formato.js` y `etiquetas.js` (reglas sin deuda del fix).
- [ ] Autorrevisión documentada en el commit.
- [ ] `docs/INV-26-predicciones.md` o `docs/INV-27-recomendaciones.md`.
- [ ] Integrado en `develop`.
- [ ] Verificado con los tres roles en el navegador, con la guía de pantallas ampliada con un bloque para la vista nueva (H para Predicciones, I para Recomendaciones).
- [ ] Datos desde el Core API (`/api/ml/*` y `/api/consulta/*`), no desde `ml_service`.
- [ ] Sin bugs bloqueantes.

**Solo INV-26**

- [ ] La búsqueda por código (V11) con su prueba en el Core API y las suites del Core API en verde.

**Solo INV-27**

- [ ] Una carga en frío verificada de punta a punta.
- [ ] Exportación verificada abriendo el CSV en Excel.

## Riesgos y limitaciones

- **Calendario.** El Sprint 5 cierra el 10 de octubre: quedan 4 días. INV-26 cabe en uno y medio e INV-27 en dos.
- **Puntos.** El fix creció mucho más allá de lo que 8 SP suelen cubrir: incluyó la vista de reportes, la adaptación del Dashboard, Inventario y Alertas, las versiones mayores del frontend y el seed de usuarios. Se registró dentro de INV-26 (F3). Lo que queda de INV-26 y de INV-27 es menos de lo que 8 SP cada una sugerían.
- **Dos lecturas de riesgo.** Si el semáforo del ETL y el pronóstico discrepan, la pantalla lo muestra. Hay que explicarlo, no ocultarlo (V5).
- **Nombre de la Bodega.** Mandar el rótulo "Bodega Central" en vez de "BODEGA_CENTRAL" da un 422 en INV-23. Tiene prueba propia.
- **Cobertura.** El umbral de 80 % es global sobre `coverage.include`: una página nueva con poca cobertura hace fallar el CI. Las gráficas no se dibujan en jsdom, así que la lógica que alimenta el gráfico va en funciones puras con su prueba.
- **Etiquetas.** `etiquetaTipoAlerta` convierte guiones bajos en espacios si no conoce el tipo, así que un tipo nuevo sin etiqueta se vería crudo.
- **Foto única.** El stock es al 2025-12-31 y el pronóstico se calcula a esa fecha. Las pantallas deben mostrar esas fechas.
- **Casi todo es intermitente.** El 98,6 % de los pares lo es: muchas ventanas históricas quedarán en 0 o muy bajas. Es lo esperado.
- **Primera llamada lenta.** Unos 32 s en frío para compras. En producción, Nginx necesitará un `proxy_read_timeout` mayor a 130 s (INV-34 e INV-36).
- **Sin paginación en el backend.** Compras sin filtros trae 1.340 líneas (737 KB sin el detalle); el cliente las pagina.
- **Excel.** V12 sigue la configuración regional de Colombia. Un Excel con otra configuración puede necesitar "Datos → Desde texto/CSV".

## Pendientes de confirmar

Ninguno bloquea el arranque.

| # | Pregunta | Valor por defecto mientras tanto |
| --- | --- | --- |
| 1 | ¿Cómo se refleja en Jira el trabajo del fix dentro de los 8 SP de INV-26? | Descripción de INV-26 con el fix entregado y la vista pendiente |
| 2 | ¿Balance completo de transferencias en pantalla más adelante? | No en esta historia |

## Ambiente de desarrollo

1. `git checkout develop && git pull`, y la rama de la historia: `feature/INV-26-predicciones` o `feature/INV-27-recomendaciones`.
2. Usuarios de prueba: `docker exec inventaio-api python -m scripts.seed_usuarios` (clave `admin123`).
3. `docker compose up -d ml-service api`; en `frontend/`, `npm ci` y `npm run dev` (Node 22.12 o superior). `ml-service` corre desde su imagen: si cambia su código, `docker compose up -d --build ml-service`.
4. Pruebas: `npm run test` y `npm run test:cov` en `frontend/`; `docker exec inventaio-api python -m pytest` para V11.
5. Verificar con `gerente@inventaio.co`, `admin.principal@inventaio.co` y `bodega@inventaio.co`.

**Archivos a crear o tocar**

| Archivo | Cambio |
| --- | --- |
| `docs/INV-26-27-requerimientos.md` (este) | Requerimientos |
| `frontend/src/pages/Predicciones.jsx` y su prueba (nuevos) | Fase B |
| `frontend/src/utils/riesgo.js` y su prueba (nuevos) | `calcularRiesgo` (V5) |
| `frontend/src/components/SucursalSelector.jsx` y su prueba | `opcionVacia` (V10) |
| `api/consulta/router.py` y su prueba | Búsqueda por `codigo_item` (V11) |
| `frontend/src/pages/Recomendaciones.jsx`, su prueba, `frontend/src/utils/csv.js` y su prueba (nuevos) | Fase C |
| `frontend/src/rutas.js` | Una entrada por vista |
| `frontend/src/utils/etiquetas.js` y su prueba | Etiquetas de V7 |
| `frontend/vite.config.js` | Las dos páginas en `coverage.include` |
| `frontend/README.md` | Matriz actualizada |
| `docs/INV-26-pruebas-pantallas.md` | Bloques H (Predicciones) e I (Recomendaciones) |
| `docs/INV-26-predicciones.md`, `docs/INV-27-recomendaciones.md` (nuevos) | Documentación |
