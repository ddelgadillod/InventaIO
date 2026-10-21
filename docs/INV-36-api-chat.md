# INV-36 · API de chat en el Core API (SSE) y Nginx · Resultados y guía de pruebas

Requerimientos y decisiones: [`INV-36-requerimientos.md`](INV-36-requerimientos.md) (C1–C19 y X1–X16). Contrato de eventos v1 del agente: §4.3 de [`INV-30-requerimientos.md`](INV-30-requerimientos.md).

## 1. Qué se entregó

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

**Pendiente:**
- **Nginx con el stack completo** (perfil `web`): reconstruir la imagen `web` descarga Node y las dependencias de npm, así que se pide permiso antes, por el disco. El bloque se probó con el Nginx 1.30 real del script.
- **La colección de Postman.**

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
