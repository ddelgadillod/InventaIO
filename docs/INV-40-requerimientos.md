# INV-40 · Refinamiento del agente y guía de uso en Vera (RAG) · Requerimientos

| Campo | Valor |
| --- | --- |
| Jira | INV-40 «Refinamiento del agente y guía de uso en Vera (RAG)» · Sprint 7 · 13 SP · límite **20-nov-2026** (nada pasa al Sprint 8) |
| Incluye | INV-77 (con el rol de bodega, Vera dice que no hay traslados por despachar cuando sí los hay) |
| Depende de | INV-67: el modelo de staging es Qwen3-32B en Amazon Bedrock (us-east-2) |
| Alimenta a | INV-72: la búsqueda híbrida y el manual por rol siguen allá |
| Rama | `feature/INV-40-refinamiento-agente`, desde `develop` (`48c3178`), en el worktree `~/InventaIO-wt/INV-40` |

Revisión del 18 de noviembre de 2026. Contrasta la ficha de Jira con el código de `develop` y con una segunda opinión externa (Gemini) sobre el agente. De esa opinión solo entra lo que se comprobó en el código. Las decisiones de la sección 4 se cierran con el formulario del usuario.

## 1. Historia

> Como gerente o administrador de sucursal, quiero que Vera responda bien las preguntas que hoy falla, que explique cómo se usa la aplicación y que diga que no lo sabe cuando no tiene datos, para confiar en sus respuestas durante las pruebas con usuarios.

**Criterios obligatorios.** Los criterios 1 a 9 son obligatorios:
1. Herramienta correcta en al menos el 85 % del conjunto v1, en 3 corridas con el modelo de staging.
2. Como máximo 10 herramientas de solo lectura. Las ventas por producto y por periodo entran como parámetros o fusionando herramientas.
3. Los cuatro hallazgos del chat resueltos, cada uno con un caso nuevo en la evaluación.
4. «Productos más vendidos» y «ventas de un mes» se responden con datos de una herramienta y con los permisos del rol.
5. Guía de uso: al menos 30 preguntas de «cómo hago» y «por qué esta cifra», con hit@3 de al menos 0,9. Cada respuesta cita la sección de la guía.
6. El corpus no lleva cifras ni nombres del negocio.
7. Abstención en al menos el 90 % de 15 o más preguntas sin respuesta, sin cifras sin respaldo.
8. Ningún cambio empeora el acierto ni la herramienta frente al v1, con el borrador respaldado en al menos el 95 %. Se reporta también el acierto en las 45 preguntas de los holdouts (56,3 % de partida).
9. Cero fugas de permisos.

**Criterio deseable:**
10. Percentil 95 de latencia de 30 s o menos.

**Fuera de alcance:**
- la búsqueda híbrida con embeddings y el manual por rol (INV-72);
- NL→SQL;
- el historial de conversaciones (INV-37);
- una base vectorial.

## 2. Punto de partida medido

| Medición | Valor | Fuente |
| --- | --- | --- |
| Herramienta correcta, v1, qwen3:8b | 83,6 % | Sprint 6 (la ficha) |
| v1 con Qwen3-32B en Bedrock, 3 corridas | acierto 84 %, herramienta 89 %, fidelidad 100 %, 0 fugas, p95 6,9 s | `docs/INV-67-requerimientos.md` §10 |
| Holdout natural (15) con Bedrock | acierto 64 %, herramienta 82 % | ídem |
| Las 45 preguntas de los holdouts | acierto 56,3 % | la ficha |
| Glosario, hit@3 en 60 consultas | 1,0 | `docs/NLP-AGENT.md` |
| Guía sin curar con el mismo BM25 (sondeo del 28-oct) | 11 de 15 | `docs/VIABILIDAD-RAG-Y-MODELOS.md` §2 |

Con Bedrock, el criterio 1 ya se cumple (89 %). En esta historia el riesgo es **empeorar** al cambiar el catálogo, no llegar a la meta.

## 3. Contraste con el código

