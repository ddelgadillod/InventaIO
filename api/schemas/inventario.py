"""
InventAI/o — Pydantic schemas for Inventario module
INV-005: Consulta de inventario y stock con semáforo.
"""

from pydantic import BaseModel

# ── Semáforo constants ──────────────────────────────
# Inconsistencia: stock negativo, sin importar la cobertura (INV-26 fix, K3)
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
    unidad: str  # INV-26 fix (J5): "kg" si se vende por kilo; si no, "unidad"
    sucursal: str
    id_sucursal: int
    tipo_ubicacion: str  # INV-25: "sucursal" o "bodega_central"
    stock_disponible: float
    stock_bodega: float | None = None  # INV-25: stock de la Bodega del mismo producto; nulo en la Bodega
    stock_minimo: float
    stock_maximo: float
    punto_reorden: float
    dias_cobertura: float
    semaforo: str  # "ok", "bajo", "critico" o "inconsistencia"
    fecha: str


class InventarioList(BaseModel):
    items: list[InventarioItem]
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
    tipo_ubicacion: str
    stock_actual: float
    stock_bodega: float | None = None
    stock_minimo: float
    stock_maximo: float
    punto_reorden: float
    dias_cobertura: float
    semaforo: str
    historial: list[InventarioHistorialDia]


# ── Resumen: contadores por semáforo ────────────────

class SemaforoContador(BaseModel):
    ok: int
    bajo: int
    critico: int
    inconsistencia: int  # INV-26 fix (K3)
    total: int


class InventarioResumen(BaseModel):
    sucursal: str | None = None
    id_sucursal: int | None = None
    tipo_ubicacion: str | None = None
    contadores: SemaforoContador
    fecha_inventario: str


class InventarioResumenList(BaseModel):
    items: list[InventarioResumen]
    global_: SemaforoContador
    fecha_inventario: str


# ── Valorizado: valor por sucursal y categoría ──────

class ValorizadoItem(BaseModel):
    sucursal: str
    id_sucursal: int
    tipo_ubicacion: str
    categoria: str
    total_productos: int
    stock_total: float
    valor_stock: float  # stock * precio_base


class ValorizadoList(BaseModel):
    items: list[ValorizadoItem]
    total_valor: float
    fecha_inventario: str
