# Holdout de INV-33

Escrito por el usuario el 23-oct-2026 en la plantilla de INV-33 y aprobado por él. Se congeló ese mismo día, **antes de medir**.

| Qué | Valor |
| --- | --- |
| Archivo | `preguntas.json` |
| sha256 del archivo | `ad7bcceb215ef45484d2adaa60c2cdc26908dce68953e33cd4813f050e40c5d2` |
| Huella del conjunto (`huella_conjunto` de cada corrida) | `c86de2eaa800` |
| Preguntas | 15: A 3, B 1, C 3, D 4, E 2, F 2. h-06 trae turnos previos |
| Datos | Solo reales: Core API, foto del 31-dic-2025 |

## Para qué es

El prompt v2 se ajustó mirando las fallas del conjunto v1. El holdout mide cuánto de esa mejora generaliza a preguntas que ni el agente ni quien ajustó el prompt habían visto.

## Reglas

1. **No se cambia.** `tests/test_conjunto_holdout.py` falla si el archivo ya no tiene el sha256 de arriba.
2. **Se corre con el prompt vigente y solo se reporta.** No se ajusta el prompt mirando estas preguntas. Si después se ajusta, el holdout deja de ser limpio y hay que decirlo al reportar.
3. **La revisión fue solo de forma.** Se revisó que cada pregunta se pudiera calificar: que la herramienta exista, que el dato esté en la bodega y que la regla se pueda cumplir. Las reglas se probaron con respuestas ideales escritas a mano. La dificultad la decidió el usuario.
4. **Los cambios aprobados el 23-oct están en cada `nota`:**
   - h-03: el destino pasó a LA 21.
   - h-04, h-05 y h-11: pasaron al bloque D.
   - h-06: el rol pasó a gerente.
   - h-07: pasó al bloque C.

## Cómo se corre

```bash
cd nlp_agent
INVENTAIO_CLAVE_PRUEBA=… python -m evaluacion.correr --modelo qwen3:8b --conjunto holdout \
  --core-api http://localhost:8010 --verificar --entorno local-holdout --mlflow --historia INV-33
```

Queda en el experimento `agente-conjunto-holdout` de MLflow. No tiene línea base: no hay con qué compararlo.
