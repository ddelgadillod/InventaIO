# INV-31 · Conocimiento del agente y conjunto de referencia · Requerimientos

| Campo | Valor |
| --- | --- |
| Jira | INV-31 «RAG sobre la bodega», reencuadrada como «Conocimiento del agente y conjunto de referencia» (decisión 2 del documento de Sprint 6) · 8 SP · Sprint 6 · Release 2 · épica E10 NLP Agent |
| Depende de | INV-30 (servicio y spike, integrada en `9ba2051`) e INV-32 (catálogo v1, integrada en `4942662`) |
| Alimenta a | INV-33 (prompts: se miden con el v1) y la medición de las brechas del catálogo |
| Rama | `feature/INV-31-conocimiento-conjunto`, desde `develop` (`0c86bde`, con el fix de INV-64 y 65), en `~/InventaIO-wt/INV-31` |

Revisión del 20 de octubre de 2026 contra `develop`, la bodega (foto al 31-dic-2025) y el Core API.

## 1. Historia

> Como usuario del agente, quiero que me explique los términos y las reglas del negocio con su fuente y que diga «no tengo esa información» cuando no la tiene, y como equipo, queremos un conjunto de preguntas que el agente no ha visto para medir con números si cada cambio lo mejora.

Dos entregables (documento de Sprint 6, §INV-31):

- **(a) Conocimiento:** un RAG acotado sobre definiciones y políticas del negocio, con recuperación léxica (BM25) y la herramienta `buscar_en_glosario`.
- **(b) Conjunto de referencia v1:** con el que se mide todo el agente.

NL → SQL queda fuera (N1: saltaría los permisos del Core API); si se retoma, en el Release 3.

## 2. Contraste con el repositorio y los datos

| # | Hallazgo | Consecuencia |
| --- | --- | --- |
| K1 | `docs/GLOSARIO.md` (285 líneas) es del **pronóstico**: features, modelos, métricas. No explica semáforo, cobertura, punto de pedido ni calendario en lenguaje de negocio | Hay que escribir el glosario de negocio (`docs/GLOSARIO-NEGOCIO.md`): es trabajo real, como advertía la ficha |
| K2 | Las reglas del negocio están repartidas en el código y en los documentos de cada historia: semáforo en `api/core/semaforo.py` (crítico < 3 días de cobertura, bajo de 3 a 7, inconsistencia con stock negativo); alertas en INV-25 (D4); compras en INV-21 (pedidos los días 2 y 16, perecederos y frío cada martes y directo a la sucursal, 5 días hábiles de entrega, urgente ≤ 5 días, alta ≤ 10); traslados en INV-22; alertas de IA en INV-28 | El glosario las reúne con su fuente, y una prueba compara las cifras del glosario con las constantes del código para que no se desactualicen |
| K3 | El Dockerfile del agente se construye con el contexto `nlp_agent/`: los archivos de `docs/` no llegan a la imagen | El corpus que usa el agente tiene que vivir dentro de `nlp_agent/` (decisión G3) |
| K4 | El agente no tiene dependencias de búsqueda ni de embeddings, y la GPU de 8 GB la ocupa el modelo | BM25 en CPU, sin embeddings (criterio 2) |
| K5 | El catálogo v1 tiene 8 herramientas y ninguna de conocimiento | `buscar_en_glosario` es la novena (las brechas suman 2 más; ver §7) |
| K6 | El v0 (43 preguntas) ya se usó para ajustar INV-32: no sirve como examen | El v1 tiene que ser material nuevo (DoD 3) |
| K7 | Con el Core API real, el arnés no calificaba hechos: los del v0 son sintéticos (T17 de INV-32), y no detectó «hay 10» cuando eran 147 (I8) | El v1 trae hechos sintéticos y reales |
| K8 | INV-33 (otra sesión) pone las capacidades del asistente y el «acerca de» en el prompt, no en el glosario | Las preguntas v1-48 y v1-53 son de abstención: no llaman herramientas |

