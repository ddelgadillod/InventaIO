"""
InventAI/o — Filtro por la fecha de la foto de inventario (INV-41, docs/INV-41-requerimientos.md H14)

Las consultas filtran la fecha con `JOIN dw.dim_tiempo t ... WHERE t.fecha = :fecha`. Postgres estima esa unión con
la selectividad de dim_tiempo (miles de fechas), no con la de la tabla de hechos (dos fotos), y espera 2 filas
donde hay miles. Con un filtro de sucursal elige bucles anidados: la lista del inventario de un administrador de
sucursal tardaba 4,7 s en vez de 0,2 s.

Filtrar además por el id_tiempo de la tabla de hechos, resuelto en una subconsulta, le da la estimación correcta. El
resultado no cambia: es la misma fecha.
"""


def mismo_dia(alias: str) -> str:
    """La condición extra para la tabla de hechos `alias`, con el parámetro :fecha de la consulta."""
    return f"{alias}.id_tiempo = (SELECT id_tiempo FROM dw.dim_tiempo WHERE fecha = :fecha)"
