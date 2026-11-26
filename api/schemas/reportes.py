"""
InventAI/o — Pydantic schemas for Reportes module
INV-006: Reportes de ventas, KPIs y análisis.
"""

from pydantic import BaseModel

# ── KPIs ────────────────────────────────────────────

class KPIs(BaseModel):
    ventas_hoy: float
    ventas_mes: float
    productos_en_riesgo: int       # semáforo bajo + critico
    stock_valorizado: float
    fecha_referencia: str
    variacion_ventas_hoy_pct: float | None = None   # vs mismo día semana anterior
    variacion_ventas_mes_pct: float | None = None    # vs mes anterior


# ── Ventas con filtros y agrupación ─────────────────

class VentaPeriodo(BaseModel):
    periodo: str        # "2017-08-01", "2017-W32", "2017-08", "2017-T3" (INV-33), "2017" (INV-33)
    cantidad: float
    valor_total: float
    costo_total: float
    margen: float       # valor_total - costo_total
    transacciones: int


class ProductoReporte(BaseModel):
    """INV-33 (B4): el producto filtrado en /ventas."""
    codigo: str
    nombre: str
    unidad: str         # 'kg' si se vende por kilo; si no, 'unidad'


class VentasReporte(BaseModel):
    items: list[VentaPeriodo]
    total_cantidad: float
    total_valor: float
    total_margen: float
    agrupacion: str     # dia, semana, mes
    fecha_inicio: str
    fecha_fin: str
    datos_desde: str    # INV-26 fix (K7): primera y última fecha con ventas
    datos_hasta: str
    producto: ProductoReporte | None = None   # INV-33 (B4): solo con el filtro de producto


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
    detalle: list[VentaPeriodo]     # desglose del periodo actual
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
    items: list[TopProducto]
    fecha_inicio: str
    fecha_fin: str
    total_valor: float


# ── Tendencias (series de tiempo) ───────────────────

class TendenciaPunto(BaseModel):
    fecha: str
    valor_total: float
    cantidad: float
    promedio_movil_7d: float | None = None


class TendenciaSerie(BaseModel):
    sucursal: str | None = None
    puntos: list[TendenciaPunto]


class TendenciasReporte(BaseModel):
    series: list[TendenciaSerie]
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
    items: list[CategoriaDistribucion]
    total_valor: float
    fecha_inicio: str
    fecha_fin: str


# ── Análisis de ventas (INV-72, recibido de INV-82) ─

class MedidasVentas(BaseModel):
    cantidad: float
    valor_total: float          # sin IVA (INV-82)
    costo_total: float
    margen: float               # valor_total - costo_total
    margen_pct: float | None    # margen / valor_total × 100; None sin venta
    transacciones: int


class FilaAnalisis(MedidasVentas):
    dimensiones: dict[str, str]  # {"anio": "2025", "sucursal": "PRINCIPAL"}; mes AAAA-MM, trimestre AAAA-Tn
    # Días con alguna venta en la fila: dice si un periodo está completo en los datos (2026 hasta septiembre, feb-2023)
    dias_con_ventas: int
    producto_nombre: str | None = None    # con la dimensión producto
    unidad: str | None = None             # con la dimensión producto: 'kg' o 'unidad'
    anterior: MedidasVentas | None = None  # con comparar: el mismo periodo un año antes
    variacion_valor_pct: float | None = None
    variacion_cantidad_pct: float | None = None


class AnalisisVentas(BaseModel):
    dimensiones: list[str]
    filas: list[FilaAnalisis]
    filas_totales: int          # cuántas filas había antes del límite
    total: MedidasVentas        # de todas las filas, no solo de las devueltas
    orden: str
    ascendente: bool
    limite: int
    comparar: bool
    fecha_inicio: str
    fecha_fin: str
    meses: list[int] | None = None
    anios: list[int] | None = None
    sucursal: str | None = None           # la sucursal filtrada (la propia, para un administrador de sucursal)
    categoria: str | None = None
    productos: list[ProductoReporte] | None = None   # el grupo de productos sumado
    unidades_mixtas: bool       # las unidades suman kilos y unidades
    datos_desde: str
    datos_hasta: str
