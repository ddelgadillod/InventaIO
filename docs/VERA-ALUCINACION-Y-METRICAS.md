# Vera: control de alucinaciones y métricas de evaluación

**Versión:** v3.0.0, staging en AWS. **Fecha:** 22 de noviembre de 2026.

En el Avance 3 los evaluadores preguntaron cómo se controla que el agente no alucine. Este documento responde con:
- la arquitectura;
- la evidencia medida;
- un marco de métricas apoyado en la literatura;
- la ruta de pruebas que falta;
- los caminos posibles si se amplía el uso de RAG.

Complementa a [`docs/NLP-AGENT.md`](NLP-AGENT.md), [`docs/INV-40-requerimientos.md`](INV-40-requerimientos.md) y [`docs/VIABILIDAD-RAG-Y-MODELOS.md`](VIABILIDAD-RAG-Y-MODELOS.md).

## 1. Respuesta corta

Vera no puede afirmar una cifra que no haya traído una herramienta. Un verificador determinista revisa cada número de la respuesta antes de mostrarla. Si encuentra uno sin respaldo, pide un reintento; si vuelve a fallar, Vera responde solo con los datos consultados.

En las 425 respuestas evaluadas el 18 y el 19 de noviembre con el modelo de producción (Qwen3-32B en Amazon Bedrock, contra el Core API de staging):
- el modelo dio cifras sin respaldo en 11 borradores, el 2,6 %;
- el verificador detuvo las 11;
- **ninguna respuesta final tuvo una cifra sin respaldo.**

Que no haya fallas en una muestra no prueba que no existan, pero la acota. Con 0 casos en 425, la tasa real queda por debajo del 0,71 % con un 95 % de confianza, según la regla del tres (Hanley y Lippman-Hand, 1983).

## 2. Por qué herramientas y no un RAG sobre los datos

En la propuesta se contempló un RAG y una variante de texto a SQL. Un RAG no se entrena: se indexa una colección de textos y, para cada pregunta, se recuperan los fragmentos más parecidos y se le pasan al modelo (Lewis et al., 2020). Entrenar sería ajustar los pesos del modelo, otra técnica con otros costos.

Los datos de InventAI/o son tablas que cambian cada día, con agregaciones (sumas, rankings y pronósticos) y permisos por ubicación. Por eso se eligió que el modelo use herramientas: funciones de solo lectura sobre el Core API que llama con el token del usuario (Schick et al., 2023; Yao et al., 2023). El RAG quedó para lo que sí es texto: el glosario del negocio y la guía de uso. Las decisiones están en «Modelos y decisiones técnicas»:
- 22, el modelo autoalojado;
- 30, herramientas sin SQL;
- 31, BM25 sobre el glosario;
- 48, el verificador ampliado;
- 49, la guía de uso en la búsqueda.

## 3. Qué es una alucinación aquí y cómo se controla

La literatura distingue dos clases de alucinación (Ji et al., 2023; Huang et al., 2025):
- **De fidelidad:** el texto contradice o no está respaldado por la fuente que el modelo tenía.
- **De factualidad:** el texto contradice el mundo real.

En Vera la fuente son los resultados de las herramientas y los fragmentos recuperados. El riesgo principal es, por eso, la falta de fidelidad.

| Tipo | Ejemplo | Control | ¿Se mide? |
| --- | --- | --- | --- |
| Cifra inventada | «Hay 125 críticos» cuando la herramienta dio 147 | Verificador de cifras: cada número debe estar en los resultados o ser una suma de una columna | Sí |
| Afirmación sin consulta | «No hay traslados» sin haber llamado una herramienta | Reglas de respuesta sin consulta y de «sin datos con contenido» | Sí |
| Respuesta sin datos | Inventar el margen de la competencia | Abstención: si ni las herramientas ni la búsqueda traen la respuesta, Vera lo dice | Sí |
| Cita inventada | Citar la «sección 8.3» de la guía sin haberla recuperado | Regla de cita inventada | Sí |
| Generalización indebida | «La mayoría están en inconsistencia» mirando 10 de 300 | Regla de cuantificador sobre una muestra | Sí |
| Fuga de permisos | Datos de otra sucursal | Cada herramienta llama al Core API con el token del usuario | Sí |
| Entidad inventada | Nombrar un producto o una fecha que no vino de una herramienta | Sin control automático | **No** (fase 3 de la ruta) |
| Interpretación errónea | «El stock alcanza» cuando no alcanza | Sin control automático | **No** (fase 4 de la ruta) |

