# Viabilidad del RAG y mejoras a los modelos, con el Release Plan corregido

| Campo | Valor |
| --- | --- |
| Estado | **Aprobado y aplicado en Jira el 28-oct-2026** (INV-72 a INV-75 e INV-63 renombrada); complementa `docs/RUTA-AVANCE-3.md` (§7, Release Plan revalidado). Los textos de los releases (§5) los cambia la persona en Jira |
| Preguntas | ¿Es viable ampliar el RAG de Vera y de qué forma? ¿Qué mejoras o adiciones a los modelos conviene planear? ¿Qué dicen hoy los releases de Jira frente a lo que de verdad se construyó? |
| Fuentes | `docs/INV-31-requerimientos.md` y `docs/NLP-AGENT.md` (conocimiento del agente), `models/nivel1_metadata.json` y `docs/INV-20-ml-service.md` (motor en producción), `docs/FIX-EDA-MODELADO-NIVEL1.md`, `docs/PREREGISTRO-HOLDOUT-2026.md`, el spike de INV-30 y Jira al 28-oct |

## 1. Qué hay hoy

**Conocimiento de Vera (INV-31, «RAG acotado»).**
- 68 fragmentos del glosario de negocio y de modelos (`docs/GLOSARIO.md` → `nlp_agent/conocimiento/corpus.json`).
- Búsqueda BM25 propia, sin embeddings ni base vectorial, servida por la herramienta `buscar_en_glosario`.
- hit@3 de 1,0 en 60 consultas, y «no tengo esa información» cuando la consulta no pasa el umbral de cobertura (0,6).
- Fuera de alcance por decisión: los embeddings (la GPU de 8 GB la ocupa el modelo) y el NL→SQL. Este último lo reemplazaron las herramientas de solo lectura, que heredan los permisos del Core API (retrospectiva del Sprint 5).

**Motor de pronóstico en producción** (`models/nivel1_metadata.json`, política del 24-sep):

| Rama | Modelo servido | Por qué |
| --- | --- | --- |
| `intermitente` (257.894 filas de entrenamiento) | **LightGBM cuantílico relativo** (sobre la demanda dividida por su nivel), con recalibración conformal por estrato de volumen | Mejoró el WAPE frente a la media móvil (+5,1 % [+4,5; +5,8]) en la evaluación walk-forward con purge |
| `suave_no_perecedero` y `suave_perecedero` | **Base simple** (`baseline_cuantil`): q50 = media móvil; cuantil de negocio = razón empírica por estrato | Ningún modelo de ML la superó de forma confirmable (el fold 5 contradijo la mejora) |

LightGBM no es el núcleo de todo el motor: sirve solo la rama intermitente. El resto es la base simple calibrada.

**Modelo de lenguaje:** qwen3:8b, autoalojado en Ollama (decisión D22). Las métricas que siguen son del spike y del conjunto v1; la latencia es de la GPU local (RTX 5050, 8 GB).
- herramienta correcta, 82–86 %;
- fidelidad, 98–100 %;
- 0 fugas;
- p95 local de 10 a 15 s.

En la L4 de Colab, qwen3:14b acertó el 72 % frente al 63 % del 8b, pero necesita unos 10,5 GB de VRAM.

## 2. RAG: opciones y viabilidad

**Sondeo del 28-oct.** Se probó el BM25 de Vera, sin ningún cambio, sobre la guía del sistema (Parte II: 50 páginas y 133 fragmentos de unas 150 palabras). Las 15 preguntas eran de «cómo hago» y «por qué esta cifra», y cada una tenía su sección esperada:

| Medida | Resultado |
| --- | --- |
| hit@3 sobre la guía | **11 de 15** |
| Pasan el umbral de cobertura | 13 de 15 |
| Respondidas con el glosario actual | 6 de 15, y no siempre con la sección correcta |
| Fallas | Sinónimos y paráfrasis: «celular» frente a «pantallas pequeñas», «trasladar» frente a «traslados», «fecha de los datos» frente a «foto de inventario», «cambiar la contraseña» |

Es un sondeo: las preguntas las escribió esta revisión, hay una sola corrida y la guía no está curada. Sirve para decidir si vale la pena, no para aceptar una historia. El script está en el scratchpad de la sesión: lee el PDF local, que no está en el repositorio. La historia de la §4 lo convierte en una prueba versionada.

