"""
Cantidades y números como los muestra la app (INV-32, criterio 4).

Es la misma regla de `texto_cantidad` del Core API (api/core/productos.py) y de
`fmtCantidad` en la app: "77,1 kg" en los productos por kilo; "1 unidad" y
"4.024 unidades" en los demás; punto de miles, coma decimal y los empates lejos
de 0. El agente no importa código del Core API (son servicios e imágenes
distintos), así que la regla se copia y las pruebas repiten sus casos.
"""
from decimal import ROUND_HALF_UP, Decimal


def _redondear(valor, decimales: int) -> Decimal:
    redondeado = Decimal(repr(float(valor))).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)
    return abs(redondeado) if redondeado == 0 else redondeado


def texto_numero(valor, decimales: int = 0) -> str:
    texto = f"{_redondear(valor, decimales):,.{decimales}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def texto_cantidad(valor, se_vende_por_kilo: bool) -> str:
    decimales = 1 if se_vende_por_kilo else 0
    while decimales < 3 and valor != 0 and _redondear(valor, decimales) == 0:
        decimales += 1
    if se_vende_por_kilo:
        return f"{texto_numero(valor, decimales)} kg"
    return f"{texto_numero(valor, decimales)} {'unidad' if abs(_redondear(valor, decimales)) == 1 else 'unidades'}"


def texto_dias(dias) -> str:
    return f"{texto_numero(dias, 1)} d"


def por_kilo(unidad: str | None) -> bool:
    """El Core API dice `unidad`: 'kg' si se vende por kilo; si no, 'unidad'."""
    return unidad == "kg"
