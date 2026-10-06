"""
InventAI/o — Reglas de producto compartidas por los routers (INV-26 fix, J5)
"""
from decimal import ROUND_HALF_UP, Decimal


def unidad_venta(se_vende_por_kilo: bool) -> str:
    """En qué se cuentan el stock y las ventas, como `unidad` en ml_service.
    unidad_medida no sirve para esto: es la de la presentación (g, ml)."""
    return "kg" if se_vende_por_kilo else "unidad"


def _redondear(valor, decimales: int) -> Decimal:
    """Redondea como Intl.NumberFormat en la app: sobre el decimal corto del
    número (-2.05, no el binario -2.04999…) y los empates lejos de 0. Con
    round() de Python, -2,05 kg salía "-2,0" en la alerta y "-2,1" en pantalla."""
    redondeado = Decimal(repr(float(valor))).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)
    return abs(redondeado) if redondeado == 0 else redondeado


def texto_numero(valor, decimales: int) -> str:
    """Número como lo muestra la app (es-CO): punto de miles y coma decimal."""
    texto = f"{_redondear(valor, decimales):,.{decimales}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def texto_cantidad(valor, se_vende_por_kilo: bool) -> str:
    """Cantidad de stock o de ventas para los textos de la API, con la regla de
    fmtCantidad en la app: "77,1 kg" en los productos por kilo; "1 unidad" y
    "4.024 unidades" en los demás. Una cantidad distinta de 0 no se redondea a
    0: -0,01 kg no es "-0,0 kg"."""
    decimales = 1 if se_vende_por_kilo else 0
    while decimales < 3 and valor != 0 and _redondear(valor, decimales) == 0:
        decimales += 1
    if se_vende_por_kilo:
        return f"{texto_numero(valor, decimales)} kg"
    return f"{texto_numero(valor, decimales)} {'unidad' if abs(_redondear(valor, decimales)) == 1 else 'unidades'}"


def texto_dias(dias) -> str:
    """Días de cobertura como los muestra la app: "5,3 d"."""
    return f"{texto_numero(dias, 1)} d"
