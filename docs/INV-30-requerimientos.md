# INV-30 · Servicio del agente (NLP Agent) con Ollama · Requerimientos

| Campo | Valor |
| --- | --- |
| Jira | INV-30 «NLP Agent Service: LLM autoalojado con Ollama» · 5 SP · Sprint 6 · Release 2 · épica E10 NLP Agent (INV-55) |
| Depende de | INV-24 (CI, imágenes y Dependabot), INV-25 (contrato de errores y permisos del Core API) |
| Alimenta a | INV-31 (conjunto de referencia), INV-32 (herramientas), INV-33 (prompts) e INV-36 (API de chat) |
| Rama | `feature/INV-30-nlp-agent`, desde `develop` (`bcc5a10`) |
| Hardware | Portátil con NVIDIA RTX 5050 Laptop (8 GB de VRAM), 12 hilos y 19 GB de RAM en WSL2 |

Revisión del 15 de octubre de 2026 contra `develop` y el equipo de desarrollo.

> **Estado al 18 de octubre:** spike cerrado. El conjunto creció de 20 a 43 preguntas (23 variantes del usuario) y se sumaron `qwen3:14b` y `qwen3:30b-a3b` en Colab. Modelo elegido: **`qwen3:8b`**, sin razonamiento. Mediciones, decisión y hallazgos en `docs/INV-30-nlp-agent-service.md`.

## 1. Historia de Jira

> Como desarrollador, quiero un servicio del agente conversacional que ejecute un modelo de lenguaje autoalojado con Ollama, para que las historias de herramientas, prompts y chat se construyan sobre una base medida, segura y lista para migrar a la nube.

La ficha trae 10 criterios (M) y las decisiones D22 (modelo autoalojado, sin APIs externas), N2 (spike de modelo), N6 (dos modos de Ollama) y N9 (Colab solo con datos sintéticos). Este documento las contrasta con el repositorio y fija lo que la ficha deja abierto.

## 2. Contraste con lo ya construido

| # | Hallazgo | Consecuencia |
| --- | --- | --- |
| C1 | No existe `nlp_agent/` ni código del agente en ninguna rama; la ficha está «En curso» desde el 15-oct sin trabajo en el repositorio | Se construye desde cero, con el molde de `ml_service/` |
| C2 | `ml_service/` ya resuelve lo que pide el criterio 1: `python:3.11-slim`, usuario 10001 sin shell, `HEALTHCHECK` en Python (la imagen no trae curl), pip, setuptools y wheel desinstalados, configuración con `pydantic-settings` | El Dockerfile y `core/config.py` del agente siguen ese patrón |
| C3 | `images.yml` está preparado para un servicio nuevo: «una fila en la lista `servicios` y el servicio en `docker-compose.verify.yml`». El escaneo semanal tiene su propia lista | Criterio 7: una fila en las dos listas, un job nuevo en `ci.yml` y `nlp_agent` en Dependabot |
| C4 | El compose de desarrollo publica 8000, 8001, 5432 y 6379. INV-36 exige que el 8002 no se publique | `nlp-agent` sin `ports:`; se prueba desde la red de compose o con `docker compose exec` |
| C5 | Ollama no está instalado. La última versión es la v0.40.5, que se distribuye como `.tar.zst` y no como `.tgz` | Instalación sin sudo en `~/.local/ollama` (W2) |
| C6 | WSL ve la GPU (`nvidia-smi`) y Docker también (`--gpus all`). Un contenedor alcanza un servicio de WSL por `host.docker.internal` (con `host-gateway`), no por `172.17.0.1` ni con `network_mode: host` | Los dos modos de N6 son viables. En modo WSL, el agente usa `OLLAMA_BASE_URL=http://host.docker.internal:11434` y Ollama escucha en `127.0.0.1`: con `0.0.0.0` escucha en `[::]` y WSL solo lo reenvía por `::1`, que Docker Desktop no usa (medido el 16-oct) |
| C7 | 8 GB de VRAM: un modelo de 8B en Q4_K_M (~5 GB) cabe con contexto de 8k; dos a la vez no | El spike carga un candidato a la vez (`keep_alive` corto entre candidatos) |
| C8 | El Core API valida el JWT y los permisos por ubicación (INV-25); el agente no tiene credenciales propias (criterio 6) | El agente reenvía el `Authorization` que recibe del Core API; no lee `.env` de la bodega |

