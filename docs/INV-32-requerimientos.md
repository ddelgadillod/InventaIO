# INV-32 · Herramientas del agente sobre el Core API · Requerimientos

| Campo | Valor |
| --- | --- |
| Jira | INV-32 «Tool-calling: herramientas de solo lectura sobre el Core API» · 8 SP · Sprint 6 · Release 2 · épica E10 NLP Agent (INV-55) |
| Depende de | INV-30 (servicio, cliente de Ollama, arnés y conjunto v0), INV-25 (permisos por ubicación), INV-21, INV-23 e INV-28 (compras, pronóstico y alertas con IA) |
| Alimenta a | INV-33 (prompts), INV-36 e INV-35 (contrato de eventos v1) e INV-31 (conjunto v1) |
| Rama | `feature/INV-32-herramientas`, desde `develop` (`9ba2051`) |
| Modelo | `qwen3:8b` sin razonamiento (decisión de INV-30) |

Revisión del 18 de octubre de 2026. Se contrastó con `develop` y con el Core API real del stack local, usando los usuarios de prueba de los tres roles (`api/scripts/seed_usuarios.py`). Todas las mediciones fueron de solo lectura.

## 1. Historia de Jira

> Como usuario del sistema, quiero que el agente consulte los datos reales con herramientas de solo lectura sobre el Core API, para que sus respuestas salgan de las mismas reglas, permisos y cifras que ya usa la aplicación y no de lo que el modelo cree recordar.

La ficha trae 13 criterios: 11 (M), 1 (S) y 1 (C). También trae estas decisiones:
- N1: solo lectura sobre el Core API, sin SQL libre.
- D12: `ml_service` es interno.
- D13: el permiso es el del usuario.
- N5: bucle propio sobre Ollama.
- D22: el presupuesto de tokens es requisito de diseño.

Este documento las contrasta con el repositorio y con los datos.

## 2. Contraste con el repositorio y con los datos reales

