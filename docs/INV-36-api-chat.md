# INV-36 · API de chat en el Core API (SSE) y Nginx · Resultados y guía de pruebas

Requerimientos y decisiones: [`INV-36-requerimientos.md`](INV-36-requerimientos.md) (C1–C19 y X1–X16). Contrato de eventos v1 del agente: §4.3 de [`INV-30-requerimientos.md`](INV-30-requerimientos.md).

## 1. Decisiones de la ficha

- **N3, una sola puerta.** El navegador pasa por Nginx y llega al Core API (`/api/chat/`). El Core API reenvía al agente interno, y las herramientas consultan con el JWT del usuario. **D12:** el criterio original, en que Nginx iba directo al agente en el 8002, se reemplazó: saltaba el JWT y los permisos.
- **N4, SSE sobre `fetch`.** El JWT va en un encabezado, que el WebSocket del navegador no permite, y el flujo va en un solo sentido. El WebSocket, que era el criterio 10 (C), no se entrega.

## 1b. Qué se entregó

```
Navegador ──▶ Nginx /api/chat/ ──▶ Core API POST /api/chat/message ──▶ agente /chat (interno) ──▶ Ollama
              (sin buffer ni gzip)   (token, 422, 429, 401 por vencer)    (herramientas con el mismo token)
```

| Pieza | Dónde |
| --- | --- |
| `POST /api/chat/message`: valida el token de los 3 roles y la conversación (X1, X2, X6), toma un cupo (429, X3), espera el primer evento hasta 15 s (X4) y reenvía los eventos del agente byte a byte (X10). A los 120 s, `error` `tiempo_agotado`. Si el cliente se va, cierra el flujo del agente | `api/chat/router.py`, `cliente.py`, `concurrencia.py` y `sse.py`; `api/schemas/chat.py` |
| `GET /api/chat/health` para los 3 roles (X7) | `api/chat/router.py` |
| Una línea de registro por flujo, sin el texto (X9). La sesión de la base se cierra al validar el usuario (X12) | `inventaio.chat`; `Depends(get_db, scope="function")` |
| Bloque de Nginx incluido en `nginx.conf` (X8) | `frontend/nginx/chat-sse.conf`, `frontend/Dockerfile` |
| `: ping` cada 15 s de silencio en el agente (X5-c) | `nlp_agent/chat/router.py`, `CHAT_PING_S` |
| Configuración (§4.4) | `api/core/config.py`, `.env.example`, `NLP_AGENT_URL` en el compose, sin `depends_on` (X13) |
| OpenAPI: `200 text/event-stream` con un ejemplo del flujo y los 7 códigos de error (X15) | `api/tests/postman/inventaio-core-api.openapi.yml` |

## 2. Hallazgos de la implementación

| # | Hallazgo | Qué se hizo |
| --- | --- | --- |
| H1 | Con el modelo en frío, entre `meta` y la primera herramienta hubo **64 s sin eventos** (21-oct). Un balanceador que corta a los 60 s de silencio, como el de AWS que verá INV-34, habría cerrado la conexión | El ping de X5-c en el agente: «: ping» cada 15 s, sin cancelar la espera del modelo (P-19) |
| H2 | La imagen de Nginx incluye `conf.d/*.conf` fuera del `server`: copiar el bloque del chat ahí invalida la configuración | El bloque va en `/etc/nginx/snippets/` y `nginx.conf` lo incluye dentro del `server`. `scripts/probar_nginx_timeout.sh` lo monta también |
| H3 | Una prueba comparaba dos tokens JWT generados en momentos distintos: `exp` va en segundos y, a veces, cambiaba | Se genera una sola vez. 20 corridas seguidas sin fallas |
| H4 | En la prueba de desconexión, el servidor libera el cupo y después escribe el registro: la prueba a veces miraba en medio | Espera las dos cosas |
| H5 | Aun con `conteo`, el modelo dice «hay 10 productos críticos» en LA 21, cuando son 147 | Es el hallazgo I8 de INV-32: va para INV-33 |
| H6 | **Conversación de varios turnos (22-oct, Postman):**<ul><li>con el historial «En GLORIETA hay 173 productos en estado crítico.» y la pregunta «¿Y en LA 21?», qwen3:8b responde **sin consultar** e inventa «125» (son 147);</li><li>con «Hay 173 productos críticos.» consulta y responde bien.</li></ul>Es reproducible con temperatura 0. El transporte de INV-36 funcionó en los dos casos | Va para INV-33: el verificador marca el «125», y el prompt v2 dice que las cifras de turnos anteriores no sirven para una pregunta nueva (commit `85cd912` de su rama). La colección de Postman solo verifica el transporte en ese caso |