## 3. Decisiones

Aprobadas por el usuario el 15-oct (formulario):

| # | Decisión | Elegida |
| --- | --- | --- |
| W1 | Dónde corre Ollama para desarrollar y para el spike | **Nativo en WSL**. El contenedor `ollama` del perfil `llm` es el segundo modo (el de AWS) y se verifica una vez |
| W2 | Instalación | **Sin sudo**, binario oficial v0.40.5 en `~/.local/ollama`, verificado con su SHA-256, y un script de arranque `scripts/ollama_wsl.sh` |
| W3 | Candidatos del spike | **Los 3 de la ficha**: `qwen3:8b`, `llama3.1:8b` (línea base) y Qwen3-4B-Instruct-2507 (perfil de CPU) |
| W4 | Razonamiento de Qwen3 | **Sin razonamiento** (`/no_think` o `think: false`) en las 20 preguntas × 3 corridas; con razonamiento, solo la latencia en 5 preguntas |
| W5 | Paralelismo de los carriles | **Worktrees y una segunda sesión** para el carril C (INV-36 → INV-35); esta sesión lleva A (INV-30) y B (INV-31) |
| W6 | Las 20 preguntas v0 | **Las redacto con datos reales y el usuario valida** que sean preguntas que harían los tres roles |
| W7 | Colab (N9) | **También en Colab**, con resultados de herramientas sintéticos, como punto de comparación; las mediciones de la decisión son las del equipo local. La cuenta es Colab Pro (300 unidades, L4 disponible): en la L4, que es la GPU de la `g6.xlarge` de AWS, se suman `qwen3:14b` y `Qwen3-30B-A3B-Instruct-2507` como techo de calidad (documento de Sprint 6, §5) |
| W8 | Integración | **Dos merges**: el esqueleto (desbloquea INV-32 e INV-36) y después el spike con la decisión del modelo |

Propuestas técnicas, que siguen el molde existente (se cambian si el usuario lo pide):

| # | Propuesta |
| --- | --- |
| W9 | El conjunto v0 (20 preguntas) vive en `nlp_agent/evaluacion/conjuntos/v0/` dentro de esta historia, porque el spike lo necesita ya. INV-31 entrega la v1 (40 o más preguntas), el documento `docs/PLN-conjunto-referencia.*` y el glosario |
| W10 | El spike usa un catálogo provisional con las 8 herramientas (M) de la ficha de INV-32 y resultados sintéticos. INV-32 lo reemplaza por el catálogo real, validado contra el OpenAPI |
| W11 | El cliente de Ollama usa `/api/chat` nativo de Ollama (no la capa compatible con OpenAI) porque trae `think`, `keep_alive`, `options.num_gpu` y los tiempos (`prompt_eval_duration`, `eval_duration`) que piden los criterios 3 y 5 |
| W12 | Sin GPU se mide con el mismo Ollama y `options.num_gpu = 0`, no con otra instalación |
| W13 | Contrato interno del agente fijado aquí (sección 4.3) para que INV-36 e INV-35 avancen con un agente simulado |

## 4. Entradas, salidas e interfaz

### 4.1 Servicio

`nlp_agent/` (FastAPI, puerto 8002, solo en la red de compose):

| Ruta | Qué responde |
| --- | --- |
| `GET /health` | `200 {"status": "ok", "version": …}` si el proceso vive. Es lo único que verifica el CI de imágenes |
| `GET /ready` | `200` si Ollama responde y el modelo configurado está descargado; `503` con el motivo (`ollama_no_alcanzable`, `modelo_no_descargado`) si no |
| `POST /chat` | Sección 4.3. En INV-30 responde con el modelo y sin herramientas («hola» de punta a punta); INV-32 agrega las herramientas |