| # | Hallazgo | Consecuencia |
| --- | --- | --- |
| C1 | El agente ya trae la base:<ul><li>`ClienteLLM.chat` con herramientas;</li><li>la conversión de argumentos que llegan como texto JSON (`_argumentos`, criterio 13);</li><li>el filtro de `<think>` (`FiltroRazonamiento`);</li><li>en el arnés (`evaluacion/arnes.py`), el bucle de 3 rondas más una última sin herramientas.</li></ul> | El bucle pasa del arnés a `nlp_agent/agente/` y el arnés lo usa: lo que se mide es lo que corre (T11) |
| C2 | El catálogo v0 (`evaluacion/catalogo_v0.py`: 9 herramientas, ~1.050 tokens) no llama al Core API: el arnés responde con resultados sintéticos | Lo reemplaza el catálogo v1 real (sección 4). El v0 queda para reproducir el spike |
| C3 | `GET /api/consulta/inventario/detalle` devuelve un historial de **1 día**, porque la bodega tiene una sola foto de inventario (31-dic-2025) | T1: `detalle_inventario` sale del catálogo. Las 3 preguntas del v0 que la aceptaban (v0-04, 04b y 04c) también aceptan `historial_ventas` |
| C4 | `busqueda` en productos busca por subcadena (nombre, familia o código) y ordena alfabéticamente:<ul><li>«arroz» da 71 productos;</li><li>«leche» da 110, y el primero es «ARROZ CON LECHE ROA…»;</li><li>«aceite girasol» da 4 atunes;</li><li>«P1632» da 1</li></ul> | T2: la herramienta resuelve el producto dando prioridad al código y al nombre exactos. Pedir aclaración entre 110 candidatos no sirve |
| C5 | Hay 4 sucursales fijas: 1 PRINCIPAL, 2 LA 21, 3 GLORIETA y 5 BODEGA_CENTRAL. Unos endpoints las piden por id (`sucursal_id`; `id_sucursal` en el detalle) y otros por nombre (`sucursal` en las recomendaciones; `sucursal_id` con el nombre en el pronóstico) | T2: el modelo da el nombre (enum) y la herramienta lo traduce con los ids que lee de `/api/consulta/sucursales` |
| C6 | Las alertas de reglas (`/api/alertas`) y las de IA (`/api/alertas/ml`) son endpoints distintos. En el segundo, `origen` vale `ml` o `ambos` (la alerta la ven el modelo y las reglas), no `reglas` o `ia`. `/api/alertas/resumen` cuenta solo las de reglas (4.452); las de IA traen su propio `resumen` (1.587) | T3: `listar_alertas(origen)` elige el endpoint; sin origen, usa el de reglas |
| C7 | `/api/alertas/ml` tarda **39,7 s** en frío y 116 ms con la caché caliente. La caché del Core API dura 6 h (`ML_CACHE_TTL_SEGUNDOS = 21600`) | `lenta: true` en el evento `tool` (T7). El tiempo por llamada tiene que cubrir el frío (T10) |
| C8 | Sin paginar, `/api/alertas` devuelve las 4.452 alertas: 1,4 MB, ~350.000 tokens. `/api/ml/recomendaciones/compras` no pagina: 736 KB para el gerente (1.340 líneas) y 129 KB con GLORIETA y urgencia urgente | Criterio 4: las herramientas siempre paginan (`page_size = 10`) o recortan, y el total sale de los contadores (`total`, `resumen`) |
| C9 | `/api/ml/predict` para P1632 en GLORIETA da q50 **3.871** y `limite_superior` **3.094**, menor que la mediana. En perecederos, `alpha_negocio` es 0,167 y la interpretación dice «no usar como cota de reposición» | T5: la tarjeta lleva q50 e `interpretacion`, sin el intervalo |
| C10 | Ventas por producto (`/productos/{id}/ventas`): gerente y admin_bodega reciben 422 si no envían `sucursal_id`; `admin_sucursal` usa la suya. El pronóstico sin sucursal da 422 a todos | T4: para un rol global sin sucursal, una llamada por sucursal física. T9 propone la misma regla para el pronóstico, que es lo que pide la v0-09b |
| C11 | El Core API devuelve los errores como `{"detail": "<texto>"}`, en español y listos para el modelo: «Solo puede consultar su sucursal (PRINCIPAL)», «… la Bodega Central, solo en el stock», «Token inválido o expirado», «No hay inventario para producto … en sucursal 3». La validación de FastAPI, como el 422 del pronóstico, trae `detail` como lista | Criterio 5: el resultado de error lleva `status` y `mensaje`. `mensaje` es el `detail`, o los `msg` unidos si es una lista |
| C12 | Un `semaforo` inválido en `/api/consulta/inventario` no da 422: responde 200 con las 11.101 filas sin filtrar | El agente valida los enums antes de llamar. Es un error del Core API, anotado para un `fix/` aparte, fuera de INV-32 |
| C13 | Todos los endpoints informan la misma fecha de datos, `2025-12-31` (`fecha_inventario`, `fecha_pronostico`, `fecha_fin`, `fecha_features`). `meta.fecha_datos` sale siempre en `null`, porque `meta` va antes de cualquier herramienta | T6 |
| C14 | El agente limita la petición a 12 mensajes (`MAX_MENSAJES`). INV-36 aprobó 13 (X2), y su prueba P-06 espera que el agente reciba los 13 | `MAX_MENSAJES = 13` (contrato v1) |
| C15 | El contrato v0 promete el error `herramienta_error`, que el código nunca emite, y omite `modelo_no_descargado`, `respuesta_invalida` y `solicitud_invalida`, que sí emite | El contrato v1 usa la lista real |
| C16 | Las compras filtradas por sucursal física traen en `cantidad` el total de **toda** la compra (R1 de INV-21) y en `necesidad_sucursal` la parte de esa sucursal. `destino` es `BODEGA_CENTRAL` en 891 de las 1.340 líneas. `filtros_aplicados.sucursal_por_rol` dice si el filtro lo puso el rol | La fila muestra el destino, la cantidad de la compra y, con sucursal, la necesidad de esa sucursal (sección 4) |
| C17 | El prompt v0 del servicio dice «Todavía no tienes acceso a los datos del inventario» | INV-32 necesita un prompt con herramientas (T15); los prompts por rol siguen en INV-33 |

## 3. Decisiones

Aprobadas por el usuario el 18-oct (formulario):