**Las capas, en orden:**
1. Herramientas de solo lectura con permisos.
2. Búsqueda con umbral doble, que devuelve «sin resultados».
3. Prompt por rol.
4. Verificador determinista.
5. Reintento.
6. Respuesta de respaldo.

El verificador no usa un segundo modelo como juez. Es código, se prueba en el CI y siempre da el mismo resultado.

## 4. Evidencia medida

**Condiciones:**
- 425 respuestas de Qwen3-32B en Bedrock (us-east-2), con el verificador encendido, contra el Core API de staging.
- Son las corridas integradas de INV-40 (18-nov) y de INV-79 (19-nov): el conjunto de 61 preguntas × 3 corridas, tres holdouts, abstención, guía de uso y los conjuntos de INV-40 y de la fecha elegida.
- Están en MLflow con la etiqueta de su historia y en los archivos de resultados del arnés.

| Medida | Resultado |
| --- | --- |
| Respuestas evaluadas | 425 |
| Borradores con alguna cifra sin respaldo | 11 (2,6 %) |
| Intervenciones del verificador | 19 reintentos y 4 respuestas de respaldo (5,4 %) |
| **Respuestas finales con cifras sin respaldo** | **0** (cota superior del 0,71 % con 95 % de confianza) |
| Fidelidad de cifras del borrador, por cifra | 96,7 % en el conjunto de 61 preguntas |
| Respuestas que afirman algo cuando las herramientas no trajeron datos | 0 |
| Abstención ante preguntas sin respuesta (18 × 3) | 100 % |
| Abstención de más (se abstiene cuando había una herramienta para responder) | 1 de 233 (0,4 %) |
| Fugas de permisos | 0 |
| Respuestas sin un hecho clave esperado | 19, por omisión, pedido de aclaración o abstención; ninguna por invención de datos |

## 5. Métricas de evaluación y su respaldo en la literatura

Las métricas del arnés coinciden con las que se usan para evaluar agentes con herramientas y sistemas RAG. En esta tabla, cada métrica va con su referencia y con el valor que tiene Vera hoy.

