"""
InventAI/o — Pydantic schemas for Alertas module
INV-007: Alertas automáticas basadas en reglas de inventario.
"""

from typing import Literal

from pydantic import BaseModel

# ── Alert types ─────────────────────────────────────
# inconsistencia_inventario: stock negativo en la foto → urgencia critica (INV-25)
# stock_critico:   cobertura < 3 días y stock ≥ 0 → urgencia critica
# stock_bajo:      cobertura 3–7 días          → urgencia alta
# sin_movimiento:  0 ventas en últimos 30 días → urgencia media (solo sucursales: la Bodega no vende)
# rotacion_baja:   ventas < 20% del promedio   → urgencia media (solo sucursales)

URGENCIA_ORDER = {"critica": 0, "alta": 1, "media": 2}


class AlertaItem(BaseModel):
    id_producto: int
    nombre_producto: str
    categoria: str
    sucursal: str
    id_sucursal: int
    tipo_ubicacion: str  # INV-25: "sucursal" o "bodega_central"
    tipo: str           # inconsistencia_inventario, stock_critico, stock_bajo, sin_movimiento, rotacion_baja
    urgencia: str       # critica, alta, media
    valor: float        # valor actual (dias_cobertura, ventas_30d, stock negativo, etc.)
    umbral: float       # umbral de referencia
    detalle: str        # descripción legible
    fecha: str


class AlertaList(BaseModel):
    items: list[AlertaItem]
    total: int
    # INV-26 fix (K2): solo cuando se pide una página (page o page_size)
    page: int | None = None
    page_size: int | None = None
    pages: int | None = None
    fecha_inventario: str


# ── Resumen: contadores ─────────────────────────────

class AlertaContadores(BaseModel):
    critica: int
    alta: int
    media: int
    total: int


class AlertaResumenSucursal(BaseModel):
    sucursal: str
    id_sucursal: int
    tipo_ubicacion: str
    contadores: AlertaContadores


class AlertaResumen(BaseModel):
    items: list[AlertaResumenSucursal]
    global_: AlertaContadores
    por_tipo: dict      # {"inconsistencia_inventario": N, "stock_critico": N, "stock_bajo": N, ...}
    fecha_inventario: str


# ── Alertas con IA (INV-28) ─────────────────────────
# riesgo_desabastecimiento_ml: urgencia urgente/alta del balance de INV-22, q50 ≥ 1 y stock ≥ 0 (V3, V5)
# sobrestock_previsto_ml:      stock > 2 × máximo de INV-22, q50 > 0 y stock > 0 (V4, V5)

TipoAlertaML = Literal["riesgo_desabastecimiento_ml", "sobrestock_previsto_ml"]
UrgenciaAlerta = Literal["critica", "alta", "media"]
OrigenAlertaML = Literal["ml", "ambos"]
AccionAlertaML = Literal["traslado", "traslado_y_compra", "compra"]


class AlertaMLItem(BaseModel):
    id_producto: int | None      # nulo si el código no tiene fila en dim_producto
    codigo_item: str
    nombre_producto: str | None
    categoria: str | None
    sucursal: str
    id_sucursal: int
    tipo_ubicacion: str          # siempre "sucursal": la Bodega no tiene pronóstico (C10)
    tipo: TipoAlertaML
    urgencia: UrgenciaAlerta
    origen: OrigenAlertaML       # "ambos": las reglas ya marcan el par con stock_critico o stock_bajo (V2)
    valor: float                 # riesgo: días hábiles hasta agotarse; sobrestock: stock / máximo
    umbral: float                # riesgo: 5 o 10 días hábiles; sobrestock: 2
    unidad: Literal["unidad", "kg"]
    stock: float
    q50: float                   # demanda prevista en los 15 días hábiles
    accion: AccionAlertaML | None    # V14, solo en el riesgo: qué lo resuelve según el balance de INV-22
    llega_tarde: bool | None         # V14: el traslado sugerido llega después de agotarse; nulo sin traslado
    detalle: str
    fecha: str                   # fecha de la foto de inventario
    fecha_pronostico: str | None     # V14: fecha de los datos con que se pronosticó


class AlertaMLResumen(BaseModel):
    total: int
    riesgo_desabastecimiento_ml: int
    sobrestock_previsto_ml: int
    critica: int
    alta: int
    media: int
    ambos: int
    ml: int


class AlertaMLList(BaseModel):
    items: list[AlertaMLItem]
    total: int
    page: int | None = None
    page_size: int | None = None
    pages: int | None = None
    resumen: AlertaMLResumen
    fecha_inventario: str
    fecha_pronostico: str | None = None
    politicas: dict              # versión de las políticas de INV-22 con que se calculó el balance
    calculado_en: str
