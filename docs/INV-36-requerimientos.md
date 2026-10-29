# INV-36 · API de chat en el Core API (SSE) y Nginx para streaming · Requerimientos

| Campo | Valor |
| --- | --- |
| Jira | INV-36 «INV-036: API de chat en el Core API (SSE) y Nginx para streaming» · 5 SP · Sprint 6 · Release 2 · épica E12 Chat PWA (INV-57) · prioridad Highest |
| Depende de | INV-30 (agente `nlp-agent:8002`) e INV-32 (contrato v1 de `POST /chat`, sección 4.3 de `docs/INV-30-requerimientos.md`), INV-25 (contrato de errores y permisos del Core API), INV-24 (CI e imágenes) |
| Alimenta a | INV-35 (panel de chat) e INV-34 (Nginx con TLS y dominio) |
| Rama | `feature/INV-36-api-chat`, al día con `develop` (`0c86bde`) el 20-oct, en `~/InventaIO`. El worktree `~/InventaIO-wt/INV-36` del carril C queda sin uso |
| Agente | El real está en `develop`: INV-30 desde el 17-oct y con herramientas (INV-32) desde el 19-oct. Las pruebas usan uno simulado |

Revisión del 15 y el 16 de octubre de 2026 contra `develop` y un Nginx 1.30 real (la imagen base de `frontend/Dockerfile`). La escribió el carril C.

> **Actualizado el 20 de octubre** por la sesión de INV-32, que toma la historia:
> - el contrato del agente es el **v1**, fijado por INV-32;
> - las decisiones X1–X8 son las que tomó el usuario el **18-oct** (sección 3);
> - se agregan los hallazgos C17 a C19;
> - el ejemplo de la §4.1 usa `agente` y no `asistente` como rol;
> - el ping X5-c entra en esta historia.

## 1. Historia de Jira

> Como usuario autenticado, quiero un endpoint de chat que me responda en streaming pasando por la misma puerta y los mismos permisos que el resto de la aplicación, para que el agente nunca sea una vía de acceso paralela a los datos.

La ficha trae 8 criterios (M), uno (S) y uno (C), y tres decisiones:

- **N3:** navegador → Nginx → Core API `/api/chat` → agente interno → herramientas con el JWT del usuario.
- **D12:** una sola puerta. Reemplaza el criterio original, que pasaba de Nginx directo al agente en el 8002.
- **N4:** SSE sobre `fetch`, no WebSocket.

Este documento contrasta la ficha con el repositorio y fija lo que deja abierto: el cuerpo de la petición, los límites, qué pasa cuando se agota el tiempo después de empezar a responder y los ajustes al contrato del agente.

## 2. Contraste con lo ya construido