| Opción | Qué es | Viabilidad | Valor | Recomendación |
| --- | --- | --- | --- | --- |
| R-A. Ampliar el corpus | La guía del sistema y el manual por rol (INV-42), curados en fragmentos cortos con su campo `tambien` (sinónimos), para que Vera responda «cómo uso la aplicación» y «por qué esta cifra» | **Alta**: el mismo BM25 ya acierta 11 de 15 sin ajustes | **Alto**: hoy Vera no sabe responder sobre su propia aplicación, y es lo primero que preguntan quienes la prueban | **Sí** |
| R-B. Búsqueda híbrida | BM25 más embeddings, combinados (`docs/NLP-AGENT.md` ya describe cómo): un modelo pequeño en CPU (por ejemplo `nomic-embed-text`, unos 270 MB) o Titan Embeddings en Bedrock | **Alta**: con menos de 500 fragmentos no hace falta una base vectorial | **Medio**: corrige las paráfrasis del sondeo; el glosario ya está en 1,0 | **Sí, si mejora el hit@3 medido**; si no, sinónimos curados en `tambien` |
| R-C. NL→SQL | El modelo escribe SQL contra la bodega | **Baja** | **Negativo**: se salta los permisos por rol y la fidelidad de cifras que hoy garantizan las herramientas | **No**: queda descartado y documentado |
| R-D. Base vectorial (pgvector, OpenSearch) | Índice externo | Innecesaria al tamaño actual | Bajo | **No**, hasta tener miles de fragmentos |

**Riesgos de R-A y R-B, y cómo se cubren:**
- La guía tiene cifras de una fecha. Cada fragmento lleva su fecha y Vera cita la fuente, como ya hace el glosario.
- El repositorio es público. El corpus lleva solo cifras agregadas, que es el mismo criterio aceptado en INV-31.
- El modelo de 8B explica mal los fragmentos largos. Por eso se curan fragmentos cortos, que fue la razón de G1 en INV-31.
- La guía se desactualiza si cambia la aplicación. Una prueba compara las cifras del corpus con las constantes del código, como ya existe para el glosario.

## 3. Mejoras y adiciones a los modelos

**Pronóstico:**

| # | Mejora | Estado | Viabilidad | Recomendación |
| --- | --- | --- | --- | --- |
| M-1 | Evaluar el motor completo con el holdout 2026 (reglas preregistradas R1 a R4, las tres ramas) | Es INV-63 (Sprint 7). Su título dice «segmento suave-perecedero», pero sus criterios ya aplican R1 a R4 | Depende de cargar las ventas de 2026 (al menos 8 orígenes) | **Renombrar INV-63** para que diga lo que hace; reestimar en el Planning si la carga de 2026 trae formatos nuevos |
| M-2 | Monitoreo de la calibración en producción: cobertura real frente a `alpha` por rama y por estrato, con aviso si se sale de ±0,05 (la regla R3, repetida cada mes) | No existe | Alta, una vez lleguen ventas nuevas a la bodega | **Sí**, como historia nueva para después de producción |
| M-3 | Variables de quincena, prima y eventos locales (la propuesta habla de «eventos locales y variaciones por tienda») | No existe | Media: exige datos de eventos y reentrenar con evaluación preregistrada | **Después**: en el backlog, sin release |
| M-4 | Cuantil inferior del intervalo (hoy `limite_inferior` es siempre 0) | No existe | Alta | **No por ahora**: ninguna pantalla ni decisión lo usa |

**Modelo de lenguaje:**

| # | Mejora | Estado | Viabilidad | Recomendación |
| --- | --- | --- | --- | --- |
| L-1 | Un modelo mayor en la nube: qwen3:14b en una GPU de 24 GB (L4 o A10G), o Qwen3-32B en Bedrock | Candidato desde el spike (72 % frente a 63 % en Colab) | Depende de la decisión del spike INV-67 | **Sí**: evaluar con el v1 y los holdouts y adoptar solo si mejora acierto y herramienta (la regla de INV-33) |
| L-2 | Palancas del agente v3: razonamiento en la primera ronda, enrutador y las mejoras P y C de INV-33 | Medidas: no generalizaron en el holdout-2 | Media | Quedan en INV-40, solo las que pasen la regla |

## 4. Plan (aprobado por el usuario el 28-oct)

Se suma a la §7 de `docs/RUTA-AVANCE-3.md`, sin tocar el Sprint 7, que ya tiene 39 SP:

| Historia | SP | Dónde | Por qué ahí |
| --- | --- | --- | --- |
| **INV-72** · Vera responde cómo usar la aplicación (RAG v2): corpus con la guía y el manual (R-A), búsqueda híbrida si mejora (R-B), ≥ 30 preguntas con su fragmento esperado y hit@3 ≥ 0,9 | 8 | **Sprint 8 (Release 4)**: cabe en el margen (31 + 8 = 39 SP) | El asesor y el cliente pueden preguntarle a Vera cómo se usa la aplicación en las pruebas del 2 al 4-dic |
| **INV-73** · Monitoreo de la calibración del pronóstico (M-2) | 5 | Sprint 9 | Necesita producción (INV-69) y ventas nuevas |
| **INV-74** · Modelo de lenguaje mayor en la nube (L-1) | 5 | Sprint 9 | Necesita la decisión de INV-67 y la GPU o Bedrock en producción |
| **INV-63**, con el título nuevo «Evaluación del motor de pronóstico con el holdout 2026 (reglas R1 a R4)» | 5 | Sprint 7 (sin cambios) | Ya era su alcance |
| **INV-75** · Variables de quincena, prima y eventos locales (M-3) | 5 | Backlog, sin release | No cabe y necesita datos |

Con esto, el Sprint 8 queda en 39 SP y el Sprint 9 en 28 SP (18 + 10), con margen para validar y estabilizar.

## 5. Releases de Jira: lo planeado frente a lo implementado

Las fechas coinciden con los sprints: Release 1 del 9-feb al 25-abr (Sprints 1 a 3); Release 2 del 14-sep al 31-oct (Sprints 4 a 6); Release 3 del 2 al 21-nov (Sprint 7); Release 4 del 23-nov al 11-dic (Sprint 8). Lo que no coincide es el contenido:

| Release | Dice hoy | Lo que pasó | Texto propuesto |
| --- | --- | --- | --- |
| **1 · MVP Operacional** (publicado el 25-abr) | «PWA: Dashboard · Inventario semáforo · Tendencias» | Se entregó una aplicación web React; la PWA (manifest y service worker) no se hizo y quedó en INV-70 | Bodega de datos (esquema estrella) y ETL · Core API (autenticación, inventario, reportes, alertas por reglas, catálogos) · aplicación web con Dashboard, Inventario con semáforo y Tendencias · Ambiente: local con Docker Compose · *La PWA del plan original pasó a INV-70 (Release 4)* |
| **2 · Predictivo y conversacional** (31-oct) | «Modelos LightGBM + ML Service · Motor EOQ + Recomendaciones» · Ambiente: local | El motor sirve LightGBM solo en la rama intermitente y la base simple en las suaves. Las compras usan punto de pedido, nivel objetivo y calendario fijo, no EOQ. El agente y el chat, planeados para el R3, se adelantaron a este release | EDA, ingeniería de variables y MLflow · Motor de pronóstico por segmento: LightGBM cuantílico relativo con calibración conformal (rama intermitente) y base de media móvil con cuantil empírico (ramas suaves) · ML Service · Recomendaciones de compra (punto de pedido, nivel objetivo y calendario fijo) y de traslados · CI/CD con imágenes publicadas · Vistas de predicciones y recomendaciones, alertas con IA · Agente de PLN autoalojado (qwen3:8b, 11 herramientas de solo lectura, glosario con BM25, prompts v2 con verificación) y el chat Vera con streaming · Ambiente: local · `v2.0.0` |
| **3** (21-nov) | «InventAI/o Conversacional: NLP Agent: Llama + RAG NL→SQL» | El agente ya está en el R2; Llama perdió el spike frente a Qwen; el NL→SQL se descartó por permisos | Nombre: **Primera versión en la nube**. Motor de pronóstico evaluado con el holdout 2026 y reentrenamiento programado · hardening mínimo · decisión del modelo de lenguaje en la nube · primer despliegue en staging en AWS · agente refinado · ajustes previos a las pruebas · Ambiente: AWS (staging) · `v3.0.0` |
| **4** (11-dic) | «Producción y Entrega: Despliegue AWS · Chat UI en PWA · Documentación · Demo · Entrega» | La documentación y la entrega pasan al Sprint 9; el chat ya existe en la web | Nombre: **Producción**. Producción en AWS (RDS, copias en S3, dominio, monitoreo) · pruebas de carga y seguridad · PWA · Vera responde cómo usar la aplicación (RAG v2) · pruebas con el asesor y el cliente, y sus ajustes · Ambiente: AWS · `v4.0.0` |
| **5** (nuevo; fechas del Sprint 9 todavía sin definir, decisión del usuario del 28-oct) | — | — | Nombre: **Validación y entrega**. Documentación final · demostración y entrega académica · monitoreo de la calibración del pronóstico · modelo de lenguaje mayor · historial de conversaciones · recordatorios push · `v5.0.0` |

Fechas de inicio sugeridas, en el campo «Fecha de inicio» de cada release: R2, 14-sep; R3, 2-nov; R4, 23-nov; R5, el inicio del Sprint 9.
