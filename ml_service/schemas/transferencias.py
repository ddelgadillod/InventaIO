"""
InventAI/o — ML Service: schemas Pydantic de transferencias (INV-22)
Contrato de POST /api/transferencias. Ver docs/INV-22-transferencias.md y,
campo por campo, docs/ML-SERVICE-API.md.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

Urgencia = Literal["urgente", "alta", "normal", "vigilancia"]
Unidad = Literal["unidad", "kg"]


class TransferenciasRequest(BaseModel):
    productos: Optional[List[str]] = Field(
        None, min_length=1,
        description=("Códigos de producto (codigo_item). Sin la lista se procesan todos los productos con fila en "
                     "la foto de inventario. Un código desconocido va a `no_encontrados`, no produce error."),
    )
    incluir_balance: bool = Field(True, description="Con false solo se devuelven traslados, alertas y resumen.")


class PoliticasUsadas(BaseModel):
    version: int = Field(..., description="Versión de politicas_inv22.json usada en el cálculo.")
    fecha: str = Field(..., description="Fecha de esa versión.")


class Traslado(BaseModel):
    producto_id: str = Field(..., description="codigo_item del producto.")
    origen: str = Field(..., description="BODEGA_CENTRAL o una sucursal con excedente; la Bodega va primero (P10).")
    destino: str = Field(..., description="Sucursal física que recibe; nunca la Bodega (P12).")
    cantidad: int = Field(..., description="Entera, hacia abajo; en kilos, con el descuento por pérdidas (P11).")
    unidad: Unidad = Field(..., description="kg si el producto se vende por kilo (dim_producto.se_vende_por_kilo).")
    urgencia: Urgencia = Field(..., description="La del destino (P13).")
    dias_hasta_agotarse: Optional[float] = Field(
        None, description="Días hábiles hasta agotarse el destino sin el traslado, sobre q50. Nulo en vigilancia.")
    fecha_llegada: str = Field(..., description="Fecha en que llega el traslado (P13, Q7).")
    dias_habiles_llegada: int = Field(..., description="Días hábiles entre la foto y la llegada.")
    llega_tarde: bool = Field(..., description="El destino se agota antes de que llegue el traslado (P13).")


class BalanceFila(BaseModel):
    producto_id: str = Field(..., description="codigo_item del producto.")
    sucursal: str = Field(..., description="Nombre de la ubicación, incluida BODEGA_CENTRAL.")
    tipo_ubicacion: Literal["bodega_central", "sucursal"]
    rama: Optional[str] = Field(None, description="Rama del modelo; nula en la Bodega y sin pronóstico.")
    stock: float = Field(..., description="Stock de la foto; 0 si la ubicación no tiene fila.")
    q50: Optional[float] = Field(None, description="Mediana de la demanda a 15 días hábiles (la de /api/predict).")
    limite_superior: Optional[float] = Field(None, description="Cuantil de negocio qα (el de /api/predict).")
    objetivo: Optional[float] = Field(None, description="Stock objetivo de la sucursal: q50 (P2).")
    maximo: Optional[float] = Field(None, description="max(qα × (1 + margen), q50); sobre esto hay excedente (P1).")
    excedente: Optional[float] = Field(
        None, description="Lo que puede ceder: stock − max(máximo, exhibición); en la Bodega, todo su stock (P3).")
    excedente_sin_destino: Optional[float] = Field(None, description="Excedente que se queda en el origen (P12).")
    deficit: Optional[float] = Field(None, description="max(0, q50 − stock), con el stock negativo como 0.")
    deficit_vigilancia: Optional[float] = Field(None, description="Solo en vigilancia: qα − stock (P14).")
    recibido: int = Field(..., description="Total que llega en los traslados sugeridos.")
    enviado: int = Field(..., description="Total que sale en los traslados sugeridos.")
    deficit_neto: Optional[float] = Field(None, description="Déficit − recibido: la entrada de INV-21 (P15).")
    estado: Literal["origen", "destino", "vigilancia", "equilibrio", "sin_pronostico", "stock_negativo", "bodega"] = Field(
        ..., description=("bodega: la Bodega Central; origen: sobre el máximo, puede enviar; destino: bajo el objetivo, "
                          "necesita recibir; equilibrio: entre ambos; vigilancia: q50 = 0 (P14); sin_pronostico y "
                          "stock_negativo: no participan y generan alerta (P6, P7)."))
    urgencia: Optional[Urgencia] = Field(None, description="Por días hasta agotarse (P13); nula sin pronóstico.")
    dias_hasta_agotarse: Optional[float] = Field(
        None, description="stock / (q50 / 15) en días hábiles; nulo si q50 es 0 o no hay pronóstico.")
    unidad: Unidad


class Alerta(BaseModel):
    producto_id: str = Field(..., description="codigo_item del producto.")
    sucursal: str = Field(..., description="Ubicación de la alerta (puede ser BODEGA_CENTRAL).")
    tipo: Literal["stock_negativo", "sin_pronostico"] = Field(
        ..., description="stock_negativo: la foto tiene stock < 0; sin_pronostico: la fila de la foto no tiene pronóstico.")
    stock: Optional[float] = Field(None, description="Stock de la foto.")
    accion: Literal["pedido_urgente", "ninguna"] = Field(
        ..., description="pedido_urgente con stock negativo (P7); ninguna sin pronóstico (P6).")
    detalle: str = Field(..., description="Explicación; sin pronóstico, incluye el motivo.")


class Resumen(BaseModel):
    productos: int = Field(..., description="Productos procesados, sin no_encontrados ni repetidos.")
    traslados: int
    cantidad_trasladada: int = Field(..., description="Suma de cantidades: mezcla unidades y kilos.")
    deficit_total: float = Field(..., description="Suma de deficit del balance, antes de los traslados.")
    deficit_neto: float = Field(..., description="Suma de deficit_neto: lo que pasa a compras (INV-21).")
    excedente_sin_destino: float = Field(..., description="Suma de excedente_sin_destino, incluida la Bodega.")
    alertas: int


class TransferenciasResponse(BaseModel):
    fecha_inventario: str = Field(..., description="Fecha de la foto de dw.fact_inventario usada.")
    fecha_pronostico: str = Field(..., description="Fecha as-of del pronóstico (la de la foto).")
    horizonte_dias: int = Field(..., description="Días hábiles del pronóstico (15).")
    politicas: PoliticasUsadas
    traslados: List[Traslado] = Field(..., description="Ordenados por urgencia, producto, destino y origen.")
    balance: Optional[List[BalanceFila]] = Field(
        None, description="Una fila por producto y ubicación; no viene con incluir_balance=false.")
    alertas: List[Alerta]
    no_encontrados: List[str] = Field(..., description="Códigos pedidos que no existen en dw.dim_producto.")
    resumen: Resumen
