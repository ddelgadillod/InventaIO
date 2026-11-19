"""
InventAI/o — Pydantic schemas del pronóstico en el Core API (INV-25)
El mismo contrato que POST /api/predict de ml_service (docs/ML-SERVICE-API.md),
expuesto con token y permisos en POST /api/ml/predict.
"""
from datetime import date

from pydantic import BaseModel, Field, model_validator


class PrediccionRequest(BaseModel):
    producto_id: str | None = Field(None, description="Código de negocio del producto (codigo_item), ej. 'P1632'.")
    id_producto: int | None = Field(None, description="Alternativa a producto_id: dw.dim_producto.id_producto.")
    sucursal_id: str | None = Field(None, description="Nombre de la sucursal: PRINCIPAL, LA 21 o GLORIETA.")
    id_sucursal: int | None = Field(None, description="Alternativa a sucursal_id: dw.dim_sucursal.id_sucursal.")
    horizonte: int = Field(..., description="Días hábiles del pronóstico. Solo se acepta 15.")
    fecha_corte: date | None = Field(
        None, description="Fecha de los datos con que se predice; por defecto, el último día con ventas.")
    fecha_inicio: date | None = Field(
        None, description=("Primer día de la ventana (INV-79). Pasada: con lo que se sabía el día hábil anterior y con lo "
                           "vendido. Futura: la ventana empieza ese día. Sin ella, después de la fecha de operación (hoy)."))
    fecha_fin: date | None = Field(
        None, description="Último día de un rango (INV-79): la respuesta trae `rango`, aproximado. Máximo 90 días hábiles.")

    @model_validator(mode="after")
    def _fechas(self):
        if self.fecha_corte is not None and (self.fecha_inicio is not None or self.fecha_fin is not None):
            raise ValueError("fecha_corte no se combina con fecha_inicio ni con fecha_fin: para una fecha pasada, usar fecha_inicio")
        if self.fecha_inicio is not None and self.fecha_fin is not None and self.fecha_fin < self.fecha_inicio:
            raise ValueError("fecha_fin es anterior a fecha_inicio")
        return self


class IntervaloConfianza(BaseModel):
    limite_inferior: float = Field(..., description="Siempre 0: no hay un modelo de cuantil bajo.")
    limite_superior: float = Field(..., description="Cuantil de negocio (qα) de la demanda acumulada.")
    alpha_negocio: float = Field(..., description="Cuantil que representa limite_superior (0,893 o 0,167).")


class TramoRango(BaseModel):
    desde: str
    hasta: str
    dias_habiles: int = Field(..., description="Días hábiles del tramo (15 o menos).")
    prediccion_q50_aproximada: float = Field(..., description="Mediana de su ventana por días hábiles / 15.")
    ventas_reales: float | None = Field(None, description="Lo vendido en el tramo, solo si está entero en la historia.")


class RangoPronostico(BaseModel):
    desde: str
    hasta: str
    dias_habiles: int = Field(..., description="Días hábiles del rango (máximo 90).")
    prediccion_q50_aproximada: float = Field(..., description="Mediana aproximada del rango: la suma de la de sus tramos.")
    metodo: str = Field(..., description="«reparto» (15 días hábiles o menos) o «ventanas_encadenadas».")
    ventanas: list[TramoRango] = Field(..., description="Una entrada por ventana de 15 días hábiles, recortada al rango.")
    ventas_reales: float | None = Field(None, description="Lo vendido en el rango, solo si está entero en la historia.")
    fuera_de_lo_medido: bool = Field(..., description="La última ventana empieza más de 90 días hábiles después del dato.")
    aproximado: bool = Field(True, description="Siempre verdadero: sin cantidad de reposición.")


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
    modelo_entrenado_en: str | None = None
    fecha_datos: str | None = Field(None, description="Último día con datos de ventas (INV-62).")
    fecha_operacion: str | None = Field(None, description="Fecha desde la que se pronostica: hoy, nunca antes de fecha_datos (INV-62).")
    ventana_desde: str | None = Field(None, description="Primer día hábil de la ventana del pronóstico (INV-62).")
    ventana_hasta: str | None = Field(None, description="Último día hábil de la ventana del pronóstico (INV-62).")
    dias_habiles_sin_datos: int | None = Field(None, description="Días hábiles entre fecha_datos y fecha_operacion (INV-62).")
    fuera_de_lo_medido: bool | None = Field(None, description="Más de 90 días hábiles sin datos: fuera de lo que cubrió la medición del desfase (INV-62).")
    ventas_reales_ventana: float | None = Field(None, description="Lo vendido en la ventana, solo si está entera en la historia (INV-79).")
    rango: RangoPronostico | None = Field(None, description="Solo con fecha_fin (INV-79).")
