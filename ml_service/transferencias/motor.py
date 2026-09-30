"""
InventAI/o — ML Service: recomendación de transferencias entre sucursales (INV-22)

Recomienda traslados de stock desde la Bodega Central y entre sucursales
físicas antes de comprar a proveedor. Usa la foto de inventario
(dw.fact_inventario) y el pronóstico a 15 días hábiles de /api/predict, con
el mismo código y en el mismo proceso (prediccion/servicio.py). Las reglas
(P1-P15) salen de politicas_inv22.json; ver docs/INV-22-transferencias.md.

`recomendar_transferencias` es la función pública: la usa POST
/api/transferencias y la puede llamar INV-21 en el mismo proceso para tomar
balance[].deficit_neto y alertas sin recalcular traslados. Lee la bodega por
lotes (unas pocas consultas para todo el catálogo, nunca una por par),
pronostica todos los pares en un lote y delega cada producto en
`planificar_producto`, que no hace I/O: recibe stocks y pronósticos y
devuelve traslados, balance y alertas.

Por producto (s = sucursal física con pronóstico y q50 > 0):
    objetivo_s  = q50(15)
    máximo_s    = max(qα(15) × (1 + margen), objetivo_s)
    excedente_s = max(0, stock_s − max(máximo_s, unidades_exhibicion))
    déficit_s   = max(0, objetivo_s − stock_s)
    cobertura_s = (stock_s + recibido_s) / (q50(15) / 15)       [días hábiles]
La Bodega no tiene demanda: todo su stock positivo es excedente (P3).
"""
import math
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from prediccion.features import Calendario, HistoriaInsuficiente
from prediccion.servicio import PronosticadorNivel1, Pronostico
from transferencias.politicas import Politicas

TIPOS_SUCURSAL_FISICA = ("principal", "estandar")   # las del modelo (tipos_sucursal_modelo)
TIPO_BODEGA = "bodega_central"
Q50_CERO = 1e-9          # q50 por debajo de esto es cero (el motor ya recorta en 0)
EPSILON = 1e-9           # para que 9.0000000001 no se redondee hacia abajo a 8
ORDEN_URGENCIA = {"urgente": 0, "alta": 1, "normal": 2, "vigilancia": 3}
SERIE_VACIA = pd.Series(dtype=float)


class FotoSinVentas(Exception):
    """P8: la foto de inventario es más nueva que la última venta cargada."""

    def __init__(self, fecha_inventario: pd.Timestamp, fecha_ventas: pd.Timestamp):
        self.fecha_inventario = fecha_inventario
        self.fecha_ventas = fecha_ventas
        self.dias = (fecha_inventario - fecha_ventas).days
        super().__init__(
            f"La foto de inventario ({fecha_inventario.date()}) es posterior a la última venta cargada "
            f"({fecha_ventas.date()}): faltan las ventas de {self.dias} día(s). No se recomiendan "
            "transferencias hasta cargarlas.")


@dataclass(frozen=True)
class Llegada:
    """Cuándo llegan los traslados sugeridos (el mismo día para todos)."""
    fecha: pd.Timestamp
    dias_habiles: int


def calcular_llegada(calendario: Calendario, fecha_foto, politicas: Politicas) -> Llegada:
    """P13 / Q7: el siguiente día fijo de traslado después de la foto o, si no
    hay días fijos, N días hábiles después. Días hábiles: los de la historia y,
    después del último dato, los de dim_tiempo que no son cierre programado."""
    n = politicas.traslado.dias_habiles_si_no_hay_dias_fijos
    dias = calendario.proximos_habiles(fecha_foto, max(n, 14))
    fijos = politicas.traslado.dias_semana_iso()
    if fijos:
        for i, dia in enumerate(dias, start=1):
            if dia.weekday() in fijos:
                return Llegada(dia, i)
    return Llegada(dias[n - 1], n)