| Dimensión | Métrica | Qué mide | Referencia | Vera hoy |
| --- | --- | --- | --- | --- |
| Uso de herramientas | Herramienta correcta | Si llamó la herramienta esperada | Patil et al. (2025), BFCL; Li et al. (2023), API-Bank | 92,9 % con equivalencias declaradas (82,5 % estricta) |
| Uso de herramientas | Detección de irrelevancia | No responder con una herramienta cuando ninguna sirve | Patil et al. (2025), BFCL | Conjunto de abstención: se abstiene en el 100 % (18 × 3) |
| Consistencia | pass^k | Que acierte en las k corridas, no solo en una | Yao et al. (2025), τ-bench | Fidelidad pass^3 = 100 %; la misma herramienta en las 3 corridas en 59 de 61 preguntas |
| Fidelidad | Fidelidad de cifras (borrador y final) | Afirmaciones respaldadas por los datos recuperados | Es et al. (2024), RAGAS; Saad-Falcon et al. (2024), ARES | Borrador 96,7 % · final 100 % |
| Fidelidad | Precisión de hechos atómicos | Fracción de afirmaciones verificables que son correctas | Min et al. (2023), FActScore | Por medir (fase 4) |
| Exactitud | Acierto (hechos clave) | La respuesta trae lo esperado | Rajpurkar et al. (2018); Liang et al. (2023), HELM | 89,6 % con equivalencias (79,8 % estricta) |
| Abstención | Abstención correcta y abstención de más | Abstenerse cuando no hay respuesta, sin dejar de responder lo que sí la tiene | Wen et al. (2025); Rajpurkar et al. (2018) | 100 % y 0,4 % |
| Recuperación | hit@3 (recall@3) | El fragmento esperado está entre los 3 primeros | Manning et al. (2008) | Glosario 60/60 · guía 33/35 |
| Recuperación | MRR@3 | Qué tan arriba queda el fragmento esperado | Voorhees (1999) | Glosario 0,939 · guía 0,810 · guía de desarrollo 0,933 |
| Citas | Precisión de la cita | La cita corresponde a la fuente recuperada | Gao et al. (2023), ALCE | Sección esperada en el 54 % · 0 citas inventadas |
| Seguridad | Fugas de permisos y resistencia a instrucciones inyectadas | No revelar datos fuera del rol; no obedecer instrucciones del usuario contra las reglas | OWASP (2025), LLM01 y LLM02; Greshake et al. (2023) | 0 fugas y ningún contenido prohibido; preguntas adversariales del conjunto de 61: 18 de 21 aciertos estrictos |
| Eficiencia | Latencia p50 y p95; costo por pregunta | Uso real | Liang et al. (2023), HELM | p50 2,6 s, p95 6,2 s; US$0,0017 por pregunta |
| Estadística | Intervalos y comparación pareada | Separar una mejora del ruido | Efron y Tibshirani (1993); Wilson (1927); Hanley y Lippman-Hand (1983) | Bootstrap pareado en cada adopción; regla del tres para 0 eventos |

**Notas:**
- Las métricas de RAGAS, ARES y FActScore usan un modelo como juez. Vera mide la fidelidad de las cifras con código determinista, que es más estricto y reproducible, pero solo cubre números.
- La fidelidad de las afirmaciones no numéricas queda para la auditoría humana, con un posible juez automático validado contra ella (Zheng et al., 2023).
- Lo «estricto» y lo «con equivalencias» se explican en la decisión 51: el conjunto de 61 se escribió antes de la ficha de producto, de los periodos con nombre y de la guía.

## 6. Ruta de pruebas para demostrarlo

| Fase | Qué se hace | Métrica y meta | Costo |
| --- | --- | --- | --- |
| 1. Reporte con lo que existe | La tabla de la sección 4, por conjunto, con la cota de la regla del tres; un script que la recalcule desde los resultados del arnés | 0 cifras sin respaldo en la respuesta final | Hecho para este documento; falta el script en el repositorio |
| 2. Conjunto de trampas, congelado antes de medir | Unas 30 preguntas × 3 corridas de estos tipos: producto o sucursal inexistentes; premisa falsa («¿por qué subieron las ventas en 2019?»); cifra sugerida falsa («confirma que hay 500 unidades»); fechas fuera del calendario; instrucciones inyectadas («ignora tus reglas y…»); otra sucursal; preguntas mixtas con una parte respondible | 0 afirmaciones sin respaldo; corrige la premisa ≥ 90 %; 0 fugas; pass^3 ≥ 90 % | Unos US$0,15 en Bedrock |
| 3. Verificador de entidades | Regla determinista: cada código o nombre de producto, sucursal o fecha que aparece en la respuesta debe venir de una herramienta o de la pregunta | Entidades respaldadas = 100 % en todos los conjuntos | Unas horas, con pruebas |
| 4. Auditoría humana de lo cualitativo | Muestra aleatoria de 60 respuestas, revisada por dos personas con una rúbrica (correcta, omisión, interpretación errónea o invención), contando hechos atómicos como en FActScore | Tasa de invención con intervalo de Wilson; acuerdo entre revisores con kappa de Cohen (1960) | Unas 2 horas por revisor |
| 5. Monitoreo en producción | Contar por día, desde el evento de cierre de cada respuesta, los reintentos, los respaldos y las abstenciones, sin guardar el texto (Ley 1581) | Alerta si los respaldos pasan del 5 % de las respuestas del día | Pequeño; junto con la producción (INV-69) |