### 4.2 Configuración (solo variables de entorno, criterio 10)

| Variable | Valor por defecto | Para qué |
| --- | --- | --- |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` en compose; `http://localhost:11434` fuera de Docker | Modo WSL o contenedor (N6) |
| `LLM_MODELO` | El que decida el spike (tag fijo y digest anotado) | Criterio 3 |
| `LLM_NUM_CTX` | 8192 (lo ajusta el spike) | Criterio 5 |
| `LLM_KEEP_ALIVE` | `30m` | Evita recargar varios GB entre preguntas |
| `LLM_TEMPERATURA`, `LLM_TOP_P`, `LLM_SEMILLA` | 0, 1, 42 para herramientas | Criterio 5; reproducibilidad del spike |
| `LLM_RAZONAMIENTO` | `false` | W4 |
| `LLM_TIMEOUT_S` | 120 | Igual al límite que fija INV-36 |
| `CORE_API_URL` | `http://api:8000` | Lo usa INV-32 |

`OLLAMA_NUM_PARALLEL=1` es variable del servidor de Ollama: va en `scripts/ollama_wsl.sh` y en el servicio `ollama` del perfil `llm`.

### 4.3 Contrato interno `POST /chat` (v1, para el carril C)

> **v1 del 18 de octubre de 2026.** La fija INV-32 a partir del Core API real (decisiones T5 a T7 de `docs/INV-32-requerimientos.md`) y de las decisiones X de INV-36 del mismo día. Reemplaza a la v0 del 15-oct; los cambios están al final de esta sección. Lo implementa INV-32, salvo el `: ping`.

Solo lo llama el Core API (INV-36), con el `Authorization` del usuario y `X-Request-Id`.

```json
{ "mensajes": [ { "rol": "usuario", "texto": "¿Cuánto arroz hay en GLORIETA?" } ] }
```

- `rol` es `usuario` o `agente`, y el último mensaje es del `usuario`.
- Se aceptan a lo sumo **13 mensajes** (6 turnos y la pregunta) de hasta 2.000 caracteres cada uno. Son los mismos límites que valida el Core API (X2): lo que el Core API acepta llega al agente sin un 422.
- Antes de abrir el flujo, el agente responde `401` si falta `Authorization` y `422` si el cuerpo no cumple lo anterior.

Respuesta `text/event-stream`, un evento por bloque (`event: <nombre>` y `data: <JSON>`):

| Evento | Datos | Cuándo |
| --- | --- | --- |
| `meta` | `{request_id, modelo, version_prompt}` | Primero, en cuanto llega la petición y antes de llamar a Ollama (X5-f) |
| `tool` | Al empezar, `{id, nombre, estado: "inicio", etiqueta, lenta}`; al terminar, `{id, nombre, estado: "ok" \| "error", ms, codigo}` | Cada llamada a una herramienta |
| `data` | `{id, herramienta, forma, titulo, columnas, filas, total, mostrando, fecha_dato}` | Después del `tool` `ok` con el mismo `id`, si la herramienta devolvió filas para mostrar |
| `token` | `{texto}` | Fragmentos de la respuesta final. Las rondas de herramientas no se transmiten |
| `done` | `{tokens_prompt, tokens_respuesta, ms_total, ms_modelo, ms_herramientas, rondas, fechas_datos}` | Último evento si todo salió bien |
| `error` | `{codigo, mensaje}` | Último evento si algo falló |

El agente envía un comentario SSE `: ping` cada 15 s mientras no haya otro evento (X5-c, aprobado el 18-oct; se implementa en el agente fuera de INV-32). El lector de INV-35 ignora las líneas que empiezan con `:`.