@dataclass
class _Ubicacion:
    """Estado de trabajo de un producto en una ubicación."""
    nombre: str
    tipo: str                               # "bodega_central" o "sucursal"
    stock: Optional[float]                  # None: sin fila en la foto (cuenta como 0)
    pronostico: Optional[Pronostico] = None
    estado: str = ""
    objetivo: Optional[float] = None
    maximo: Optional[float] = None
    excedente: Optional[float] = None
    deficit: Optional[float] = None
    deficit_vigilancia: Optional[float] = None
    dias_hasta_agotarse: Optional[float] = None
    urgencia: Optional[str] = None
    disponible: int = 0                     # lo que puede despachar (unidades o kg enteros)
    capacidad: int = 0                      # lo que puede recibir
    recibido: int = 0
    enviado: int = 0

    @property
    def q50(self) -> float:
        return self.pronostico.q50

    def cobertura(self, extra: int, horizonte: int) -> float:
        return (max(self.stock or 0.0, 0.0) + self.recibido + extra) / (self.q50 / horizonte)


def _entero(x: float) -> int:
    """P11: cantidades enteras, siempre hacia abajo."""
    return max(0, math.floor(x + EPSILON))


def _r(x: Optional[float], n: int = 2) -> Optional[float]:
    return None if x is None else round(float(x), n)


def _urgencia(dias: float, politicas: Politicas) -> str:
    if dias <= politicas.urgencia.urgente_dias:
        return "urgente"
    if dias <= politicas.urgencia.alta_dias:
        return "alta"
    return "normal"


def _clasificar_bodega(u: _Ubicacion, politicas: Politicas, factor: float):
    if u.stock < 0:
        u.estado = "stock_negativo"      # A4: anomalía, no se traslada
        return
    u.estado = "bodega"
    u.excedente = max(0.0, u.stock - politicas.reserva_bodega)          # P3
    u.disponible = _entero(u.excedente * factor)                          # Q9


def _clasificar_sucursal(u: _Ubicacion, politicas: Politicas, perecedero: bool, factor: float):
    s = max(u.stock or 0.0, 0.0)          # P7: el stock negativo se toma como 0
    pron = u.pronostico
    horizonte = politicas.horizonte_dias
    if pron is not None:
        if pron.q50 > Q50_CERO:
            u.dias_hasta_agotarse = s / (pron.q50 / horizonte)
            u.urgencia = _urgencia(u.dias_hasta_agotarse, politicas)
        else:
            u.urgencia = "vigilancia"       # P14: nunca urgente

    if u.stock is not None and u.stock < 0:
        u.estado = "stock_negativo"        # A4, P7: no se traslada; va al pedido con stock 0
        if pron is not None:
            u.objetivo = pron.q50
            u.deficit = max(0.0, pron.q50 - s)
        return
    if pron is None:
        u.estado = "sin_pronostico"        # P6, Q4: no participa; su stock no es excedente
        return
    if pron.q50 <= Q50_CERO:
        u.estado = "vigilancia"            # P14, Q5: no es origen; solo recibe sobrante, hasta qα
        u.objetivo, u.deficit = 0.0, 0.0
        u.deficit_vigilancia = max(0.0, pron.limite_superior - s)
        u.capacidad = 0 if perecedero else _entero(u.deficit_vigilancia)      # P4
        return

    margen = politicas.stock_maximo.margen_perecedero if perecedero else politicas.stock_maximo.margen_no_perecedero
    u.objetivo = pron.q50                                                    # P2
    u.maximo = max(pron.limite_superior * (1 + margen), u.objetivo)          # P1
    u.excedente = max(0.0, s - max(u.maximo, politicas.stock_maximo.unidades_exhibicion))
    u.deficit = max(0.0, u.objetivo - s)
    if u.excedente > 0:
        u.estado = "origen"
        u.disponible = _entero(u.excedente * factor)
    elif u.deficit > 0:
        u.estado = "destino"
        u.capacidad = _entero(u.deficit)
    else:
        u.estado = "equilibrio"


