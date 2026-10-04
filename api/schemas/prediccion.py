"""
InventAI/o — Pydantic schemas del pronóstico en el Core API (INV-25)
El mismo contrato que POST /api/predict de ml_service (docs/ML-SERVICE-API.md),
expuesto con token y permisos en POST /api/ml/predict.
"""
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class PrediccionRequest(BaseModel):
    producto_id: Optional[str] = Field(None, description="Código de negocio del producto (codigo_item), ej. 'P1632'.")
    id_producto: Optional[int] = Field(None, description="Alternativa a producto_id: dw.dim_producto.id_producto.")
    sucursal_id: Optional[str] = Field(None, description="Nombre de la sucursal: PRINCIPAL, LA 21 o GLORIETA.")
    id_sucursal: Optional[int] = Field(None, description="Alternativa a sucursal_id: dw.dim_sucursal.id_sucursal.")
    horizonte: int = Field(..., description="Días hábiles del pronóstico. Solo se acepta 15.")
    fecha_corte: Optional[date] = Field(
        None, description="Fecha de los datos con que se predice; por defecto, el último día con ventas.")


class IntervaloConfianza(BaseModel):
    limite_inferior: float = Field(..., description="Siempre 0: no hay un modelo de cuantil bajo.")
    limite_superior: float = Field(..., description="Cuantil de negocio (qα) de la demanda acumulada.")
    alpha_negocio: float = Field(..., description="Cuantil que representa limite_superior (0,893 o 0,167).")


class PrediccionResponse(BaseModel):
    producto_id: str
    id_producto: int
    sucursal_id: str
    id_sucursal: int
    horizonte_dias: int
    rama: str = Field(..., description="intermitente, suave_no_perecedero o suave_perecedero.")
    prediccion_q50: float = Field(..., description="Mediana de la demanda acumulada en los 15 días hábiles.")
    intervalo_confianza: IntervaloConfianza
    interpretacion: str
    fecha_features: str
    modelo_entrenado_en: Optional[str] = None
