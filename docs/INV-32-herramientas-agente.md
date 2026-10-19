# INV-32 · Herramientas del agente · Resultados y guía de pruebas

Requerimientos, decisiones T1–T18 y hallazgos C1–C19: [`INV-32-requerimientos.md`](INV-32-requerimientos.md). Contrato de eventos v1: §4.3 de [`INV-30-requerimientos.md`](INV-30-requerimientos.md). Operación del servicio: [`NLP-AGENT.md`](NLP-AGENT.md).

## 1. Qué se entregó

- **Catálogo v1 de 8 herramientas** de solo lectura sobre el Core API, con el token del usuario (`nlp_agent/herramientas/`).
- **Bucle de herramientas** compartido por el chat y el arnés (`nlp_agent/agente/bucle.py`):
  - hasta 3 rondas, más una final sin herramientas;
  - eventos `tool`, `data` y `token` del contrato v1.
- **`POST /chat` con el contrato v1:**
  - `meta` sin fecha;
  - `done` con `ms_modelo`, `ms_herramientas`, `rondas` y `fechas_datos`;
  - hasta 13 mensajes.
- **Prompt `v1`** (T15) y descripción del usuario por rol, leída de `/api/auth/me` (C18).
- **Pruebas:**
  - 233 sin el modelo, 98 % de cobertura;
  - 3 nuevas con el modelo y el Core API reales;
  - prueba de contrato con el OpenAPI (T13).
- **Arnés en modo real** (`--core-api`, T17).
- **`scripts/preguntar_agente.py`**, para probar a mano.

**Decisión N5 (bucle propio, sin LangChain).** El bucle se escribió sobre la API nativa de Ollama, con esquemas Pydantic, en unas 190 líneas. No hizo falta `langchain-core`: el cliente ya tenía las llamadas a herramientas, los argumentos como texto JSON y el filtro de razonamiento.

## 2. Hallazgos de la implementación

| # | Hallazgo | Qué se hizo |
| --- | --- | --- |
| I1 | Con herramientas y `stream: true`, Ollama 0.40.5 entrega la llamada a la herramienta en un fragmento propio y **sin texto**. La respuesta sale token por token. Medido el 18-oct con qwen3:8b | Todas las rondas van en streaming: la que pide herramientas no transmite nada y la que responde se ve mientras se genera, sin una llamada extra al modelo |
| I2 | Con solo `total: 173, mostrando: 10`, qwen3:8b respondió «hay **10** productos críticos» en GLORIETA | Las herramientas de listas agregan `conteo`: «173 filas de inventario en total; se muestran los primeros 10». Con eso respondió «173» |
| I3 | Con «Omítelo para no filtrar», qwen3:8b igual puso PRINCIPAL en un pronóstico que no nombraba sucursal | Pronóstico y ventas dicen «Solo si la pregunta nombra una sucursal; si no, se consultan todas las que ve el usuario». Con eso omitió la sucursal y T9 dio las 3 |
| I4 | httpx registra en INFO la URL completa de cada petición. La de `buscar_producto` lleva lo que escribió el usuario (`busqueda=Mi cédula es…`). Lo encontró la prueba del registro | Los registros de `httpx` y `httpcore` quedan en WARNING (`herramientas/core_api.py`) |
| I5 | Con las ventas de 3 sucursales, el modelo sumó por su cuenta y dio un total que no está en los datos (9.536; la suma de la última ventana es 11.006) | Para INV-33: instrucción de no sumar y de citar `suma_por_sucursal` |
| I6 | Las compras urgentes del admin_bodega en frío: **31,9 s** en la herramienta y 35,3 s en total | El evento `tool` marca `lenta: true`. Calentar la caché al arrancar el Core API queda propuesto para INV-34 |
| I7 | En el pronóstico de 3 sucursales del arroz Carolina, la respuesta dijo «cobertura recomendada hasta 313, 34 y 145» | No es una fuga del intervalo: es el texto oficial de `interpretacion` de ml_service para los productos intermitentes. En los perecederos (C9) ese texto no da cifra |
| I8 | Aun con `conteo`, el admin de LA 21 recibió «hay 10 productos críticos» en su sucursal (son 147). En GLORIETA, la misma pregunta del gerente dijo bien «173» | La salida explícita es de INV-32 y ya está (`total` y `conteo`). La instrucción de decir el total es de INV-33, como dejó anotado el spike |
| I9 | «¿Cuánta leche hay en PRINCIPAL?» responde «89 productos de leche», contando «arroz con leche» y «café con leche» | Es la v0-14: debería pedir aclaración. Va para INV-33 |