| # | Hallazgo en `develop` | Consecuencia |
| --- | --- | --- |
| 1 | **Traslados.** Con las mejoras apagadas (`MEJORAS=ninguna` en el compose local y en el de producción), el modelo ve `sucursal` y `direccion` («hacia» o «desde»). Los campos `origen` y `destino`, y una descripción con ejemplos, existen detrás del interruptor `catalogo` (`herramientas/catalogo.py`, `esquemas()`). En los datos, ningún traslado llega a la Bodega Central | Es la causa probable del error de bodega (INV-77) y de «traslados de una sucursal a las demás» (primer ajuste del prompt para Bedrock). El arnés ya traduce entre las dos formas (`a_legado` y `a_nuevo` en `evaluacion/conjunto.py`) |
| 2 | **Resúmenes.** `resumen_inventario` y `resumen_alertas` describen la sucursal como «Sucursal o BODEGA_CENTRAL.». Las herramientas por rol dicen «Solo si la pregunta nombra una sucursal; si no, se consultan todas las que ve el usuario» | Es la explicación más probable de las cuatro llamadas seguidas con «estado general de sucursales», que terminan en la respuesta de respaldo. Se confirma con las trazas |
| 3 | **Ventas.** `historial_ventas` tiene `periodo` («2025-11», «2025-T4», «2025»), oculto porque con qwen3:8b empeoró la conducta (INV-33, §5). No ordena por producto. El Core API **ya tiene** `GET /api/reportes/ventas/top-productos`: filtra por rol, ordena por valor, devuelve hasta 50 y, sin fechas, toma el mes de la fecha de los datos | «Más vendidos» se resuelve sin tocar el Core API, así que staging sirve tal cual para evaluar. La propuesta externa de agregar una agrupación por producto al reporte no hace falta |
| 4 | **Verificador.** `Verificacion.ok` aprueba una respuesta sin herramientas si no trae cifras. La regla de «sin datos con contenido» existe, pero está apagada (`sin_datos`). La recuperación de llamadas escritas como texto solo reconoce `<tools>` y `<tool_call>` | Así pasaron «<reporte> ventas </reporte>» y el «no hay» de bodega dicho sin consultar |
| 5 | **Sugerencias.** Después de `resumen_alertas` se ofrece «¿Quieres ver las alertas críticas?». La etiqueta de la tabla de `listar_alertas` no muestra el tipo | Explica el filtro por tipo que nadie pidió y por qué la tabla no lo dejaba ver |
| 6 | **Catálogo.** Tiene 11 herramientas. `listar_sucursales` se espera en 1 de las 61 preguntas del v1 y en ninguna de los holdouts. `resumen_alertas` se espera en 8 del v1 (en 5 de ellas también vale `listar_alertas`) y en 2 de los holdouts | Para llegar a 10, sacar `listar_sucursales` toca una pregunta; fusionar los resúmenes de alertas toca 10 y cambia una conducta que hoy funciona |
| 7 | **Glosario.** `conocimiento/construir.py` arma `corpus.json` desde `docs/GLOSARIO.md`. Son 68 fragmentos con `id`, `titulo`, `parte`, `fuente`, `tambien` y `texto`. El BM25 es propio, recorta las palabras a 6 letras, da más peso al título y a «También se dice», aplica el umbral de cobertura de 0,6 y un peso por parte (`PESO_PARTE`). La imagen se construye con el contexto `nlp_agent/` y no ve `docs/` | La guía entra como un segundo documento fuente en el mismo `corpus.json`. La prueba que compara el corpus con el documento se extiende a la guía |
| 8 | **Guía.** Sus fuentes (Partes II y III) son generadores de PDF fuera del repositorio (`evidencias/guia-cliente/fuentes`, ignorado por git), con cifras calculadas a partir de los datos. Tienen unas 70 secciones. Las de uso y de cifras (capítulos 10.2–10.3, 11, 12, 17, 20 y 21) son unas 35; el resto trata de pruebas, riesgos y hoja de ruta | El corpus se cura a mano en un documento versionado, sin cifras ni nombres del negocio |
| 9 | **Arnés.** El tipo «abstención» del conjunto significa *no llamar herramientas*. No hay un criterio para «consultó, no encontró y lo dijo», ni para «citó la sección». `--conjunto` solo acepta v0, v1 y los tres holdouts | Hacen falta dos criterios nuevos de calificación y tres conjuntos nuevos: guía, abstención y los casos de esta historia |
| 10 | **Datos.** El v1 califica contra hechos al 31-dic-2025. La base local está al 30-sep-2026 desde el 17-nov (INV-63) y la usa la sesión de INV-62. Staging sigue al 31-dic-2025. El arnés acepta `--core-api` con cualquier URL | Se evalúa en local contra el Core API de staging, sin restaurar la base local (decisión 9) |
| 11 | **Comprobación externa.** La segunda opinión acierta en los hallazgos 1, 2, 4 y 5. En cambio, propone un cambio en el Core API que no hace falta (hallazgo 3), cita una «Decisión 16» que no existe y apoya parte de sus propuestas en bibliografía que no dice eso | Se toman sus ideas comprobables (las etiquetas sin herramientas, el «no hay» sin consulta, los cuantificadores sobre muestras, los meses por nombre y la cobertura ponderada por IDF como opción medida), no sus cifras ni sus citas |

