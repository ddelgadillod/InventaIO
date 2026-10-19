# NLP Agent · Arquitectura y operación

El agente conversacional de InventAI/o: responde en español sobre el inventario usando un modelo de lenguaje **autoalojado** con Ollama (D22: ninguna API externa de LLM). Historias: INV-30 (servicio y modelo), INV-31 (conocimiento y conjunto de referencia), INV-32 (herramientas), INV-33 (prompts) e INV-36 (API de chat). Requerimientos y decisiones: [`INV-30-requerimientos.md`](INV-30-requerimientos.md) y [`SPRINT-6-requerimientos.md`](SPRINT-6-requerimientos.md).

Estado al 19 de octubre de 2026: el servicio (INV-30) responde con `qwen3:8b` y **consulta los datos con 8 herramientas de solo lectura sobre el Core API** (INV-32, catálogo y decisiones en [`INV-32-requerimientos.md`](INV-32-requerimientos.md); medición y guía de pruebas en [`INV-32-herramientas-agente.md`](INV-32-herramientas-agente.md)). Los prompts por rol llegan con INV-33.

## Arquitectura

```
Navegador ──▶ Nginx (web) ──▶ Core API /api/chat (INV-36: JWT, permisos, límites)
                                    │  Authorization del usuario + X-Request-Id
                                    ▼
                              nlp-agent :8002 (interno) ──▶ Ollama :11434
                                    │
                                    └─▶ herramientas de INV-32 ──▶ Core API, con el mismo token
```

- **Una sola puerta (N3, D12).** El navegador nunca llega al agente: pasa por el Core API, que valida el token y los permisos. Ni el compose ni Nginx publican el 8002.
- **Sin credenciales propias (criterio 6).** El agente no tiene `POSTGRES_*` ni usuario del Core API. Cada herramienta consulta el Core API con el token de quien pregunta, así que el agente ve lo mismo que esa persona, ni más ni menos.
- **Sin texto en los registros (Ley 1581).** Se registra el `request_id`, el resultado y la duración; nunca el contenido de los mensajes. Por cada herramienta, una línea con su nombre, estado, código y milisegundos, sin argumentos ni resultados. El registro de URLs de httpx queda en WARNING porque las consultas llevan lo que escribió el usuario.

## Código

| Ruta | Qué hace |
| --- | --- |
| `nlp_agent/main.py` | `crear_app()`, `/health` y `/ready` |
| `nlp_agent/core/config.py` | Configuración por variables de entorno |
| `nlp_agent/llm/cliente.py` | `ClienteLLM` (interfaz) y `ClienteOllama` (API nativa `/api/chat`, W11): respuesta normal, stream, llamadas a herramientas, métricas y errores con código |
| `nlp_agent/llm/razonamiento.py` | Quita el razonamiento (`<think>…</think>`) aunque venga partido entre fragmentos |
| `nlp_agent/chat/` | `POST /chat`: validación, eventos SSE del contrato v1 y tiempo máximo |
| `nlp_agent/agente/bucle.py` | Bucle de herramientas (INV-32, T11): hasta 3 rondas en streaming y una final sin herramientas; eventos `tool`, `data` y `token`. Lo usa también el arnés |
| `nlp_agent/agente/prompt.py` | Prompt de sistema con herramientas (`prompts/v1/`, T15) y la descripción del usuario por rol |
| `nlp_agent/herramientas/` | Catálogo v1 (`catalogo.py`), base común y validación tolerante (`base.py`), resolución de productos, sucursales y categorías (`contexto.py`), cliente del Core API (`core_api.py`) y formato es-CO (`formato.py`) |
| `nlp_agent/prompts/` | `v0/`, el del esqueleto (sin datos), y `v1/`, el de INV-32; INV-33 agrega las partes por rol |

## Rutas