def _repartir(destinos: list, total: int, minimo: int, horizonte: int) -> dict:
    """P9: si el excedente alcanza, cada destino recibe su déficit. Si no, cada
    unidad va al destino con menor cobertura (desempate: mayor q50). Un destino
    entra al reparto con un primer bloque del mínimo (P11): repartir de a una
    unidad dejaría traslados menores al mínimo que después se descartan."""
    if total >= sum(d.capacidad for d in destinos):
        return {d.nombre: d.capacidad for d in destinos}
    asignado = {d.nombre: 0 for d in destinos}
    restante = total
    while restante > 0:
        candidatos = [d for d in destinos
                      if asignado[d.nombre] < d.capacidad and (asignado[d.nombre] > 0 or restante >= minimo)]
        if not candidatos:
            break
        d = min(candidatos, key=lambda d: (d.cobertura(asignado[d.nombre], horizonte), -d.q50, d.nombre))
        paso = 1 if asignado[d.nombre] else minimo
        asignado[d.nombre] += paso
        restante -= paso
    return asignado


def _siguiente_origen(origenes: list, minimo: int) -> Optional[_Ubicacion]:
    """P10: primero la Bodega; luego la sucursal con más excedente restante.
    Un origen con menos del mínimo disponible no puede armar un traslado."""
    con_stock = [o for o in origenes if o.disponible >= minimo]
    bodegas = [o for o in con_stock if o.tipo == TIPO_BODEGA]
    if bodegas:
        return bodegas[0]
    return min(con_stock, key=lambda o: (-o.disponible, o.nombre), default=None)


def _servir(destino: _Ubicacion, cantidad: int, origenes: list, minimo: int, piezas: list):
    """Asigna orígenes a lo que recibe un destino (paso 8). Cada par origen →
    destino es un traslado de al menos el mínimo (paso 9); un resto menor queda
    sin servir, en el origen, y el déficit sigue en el neto."""
    pendiente = cantidad
    while pendiente >= minimo:
        origen = _siguiente_origen(origenes, minimo)
        if origen is None:
            break
        q = min(pendiente, origen.disponible)
        origen.disponible -= q
        origen.enviado += q
        destino.recibido += q
        pendiente -= q
        piezas.append((origen, destino, q))