**`tool`**
- `id`: `"<ronda>-<n>"` (`"1-1"`, `"1-2"`, `"2-1"`). Ollama puede pedir varias herramientas en una ronda; el `id` une el inicio con su fin y con su `data`.
- `nombre`: una de las 8 herramientas del catálogo v1 (sección 4 de `docs/INV-32-requerimientos.md`). Si el modelo inventa una herramienta, no se ejecuta ni genera evento.
- `etiqueta`: texto en español, por ejemplo «Inventario · GLORIETA · crítico». Lo arma el agente con los argumentos ya validados, nunca con texto libre del modelo. Solo va en `inicio`.
- `lenta`: `true` en las herramientas que pasan por la caché de ML del Core API, que en frío tardan hasta 40 s (39,7 s medidos el 18-oct). Son `listar_alertas` con origen IA y `recomendar_compras`. Solo va en `inicio`.
- `ms` y `codigo`: solo al final. Con `ok`, `codigo` es `null`. Con `error`, vale:
  - el estado HTTP del Core API (401, 403, 404, 422 o 5xx);
  - `422` si el agente rechazó los argumentos antes de llamar;
  - `504` si la llamada agotó su tiempo.
- Un error de herramienta **no** cierra el flujo: el modelo lo explica (INV-32, criterio 5).

**`data`**
- `forma`: `tabla`, o `tarjeta` para el pronóstico de una sucursal.
- `titulo`: se arma como `etiqueta`, con los argumentos validados.
- `columnas`: `[{clave, titulo, tipo}]`. `tipo` es `texto`, `cantidad`, `numero`, `fecha`, `semaforo` o `urgencia`.
- `filas`: `[{<clave>: <valor>}]`, a lo sumo 10, con **los mismos valores que leyó el modelo** (T5):
  - las cantidades, formateadas con la regla `texto_cantidad` («77,1 kg», «1 unidad», «4.024 unidades»);
  - los números, en es-CO;
  - las fechas, en ISO (`2026-01-02`);
  - `semaforo`, como `ok`, `bajo`, `critico` o `inconsistencia`;
  - `urgencia`, como `critica`, `alta` o `media` en las alertas, o como `urgente`, `alta` o `normal` en las compras.

  Semáforo y urgencia van como código para que el panel use sus chips.
- `total`: el total real que informa el Core API, por ejemplo 173 productos críticos en GLORIETA. `mostrando` es el número de filas enviadas.
- `fecha_dato`: la fecha de los datos que devolvió el Core API (`fecha_inventario`, `fecha_pronostico`, `fecha_fin` o `fecha_features`). Hoy es `2025-12-31` en todos los endpoints.
- Qué herramientas generan `data`:
  - en tabla: `consultar_inventario`, `listar_alertas`, `resumen_alertas`, `recomendar_compras` e `historial_ventas`;
  - en tarjeta: `pronosticar_demanda`.

  `buscar_producto` y `listar_sucursales` no generan `data`. Tampoco lo genera un resultado con error, sin filas, ambiguo o no encontrado.

**`done`**
- `tokens_prompt`: el de la ronda más grande, que es el presupuesto por ronda (INV-32, criterio 12). `tokens_respuesta`: la suma de todas las rondas.
- `ms_modelo` y `ms_herramientas`: el tiempo en Ollama y en las herramientas, sumados en todas las rondas. Los pide el documento de Sprint 6 (observabilidad: «tiempos del modelo y de las herramientas en el evento `done`»), e INV-36 los puede registrar con los tokens. `rondas`: las rondas con el modelo, de 1 a 4 (3 con herramientas y la última sin ellas).
- `fechas_datos`: las `fecha_dato` distintas de las herramientas que respondieron `ok`, en orden. Es `[]` si no se consultó ninguna. El panel la muestra al pie de la respuesta (INV-35, criterio 6).

