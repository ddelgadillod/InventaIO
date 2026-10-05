# INV-26 · Fix previo · Ventas por producto, base del frontend y adaptación de la app

Este fix deja la app de Release 1 funcionando con la bodega real y sobre los
endpoints actuales del Core API, y prepara la base para que las vistas de
predicciones (INV-26) y de recomendaciones (INV-27) solo agreguen su página,
su ruta y sus pruebas. Agrega el endpoint de ventas por producto, que la vista
de predicciones necesita. Con la adenda (K1–K10) cierra además lo que iba a
quedar reportado: higiene del repo, Node 22 en el CI, versiones mayores del
frontend, ajustes de inventario, alertas y el KPI en riesgo, la vista de
reportes de ventas y el seed de usuarios. No quedan pendientes por reportar.

La especificación, con las decisiones G1–G9, H1–H5, J1–J5 y K1–K10, está en
[`INV-26-fix-requerimientos.md`](INV-26-fix-requerimientos.md). Este documento
dice cómo quedó implementado y qué dio con los datos reales. La guía para
trabajar sobre la base y la matriz endpoint → pantalla están en
[`frontend/README.md`](../frontend/README.md).

## A1 · Ventas por producto

`GET /api/consulta/productos/{id_producto}/ventas`, en `api/consulta/router.py`.
Devuelve las ventas de un producto en una sucursal física en ventanas de 15
días hábiles: días con alguna venta en la red, como el modelo. Los días sin
venta cuentan 0 (G1), y la última ventana termina en el último día hábil de la
red. El agrupamiento está en la función `armar_ventanas`, que se prueba sin
base. Los días hábiles se piden con `LIMIT ventanas × 15`, y la consulta tarda
unos 35 ms.

Con la bodega real (foto al 2025-12-31):

| Consulta | Resultado |
| --- | --- |
| P1632 en PRINCIPAL, `ventanas=3` | 2.426 (17 nov – 1 dic), 3.522 (2 – 16 dic) y 4.608 (17 – 31 dic) unidades |
| P1632 en PRINCIPAL, por defecto | 8 ventanas, de 2025-09-02 a 2025-12-31; cada una igual a la suma a mano sobre `v_ventas_diarias_netas` |
| `fecha_fin` | 2025-12-31, igual al `fecha_features` de `POST /api/ml/predict` |
| `unidad` (J5) | "unidad" para P1632; "kg" para PAPA PASTUSA \*KL (P1814), que se vende por kilo |
| `gerente` o `admin_bodega` sin `sucursal_id` | 422 "sucursal_id es obligatorio. Válidos: 1 (PRINCIPAL), 2 (LA 21), 3 (GLORIETA)" |
| La Bodega (`gerente`, `admin_bodega`) | 422 "La Bodega Central no vende: las ventas son por sucursal física" |
| SIN_SUCURSAL o un id inexistente | 422 con la lista de válidos (R2 de INV-25) |
| `admin_sucursal` con otra sucursal / con la Bodega | 403 (R1 de INV-25) |
| Producto inexistente | 404, después de validar la sucursal |
| `ventanas` en 0 o 25 | 422 |

## A2 · Base del frontend

