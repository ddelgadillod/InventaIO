"""
InventAI/o — ML Service: schemas Pydantic de compras (INV-21)
Contrato de POST /api/compras. Ver docs/INV-21-compras.md y, campo por
campo, docs/ML-SERVICE-API.md.
"""
from typing import Literal

from pydantic import BaseModel, Field

from schemas.transferencias import PoliticasUsadas, Unidad

UrgenciaCompra = Literal["urgente", "alta", "normal"]
Grupo = Literal["quincenal", "semanal"]
TipoDestino = Literal["bodega_central", "sucursal"]
Motivo = Literal["reposicion", "stock_negativo"]


class ComprasRequest(BaseModel):
    productos: list[str] | None = Field(
        None, min_length=1,
        description=("Códigos de producto (codigo_item). Sin la lista se procesan todos los productos con fila en "
                     "la foto de inventario. Un código desconocido va a `no_encontrados`, no produce error."),
    )
    incluir_detalle: bool = Field(True, description="Con false las líneas no traen el cálculo por sucursal.")


class PoliticasCompraUsadas(BaseModel):
    inv21: PoliticasUsadas = Field(..., description="Versión de politicas_inv21.json.")
    inv22: PoliticasUsadas = Field(..., description="Versión de politicas_inv22.json (traslados descontados).")


class PlanPedido(BaseModel):
    grupo: Grupo = Field(..., description="quincenal (días fijos del mes) o semanal (día fijo de la semana).")
    tipo_destino: TipoDestino = Field(..., description="Ruta: a la Bodega Central o directo a la sucursal.")
    fecha_pedido: str = Field(..., description="Fecha en que sale el pedido: la primera fecha fija en o después de la foto.")
    fecha_llegada: str = Field(..., description="Llegada al destino de la compra, lead time después del pedido.")
    fecha_llegada_sucursal: str = Field(..., description="Llegada a la sucursal; por la Bodega, con el traslado de INV-22.")
    pedido_siguiente: str = Field(..., description="Fecha del pedido que sigue al actual.")
    cubre_hasta: str = Field(..., description="Llegada a la sucursal del pedido siguiente: hasta aquí debe alcanzar la compra.")
    dias_cubiertos: int = Field(..., description="Plazo a cubrir P: días hábiles desde la foto hasta cubre_hasta.")
    dias_hasta_llegada: int = Field(..., description="Días hábiles desde la foto hasta fecha_llegada_sucursal.")


class DetalleCompra(BaseModel):
    sucursal: str
    posicion: float = Field(..., description="max(stock, 0) + recibido en los traslados de INV-22.")
    q50: float = Field(..., description="Mediana de la demanda a 15 días hábiles.")
    limite_superior: float = Field(..., description="Cuantil de negocio qα a 15 días hábiles.")
    punto_pedido: float = Field(..., description="q50 × P / 15: se compra si la posición queda por debajo (B4).")
    nivel: float = Field(..., description="max(qα, q50) × P / 15: hasta aquí se compra (B5).")
    necesidad: float = Field(..., description="nivel − posición.")
    dias_hasta_agotarse: float = Field(..., description="posición / (q50 / 15), en días hábiles.")
    urgencia: UrgenciaCompra
    llega_tarde: bool = Field(..., description="La sucursal se agota antes de que llegue la compra (B12).")
    motivo: Motivo


class LineaCompra(BaseModel):
    producto_id: str = Field(..., description="codigo_item del producto.")
    destino: str = Field(..., description="Sucursal (perecederos y frío) o BODEGA_CENTRAL (lo demás).")
    tipo_destino: TipoDestino
    grupo: Grupo
    cantidad: int = Field(..., description="Entera, hacia arriba (B6); en la Bodega, neta de su sobrante (B9).")
    unidad: Unidad
    urgencia: UrgenciaCompra = Field(..., description="La de la sucursal más urgente de la línea.")
    dias_hasta_agotarse: float = Field(..., description="Los de la sucursal más urgente.")
    fecha_pedido: str
    fecha_llegada: str = Field(..., description="Llegada al destino de la línea.")
    fecha_llegada_sucursal: str = Field(..., description="Llegada a la sucursal (igual a fecha_llegada si es directo).")
    llega_tarde: bool = Field(..., description="Alguna sucursal se agota antes de que le llegue la compra.")
    necesidad: float = Field(..., description="Suma de las necesidades de las sucursales, antes de descontar la Bodega.")
    sobrante_bodega: float | None = Field(None, description="Sobrante de la Bodega descontado; nulo si es directo.")
    motivo: Motivo = Field(..., description="stock_negativo si alguna sucursal compró con el stock tomado como 0.")
    detalle: list[DetalleCompra] | None = Field(None, description="Cálculo por sucursal; no viene con incluir_detalle=false.")


class CubrirConTraslado(BaseModel):
    producto_id: str
    necesidad: float = Field(..., description="Suma de las necesidades de las sucursales.")
    sobrante_bodega: float = Field(..., description="Lo que la Bodega ya tiene y alcanza para cubrirlas.")
    unidad: Unidad
    urgencia: UrgenciaCompra
    dias_hasta_agotarse: float
    detalle: list[DetalleCompra] | None = None


class AlertaCompra(BaseModel):
    producto_id: str
    sucursal: str = Field(..., description="Ubicación de la alerta (puede ser BODEGA_CENTRAL).")
    tipo: Literal["posible_inconsistencia_inventario"]
    stock: float = Field(..., description="Stock negativo de la foto.")
    accion: Literal["compra_urgente", "verificar_conteo"] = Field(
        ..., description="compra_urgente si el par tiene q50 > 0 (compra con stock 0); si no, verificar_conteo (B11).")
    detalle: str


class CantidadPorUnidad(BaseModel):
    unidad: int
    kg: int


class ResumenCompras(BaseModel):
    productos: int = Field(..., description="Productos procesados, sin no_encontrados ni repetidos.")
    lineas: int
    lineas_sucursal: int
    lineas_bodega: int
    cantidad: CantidadPorUnidad = Field(..., description="Suma de cantidades, separada por unidad.")
    cubiertos_por_bodega: int = Field(..., description="Productos que no compran porque la Bodega ya los tiene.")
    alertas: int
    pares_sin_pronostico: int = Field(..., description="Pares sin pronóstico: no compran; el detalle está en /api/transferencias.")


class ComprasResponse(BaseModel):
    fecha_inventario: str = Field(..., description="Fecha de la foto de dw.fact_inventario usada.")
    fecha_pronostico: str = Field(..., description="Fecha as-of del pronóstico (la de la foto).")
    lead_time_dias: int = Field(..., description="Días hábiles entre el pedido y su llegada (B1).")
    politicas: PoliticasCompraUsadas
    calendario: list[PlanPedido] = Field(..., description="Fechas de cada grupo de pedido y ruta.")
    compras: list[LineaCompra] = Field(..., description="Ordenadas por urgencia, producto y destino.")
    cubrir_con_traslado: list[CubrirConTraslado] = Field(
        ..., description="Productos que necesitan reposición pero la Bodega ya la tiene (B9).")
    alertas: list[AlertaCompra]
    no_encontrados: list[str] = Field(..., description="Códigos pedidos que no existen en dw.dim_producto.")
    resumen: ResumenCompras
