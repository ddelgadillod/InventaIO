"""
InventAI/o — Pydantic schemas for Reportes module
INV-006: Reportes de ventas, KPIs y análisis.
"""
from pydantic import BaseModel
from typing import Optional, List


# ── KPIs ────────────────────────────────────────────

class KPIs(BaseModel):
    ventas_hoy: float
    ventas_mes: float
    productos_en_riesgo: int       # semáforo bajo + critico
    stock_valorizado: float
    fecha_referencia: str
    variacion_ventas_hoy_pct: Optional[float] = None   # vs mismo día semana anterior
    variacion_ventas_mes_pct: Optional[float] = None    # vs mes anterior


# ── Ventas con filtros y agrupación ─────────────────

class VentaPeriodo(BaseModel):
    periodo: str        # "2017-08-01", "2017-W32", "2017-08"
    cantidad: float
    valor_total: float
    costo_total: float
    margen: float       # valor_total - costo_total
    transacciones: int


class VentasReporte(BaseModel):
    items: List[VentaPeriodo]
    total_cantidad: float
    total_valor: float
    total_margen: float
    agrupacion: str     # dia, semana, mes
    fecha_inicio: str
    fecha_fin: str


# ── Comparativa ─────────────────────────────────────

class ComparativaPeriodo(BaseModel):
    periodo_actual: str
    periodo_anterior: str
    valor_actual: float
    valor_anterior: float
    variacion_pct: float
    cantidad_actual: float
    cantidad_anterior: float


class VentasComparativa(BaseModel):
    resumen: ComparativaPeriodo
    detalle: List[VentaPeriodo]     # desglose del periodo actual
    agrupacion: str


# ── Top productos ───────────────────────────────────

class TopProducto(BaseModel):
    id_producto: int
    nombre: str
    categoria: str
    cantidad: float
    valor_total: float
    margen: float
    participacion_pct: float       # % del total de ventas


class TopProductosList(BaseModel):
    items: List[TopProducto]
    fecha_inicio: str
    fecha_fin: str
    total_valor: float


# ── Tendencias (series de tiempo) ───────────────────

class TendenciaPunto(BaseModel):
    fecha: str
    valor_total: float
    cantidad: float
    promedio_movil_7d: Optional[float] = None


class TendenciaSerie(BaseModel):
    sucursal: Optional[str] = None
    puntos: List[TendenciaPunto]


class TendenciasReporte(BaseModel):
    series: List[TendenciaSerie]
    fecha_inicio: str
    fecha_fin: str


# ── Distribución por categoría ──────────────────────

class CategoriaDistribucion(BaseModel):
    categoria: str
    cantidad: float
    valor_total: float
    margen: float
    participacion_pct: float
    num_productos: int


class DistribucionCategorias(BaseModel):
    items: List[CategoriaDistribucion]
    total_valor: float
    fecha_inicio: str
    fecha_fin: str