## 3. Lo ya entregado: el conjunto v1 (criterios 6 y 10)

Congelado el 20 de octubre (`f7f1e7e`, ajuste de la v1-29 en `d101361`).

**Origen.** 61 preguntas escritas por el usuario en una plantilla de bloques. Cada una se revisó contra la bodega y el Core API hasta cerrarla: productos que existen, respuestas posibles con las herramientas, sin copiar el v0. Los errores de tipeo se conservan porque así escriben los usuarios.

| Bloque | Preguntas | Qué mide |
| --- | --- | --- |
| A · Una herramienta | 23 | Herramienta y argumentos, hechos y fidelidad |
| B · Varios pasos | 7 | Encadenar herramientas (buscar → inventario, pronóstico frente a stock) |
| C · Glosario y capacidades que no tiene | 11 | Definiciones con su fuente; «no tengo esa información» sin inventar |
| D · Ambiguas | 5 | Pedir aclaración (además, v1-15 en el bloque A) |
| E · Abstención | 8 | No llamar herramientas: saludo, despedida, fuera de alcance |
| F · Adversariales | 7 | Otra sucursal u otra ubicación (403 real), datos sensibles, acciones de escritura, cambio de rol, instrucción escondida en los datos |

- **Cobertura:** 27 de gerente, 21 de administrador de sucursal (rotan las 3 sucursales) y 13 de administrador de bodega. Hay 13 de abstención (21 %).
- **Archivos** (`nlp_agent/evaluacion/conjuntos/v1/`):
  - `fuente.json`: lo que se congela (preguntas, llamadas esperadas, criterios y referencias a los hechos);
  - `preguntas.json`: lo que arma `evaluacion/construir_v1.py` (el arnés lo lee con el mismo esquema que el v0, más campos opcionales).
- **Resultados de herramientas** (criterio 10): `construir_v1` corre cada llamada contra el Core API real con el usuario de prueba del rol.
  - **Variante sintética (Colab, N9):** las cantidades se escalan por un factor fijo de cada pregunta (1,20 a 1,59) y las fechas pasan a ser relativas a la foto; la variante `colab` cambia sucursales y fecha.
  - **Hechos reales:** se guardan aparte, para calificar contra el Core API, porque los datos están congelados al 31-dic-2025.
- **Pendientes:** 21 preguntas esperan su herramienta y no se corren sin `--incluir-pendientes`:
  - 9 del glosario (esta historia);
  - 3 de la búsqueda tolerante;
  - 3 de traslados;
  - 2 del resumen de inventario;
  - 4 de ventas por periodo.

  Cuando cada herramienta llega, se vuelve a correr `construir_v1`.
- **Cómo se corre:**

```bash
cd nlp_agent
python -m evaluacion.correr --modelo qwen3:8b --conjunto v1                       # sintético, local
python -m evaluacion.correr --modelo qwen3:8b --conjunto v1 --variante colab      # para Colab
INVENTAIO_CLAVE_PRUEBA=… python -m evaluacion.correr --modelo qwen3:8b --conjunto v1 --core-api http://localhost:8000
INVENTAIO_CLAVE_PRUEBA=… python -m evaluacion.construir_v1                         # rearma resultados y hechos
```

**Primera medición real (20-oct, 4 preguntas).** v1-04, v1-46 y v1-54 pasan. En la v1-13 el modelo pidió el resumen de alertas sucursal por sucursal y sumó mal (dijo 5.856; son 4.452), y la fidelidad lo marcó. Es la falla «filtros que nadie pidió» más «sumas del modelo» que ataca INV-33.

## 4. Decisiones del glosario (formulario)

**Aprobadas por el usuario el 20-oct, todas en la opción recomendada:** G1 a G7.