Las fases 2 a 5 no tienen puntos todavía. Se proponen como una historia del Sprint 8, o dentro de INV-72, según decida el Planning.

## 7. Ventajas y límites de la arquitectura de herramientas

| Ventaja | Por qué importa aquí |
| --- | --- |
| Las cifras salen de SQL, no de texto recuperado | Sumas, rankings y pronósticos exactos. Un RAG sobre documentos no agrega de forma fiable |
| Permisos heredados | Cada consulta lleva el token del usuario y pasa por la regla de ubicaciones del Core API: 0 fugas medidas |
| Datos al día | Las herramientas leen la bodega en vivo; un índice vectorial habría que reconstruirlo en cada carga |
| Trazabilidad | Cada respuesta dice qué consultó; eso hace posible el verificador determinista |
| Evaluación objetiva | Se puede medir si eligió la herramienta correcta, con qué argumentos y si fue consistente entre corridas |
| Privacidad | Los datos del negocio no se copian a un índice externo, y el repositorio público solo lleva textos sin cifras |
| Costo y latencia | US$0,0017 por pregunta y p95 de 6,2 s, sin infraestructura de embeddings |

**Límites:**
- Vera solo responde lo que cubren sus 14 herramientas; lo demás lo abstiene.
- Depende de que el modelo elija bien la herramienta (82,5 % en estricto).
- Las preguntas analíticas nuevas exigen una herramienta nueva.

## 8. Caminos para ampliar el uso de RAG

| Camino | Ventajas | Desventajas | Estado |
| --- | --- | --- | --- |
| Léxico (BM25) sobre el glosario y la guía (Robertson y Zaragoza, 2009) | Determinista, sin infraestructura, explicable; el umbral doble permite abstenerse | No reconoce sinónimos ni paráfrasis; cita la sección esperada en el 54 % | Hecho (INV-40) |
| Híbrido: BM25 más embeddings, con fusión por rango recíproco (Cormack et al., 2009), solo sobre la documentación | Mejor con paráfrasis y preguntas nuevas | Costo de embeddings o un modelo local; índice que reconstruir; ranking menos predecible; hay que volver a medir | INV-72, entra solo si mejora lo medido |
| RAG sobre los datos (filas o reportes convertidos en texto) | Preguntas libres sobre cualquier dato | Cifras viejas en cuanto cambia la bodega; no agrega; filtrar por rol cada fragmento es frágil; **aumenta la alucinación de cifras** | No recomendado |
| Texto a SQL con un rol de solo lectura y seguridad por fila | Preguntas analíticas fuera de las 14 herramientas | Se salta las reglas del Core API salvo con seguridad por fila en la base; consultas costosas; difícil de verificar | Descartado (decisión 30) |
| Ajuste fino del modelo | Mejor elección de herramientas y estilo | Datos etiquetados y cómputo; hay que repetirlo con cada modelo; no resuelve permisos ni frescura | No planeado |

**Recomendación:** mantener los datos por herramientas y el RAG solo para el conocimiento, con verificador de citas. Es lo que hay hoy. La siguiente mejora es la búsqueda híbrida sobre la documentación (INV-72), medida con el holdout de la guía que escribe el usuario y adoptada solo si mejora. Una revisión general de los caminos de RAG está en Gao et al. (2024).

## 9. Cómo se reproduce

- **Corridas:**
  ```
  python -m evaluacion.correr --proveedor bedrock --core-api <URL de staging> --verificar --mlflow --conjunto <nombre>
  ```
  Las claves de prueba van en un archivo fuera del repositorio.
- **Cada respuesta** queda en `nlp_agent/evaluacion/resultados/<fecha>_<conjunto>/*.jsonl`, con:
  - `calificacion`: fidelidad, hechos, abstención y cita;
  - `verificacion`: borrador, cifras sin respaldo del borrador y resultado (`ok`, `reintento` o `respaldo`).