| # | Hallazgo | Consecuencia |
| --- | --- | --- |
| C1 | No hay nada de chat en `api/`. El agente está en `develop` con el contrato **v1** (§4.3 de `docs/INV-30-requerimientos.md`, INV-32): `tool` con `id`, `etiqueta`, `lenta` y `codigo`; `data` con `forma` y columnas con tipo; `done` con tiempos y `fechas_datos`; sin `fecha_datos` en `meta` | Se construye contra el v1 con un agente simulado y se verifica con el real (P-18) |
| C2 | La ficha dice que Nginx «no está preparado para streaming». Medido el 15-oct con el `frontend/nginx.conf` actual: un SSE de 5 eventos, uno por segundo, pasa por `/api/` sin acumularse (llegadas a 0,07, 1,03, 2,03, 3,03 y 4,10 s), con `X-Accel-Buffering` o sin él | Hoy el buffer de Nginx no rompe el streaming. La ubicación `/api/chat/` se hace igual (criterio 5): deja explícito lo que hoy funciona por omisión |
| C3 | Con `text/event-stream` en `gzip_types`, el primer byte llega a los **5,04 s**: todo junto al final. Con `X-Accel-Buffering: no` o `proxy_buffering off`, el primer byte llega a los 0,004 s, pero comprimido | Lo que de verdad rompe el streaming es la compresión. `/api/chat/` lleva `gzip off`. El control del script que debe fallar es el de gzip, no el del buffer |
| C4 | El Core API corre en un solo proceso de uvicorn: ni el Dockerfile ni el compose usan `--workers`. Redis está en el compose, pero el Core API no lo usa (el README lo reserva «para cuando haya más de un servidor») | Los contadores de concurrencia caben en memoria. Si INV-34 usa varios procesos, pasan a Redis |
| C5 | `get_db` es una dependencia con `yield`. En FastAPI 0.142, por defecto, cierra la sesión al terminar la respuesta | Un flujo de 120 s retendría una conexión del pool (5 + 10) con una transacción abierta. La ruta de chat resuelve al usuario con `Depends(get_db, scope="function")` |
| C6 | Sin token, la respuesta es 403 (`BearerSinToken403`, el contrato de INV-25). Con un token inválido, vencido o de refresco, 401 | El 401 del criterio 8, con el que el cliente renueva el token, ya existe. Sin token sigue siendo 403, como en el resto del Core API |
| C7 | El token de acceso dura 30 min. `client.js` lo renueva ante un 401 y reintenta | Si el token vence en medio de un flujo, el agente recibe 401 en sus herramientas y el usuario ve un `herramienta_error` incomprensible (X6) |
| C8 | El Core API no tiene registros propios: solo el access log de uvicorn (método, ruta y código) | Se crea el registro del chat con `request_id` y sin el texto de los mensajes (Ley 1581) |
| C9 | Starlette 1.7: `StreamingResponse` escucha `http.disconnect` y cancela el generador | Cancelar aguas arriba es cerrar el stream de httpx dentro del generador. El agente (INV-30), a su vez, debe cancelar la llamada a Ollama |
| C10 | La ficha pide 120 s de tiempo máximo y 504. Un código HTTP solo se puede enviar antes del primer byte de la respuesta | Un 504 solo es posible antes de empezar. Si el tiempo se agota después, se envía un evento `error` (X4) |
| C11 | INV-30 fija `LLM_TIMEOUT_S = 120`, el mismo valor que el Core API | X5-d (110 s) no se aprobó: los dos cortan a los 120 s y, en el límite, el `tiempo_agotado` puede llegar de cualquiera de los dos. Es un comportamiento conocido, anotado en la §4.3 |
| C12 | `/ready` del agente ya responde `{status: "listo", modelo, version_ollama, version}`, y en 503 `{status: "no_listo", modelo, motivo}` (medido el 20-oct; X5-a quedó hecho en INV-30) | `/api/chat/health` toma de ahí el modelo y el motivo |
| C13 | El compose publica 8000, 8001, 5432, 6379, 5050 y, con el perfil `web`, 8080. Nadie publica el 8002 | Criterio 6: una prueba lee `docker-compose*.yml` y falla si algún servicio publica el 8002 o si `nlp-agent` tiene `ports:` |
| C14 | El CI corre `pytest -m "not integracion"`. El DoD pide además las pruebas de la marca `llm` en local | Se agrega la marca `llm` en `api/pytest.ini` y el CI corre `-m "not integracion and not llm"` |
| C15 | `proxy_read_timeout` mide el silencio entre dos lecturas, no la duración total. Una herramienta lenta o la carga del modelo (~20 s en frío) dejan el flujo callado | Con un `: ping` cada 15 s el flujo no se queda callado; el tiempo total lo controla el Core API. Hacia INV-34: un balanceador de AWS corta a los 60 s de silencio |
| C16 | No hacen falta dependencias nuevas: `httpx` 0.28 (cliente asíncrono con streaming) y Starlette ya están, y `sse-starlette` no se necesita | Sin cambios en `requirements.txt` ni en la imagen |
| C17 | El agente acepta `rol` en `usuario` o `agente` (`nlp_agent/chat/schemas.py`) y, como el Core API, a lo sumo 13 mensajes de 2.000 caracteres (INV-32). El borrador del 16-oct ponía `asistente` en el ejemplo | El Core API usa los mismos roles: con `asistente`, el segundo turno de cualquier conversación habría dado 422 en el agente |
| C18 | El agente ya hace X5-e (cierra el stream de Ollama al perder la conexión) y X5-f (`meta` antes de llamar al Core API o a Ollama). No envía el `: ping` | El ping (X5-c) se agrega en el agente dentro de esta historia: es parte del contrato que INV-36 necesita |
| C19 | El agente responde 401 sin `Authorization` y 422 a un cuerpo inválido, antes de abrir el flujo | No debería pasar si el Core API valida igual (X2). Si llega, el Core API lo trata como «el agente respondió N» (502) |