| # | Decisión | Elegida |
| --- | --- | --- |
| T1 | Tamaño del catálogo | **8 herramientas**, sin `detalle_inventario` (C3) |
| T2 | Nombres de productos y sucursales | **Se resuelven dentro de la herramienta**, en este orden: código exacto, nombre exacto y subcadena.<ul><li>Con 1 coincidencia, sigue.</li><li>Con varias, devuelve `ambiguo` con el total y hasta 5 candidatos, para que el modelo pregunte.</li><li>Con 0, devuelve `no_encontrado`.</li></ul>Las sucursales se traducen con los ids que se leen del Core API |
| T3 | Alertas sin origen | **Solo las de reglas** (`/api/alertas`). Las de IA, solo cuando la pregunta las pide: riesgo, sobrestock, «según la IA» |
| T4 | Ventas sin sucursal, para un rol global | **Las 3 sucursales físicas**: una llamada y una fila por sucursal |
| T5 | Forma de `data` | **El texto tal como lo leyó el modelo**, con cantidades por `texto_cantidad` y semáforo y urgencia como código. Puede ser tabla o tarjeta; el pronóstico es una tarjeta con q50 e interpretación, sin el intervalo |
| T6 | Fecha del dato | **Sale de `meta`**. Va en cada `data.fecha_dato` y en `done.fechas_datos` |
| T7 | Evento `tool` | **`id`, `etiqueta`, `lenta` y `codigo`**, además de `nombre`, `estado` y `ms` |
| T8 | Entrega del contrato | **Antes del código**, en un merge de solo documentación: este documento y la §4.3 v1 de `docs/INV-30-requerimientos.md` |

Propuestas técnicas, que siguen el molde existente (se cambian si el usuario lo pide):

| # | Propuesta |
| --- | --- |
| T9 | **Pronóstico sin sucursal** para un rol global: la misma regla de T4. Devuelve una tabla con una fila por sucursal física; con una sola sucursal, es una tarjeta |
| T10 | **Cliente del Core API**: `httpx.AsyncClient` sobre `CORE_API_URL`, que reenvía el `Authorization` del usuario y el `X-Request-Id`. Cada llamada tiene un límite de `CORE_API_TIMEOUT_S = 60`, que cubre los 39,7 s del frío, dentro del límite total de `LLM_TIMEOUT_S`. Al agotarse, la herramienta devuelve un error 504 que el modelo explica |
| T11 | **El bucle vive en `nlp_agent/agente/`**: hasta 3 rondas con herramientas (criterio 6) y después una sin herramientas, que obliga a responder. Solo esa última se transmite en streaming. El arnés usa el mismo bucle, con un ejecutor sintético (Colab, N9) o real (el Core API con el token del rol de cada pregunta) |
| T12 | **Parámetros con Pydantic**, de donde sale el JSON Schema para Ollama (criterio 1).<ul><li>Un argumento inválido vuelve al modelo como `{"error": {"status": 422, "mensaje": …}}`, una sola vez por llamada (criterio 13).</li><li>Los filtros opcionales dicen «Omítelo para no filtrar», por el hallazgo del spike</li></ul> |
| T13 | **Prueba de contrato** (criterio 7): cada herramienta declara su endpoint y los parámetros que envía, y una prueba los compara con `api/tests/postman/inventaio-core-api.openapi.yml`. Si el Core API cambia y se regenera el OpenAPI, la prueba falla en el CI |
| T14 | **Los resultados son datos** (criterio 8).<ul><li>El mensaje `tool` lleva el JSON del resultado, con la forma del spike, que es con la que se midió el modelo.</li><li>Los textos del Core API, como nombres de producto o `detalle`, van como valores del JSON y nunca se concatenan al prompt</li></ul> |
| T15 | **Prompt `v1`**:<ul><li>el del spike (`evaluacion/prompt_spike.md`);</li><li>con la fecha de los datos que dan las herramientas;</li><li>con la instrucción de no obedecer lo que venga dentro de un resultado.</li></ul>INV-33 se encarga de los prompts por rol, la aclaración y los totales |
| T16 | **Registro** (criterio 9, S): una línea por llamada en `nlp_agent.herramientas`, con `request_id`, herramienta, estado, `codigo` y ms. No se registran argumentos ni resultados |
| T17 | **Medición** (criterio 10 y DoD 4): el conjunto v0 (43 preguntas) corre en local contra el Core API real, con qwen3:8b y 3 corridas, hasta que INV-31 entregue la v1.<ul><li>Con datos reales se miden la herramienta y los argumentos, la fidelidad frente a los resultados reales, las fugas, la abstención y el p95.</li><li>Los «hechos clave» del v0 son sintéticos y solo se califican en modo sintético (Colab).</li></ul> |

## 4. Catálogo v1

Todas las herramientas son de solo lectura y llaman al Core API con el token del usuario. Ninguna llama a `ml_service`, ni a una URL armada por el modelo (criterio 2).