| # | Tema | Propuesta recomendada | Alternativas |
| --- | --- | --- | --- |
| G1 | Contenido del corpus (criterio 1) | **`docs/GLOSARIO-NEGOCIO.md`, nuevo:** un término por sección, en lenguaje no técnico, con su regla, su fuente y un ejemplo con cifras de la foto (así el agente no inventa ejemplos, que la fidelidad marcaría). **Más** las reglas de INV-21, 22, 25 y 28 resumidas como políticas en el mismo archivo, y las secciones de `docs/GLOSARIO.md` que un usuario puede preguntar (calendario y estacionalidad, patrón de demanda) | Indexar los documentos de cada historia tal cual: son técnicos y largos, y la recuperación devolvería fragmentos que el modelo de 8B explica mal |
| G2 | Quién lo escribe | **Lo redacta esta sesión desde el código y los documentos, y el usuario lo valida término por término** (como las preguntas del v0) | El usuario lo escribe |
| G3 | Dónde vive el corpus del agente (K3) | **`docs/GLOSARIO-NEGOCIO.md` es la fuente legible.** Un script lo parte en fragmentos y escribe `nlp_agent/conocimiento/corpus.json` (id, título, fuente, texto), que va en la imagen. Una prueba del CI falla si el JSON no corresponde a los documentos (criterio 8) | Cambiar el contexto de la imagen a la raíz del repositorio (toca INV-24 y agranda la imagen); o escribir el glosario dentro de `nlp_agent/` y no en `docs/` |
| G4 | BM25 (criterio 2) | **Implementación propia** (unas 60 líneas), sin dependencias: minúsculas, sin acentos, palabras vacías del español y plurales simples. k1 = 1,5 y b = 0,75. k = 3 fragmentos | `rank-bm25` (una dependencia más que congelar y auditar, para lo mismo) |
| G5 | «No tengo esa información» (criterio 4) | **Umbral de puntaje** calibrado con las preguntas del bloque C: debajo de él, la herramienta devuelve `{"resultado": "sin_resultados", "indicacion": "Di que no tienes esa información; no la inventes."}`, igual que `no_encontrado` en los productos | Que el modelo decida con los 3 fragmentos siempre (inventa más) |
| G6 | Citar la fuente (criterio 3) | Cada fragmento trae `fuente` («Glosario de negocio · Semáforo», «Política de compras, INV-21») y la herramienta agrega `indicacion: "Cita la fuente"`, como ya hace con la ambigüedad. No toca el prompt, que es de INV-33 | Una regla nueva en el prompt (choca con la reescritura de INV-33) |
| G7 | hit@3 ≥ 0,8 (criterio 7, S) | **Consultas de recuperación** con su fragmento esperado: las 8 definiciones del v1 más 2 o 3 paráfrasis por término (unas 30), en `nlp_agent/conocimiento/consultas_hit3.json`, con prueba en el CI | Medir solo con las 8 del v1 (con 8, el 0,8 es una sola falla) |

## 4b. Trazabilidad de los experimentos en MLflow (agregado el 21-oct)

El usuario pidió llevar en MLflow la trazabilidad del v0, del v1 y de lo que siga, **dentro de esta historia** (no como tarea aparte) y **en local, en WSL**.

