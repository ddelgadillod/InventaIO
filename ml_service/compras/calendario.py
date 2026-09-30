"""
InventAI/o — ML Service: calendario de pedidos a proveedor (INV-21, B2-B3, B7-B8)

Cada producto pertenece a un grupo de pedido (quincenal: días fijos del mes;
semanal: un día fijo de la semana) y tiene una ruta (directo a la sucursal o
por la Bodega Central). De ahí salen, a partir de la fecha de la foto:

- el pedido actual: la primera fecha fija en o después de la foto; si cae en
  un día no hábil (cierre programado), el siguiente día hábil;
- su llegada: lead time en días hábiles después del pedido; por la Bodega, la
  sucursal lo recibe con la regla de llegada de los traslados de INV-22;
- el plazo a cubrir P: días hábiles desde la foto hasta que llega a la
  sucursal el pedido SIGUIENTE, porque lo que se pide hoy tiene que alcanzar
  hasta entonces.

Días hábiles, los mismos del modelo y de INV-22: en la historia, los días con
venta; después del último dato, los de dim_tiempo sin cierre programado.
Funciones sin I/O: reciben el Calendario ya leído de la bodega.
"""
from dataclasses import dataclass
from typing import Iterator

import pandas as pd

from compras.politicas import FechasPedido, PoliticasCompras
from prediccion.features import Calendario, CalendarioInsuficiente
from transferencias.motor import calcular_llegada
from transferencias.politicas import Politicas

UN_DIA = pd.Timedelta(days=1)


@dataclass(frozen=True)
class Plan:
    """Fechas de un grupo de pedido por una ruta. `dias_cubiertos` es P."""
    grupo: str                          # "quincenal" o "semanal"
    tipo_destino: str                   # "bodega_central" o "sucursal"
    fecha_pedido: pd.Timestamp
    fecha_llegada: pd.Timestamp         # al destino de la compra (la Bodega o la sucursal)
    fecha_llegada_sucursal: pd.Timestamp
    pedido_siguiente: pd.Timestamp
    cubre_hasta: pd.Timestamp           # llegada a la sucursal del pedido siguiente
    dias_cubiertos: int                 # P, en días hábiles desde la foto
    dias_hasta_llegada: int             # días hábiles desde la foto hasta fecha_llegada_sucursal


def habil_en_o_despues(calendario: Calendario, fecha) -> pd.Timestamp:
    """`fecha` si es día hábil; si no, el siguiente."""
    return calendario.proximos_habiles(pd.Timestamp(fecha) - UN_DIA, 1)[0]


def sumar_habiles(calendario: Calendario, fecha, n: int) -> pd.Timestamp:
    """El n-ésimo día hábil después de `fecha`."""
    return calendario.proximos_habiles(fecha, n)[-1]


def habiles_entre(calendario: Calendario, desde, hasta) -> int:
    """Días hábiles en (desde, hasta], con la definición de proximos_habiles."""
    desde, hasta = pd.Timestamp(desde), pd.Timestamp(hasta)
    if hasta <= desde:
        return 0
    marcas = calendario.marcas
    if hasta > marcas.index.max():
        raise CalendarioInsuficiente(f"dim_tiempo llega a {marcas.index.max().date()} y el pedido a {hasta.date()}")
    historicos = ((calendario.habiles > desde) & (calendario.habiles <= hasta)).sum()
    corte = max(desde, calendario.ultima_fecha)
    futuros = ((marcas.index > corte) & (marcas.index <= hasta) & ~marcas["es_cierre_programado"].astype(bool)).sum()
    return int(historicos + futuros)


def fechas_fijas(regla: FechasPedido, desde) -> Iterator[pd.Timestamp]:
    """Las fechas fijas de la regla en o después de `desde`, en orden (sin fin)."""
    desde = pd.Timestamp(desde).normalize()
    if regla.dias_mes is not None:
        mes = desde.to_period("M")
        while True:
            for dia in sorted(set(regla.dias_mes)):
                fecha = pd.Timestamp(year=mes.year, month=mes.month, day=dia)
                if fecha >= desde:
                    yield fecha
            mes += 1
    else:
        dias = regla.dias_semana_iso()
        fecha = desde
        while True:
            if fecha.weekday() in dias:
                yield fecha
            fecha += UN_DIA


def pedidos_del_grupo(calendario: Calendario, foto, regla: FechasPedido) -> tuple:
    """(pedido actual, pedido siguiente), ya movidos al día hábil."""
    fechas = fechas_fijas(regla, foto)
    actual = habil_en_o_despues(calendario, next(fechas))
    for fecha in fechas:
        siguiente = habil_en_o_despues(calendario, fecha)
        if siguiente > actual:
            return actual, siguiente
    raise AssertionError("inalcanzable: las fechas fijas no se acaban")


def clasificar(producto: dict, politicas: PoliticasCompras) -> tuple:
    """(grupo, tipo_destino) del producto según sus marcas (B7, B8)."""
    marcas = {"perecedero": bool(producto.get("es_perecedero_estricto")),
              "requiere_frio": bool(producto.get("requiere_frio"))}
    grupo = "semanal" if any(marcas[m] for m in politicas.grupo_semanal) else "quincenal"
    destino = "sucursal" if any(marcas[m] for m in politicas.destino_directo) else "bodega_central"
    return grupo, destino


def combinaciones(politicas: PoliticasCompras) -> list:
    """Las (grupo, tipo_destino) que pueden darse con estas políticas: lo seco
    siempre es quincenal y va a la Bodega; perecederos y frío van directo, en el
    grupo semanal si su marca está en grupo_semanal."""
    combos = [("quincenal", "bodega_central")]
    if politicas.grupo_semanal:
        combos.append(("semanal", "sucursal"))
    if set(politicas.destino_directo) - set(politicas.grupo_semanal):
        combos.append(("quincenal", "sucursal"))
    return combos


def planes_de_pedido(calendario: Calendario, foto, politicas: PoliticasCompras,
                     politicas_traslados: Politicas) -> dict:
    """{(grupo, tipo_destino): Plan} para las combinaciones posibles."""
    foto = pd.Timestamp(foto)
    planes = {}
    for grupo, destino in combinaciones(politicas):
        pedido, siguiente = pedidos_del_grupo(calendario, foto, getattr(politicas.calendario_pedidos, grupo))
        llegada = sumar_habiles(calendario, pedido, politicas.lead_time_dias)
        llegada_siguiente = sumar_habiles(calendario, siguiente, politicas.lead_time_dias)
        if destino == "bodega_central":
            # la sucursal lo recibe con el traslado de INV-22 desde la Bodega
            en_sucursal = calcular_llegada(calendario, llegada, politicas_traslados).fecha
            cubre_hasta = calcular_llegada(calendario, llegada_siguiente, politicas_traslados).fecha
        else:
            en_sucursal, cubre_hasta = llegada, llegada_siguiente
        planes[(grupo, destino)] = Plan(
            grupo=grupo, tipo_destino=destino, fecha_pedido=pedido, fecha_llegada=llegada,
            fecha_llegada_sucursal=en_sucursal, pedido_siguiente=siguiente, cubre_hasta=cubre_hasta,
            dias_cubiertos=habiles_entre(calendario, foto, cubre_hasta),
            dias_hasta_llegada=habiles_entre(calendario, foto, en_sucursal))
    return planes