## 3. Verificación (21-oct)

- **Core API: 224 pruebas sin base** (80 % de cobertura total; los módulos del chat, entre 86 % y 95 %) y **67 de integración**, todas en verde. `tests/test_chat.py` cubre los casos P-01 a P-17 y P-19:
  - el flujo v1 pasa byte a byte, con el ping;
  - los 3 roles;
  - el `request_id`;
  - 403 y 401, incluido el del token por vencer;
  - 422 y los 13 mensajes;
  - 429, por usuario y en total;
  - 503, 502 y 504 antes del primer evento;
  - el tiempo total agotado;
  - el corte del agente sin `done`;
  - el error del agente, que pasa sin cambios;
  - el registro sin texto;
  - `/health`;
  - que nadie publique el 8002;
  - la **desconexión real** con un uvicorn (P-09).
- **Agente: 297 pruebas**, con la del ping.
- **Nginx:** `scripts/probar_nginx_streaming.sh`, con 4 de 4 comprobaciones:
  - por `/api/chat/`, los eventos llegan a 0,01, 1,01, 2,01, 3,01 y 4,01 s, sin comprimir;
  - el control, con gzip y sin el bloque, entrega todo a los 5,01 s;
  - `/api/` sigue comprimiendo el JSON.

  `scripts/probar_nginx_timeout.sh` sigue pasando con el bloque montado.
- **P-18, con el agente y el Core API reales:**
  - gerente, admin_bodega y admin_sucursal de LA 21 reciben `tool`, `data`, `token` y `done` en 6 a 9 s;
  - con el modelo en frío, `meta` llega a los 0,08 s y la respuesta a los 68 s, sin cortes;
  - una segunda pregunta del mismo usuario en curso da `429` con `Retry-After: 10`;
  - sin token, 403;
  - una línea por flujo: `resultado=ok codigo=200 … rondas=2`, sin el texto.

- **Pruebas manuales del usuario** (21 y 22-oct): satisfactorias. Cubrieron los 3 roles, el 403, la conversación, el 429, el corte y el registro sin texto.
- **Colección de Postman** `api/tests/postman/INV-36.postman_collection.json`: 16 peticiones y 33 verificaciones, sin fallas. Prueba la salud y el flujo v1 con los 3 roles, el 403 dentro del flujo, la conversación y los errores 401, 403 y 422. Se corre así:

  ```bash
  npx newman run api/tests/postman/INV-36.postman_collection.json --env-var baseUrl=http://localhost:8000 --timeout-request 150000
  ```

  El 429, el 502, el 503 y el 504 no se pueden provocar con el agente real: los cubre `tests/test_chat.py`.
- **Pruebas solo locales (DoD 3):** las 5 de la marca `llm` del agente, con el ping, contra el Core API y Ollama reales, y las 16 de la bodega de `ml_service`.

## 4. Cómo probarlo

**Pruebas automáticas:**

```bash
docker exec inventaio-api python -m pytest -q tests/test_chat.py
cd ~/InventaIO/nlp_agent && ~/venvs/inventaio/bin/python -m pytest -q tests/test_chat.py
bash scripts/probar_nginx_streaming.sh          # menos de 1 min; usa imágenes ya descargadas
```

**A mano, por el Core API.** Es el camino de la app. Necesita el stack arriba con el agente y Ollama:

