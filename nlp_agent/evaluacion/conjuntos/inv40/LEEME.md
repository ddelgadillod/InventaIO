# Conjunto `inv40` · Casos de INV-40

Son 18 preguntas que cubren los hallazgos del chat (`docs/INV-35-chat.md`) y el error de bodega (INV-77). Cada hallazgo tiene uno o más casos, con los tres roles donde aplica:
- la respuesta literal «<reporte> ventas </reporte>» (hallazgo H12);
- la dirección de los traslados (hallazgo H13);
- el estado general, el ranking y las ventas de un mes (hallazgo H14);
- el filtro por tipo que nadie pidió (hallazgo H15);
- los despachos de la Bodega Central (INV-77).

Responde al criterio 3 de la historia.

- **Congelado** el 18-nov-2026 (sha256 `c7a508f4c277…` de `preguntas.json`), antes de medir.
- **Uso:** solo contra el Core API, con datos al 31-dic-2025, es decir, contra staging. Se corre con `--conjunto inv40 --core-api … --verificar`.
- **Qué se califica:**
  - la herramienta y los argumentos esperados;
  - lo prohibido («<reporte», «no hay traslados»);
  - el rechazo sin cifras en la pregunta de otra sucursal;
  - los hechos reales donde se conocen: los 109 traslados que salen de la Bodega Central.
- **Hechos pendientes:** los hechos que faltan se pueden completar después con el Core API de staging. Son datos, no reglas: no cambian ninguna pregunta ni ninguna regla de calificación.
- **Nada se ajusta mirando sus fallas.** Si un cambio se diseña a partir de una de ellas, se dice en el reporte.
