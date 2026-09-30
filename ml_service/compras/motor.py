"""
InventAI/o — ML Service: recomendación de compras a proveedor (INV-21)

Compra lo que las transferencias de INV-22 no alcanzan a cubrir. Parte del
balance de `recomendar_transferencias` (en el mismo proceso, sin recalcular
traslados: descuenta todos los sugeridos, P15 de INV-22) y compra cuando la
posición no alcanza hasta que llegue el pedido siguiente. Las reglas (B1-B13)
salen de politicas_inv21.json; ver docs/INV-21-compras.md.

Por par producto × sucursal física con q50 > 0 (P = plazo a cubrir del grupo
del producto, en días hábiles; ver compras/calendario.py):
    posición     = max(stock, 0) + recibido                  [de INV-22]
    punto_pedido = q50(15) × P / 15
    nivel        = max(qα(15), q50(15)) × P / 15
    compra si posición < punto_pedido; necesidad = nivel − posición
Perecederos y frío compran por sucursal, directo. Lo seco suma las
necesidades del producto y descuenta el sobrante de la Bodega: si alcanza, no
se compra y el producto se cubre con traslado.

`recomendar_compras` es la función pública (la usa POST /api/compras);
`planificar_compras_producto` resuelve un producto sin I/O.
"""
import math
from typing import Optional

import pandas as pd

from compras.calendario import clasificar, planes_de_pedido
from compras.politicas import PoliticasCompras
from transferencias.motor import ORDEN_URGENCIA, Q50_CERO, TIPO_BODEGA, recomendar_transferencias
from transferencias.politicas import Politicas

EPSILON = 1e-9          # para que 7.0000000001 no se redondee hacia arriba a 8


def _arriba(x: float) -> int:
    """B6: cantidades enteras, siempre hacia arriba."""
    return max(0, math.ceil(x - EPSILON))


def _r(x: Optional[float], n: int = 2) -> Optional[float]:
    return None if x is None else round(float(x), n)


def _urgencia(dias: float, politicas: PoliticasCompras) -> str:
    if dias <= politicas.urgencia.urgente_dias:
        return "urgente"
    if dias <= politicas.urgencia.alta_dias:
        return "alta"
    return "normal"


def _fecha(t: pd.Timestamp) -> str:
    return t.date().isoformat()


def necesidad_par(fila: dict, plan, politicas: PoliticasCompras) -> Optional[dict]:
    """Punto de pedido, nivel y necesidad de una fila de sucursal del balance
    de INV-22. None si el par no compra: sin pronóstico, q50 = 0 (B10) o
    posición suficiente para el plazo (B4)."""
    q50 = fila["q50"]
    if q50 is None or q50 <= Q50_CERO:
        return None
    horizonte = politicas.horizonte_modelo_dias
    posicion = max(fila["stock"], 0.0) + fila["recibido"]            # B11: el stock negativo cuenta como 0
    escala = plan.dias_cubiertos / horizonte
    punto = q50 * escala
    if posicion >= punto:
        return None
    nivel = max(fila["limite_superior"], q50) * escala
    dias = posicion / (q50 / horizonte)
    return {
        "sucursal": fila["sucursal"], "posicion": posicion, "q50": q50, "limite_superior": fila["limite_superior"],
        "punto_pedido": punto, "nivel": nivel, "necesidad": nivel - posicion,
        "dias_hasta_agotarse": dias, "urgencia": _urgencia(dias, politicas),
        "llega_tarde": dias < plan.dias_hasta_llegada,                  # B12: se compra igual
        "motivo": "stock_negativo" if fila["estado"] == "stock_negativo" else "reposicion",
    }


def _mas_urgente(detalle: list) -> dict:
    return min(detalle, key=lambda d: (ORDEN_URGENCIA[d["urgencia"]], d["dias_hasta_agotarse"]))


