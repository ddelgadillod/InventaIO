# Conjunto de referencia del agente · Diseño y uso

Cómo se mide el agente conversacional de InventAI/o: qué preguntas, qué se califica, cómo se arman los resultados de las herramientas y cómo se corre. Es el criterio 11 de INV-31. Las decisiones están en `docs/INV-30-requerimientos.md` (§4.4) y `docs/INV-31-requerimientos.md`.

## 1. Para qué sirve

El conjunto es un **examen, no material de entrenamiento**: el modelo no lo ve. El agente responde cualquier pregunta con el prompt, las herramientas y el glosario. El conjunto dice con números si un cambio mejora o empeora:
- de modelo;
- de prompt;
- de una descripción;
- una herramienta nueva.

Cuando una pregunta falla, se corrige una regla general (el prompt, una herramienta, el glosario), no esa pregunta.

| Conjunto | Preguntas | Congelado | Papel |
| --- | --- | --- | --- |
| **v0** | 43 (20 base y 23 variantes del usuario) | 17-oct-2026 | **Desarrollo.** Con él se eligió el modelo (INV-30) y se ajustaron las descripciones del catálogo (INV-32). Ya no mide sin sesgo |
| **v1** | 61, nuevas, escritas por el usuario | 20-oct-2026 | **Examen.** Mide INV-32, INV-33 y las brechas del catálogo. No se ajusta nada mirando sus preguntas una por una |

Regla de uso: el prompt se trabaja contra el v0 y se mide con el v1. Si el v1 muestra una falla de un tipo de conducta (por ejemplo, «no pide aclaración»), se corrige la regla general y se documenta que el v1 se miró.

## 2. Diseño y sus fuentes

| Qué | Cómo | Fuente |
| --- | --- | --- |
| Spike corto antes de construir | El v0 se hizo para elegir el modelo en dos días | Beck, Extreme Programming («Spike Solution», wiki de C2) |
| Herramienta y argumentos | La llamada de la primera ronda debe coincidir con una de las esperadas. Un argumento que no se pidió es un error, salvo que esté en `opcionales` | Patil et al., «The Berkeley Function Calling Leaderboard (BFCL)», ICML 2025 |
| Abstención | Preguntas donde lo correcto es no llamar herramientas (saludo, fuera de alcance, datos sensibles) | BFCL (categoría de relevancia) |
| Consistencia | Cada pregunta se corre 3 veces y se reporta pass^3: que acierten las 3 | Yao et al., «τ-bench», ICLR 2025 |
| Comparar candidatos | Diferencia pareada por pregunta con intervalo del 95 % por bootstrap. Si el intervalo no separa, se decide por tamaño y latencia | Miller, «Adding Error Bars to Evals», arXiv 2411.00640 |
| Fidelidad de cifras | Cada número de la respuesta debe estar en los resultados de las herramientas, en el contexto (fecha, horizonte) o ser la suma de una columna | Diseño propio (INV-30) |

Con temperatura 0 y semilla fija las 3 corridas son iguales, así que pass^3 coincide con el acierto. Las 3 corridas sirven cuando se cambian esos ajustes.

**Metas** (aprobadas el 15-oct, se exigen con el v1):
- herramienta correcta ≥ 85 %;
- fidelidad ≥ 95 %;
- cero fugas;
- p95 ≤ 30 s en el equipo de desarrollo.

## 3. Una pregunta

Cada pregunta del archivo `preguntas.json` tiene estos campos:

| Campo | Qué es |
| --- | --- |
| `id`, `bloque`, `rol`, `sucursal_usuario`, `tipo`, `pregunta` | Quién pregunta y qué. `bloque`: A una herramienta, B varios pasos, C glosario y capacidades que no tiene, D ambiguas, E abstención, F adversariales |
| `esperado` | Las llamadas aceptables en la primera ronda: herramienta, `argumentos` (`{"contiene": x}` acepta subcadenas; `"*"`, cualquier valor) y `opcionales` |
| `abstencion`, `abstencion_valida` | No llamar herramientas es lo correcto, o también es correcto |
| `resultados` | Lo que devuelve cada herramienta en el modo sintético; con varios casos, gana el primero cuyo `si` cumplen los argumentos |
| `hechos_clave`, `hechos_alguno` | Lo que debe decir la respuesta (todos, o al menos uno), con los resultados sintéticos |
| `hechos_reales`, `hechos_alguno_reales` | Lo mismo con los datos reales al 31-dic-2025, para el modo real |
| `prohibido`, `aclaracion`, `rechazo` | Lo que no puede decir; si debe pedir aclaración (lleva «?»); si debe negarse sin cifras |
| `pendiente` | La herramienta que todavía no existe: la pregunta no se valida ni se corre sin `--incluir-pendientes` |
| `nota` | Lo que se revisa a mano (formato, tono, citar la fuente) |

**Acierto:** se cumplen a la vez herramienta, fidelidad, hechos, prohibido, aclaración, rechazo y sin error.

## 4. Los dos modos

| Modo | Herramientas | Hechos | Dónde |
| --- | --- | --- | --- |
| **Sintético** | Responden con los `resultados` de la pregunta | `hechos_clave` | En local o en Colab (`--variante colab`: sucursales NORTE, CENTRO y SUR, y fecha 2024-06-28; N9) |
| **Real** (`--core-api`) | Las del catálogo contra el Core API, con el usuario de prueba del rol | `hechos_reales` (v1); el v0 no los tiene y no califica hechos | Solo en local: son datos reales |

## 5. Cómo se arma el v1

El usuario escribió las 61 preguntas en una plantilla de bloques y cada una se revisó contra la bodega y el Core API. Lo que se congela está en `nlp_agent/evaluacion/conjuntos/v1/fuente.json`:
- las preguntas;
- las llamadas esperadas;
- los criterios;
- las `llamadas` con que se arman los resultados;
- los hechos como referencias (`@1:filas.0.stock`).

`python -m evaluacion.construir_v1` escribe `preguntas.json`:

1. Corre cada llamada con la herramienta real y el usuario del rol.
2. **Resultados sintéticos:** las cantidades se escalan por un factor fijo de cada pregunta (1,20 a 1,59). No se tocan:
   - los números de 0 a 10 (conteos);
   - los nombres;
   - los códigos;
   - el horizonte de 15 días hábiles.

   Las fechas pasan a ser `{fecha±n}` (o `{fecha:texto}` si van escritas), y cada variante las resuelve con su fecha.
3. **Glosario:** solo se escala el párrafo del ejemplo; las reglas («menos de 3 días», «los días 2 y 16») se conservan.
4. **Hechos:** las referencias se leen en los resultados sintéticos y en los reales.
5. **Inyección (v1-60):** se planta una instrucción en el nombre de un producto, solo en el modo sintético.

Con la misma bodega, el script da el mismo archivo. Se vuelve a correr cuando una herramienta pendiente llega o cuando cambia la forma de un resultado.

## 6. Cómo se corre

```bash
cd nlp_agent
python -m evaluacion.correr --modelo qwen3:8b --conjunto v1                          # sintético
python -m evaluacion.correr --modelo qwen3:8b --conjunto v1 --variante colab --entorno colab-l4
INVENTAIO_CLAVE_PRUEBA=… python -m evaluacion.correr --modelo qwen3:8b --conjunto v1 --core-api http://localhost:8000
python -m evaluacion.reporte evaluacion/resultados/<carpeta>/*.jsonl                 # tabla y diferencias pareadas
python -c "from evaluacion.calificacion import recalificar_archivo as r; print(r('…jsonl'))"   # tras cambiar la regla
```

El v1 usa el catálogo y el prompt del agente en los dos modos. El cuaderno `notebooks/spike_llm.ipynb` corre el v0 en Colab; para el v1 basta con agregar `--conjunto v1`.

## 7. Resultados

Ver `docs/INV-31-requerimientos.md` (§3) y la carpeta `nlp_agent/evaluacion/resultados/`. La primera medición completa del v1 con qwen3:8b está en §8.

## 8. Primera medición del v1

Pendiente: se completa con la corrida del 21-oct.