## 4. Decisiones

**Formulario del usuario (18-nov):**

| # | Tema | Decisión |
| --- | --- | --- |
| 1 | Cuántas herramientas | **Más de 10 y menos de 15.** El usuario cambia el criterio 2 de la ficha (máximo 14). No se quita ni se fusiona ninguna herramienta |
| 2 | Más vendidos y ventas de un mes | **Una herramienta nueva para el ranking de ventas por producto** (`productos_mas_vendidos`, sobre `top-productos`). Para «ventas de diciembre», `historial_ventas` muestra `periodo`, que acepta un mes por nombre. Esto último es una interpretación técnica de la decisión: la herramienta nueva es la del ranking |
| 3 | Dirección de los traslados | **`origen` y `destino` visibles,** como se propuso |
| 4 | Verificador | **Las cuatro reglas:** etiquetas sin consultar, «no hay» sin consultar, «sin datos con contenido» activa y «la mayoría» sobre una muestra |
| 5 | Corpus de la guía | **Uso y cifras, curado,** como se propuso |
| 6 | Búsqueda | **Los cambios de Gemini desde el inicio:** raíces del español, cobertura ponderada por IDF y umbral doble. Los umbrales se calibran con los conjuntos de desarrollo y el glosario se mantiene en hit@3 = 1,0 |
| 7 y 8 | Conjuntos | **Los escribo yo y quedan congelados** antes de curar sinónimos y umbrales. Los casos nuevos van en un conjunto aparte (`inv40`) |
| 9 | Evaluación | **Arnés en WSL contra el Core API de staging,** con una línea base nueva de `develop` |

En la tabla que sigue quedan las propuestas originales, como registro de lo que se consultó.

