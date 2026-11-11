# INV-67 · Spike: modelo de lenguaje en la nube · Requerimientos

| Campo | Valor |
| --- | --- |
| Jira | INV-67 «Spike: modelo de lenguaje en la nube» · Sprint 7 · Release 3 · límite 13-nov |
| Depende de | D26 (aprobada el 10-nov: las preguntas y los resultados de las herramientas pueden ir a Bedrock dentro de la cuenta) |
| Bloquea a | INV-34 (qué modelo se despliega en staging) · Alimenta a INV-40 (ajustes de prompts) |
| Rama | `feature/INV-67-bedrock`, desde `develop` (`abb93dc`), en el worktree `~/InventaIO-wt/INV-67` |

Revisión del 11 de noviembre de 2026 contra `develop` y la documentación de AWS. Las decisiones B1 a B3 las tomó el usuario ese día en un formulario; las demás son técnicas y siguen de los hallazgos.

## 1. Historia de Jira

> Como responsable del agente, quiero decidir con evidencia dónde corre el modelo de lenguaje en la nube, para desplegar a Vera sin perder la calidad medida ni salirme del presupuesto.

Seis criterios: cuatro (M) y dos (S). Fuera de alcance: ajustar los prompts al modelo nuevo (INV-40), desplegarlo y cambiar el compose de producción (INV-34), la GPU si la cuota no llega y cambiar el proveedor del stack local, que sigue en Ollama.

## 2. Contraste con lo ya construido y con AWS

| # | Hallazgo | Consecuencia |
| --- | --- | --- |
| K1 | La ficha de Qwen3-32B en Bedrock (11-nov) lista el llamado a herramientas del lado del cliente para la API compatible con OpenAI (Chat Completions), pero no para Converse, que era la API que nombraba la historia | El adaptador usa Chat Completions (B1) |
| K2 | Chat Completions existe en dos superficies con el mismo motor: `bedrock-runtime.{región}.amazonaws.com/openai/v1` (firma SigV4 con el servicio `bedrock`, permisos `bedrock:InvokeModel` e `InvokeModelWithResponseStream`) y `bedrock-mantle.{región}.api.aws/v1` (servicio `bedrock-mantle`, permiso `bedrock-mantle:CreateInference`). La ficha pone las herramientas de este modelo bajo `bedrock-mantle` | Las dos se configuran con `BEDROCK_ENDPOINT` (B6). Se empieza por `runtime`, la recomendada; la sonda dice si hace falta `mantle` |
| K3 | El modelo está en la región en us-east-1 y sa-east-1. Tiene 32K de contexto y 8K de salida, y su ciclo de vida dice «EOL no antes del 29-abr-2026», aunque sigue activo | El CA 6 se puede medir. El riesgo de legado queda declarado |
| K4 | `ClienteOllama` lo crean `main.py` y `evaluacion/correr.py`. El arnés usa además `/api/tags` y `/api/ps` de Ollama para la línea `meta` | Una función `crear_cliente` elige el proveedor. El arnés no llama a Ollama con `--proveedor bedrock` (B12) |
| K5 | El bucle guarda las llamadas como `{"id"?, "function": {"name", "arguments": dict}}` y los resultados como `{"role": "tool", "tool_name", "content"}`, sin `tool_call_id`. Chat Completions exige `type`, `id`, los argumentos como texto JSON y el `tool_call_id` de cada resultado | La traducción vive en el adaptador: el agente no cambia (B7, CA 5) |
| K6 | `Resumen` solo guarda el máximo de tokens de entrada por ronda (`tokens_prompt_max`), y el costo necesita la suma | El adaptador acumula su consumo y el arnés lo lee antes y después de cada pregunta (B11) |
| K7 | El Core API consulta `/ready` del agente para saber si el chat está disponible (X7 de INV-36) | Con Bedrock, `/ready` no puede llamar al modelo en cada consulta: revisa las credenciales (B10) |
| K8 | `chat/router.py` manda al Core API el `codigo` de `ErrorLLM` y el Core API lo traduce para el usuario | El adaptador usa solo los códigos que ya existen (B8) |
| K9 | No hay AWS CLI ni boto3 en el entorno. Las imágenes fijan todas sus dependencias y el CI pasa `pip-audit` | botocore (solo para la firma y la cadena de credenciales) entra fijado con sus transitivas (B4) |
| K10 | La página oficial de precios no mostró Qwen3-32B en us-east-1 (11-nov). La ruta estimó US$0,15 por millón de entrada y US$0,60 de salida, con fuentes de terceros | El precio es configurable y se reconcilia con la factura (DoD 6) |