def planificar_producto(producto: dict, stocks: dict, bodegas: list, sucursales: list, pronosticos: dict,
                        politicas: Politicas, llegada: Llegada, motivos: Optional[dict] = None) -> dict:
    """Traslados, balance y alertas de un producto. Sin I/O.

    `stocks`: {ubicación: stock de la foto} (una ubicación sin fila no está);
    `bodegas` y `sucursales`: nombres de la Bodega Central y de las sucursales
    físicas; `pronosticos`: {sucursal: Pronostico o None}; `motivos`: por qué
    no hay pronóstico, para la alerta."""
    codigo = producto["codigo_item"]
    perecedero = bool(producto.get("es_perecedero_estricto"))
    kilo = bool(producto.get("se_vende_por_kilo"))
    unidad = "kg" if kilo else "unidad"
    factor = 1.0 - politicas.cantidades.descuento_kilos if kilo else 1.0      # Q9
    minimo = politicas.cantidades.minimo
    horizonte = politicas.horizonte_dias
    motivos = motivos or {}

    ubicaciones = []
    for nombre in bodegas:
        if nombre in stocks:
            u = _Ubicacion(nombre, TIPO_BODEGA, stocks[nombre])
            _clasificar_bodega(u, politicas, factor)
            ubicaciones.append(u)
    for nombre in sucursales:
        stock, pron = stocks.get(nombre), pronosticos.get(nombre)
        if stock is None and pron is None:
            continue              # ni stock ni pronóstico: el par no existe para el negocio
        u = _Ubicacion(nombre, "sucursal", stock, pron)
        _clasificar_sucursal(u, politicas, perecedero, factor)
        ubicaciones.append(u)

    # Pasos 6-9: reparto del excedente entre destinos con q50 > 0. Nada entra a
    # la Bodega (P12): los perecederos (P4) y los de frío (P5) solo van directo
    # de una ubicación a una sucursal; la Bodega despacha lo que ya tiene (A3).
    origenes = [u for u in ubicaciones if u.estado in ("bodega", "origen")]
    destinos = [u for u in ubicaciones if u.estado == "destino" and u.capacidad >= minimo]
    usable = sum(o.disponible for o in origenes if o.disponible >= minimo)
    piezas = []
    if destinos and usable >= minimo:
        asignado = _repartir(destinos, usable, minimo, horizonte)
        for d in sorted(destinos, key=lambda d: (d.cobertura(0, horizonte), -d.q50, d.nombre)):
            _servir(d, asignado[d.nombre], origenes, minimo, piezas)

    # Paso 10 (P14): el sobrante va a los pares en vigilancia que no son
    # perecederos, de mayor a menor límite superior, con las mismas reglas.
    vigilancia = [u for u in ubicaciones if u.estado == "vigilancia" and u.capacidad >= minimo]
    for v in sorted(vigilancia, key=lambda v: (-v.pronostico.limite_superior, v.nombre)):
        _servir(v, v.capacidad, origenes, minimo, piezas)

    traslados = [{
        "producto_id": codigo, "origen": o.nombre, "destino": d.nombre, "cantidad": q, "unidad": unidad,
        "urgencia": d.urgencia, "dias_hasta_agotarse": _r(d.dias_hasta_agotarse, 1),
        "fecha_llegada": llegada.fecha.date().isoformat(), "dias_habiles_llegada": llegada.dias_habiles,
        # P13: se sugiere igual aunque llegue después de agotarse
        "llega_tarde": d.dias_hasta_agotarse is not None and d.dias_hasta_agotarse < llegada.dias_habiles,
    } for o, d, q in piezas]

    balance = [{
        "producto_id": codigo, "sucursal": u.nombre, "tipo_ubicacion": u.tipo,
        "rama": u.pronostico.rama if u.pronostico else None,
        "stock": u.stock if u.stock is not None else 0.0,
        "q50": _r(u.pronostico.q50) if u.pronostico else None,
        "limite_superior": _r(u.pronostico.limite_superior) if u.pronostico else None,
        "objetivo": _r(u.objetivo), "maximo": _r(u.maximo), "excedente": _r(u.excedente),
        "excedente_sin_destino": _r(max(0.0, u.excedente - u.enviado)) if u.excedente is not None else None,
        "deficit": _r(u.deficit), "deficit_vigilancia": _r(u.deficit_vigilancia),
        "recibido": u.recibido, "enviado": u.enviado,
        "deficit_neto": _r(max(0.0, u.deficit - u.recibido)) if u.deficit is not None else None,
        "estado": u.estado, "urgencia": u.urgencia, "dias_hasta_agotarse": _r(u.dias_hasta_agotarse, 1),
        "unidad": unidad,
    } for u in ubicaciones]

    alertas = []
    for u in ubicaciones:
        if u.estado == "stock_negativo":
            alertas.append({"producto_id": codigo, "sucursal": u.nombre, "tipo": "stock_negativo",
                            "stock": u.stock, "accion": "pedido_urgente",
                            "detalle": "Stock negativo en la foto: verificar el conteo. No se traslada y para "
                                       "el pedido se toma como 0."})
        elif u.estado == "sin_pronostico":
            motivo = motivos.get(u.nombre)
            alertas.append({"producto_id": codigo, "sucursal": u.nombre, "tipo": "sin_pronostico",
                            "stock": u.stock, "accion": "ninguna",
                            "detalle": "Sin pronóstico: no participa en los traslados y su stock no se toma "
                                       "como excedente." + (f" ({motivo})" if motivo else "")})
    return {"traslados": traslados, "balance": balance, "alertas": alertas}