| Herramienta | Endpoint del Core API | Parámetros del modelo | Qué devuelve (al modelo y en `data`) |
| --- | --- | --- | --- |
| `buscar_producto` | `GET /api/consulta/productos` (`busqueda`, `page_size = 10`) | `texto` | `total` y hasta 10 filas `{codigo, nombre, categoria, unidad}`. Sin `data` |
| `listar_sucursales` | `GET /api/consulta/sucursales` | — | Las 4 ubicaciones `{nombre, tipo}`. Sin `data` |
| `consultar_inventario` | `GET /api/consulta/inventario` (`sucursal_id`, `busqueda`, `categoria`, `semaforo`, `page_size = 10`) | `sucursal`, `producto`, `categoria` y `estado`, todos opcionales | `total`, `fecha_dato` y hasta 10 filas `{producto, sucursal, stock, minimo, cobertura, semaforo}`. Tabla |
| `listar_alertas` | Reglas: `GET /api/alertas`. IA: `GET /api/alertas/ml`. Las dos con `sucursal_id`, `tipo`, `urgencia`, `page = 1` y `page_size = 10` | `origen` (`reglas` o `ia`), `sucursal`, `tipo` y `urgencia`, todos opcionales | `total`, `fecha_dato` y hasta 10 filas `{producto, sucursal, tipo, urgencia, detalle}`. Tabla. `lenta` con IA |
| `resumen_alertas` | `GET /api/alertas/resumen` (`sucursal_id`) | `sucursal`, opcional | Una fila por sucursal `{sucursal, critica, alta, media, total}` y el global. Tabla |
| `pronosticar_demanda` | `POST /api/ml/predict` (`producto_id`, `sucursal_id` con el nombre, `horizonte = 15`) | `producto`; `sucursal` (PRINCIPAL, LA 21 o GLORIETA) | `{producto, sucursal, demanda, horizonte, interpretacion}`, con la demanda (q50) por `texto_cantidad`. Tarjeta, o tabla con T9 |
| `historial_ventas` | `GET /api/consulta/productos/{id}/ventas` (`sucursal_id`, `ventanas`) | `producto`; `sucursal`, opcional (T4) | Ventanas de 15 días hábiles `{sucursal, desde, hasta, ventas}`:<ul><li>con una sucursal, las 8 últimas (~5,5 meses);</li><li>con las 3, las 3 últimas de cada una (9 filas).</li></ul>Tabla |
| `recomendar_compras` | `GET /api/ml/recomendaciones/compras` (`sucursal` con el nombre, `categoria`, `urgencia`, `incluir_detalle = false`) | `sucursal`, `categoria` y `urgencia`, todos opcionales | Un resumen (líneas, productos y cantidad por unidad) y hasta 10 líneas `{producto, destino, cantidad, urgencia, fecha_pedido}`, ordenadas por urgencia y por días hasta agotarse. Con sucursal, cada línea suma `necesidad_sucursal` (C16). Tabla. `lenta` |

Los filtros opcionales llevan «Omítelo para no filtrar» (T12). Las enumeraciones son las del Core API:
- `estado`: `ok`, `bajo`, `critico` e `inconsistencia`;
- tipos de alerta de reglas: `stock_critico`, `stock_bajo`, `sin_movimiento`, `rotacion_baja` e `inconsistencia_inventario`;
- tipos de alerta de IA: `riesgo_desabastecimiento_ml` y `sobrestock_previsto_ml`;
- urgencia de alertas: `critica`, `alta` y `media`;
- urgencia de compras: `urgente`, `alta` y `normal`.

El presupuesto de tokens del catálogo se mide al implementarlo (criterio 12); el v0 medía ~1.050 tokens con 9 herramientas.

Lo que el agente envía y recibe por SSE está en la §4.3 de `docs/INV-30-requerimientos.md`, contrato v1. Ahí están `tool`, `data`, `done` y los códigos de `error`.

## 5. Criterios de aceptación

