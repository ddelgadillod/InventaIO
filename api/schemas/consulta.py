"""
InventAI/o — Pydantic schemas for Consulta (Catálogos) module
Response models for productos, sucursales, proveedores, categorías.
"""
from pydantic import BaseModel
from typing import Optional, List


# ── Producto ────────────────────────────────────────

class ProductoItem(BaseModel):
    id_producto: int
    codigo_item: int
    nombre: str
    familia: str
    clase: Optional[int] = None
    categoria: str
    es_perecedero: bool
    unidad_medida: str
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


# ── Sucursal ────────────────────────────────────────

class SucursalItem(BaseModel):
    id_sucursal: int
    codigo_tienda: int
    nombre: str
    ciudad: str
    departamento: str
    tipo: str
    cluster: Optional[int] = None
    factor_volumen: float


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