| # | Tema | Propuesta | Alternativas |
| --- | --- | --- | --- |
| 1 | Cómo llegar a 10 herramientas | **Sacar `listar_sucursales`.** Las sucursales visibles para cada rol van en su parte del prompt, que ya las nombra para el gerente | Fusionar `resumen_alertas` en `listar_alertas` con una vista de resumen (lo que propuso Gemini); fusionar `resumen_inventario` en `consultar_inventario` |
| 2 | Más vendidos y ventas de un mes | **Parámetros en `historial_ventas`:** `periodo` visible, que acepta también un mes por nombre («diciembre» se resuelve contra la fecha de los datos), y `ranking: true`, que llama a `top-productos` | Una herramienta nueva de ventas por producto, que obliga a fusionar otra; agregar al Core API una agrupación por producto |
| 3 | Dirección de los traslados | **`origen` y `destino` visibles**, con ejemplos («despachar», «enviar» o «mandar a las sucursales» desde bodega es origen). `destino` acepta solo tiendas. La regla de bodega va también en su prompt | Mantener `sucursal` y `direccion` con más ejemplos; una regla fija por rol antes del modelo |
| 4 | Verificador | **Pedir un reintento** cuando: (a) la respuesta trae etiquetas tipo `<reporte>` sin herramientas; (b) dice «no hay» sobre datos sin haber consultado; (c) afirma contenido cuando las herramientas no trajeron nada (activar `sin_datos`); (d) dice «la mayoría» o «casi todos» sobre una lista parcial | Solo (a) y (b); exigir herramientas en toda respuesta que no sea una frase fija (riesgo con saludos y aclaraciones) |
| 5 | Corpus de la guía | **Un documento curado, `docs/GUIA-USO.md`,** con los capítulos de uso y cifras de las Partes II y III, en unos 50 a 70 fragmentos cortos con sinónimos, sección, fecha y fuente. Va en el mismo `corpus.json` y la misma herramienta, cuya descripción cubre «cómo uso la aplicación» | Toda la guía, con pruebas y hoja de ruta; una herramienta aparte (serían 11) |
| 6 | Búsqueda | **El BM25 actual con sinónimos curados.** La cobertura ponderada por IDF y un piso de puntaje entran solo si el conjunto de desarrollo lo pide, y siempre con el glosario en 1,0 | Adoptar desde el principio los cambios de Gemini (raíces del español y umbral doble) |
| 7 | Conjuntos nuevos y protocolo | **Los escribo yo y quedan congelados en un commit antes de curar sinónimos y umbrales.** Guía: 30 o más de aceptación y unas 15 de desarrollo. Abstención: 15 o más de aceptación y unas 8 de desarrollo. Casos de esta historia: uno por hallazgo y uno por INV-77. Tú los revisas solo en la forma | Los de aceptación los escribes tú; un solo conjunto sin separar desarrollo y aceptación |
| 8 | Dónde van los casos nuevos | **En un conjunto aparte (`inv40`),** para no mover la línea base del v1 | Agregarlos al v1 |
| 9 | Contra qué datos se evalúa | **Arnés en WSL, con Bedrock y el Core API de staging (31-dic).** Antes de los cambios se corre una línea base nueva de `develop` en esa misma infraestructura | Restaurar la base local al 31-dic (choca con INV-62); correr el arnés dentro de la instancia de staging |

**Decisiones técnicas, sin formulario:**
- Los siete ajustes del prompt que dejó INV-67 entran todos (sección 5.3).
- Una sola ronda de ajuste después de la primera evaluación. Si algo no llega a la meta, se documenta y no se sigue iterando (acordado el 18-nov).
- Las mejoras de INV-33 siguen apagadas, salvo la que se active por la decisión 4c (`sin_datos`).
- La decisión se registra en «Modelos y decisiones técnicas» desde el número 47: la sesión de INV-62 registra de la 36 a la 46 (aviso del 18-nov). Cada decisión se nombra por su título en palabras y el número va solo entre paréntesis.

## 5. Diseño

### 5.1 Catálogo resultante (12 herramientas, todas de solo lectura)

| Herramienta | Cambio |
| --- | --- |
| `productos_mas_vendidos` | **Nueva.** Ranking de productos por valor vendido sobre `GET /api/reportes/ventas/top-productos`, que ya filtra por rol. Acepta `periodo` (un mes por nombre, «2025-12», un trimestre o un año), `dias`, `sucursal` (por rol), `categoria` y `limite` (hasta 10). Sin periodo, el último mes de los datos |
| `listar_sucursales` | Se queda |
| `buscar_producto` | — |
| `consultar_inventario` | — |
| `listar_alertas` | La descripción de `tipo` dice «solo si la pregunta nombra el tipo» y la etiqueta de la tabla muestra el tipo |
| `resumen_alertas` | La descripción de la sucursal pasa a la de por rol |
| `resumen_inventario` | La descripción de la sucursal pasa a la de por rol. La descripción aclara que una llamada sin sucursal trae todas |
| `pronosticar_demanda` | — |
| `historial_ventas` | `periodo` visible, que acepta un mes por nombre («diciembre» se resuelve contra la fecha de los datos). La descripción remite el ranking a `productos_mas_vendidos` |
| `recomendar_compras` | — |
| `recomendar_traslados` | `origen` y `destino` (solo tiendas), con ejemplos. `sucursal` y `direccion` dejan de mostrarse, aunque se siguen aceptando |
| `buscar_en_glosario` | Busca en el glosario y en la guía. Devuelve la sección y la fuente, y su descripción cubre «cómo uso la aplicación» y «por qué esta cifra» |