## 3. Decisiones

**Decididas por el usuario el 18-oct** (formulario):
- X1, X2, X4, X6, X7 y X8: **como se propusieron**;
- X3: **429 inmediato con `Retry-After`**, sin evento de cola;
- X5: **solo (c)**, el `: ping` cada 15 s.

  Las demás partes de X5 quedan así:
  - (a), (e) y (f) ya estaban en el agente;
  - **(b) no se aprobó.** Si el agente corta sin `done` ni `error`, el Core API cierra el flujo sin agregar eventos; INV-35 lo trata como un corte, porque falta el `done`;
  - **(d) no se aprobó.** Los dos cortan a los 120 s (C11).

La tabla conserva la propuesta y la alternativa, para el registro:

| # | Tema | Propuesta (la elegida, salvo en X5) | Alternativa |
| --- | --- | --- | --- |
| X1 | Cuerpo de la petición | El cliente envía el historial, `{"mensajes": [{"rol", "texto"}]}`, con el mismo formato del agente, porque no hay persistencia hasta INV-37 | Solo el último mensaje: no hay conversación de varios turnos |
| X2 | Límites (422) | El Core API solo valida; no recorta. El último mensaje debe ser del usuario y tener entre 1 y 2.000 caracteres, y el cuerpo, a lo sumo 13 mensajes (6 turnos y la pregunta) y 16.000 caracteres; si no, 422. El cliente envía los últimos 6 turnos (INV-35) y el agente recorta por presupuesto de tokens (INV-33, criterio 5) | El Core API recorta el historial en vez de responder 422 |
| X3 | Concurrencia | 429 inmediato con `Retry-After: 10`: un flujo por usuario y 1 en total por defecto (`CHAT_MAX_FLUJOS`; 8 GB de VRAM y `OLLAMA_NUM_PARALLEL=1`). Contadores en memoria (C4). El estado «en cola» del criterio 5 de INV-35 lo da el cliente: ante un 429 global, muestra «en cola» y reintenta solo después de `Retry-After` | Cola: 200 con eventos `cola` (posición) y después el flujo normal. Excluye el 429 global y necesita pings mientras espera (hasta 120 s por turno) |
| X4 | Tiempos y errores | Antes de responder, el Core API espera el primer evento del agente, hasta 15 s. Así, los fallos de conexión se informan con su código HTTP (503, 502 o 504). Después, un fallo es un evento `error` y se cierra el flujo. Tiempo total: 120 s | Responder 200 de inmediato y llevar todos los errores como eventos |
| X5 | Ajustes al contrato v0 (la sesión de INV-30 los acepta si el usuario los aprueba) | **(a)** `/ready` con `{status, modelo, version}` y, en 503, `motivo`. **(b)** Código `agente_interrumpido` del Core API, para cuando el agente corta sin `done` ni `error`. **(c)** Comentario SSE `: ping` cada 15 s (C15). **(d)** `LLM_TIMEOUT_S = 110` en el agente (C11). **(e)** El agente cancela la llamada a Ollama si pierde la conexión (C9). **(f)** El agente envía `meta` en cuanto recibe la petición, antes de llamar a Ollama: la carga del modelo en frío (~20 s) no puede ir antes del primer evento | Cualquier subconjunto |
| X6 | Token por vencer | Si al token le quedan menos de 120 s, el Core API responde 401 y el cliente lo renueva antes de empezar (C7) | Aceptarlo y que falle a mitad de camino |
| X7 | `GET /api/chat/health` | Para los 3 roles. Responde 200 con `{estado: "listo", modelo, version, flujos_activos, limite}` y 503 con `motivo` si el agente o el modelo no están listos | Solo el gerente, o siempre 200 con el estado en el cuerpo |
| X8 | Bloque de Nginx | Un archivo `frontend/nginx/chat-sse.conf` con los tiempos, el destino y el buffer. `nginx.conf` lo incluye y INV-34 lo reutiliza en el servidor con TLS | Bloque dentro de `nginx.conf`, que INV-34 copia |

**Propuestas técnicas.** Siguen el molde existente y se cambian si el usuario lo pide:

| # | Propuesta |
| --- | --- |
| X9 | **`request_id`:** según la sección 8 del documento del Sprint 6 («`X-Request-Id` de Nginx al agente y a las herramientas»), nace en Nginx (`proxy_set_header X-Request-Id $request_id`, que pisa el que mande el navegador). El Core API lo acepta solo si son 32 caracteres hexadecimales y, si no, genera uno; lo envía al agente en `X-Request-Id` y lo devuelve en el mismo encabezado. Cada flujo deja **una** línea en el registro `inventaio.chat`, con `request_id`, `usuario_id`, `rol`, `resultado` (`ok`, `error`, `cancelado`, `rechazado`, `interrumpido`), `codigo`, `ms`, `eventos`, `tokens_prompt`, `tokens_respuesta` y, del `done` v1, `ms_modelo`, `ms_herramientas` y `rondas`. **Nunca el texto** |
| X10 | **Reenvío por evento:** el Core API separa los eventos del agente por la línea vacía y reenvía los bytes de cada uno sin cambios. Los lee solo para saber cuál fue el último y tomar las cifras de `done` |
| X11 | **Cliente del agente:** `api/chat/cliente.py`, con `httpx.AsyncClient`, siguiendo el molde de `api/ml/cliente.py`. Configuración en `core/config.py` (sección 4.4) |
| X12 | **Sesión de la base:** `scope="function"` en la ruta de chat (C5) |
| X13 | **Compose:** `NLP_AGENT_URL` en el servicio `api`, sin `depends_on` hacia el agente, para que un chat caído no impida que arranque la API. `docker-compose.verify.yml` no cambia |
| X14 | **Pruebas:** un agente simulado (Starlette servido por uvicorn en un hilo y un puerto libre) para la desconexión real; el resto con `TestClient`. La marca `llm`, para el flujo con el agente real (C14) |
| X15 | **OpenAPI:** la respuesta 200 se documenta como `text/event-stream`, con un esquema Pydantic por evento en `components`. Ejemplo del cuerpo en `exportar_openapi.py` |
| X16 | **WebSocket**, el criterio (C): no se entrega, porque N4 lo descarta. Queda anotado |

## 4. Entradas, salidas e interfaz

### 4.1 `POST /api/chat/message`

**Entrada.** `Authorization: Bearer <access token>` de cualquiera de los 3 roles (`gerente`, `admin_bodega` y `admin_sucursal`). Los permisos por ubicación los aplica el Core API cuando el agente llama a sus herramientas con ese mismo token (INV-25 e INV-32).

```json
{ "mensajes": [
    { "rol": "usuario",   "texto": "¿Cuánto arroz hay en GLORIETA?" },
    { "rol": "agente",    "texto": "En GLORIETA hay 312 unidades de ARROZ ZULIA *500 GR…" },
    { "rol": "usuario",   "texto": "¿Y en LA 21?" }
] }
```

**Salida.** `200`, con estos encabezados:

- `Content-Type: text/event-stream; charset=utf-8`
- `Cache-Control: no-cache`
- `X-Accel-Buffering: no`
- `X-Request-Id: <uuid>`

Cada evento sigue el formato `event: <nombre>\ndata: <json>\n\n`. Los del agente (contrato **v1**, §4.3 de `docs/INV-30-requerimientos.md`) pasan sin cambios:

| Evento | Datos | Origen |
| --- | --- | --- |
| `meta` | `{request_id, modelo, version_prompt}` | Agente, siempre primero e inmediato |
| `tool` | Al empezar, `{id, nombre, estado: "inicio", etiqueta, lenta}`; al terminar, `{id, nombre, estado: "ok" \| "error", ms, codigo}` | Agente |
| `data` | `{id, herramienta, forma, titulo, columnas, filas, total, mostrando, fecha_dato}` | Agente |
| `token` | `{texto}` | Agente |
| `done` | `{tokens_prompt, tokens_respuesta, ms_total, ms_modelo, ms_herramientas, rondas, fechas_datos}` | Agente, último si todo salió bien |
| `error` | `{codigo, mensaje}` | Agente (`llm_no_disponible`, `modelo_no_descargado`, `respuesta_invalida`, `solicitud_invalida`, `tiempo_agotado`) o **Core API** (`tiempo_agotado` a los 120 s) |
| `: ping` | Comentario SSE, sin datos | Agente, cada 15 s sin otro evento (X5-c). El parser de INV-35 ignora las líneas que empiezan con `:` |

### 4.2 Errores