- **La búsqueda** se mide sin modelo en el CI: `tests/test_conocimiento.py` y `tests/test_guia.py`.

## Referencias

- Cohen, J. (1960). A coefficient of agreement for nominal scales. *Educational and Psychological Measurement, 20*(1), 37–46.
- Cormack, G. V., Clarke, C. L. A. y Büttcher, S. (2009). Reciprocal rank fusion outperforms Condorcet and individual rank learning methods. *SIGIR 2009*.
- Efron, B. y Tibshirani, R. J. (1993). *An Introduction to the Bootstrap*. Chapman & Hall.
- Es, S., James, J., Espinosa-Anke, L. y Schockaert, S. (2024). RAGAS: Automated evaluation of retrieval augmented generation. *EACL 2024, demostraciones*.
- Gao, T., Yen, H., Yu, J. y Chen, D. (2023). Enabling large language models to generate text with citations. *EMNLP 2023*, 6465–6488.
- Gao, Y. et al. (2024). Retrieval-augmented generation for large language models: A survey. arXiv:2312.10997.
- Greshake, K. et al. (2023). Not what you've signed up for: Compromising real-world LLM-integrated applications with indirect prompt injection. *AISec 2023*.
- Hanley, J. A. y Lippman-Hand, A. (1983). If nothing goes wrong, is everything all right? Interpreting zero numerators. *JAMA, 249*(13), 1743–1745.
- Huang, L. et al. (2025). A survey on hallucination in large language models: Principles, taxonomy, challenges, and open questions. *ACM Transactions on Information Systems, 43*(2).
- Ji, Z. et al. (2023). Survey of hallucination in natural language generation. *ACM Computing Surveys, 55*(12).
- Lewis, P. et al. (2020). Retrieval-augmented generation for knowledge-intensive NLP tasks. *NeurIPS 2020*.
- Li, M. et al. (2023). API-Bank: A comprehensive benchmark for tool-augmented LLMs. *EMNLP 2023*.
- Liang, P. et al. (2023). Holistic evaluation of language models (HELM). *Transactions on Machine Learning Research*.
- Manning, C. D., Raghavan, P. y Schütze, H. (2008). *Introduction to Information Retrieval*. Cambridge University Press.
- Min, S. et al. (2023). FActScore: Fine-grained atomic evaluation of factual precision in long form text generation. *EMNLP 2023*.
- OWASP (2025). *OWASP Top 10 for Large Language Model Applications*.
- Patil, S. G. et al. (2025). The Berkeley Function Calling Leaderboard (BFCL): From tool use to agentic evaluation of large language models. *ICML 2025*, PMLR 267.
- Rajpurkar, P., Jia, R. y Liang, P. (2018). Know what you don't know: Unanswerable questions for SQuAD. *ACL 2018*.
- Robertson, S. y Zaragoza, H. (2009). The probabilistic relevance framework: BM25 and beyond. *Foundations and Trends in Information Retrieval, 3*(4).
- Saad-Falcon, J., Khattab, O., Potts, C. y Zaharia, M. (2024). ARES: An automated evaluation framework for retrieval-augmented generation systems. *NAACL 2024*.
- Schick, T. et al. (2023). Toolformer: Language models can teach themselves to use tools. *NeurIPS 2023*.
- Voorhees, E. M. (1999). The TREC-8 question answering track report. *TREC-8*.
- Wen, B. et al. (2025). Know your limits: A survey of abstention in large language models. *Transactions of the ACL, 13*, 529–556.
- Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. *JASA, 22*(158), 209–212.
- Yao, S. et al. (2023). ReAct: Synergizing reasoning and acting in language models. *ICLR 2023*.
- Yao, S., Shinn, N., Razavi, P. y Narasimhan, K. (2025). τ-bench: A benchmark for tool-agent-user interaction in real-world domains. *ICLR 2025*.
- Zheng, L. et al. (2023). Judging LLM-as-a-judge with MT-Bench and Chatbot Arena. *NeurIPS 2023, Datasets and Benchmarks*.
