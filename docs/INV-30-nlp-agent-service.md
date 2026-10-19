# INV-30 · Spike del modelo y decisión

| Campo | Valor |
| --- | --- |
| Decisión | **`qwen3:8b`** (Q4_K_M, digest `500a1f067a9f`), sin razonamiento, con Ollama 0.40.5 |
| Candidato | `qwen3:14b` (digest `bdbd181c33f2`), cuando haya una GPU con 12 GB o más |
| Decidido | 18 de octubre de 2026, por el equipo del proyecto |
| Conjunto | v0 congelado (`fe63d0f`): 43 preguntas (20 base y 23 variantes), 9 de abstención; 3 corridas por pregunta |
| Resultados | `nlp_agent/evaluacion/resultados/` (JSONL por modelo, `resumen.csv`, `detalle.csv` y los smoke) |
| Requerimientos | `docs/INV-30-requerimientos.md` (§4.4, metas y regla de decisión) |

Criterio 3 de la ficha. El spike orienta, no certifica: las metas se exigen con el conjunto v1 de INV-31, con preguntas que los modelos no han visto.

## 1. Cómo se midió

- **Arnés:** `nlp_agent/evaluacion/` corre cada pregunta con el catálogo provisional de 9 herramientas y resultados sintéticos, hasta 3 rondas, y la califica (herramienta y argumentos con la regla de BFCL, fidelidad de cifras, hechos clave, abstención, rechazo y aclaración).
- **Parámetros:** temperatura 0, `top_p` 1, semilla 42, contexto de 8.192 tokens y sin razonamiento (W4). Con temperatura 0 y semilla fija las 3 corridas dan lo mismo, así que pass^3 coincide con el acierto.
- **Entornos:**
  - **Equipo de desarrollo:** RTX 5050 Laptop (8 GB de VRAM), 12 hilos y 19 GB de RAM en WSL2; Ollama 0.40.5 nativo.
  - **Colab Pro, L4** (24 GB, la GPU de la `g6.xlarge` de AWS): la misma versión de Ollama y los mismos digests. Por N9 corre la variante `colab`, con sucursales y fecha ficticias (NORTE, CENTRO, SUR y el 2024-06-28).
- **Comparación:** diferencia pareada por pregunta con intervalo del 95 % por bootstrap. Si el intervalo no separa a dos candidatos, se decide por tamaño y latencia.

## 2. Resultados

### 2.1 Equipo de desarrollo, nombres reales (17-oct)

| Modelo | Acierto | Herramienta | Fidelidad | Abstención | Fugas | p50 | p95 | VRAM |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **qwen3:8b** | **65 %** | 86 % | 100 % | 100 % | 0 | 2,0 s | 4,8 s | 6,2 GB |
| qwen3:4b-instruct-2507 | 58 % | 88 % | 100 % | 100 % | 0 | 1,6 s | 3,0 s | 3,9 GB |
| llama3.1:8b | 43 % | 77 % | 98 % | 33 % | 0 | 2,8 s | 6,6 s | 5,8 GB |

- qwen3:8b le gana a llama3.1:8b: +21,7 puntos, IC [+8,5; +35,7].
- Frente a qwen3:4b no se separa: +7,0 puntos, IC [−2,3; +18,6].

### 2.2 Colab L4, variante colab (19-oct)

| Modelo | Acierto | Herramienta | Fidelidad | Abstención | Fugas | p50 | p95 | VRAM |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| qwen3:14b | 72 % | 88 % | 100 % | 100 % | 0 | 3,9 s | 7,3 s | 10,5 GB |
| **qwen3:8b** | **63 %** | 86 % | 100 % | 100 % | 0 | 2,2 s | 4,2 s | 6,3 GB |
| qwen3:30b-a3b-instruct-2507 | 60 % | 88 % | 98 % | 100 % | 0 | 1,5 s | 2,7 s | 19,3 GB |
| qwen3:4b-instruct-2507 | 59 % | 89 % | 100 % | 100 % | 0 | 1,4 s | 2,5 s | 3,9 GB |
| llama3.1:8b | 49 % | 77 % | 100 % | 33 % | 0 | 2,0 s | 3,5 s | 6,0 GB |

- qwen3:14b es el único que se separa de qwen3:4b (+13,2 puntos, IC [+2,3; +25,6]). Frente a qwen3:8b queda en el límite: +9,3 puntos, IC [0; +20,9].
- qwen3:30b-a3b no supera a qwen3:8b (−2,3 puntos) y fue el único que dio una cifra sin respaldo.

### 2.3 ¿Colab vale como el equipo de desarrollo?

Sí, con la misma versión de Ollama y los mismos digests. Los tres modelos que corrieron en los dos entornos, con la misma variante colab:

| Modelo | Acierto en Colab | Acierto en el equipo | Preguntas que cambian | Herramienta de la 1.ª ronda igual |
| --- | --- | --- | --- | --- |
| qwen3:8b | 63 % | 60 % | 1 | 42 de 43 |
| qwen3:4b-instruct-2507 | 59 % | 59 % | 0 | 43 de 43 |
| llama3.1:8b | 49 % | 47 % | 1 | 42 de 43 |

La corrida del 17-oct en Colab (Ollama 0.4.4 y Qwen 2.5) daba +7,8 puntos al mismo llama: la diferencia era de versión, no de la GPU. Cambiar los nombres de las sucursales mueve unos 5 puntos (qwen3:8b: 65 % con nombres reales, 60 % con la variante), así que solo se comparan corridas con la misma variante.