| Pieza | Archivo | Qué hace |
| --- | --- | --- |
| `ApiError`, timeout y cancelación | `src/api/client.js` | Errores con `status` y `detail`, el 422 de validación como texto, `timeoutMs` (130 s en ML), `clave` y `signal` para cancelar |
| Funciones nuevas | `src/api/client.js` | `getCategorias`, `getProducto`, `getInventarioDetalle` y `cambiarPassword` (las usa la app); `getProductos`, `getVentasProducto`, `predecir`, `getRecomendacionesCompras` y `getRecomendacionesTransferencias` (las vistas). `getDistribucionCategorias` salió por no tener pantalla (J1) y volvió con la vista de reportes (A9), junto con `getVentas`, `getComparativa` y `getValorizado` |
| Proxy de desarrollo | `vite.config.js` | `timeout` y `proxyTimeout` de 130 s |
| `useSucursales` | `src/hooks/useSucursales.js` | Una sola carga de `/consulta/sucursales`; `porId`, `porNombre` y `fisicas` |
| `useSucursal` | `src/hooks/useSucursal.js` | Lee `id_sucursal` de `/auth/me`; devuelve también `sucursalNombre` y `esBodega` |
| `SucursalSelector` | `src/components/SucursalSelector.jsx` | `incluirBodega`, "Bodega Central" y aviso si la carga falla |
| Rutas | `src/rutas.js`, `src/components/GuardaRol.jsx`, `App.jsx` | Una lista `RUTAS` para el menú y las rutas, con guarda por rol; cada página se descarga al entrar a ella (A11) |
| `useConsulta` | `src/hooks/useConsulta.js` | Consulta desde una página: cancela la anterior, ignora la cancelada y nunca deja una respuesta vieja |
| Estados | `Cargando`, `MensajeError`, `EstadoConsulta`, `DistintivoBodega` | Spinner con aviso de espera larga, error por código con "Reintentar", y el distintivo de la Bodega |
| Formato y etiquetas | `src/utils/formato.js`, `src/utils/etiquetas.js` | Números de es-CO, cantidades según la unidad, moneda corta, fechas; nombres de alertas, urgencias, estados de inventario, ubicaciones y unidad de venta |
| Pruebas | `src/test/setup.js`, `src/test/utils.jsx`, `package.json` | Vitest 5 (A7), Testing Library y jsdom; `renderConUsuario`, `simularApi`, `USUARIOS`; scripts `test` y `test:cov` |

## A3 · La app sobre la bodega real

| Pantalla | Antes | Ahora |
| --- | --- | --- |
| Dashboard | Un error en una de las 5 consultas tumbaba la página; "Ventas hoy"; claves crudas en el widget de alertas; con la Bodega, ventas en $0 y gráficas que desaparecían; sin entrada para `admin_bodega` | Cada bloque carga y falla por separado; "Ventas del día" y "Ventas del mes" con la fecha de la foto; etiquetas de alertas; vista de Bodega (H1); `admin_bodega` lo ve y entra a él (H2); semáforo con cuatro tramos, uno de inconsistencia (A8) |
| Inventario | 15 categorías fijas de la bodega simulada; "999.0d" y coberturas negativas; sin `stock_bodega`; errores perdidos; sin detalle | Las 33 categorías de la bodega; "Inconsistencia" con cobertura "—", ahora como estado de la API y con su filtro (A8), y "Sin ventas" (H3); columna "Stock Bodega" y distintivo (G6); separador de miles y un decimal en los productos por kilo (A8); panel de detalle con el proveedor (J2, J3) |
| Alertas | Sin `inconsistencia_inventario`; 4.452 tarjetas en una lista; errores perdidos | Etiqueta y filtro del tipo nuevo; distintivo "Bodega"; páginas de 50 que entrega la API (A8, K2); los errores se muestran |
| Menú | Rutas sin guarda; sin cambio de contraseña | Menú y rutas desde `RUTAS` con guarda por rol; "Cambiar contraseña" (J4); "Reportes" (A9) |

## A4 · Ruta sin deuda técnica

- **Matriz** en `frontend/README.md`: los 28 endpoints con su función, su pantalla y su historia.
  - 20 tienen pantalla: los 16 de A3 y los 4 de reportes que consume la vista nueva (A9).
  - 5 los consumen INV-26 e INV-27, con su función ya lista y probada.
  - Los 2 de proveedores no se consumen por decisión (J3).
  - El health es de infraestructura.
- **Reglas sin deuda** y **guía para agregar una vista**, en el mismo README.
- **Vista de reportes de ventas**: iba a ser una historia nueva (J1); con la adenda se hizo en este fix (A9).
- **El OpenAPI en YAML de Postman** (`api/tests/postman/inventaio-core-api.openapi.yml`) quedó regenerado con todos los cambios del Core API (A11).

## A5 · Higiene

| Cambio | Por qué |
| --- | --- |
| `.gitattributes` con `*.sh text eol=lf` | Después de cada merge, los `.sh` quedaban en CRLF y fallaban en WSL y en el contenedor |
| `ml_service/tests/conftest.py` lee `MODELOS_DIR` si está definida | Las pruebas corren dentro de la imagen, donde los modelos están en otra ruta |
| Se borró la carpeta vacía `frontend/src/{pages,components,api,assets}` | La había dejado un `mkdir` con llaves que no se expandieron |
| Se quitó la referencia a `INV-26-27-requerimientos.md` (K1) | Los requerimientos del fix son autosuficientes; las vistas tendrán su propio documento |