def _detalle_redondeado(detalle: list) -> list:
    return [{**d, "posicion": _r(d["posicion"]), "punto_pedido": _r(d["punto_pedido"]), "nivel": _r(d["nivel"]),
             "necesidad": _r(d["necesidad"]), "dias_hasta_agotarse": _r(d["dias_hasta_agotarse"], 1)}
            for d in detalle]


def _linea(codigo: str, destino: str, plan, unidad: str, cantidad: int, necesidad: float,
           sobrante: Optional[float], detalle: list) -> dict:
    critico = _mas_urgente(detalle)
    return {
        "producto_id": codigo, "destino": destino, "tipo_destino": plan.tipo_destino, "grupo": plan.grupo,
        "cantidad": cantidad, "unidad": unidad, "urgencia": critico["urgencia"],
        "dias_hasta_agotarse": _r(critico["dias_hasta_agotarse"], 1),
        "fecha_pedido": _fecha(plan.fecha_pedido), "fecha_llegada": _fecha(plan.fecha_llegada),
        "fecha_llegada_sucursal": _fecha(plan.fecha_llegada_sucursal),
        "llega_tarde": any(d["llega_tarde"] for d in detalle),
        "necesidad": _r(necesidad), "sobrante_bodega": _r(sobrante),
        "motivo": "stock_negativo" if any(d["motivo"] == "stock_negativo" for d in detalle) else "reposicion",
        "detalle": _detalle_redondeado(detalle),
    }


def planificar_compras_producto(producto: dict, filas: list, planes: dict, politicas: PoliticasCompras,
                                politicas_traslados: Politicas) -> dict:
    """Compras, producto a cubrir con traslado y alertas de un producto. Sin I/O.

    `filas`: las filas del producto en el balance de INV-22 (Bodega y
    sucursales); `planes`: los de compras/calendario.planes_de_pedido."""
    codigo = producto["codigo_item"]
    kilo = bool(producto.get("se_vende_por_kilo"))
    unidad = "kg" if kilo else "unidad"
    grupo, tipo_destino = clasificar(producto, politicas)
    plan = planes[(grupo, tipo_destino)]

    alertas, detalle, sobrante = [], [], 0.0
    for fila in filas:
        if fila["estado"] == "stock_negativo":                           # B11
            compra = fila["tipo_ubicacion"] != TIPO_BODEGA and (fila["q50"] or 0.0) > Q50_CERO
            alertas.append({
                "producto_id": codigo, "sucursal": fila["sucursal"], "tipo": "posible_inconsistencia_inventario",
                "stock": fila["stock"], "accion": "compra_urgente" if compra else "verificar_conteo",
                "detalle": ("Stock negativo en la foto: verificar el conteo. "
                            + ("Se compra con el stock tomado como 0." if compra
                               else "No se compra: el par no tiene pronóstico o su mediana es 0."))})
        if fila["tipo_ubicacion"] == TIPO_BODEGA:
            if fila["estado"] == "bodega":
                # B9: lo que la Bodega no envió; en kilos, con la pérdida del traslado que falta (Q9)
                factor = 1.0 - politicas_traslados.cantidades.descuento_kilos if kilo else 1.0
                sobrante = max(0.0, fila["excedente_sin_destino"] or 0.0) * factor
            continue
        necesidad = necesidad_par(fila, plan, politicas)
        if necesidad is not None:
            detalle.append(necesidad)

    compras, cubrir = [], []
    if detalle and tipo_destino == "sucursal":                            # B8: directo, una línea por sucursal
        for d in detalle:
            cantidad = max(_arriba(d["necesidad"]), politicas.minimo_linea)
            compras.append(_linea(codigo, d["sucursal"], plan, unidad, cantidad, d["necesidad"], None, [d]))
    elif detalle:                                                         # B9: una línea para la Bodega
        total = sum(d["necesidad"] for d in detalle)
        neto = total - sobrante
        if neto > EPSILON:
            cantidad = max(_arriba(neto), politicas.minimo_linea)
            compras.append(_linea(codigo, "BODEGA_CENTRAL", plan, unidad, cantidad, total, sobrante, detalle))
        else:
            critico = _mas_urgente(detalle)
            cubrir.append({"producto_id": codigo, "necesidad": _r(total), "sobrante_bodega": _r(sobrante),
                           "unidad": unidad, "urgencia": critico["urgencia"],
                           "dias_hasta_agotarse": _r(critico["dias_hasta_agotarse"], 1),
                           "detalle": _detalle_redondeado(detalle)})
    return {"compras": compras, "cubrir_con_traslado": cubrir, "alertas": alertas}


