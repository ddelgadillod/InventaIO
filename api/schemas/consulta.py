"""
InventAI/o — Pydantic schemas for Consulta (Catálogos) module
Response models for productos, sucursales, proveedores, categorías.
"""
from datetime import date

from pydantic import BaseModel, Field

# ── Producto ────────────────────────────────────────

class ProductoItem(BaseModel):
    id_producto: int
    codigo_item: str    # INV-25: texto en la bodega real (P1632, 00008)
    nombre: str
    familia: str
    clase: int | None = None
    categoria: str
    es_perecedero: bool
    unidad_medida: str  # la de la presentación (g, ml, l), no la del stock
    # INV-26 (fix): en qué se cuentan el stock y las ventas, como `unidad` en ml_service
    unidad: str = Field(..., description="'kg' si se vende por kilo; si no, 'unidad'.")
    precio_base: float | None = None
    costo_base: float | None = None
    margen_pct: float | None = None
    iva_pct: float


class ProductoList(BaseModel):
    items: list[ProductoItem]
    total: int
    page: int
    page_size: int
    pages: int


class ProductoDetalle(ProductoItem):
    proveedores: list[str] = []


# ── Ventas por producto (INV-26) ────────────────────

class VentanaVentas(BaseModel):
    desde: date = Field(..., description="Primer día hábil de la ventana.")
    hasta: date = Field(..., description="Último día hábil de la ventana.")
    unidades: float = Field(..., description="Unidades vendidas en los días hábiles de la ventana (0 si no hubo venta).")


class VentasProducto(BaseModel):
    id_producto: int
    codigo_item: str
    nombre_producto: str
    categoria: str
    unidad: str = Field(..., description="Unidad de las ventanas: 'kg' si se vende por kilo; si no, 'unidad'.")
    id_sucursal: int
    sucursal: str
    horizonte_dias_habiles: int = Field(..., description="Días hábiles de cada ventana: 15, el horizonte del pronóstico.")
    fecha_fin: date = Field(..., description="Último día hábil de la red; la última ventana termina ahí.")
    ventanas: list[VentanaVentas] = Field(..., description="En orden cronológico.")


# ── Sucursal ────────────────────────────────────────

class SucursalItem(BaseModel):
    id_sucursal: int
    codigo_tienda: int
    nombre: str
    ciudad: str | None = None          # INV-25: nulos en la bodega real
    departamento: str | None = None
    tipo: str                             # principal, estandar o bodega_central
    cluster: int | None = None
    factor_volumen: float | None = None


class SucursalList(BaseModel):
    items: list[SucursalItem]
    total: int


# ── Proveedor ───────────────────────────────────────

class ProveedorItem(BaseModel):
    id_proveedor: int
    codigo: str
    razon_social: str
    nit: str
    ciudad: str
    telefono: str | None = None
    email: str | None = None
    lead_time_dias: int
    categorias: list[str] = []
    calificacion: float | None = None


class ProveedorList(BaseModel):
    items: list[ProveedorItem]
    total: int


class ProveedorDetalle(ProveedorItem):
    productos: list[ProductoItem] = []
    total_productos: int = 0


# ── Categoría ───────────────────────────────────────

class CategoriaItem(BaseModel):
    categoria: str
    total_productos: int
    perecederos: int
    no_perecederos: int


class CategoriaList(BaseModel):
    items: list[CategoriaItem]
    total: int
