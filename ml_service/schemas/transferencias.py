"""
InventAI/o — ML Service: schemas Pydantic de transferencias (INV-22)
Contrato de POST /api/transferencias. Ver docs/INV-22-transferencias.md.
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
    version: int
    fecha: str


class Traslado(BaseModel):
    producto_id: str
    origen: str
    destino: str
    cantidad: int = Field(..., description="Entera, hacia abajo; en kilos, con el descuento por pérdidas (P11).")
    unidad: Unidad
    urgencia: Urgencia = Field(..., description="La del destino (P13).")
    dias_hasta_agotarse: Optional[float] = Field(
        None, description="Días hábiles hasta agotarse el destino sin el traslado, sobre q50. Nulo en vigilancia.")
    fecha_llegada: str
    dias_habiles_llegada: int
    llega_tarde: bool = Field(..., description="El destino se agota antes de que llegue el traslado (P13).")


class BalanceFila(BaseModel):
    producto_id: str
    sucursal: str
    tipo_ubicacion: Literal["bodega_central", "sucursal"]
    rama: Optional[str] = None
    stock: float = Field(..., description="Stock de la foto; 0 si la ubicación no tiene fila.")
    q50: Optional[float] = None
    limite_superior: Optional[float] = None
    objetivo: Optional[float] = None
    maximo: Optional[float] = None
    excedente: Optional[float] = None
    excedente_sin_destino: Optional[float] = Field(None, description="Excedente que se queda en el origen (P12).")
    deficit: Optional[float] = None
    deficit_vigilancia: Optional[float] = Field(None, description="Solo en vigilancia: qα − stock (P14).")
    recibido: int
    enviado: int
    deficit_neto: Optional[float] = Field(None, description="Déficit − recibido: la entrada de INV-21 (P15).")
    estado: Literal["origen", "destino", "vigilancia", "equilibrio", "sin_pronostico", "stock_negativo", "bodega"]
    urgencia: Optional[Urgencia] = None
    dias_hasta_agotarse: Optional[float] = None
    unidad: Unidad


class Alerta(BaseModel):
    producto_id: str
    sucursal: str
    tipo: Literal["stock_negativo", "sin_pronostico"]
    stock: Optional[float] = None
    accion: Literal["pedido_urgente", "ninguna"]
    detalle: str


class Resumen(BaseModel):
    productos: int
    traslados: int
    cantidad_trasladada: int
    deficit_total: float
    deficit_neto: float
    excedente_sin_destino: float
    alertas: int


class TransferenciasResponse(BaseModel):
    fecha_inventario: str = Field(..., description="Fecha de la foto de dw.fact_inventario usada.")
    fecha_pronostico: str = Field(..., description="Fecha as-of del pronóstico (la de la foto).")
    horizonte_dias: int
    politicas: PoliticasUsadas
    traslados: List[Traslado]
    balance: Optional[List[BalanceFila]] = None
    alertas: List[Alerta]
    no_encontrados: List[str]
    resumen: Resumen