## 3. Decisiones

| # | Decisión | Origen |
| --- | --- | --- |
| B1 | Adaptador sobre Chat Completions, no sobre Converse (K1) | Usuario, 11-nov |
| B2 | Se corren el v1 completo (61) y el holdout-3 (15), 3 corridas cada uno, con las herramientas reales del Core API local. Bedrock se elige si no empeora el acierto ni la herramienta frente a la línea base (la diferencia pareada no es negativa con significancia) y si su p95 ≤ 30 s | Usuario, 11-nov (la regla de INV-33) |
| B3 | Credenciales locales: un usuario IAM solo para el spike (`inventaio-spike-bedrock`) con política mínima, en el perfil `inventaio-spike` de `~/.aws/credentials`. Su llave se desactiva al cerrar (DoD 7). INV-34 usará el rol de la EC2 | Usuario, 11-nov |
| B4 | La firma es SigV4 con botocore, que también resuelve la cadena estándar de credenciales (variables, `AWS_PROFILE`, rol de la EC2). No se usan claves de API de Bedrock: no sirven para el rol de INV-34 | Técnica |
| B5 | `LLM_PROVEEDOR` (`ollama` por defecto, o `bedrock`). Con `bedrock` y sin `LLM_MODELO` explícito, el modelo es Qwen3-32B con el id de su superficie: `qwen.qwen3-32b-v1:0` en `runtime` y `qwen.qwen3-32b` en `mantle` (en `runtime`, el corto da «The provided model identifier is invalid»: sonda del 11-nov) | Técnica |
| B6 | `BEDROCK_REGION` (`us-east-1`) y `BEDROCK_ENDPOINT` (`runtime` o `mantle`): de ahí salen la URL y el servicio de la firma | Técnica (K2) |
| B7 | La traducción del formato de Ollama al de Chat Completions vive en el adaptador: `type: function`, un `id` cuando falta, los argumentos como texto JSON y el `tool_call_id` de cada resultado, emparejado en orden con las llamadas de la ronda | Técnica (K5) |
| B8 | Errores con los códigos que ya existen: 400 y 422 → `solicitud_invalida`; 404 → `modelo_no_descargado`; 401, 403, 429 y 5xx → `llm_no_disponible`, con el motivo en el mensaje; tiempo → `tiempo_agotado`; respuesta rota → `respuesta_invalida` | Técnica (K8) |
| B9 | Reintento solo ante 429 y 503, hasta 2 veces (1 s y 2 s), y solo antes de recibir respuesta: nunca a mitad del streaming | Técnica: una cuenta nueva tiene cuotas bajas y un 429 en la medición contaría como fallo del modelo |
| B10 | Con Bedrock, `/ready` no llama al modelo: `version()` devuelve `bedrock {endpoint} {región}` y `modelo_disponible()` dice si hay credenciales. Si el modelo no existe, el primer chat responde `modelo_no_descargado`. El contrato de `/ready` con el Core API no cambia | Técnica (K7) |
| B11 | El adaptador acumula los tokens de entrada y salida (`uso`). El arnés guarda por pregunta `tokens_entrada`, `tokens_salida` y `costo_usd`, con `BEDROCK_PRECIO_ENTRADA` y `BEDROCK_PRECIO_SALIDA` (US$ por millón, 0,15 y 0,60 por defecto) | Técnica (K6, K10) |
| B12 | Arnés: `--proveedor bedrock` y `--region`. Con Bedrock no consulta `/api/tags` ni `/api/ps`, el modo es `nube` y la línea `meta` lleva el proveedor, el endpoint, la región y los precios | Técnica (K4) |
| B13 | `evaluacion/comparar.py` compara una corrida con su línea base pregunta por pregunta (acierto y herramienta, con intervalo por bootstrap pareado), más p95 y costo, y aplica la regla de B2 | Técnica (CA 2 y CA 3) |
| B14 | `BEDROCK_CUERPO_EXTRA` (JSON) agrega campos al cuerpo de la petición. Existe porque la ficha no documenta cómo apagar el razonamiento de Qwen3 en Chat Completions: si la sonda lo ve encendido, se apaga por configuración, sin tocar el código | Técnica |
| B15 | Pruebas reales con la marca `bedrock`: se saltan sin credenciales y nunca corren en el CI | Técnica |
| B16 | Tope de costo en el arnés (`--tope-usd`, US$2 por corrida por defecto): con el calentamiento incluido, la corrida se detiene al llegar, queda incompleta y no se registra en MLflow. El presupuesto de AWS solo avisa; el tope frena | Pedido del usuario, 11-nov |