def recomendar_transferencias(bodega, modelos, politicas: Politicas, productos: Optional[list] = None) -> dict:
    """Traslados sugeridos, balance por producto y ubicación, y alertas.

    `bodega`: prediccion.bodega.BodegaPostgres (o una con su interfaz);
    `modelos`: el ModeloLoader de Nivel 1, o cualquier objeto con
    `pronosticar_lote(solicitudes, calendario, fecha)` como
    prediccion.servicio.PronosticadorNivel1;
    `productos`: códigos a procesar; sin la lista, todos los que tienen fila en
    la foto. Un código que no existe va a `no_encontrados`.

    Lanza FotoSinVentas (P8), CalendarioInsuficiente, LookupError (bodega vacía)
    o errores de SQLAlchemy (bodega caída); el router los traduce a HTTP."""
    pronosticador = modelos if hasattr(modelos, "pronosticar_lote") else PronosticadorNivel1(modelos)

    calendario = bodega.calendario()
    fecha_inventario = bodega.fecha_inventario()
    if fecha_inventario > calendario.ultima_fecha:
        raise FotoSinVentas(fecha_inventario, calendario.ultima_fecha)
    fecha_pronostico = calendario.ultimo_habil(fecha_inventario)        # A6: pronóstico a la fecha de la foto
    llegada = calcular_llegada(calendario, fecha_inventario, politicas)

    ubicaciones = bodega.sucursales()
    bodegas = [s["nombre"] for s in ubicaciones if s["tipo"] == TIPO_BODEGA]
    sucursales = [s["nombre"] for s in ubicaciones if s["tipo"] in TIPOS_SUCURSAL_FISICA]

    if productos is None:
        filas = bodega.inventario(fecha_inventario)
        catalogo = bodega.productos(sorted({f["codigo_item"] for f in filas}))
        codigos, no_encontrados = sorted(catalogo), []
    else:
        pedidos = list(dict.fromkeys(productos))
        catalogo = bodega.productos(pedidos)
        codigos = [c for c in pedidos if c in catalogo]
        no_encontrados = [c for c in pedidos if c not in catalogo]
        filas = bodega.inventario(fecha_inventario, codigos) if codigos else []

    stocks = {}
    for fila in filas:
        stocks.setdefault(fila["codigo_item"], {})[fila["sucursal"]] = fila["stock"]
    ventas = bodega.ventas_diarias_lote(codigos, sucursales, hasta=fecha_pronostico)

    # Todos los pares producto x sucursal física en un solo lote.
    solicitudes = [(catalogo[codigo], sucursal, ventas.get((codigo, sucursal), SERIE_VACIA))
                   for codigo in codigos for sucursal in sucursales]
    resultados = iter(pronosticador.pronosticar_lote(solicitudes, calendario, fecha_pronostico))

    traslados, balance, alertas = [], [], []
    for codigo in codigos:
        pronosticos, motivos = {}, {}
        for sucursal in sucursales:
            resultado = next(resultados)
            if isinstance(resultado, HistoriaInsuficiente):
                pronosticos[sucursal], motivos[sucursal] = None, str(resultado)
            else:
                pronosticos[sucursal] = resultado
        r = planificar_producto(catalogo[codigo], stocks.get(codigo, {}), bodegas, sucursales, pronosticos,
                                politicas, llegada, motivos)
        traslados += r["traslados"]
        balance += r["balance"]
        alertas += r["alertas"]

    traslados.sort(key=lambda t: (ORDEN_URGENCIA.get(t["urgencia"], 9), t["producto_id"], t["destino"], t["origen"]))
    deficits = [b["deficit"] for b in balance if b["deficit"] is not None]
    netos = [b["deficit_neto"] for b in balance if b["deficit_neto"] is not None]
    sin_destino = [b["excedente_sin_destino"] for b in balance if b["excedente_sin_destino"] is not None]
    return {
        "fecha_inventario": fecha_inventario.date().isoformat(),
        "fecha_pronostico": fecha_pronostico.date().isoformat(),
        "horizonte_dias": politicas.horizonte_dias,
        "politicas": {"version": politicas.version, "fecha": politicas.fecha.isoformat()},
        "traslados": traslados,
        "balance": balance,
        "alertas": alertas,
        "no_encontrados": no_encontrados,
        "resumen": {
            "productos": len(codigos),
            "traslados": len(traslados),
            "cantidad_trasladada": sum(t["cantidad"] for t in traslados),
            "deficit_total": round(sum(deficits), 2),
            "deficit_neto": round(sum(netos), 2),
            "excedente_sin_destino": round(sum(sin_destino), 2),
            "alertas": len(alertas),
        },
    }
