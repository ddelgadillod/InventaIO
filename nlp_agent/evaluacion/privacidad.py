"""Cifras en pesos fuera del repositorio (INV-33, B4). Las ventas reales en pesos no se publican: `historial_ventas`
trae valor y margen, y en el modo real el arnés guarda lo que devuelven las herramientas y la respuesta del modelo.
Antes de escribir, las cifras en pesos se reemplazan por «$ [omitido]»."""
import re
from typing import Any

OMITIDO = "$ [omitido]"
PESOS = re.compile(
    r"\$\s?-?\d[\d.]*(?:,\d+)?(?:\s*(?:mil\s+millones|millones|millón|mil))?"
    r"|-?\d[\d.]*(?:,\d+)?(?:\s*(?:mil\s+millones|millones|millón|mil))?\s*(?:de\s+)?(?:pesos|COP)\b",
    re.IGNORECASE)


def sin_pesos(valor: Any) -> Any:
    """Copia de `valor` (texto, lista o dict) sin cifras en pesos."""
    if isinstance(valor, str):
        return PESOS.sub(OMITIDO, valor)
    if isinstance(valor, list):
        return [sin_pesos(v) for v in valor]
    if isinstance(valor, dict):
        return {k: sin_pesos(v) for k, v in valor.items()}
    return valor


def tiene_pesos(valor: Any) -> bool:
    return sin_pesos(valor) != valor