**`error`**: `codigo` es `llm_no_disponible`, `modelo_no_descargado`, `respuesta_invalida`, `solicitud_invalida` o `tiempo_agotado` (a los `LLM_TIMEOUT_S` = 120 s). El Core API también corta a los 120 s, porque X5-d no se aprobó. Al llegar al límite, el `tiempo_agotado` puede venir de cualquiera de los dos.

INV-36 reenvía estos eventos sin cambiarlos y agrega los errores propios del Core API (401, 403, 422, 429, 502, 503 y 504). Cualquier cambio a este contrato se anota aquí y en el brief del carril C.

**Cambios de la v1 respecto a la v0 (15-oct):**
- `meta` ya no lleva `fecha_datos`. Salía siempre en `null`, porque `meta` va antes de cualquier herramienta. La fecha pasa a `data.fecha_dato` y a `done.fechas_datos` (T6).
- `tool` agrega `id`, `etiqueta`, `lenta` y `codigo` (T7).
- `data` agrega `id`, `forma`, `titulo` y `mostrando`, define el `tipo` de cada columna y fija que las filas llevan el texto que leyó el modelo (T5).
- `done` agrega `ms_modelo`, `ms_herramientas`, `rondas` (documento de Sprint 6, observabilidad) y `fechas_datos`.
- `error` usa la lista de códigos que el código emite de verdad:
  - sale `herramienta_error`, que nunca se emitía, porque los errores de herramienta no cortan el flujo;
  - entran `modelo_no_descargado`, `respuesta_invalida` y `solicitud_invalida`.
- El límite de mensajes pasa de 12 a 13 (X2).
- Se agrega el `: ping` cada 15 s (X5-c).

### 4.4 Spike

`scripts/smoke_llm.py` y `nlp_agent/evaluacion/` corren sin Docker contra cualquier `LLM_BASE_URL` (local o Colab):

- **Por candidato y modo:** con GPU y sin GPU; 20 preguntas × 3 corridas.
- **Registra:**
  - versión de Ollama y digest del modelo;
  - latencia al primer token y tiempo total;
  - tokens por segundo de generación y de procesamiento del prompt;
  - tokens por ronda (prompt y respuesta);
  - memoria (VRAM y RAM, de `/api/ps`);
  - herramienta y argumentos elegidos, y el acierto por corrida;
  - fallas de formato: argumentos que no validan, listas devueltas como texto JSON y razonamiento (`<think>`) filtrado al texto;
  - fidelidad de cifras: si los números de la respuesta aparecen en los resultados de las herramientas o en la pregunta.
- **Calcula:**
  - promedio y pass^3;
  - acierto en abstención;
  - p95 del tiempo total;
  - diferencias pareadas por pregunta entre candidatos, con intervalo por bootstrap pareado.
- **Metas aprobadas** (15-oct; se exigen con la v1 de INV-31): herramientas correctas ≥ 85 %, fidelidad ≥ 95 %, cero fugas y p95 ≤ 30 s en el equipo de desarrollo. Con 20 preguntas solo orientan.
- **Regla de decisión:** si el intervalo no separa a dos candidatos, se decide por tamaño y latencia (ficha de INV-31, criterio 11).

## 5. Criterios de aceptación

Los 10 criterios (M) de la ficha, con esta traducción al repositorio:

| CA | Cómo se cumple |
| --- | --- |
| 1 | `nlp_agent/` con Dockerfile como el de `ml_service` (usuario 10001, `HEALTHCHECK`, sin `--reload`) |
| 2 | `/health` y `/ready` (sección 4.1); `docker-compose.verify.yml` espera solo `/health` |
| 3 | `docs/INV-30-nlp-agent-service.md` con la tabla de mediciones del spike en GPU y CPU y la decisión del modelo con su número |
| 4 | Modo WSL (`OLLAMA_BASE_URL` a `host.docker.internal`) y servicio `ollama` en el perfil `llm`, con volumen `ollama_modelos` y GPU opcional; ninguno publica el 11434 |
| 5 | Sección 4.2, documentada en `docs/NLP-AGENT.md` |
| 6 | El agente no tiene variables `POSTGRES_*` ni credenciales del Core API; prueba que lo verifica |
| 7 | Fila en `images.yml` (build, publicación y escaneo), job en `ci.yml`, `nlp_agent/.coveragerc` con umbral, Dependabot, `requirements.txt` y `requirements-dev.txt` separados |
| 8 | Arnés con registro de las 3 corridas, pass^3 y bootstrap pareado; corre en Colab (W7) |
| 9 | Los dos modos documentados; sin GPU con `num_gpu = 0` (W12) |
| 10 | `.env.example` con las variables nuevas, volumen nombrado y descarga idempotente (`scripts/descargar_modelos_llm.sh`) |

