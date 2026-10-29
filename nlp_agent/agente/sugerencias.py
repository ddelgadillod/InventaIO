"""
Sugerencias de seguimiento (INV-33, criterio 7, decisión Z6): deterministas, según las herramientas que se usaron
en la respuesta, hasta 3. Van en `done.sugerencias` y el chat (INV-35) las muestra como botones. No usan el modelo:
no pueden inventar cifras ni prometer lo que el agente no hace.
"""
MAX_SUGERENCIAS = 3
POR_HERRAMIENTA = {
    "consultar_inventario": ("¿Quieres el pronóstico de demanda de ese producto?", "¿Quieres las compras sugeridas?"),
    "resumen_inventario": ("¿Quieres ver los productos en estado crítico?", "¿Quieres los traslados sugeridos?"),
    "listar_alertas": ("¿Quieres el resumen de alertas por sucursal?", "¿Quieres las compras sugeridas?"),
    "resumen_alertas": ("¿Quieres ver las alertas críticas?",),
    "pronosticar_demanda": ("¿Quieres compararlo con el inventario actual?", "¿Quieres el historial de ventas?"),
    "historial_ventas": ("¿Quieres el pronóstico de los próximos 15 días hábiles?", "¿Quieres verlo por año?"),
    "recomendar_compras": ("¿Quieres los traslados sugeridos?",),
    "recomendar_traslados": ("¿Quieres las compras sugeridas?", "¿Quieres solo los urgentes?"),
    "buscar_producto": ("¿Quieres el inventario de ese producto?",),
    "buscar_en_glosario": ("¿Quieres ver cómo está el inventario?",),
}
GENERALES = ("¿Qué productos están en estado crítico?", "¿Qué compras se sugieren?")


def sugerencias(herramientas: list[str], hubo_error: bool = False) -> list[str]:
    """Las de las herramientas usadas, en orden y sin repetir; sin herramientas, las generales. Si la respuesta
    fue un error o un rechazo, ninguna."""
    if hubo_error:
        return []
    salida: list[str] = []
    for h in herramientas:
        for s in POR_HERRAMIENTA.get(h, ()):
            if s not in salida:
                salida.append(s)
    return (salida or list(GENERALES))[:MAX_SUGERENCIAS]
