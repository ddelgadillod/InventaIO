"""
InventAI/o — Pydantic schemas de las recomendaciones (INV-23)
Las respuestas de POST /api/compras y POST /api/transferencias de ml_service
(ver docs/ML-SERVICE-API.md), con el nombre y la categoría del producto, los
filtros aplicados y un resumen propio. Reglas en docs/INV-23-requerimientos.md.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

Unidad = Literal["unidad", "kg"]
UrgenciaCompra = Literal["urgente", "alta", "normal"]
UrgenciaTraslado = Literal["urgente", "alta", "normal", "vigilancia"]
Grupo = Literal["quincenal", "semanal"]
TipoDestino = Literal["bodega_central", "sucursal"]
Motivo = Literal["reposicion", "stock_negativo"]

NOMBRE = "Nombre del producto en dw.dim_producto; nulo si no tiene fila."
CATEGORIA = "Categoría del producto en dw.dim_producto; nula si no tiene fila."


# ── Comunes ─────────────────────────────────────────

class CantidadPorUnidad(BaseModel):
    unidad: int
    kg: int


class MagnitudPorUnidad(BaseModel):
    unidad: float
    kg: float


class VersionPoliticas(BaseModel):
    version: int
    fecha: str


class FiltrosAplicados(BaseModel):
    sucursal: Optional[str] = Field(None, description="Sucursal usada (nombre canónico); la del rol si sucursal_por_rol.")
    sucursal_por_rol: bool = Field(..., description="true si la sucursal la puso el rol del usuario (admin_sucursal).")
    categoria: Optional[str] = Field(None, description="Categoría usada (nombre canónico).")
    urgencia: Optional[str] = None


# ── Compras (INV-21) ────────────────────────────────

class PoliticasCompras(BaseModel):
    inv21: VersionPoliticas
    inv22: VersionPoliticas


class PlanPedido(BaseModel):
    grupo: Grupo
    tipo_destino: TipoDestino
    fecha_pedido: str
    fecha_llegada: str
    fecha_llegada_sucursal: str
    pedido_siguiente: str
    cubre_hasta: str
    dias_cubiertos: int
    dias_hasta_llegada: int


class DetalleCompra(BaseModel):
    sucursal: str
    posicion: float
    q50: float
    limite_superior: float
    punto_pedido: float
    nivel: float
    necesidad: float
    dias_hasta_agotarse: float
    urgencia: UrgenciaCompra
    llega_tarde: bool
    motivo: Motivo


class LineaCompra(BaseModel):
    producto_id: str = Field(..., description="codigo_item del producto.")
    nombre_producto: Optional[str] = Field(None, description=NOMBRE)
    categoria: Optional[str] = Field(None, description=CATEGORIA)
    destino: str = Field(..., description="Sucursal (perecederos y frío) o BODEGA_CENTRAL.")
    tipo_destino: TipoDestino
    grupo: Grupo
    cantidad: int = Field(..., description="La de toda la compra, también en la vista desde una sucursal.")
    unidad: Unidad
    urgencia: UrgenciaCompra = Field(..., description="Con filtro de sucursal física, la de esa sucursal (R1).")
    dias_hasta_agotarse: float = Field(..., description="Con filtro de sucursal física, los de esa sucursal (R1).")
    fecha_pedido: str
    fecha_llegada: str
    fecha_llegada_sucursal: str
    llega_tarde: bool = Field(..., description="Con filtro de sucursal física, el de esa sucursal (R1).")
    necesidad: float = Field(..., description="Suma de las necesidades de las sucursales de la compra.")
    necesidad_sucursal: Optional[float] = Field(
        None, description="Parte de la necesidad que es de la sucursal filtrada; nula sin filtro de sucursal física.")
    sobrante_bodega: Optional[float] = None
    motivo: Motivo = Field(..., description="Con filtro de sucursal física, el de esa sucursal (R1).")
    detalle: Optional[List[DetalleCompra]] = Field(
        None, description="Cálculo por sucursal; solo la filtrada en la vista desde una sucursal. No viene con incluir_detalle=false.")


class CubrirConTraslado(BaseModel):
    producto_id: str
    nombre_producto: Optional[str] = Field(None, description=NOMBRE)
    categoria: Optional[str] = Field(None, description=CATEGORIA)
    necesidad: float
    necesidad_sucursal: Optional[float] = None
    sobrante_bodega: float
    unidad: Unidad
    urgencia: UrgenciaCompra
    dias_hasta_agotarse: float
    detalle: Optional[List[DetalleCompra]] = None


class AlertaCompra(BaseModel):
    producto_id: str
    nombre_producto: Optional[str] = Field(None, description=NOMBRE)
    categoria: Optional[str] = Field(None, description=CATEGORIA)
    sucursal: str
    tipo: Literal["posible_inconsistencia_inventario"]
    stock: float
    accion: Literal["compra_urgente", "verificar_conteo"]
    detalle: str


class ResumenCompras(BaseModel):
    productos: int = Field(..., description="Productos distintos en compras y cubrir_con_traslado.")
    lineas: int
    lineas_sucursal: int
    lineas_bodega: int
    cantidad: CantidadPorUnidad = Field(..., description="Suma de todas las líneas.")
    cantidad_directa: CantidadPorUnidad = Field(..., description="Suma de las líneas directas a sucursal.")
    cantidad_bodega: CantidadPorUnidad = Field(..., description="Suma de las líneas para la Bodega (compras completas).")
    necesidad_via_bodega: Optional[MagnitudPorUnidad] = Field(
        None, description="Con sucursal física: su necesidad en las compras de la Bodega. Nula en otro caso.")
    cubiertos_por_bodega: int
    alertas: int


class RecomendacionesCompras(BaseModel):
    fecha_inventario: str
    fecha_pronostico: str
    lead_time_dias: int
    politicas: PoliticasCompras
    calendario: List[PlanPedido]
    compras: List[LineaCompra]
    cubrir_con_traslado: List[CubrirConTraslado]
    alertas: List[AlertaCompra] = Field(..., description="La urgencia no las filtra (R2).")
    no_encontrados: List[str] = Field(..., description="Siempre vacía: el GET no recibe lista de productos.")
    resumen: ResumenCompras
    filtros_aplicados: FiltrosAplicados
    calculado_en: str = Field(..., description="Cuándo se pidió el resultado a ml_service (UTC); en la caché, el original.")


# ── Transferencias (INV-22) ─────────────────────────

class Traslado(BaseModel):
    producto_id: str
    nombre_producto: Optional[str] = Field(None, description=NOMBRE)
    categoria: Optional[str] = Field(None, description=CATEGORIA)
    origen: str
    destino: str
    cantidad: int
    unidad: Unidad
    urgencia: UrgenciaTraslado
    dias_hasta_agotarse: Optional[float] = None
    fecha_llegada: str
    dias_habiles_llegada: int
    llega_tarde: bool


class BalanceFila(BaseModel):
    producto_id: str
    nombre_producto: Optional[str] = Field(None, description=NOMBRE)
    categoria: Optional[str] = Field(None, description=CATEGORIA)
    sucursal: str
    tipo_ubicacion: Literal["bodega_central", "sucursal"]
    rama: Optional[str] = None
    stock: float
    q50: Optional[float] = None
    limite_superior: Optional[float] = None
    objetivo: Optional[float] = None
    maximo: Optional[float] = None
    excedente: Optional[float] = None
    excedente_sin_destino: Optional[float] = None
    deficit: Optional[float] = None
    deficit_vigilancia: Optional[float] = None
    recibido: int
    enviado: int
    deficit_neto: Optional[float] = None
    estado: Literal["origen", "destino", "vigilancia", "equilibrio", "sin_pronostico", "stock_negativo", "bodega"]
    urgencia: Optional[UrgenciaTraslado] = None
    dias_hasta_agotarse: Optional[float] = None
    unidad: Unidad


class AlertaTraslado(BaseModel):
    producto_id: str
    nombre_producto: Optional[str] = Field(None, description=NOMBRE)
    categoria: Optional[str] = Field(None, description=CATEGORIA)
    sucursal: str
    tipo: Literal["stock_negativo", "sin_pronostico"]
    stock: Optional[float] = None
    accion: Literal["pedido_urgente", "ninguna"]
    detalle: str


class ResumenTransferencias(BaseModel):
    productos: int = Field(..., description="Productos distintos en traslados y balance (aunque el balance no se liste).")
    traslados: int
    cantidad_trasladada: CantidadPorUnidad
    filas_balance: int = Field(..., description="Filas del balance que pasan los filtros, se listen o no.")
    deficit_total: MagnitudPorUnidad
    deficit_neto: MagnitudPorUnidad
    excedente_sin_destino: MagnitudPorUnidad
    alertas: int = Field(..., description="Alertas listadas.")
    alertas_stock_negativo: int
    alertas_sin_pronostico: int = Field(..., description="Se cuentan siempre; se listan solo con incluir_balance=true.")


class RecomendacionesTransferencias(BaseModel):
    fecha_inventario: str
    fecha_pronostico: str
    horizonte_dias: int
    politicas: VersionPoliticas
    traslados: List[Traslado]
    balance: Optional[List[BalanceFila]] = Field(None, description="Solo con incluir_balance=true.")
    alertas: List[AlertaTraslado] = Field(
        ..., description="La urgencia no las filtra (R2). Las sin_pronostico, solo con incluir_balance=true.")
    no_encontrados: List[str] = Field(..., description="Siempre vacía: el GET no recibe lista de productos.")
    resumen: ResumenTransferencias
    filtros_aplicados: FiltrosAplicados
    calculado_en: str = Field(..., description="Cuándo se pidió el resultado a ml_service (UTC); en la caché, el original.")