Todos se responden con `{"detail": "…"}` en español, como en el resto del Core API.

| Código | Cuándo | `detail` |
| --- | --- | --- |
| 401 | Token inválido, vencido, de refresco o por vencer (X6) | «Token inválido o expirado» / «El token vence antes de terminar la respuesta: renuévelo» |
| 403 | Sin token o cuenta desactivada | «Not authenticated» / «Cuenta desactivada» |
| 422 | Cuerpo inválido: sin mensajes, el último no es del usuario, un rol desconocido o un texto vacío o de más de 2.000 caracteres | Los errores de validación de FastAPI |
| 429 | Ya hay un flujo del mismo usuario, o se alcanzó el límite total; con `Retry-After` | «Ya hay una respuesta en curso» / «El asistente está atendiendo otra consulta» |
| 502 | El agente responde con un código distinto de 200 y 503, o con un tipo de contenido que no es `text/event-stream` | «Agente respondió N» |
| 503 | El agente no acepta la conexión, o responde 503 | «Agente no disponible» / el motivo del agente |
| 504 | No llega el primer evento en 15 s (X4) | «El agente no respondió en 15 s» |

Una vez enviado el 200, los fallos llegan como un evento `error` y el flujo se cierra:

- a los 120 s, `tiempo_agotado`;
- si el agente corta sin `done` ni `error`, el flujo se cierra sin agregar eventos (X5-b no se aprobó). El registro lo anota como `interrumpido`.

### 4.3 `GET /api/chat/health`

Para los 3 roles (X7). Consulta `GET /ready` del agente:

```json
{ "estado": "listo", "modelo": "qwen3:8b", "version": "0.1.0", "flujos_activos": 0, "limite": 1 }
```

Si el agente no está listo, responde 503 con `{"detail": {"motivo": "modelo_no_descargado"}}`. Los motivos posibles son `ollama_no_alcanzable`, `modelo_no_descargado` y `agente_no_disponible`.

### 4.4 Configuración (variables de entorno del Core API)

| Variable | Por defecto | Para qué |
| --- | --- | --- |
| `NLP_AGENT_URL` | `http://localhost:8002`; `http://nlp-agent:8002` en el compose | Destino interno |
| `CHAT_TIMEOUT_S` | 120 | Tiempo total del flujo (criterio 4) |
| `CHAT_ESPERA_INICIO_S` | 15 | Espera del primer evento (X4) |
| `CHAT_MAX_FLUJOS` | 1 | Límite total (criterio 3) |
| `CHAT_RETRY_AFTER_S` | 10 | Valor de `Retry-After` |
| `CHAT_MAX_CARACTERES_MENSAJE` | 2000 | 422 por longitud (X2) |
| `CHAT_MAX_MENSAJES`, `CHAT_MAX_CARACTERES_TOTAL` | 13 y 16000 | 422 por un cuerpo demasiado grande (X2) |

Todas van a `.env.example`, como pide la sección 8.1 del documento del Sprint 6.

### 4.5 Nginx

Borrador de `frontend/nginx/chat-sse.conf` (X8), incluido antes de `location /api/`:

```nginx
location /api/chat/ {
    proxy_pass $core_api;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;          # cada evento sale apenas llega
    proxy_cache off;
    gzip off;                     # comprimir acumula el flujo (C3)
    proxy_connect_timeout 10s;
    proxy_send_timeout 135s;
    proxy_read_timeout 135s;      # entre lecturas; el total lo corta el Core API a los 120 s
}
```

`frontend/Dockerfile` copia el archivo nuevo, y el script de tiempos lo monta también.

**`scripts/probar_nginx_streaming.sh`.** Sigue el molde de `probar_nginx_timeout.sh`, con un Core API falso y las imágenes que ya están descargadas, sin construir nada. Comprueba que:

1. por `/api/chat/`, cada uno de 5 eventos enviados uno por segundo llega con menos de 0,3 s de diferencia respecto a su envío;
2. con `Accept-Encoding: gzip`, la respuesta de `/api/chat/` no trae `Content-Encoding`;
3. **el control:** el mismo Nginx con `text/event-stream` en `gzip_types` y sin el bloque acumula los eventos (primer evento después de 4 s);
4. `/api/` sigue igual (`nginx -t` y una petición JSON comprimida).

Tarda menos de un minuto.

