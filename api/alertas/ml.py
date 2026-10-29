"""
InventAI/o — Alertas con IA (INV-28)
Funciones puras sobre la respuesta de POST /api/transferencias de ml_service
(la que guarda la caché de INV-23): no hacen I/O ni modifican lo guardado.
No hay modelo nuevo: el balance de INV-22 ya trae el pronóstico (q50), el
máximo y la urgencia por días hábiles hasta agotarse. Ver
docs/INV-28-requerimientos.md (V2 a V6, V10, V11 y V14).
"""
from core.productos import texto_cantidad, texto_numero
from schemas.alertas import URGENCIA_ORDER

RIESGO = "riesgo_desabastecimiento_ml"
SOBRESTOCK = "sobrestock_previsto_ml"
TIPOS_ML = (RIESGO, SOBRESTOCK)

# V5: urgencia del balance (INV-22: ≤ 5 días hábiles urgente, ≤ 10 alta) -> urgencia de alerta
URGENCIA_RIESGO = {"urgente": "critica", "alta": "alta"}
UMBRAL_DIAS = {"urgente": 5.0, "alta": 10.0}
Q50_MINIMO = 1.0            # V3: al menos 1 unidad (o kg) prevista en 15 días hábiles
FACTOR_SOBRESTOCK = 2.0     # V4: stock > 2 × máximo
FALTANTE_MINIMO = 1.0       # V14: con un traslado, desde 1 unidad (o kg) de déficit neto también va a compras


def _traslados_recibidos(respuesta: dict) -> dict:
    """(codigo_item, destino) -> traslados sugeridos hacia ese par (origen, cantidad, unidad, llega_tarde)."""
    recibidos: dict = {}
    for t in respuesta.get("traslados") or []:
        recibidos.setdefault((t["producto_id"], t["destino"]), []).append(t)
    return recibidos


def _accion(fila: dict, traslados: list) -> str:
    """V14: qué resuelve el riesgo según el balance de INV-22. Sin traslado, compra; con
    traslado, también compra si queda déficit neto. La cantidad la decide INV-21 en Recomendaciones."""
    if not traslados:
        return "compra"
    return "traslado_y_compra" if (fila.get("deficit_neto") or 0) >= FALTANTE_MINIMO else "traslado"


def _detalle_riesgo(stock: float, q50: float, dias: float, kg: bool, traslados: list, accion: str) -> str:
    # V14: el rótulo dice «según el pronóstico», como Predicciones
    texto = (f"Stock {texto_cantidad(stock, kg)}; según el pronóstico ({texto_cantidad(q50, kg)} en 15 días "
             f"hábiles) alcanza {texto_numero(dias, 1)} días hábiles")
    if traslados:   # V10: el riesgo es con el stock de la foto; el traslado se nombra, no se descuenta
        texto += "; traslado sugerido: " + " y ".join(
            f"{texto_cantidad(t['cantidad'], t['unidad'] == 'kg')} desde {t['origen']}"
            + (" (llega tarde)" if t.get("llega_tarde") else "") for t in traslados)
        if accion == "traslado_y_compra":
            texto += "; el faltante va a compras"
    else:
        texto += "; sin traslado posible: va a compras"
    return texto


def _detalle_sobrestock(stock: float, maximo: float, q50: float, kg: bool) -> str:
    return (f"Stock {texto_cantidad(stock, kg)}: {texto_numero(stock / maximo, 1)} veces el máximo "
            f"({texto_cantidad(maximo, kg)}); según el pronóstico, {texto_cantidad(q50, kg)} en 15 días hábiles")


