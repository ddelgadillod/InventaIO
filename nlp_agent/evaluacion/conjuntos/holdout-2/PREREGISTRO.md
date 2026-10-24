# Preregistro del holdout-2 de INV-33

Escrito el 23-10-2026 a las 21:27:52 -0500, ANTES de abrir Descargas/INV-33-plantilla-holdout-2.xlsx.
Decisión del usuario del 23-oct: congelar las palancas ya y revisar el holdout-2 mientras corre la serie del v1.

1. **Código congelado en 4e6bca4.** No cambia la lógica de las palancas después de abrir el holdout-2: agente/mejoras.py,
   agente/bucle.py, agente/fidelidad.py, herramientas/catalogo.py, prompts/v2/ y evaluacion/calificacion.py. Si la
   serie del v1 muestra un error de código en una palanca, esa palanca se apaga (no se corrige) y se reporta.
2. **Activación de cada interruptor (MEJORAS), decidida solo con la serie del v1** (resultados/2026-10-23_local-mejoras-*):
   - argumentos, aclaracion y seguir: se activan si acierto(todas) ≥ acierto(todas sin ella) en el v1;
   - agrupacion y sin_datos (sin ablación propia): se activan si las preguntas que tocan no empeoran en «todas» frente a «ninguna»;
   - razonar (P7): solo si «todas+razonar» supera a «todas» en acierto y su p95 queda ≤ 30 s;
   - los cambios sin interruptor (P3b, P5, P6, ambigüedad del inventario) ya están en el código: se reportan con
     «ninguna» frente a la confirmación del 22-oct.
3. **El holdout-2 se corre una vez** con la configuración que salga de 2 y, para comparar, con MEJORAS=ninguna sobre el
   mismo código. Solo se reporta; no se ajusta nada mirándolo.
4. **Regla de activación en el chat** (§3f): sube el acierto en el holdout-2 frente a «ninguna», sin empeorar la
   herramienta (del modelo) ni la fidelidad, y con p95 ≤ 30 s.

## Adenda del 23-10-2026 a las 22:58:13 -0500, antes de correr el holdout-2 (aprobada por el usuario)

5. **Tres corridas del holdout-2** (15 × 3, real, con verificación), en vez de dos:
   1. **Línea base:** el agente de la rama al 22-oct (commit 6a54423, idéntico en el agente a f652559: prompt v2.1 con
      verificación, sin las mejoras de hoy), en un worktree temporal; solo se ajusta el arnés para aceptar el conjunto.
      Se recalifica con el calificador vigente.
   2. Código congelado (4e6bca4) con MEJORAS=ninguna.
   3. Código congelado con la configuración que salga de la regla 2 (hoy: argumentos, agrupacion, aclaracion, sin_datos;
      P7 según su corrida).
6. **Predicciones, escritas antes de ver resultados** (15 preguntas: una diferencia menor a ~20 puntos cae en el ruido):
   - acierto de 3 > 2 ≥ 1; diferencia 3 − 1 entre +5 y +20 puntos, probablemente con un intervalo que incluye 0;
   - herramienta del modelo: parecida en las tres (±10 puntos);
   - h2-07 falla en 3 por la guarda P1 (meses); h2-04 y h2-05 mejoran en 2 y 3 por P5; h2-03 puede mejorar o empeorar por P6;
   - p95 ≤ 30 s en las tres.

## Adenda 2 del 23-10-2026 a las 23:01:43 -0500, antes de correr el holdout-2 (pedida por el usuario)

7. **Cuarta corrida:** el prompt v1 de INV-32 con verificación sobre el agente del 22-oct (commit 6a54423, `--prompt v1
   --verificar`), la misma configuración que la comparación del primer holdout. Predicción: acierto parecido al de la
   corrida 1 (±10 puntos) y herramienta del modelo más baja que la del v2.1 (como en el primer holdout: 60 % frente a 86,7 %).
