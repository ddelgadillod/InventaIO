"""
InventAI/o — ML Service: schemas Pydantic
INV-20
"""
from typing import Optional

from pydantic import BaseModel, Field


class PrediccionRequest(BaseModel):
    producto_id: str = Field(..., description="Código de negocio del producto (codigo_item), ej. 'P841'")
    sucursal_id: str = Field(..., description="Nombre de la sucursal, ej. 'PRINCIPAL'")
    horizonte: int = Field(..., description="Horizonte de pronóstico en días hábiles. Solo 15 está soportado.")


class IntervaloConfianza(BaseModel):
    limite_inferior: float
    limite_superior: float
    alpha_negocio: float = Field(
        ..., description="Cuantil de negocio usado para el límite superior (costos supuestos, INV-17)."
    )


class PrediccionResponse(BaseModel):
    producto_id: str
    sucursal_id: str
    horizonte_dias: int
    rama: str = Field(..., description="Rama de enrutamiento del modelo (ADI/CV2, INV-14/15).")
    prediccion_q50: float = Field(..., description="Mediana -- comparable contra el piso por WAPE (INV-17).")
    intervalo_confianza: IntervaloConfianza
    interpretacion: str = Field(
        ..., description="Traducción en lenguaje directo de la predicción, generada por reglas fijas."
    )
    fecha_features: str = Field(..., description="fecha_origen de la fila de features usada (as-of).")
    modelo_entrenado_en: Optional[str] = Field(
        None, description="fecha_generacion de models/nivel1_metadata.json (trazabilidad a MLflow, INV-17)."
    )