## 5. Criterios de aceptación

| CA | Cómo se cumple |
| --- | --- |
| 1 (M) | `POST /api/chat/message` con JWT para los 3 roles y respuesta SSE con los 6 eventos; contrato en el OpenAPI (X15) |
| 2 (M) | Reenvío con `Authorization` y `X-Request-Id`; cancelación aguas arriba al desconectarse el cliente (C9), probada con el agente simulado |
| 3 (M) | Un flujo por usuario, `CHAT_MAX_FLUJOS` y 429 con `Retry-After` (X3) |
| 4 (M) | `CHAT_TIMEOUT_S`: 504 antes de empezar y `tiempo_agotado` después (X4) |
| 5 (M) | Bloque `/api/chat/` (sección 4.5), `X-Accel-Buffering: no` desde el Core API y `scripts/probar_nginx_streaming.sh` |
| 6 (M) | Prueba sobre los archivos de compose (C13); el bloque de Nginx apunta al Core API, nunca al 8002 |
| 7 (M) | `GET /api/chat/health` (sección 4.3) |
| 8 (M) | La tabla de la sección 4.2, con una prueba por código |
| 9 (S) | `request_id` en el registro, el encabezado y el `meta`, sin texto (X9); una prueba busca una cadena testigo en los registros capturados |
| 10 (C) | No se entrega (X16) |

## 6. Casos de prueba

| Caso | Entrada | Resultado esperado |
| --- | --- | --- |
| P-01 | Gerente, «hola»; el agente simulado emite `meta`, 3 `token` y `done` | 200 `text/event-stream` con `X-Accel-Buffering: no`; `X-Request-Id` igual al `request_id` de `meta`; eventos idénticos byte a byte |
| P-02 | Los 3 roles | 200 en los tres |
| P-03 | Sin token / token vencido / token de refresco / cuenta desactivada | 403 / 401 / 401 / 403; el agente no recibe la llamada |
| P-04 | Token al que le quedan 60 s (X6) | 401 |
| P-05 | Texto vacío / 2.001 caracteres / último mensaje del agente / rol `sistema` | 422; el agente no recibe la llamada |
| P-06 | 14 mensajes / 13 mensajes que suman 16.001 caracteres / 13 mensajes válidos (X2) | 422 / 422 / 200, y el agente recibe los 13 sin cambios |
| P-07 | Segunda petición del mismo usuario con la primera en curso | 429 con `Retry-After`; al terminar la primera, 200 |
| P-08 | Otro usuario con `CHAT_MAX_FLUJOS=1` / `=2` | 429 / 200 |
| P-09 | El cliente cierra a mitad del flujo | El agente simulado registra la desconexión en menos de 1 s y el cupo se libera: la siguiente petición da 200 |
| P-10 | Agente apagado / responde 500 / responde 503 / no envía nada en 15 s | 503 / 502 / 503 / 504 |
| P-11 | El agente sigue emitiendo durante 125 s | Evento `error` `tiempo_agotado` hacia los 120 s y cierre; el agente ve la desconexión |
| P-12 | El agente corta sin `done` ni `error` | El flujo termina con lo que llegó, sin eventos agregados; registro con `resultado = interrumpido` |
| P-13 | El agente emite `error` `llm_no_disponible` | Pasa sin cambios; registro con `resultado = error` |
| P-14 | Pregunta con una cadena testigo | La cadena no aparece en ningún registro capturado; el `request_id` sí |
| P-15 | `/api/chat/health`: agente listo / sin modelo / caído / sin token | 200 con el modelo / 503 `modelo_no_descargado` / 503 `agente_no_disponible` / 403 |
| P-16 | Archivos de compose | Ningún servicio publica el 8002 |
| P-17 | `scripts/probar_nginx_streaming.sh` | Las 4 comprobaciones de la sección 4.5 |
| P-18 | Marca `llm`: una pregunta con herramienta y el agente real, con los 3 roles; por Nginx, desde `~/InventaIO` | Eventos `tool`, `data` y `token` progresivos y `done`; 401, 403, 429 y 504 comprobados (DoD 6) |
| P-19 | El agente simulado calla 20 s antes de responder (X5-c) | Llega `: ping` a los 15 s y después el flujo normal. En el agente real, una prueba de que emite `: ping` sin otro evento |

## 7. Ruta de implementación

