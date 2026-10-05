"""
InventAI/o — Reglas de producto compartidas por los routers (INV-26 fix, J5)
"""


def unidad_venta(se_vende_por_kilo: bool) -> str:
    """En qué se cuentan el stock y las ventas, como `unidad` en ml_service.
    unidad_medida no sirve para esto: es la de la presentación (g, ml)."""
    return "kg" if se_vende_por_kilo else "unidad"