## 3. Medición con el Core API real (T17)

Dos corridas el 18-oct con el conjunto v0 (43 preguntas × 3 corridas), qwen3:8b con GPU en el equipo de desarrollo, las herramientas reales contra el Core API y el usuario de prueba del rol de cada pregunta. Archivos en `nlp_agent/evaluacion/resultados/2026-10-18_local/`:
- línea base: `qwen3_8b_gpu_real_linea-base.jsonl`;
- con las descripciones que separan pronóstico, alertas y compras: `qwen3_8b_gpu_real.jsonl`.

| Corrida | Acierto | pass^3 | Herramienta | Fidelidad | Abstención | Fugas | Errores | p50 | p95 | Tokens por ronda (p95 / máx.) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Línea base | 84 % | 84 % | 86 % | 100 % | 100 % | 0 | 0 | 2,4 s | 11,5 s | 2.240 / 2.543 |
| **Descripciones ajustadas** (la entregada) | **88 %** | **88 %** | **91 %** | **100 %** | **100 %** | **0** | **0** | **2,6 s** | **11,6 s** | **2.310 / 2.583** |

Metas aprobadas el 15-oct: herramienta ≥ 85 %, fidelidad ≥ 95 %, cero fugas y p95 ≤ 30 s. **Las dos corridas las cumplen.**

**Cómo leer estas cifras:**
- **No se comparan con el spike.** Con datos reales no se califican los hechos clave del v0, que son sintéticos (T17). Por eso el acierto real (88 %) no es comparable con el 63–65 % del spike. La herramienta correcta sí es comparable: 86 % en el spike y 91 % ahora.
- **La mejora no está demostrada.** Las descripciones ajustadas corrigen v0-07b (pronóstico en vez de alertas con IA, el hallazgo del spike asignado a INV-32) y v0-06c, en las 3 corridas. La diferencia pareada es +4,7 puntos, con un IC del 95 % de [0,0; +11,6]: no se separa. Además se ajustó mirando el mismo v0, así que solo orienta. Las metas se exigen con la v1 de INV-31.
- **pass^3 = acierto.** Con temperatura 0 y semilla fija, las 3 corridas dan lo mismo, como en el spike.
- **El p95 de 11,6 s viene de una sola pregunta.** v0-03 dio 12,6 s en la primera corrida. Una sola consulta en frío a la caché de ML, en cambio, pasa de 30 s (I6).
- **La ronda más grande cabe en el contexto.** Usa como máximo 2.583 tokens, con el catálogo de 8 herramientas, el prompt y los resultados, y queda muy por debajo de los 8.192 de `LLM_NUM_CTX`. El presupuesto de referencia de la ficha para CPU era de unos 3.000 tokens (criterio 12).

**Siguen fallando 5 preguntas, las 3 corridas:**

| Pregunta | Qué hace el modelo | Para |
| --- | --- | --- |
| v0-05b, v0-11, v0-11b, v0-20b | Llena un filtro opcional que nadie pidió: `urgencia` en el resumen, `urgencia: normal` en compras o BODEGA_CENTRAL en «todas las sucursales» | INV-33 (instrucción) e INV-31 (medirlo con la v1). El «Omítelo para no filtrar» del spike no alcanza |
| v0-14 | No pide aclaración ante «leche» (I9) | INV-33 |

**Punto ciego:** en el modo real, el calificador no detecta un total equivocado como el de I8. No califica los hechos del v0, y «10» cae en el umbral de conteos. INV-31 debería calificar, con datos reales, que el total dicho coincida con `total`.

## 4. Cómo probarlo

### 4.1 Pruebas automáticas (sin el modelo)

```bash
cd ~/InventaIO/nlp_agent
~/venvs/inventaio/bin/ruff check . ../scripts/preguntar_agente.py
~/venvs/inventaio/bin/python -m pytest -m "not llm" --cov=.      # 233 pruebas, umbral 90 %
```

