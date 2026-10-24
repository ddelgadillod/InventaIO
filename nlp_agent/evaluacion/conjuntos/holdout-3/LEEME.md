# Holdout-3 de INV-33

Escrito por el usuario el 24-oct-2026 como **muestra natural** (sin dirigirlo a las correcciones) y aprobado por él. Se congeló ese mismo día, **antes de medir**. Decide la integración de INV-33 (§3g de `docs/INV-33-requerimientos.md`).

| Qué | Valor |
| --- | --- |
| Archivo | `preguntas.json` |
| sha256 del archivo | `1227d55011b1f1b991166cdfceca1db99144a525b01e8a18b6b34e678f7f27de` |
| Huella del conjunto | `6f0fc6b8f648` |
| Preregistro | `PREREGISTRO.md`, escrito antes de medir las correcciones, con adendas y el congelamiento del código (`42172fa`) antes de abrir la plantilla; sha256 `f3248a310812eab1751fa92ae2213bf3952e6667ea66d8f79886977b561c5170` |
| Preguntas | 15: A 4, B 3, C 2, D 2, E 2, F 2. h3-06 trae turnos previos |
| Datos | Solo reales: Core API, foto del 31-dic-2025 |

## Configuraciones (regla 10 del preregistro)

1. El agente del 22-oct (commit `6a54423`), en un worktree temporal.
2. **F:** las palancas activas del 23-oct más C2 a C8 (`--mejoras final`). C1 y C9 quedaron apagadas por la serie del 24-oct.

La extracción de entidades (3) **no se corre**: no pasó la regla 9 (79,1 % frente a 80,2 % en lo ya visto). Las dos corridas usan el arnés con el límite de 120 s por pregunta (`297d202`).

## Reglas

- No se cambia. `tests/test_conjunto_holdout3.py` falla si el archivo ya no tiene el sha256 de arriba.
- La revisión fue solo de forma. Las decisiones del usuario del 24-oct están en cada `nota`: h3-02 vale con críticas o altas, h3-03 con urgente, y en h3-05 vale la respuesta directa o preguntar cuál.
- Limitación conocida: si el agente dice «60 días» en h3-04, el verificador marca ese 60 (viene de su propio argumento `dias`). No se corrige, por el congelamiento.