| Ruta | Respuesta |
| --- | --- |
| `GET /health` | `200 {"status": "ok", "servicio": "nlp-agent", "version"}` si el proceso vive, aunque Ollama no esté. Es el `HEALTHCHECK` y lo único que verifica el CI |
| `GET /ready` | `200 {"status": "listo", "modelo", "version_ollama", "version"}`, o `503 {"status": "no_listo", "modelo", "motivo"}` con `ollama_no_alcanzable` o `modelo_no_descargado` |
| `POST /chat` | SSE con `meta`, `tool`, `data`, `token`… y `done` o `error` al final. Contrato v1 en la §4.3 de `INV-30-requerimientos.md`. Exige `Authorization` (401 sin él); 422 si la petición no cumple los límites |

Códigos del evento `error`: `llm_no_disponible`, `modelo_no_descargado`, `solicitud_invalida` (por ejemplo, razonamiento pedido a un modelo que no lo tiene), `respuesta_invalida` y `tiempo_agotado`.

## Configuración

Todo por variables de entorno (`.env.example`):

| Variable | Por defecto | Para qué |
| --- | --- | --- |
| `OLLAMA_BASE_URL` | `http://localhost:11434` fuera de Docker; `http://host.docker.internal:11434` en el compose | Dónde está Ollama |
| `LLM_MODELO` | `qwen3:8b` (decidido en el spike, ver `docs/INV-30-nlp-agent-service.md`) | Tag fijo del modelo |
| `LLM_NUM_CTX` | 8192 | Contexto; con 8 GB de VRAM no puede crecer sin límite |
| `LLM_KEEP_ALIVE` | `30m` | Tiempo que el modelo queda cargado; la primera carga tarda de 7 a 77 s |
| `LLM_TEMPERATURA`, `LLM_TOP_P`, `LLM_SEMILLA` | 0, 1, 42 | Respuestas lo más repetibles posible; aun así Ollama no repite exacto |
| `LLM_RAZONAMIENTO` | `false` | W4. Con `true`, un modelo sin razonamiento (llama3.1) da `solicitud_invalida` |
| `LLM_TIMEOUT_S` | 120 | Tiempo máximo de una respuesta |
| `CORE_API_URL` | `http://api:8000` | Para las herramientas de INV-32 |
| `CORE_API_TIMEOUT_S` | 60 | Tiempo máximo de cada llamada al Core API (T10): cubre los ~40 s de la caché de ML en frío |
| `MAX_MENSAJES`, `MAX_CARACTERES_MENSAJE` | 13 y 2.000 | Límites de `/chat`, los mismos que valida el Core API (X2) |

Variables del servidor de Ollama (en `scripts/ollama_wsl.sh` y en el servicio `ollama`):
- `OLLAMA_NUM_PARALLEL=1` y `OLLAMA_MAX_LOADED_MODELS=1`: un modelo cargado y una petición a la vez.
- `OLLAMA_KEEP_ALIVE=30m`.
- `OLLAMA_NO_CLOUD=1`: apaga los modelos «cloud» de Ollama, que corren en servidores externos.

## Dónde corre Ollama (N6)

### Modo 1 · Nativo en WSL, con la GPU (desarrollo, W1)

**Instalación sin sudo (W2).** Ollama v0.40.5 en `~/.local/ollama`:

```bash
mkdir -p ~/.local/ollama/descarga && cd ~/.local/ollama/descarga
curl -fL -C - -o ollama.tar.zst https://github.com/ollama/ollama/releases/download/v0.40.5/ollama-linux-amd64.tar.zst
curl -fsL -o sha256sum.txt https://github.com/ollama/ollama/releases/download/v0.40.5/sha256sum.txt
grep ollama-linux-amd64.tar.zst sha256sum.txt   # debe coincidir con: sha256sum ollama.tar.zst
cd .. && tar --use-compress-program=unzstd -xf descarga/ollama.tar.zst && rm -r descarga
```

Antes de descargar, revisar el espacio en C: (`df -h /mnt/c`). El 15 de octubre, el disco lleno dejó la extracción a medias y Ubuntu en solo lectura.

**Uso:**

```bash
bash scripts/ollama_wsl.sh iniciar     # también: detener, estado
bash scripts/descargar_modelos_llm.sh qwen3:8b qwen3:4b-instruct-2507-q4_K_M llama3.1:8b
docker compose up -d --build nlp-agent
```

