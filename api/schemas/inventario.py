"""
InventAI/o — Pydantic schemas for Inventario module
INV-005: Consulta de inventario y stock con semáforo.
"""
from pydantic import BaseModel
from typing import Optional, List


# ── Semáforo constants ──────────────────────────────
# OK (verde): cobertura > 7 días
# Bajo (amarillo): cobertura 3–7 días
# Crítico (rojo): cobertura < 3 días
SEMAFORO_OK_MIN = 7.0
SEMAFORO_BAJO_MIN = 3.0


# ── Inventario con semáforo ─────────────────────────

class InventarioItem(BaseModel):
    id_producto: int
    nombre_producto: str
    categoria: str
    es_perecedero: bool
    sucursal: str
    id_sucursal: int
    stock_disponible: float
    stock_minimo: float
    stock_maximo: float
    punto_reorden: float
    dias_cobertura: float
    semaforo: str  # "ok", "bajo", "critico"
    fecha: str


class InventarioList(BaseModel):
    items: List[InventarioItem]
    total: int
    page: int
    page_size: int
    pages: int
    fecha_inventario: str


# ── Detalle: historial 30 días ──────────────────────

class InventarioHistorialDia(BaseModel):
    fecha: str
    stock_disponible: float
    dias_cobertura: float
    semaforo: str


class InventarioDetalle(BaseModel):
    id_producto: int
    nombre_producto: str
    categoria: str
    sucursal: str
    id_sucursal: int
    stock_actual: float
    stock_minimo: float
    stock_maximo: float
    punto_reorden: float
    dias_cobertura: float
    semaforo: str
    historial: List[InventarioHistorialDia]


# ── Resumen: contadores por semáforo ────────────────

class SemaforoContador(BaseModel):
    ok: int
    bajo: int
    critico: int
    total: int


class InventarioResumen(BaseModel):
    sucursal: Optional[str] = None
    id_sucursal: Optional[int] = None
    contadores: SemaforoContador
    fecha_inventario: str


class InventarioResumenList(BaseModel):
    items: List[InventarioResumen]
    global_: SemaforoContador
    fecha_inventario: str


# ── Valorizado: valor por sucursal y categoría ──────

class ValorizadoItem(BaseModel):
    sucursal: str
    id_sucursal: int
    categoria: str
    total_productos: int
    stock_total: float
    valor_stock: float  # stock * precio_base


class ValorizadoList(BaseModel):
    items: List[ValorizadoItem]
    total_valor: float
    fecha_inventario: str
