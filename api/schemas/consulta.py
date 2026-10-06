"""
InventAI/o — Pydantic schemas for Consulta (Catálogos) module
Response models for productos, sucursales, proveedores, categorías.
"""
from datetime import date

from pydantic import BaseModel, Field
from typing import Optional, List


# ── Producto ────────────────────────────────────────

class ProductoItem(BaseModel):
    id_producto: int
    codigo_item: str    # INV-25: texto en la bodega real (P1632, 00008)
    nombre: str
    familia: str
    clase: Optional[int] = None
    categoria: str
    es_perecedero: bool
    unidad_medida: str  # la de la presentación (g, ml, l), no la del stock
    # INV-26 (fix): en qué se cuentan el stock y las ventas, como `unidad` en ml_service
    unidad: str = Field(..., description="'kg' si se vende por kilo; si no, 'unidad'.")
    precio_base: Optional[float] = None
    costo_base: Optional[float] = None
    margen_pct: Optional[float] = None
    iva_pct: float


class ProductoList(BaseModel):
    items: List[ProductoItem]
    total: int
    page: int
    page_size: int
    pages: int


class ProductoDetalle(ProductoItem):
    proveedores: List[str] = []


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
    ventanas: List[VentanaVentas] = Field(..., description="En orden cronológico.")


# ── Sucursal ────────────────────────────────────────

class SucursalItem(BaseModel):
    id_sucursal: int
    codigo_tienda: int
    nombre: str
    ciudad: Optional[str] = None          # INV-25: nulos en la bodega real
    departamento: Optional[str] = None
    tipo: str                             # principal, estandar o bodega_central
    cluster: Optional[int] = None
    factor_volumen: Optional[float] = None


class SucursalList(BaseModel):
    items: List[SucursalItem]
    total: int


# ── Proveedor ───────────────────────────────────────

class ProveedorItem(BaseModel):
    id_proveedor: int
    codigo: str
    razon_social: str
    nit: str
    ciudad: str
    telefono: Optional[str] = None
    email: Optional[str] = None
    lead_time_dias: int
    categorias: List[str] = []
    calificacion: Optional[float] = None


class ProveedorList(BaseModel):
    items: List[ProveedorItem]
    total: int


class ProveedorDetalle(ProveedorItem):
    productos: List[ProductoItem] = []
    total_productos: int = 0


# ── Categoría ───────────────────────────────────────

class CategoriaItem(BaseModel):
    categoria: str
    total_productos: int
    perecederos: int
    no_perecederos: int


class CategoriaList(BaseModel):
    items: List[CategoriaItem]
    total: int
