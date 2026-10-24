# Preregistro del holdout-3 de INV-33

Escrito el 24-10-2026 a las 07:41:28 -0500, ANTES de medir las correcciones y antes de abrir
Descargas/INV-33-plantilla-holdout-3.xlsx. Decisiones del usuario del 24-oct (§3g de docs/INV-33-requerimientos.md).

1. **Código de las correcciones:** commit 4f71615 (C1 a C9, cada una con su interruptor). Se puede corregir un error
   de código encontrado al medir con lo ya visto, siempre antes de abrir el holdout-3; después de abrirlo, el código
   queda congelado y un error solo se apaga.
2. **Conjunto de desarrollo:** lo ya visto, que son 91 preguntas: v1 (61), holdout (15) y holdout-2 (15).
3. **Corridas de desarrollo** (real, con verificación):
   - B = las palancas activas del 23-oct (argumentos, agrupacion, aclaracion, sin_datos) + C1 a C8, con 3 corridas
     por conjunto;
   - B − Cx, para cada una de las 7 correcciones con interruptor (periodo, categoria, cobertura, glosario, meses,
     relleno, totales), con 1 corrida, que se compara con la corrida 1 de B (con temperatura 0, las tres corridas
     son casi iguales);
   - B + C9 (busqueda), con 1 corrida;
   - A = solo las palancas activas del 23-oct en el holdout (el v1 y el holdout-2 ya la tienen).
4. **Regla por corrección:** Cx queda encendida si el acierto de B ≥ el de B − Cx en las 91 preguntas. C9 se enciende
   solo si B + C9 supera a B y el p95 queda ≤ 30 s.
5. **Holdout-3, una sola vez por configuración:** el agente del 22-oct (commit 6a54423, en un worktree temporal) y la
   configuración final (palancas activas + las Cx que pasen la regla 4). Se califica con el calificador vigente.
6. **Decisión de integración:** se integra el agente nuevo si en el holdout-3 su acierto supera al del 22-oct, sin
   empeorar la herramienta del modelo ni la fidelidad, y con p95 ≤ 30 s. Si no, **se integra el agente del 22-oct**
   (se revierten los cambios sin interruptor y las palancas quedan apagadas).
7. **Predicción:** en lo ya visto, B supera a A por más de 10 puntos (las correcciones apuntan a esas fallas). En el
   holdout-3, la configuración final queda entre −5 y +15 puntos frente al 22-oct; lo más probable, un intervalo que
   incluye 0.

## Adenda del 24-10-2026 a las 09:10:28 -0500, antes de construir y medir la alternativa 1 (decisión del usuario)

8. **Alternativa 1, extracción de entidades** (interruptor `entidades`): código determinista que detecta en la pregunta
   sucursales, categorías y periodos (un mes o un año nombrados), los entrega al modelo como datos y completa los
   argumentos que el modelo omita o ponga mal (la categoría, el periodo en historial_ventas y una sola sucursal nombrada).
   **No cambia esquemas ni descripciones del catálogo.** Se construye antes de abrir el holdout-3.
9. **F** = la configuración que salga de la regla 4 sobre la serie de correcciones (hoy: palancas activas + C2 a C8 menos
   C1; C9 según su corrida). Corridas de desarrollo en las 91 preguntas (1 corrida): F + entidades.
   **Regla:** entidades se enciende si acierto(F + entidades) ≥ acierto(F) y herramienta del modelo(F + entidades) ≥
   herramienta(F) − 2 puntos. La comparación usa la corrida «sin-periodo» de la serie, que es F con 1 corrida (si C9 queda
   apagada).
10. **Holdout-3, tres configuraciones, una vez cada una:** (1) el agente del 22-oct, (2) F, (3) F + entidades (solo si pasa
    la regla 9). **Integración:** se integra (3) si supera a (1) en acierto sin empeorar la herramienta del modelo ni la
    fidelidad y con p95 ≤ 30 s; si no, (2) con la misma regla; si ninguna, el agente del 22-oct.
11. **qwen3:14b (medición, no se integra):** primero el impacto en el hardware: memoria de GPU y RAM, capas en GPU y
    latencia en un smoke de 5 preguntas. Solo si el smoke da p50 ≤ 15 s y p95 ≤ 40 s se corre el v1 completo.

## Congelamiento del 24-10-2026 a las 09:25:53 -0500, antes de abrir el holdout-3

12. **Código congelado en 42172fa** (correcciones y extracción de entidades). Después de abrir el holdout-3 no cambia la
    lógica: un error de código se apaga, no se corrige. Lo único pendiente es si se enciende `entidades`, que decide la
    regla 9 sobre la corrida de desarrollo en curso (local-corr-F-entidades-*), sin margen de interpretación.

## Nota del 24-10-2026 a las 09:50:51 -0500, antes de correr el holdout-3

13. **Generación desbocada en el desarrollo** (F + entidades, h2-06 del holdout-2: 34.873 tokens en 16 min, sin terminar).
    Se corrige solo el **arnés** (commit 297d202): cada pregunta tiene el mismo límite
    total que el chat (LLM_TIMEOUT_S = 120 s) y, si se pasa, cuenta como «tiempo_agotado». El agente no cambia: el chat ya
    cortaba a los 120 s. La corrida de desarrollo F + entidades del holdout-2 se repite completa con este arnés (la anterior
    quedó en 5 de 15 y se descarta). Las tres corridas del holdout-3 usan este arnés.