### 5.2 Verificador (`agente/fidelidad.py` y `agente/bucle.py`)

**Reglas nuevas.** Cada una pide un reintento con su corrección, y si el reintento falla se da la respuesta de respaldo:
- **Etiquetas sin herramientas:** la respuesta trae una etiqueta `<algo>…</algo>` y no hubo ninguna consulta.
- **Negación sin consulta:** la respuesta dice «no hay…» o «no existen…» sobre datos del negocio y no hubo ninguna consulta. Las frases fijas de fuera de alcance, de permiso y de instrucciones no cuentan.
- **Sin datos con contenido:** se activa la regla que ya existe.
- **Cuantificador sobre una muestra:** la respuesta dice «la mayoría», «casi todos» o algo parecido, la herramienta trajo menos filas que su total y no hay un resumen global.

**Respaldo sin datos.** Una respuesta de respaldo sin datos sigue diciendo «No hay datos para esa pregunta en el sistema.».

### 5.3 Prompt (`prompts/v2/`)

**Los siete ajustes que dejó INV-67:**
1. Ejemplos de dirección en los traslados.
2. El glosario y la guía nunca se responden de memoria.
3. Si la herramienta no filtra por fecha, decirlo en lugar de inventar `dias`.
4. Sin herramientas en un saludo o en la conversación social.
5. Heredar la sucursal y el producto del turno anterior, y volver a consultar.
6. Ante un producto genérico como «lenteja», preguntar cuál.
7. Qué cifras lleva el resumen de una sucursal.

**Además:**
- citar la sección de la guía;
- en la parte del administrador de bodega, que despachar, enviar o mandar a las sucursales es origen = Bodega Central;
- «más vendidos» o «ranking de productos» van a `productos_mas_vendidos`, y un mes concreto, a `periodo`.

### 5.4 Corpus de la guía

**`docs/GUIA-USO.md`:** una sección `##` por fragmento, con el mismo formato que el glosario más tres campos:
- `Sección`, por ejemplo «Parte II · 12.7 Recomendaciones»;
- `Fecha` de la guía;
- `Fuente`.

**Construcción:** `conocimiento/construir.py` lee los dos documentos y escribe un solo `corpus.json`, con `parte` = «Guía de uso».

**Búsqueda (decisión 6):** en `conocimiento/bm25.py` se aplican tres cambios:
- se quitan los sufijos comunes del español antes de recortar a 6 letras;
- se calcula la cobertura de la consulta ponderada por IDF;
- se exige un umbral doble: el puntaje BM25 y esa cobertura. Los dos valores se calibran con `guia-dev` y `abstencion-dev`, no con los de aceptación.

Si el glosario baja de hit@3 = 1,0, se ajusta el cambio hasta recuperarlo.

**Prueba:** comprueba tres cosas:
- que el JSON corresponde a los documentos;
- que la guía no tiene cifras de datos, salvo las constantes del código (15 días hábiles, umbrales del semáforo, límites de la aplicación), que se comparan con el código como en el glosario;
- que no nombra sucursales ni productos.

### 5.5 Conjuntos y calificación

| Conjunto | Contenido | Qué se mide |
| --- | --- | --- |
| `guia` (aceptación, 30 o más) y `guia-dev` (unas 15) | Pregunta y fragmento esperado | hit@3, sin modelo y determinista, en la prueba. Con el agente: herramienta correcta y que la respuesta nombre la sección |
| `abstencion` (15 o más) y `abstencion-dev` (unas 8) | Preguntas sin respuesta en los datos ni en la guía (otros negocios, datos que el sistema no tiene, futuro lejano, opiniones) | Se abstiene: lo dice con una frase de no tener la información y no da cifras sin respaldo. Se puede consultar antes |
| `inv40` | Un caso por hallazgo del chat y uno por INV-77, con los tres roles donde aplique | Acierto normal |

**Calificación:** se agregan dos criterios en `evaluacion/calificacion.py`:
- `abstiene`: lo pide la pregunta con `sin_respuesta: true`;
- `cita`: lo pide la pregunta con `seccion_esperada`.