## A6 · Plataforma

- **CI** (`.github/workflows/ci.yml`), job del frontend: Node desde `frontend/.nvmrc` (22), `npm ci`, `npm run test:cov`, `npm audit --omit=dev --audit-level=high` y el build (K4). El nombre del job ("Build frontend (Vite)") no cambia, para no romper los checks obligatorios de la rama.
- **Node**: `engines` en `>=22.12` (lo pide Vitest 5) y `.nvmrc` con 22. Node 20 dejó de tener soporte en abril de 2026.

## A7 · Versiones mayores

Una por una, con las pruebas, el build, `npm audit` y una comparación de
capturas antes y después (Playwright, los tres roles, todas las pantallas).

| Paquete | De | A | Cambios en el código |
| --- | --- | --- | --- |
| `react-router-dom` → `react-router` | 6.30.6 | 7.18 | Los imports pasan a `react-router`; desaparecen los avisos de las banderas de v7 en las pruebas |
| `vite` | 5.4.21 | 8.3 (Rolldown) | Ninguno; la respuesta de 40 s sigue pasando por el proxy |
| `@vitejs/plugin-react` | 4.7 | 6.1 | Ninguno |
| `vitest`, `@vitest/coverage-v8` | 3.2.7 | 5.0 | Ninguno; con jsdom 26.1 |
| `tailwindcss` | 3.4 | 4.3 | Plugin `@tailwindcss/vite`; el tema pasa a `@theme` en `src/index.css`; salen `tailwind.config.js`, `postcss.config.js`, `postcss` y `autoprefixer` |