```bash
cd ~/InventaIO && export INVENTAIO_CLAVE_PRUEBA=admin123
~/venvs/inventaio/bin/python scripts/preguntar_agente.py --por-core-api --rol gerente "¿Cuántas alertas críticas hay en GLORIETA?"
~/venvs/inventaio/bin/python scripts/preguntar_agente.py --por-core-api --rol admin_sucursal --sucursal "LA 21" "¿Y en GLORIETA?"   # 403 dentro de la herramienta
~/venvs/inventaio/bin/python scripts/preguntar_agente.py --por-core-api --crudo --rol admin_bodega "¿Qué hay crítico en la Bodega Central?"   # los eventos tal cual, para INV-35
```

**Con curl:**

```bash
TOK=$(curl -s -X POST localhost:8000/api/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"gerente@inventaio.co","password":"admin123"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -s localhost:8000/api/chat/health -H "Authorization: Bearer $TOK"
curl -N -X POST localhost:8000/api/chat/message -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' \
  -d '{"mensajes":[{"rol":"usuario","texto":"¿Cuántas alertas críticas hay en GLORIETA?"}]}'
docker logs inventaio-api --since 5m 2>&1 | grep inventaio.chat     # una línea por flujo, sin texto
```

Para ver el 429, se lanza la misma pregunta dos veces seguidas con el mismo token. Para ver el ping, se pregunta con el modelo en frío (después de 30 min sin uso): aparecen líneas `: ping` cada 15 s antes del primer `tool`.

## 5. Definition of Done

| DoD | Estado |
| --- | --- |
| 1 | Criterios (M) del 1 al 8 cumplidos, el 9 (S) entregado y el 10 (C) fuera (N4) |
| 2 | CI: ruff y pruebas con cobertura (Core API 80 %, agente 98 %). El OpenAPI se regeneró. Las imágenes y Trivy se confirman con el push |
| 3 | Pruebas de integración del Core API (67) y de la bodega de `ml_service` (16), y las de la marca `llm` del agente (5) |
| 4 | Seguridad: sin puertos nuevos (prueba sobre los compose), sin secretos (la clave de prueba va por variable de entorno) y una línea de registro sin texto |
| 5 | Este documento, N3 y N4 (§1) y el OpenAPI |
| 6 | Streaming por Nginx: `probar_nginx_streaming.sh` y el stack con el perfil `web` (§6). 401, 403, 429 y 504: pruebas, Postman y verificación real |
| 7 | Los 3 roles con el agente real y `docker compose` desde cero (§6) |
| 8 | Merge a `develop` |

## 6. Verificación con el stack completo, por Nginx (22-oct)

`docker compose --profile web build` reconstruyó las imágenes `api`, `ml-service` y `web`. La de `nlp-agent` ya estaba al día con el ping. Después, `docker compose --profile web up -d --force-recreate` recreó todos los contenedores **sin borrar volúmenes**, y los 7 quedaron sanos. Todo lo de abajo pasa por **Nginx en el 8080**, con el agente y qwen3:8b reales:

| Prueba | Resultado |
| --- | --- |
| Los 3 roles | 200, `meta` … `done`. Gerente: 16 tokens hasta los 6,97 s. admin_bodega: **380 tokens repartidos entre los 3,15 y los 12,05 s**, que llegan progresivamente y no todos juntos. admin_sucursal de LA 21: 97 tokens entre los 3,07 y los 5,28 s |
| Compresión | El cliente pide gzip y la respuesta no viene comprimida |
| `request_id` | Lo pone Nginx y reemplaza el que manda el navegador (X9). El Core API lo usa en el registro |
| 401 y 403 | Token inválido, 401; sin token, 403 |
| 429 | Dos preguntas del mismo usuario a la vez: la primera recibe 200 y la segunda 429, con `Retry-After: 10` |
| 504 | Con el agente en pausa (`docker pause`), 504 a los 14,99 s con «El agente no respondió en 15 s». Al reanudarlo, `/health` vuelve a 200 con `flujos_activos: 0` |
| Postman | 16 peticiones y 33 verificaciones, sin fallas, por el 8080 y por el 8000 |
| Registro | Una línea por flujo: `ok`, `rechazado 429`, `error 504`, sin el texto |

Nginx no reenvía `X-Accel-Buffering` al navegador: es una instrucción para él. Por eso la colección lo acepta ausente cuando pasa por el 8080.