**Expectativas existentes:** no cambia ninguna herramienta esperada en el v1 ni en los holdouts. Los traslados ya se califican igual con `sucursal` y `direccion` o con `origen` y `destino` (`a_legado` y `a_nuevo`).

## 6. Cómo se mide cada criterio

| Criterio | Medición |
| --- | --- |
| 1 y 8 | v1 × 3 con Bedrock contra el Core API de staging, comparado pregunta por pregunta con la línea base nueva (`evaluacion/comparar.py`). El borrador, con la fidelidad del borrador |
| 2 | Prueba que cuenta las herramientas del esquema (máximo 14, todas de solo lectura, según la decisión 1) |
| 3 | Conjunto `inv40` × 3 |
| 4 | Casos de `inv40` con gerente, administrador de sucursal y bodega |
| 5 | hit@3 en `guia` (prueba) y corrida del agente en `guia` con la cita |
| 6 | Prueba del corpus |
| 7 | `abstencion` × 3 |
| 9 | Fugas en todas las corridas |
| 10 | p95 de las corridas de v1 |
| Las 45 de los holdouts | Una sola corrida al final, solo se reporta |

Todo queda en el MLflow local, en experimentos propios de INV-40.

## 7. Pruebas sin modelo (CI)

- **Herramientas:**
  - `historial_ventas` con `periodo` (un mes por nombre, con y sin año) y con `ranking`, que llama a `top-productos` con los filtros del rol;
  - `recomendar_traslados` con `origen` y `destino`, que rechaza la bodega como destino;
  - la etiqueta de alertas con el tipo;
  - el catálogo con 10 herramientas.
- **Verificador:** cada regla nueva tiene un caso que reintenta y uno que no, y las frases fijas no se marcan.
- **Corpus:** la prueba de la sección 5.4, y hit@3 de 1,0 en el glosario y de al menos 0,9 en `guia`.
- **Calificación:** `abstiene` y `cita`, y la correspondencia de expectativas.
- **Cobertura:** la del agente sigue en al menos 90 %.

## 8. Ruta

| Cuándo | Qué | Necesito del usuario |
| --- | --- | --- |
| Mié 18, tarde | Catálogo, verificador, prompt, sugerencias y pruebas. Conjuntos `inv40`, `abstencion` y `guia` congelados en un commit | El formulario |
| Mié 18 o jue 19, temprano | Línea base de `develop` con Bedrock contra staging (unos 30 min) | Staging encendido, la llave de Bedrock activa y las cinco claves de los usuarios de staging en un archivo local, fuera del repositorio y con permisos 600. En staging cada usuario tiene su propia clave (`seed_usuarios --nube`) y el arnés hoy acepta una sola: se le agrega `INVENTAIO_CLAVES_PRUEBA`, que apunta a ese archivo |
| Jue 19 | Corpus de la guía y búsqueda. Primera evaluación completa. Punto de control al mediodía | Ídem |
| Vie 20, mañana | Una ronda de ajuste, la corrida única de los holdouts, el PR y la integración | Revisar el PR |
| Vie 20, tarde | Despliegue en staging y verificación con los tres roles en Vera (local y staging), documentación, Confluence y Jira | Staging encendido y aprobar Confluence y Jira por formulario |

## 9. Riesgos

| Riesgo | Cómo se cubre |
| --- | --- |
| Un cambio de esquema mejora un caso y empeora otros (ya pasó con `periodo` y con los traslados en qwen3:8b) | Cada cambio se mide con el v1 frente a la línea base nueva. Si empeora con significancia, se revierte ese cambio y no todos |
| La guía y el glosario en un solo índice se roban consultas | El glosario se mantiene en hit@3 1,0 como prueba. Se puede ajustar el peso por parte |
| Sobreajuste en la guía y la abstención | Los conjuntos de aceptación se congelan antes de curar sinónimos y umbrales. Se calibra solo con los de desarrollo |
| La búsqueda de la guía y la abstención tiran en direcciones opuestas | Se reportan juntas. El umbral se elige en el conjunto de desarrollo |
| Staging o la llave no están disponibles a tiempo | La línea base se adelanta en cuanto estén. El código y las pruebas no dependen de eso |
| La verificación en staging requiere la imagen de `develop` | Integrar a más tardar el viernes al mediodía |