| CA | Cómo se cumple |
| --- | --- |
| 1 (M) | 8 herramientas (T1), con descripción en español y parámetros en Pydantic (T12) |
| 2 (M) | Solo `CORE_API_URL` y rutas fijas por herramienta, con el `Authorization` del usuario (T10). Una prueba verifica que ninguna herramienta llama a `ml_service` |
| 3 (M) | Resolución dentro de la herramienta, con `ambiguo` y hasta 5 candidatos (T2) |
| 4 (M) | Hasta 10 filas, `total` y `fecha_dato`, con las cantidades por `texto_cantidad` (sección 4, C8) |
| 5 (M) | Los 401, 403, 404, 422 y 5xx, y el tiempo agotado (504), se convierten en un resultado `{"error": {status, mensaje}}` (C11). Una prueba adversarial verifica que, ante un 403, el modelo no inventa |
| 6 (M) | 3 rondas como máximo, más una sin herramientas, dentro de `LLM_TIMEOUT_S` (T11) |
| 7 (M) | Prueba de contrato con el OpenAPI versionado (T13) |
| 8 (M) | Resultados como JSON en el mensaje `tool` y la instrucción en el prompt v1 (T14, T15). Pruebas con instrucciones dentro de un nombre de producto |
| 9 (S) | Registro por llamada (T16) |
| 10 (M) | El v0 contra el Core API real, con 3 corridas y pass^3, y cero fugas (T17) |
| 11 (C) | No se entrega: el ciclo de herramientas va sin streaming (ficha) |
| 12 (M) | Tokens por ronda medidos y en `done.tokens_prompt` (ronda más grande), con `ms_modelo`, `ms_herramientas` y `rondas`. El presupuesto se fija con la medición del catálogo v1 |
| 13 (M) | `_argumentos` ya convierte el texto JSON. El argumento inválido vuelve al modelo una sola vez (T12). El `<think>` se filtra con `FiltroRazonamiento` |

## 6. Ruta de implementación

**Merge 1, solo documentación (T8, 18-oct):**
- este documento;
- la §4.3 v1 de `docs/INV-30-requerimientos.md`.

Con eso, el carril C programa INV-36 e INV-35 contra el contrato v1.

**Merge 2, el código:**
1. `nlp_agent/herramientas/`:
   - el cliente del Core API (T10);
   - la resolución de nombres (T2);
   - las 8 herramientas con sus esquemas, sus resultados y su `data` (sección 4).
2. `nlp_agent/agente/`: el bucle (T11), los eventos `tool` y `data` del contrato v1, `fechas_datos` en `done`, `MAX_MENSAJES = 13` y el prompt v1 (T15).
3. Pruebas:
   - cada herramienta con un Core API simulado (`MockTransport`);
   - el contrato con el OpenAPI (T13);
   - casos adversariales: un `admin_sucursal` que pide otra sucursal, un resultado con instrucciones dentro y un bucle de herramientas;
   - argumentos como texto JSON.
4. El arnés con el ejecutor real (T11) y la corrida del v0 contra el Core API (T17).
5. `docs/INV-32-herramientas-agente.md`, con la medición, la decisión N5 registrada y los (S) y (C) no entregados.

La regla de corte del 21-oct (documento de Sprint 6, §5) pide una pregunta que pase por una herramienta y vuelva en streaming con los 3 roles. Para cumplirla hacen falta el merge 2 y también INV-36.

## 7. Definition of Done

La de la ficha, con sus 8 puntos. Lo que no se puede verificar en el CI (el modelo real y el Core API con datos) se corre en local y queda en `docs/INV-32-herramientas-agente.md`.

## 8. Fuera de alcance y riesgos

**Fuera de alcance:**
- herramientas de escritura o de aprobación;
- SQL libre;
- streaming del ciclo de herramientas (CA 11);
- historial persistente;
- prompts por rol (INV-33);
- el `: ping` de X5-c, que es del contrato pero se implementa fuera de esta historia;
- el arreglo del filtro `semaforo` del Core API (C12).

**Riesgos:**

| Riesgo | Mitigación |
| --- | --- |
| La primera consulta de alertas con IA o de compras tarda ~40 s en frío (C7) y empuja el p95 | `lenta` en el evento `tool`, para que INV-35 lo explique. T3 deja la IA solo cuando se pide. Calentar la caché al arrancar el Core API queda propuesto para INV-34 |
| La búsqueda alfabética devuelve primero coincidencias poco útiles («arroz con leche» para «leche») | Prioridad al código y al nombre exactos, y `ambiguo` con el total (T2) |
| El modelo trata la fecha de hoy (2026) como la de los datos (2025-12-31) | `fecha_dato` en cada resultado y en el prompt v1 (T15). INV-33 lo refuerza |
| El v0 tiene resultados sintéticos y la medición real no los usa | T17: los hechos clave solo se califican en modo sintético; con datos reales, herramienta, argumentos, fidelidad y fugas |
| El catálogo y el OpenAPI se separan | Prueba de contrato en el CI (T13) |