| # | Decisión |
| --- | --- |
| M1 | **Servidor local en WSL:** `scripts/mlflow_wsl.sh`. Escucha solo en `127.0.0.1:5000`, con la base en SQLite y los artefactos en `~/.local/mlflow`, fuera del repositorio. Los runs del modo real guardan respuestas con datos reales (D22, N9): el script de registro rechaza cualquier servidor que no sea local |
| M2 | **MLflow no va en la imagen ni en el CI:** está en `nlp_agent/requirements-evaluacion.txt` (mlflow 3.17.2), igual que en la etapa de ML, donde MLflow es trazabilidad y no servicio (INV-20). Las pruebas del CI usan un cliente simulado; la marca `mlflow` prueba contra un MLflow real en SQLite temporal |
| M3 | **Un run por archivo de resultados** (modelo, modo, conjunto y entorno), en un experimento por conjunto: `agente-conjunto-v0` y `agente-conjunto-v1`, para comparar solo corridas sobre las mismas preguntas |
| M4 | **Qué se registra:** <br>• **parámetros:** modelo y digest, Ollama, modo, contexto, entorno, datos (sintético, colab o real) y huellas del conjunto, el catálogo y el prompt; <br>• **métricas:** las del reporte, más el acierto por bloque y por tipo; <br>• **artefactos:** el `.jsonl`, el reporte y una tabla por pregunta; <br>• **etiquetas:** `historia` (la HU que produjo la corrida) y `archivo_sha256` (no se registra dos veces) |
| M5 | **Prompts en el registro de prompts de MLflow** (`agente-prompt-spike` y `agente-prompt-sistema`), ligados a cada run cuya huella coincide con el prompt actual. Las corridas viejas con otro prompt quedan solo con la huella |
| M5b | **Runs documentados para comparar:** <br>• cada run lleva una descripción (métricas frente a metas, bloques, comparación con la línea base, fallas, advertencias, cómo reproducirlo); <br>• métricas de comparación pareada con la línea base de su conjunto y datos (`base_*`); <br>• si cumple cada meta y la tasa de cada criterio; <br>• el conjunto como dataset; <br>• `fallas.md` con el detalle de cada pregunta que falla. <br>Cada experimento tiene una descripción de cómo leerlo |
| M6 | **Historial cargado el 21-oct:** 17 runs del v0 (spike de INV-30, local y Colab; las dos corridas reales de INV-32) y 2 del v1 (esta historia) |

```bash
bash scripts/mlflow_wsl.sh iniciar                                   # http://127.0.0.1:5000
cd nlp_agent
python -m evaluacion.correr --modelo qwen3:8b --conjunto v1 --mlflow --historia INV-33
python -m evaluacion.registro_mlflow evaluacion/resultados/<carpeta>/*.jsonl --historia INV-xx   # Colab o corridas viejas
```

**Lo que cambia en las historias que siguen:**

| Historia | Ajuste |
| --- | --- |
| INV-33 (prompts) | Se mide con el v1 (49 preguntas activas), contra el Core API y en sintético, con `--mlflow --historia INV-33`. Cada versión del prompt (`v2/`) se registra en el registro de prompts. La línea base es la del 21-oct (acierto 65 %, herramienta 82 %). **Fase 2 de MLflow:** trazas por pregunta (rondas del modelo y llamadas a herramientas) para ver por qué falla cada una |
| Brechas del catálogo (dentro de INV-33, decidido el 21-oct) | Búsqueda tolerante, `resumen_inventario`, `recomendar_traslados` e `historial_ventas` ampliado. Al terminar cada herramienta: reconstruir el v1 (`construir_v1`), activar sus preguntas y registrar la corrida con `--historia INV-33`. Cierran cuando las 12 preguntas pendientes del v1 pasen |
| INV-35 e INV-36 | Sin cambios: MLflow no toca el chat ni el agente en producción. El agente no registra conversaciones de usuarios |
| Sprint 7 o Release 3 | Opcional: evaluadores de MLflow GenAI sobre la calificación propia, y medir en MLflow la GPU en la nube (D26) |

## 5. Entradas, salidas e interfaz

**`buscar_en_glosario(consulta: str)`.** Solo lectura, sin Core API (lee el corpus en memoria).

```json
{"resultado": "encontrado", "total": 2,
 "fragmentos": [{"id": "semaforo", "titulo": "Semáforo", "fuente": "Glosario de negocio · Semáforo",
                 "texto": "…"}],
 "indicacion": "Responde con estos fragmentos y cita la fuente."}
```

**Archivos nuevos:**
- `docs/GLOSARIO-NEGOCIO.md`;
- `nlp_agent/conocimiento/` (`corpus.json`, `bm25.py`, `construir.py`, `consultas_hit3.json`);
- la herramienta en `herramientas/catalogo.py`;
- `docs/PLN-conjunto-referencia.md` (criterio 11).

## 6. Criterios de aceptación