Un commit por paso en `feature/INV-36-api-chat`, con las pruebas en verde antes de pasar al siguiente.

**Calendario (sección 5 del documento del Sprint 6):**

- **21-oct, punto de control «hola de punta a punta»:** una pregunta pasa por una herramienta y vuelve en streaming, con los 3 roles. INV-36 debía estar en `develop` el 20-oct, pero el código empieza ese día: **el control queda en riesgo**. Del lado del agente ya se cumple (la prueba `llm` de INV-32, con los 3 roles).
- **20 y 21-oct:** pasos 2 a 6 con el agente simulado y P-18 con el agente real.
- **22 al 27-oct:** INV-35.

1. **Requerimientos.** Este documento y el formulario.
2. **Core API.**
   - `api/chat/`: `cliente.py`, `concurrencia.py`, `sse.py` y `router.py`;
   - `api/schemas/chat.py`;
   - configuración en `core/config.py`;
   - el router incluido en `main.py`;
   - el registro `inventaio.chat`.
3. **Pruebas.**
   - `api/tests/test_chat*.py`, con el agente simulado (P-01 a P-16);
   - la marca `llm`;
   - el CI con `-m "not integracion and not llm"`.
4. **Nginx.** `frontend/nginx/chat-sse.conf`, `frontend/Dockerfile` y `scripts/probar_nginx_streaming.sh` (P-17), ejecutado con contenedores sueltos, sin compose y sin construir imágenes.
5. **Contrato.**
   - el `: ping` cada 15 s en el agente (X5-c, C18), con su prueba;
   - el OpenAPI versionado regenerado;
   - `api/tests/postman/INV-36.postman_collection.json`;
   - `NLP_AGENT_URL` en el compose.
6. **Documentación.** `docs/INV-36-api-chat.md`, con N3 y N4 registradas con su número. Confluence, solo con aprobación.
7. **Verificación real**, desde `~/InventaIO`:
   - P-18 con los 3 roles;
   - Nginx con el perfil `web` y `docker compose` desde cero, que **construyen imágenes**: se pide permiso antes, por el espacio en disco.
8. **Cierre.** Merge `--no-ff` a `develop`, push y CI en verde cuando el dueño lo pida; luego, la ficha de Jira.

## 8. Definition of Done

La de la ficha (8 puntos), más lo siguiente:

- los 18 casos de la sección 6;
- el OpenAPI sin diferencias en el CI;
- la cobertura del Core API sobre el umbral de `api/.coveragerc` (70 %);
- revisión de seguridad: sin puertos nuevos, sin secretos y sin texto en los registros.

Lo que no se puede verificar en el CI (el agente real y Nginx con el stack completo) se corre en local y queda en `resultados-INV-36-*.md`, como en las historias anteriores.

## 9. Fuera de alcance y riesgos

**Fuera de alcance:**

- persistencia del historial (INV-37);
- TLS y dominio (INV-34);
- límite de intentos de login y el resto del hardening (D21);
- WebSocket (X16);
- el panel de chat (INV-35);
- contadores en Redis para varios procesos.

**Riesgos:**

| Riesgo | Mitigación |
| --- | --- |
| INV-36 empieza el 20-oct, el día en que debía estar en `develop` | Del lado del agente, el control del 21-oct ya pasa. Aquí se prioriza el camino mínimo: endpoint, límites, Nginx y P-18. La colección de Postman y el documento pueden quedar para después del control |
| Alguien agrega `text/event-stream` a `gzip_types`, o INV-34 escribe otro servidor sin el bloque | `gzip off` en el bloque incluido (X8) y el control del script (C3) |
| El navegador limita a 6 conexiones por origen en HTTP/1.1 | Un flujo por usuario ocupa una sola conexión; HTTP/2 llega con TLS en INV-34 |
| El token de 30 min vence en una conversación larga | X6 lo renueva antes de cada flujo; ningún flujo dura más de 120 s |
| Un modelo de 8 GB atiende de a una petición | Límite total de 1 y 429 con `Retry-After`; INV-35 muestra «ocupado» |
| Con varios procesos de uvicorn (INV-34), los contadores en memoria no se comparten | Queda anotado; Redis ya está en el compose |
| El disco de C: es limitado | Sin dependencias nuevas, sin construir imágenes en las pruebas y con un aviso antes de la verificación con compose |
