# Holdout-2 de INV-33

Escrito por el usuario el 23-oct-2026 en la plantilla del holdout-2 y aprobado por él. Se congeló ese mismo día, **antes de medir**. Mide las mejoras del desempeño (§3f de `docs/INV-33-requerimientos.md`) en preguntas nuevas.

| Qué | Valor |
| --- | --- |
| Archivo | `preguntas.json` |
| sha256 del archivo | `48b7ab8977d330f2b75bbde0e49a1cb9fbf007712bfcd5a16f3700837c1dfc5a` |
| Huella del conjunto (`huella_conjunto` de cada corrida) | `4f144b11d539` |
| Preregistro | `PREREGISTRO.md`, escrito antes de abrir la plantilla y con dos adendas antes de correr; sha256 `cf16dd331c53be41dcd5f27513b78919aa829fa09f37c0f67d455fad748a3433` |
| Preguntas | 15: A 4, B 4, C 2, D 2, E 1, F 2. h2-07 trae turnos previos |
| Datos | Solo reales: Core API, foto del 31-dic-2025 |

## Reglas

1. **No se cambia.** `tests/test_conjunto_holdout2.py` falla si el archivo ya no tiene el sha256 de arriba.
2. **El código de las palancas se congeló en `4e6bca4` antes de abrir la plantilla.** Su activación se decidió solo con la serie del v1 (`resultados/2026-10-23_local-mejoras-*`), con la regla del preregistro.
3. **Se corre una vez por configuración y solo se reporta:** la línea base del 22-oct, el código nuevo sin palancas, el código nuevo con las palancas activadas y el prompt v1 sobre la línea base.
4. **La revisión fue solo de forma.** Las decisiones del usuario del 23-oct están en cada `nota`: h2-03 reescrita, h2-06 solo la respuesta directa, h2-07 con 1.960 y h2-12 en el bloque A. Las reglas se probaron con respuestas ideales.
5. **Cautelas para el reporte:**
   - varias preguntas apuntan a las palancas, porque el usuario leyó su descripción;
   - la guarda P1 quita la agrupación por mes cuando la pregunta nombra un mes (h2-07); se encontró al revisar y no se corrigió, por el preregistro.

## Cómo se corre

```bash
cd nlp_agent
INVENTAIO_CLAVE_PRUEBA=… python -m evaluacion.correr --modelo qwen3:8b --conjunto holdout-2 \
  --core-api http://localhost:8010 --verificar --mejoras argumentos,agrupacion,aclaracion,sin_datos \
  --entorno local-holdout-2-mejoras --mlflow --historia INV-33
```