def generar_alertas_ml(respuesta: dict, ids_producto: dict, id_ubicacion: dict, pares_reglas: set) -> list[dict]:
    """Las alertas con IA de todas las sucursales físicas, ordenadas como /api/alertas
    (urgencia y, dentro de ella, lo más grave primero).

    `ids_producto`: codigo_item -> id_producto. `id_ubicacion`: nombre -> id_sucursal.
    `pares_reglas`: (id_sucursal, id_producto) que las reglas ya marcan con
    stock_critico o stock_bajo (V2)."""
    fecha = respuesta["fecha_inventario"]
    fecha_pronostico = respuesta.get("fecha_pronostico")
    recibidos = _traslados_recibidos(respuesta)
    alertas = []
    for fila in respuesta.get("balance") or []:
        # C10: la Bodega no vende ni tiene pronóstico; sin_pronostico no trae q50
        if fila.get("tipo_ubicacion") != "sucursal" or fila.get("q50") is None or fila.get("stock") is None:
            continue
        q50, stock, kg = fila["q50"], fila["stock"], fila["unidad"] == "kg"
        id_producto = ids_producto.get(fila["producto_id"])
        id_sucursal = id_ubicacion[fila["sucursal"]]
        base = {
            "id_producto": id_producto, "codigo_item": fila["producto_id"],
            "nombre_producto": fila.get("nombre_producto"), "categoria": fila.get("categoria"),
            "sucursal": fila["sucursal"], "id_sucursal": id_sucursal, "tipo_ubicacion": "sucursal",
            "unidad": fila["unidad"], "stock": stock, "q50": q50, "fecha": fecha,
            "fecha_pronostico": fecha_pronostico, "accion": None, "llega_tarde": None,
        }
        urgencia = fila.get("urgencia")
        # V3 y V11: la urgencia del balance, sin redondear los días; el stock negativo ya es
        # inconsistencia_inventario en las reglas
        if urgencia in URGENCIA_RIESGO and q50 >= Q50_MINIMO and stock >= 0:
            dias = fila["dias_hasta_agotarse"]
            traslados = recibidos.get((fila["producto_id"], fila["sucursal"]), [])
            accion = _accion(fila, traslados)
            alertas.append({
                **base, "tipo": RIESGO, "urgencia": URGENCIA_RIESGO[urgencia],
                "origen": "ambos" if (id_sucursal, id_producto) in pares_reglas else "ml",
                "valor": round(dias, 2), "umbral": UMBRAL_DIAS[urgencia],
                "accion": accion, "llega_tarde": any(t.get("llega_tarde") for t in traslados) if traslados else None,
                "detalle": _detalle_riesgo(stock, q50, dias, kg, traslados, accion),
            })
        maximo = fila.get("maximo")
        # V4 y V6: independiente de sin_movimiento (demanda prevista frente a ventas pasadas)
        if maximo and q50 > 0 and stock > 0 and stock > FACTOR_SOBRESTOCK * maximo:
            alertas.append({
                **base, "tipo": SOBRESTOCK, "urgencia": "media", "origen": "ml",
                "valor": round(stock / maximo, 2), "umbral": FACTOR_SOBRESTOCK,
                "detalle": _detalle_sobrestock(stock, maximo, q50, kg),
            })
    # Riesgo: menos días primero; sobrestock: más veces el máximo primero
    alertas.sort(key=lambda a: (URGENCIA_ORDER[a["urgencia"]], a["valor"] if a["tipo"] == RIESGO else -a["valor"]))
    return alertas


def resumen_alertas_ml(alertas: list[dict]) -> dict:
    return {
        "total": len(alertas),
        "riesgo_desabastecimiento_ml": sum(a["tipo"] == RIESGO for a in alertas),
        "sobrestock_previsto_ml": sum(a["tipo"] == SOBRESTOCK for a in alertas),
        "critica": sum(a["urgencia"] == "critica" for a in alertas),
        "alta": sum(a["urgencia"] == "alta" for a in alertas),
        "media": sum(a["urgencia"] == "media" for a in alertas),
        "ambos": sum(a["origen"] == "ambos" for a in alertas),
        "ml": sum(a["origen"] == "ml" for a in alertas),
    }