## 4. Interfaz

### 4.1 Variables nuevas del agente

| Variable | Valor por defecto | Para qué |
| --- | --- | --- |
| `LLM_PROVEEDOR` | `ollama` | `ollama` o `bedrock` |
| `BEDROCK_REGION` | `us-east-1` | Región de Bedrock y de la firma |
| `BEDROCK_ENDPOINT` | `runtime` | `runtime` (`bedrock-runtime…/openai/v1`) o `mantle` (`bedrock-mantle…/v1`) |
| `BEDROCK_PRECIO_ENTRADA`, `BEDROCK_PRECIO_SALIDA` | 0,15 y 0,60 | US$ por millón de tokens, para el costo del arnés |
| `BEDROCK_CUERPO_EXTRA` | `{}` | Campos que se agregan a cada petición (B14) |
| `AWS_PROFILE` y la cadena estándar de AWS | — | Credenciales. Nunca en el repositorio ni en el compose |

`LLM_MODELO`, `LLM_TEMPERATURA`, `LLM_TOP_P`, `LLM_SEMILLA`, `LLM_TOPE_RESPUESTA` (→ `max_tokens`) y `LLM_TIMEOUT_S` valen para los dos proveedores. `LLM_NUM_CTX`, `LLM_KEEP_ALIVE` y `OLLAMA_BASE_URL` solo para Ollama.

### 4.2 Arnés

```bash
cd nlp_agent
AWS_PROFILE=inventaio-spike INVENTAIO_CLAVE_PRUEBA=… python -m evaluacion.correr --proveedor bedrock \
    --conjunto v1 --core-api http://localhost:8000 --verificar --entorno nube-us-east-1 --mlflow --historia INV-67
python -m evaluacion.comparar --base evaluacion/resultados/2026-10-24_local-integracion-22oct-v1/qwen3_8b_gpu_real.jsonl \
    --nuevo evaluacion/resultados/<fecha>_nube-us-east-1/qwen.qwen3-32b-v1_0_nube_real.jsonl
```

Líneas base: `2026-10-24_local-integracion-22oct-v1` para el v1 y `2026-10-24_local-holdout-3-base-v2-1` para el holdout-3 (el agente integrado, con el comportamiento del 22-oct).

## 5. Criterios de aceptación

| CA | Cómo se cumple |
| --- | --- |
| 1 (M) | El usuario pide 4 vCPU de «Running On-Demand G and VT instances» en us-east-1. El número de caso y el estado van a la decisión y a Jira |
| 2 (M) | Sonda de 3 preguntas, luego v1 y holdout-3 ×3 con `--proveedor bedrock --verificar --core-api`. `comparar.py` contra las dos líneas base |
| 3 (M) | D-R3 y D26 en «Modelos y decisiones técnicas» de Confluence y en `docs/RUTA-AVANCE-3.md` §5 y §8, con la aprobación del usuario |
| 4 (S) | La lista de ajustes sale de las fallas de la corrida y va a INV-40 |
| 5 (M) | `ClienteBedrock` cumple `ClienteLLM`; `crear_cliente` lo elige con `LLM_PROVEEDOR`; el bucle, los prompts y las herramientas no cambian. Credenciales de la cadena estándar |
| 6 (S) | Sonda de 15 preguntas (el holdout-3, una corrida) en sa-east-1, comparada en p50 y p95 con la misma sonda en us-east-1 |

