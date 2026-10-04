"""
InventAI/o — Pydantic schemas for Alertas module
INV-007: Alertas automáticas basadas en reglas de inventario.
"""
from pydantic import BaseModel
from typing import List


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
    items: List[AlertaItem]
    total: int
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
    items: List[AlertaResumenSucursal]
    global_: AlertaContadores
    por_tipo: dict      # {"inconsistencia_inventario": N, "stock_critico": N, "stock_bajo": N, ...}
    fecha_inventario: str