| Archivo | Qué prueba |
| --- | --- |
| `tests/test_herramientas.py` | Las 8 herramientas contra el Core API simulado con las formas reales:<ul><li>parámetros enviados, filas, `data`, roles, T4 y T9;</li><li>compras con la parte de la sucursal (C16);</li><li>argumentos tolerantes</li></ul> |
| `tests/test_contexto.py` | Resolución de productos (código, nombre exacto, varias palabras y ambigüedad), categorías, sucursales y perfil |
| `tests/test_bucle.py` | Orden de los eventos e `id`; argumentos inválidos dos veces; 403 sin cortar la respuesta; herramienta inventada; inyección dentro de un resultado; registro sin argumentos |
| `tests/test_contrato_openapi.py` | Rutas, parámetros, enums y campos de respuesta contra `api/tests/postman/inventaio-core-api.openapi.yml` (T13) |
| `tests/test_chat.py` | El chat de punta a punta con una herramienta, el contrato v1 y los 13 mensajes |

### 4.2 A mano, con el agente en el equipo

Requisitos:
- el stack arriba: `docker compose up -d`, con `api`, `ml-service` y `db`;
- Ollama nativo: `bash scripts/ollama_wsl.sh iniciar`.

```bash
# Terminal 1: el agente con el código de la rama, contra el Core API y el Ollama del equipo
cd ~/InventaIO/nlp_agent
CORE_API_URL=http://localhost:8000 OLLAMA_BASE_URL=http://localhost:11434 \
  ~/venvs/inventaio/bin/python -m uvicorn main:app --port 8002

# Terminal 2: preguntas como cada usuario de prueba
cd ~/InventaIO
export INVENTAIO_CLAVE_PRUEBA=admin123          # la de api/scripts/seed_usuarios.py
~/venvs/inventaio/bin/python scripts/preguntar_agente.py --rol gerente "¿Qué productos están críticos en GLORIETA?"
```

El script muestra cada herramienta con su etiqueta y duración, las tablas tal como las recibirá el panel (INV-35), la respuesta y la línea de `done`. Con `--crudo` imprime los eventos SSE tal cual, que es lo que reenvía INV-36. La primera pregunta después de arrancar puede tardar 15 s más, mientras carga el modelo.

**Qué revisar (casos verificados el 18-oct):**

| Rol | Pregunta | Qué debe pasar | Medido |
| --- | --- | --- | --- |
| gerente | Hola, ¿qué puedes hacer? | Sin herramientas, 1 ronda | 1,6 s |
| gerente | ¿Qué productos están críticos en GLORIETA? | `consultar_inventario`, tabla «10 de 173», respuesta con 173 | 2,9 s |
| admin_sucursal LA 21 | ¿Cuántas alertas críticas hay en GLORIETA? | La herramienta termina con **código 403**; el modelo explica que solo ve LA 21, sin cifras | 2,3 s |
| admin_sucursal LA 21 | ¿Cuántas unidades de HUEVOS *UND voy a vender en las próximas tres semanas? | **Tarjeta** de LA 21 (1.567 unidades) | 2,1 s |
| gerente | ¿Cuál es la demanda esperada de arroz Carolina x 500 gramos? | La frase no es subcadena del nombre y el producto se resuelve igual (C4). Sin sucursal salen las **3** (T9): PRINCIPAL 197, LA 21 17 y GLORIETA 85 | 3,9 s |
| gerente | Pronostica con IA los productos próximos a agotarse en GLORIETA | `listar_alertas` con origen IA, `lenta`: «10 de 246» | 4,3 s |
| admin_bodega | ¿Cuántas compras urgentes hay? | `recomendar_compras`, `lenta`: «585 en total». En frío, unos 30 s | 3,2 s (caché caliente) |
| gerente | ¿Cuánta leche hay en PRINCIPAL? | Hoy responde «89 productos» sin aclarar (I9, INV-33) | 3,2 s |

Para INV-35, la misma pregunta con `--crudo` muestra el JSON exacto de cada evento.

### 4.3 Dentro del contenedor

Reconstruir la imagen con el código de la rama (pocos MB; revisar antes `df -h /mnt/c`). El 8002 no se publica, así que el script entra por stdin:

```bash
docker compose up -d --build nlp-agent
docker compose exec -T -e INVENTAIO_CLAVE_PRUEBA=admin123 nlp-agent python - \
  --agente http://localhost:8002 --core-api http://api:8000 \
  --rol admin_sucursal --sucursal "LA 21" "¿Qué productos están en estado crítico en mi sucursal?" \
  < scripts/preguntar_agente.py
docker compose logs nlp-agent --since 5m     # request_id, herramienta, estado y ms; nunca el texto
```

### 4.4 Con el modelo real (marca `llm`) y la medición

```bash
cd ~/InventaIO/nlp_agent
CORE_API_URL=http://localhost:8000 OLLAMA_BASE_URL=http://localhost:11434 INVENTAIO_CLAVE_PRUEBA=admin123 \
  ~/venvs/inventaio/bin/python -m pytest -m llm -v      # «hola» y una herramienta con los 3 roles

INVENTAIO_CLAVE_PRUEBA=admin123 ~/venvs/inventaio/bin/python -m evaluacion.correr \
  --modelo qwen3:8b --core-api http://localhost:8000     # 43 preguntas × 3, unos 15 min
~/venvs/inventaio/bin/python -m evaluacion.reporte evaluacion/resultados/<fecha>_local/qwen3_8b_gpu_real.jsonl
```

## 5. Criterios de aceptación y DoD

| CA | Estado |
| --- | --- |
| 1 (M) | Cumplido: 8 herramientas con descripción en español y parámetros en Pydantic |
| 2 (M) | Cumplido: rutas fijas del Core API con el token del usuario. Hay una prueba de que ninguna llama a ml_service |
| 3 (M) | Cumplido: resolución dentro de la herramienta, con `ambiguo` y hasta 5 candidatos. Que el modelo pregunte en «leche» es de INV-33 (I9) |
| 4 (M) | Cumplido: a lo sumo 10 filas, `total`, `conteo`, `fecha_dato` y cantidades por `texto_cantidad` |
| 5 (M) | Cumplido: 401, 403, 404, 422, 5xx, 503 y 504 vuelven al modelo como datos. Ante el 403 no inventa (verificado a mano y con 0 fugas en el v0) |
| 6 (M) | Cumplido: 3 rondas y una final, dentro de `LLM_TIMEOUT_S`, con 60 s por llamada |
| 7 (M) | Cumplido: `tests/test_contrato_openapi.py` corre en el CI |
| 8 (M) | Cumplido: los resultados van como JSON en el mensaje `tool` y nunca en la etiqueta. Hay prueba con instrucciones dentro de un nombre |
| 9 (S) | **Entregado**: una línea por llamada, sin argumentos |
| 10 (M) | Cumplido con el v0: 91 % de herramienta, pass^3 reportado, 0 fugas. Se repite con la v1 de INV-31 |
| 11 (C) | **No entregado**, como decía la ficha: el ciclo de herramientas no transmite llamadas parciales |
| 12 (M) | Cumplido: los tokens por ronda se miden (p95 2.310, máx. 2.583) y van en `done.tokens_prompt` |
| 13 (M) | Cumplido: argumentos como texto JSON, enums sin mayúsculas ni tildes, vacíos que se descartan y un argumento inválido que vuelve al modelo; al segundo, ronda sin herramientas. El `<think>` se filtra |

| DoD | Estado |
| --- | --- |
| 1 | Criterios (M) cumplidos; (S) entregado y (C) anotado |
| 2 | CI: ruff y 234 pruebas con 98 % de cobertura en local. Se confirma en GitHub con el push |
| 3 | Pruebas `llm` (5) en verde contra el modelo y el Core API reales. Las de integración de `api` y `ml_service` no cambian con esta historia |
| 4 | Conjunto v0 corrido sin cambios, metas cumplidas e informe en este documento |
| 5 | Seguridad: solo lectura, sin puertos nuevos, sin secretos (la clave de prueba va por variable de entorno). Sin texto en los registros, incluido el arreglo de I4 |
| 6 | Este documento, `INV-32-requerimientos.md` y N5 registrada (§1) |
| 7 | La herramienta correcta se midió con el criterio 10 |
| 8 | Pendiente: merge a `develop` con aprobación |