## 6. Casos de prueba (sin AWS, en el CI)

| # | Caso |
| --- | --- |
| P1 | `chat` con texto: cuerpo de Chat Completions (modelo, temperatura, `max_tokens`, sin `stream`), texto filtrado y métricas con los tokens de `usage` |
| P2 | `chat` con llamadas: argumentos como texto JSON y como objeto; argumentos que no son JSON quedan como error de la llamada, igual que con Ollama |
| P3 | Traducción de mensajes: `tool_calls` con `type` e `id`, argumentos como texto, `tool_call_id` emparejado en orden, sin `tool_name`; varias rondas |
| P4 | `chat_stream` con texto en fragmentos, `<think>` filtrado, campo de razonamiento descartado y marcado, y el fragmento final con métricas y tiempo al primer token |
| P5 | `chat_stream` con llamadas repartidas en fragmentos (nombre, luego argumentos por partes): una sola llamada, en su propio fragmento, antes del final |
| P6 | Errores: 400, 401, 403, 404, 422, 429 y 500 → los códigos de B8; error dentro del stream; stream sin final → `respuesta_invalida`; tiempo agotado; red caída |
| P7 | Reintento: 429 y 503 se reintentan hasta 2 veces y luego fallan; 500 no se reintenta |
| P8 | Firma: la petición lleva `Authorization` SigV4 con el servicio y la región correctos, `x-amz-date` y, con credenciales temporales, `x-amz-security-token`. Credenciales ficticias |
| P9 | Sin credenciales: `modelo_disponible` da `False` y `chat` da `llm_no_disponible`, sin llamar a la red |
| P10 | `version()`, `uso` acumulado y `costo_usd` |
| P11 | Configuración: `LLM_PROVEEDOR=bedrock` cambia el modelo por defecto si `LLM_MODELO` no se dio; un `LLM_MODELO` explícito se respeta; `mantle` cambia la URL y el servicio; proveedor desconocido → error de validación |
| P12 | `crear_cliente` y `main.py`: el agente arranca con cualquiera de los dos y `/ready` responde con Bedrock sin llamar al modelo |
| P13 | Arnés: `--proveedor bedrock` con Bedrock y Core API simulados escribe la `meta` sin Ollama, el modo `nube` y los tokens y el costo por pregunta |
| P14 | `comparar.py`: diferencias pareadas, p95, costo y el veredicto de B2 en los casos que cumple y no cumple |
| P15 | Las pruebas de Ollama siguen igual (regresión) |

Reales (marca `bedrock`, en local con el perfil): una pregunta de texto, una con herramienta y el streaming.

## 7. Ruta de implementación

1. Configuración (`core/config.py`) y `llm/bedrock.py` con P1 a P11.
2. `llm/proveedor.py` (`crear_cliente`) y `main.py` (P12).
3. Arnés: `correr.py`, `arnes.py` (costo por pregunta), `reporte.py` y `registro_mlflow.py` (costo y proveedor) y `comparar.py` (P13 y P14).
4. `requirements.txt` con botocore fijado; ruff, pytest con cobertura ≥ 90 % y `pip-audit` como en el CI.
5. Documentación: variables en `docs/NLP-AGENT.md`, `.env.example`.
6. Con el perfil del usuario: sonda, corridas, comparación, decisión, lista para INV-40, PR.

## 8. Definition of Done

La de Jira (9 casillas). Además: revisión con grep de credenciales (`AKIA`, `aws_secret_access_key`, `AWS_BEARER_TOKEN_BEDROCK`) antes de cada push, y ningún archivo de resultados con ventas en pesos (`evaluacion/privacidad.py`).

## 9. Riesgos