| CA | Cómo se cumple |
| --- | --- |
| 1 (M) | Corpus en fragmentos con id y fuente desde `docs/GLOSARIO-NEGOCIO.md` (G1, G3) |
| 2 (M) | BM25 propio, k = 3, sin embeddings; la sección «Cómo agregar embeddings» en `docs/NLP-AGENT.md` |
| 3 (M) | `buscar_en_glosario` devuelve fragmentos con su fuente y pide citarla (G6); el v1 lo mide en el bloque C |
| 4 (M) | Umbral → `sin_resultados` (G5); v1-39 y v1-40 lo miden |
| 5 (M) | El agente sigue sin `POSTGRES_*` ni SQL: la prueba de INV-30 que lo verifica sigue pasando |
| 6 (M) | **Hecho:** v1 con 61 preguntas (§3) |
| 7 (S) | hit@3 ≥ 0,8 con unas 30 consultas (G7) |
| 8 (M) | Reconstrucción determinista: misma fuente → mismo `corpus.json` y mismo orden de resultados (prueba) |
| 9 (C) | NL → SQL: fuera (N1) |
| 10 (M) | **Hecho:** variante sintética y colab, hechos reales aparte (§3) |
| 11 (M) | `docs/PLN-conjunto-referencia.md`: el diseño (Beck, BFCL, τ-bench pass^k, Miller), el v0 y el v1, cómo se arma, se corre y se recalifica, y la primera medición del v1 |
| 12 (nuevo, 21-oct) | Trazabilidad en MLflow local (§4b): cada corrida del v0 y del v1 es un run con parámetros, métricas, artefactos y prompt; el historial está cargado y `correr --mlflow` registra las nuevas |

## 7. Ruta

1. **Hecho:** el conjunto v1 (§3).
2. El glosario de negocio, redactado desde el código y validado por el usuario (G2).
3. El corpus, el BM25 y la herramienta, con sus pruebas (criterios 1 a 5, 7 y 8).
4. Reconstruir el v1: se activan las 9 preguntas del glosario. Medición completa en local con qwen3:8b: sintética y real.
5. `docs/PLN-conjunto-referencia.md` y la sección del agente en `docs/NLP-AGENT.md`.
6. Merge a `develop` con aprobación del usuario.

**Después de INV-31** sigue el catálogo. El 21-oct el usuario decidió que las brechas van **dentro de INV-33**, sin HU nueva y sin cambiar sus puntos. Cierran cuando pasen las 12 preguntas pendientes del v1. Son:
- búsqueda tolerante (abreviaturas, orden de las palabras, código en el inventario);
- `resumen_inventario`;
- `recomendar_traslados`;
- `historial_ventas` ampliado (periodo, agrupación y valor; cambia `/api/reportes/ventas`).

Con `buscar_en_glosario` quedan 11 herramientas. El usuario aprobó superar el límite de 10 del criterio 1 de INV-32 si el v1 muestra que el acierto al elegir no baja (≥ 85 %). Hay que corregir la ficha en Jira.

## 8. Fuera de alcance y riesgos

**Fuera de alcance:**
- NL → SQL (Release 3);
- embeddings;
- las capacidades y el «acerca de» del asistente (prompt, INV-33);
- las brechas del catálogo (siguiente rama).

| Riesgo | Mitigación |
| --- | --- |
| El glosario se desactualiza frente al código (umbral del semáforo, días de pedido) | Prueba que compara las cifras del glosario con las constantes de `api/core/semaforo.py` y de las políticas de INV-21 |
| BM25 no encuentra sinónimos («rojo» frente a «crítico») | Cada término incluye las palabras que usan los usuarios («rojo», «amarillo», «se acaba»), y hit@3 lo mide |
| Cifras reales en un repositorio público | Son conteos y existencias agregados, como los que ya publican los documentos de INV-25 a INV-32. Los nombres de productos ya eran reales en el v0 |
| La API del contenedor monta la copia principal (`~/InventaIO/api`), que usa otra sesión | Antes de reconstruir, comprobar que su `api/` es igual a la de `develop` (`git diff develop -- api`); lo era el 20-oct |