El script ata Ollama a `127.0.0.1:11434`. Con `0.0.0.0`, Ollama escucha en `[::]` y WSL solo reenvía el puerto a Windows por `::1`. Docker Desktop, en cambio, manda `host.docker.internal` al `127.0.0.1` de Windows, así que el contenedor recibe «connection refused» (medido el 16 de octubre). Con `127.0.0.1` el agente lo alcanza y el puerto no queda expuesto a ninguna red.

**Probar los modelos a mano:**

```bash
~/.local/ollama/bin/ollama run qwen3:8b --think=false --verbose
```

Muestra la velocidad después de cada respuesta. Dentro del chat, `/set think` y `/set nothink` cambian el razonamiento, y `/bye` sale.

### Modo 2 · Contenedor `ollama` del perfil `llm` (el de la nube)

```bash
# CPU
OLLAMA_BASE_URL=http://ollama:11434 docker compose --profile llm up -d ollama nlp-agent
# GPU NVIDIA visible para Docker (en este equipo lo está)
OLLAMA_BASE_URL=http://ollama:11434 docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile llm up -d ollama nlp-agent
# Modelos, en el volumen ollama_modelos (idempotente)
OLLAMA_CMD="docker compose exec -T ollama ollama" bash scripts/descargar_modelos_llm.sh qwen3:8b
```

La imagen es `ollama/ollama:0.40.5`, fijada por digest; ocupa unos 3,8 GB más los modelos. Por el espacio en disco, este modo se verifica una vez, al final del sprint.

## Modelos

Descargados el 16 de octubre de 2026 (Q4_K_M) y probados en la GPU (RTX 5050 Laptop, 8 GB) con una pregunta corta. **No es el spike:** sus resultados y la decisión del modelo están en `docs/INV-30-nlp-agent-service.md`.

| Modelo | Digest | Disco | VRAM con ctx 8k | Carga en frío | Generación | Lectura del prompt |
| --- | --- | --- | --- | --- | --- | --- |
| `qwen3:8b` | `500a1f067a9f` | 5,2 GB | 6,2 GB | 77 s (incluye la preparación de CUDA de la primera vez) | ~50 tok/s | ~1.700 tok/s |
| `qwen3:4b-instruct-2507-q4_K_M` | `0edcdef34593` | 2,5 GB | 3,9 GB | 7 s | ~86 tok/s | ~2.500 tok/s |
| `llama3.1:8b` | `46e0c10c039e` | 4,9 GB | 5,8 GB | 11 s | ~52 tok/s | ~165 tok/s |

Observaciones para el spike:
- `llama3.1:8b` dio respuestas de distinta longitud en dos corridas con temperatura 0 y semilla fija.
- Ollama marca «thinking» en el 4B Instruct-2507, pero no razonó.

## Pruebas

```bash
cd nlp_agent
~/venvs/inventaio/bin/python -m pytest -m "not llm" --cov=.   # como el CI: Ollama simulado
~/venvs/inventaio/bin/python -m pytest -m llm                 # con Ollama y el modelo reales (solo local)
```

- Las unitarias usan un Ollama simulado (`httpx.MockTransport`, en `tests/conftest.py`). Cubren:
  - la forma de la llamada con herramientas (contrato con la API nativa);
  - las respuestas normales y en stream;
  - los argumentos que llegan como texto JSON;
  - el razonamiento filtrado;
  - cada código de error y el tiempo máximo;
  - los eventos SSE;
  - que el texto no llegue a los registros;
  - que no haya credenciales.
- La marca `llm` prueba `/ready` y el «hola» de punta a punta con el modelo real. Se salta sola si Ollama no responde.
- Umbral de cobertura: 90 % (`nlp_agent/.coveragerc`).

## Seguridad

- Solo lectura: el agente no escribe en ninguna parte y no tiene acceso a la base de datos.
- Ni el 8002 ni el 11434 se publican, y Ollama nativo escucha solo en `127.0.0.1`.
- Sin credenciales propias ni secretos en el código.
- Sin el texto de los mensajes en los registros.
- `OLLAMA_NO_CLOUD=1`: ningún modelo corre fuera del equipo.