- Las herramientas de Qwen3-32B en Bedrock pueden comportarse distinto que en Ollama. Primero la sonda. Si fallan en `runtime`, se prueba `mantle` (necesita `bedrock-mantle:CreateInference`). Si fallan en los dos y el usuario lo aprueba, se mide Qwen3 235B A22B 2507, que en us-east-1 y sa-east-1 está solo en `mantle`.
- Cuotas bajas en una cuenta nueva: reintento corto (B9) y, si no alcanza, solicitud de aumento.
- El p95 medido desde Colombia incluye la red hasta la región. En staging la llamada sale de la misma región, así que el número del spike es pesimista.
- El precio por defecto viene de terceros: se reconcilia con la factura antes de cerrar.

## 10. Resultados (11-nov)

Corridas con el commit `cc09cf9` limpio, contra el Core API local (stack 8000) y con la verificación de INV-33. Detalle y fuentes en `docs/RUTA-AVANCE-3.md` §5.1; corridas en MLflow con la etiqueta `historia = INV-67`.

| CA | Estado |
| --- | --- |
| 1 (M) | **En curso.** El usuario pidió el 11-nov 4 vCPU de «Running On-Demand G and VT instances» en **us-east-2**: estado *Pending*, sin caso de soporte (AWS lo abre solo si la revisión es manual). La cuota es por región: se pide también en **us-east-1**, la región del staging, por si se activa el plan A. No hace falta para el staging (D-R3); sirve además para el candidato de INV-74 |
| 2 (M) | **Hecho.** v1 ×3 (183 preguntas) y holdout-3 ×3 (45) en us-east-1. Acierto 84 % y 64 %, herramienta 89 % y 82 %, fidelidad 100 %, cero fugas, p95 6,9 y 5,4 s, US$0,0011 por pregunta. Comparación pareada con `comparar.py` |
| 3 (M) | Decisión del usuario (11-nov): **D-R3 = opción D, Qwen3-32B en Bedrock, us-east-1**. Registrada en la ruta (§8); falta Confluence |
| 4 (S) | **Hecho:** la lista para INV-40 está abajo |
| 5 (M) | **Hecho:** `ClienteBedrock` con `LLM_PROVEEDOR`, sin cambios en el agente; credenciales del perfil `inventaio-spike` |
| 6 (S) | Pendiente: sa-east-1 respondió 403 («account is currently being verified») a las peticiones de tamaño real |

**Hallazgos de la sonda técnica:**
- En `bedrock-runtime`, el id corto (`qwen.qwen3-32b`) da «The provided model identifier is invalid»; vale el id con versión (B5).
- El razonamiento de Qwen3 viene apagado, así que B14 no hizo falta.
- `bedrock-mantle` firma con el servicio `bedrock-mantle` y funciona con Qwen3 235B.

**Lista de ajustes para INV-40 (CA 4).** Son las preguntas en que Qwen3-32B pierde frente al agente del 22-oct:

| # | Pregunta | Qué pasó | Ajuste |
| --- | --- | --- | --- |
| 1 | v1-22 (1 de 3) | Traslados «de GLORIETA a las demás»: pidió `direccion: hacia` | Ejemplos de dirección (desde/hacia) en la descripción de `recomendar_traslados` |
| 2 | v1-34 (1 de 3) | «Calendario de pedidos»: respondió de memoria | Reforzar «nunca de memoria» para el glosario |
| 3 | v1-43 (0 de 3) | «Últimos días»: inventó `dias: 7` en `listar_alertas` | Decir que no filtra por fecha en lugar de inventar argumentos |
| 4 | v1-46 (0 de 3) | Un saludo: llamó `historial_ventas` | Sin herramientas en la conversación social |
| 5 | h3-06 (0 de 3) | Varios turnos: no heredó la sucursal del turno anterior | Usar el contexto de los turnos previos en los argumentos |
| 6 | h3-10 (0 de 3) | «Lenteja»: listó todo en lugar de preguntar cuál | La regla de ambigüedad con productos genéricos |
| 7 | h3-01 (1 de 3) | Resumen de PRINCIPAL sin los datos esperados | Qué cifras lleva un resumen de inventario |

Las preguntas 5 a 7 fallan también con Qwen3 235B (sonda de INV-74): el ajuste es del prompt, no del tamaño del modelo.
