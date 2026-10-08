"""
InventAI/o — ML Service: schemas Pydantic
INV-20. Desde el fix de la bodega, el producto y la sucursal se pueden
indicar por clave de negocio (codigo_item, nombre) o por el SERIAL de
Postgres que usa api/ (id_producto, id_sucursal).
"""
from datetime import date

from pydantic import BaseModel, Field, model_validator


class PrediccionRequest(BaseModel):
    producto_id: str | None = Field(None, description="Código de negocio del producto (codigo_item), ej. 'P841'.")
    id_producto: int | None = Field(None, description="Alternativa a producto_id: dw.dim_producto.id_producto.")
    sucursal_id: str | None = Field(None, description="Nombre de la sucursal, ej. 'PRINCIPAL'.")
    id_sucursal: int | None = Field(None, description="Alternativa a sucursal_id: dw.dim_sucursal.id_sucursal.")
    horizonte: int = Field(..., description="Horizonte de pronóstico en días hábiles. Solo 15 está soportado.")
    fecha_corte: date | None = Field(
        None,
        description=("Fecha de los datos con que se calcula la predicción (as-of). Por defecto, el último día "
                     "con ventas en la bodega; una fecha anterior reproduce lo que el modelo habría dicho ese día."),
    )

    @model_validator(mode="after")
    def _identificadores(self):
        if self.producto_id is None and self.id_producto is None:
            raise ValueError("indicar producto_id (codigo_item) o id_producto")
        if self.sucursal_id is None and self.id_sucursal is None:
            raise ValueError("indicar sucursal_id (nombre) o id_sucursal")
        return self


class IntervaloConfianza(BaseModel):
    limite_inferior: float = Field(..., description="Siempre 0: no hay un modelo de cuantil bajo.")
    limite_superior: float = Field(
        ..., description=("Cuantil de negocio de la demanda acumulada. Con alpha 0.167 (perecederos) es un cuantil "
                          "bajo y queda por debajo de prediccion_q50: no es una cota de reposición."),
    )
    alpha_negocio: float = Field(
        ..., description="Cuantil de negocio usado para el límite superior (costos Cu/Co validados por el negocio)."
    )


class PrediccionResponse(BaseModel):
    producto_id: str = Field(..., description="codigo_item del producto.")
    id_producto: int = Field(..., description="dw.dim_producto.id_producto.")
    sucursal_id: str = Field(..., description="Nombre de la sucursal.")
    id_sucursal: int = Field(..., description="dw.dim_sucursal.id_sucursal.")
    horizonte_dias: int = Field(..., description="Días hábiles del pronóstico (15).")
    rama: str = Field(
        ..., description=("Rama de enrutamiento del modelo (ADI/CV2, INV-14/15): intermitente, suave_no_perecedero "
                          "o suave_perecedero."),
    )
    prediccion_q50: float = Field(
        ..., description=("Mediana de la demanda acumulada en el horizonte, en la unidad de venta del producto -- "
                          "comparable contra el piso por WAPE (INV-17)."),
    )
    intervalo_confianza: IntervaloConfianza
    interpretacion: str = Field(
        ..., description="Traducción en lenguaje directo de la predicción, generada por reglas fijas."
    )
    fecha_features: str = Field(..., description="Fecha de los datos de la bodega con que se calcularon las features (as-of).")
    modelo_entrenado_en: str | None = Field(
        None, description="fecha_generacion de models/nivel1_metadata.json (trazabilidad a MLflow, INV-17)."
    )