**Revisión visual.** React Router 7 y Vite 8 dejaron las capturas idénticas.
Con Tailwind 4 solo cambian tres colores de la paleta, que v4 define en OKLCH:
`red-600` (#dc2626 → #e7000b), `red-500` (#ef4444 → #fb2c36) y `green-500`
(#22c55e → #00c950). Los colores de la marca no cambian. Hubo tres ajustes:

- `DistintivoBodega` lleva `leading-4`: con la altura de línea de v4, el distintivo se encogía.
- El `border-3` del spinner de carga, que en v3 no existía, ahora se dibuja como se escribió.
- Un bloque de compatibilidad en `src/index.css` mantiene lo que v3 daba por defecto: borde gris, cursor de mano en los botones y placeholder gris.

**Vulnerabilidades.** `npm audit` pasó de 19 (antes del fix) a 12 con
`npm audit fix` y a 0 con las versiones mayores.

## A8 · Ajustes de funcionalidad

**Unidad en la lista de inventario.** `InventarioItem` trae `unidad` ("unidad"
o "kg"), como los productos (J5). La tabla muestra un decimal en los productos
por kilo: la papa P1814 en PRINCIPAL se ve "77,1" en lugar de "77".

**Paginación de alertas (K2).** `GET /api/alertas` acepta `page` (≥ 1) y
`page_size` (1–500; 50 si solo llega `page`). Con ellos trae solo esa página y
agrega `page`, `page_size` y `pages`; sin ellos responde igual que en INV-25
(`response_model_exclude_unset`). La página de Alertas pide de a 50.

| Consulta (gerente) | Resultado |
| --- | --- |
| Sin `page` | Las 4.452 alertas; respuesta idéntica a la de INV-25 (1.366.500 bytes) |
| `page=1` | 50 alertas, 16,6 KB; `pages` 90 |
| `tipo=inconsistencia_inventario&page=5` | Las 20 últimas de 220 |
| `admin.principal`, `page=1` | 1.308 alertas propias, 27 páginas |
| `page=0`, `page_size=0` o `501` | 422 |

**Estado de inconsistencia (K3).** El semáforo es `inconsistencia` cuando el
stock es negativo, antes de mirar la cobertura. Una sola definición
(`SEMAFORO_CONDICION` en `api/inventario/router.py`) arma el estado de cada
fila, el filtro y los conteos del resumen. Con la foto al 2025-12-31:

| Ubicación | OK | Bajo | Crítico | Inconsistencia | Total |
| --- | --- | --- | --- | --- | --- |
| Toda la red | 9.381 | 386 | 1.114 | 220 | 11.101 |
| PRINCIPAL | 3.611 | 138 | 202 | 95 | 4.046 |
| LA 21 | 1.641 | 60 | 147 | 40 | 1.888 |
| GLORIETA | 2.842 | 109 | 173 | 70 | 3.194 |
| Bodega Central | 1.287 | 79 | 592 | 15 | 1.973 |

Crítico e inconsistencia coinciden con las alertas de stock crítico y de
inconsistencia. El CEPILLO LAVA-AUTOS en GLORIETA (stock −44) sale como
`inconsistencia` en la lista y en el detalle. El Dashboard dibuja el cuarto
tramo y Inventario filtra por "◆ Inconsistencia". `test_inventario.sh` acepta
el estado nuevo y lo suma al total.

La regla vive en `api/core/semaforo.py` (`SEMAFORO_CONDICION`, `SEMAFORO_SQL` y
`SEMAFORO_EN_RIESGO`), y la usan inventario y los KPIs.

**KPI "En riesgo" (K9).** Cuenta los tramos bajo y crítico del semáforo. Antes
contaba la cobertura menor a 7 días, que incluía 202 filas con stock negativo:

| Ubicación | Antes | Ahora (bajo + crítico) |
| --- | --- | --- |
| Toda la red | 1.702 | 1.500 |
| PRINCIPAL | 434 | 340 |
| LA 21 | 238 | 207 |
| GLORIETA | 344 | 282 |
| Bodega Central | 686 | 671 |

Ninguna prueba, script ni colección de INV-25 comparaba el valor del KPI; solo
cambiaron los datos simulados de `Dashboard.test.jsx`. Resuelve el pendiente 2
de INV-25, que queda anotado en sus requerimientos.

## A9 · Vista de reportes de ventas

Ruta `/reportes`, para los tres roles con la regla de permisos de INV-25 (K5),
en `src/pages/Reportes.jsx`.

| Bloque | Endpoint | Qué muestra |
| --- | --- | --- |
| Ventas | `/reportes/ventas` | Valor, margen, cantidad y transacciones, y la gráfica por día, semana o mes |
| Comparativa | `/reportes/ventas/comparativa` | Valor y cantidad contra el período anterior, con la variación y sus fechas; no aplica con "toda la historia" |
| Distribución por categorías | `/reportes/distribucion-categorias` | Participación de cada categoría en el valor vendido |
| Tendencia por sucursal | `/reportes/tendencias?por_sucursal=true` | Una serie por sucursal |
| Valorizado del inventario | `/consulta/inventario/valorizado` | Valor del stock por categoría y ubicación a la fecha de la foto |

**Filtros (K7).** Por defecto, el mes de la última venta (diciembre de 2025).
Atajos de mes, trimestre, año y toda la historia (`src/utils/periodos.js`),
que toman las fechas de `datos_desde` y `datos_hasta`, y rango libre. La
agrupación sigue al atajo (día, semana, mes) y se puede cambiar. Categoría y
ubicación; el `admin_sucursal` queda fijo en la suya. Con la Bodega elegida
solo se ve el valorizado, con la nota "La Bodega Central no vende".

**Cambios aditivos en el Core API.** Sin los parámetros nuevos, las respuestas
son las de INV-25: sus pruebas y su colección siguen pasando.

| Endpoint | Cambio |
| --- | --- |
| `/reportes/ventas` | `datos_desde` y `datos_hasta`: primera y última fecha con ventas (2022-01-02 y 2025-12-31). Se calculan con `EXISTS` sobre `dim_tiempo`: unos 0,2 s, frente a 0,45 s con `MIN`/`MAX` |
| `/reportes/ventas/comparativa` | Acepta `categoria`. `periodo_anterior` pasa del texto "periodo equivalente anterior" a las fechas: "2025-10-31 / 2025-11-30" |
| `/reportes/tendencias` | Acepta `categoria` y `agrupacion` (`dia`, `semana`, `mes`); el promedio móvil de 7 días solo se calcula por día |

Cifras de control: diciembre de 2025 vende 737.879.055,35 (+50,1 % contra el
período anterior, como en INV-25); la comparativa de Licores es igual a su
valor en la distribución por categorías, y la suma de diciembre en la tendencia
mensual de Licores por sucursal es igual a esa comparativa.

## A10 · Seed de usuarios de prueba

`api/scripts/seed_usuarios.py` (K8) crea o restablece, por email, los cinco
usuarios de prueba con la clave `admin123` y su ubicación, buscada por nombre
en `dw.dim_sucursal`. Es idempotente y se detiene si la bodega no tiene las
ubicaciones.

```bash
docker exec inventaio-api python -m scripts.seed_usuarios
```

Reemplaza a `api/scripts/reset_passwords.py`, que se borró: solo cambiaba las
claves de usuarios creados por el ETL simulado, y el de la bodega real no crea
usuarios. Los documentos de verificación de INV-004 e INV-008 tienen una nota
con el comando nuevo, y las pruebas de integración que se saltan sin usuarios
lo indican.

## A11 · Cierre

- **Matriz** sin endpoints sin destino (A4).
- **Páginas por ruta.** El build avisaba de un archivo de 624 kB con toda la app. Ahora cada página se descarga al entrar a ella (`lazy` en `src/rutas.js`, `Suspense` con `Cargando` en `App.jsx`). El login baja 202 kB (66,5 kB comprimido) y recharts (362 kB) llega solo con Dashboard o Reportes.
- **Estado de Inventario en una línea.** "◆ Inconsistencia" se partía en dos renglones en la columna Estado; el distintivo lleva `whitespace-nowrap`.
- **Detalles de Reportes** encontrados al armar la guía de pantallas: la distribución muestra los porcentajes como el resto de la app ("15.4%", antes "15.4 %"), y la tendencia nombra "Sin sucursal" a la serie `SIN_SUCURSAL` (ventas sin terminal asignada, hasta 2025-09-06), que aparece con los atajos Año y Todo (`nombreSerieVentas` en `etiquetas.js`).
- **Datos de la bodega a la vista en Reportes** (no son errores): no hay ventas en noviembre y diciembre de 2022, y febrero de 2023 solo tiene las del día 1. La guía de pantallas lo advierte.
- **OpenAPI, Postman, scripts y guía de pantallas** al día con las cifras nuevas (ver Pruebas).
- `npm audit` en 0.
- **Ambiente en Linux.** El desarrollo y las pruebas pasaron a Ubuntu en WSL2, con el repositorio en `~/InventaIO` (pasos en `docs/AMBIENTE-DESARROLLO.md`, sección 8). La primera corrida de Vitest en Linux, con la caché vacía como en el CI, destapó una prueba inestable: `CambiarPassword.test.jsx` escribía unas 40 letras con la pausa por defecto de `userEvent` entre teclas y, con la suite en paralelo, pasaba los 5 s de una prueba. Ahora escribe sin pausa (`userEvent.setup({ delay: null })`, los mismos eventos) y tarda entre 1,0 y 1,6 s en frío.

## Decisiones de implementación

Donde la especificación deja margen, se decidió así.

| Tema | Decisión | Por qué |
| --- | --- | --- |
| Firma de `useConsulta` | `fn` recibe `{ signal, timeoutMs }` y lo pasa a `client.js`; el hook cancela con su propio `AbortController`. La `clave` queda solo en `client.js` | El hook ya sabe cuándo cancelar (cambio de filtros o desmontaje); la `clave` sirve para llamadas directas |
| `EstadoConsulta` y `DistintivoBodega` | Componentes compartidos nuevos | Las páginas y las vistas los necesitan: una sola implementación |
| Vista de Bodega | Se piden los KPIs (traen el stock valorizado y los productos en riesgo), pero no la tendencia ni el top de productos | Los KPIs de la Bodega tienen datos útiles; las ventas, no |
| Errores sin respuesta del servidor | `status` 0: sin conexión, timeout (`timeout`) o cancelada (`cancelada`) | Se distinguen sin inventar códigos HTTP |
| Página al cambiar un filtro | Se vuelve a la primera dentro del mismo cambio, no en un efecto aparte | Evita una consulta de más con la página vieja |
| Categorías del filtro | En orden alfabético | La API las ordena por cantidad de productos |
| `frontend/.gitignore` | `dist/` y `coverage/` | Los generan `npm run build` y `npm run test:cov`; la `.gitignore` raíz tiene un cambio de otra sesión |
| Unidad de los productos (J5) | Campo `unidad` ("unidad" o "kg", de `se_vende_por_kilo`) en el histórico, en lugar de `unidad_medida`, y de forma aditiva en todas las respuestas de producto y en la lista de inventario. El detalle la muestra en la descripción ("Código P3937 · Se vende por unidad") | `unidad_medida` es la de la presentación (el arroz \*500 GR tiene `g`; la papa, que se vende por kilo, `unidad`): "556 g" sería falso |
| Consultas de productos | Las tres que arman productos (lista, detalle y productos del proveedor) usan `COLUMNAS_PRODUCTO` y `producto_item` | El campo nuevo se agrega en un solo lugar |
| "Sin ventas" | Solo cuando la cobertura es exactamente 999 | Es el centinela del ETL (317 filas, demanda observada 0); las 76 filas con cobertura mayor que 999 son reales (por ejemplo, 1.972,5 d) |
| Panel de detalle de inventario | Se dibuja con `createPortal` sobre `document.body` | Dentro de la página, el margen de `space-y` dejaba una franja de 16 px sin cubrir arriba del fondo oscuro |
| `getAlertas` y `getVentasTendencia` | Reciben un objeto de filtros: `{ tipo, urgencia, sucursalId, page, pageSize }` y `{ dias, sucursalId, fechaInicio, fechaFin, categoria, agrupacion, porSucursal }`. Antes eran posicionales (`tipo, urgencia, sucursalId` y `dias, sucursalId`) | Con la paginación y la vista de reportes los parámetros crecieron; por posición eran frágiles. Solo las llaman las páginas, que se actualizaron |
| Una sola definición del semáforo | `core/semaforo.py`: `SEMAFORO_CONDICION` arma el `CASE`, el filtro y los conteos de inventario, y `SEMAFORO_EN_RIESGO` el KPI | Antes eran expresiones separadas que podían desalinearse; el KPI de 1.702 era una de ellas |
| Paginación de alertas sin `page` | Responde la lista completa, sin las claves nuevas | Compatible con INV-25 y con quien ya la consuma |
| Atajos de período | Salen de `datos_desde` y `datos_hasta` de la API | Ninguna fecha de la bodega va fija en el código |
| Build de las imágenes con la red lenta | En `api/Dockerfile` y `ml_service/Dockerfile`: pip 26.2.1 con `--resume-retries 10`, `--timeout 120` y `--retries 10`, y una caché de BuildKit para las descargas | Con pip 24.0, una descarga trabada más de 15 s tumbaba el build; ahora se retoma donde iba (en la prueba, `scikit-learn` se retomó dos veces) |
| `.dockerignore` del Core API y de `ml_service` | Excluyen `.venv/`, `**/__pycache__`, `.pytest_cache/`, `.coverage` y `htmlcov/` | El contexto del build no lleva entornos locales ni artefactos de pruebas |
| Paleta de Tailwind 4 (K10) | Se deja la de v4 | Los colores de la marca no cambian, y fijar los de v3 sería un ajuste más que mantener |
| Páginas por ruta | `lazy` en `RUTAS`; `App.test.jsx` importa antes las páginas a las que navega | Sin eso, la primera descarga de recharts con la suite en paralelo pasaba el segundo de espera de `findBy` |

Las pruebas encontraron un error en la primera versión de `useConsulta`, que
quedó corregido. Si los filtros cambiaban antes de que saliera la consulta,
esa consulta, ya cancelada, se enviaba igual con los filtros nuevos. El hook
ahora toma la función del render en que se lanzó.

## Pruebas

Todo lo de esta sección se corrió en Linux (Ubuntu en WSL2, repositorio en
`~/InventaIO`, Docker Desktop), después de migrar el ambiente; antes también
había pasado en la copia de Windows.

**Core API** (dentro del contenedor):

```bash
docker exec inventaio-api python -m pytest
docker exec inventaio-api python -m pytest --cov=consulta --cov=inventario --cov=alertas --cov=reportes \
  --cov=core.ubicaciones --cov=core.productos --cov=core.semaforo --cov=ml --cov=scripts
```

| Archivo | Pruebas | Qué cubre |
| --- | --- | --- |
| `test_ventas_producto.py` | 22 | `armar_ventanas` y el endpoint con una bodega falsa: G1, G3, permisos de INV-25, errores, 503 sin ventas, la unidad de un producto por kilo y Swagger |
| `test_ventas_producto_integracion.py` | 6 | La bodega real: las cifras de P1632, la suma a mano de cada ventana, un producto sin ventas, la unidad en el histórico y en los productos, los permisos y la alineación con `predict` |
| `test_inv26_ajustes_integracion.py` | 22 | La bodega real: conteos del semáforo por ubicación y su cuadre con alertas, el KPI en riesgo igual a bajo + crítico, el filtro por cada estado, el detalle con stock negativo, la unidad en la lista, la paginación de alertas con filtros y permisos, y los cambios de reportes |
| `test_seed_usuarios.py` | 3 | El seed sin base: crea los cinco, es idempotente y restablece la clave, y se detiene sin las ubicaciones |

Resultado: 184 pruebas pasan (132 unitarias y 52 de integración). La cobertura
es de 99 % sobre los módulos del Core API; `consulta/router.py` queda al 100 %
y lo que falta del seed es su bloque `__main__`. `ruff` no tiene observaciones.

**Frontend** (en `frontend/`): `npm run test:cov`. 146 pruebas en 17 archivos, con esta cobertura sobre la base y las cuatro páginas:

| Métrica | Cobertura |
| --- | --- |
| Líneas | 97,93 % |
| Sentencias | 97,31 % |
| Ramas | 95,3 % |
| Funciones | 93,82 % |

Reportes queda en 95,29 % de líneas. `npm run build` pasa sin avisos y
`npm audit` no reporta vulnerabilidades. En Linux, la suite pasó tres veces
seguidas con la caché de Vitest vacía.

**`ml_service`** (fuera de Docker, con `POSTGRES_HOST=localhost`): 189 pruebas
pasan y 1 se salta (`test_paridad_matriz.py`, sin el parquet de los notebooks).

**Verificaciones contra los servicios reales:**

| Verificación | Resultado |
| --- | --- |
| Las funciones de `client.js`, como las llaman las páginas, contra el Core API, con los tres roles y cada opción del selector | 168 llamadas: 167 responden bien y 1 da el 400 esperado (cambio de contraseña con la actual incorrecta, que no cambia nada) |
| Una respuesta de 40 s a través del proxy de Vite 8, con la configuración del proyecto | 200 a los 40,0 s |
| Scripts de Release 1 y de INV-23 (`test_consulta.sh`, `test_inventario.sh`, `test_alertas.sh`, `test_reportes.sh`, `test_recomendaciones.sh`), desde WSL | Los cinco pasan completos |
| Colección de Postman de INV-25 (Newman) | 57 peticiones, 182 verificaciones, 0 fallas |
| Colección de Postman de este fix (Newman) | 31 peticiones de la colección (Newman cuenta 34, con los 3 inicios de sesión de su script), 100 verificaciones, 0 fallas |
| Capturas de todas las pantallas con los tres roles, comparadas con las anteriores a cada cambio de versión | Sin cambios fuera de los tres colores de la paleta y de los ajustes de A7 y A11 |
| Las mismas capturas con Vite corriendo en WSL y Chrome en Windows, comparadas con las tomadas en Windows | Solo cambian "En riesgo" (1.500, K9) y el formato de los porcentajes de Reportes ("15.4%"); el resto es suavizado de letras |
| Casos nuevos de la guía de pantallas (Reportes, filtro de inconsistencia, decimales por kilo, semáforo por sucursal), en Chrome con Playwright | Los textos y cifras de la guía coinciden con lo que muestra la app |
| Imágenes de Docker del Core API y de `ml_service` | Se construyen con la red lenta y sus pruebas pasan dentro |

**Postman.** `api/tests/postman/INV-26-fix.postman_collection.json` tiene 27
casos (CF-01 a CF-27) en cinco carpetas: histórico, permisos, errores, unidad
de venta y adenda (semáforo con inconsistencia, KPI en riesgo, unidad en la
lista, paginación de alertas y reportes). Inicia sesión sola con los usuarios
de prueba, como la de INV-25.

1. En Postman, **Import** → `INV-26-fix.postman_collection.json`.
2. **Run** con el orden por defecto.
3. Esperado: 31 peticiones (los 27 casos, el health y 3 logins), 100 verificaciones, 0 fallas.

Desde la terminal: `npx newman run api/tests/postman/INV-26-fix.postman_collection.json`.

## Criterios de aceptación

| # | Dónde se verifica |
| --- | --- |
| 1–2 | `test_ventas_producto.py`, `test_ventas_producto_integracion.py` |
| 3–5 | `client.test.js` (ApiError, timeout, cancelación, funciones y parámetros) |
| 6 | Respuesta de 40 s por el proxy (arriba) |
| 7 | `useSucursal.test.jsx` |
| 8 | `SucursalSelector.test.jsx` |
| 9 | `rutas.test.jsx`, `App.test.jsx` |
| 10 | `useConsulta.test.jsx`, y en Inventario "una búsqueda nueva nunca queda pisada" |
| 11 | `estados.test.jsx`, `formato.test.js` |
| 12 | Todas las pruebas de páginas usan `renderConUsuario` y `simularApi` |
| 13 | `Dashboard.test.jsx` |
| 14 | `Inventario.test.jsx` |
| 15 | `Alertas.test.jsx` |
| 16 | `DetalleInventario.test.jsx`, `Inventario.test.jsx` |
| 17 | `CambiarPassword.test.jsx`, `App.test.jsx` |
| 18–19 | `frontend/README.md`; `client.test.js` |
| 20 | `npm run test:cov` (arriba) |
| 21 | 184 pruebas del Core API, los cinco scripts, las dos colecciones de Postman, `npm run build` y el recorrido real con los tres roles |
| 22 | `.gitattributes`; las pruebas de `ml_service` dentro de su imagen |
| 23 | `.github/workflows/ci.yml` (A6) |
| 24 | `package.json`, la comparación de capturas (A7) y `npm audit` |
| 25 | `test_lista_de_inventario_trae_la_unidad`, CF-19, `Inventario.test.jsx` |
| 26 | `test_inv26_ajustes_integracion.py` (paginación), CF-20 a CF-23, `Alertas.test.jsx` |
| 27 | `test_inv26_ajustes_integracion.py` (semáforo y KPI en riesgo), CF-17, CF-18 y CF-27, `test_inventario.sh`, `Dashboard.test.jsx`, `Inventario.test.jsx` |
| 28 | `Reportes.test.jsx`, `periodos.test.js`, CF-24 a CF-26 |
| 29 | `test_seed_usuarios.py` |
| 30 | La matriz de `frontend/README.md` |

## Pendientes por reportar

Ninguno. Los cinco que iban a reportarse con el commit quedaron resueltos
dentro del fix:

| # | Qué | Dónde se resolvió |
| --- | --- | --- |
| 1 | Vista de reportes de ventas | A9 |
| 2 | Versiones mayores del frontend y sus 12 vulnerabilidades | A7 |
| 3 | Node 22 en el CI | A6 |
| 4 | Referencia a `INV-26-27-requerimientos.md` | A5 (K1) |
| 5 | `unidad` en la lista de inventario | A8 |

Tampoco quedan preguntas abiertas: la paleta de Tailwind 4 se decidió en K10 y
el KPI "En riesgo" en K9.

## Limitaciones

- **Recorrido manual.** Las pantallas se probaron con Testing Library, contra el Core API real y con capturas automáticas, pero la DoD pide recorrerlas en el navegador con los tres roles. La guía, con los valores esperados de la bodega real, está en [`INV-26-pruebas-pantallas.md`](INV-26-pruebas-pantallas.md).
- **Proveedores simulados.** El detalle de inventario muestra el proveedor de `producto_proveedor`, que es simulado (J3).
- **Contraseñas de prueba.** Las pruebas de integración, los scripts y las colecciones de Postman usan `admin123`; después de probar el cambio de contraseña, el seed las deja como estaban.
- **Navegadores.** Tailwind 4 pide Chrome 111, Safari 16.4 o Firefox 128 o superiores.
- **Sin lint del frontend.** Lo resuelve INV-24.