def recomendar_compras(bodega, modelos, politicas: PoliticasCompras, politicas_traslados: Politicas,
                       productos: Optional[list] = None) -> dict:
    """Compras sugeridas, productos a cubrir con traslado y alertas.

    `bodega`, `modelos` y `productos` como en recomendar_transferencias, que
    se llama primero con las políticas de INV-22. Lanza lo mismo que ella
    (FotoSinVentas, CalendarioInsuficiente, LookupError, errores de
    SQLAlchemy); el router los traduce a HTTP."""
    traslados = recomendar_transferencias(bodega, modelos, politicas_traslados, productos=productos)
    calendario = bodega.calendario()
    foto = pd.Timestamp(traslados["fecha_inventario"])
    planes = planes_de_pedido(calendario, foto, politicas, politicas_traslados)

    filas_por_producto = {}
    for fila in traslados["balance"]:
        filas_por_producto.setdefault(fila["producto_id"], []).append(fila)
    catalogo = bodega.productos(list(filas_por_producto)) if filas_por_producto else {}

    compras, cubrir, alertas = [], [], []
    for codigo, filas in filas_por_producto.items():
        r = planificar_compras_producto(catalogo[codigo], filas, planes, politicas, politicas_traslados)
        compras += r["compras"]
        cubrir += r["cubrir_con_traslado"]
        alertas += r["alertas"]

    compras.sort(key=lambda c: (ORDEN_URGENCIA[c["urgencia"]], c["producto_id"], c["destino"]))
    cantidad = {"unidad": 0, "kg": 0}
    for c in compras:
        cantidad[c["unidad"]] += c["cantidad"]
    return {
        "fecha_inventario": traslados["fecha_inventario"],
        "fecha_pronostico": traslados["fecha_pronostico"],
        "lead_time_dias": politicas.lead_time_dias,
        "politicas": {"inv21": {"version": politicas.version, "fecha": politicas.fecha.isoformat()},
                      "inv22": traslados["politicas"]},
        "calendario": [{
            "grupo": p.grupo, "tipo_destino": p.tipo_destino, "fecha_pedido": _fecha(p.fecha_pedido),
            "fecha_llegada": _fecha(p.fecha_llegada), "fecha_llegada_sucursal": _fecha(p.fecha_llegada_sucursal),
            "pedido_siguiente": _fecha(p.pedido_siguiente), "cubre_hasta": _fecha(p.cubre_hasta),
            "dias_cubiertos": p.dias_cubiertos, "dias_hasta_llegada": p.dias_hasta_llegada,
        } for p in planes.values()],
        "compras": compras,
        "cubrir_con_traslado": cubrir,
        "alertas": alertas,
        "no_encontrados": traslados["no_encontrados"],
        "resumen": {
            "productos": traslados["resumen"]["productos"],
            "lineas": len(compras),
            "lineas_sucursal": sum(c["tipo_destino"] == "sucursal" for c in compras),
            "lineas_bodega": sum(c["tipo_destino"] == TIPO_BODEGA for c in compras),
            "cantidad": cantidad,
            "cubiertos_por_bodega": len(cubrir),
            "alertas": len(alertas),
            "pares_sin_pronostico": sum(f["estado"] == "sin_pronostico" for f in traslados["balance"]),
        },
    }