### 2.4 Latencia de una pregunta (smoke)

`python -m evaluacion.smoke`: 5 preguntas, la primera en frío. Las cifras son medianas de las 4 en caliente; la lectura del prompt, de las 5.

| Modelo | Entorno | Modo | Primer token | Total | Generación | Lectura del prompt | Memoria |
| --- | --- | --- | --- | --- | --- | --- | --- |
| qwen3:8b | Equipo | GPU | 0,44 s | 2,3 s | 47 tok/s | 1.535 tok/s | 6,2 GB |
| qwen3:8b | Equipo | GPU con razonamiento | 4,6 s | 7,1 s | 44 tok/s | 1.542 tok/s | 6,2 GB |
| qwen3:8b | Equipo | CPU (`num_gpu = 0`) | 9,3 s | **41,9 s** | 3,9 tok/s | 32 tok/s | 6,7 GB de RAM |
| qwen3:8b | Colab L4 | GPU | 0,23 s | 1,9 s | 45 tok/s | 2.442 tok/s | 6,3 GB |
| qwen3:8b | Colab L4 | GPU con razonamiento | 3,75 s | 5,6 s | 44 tok/s | 2.360 tok/s | 6,3 GB |
| qwen3:14b | Colab L4 | GPU | 0,33 s | 3,7 s | 26 tok/s | 1.376 tok/s | 10,5 GB |
| qwen3:4b-instruct-2507 | Equipo | GPU | 0,42 s | 1,6 s | 67 tok/s | 2.715 tok/s | 3,9 GB |
| llama3.1:8b | Equipo | GPU | 0,19 s | 1,3 s | 51 tok/s | 1.634 tok/s | 5,8 GB |

**Sin GPU no es viable.** En el equipo de desarrollo (12 hilos), qwen3:8b genera unos 4 tokens por segundo y lee el prompt a 32 tokens por segundo, unas 50 veces más lento que con la GPU. Una sola ronda tarda 42 s de mediana, y la primera pregunta, con la carga, 123 s. Las preguntas del spike usan 2 o 3 llamadas al modelo, así que el p95 pasaría de 1 minuto: no cumple la meta de 30 s. El modo sin GPU queda solo para comprobar que funciona (criterio 9). Producción necesita GPU; se decide en el Sprint 7 con la propuesta de nube (D26).

## 3. Decisión

**`qwen3:8b`, sin razonamiento.** Es el valor por defecto de `LLM_MODELO`.

- Cumple las cuatro metas en los dos entornos: herramienta 86 % (≥ 85 %), fidelidad 100 % (≥ 95 %), cero fugas y p95 de 4,8 s (≤ 30 s).
- Cabe en la GPU del equipo de desarrollo con el contexto de 8k.
- Le gana con claridad a llama3.1:8b, que además no se abstiene (33 %).
- qwen3:4b no se separa de él, pero queda por debajo en los dos entornos y en abstención por permisos (v0-19). La diferencia de latencia no compensa: los dos están lejos de los 30 s.
- qwen3:14b es el mejor, pero no queda demostrado frente al 8b y necesita 10,5 GB: en una GPU de 8 GB correría en parte en CPU. Queda como **candidato**: cambiarlo es solo `LLM_MODELO=qwen3:14b` en una GPU de 12 GB o más (la L4 de la `g6.xlarge`, por ejemplo; la propuesta de nube D26 se revisa en el Sprint 7).
- El razonamiento no se activa: suma unos 3 s al primer token y el spike no lo necesitó para elegir herramientas.

## 4. Hallazgos para las siguientes historias

| Hallazgo | Evidencia | Historia |
| --- | --- | --- |
| **Los modelos no dicen el total.** Listan los productos pero omiten «23 críticos» o «412 alertas» | 9 de las 10 preguntas que fallan los 5 modelos son de este tipo (v0-02, 02b, 05, 06, 06c, 07, 07b, 10b y 11). Es la mayor parte de lo que separa el 63 % del 100 % | INV-32: las herramientas devuelven el total en un campo explícito. INV-33: el prompt pide decirlo |
| **Sin «Omítelo para no filtrar», los modelos llenan los filtros opcionales** | Sondeo del 17-oct, antes de agregarlo al catálogo | INV-32: la descripción de cada filtro opcional lo dice |
| **No piden aclaración cuando la pregunta es ambigua** | v0-14 («¿Cuánta leche hay en PRINCIPAL?») la fallan los 5 | INV-33: instrucción de aclarar |
| **«Según la IA» y «para comprar» confunden la herramienta** | v0-07b y v0-11 eligen la herramienta equivocada en la 1.ª ronda | INV-32: descripciones que distingan pronóstico, alertas y compras |
| **Los nombres de las sucursales mueven el resultado** | ~5 puntos entre nombres reales y ficticios | INV-31: la v1 se mide con los nombres reales en el equipo; Colab solo compara modelos entre sí |

## 5. Lo que no se hizo

- **La corrida completa sin GPU** (43 preguntas): no hace falta. El smoke (§2.4) ya muestra que una ronda tarda 42 s, por encima de la meta. Dónde correr el modelo en producción se decide en el Sprint 7, con la propuesta de nube (D26).
- **La corrida de consistencia** (temperatura 0,7 y varias semillas): no cambia la elección y queda para INV-31.
- **Ajuste fino:** fuera de alcance; el margen está en el prompt y en el formato de las herramientas (§4).
