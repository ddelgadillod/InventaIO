"""
Catálogo provisional de herramientas para el spike (INV-30, W10).

Las 8 herramientas (M) de la ficha de INV-32 más `historial_ventas` (S), que
pidieron las preguntas de ventas que agregó el usuario (17-oct), con descripciones breves en
español (un modelo de 8B elige peor entre muchas herramientas y descripciones
largas, y cada palabra cuenta en el presupuesto de tokens). En el spike no
llaman al Core API: el arnés responde con los resultados sintéticos de cada
pregunta. INV-32 las reemplaza por las reales, validadas contra el OpenAPI.
"""

SUCURSALES = ["PRINCIPAL", "LA 21", "GLORIETA", "BODEGA_CENTRAL"]
TIPOS_ALERTA = [
    "stock_critico", "stock_bajo", "sin_movimiento", "rotacion_baja", "inconsistencia_inventario",
    "riesgo_desabastecimiento_ml", "sobrestock_previsto_ml",
]


# Sin esto, los modelos llenan los filtros opcionales con valores inventados
# («todos», «null») o con uno de la lista (urgencia «normal»): sondeo del 17-oct
OMITIR = "Omítelo para no filtrar."


def _filtro(tipo: dict) -> dict:
    return {**tipo, "description": (tipo.get("description", "") + " " + OMITIR).strip()}


def _herramienta(nombre: str, descripcion: str, propiedades: dict, requeridos: list[str] | None = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": nombre,
            "description": descripcion,
            "parameters": {"type": "object", "properties": propiedades, "required": requeridos or []},
        },
    }


def herramientas(sucursales: list[str] = SUCURSALES) -> list[dict]:
    """El catálogo en el formato de Ollama. `sucursales` cambia en la variante de Colab."""
    tiendas = [s for s in sucursales if s != "BODEGA_CENTRAL"]
    sucursal = {"type": "string", "enum": sucursales, "description": f"Sucursal o BODEGA_CENTRAL. {OMITIR}"}
    return [
        _herramienta(
            "buscar_producto", "Busca productos por nombre, marca o código. Devuelve código, nombre y categoría.",
            {"texto": {"type": "string"}}, ["texto"],
        ),
        _herramienta("listar_sucursales", "Lista las sucursales y la Bodega Central con su tipo.", {}),
        _herramienta(
            "consultar_inventario",
            "Stock actual según la última foto de inventario, con semáforo y días de cobertura.",
            {
                "sucursal": sucursal,
                "producto": _filtro({"type": "string", "description": "Texto a buscar en el nombre."}),
                "categoria": _filtro({"type": "string"}),
                "estado": _filtro({"type": "string", "enum": ["ok", "bajo", "critico", "inconsistencia"]}),
            },
        ),
        _herramienta(
            "detalle_inventario", "Historial de los últimos 30 días del stock de un producto en una sucursal.",
            {"producto": {"type": "string"}, "sucursal": sucursal}, ["producto", "sucursal"],
        ),
        _herramienta(
            "listar_alertas",
            "Alertas activas. origen 'reglas': stock crítico o bajo, sin movimiento, rotación baja o inconsistencias. "
            "origen 'ia': riesgo de desabastecimiento o sobrestock según el pronóstico.",
            {
                "sucursal": sucursal,
                "origen": _filtro({"type": "string", "enum": ["reglas", "ia"]}),
                "tipo": _filtro({"type": "string", "enum": TIPOS_ALERTA}),
                "urgencia": _filtro({"type": "string", "enum": ["critica", "alta", "media"]}),
            },
        ),
        _herramienta("resumen_alertas", "Cuántas alertas hay por sucursal y por urgencia.", {"sucursal": sucursal}),
        _herramienta(
            "pronosticar_demanda", "Unidades que se venderán de un producto en una sucursal en los próximos 15 días hábiles.",
            {"producto": {"type": "string"}, "sucursal": {"type": "string", "enum": tiendas}}, ["producto", "sucursal"],
        ),
        _herramienta(
            "historial_ventas", "Ventas de un producto en los últimos meses, en periodos de 15 días hábiles.",
            {"producto": {"type": "string"}, "sucursal": {"type": "string", "enum": tiendas}}, ["producto"],
        ),
        _herramienta(
            "recomendar_compras", "Compras sugeridas a proveedores, con cantidad, urgencia y fecha de pedido.",
            {
                "sucursal": sucursal,
                "categoria": _filtro({"type": "string"}),
                "urgencia": _filtro({"type": "string", "enum": ["urgente", "alta", "normal"]}),
            },
        ),
    ]


def nombres() -> set[str]:
    return {h["function"]["name"] for h in herramientas()}