## 6. Ruta de implementación

**Merge 1, el esqueleto (objetivo: sábado 17 de octubre):**
1. `nlp_agent/`: `core/config.py`, cliente de Ollama, `main.py` con `/health`, `/ready` y `/chat` sin herramientas.
2. Dockerfile, servicio `nlp-agent` en los dos compose y perfil `llm` con `ollama`.
3. CI: job en `ci.yml`, fila en `images.yml`, Dependabot y `.coveragerc`.
4. Pruebas unitarias con `httpx.MockTransport`; la marca `llm` para las que usan el modelo real.
5. Brief del carril C con el contrato de la sección 4.3.

**Merge 2, el spike (objetivo: lunes 19 de octubre):**
1. Las 20 preguntas v0, validadas por el usuario (W6), y el catálogo provisional de herramientas (W10).
2. El arnés y `scripts/smoke_llm.py`.
3. Las corridas: 3 candidatos × 2 modos × 20 preguntas × 3 corridas, más la latencia con razonamiento de W4.
4. El cuaderno de Colab (W7).
5. Los documentos `docs/INV-30-nlp-agent-service.md` y `docs/NLP-AGENT.md`.
6. La decisión del modelo, registrada con su número en Confluence.

**Calendario y reglas de corte** (documento de Sprint 6, §5):

| Fecha | Hito | Si no se cumple |
| --- | --- | --- |
| Sáb 17-oct | Merge del esqueleto de INV-30 | Los carriles B y C siguen con dobles; se corre el spike igual |
| Lun 19-oct | Merge del spike: modelo elegido | — |
| Mié 21-oct | «Hola» de punta a punta: una pregunta pasa por una herramienta y vuelve en streaming, con los 3 roles | INV-31 pasa al Release 3 y el catálogo de INV-32 se recorta a 6 herramientas |
| Mar 27-oct | p95 del modelo elegido ≤ 30 s en el equipo de desarrollo | Se baja a un modelo menor o se apaga el razonamiento |
| Mié 28-oct | Congelamiento de código | — |
| 29 y 30-oct | Regresión local, documentación, dossier y decisiones | — |
| Sáb 31-oct | Etiqueta `v2.0.0` y lanzamiento (PR de `develop` a `main`) | — |

## 7. Definition of Done

La de la ficha (8 puntos). Lo que no se puede verificar en el CI (modelo real, GPU) se corre en local y queda en `resultados-INV-30-*.md`, como en las historias anteriores.

## 8. Fuera de alcance y riesgos

**Fuera de alcance:** herramientas (INV-32), prompts por rol (INV-33), endpoint en el Core API (INV-36), compose de producción y AWS (INV-34) y ajuste fino del modelo.

**Riesgos:**

| Riesgo | Mitigación |
| --- | --- |
| La RTX 5050 (arquitectura Blackwell) necesita un CUDA reciente | Si Ollama no la usa, se documenta y se mide en CPU |
| Las descargas son grandes (~13 GB de modelos con red inestable) | Descargas reanudables |
| El spike ya va un día tarde respecto a la ficha (15–16 oct) | Se recupera con el merge del esqueleto antes del spike y con los carriles B y C en paralelo |
| Con 20 preguntas el intervalo de la comparación es ancho | El spike orienta, no certifica |
