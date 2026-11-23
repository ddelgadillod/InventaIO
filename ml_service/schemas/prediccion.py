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
    fecha_inicio: date | None = Field(
        None,
        description=("INV-79: primer día de la ventana. Pasada (hasta el último dato): se pronostica con lo que se sabía el día "
                     "hábil anterior y se trae lo vendido. Futura: features del último dato y la ventana empieza ese día. "
                     "Sin ella, la ventana empieza después de la fecha de operación (hoy)."),
    )
    fecha_fin: date | None = Field(
        None,
        description=("INV-79: último día de un rango. La respuesta trae `rango` con la mediana aproximada (reparto o ventanas "
                     "de 15 días encadenadas), sin cantidad de reposición. Máximo 90 días hábiles."),
    )

    @model_validator(mode="after")
    def _identificadores(self):
        if self.producto_id is None and self.id_producto is None:
            raise ValueError("indicar producto_id (codigo_item) o id_producto")
        if self.sucursal_id is None and self.id_sucursal is None:
            raise ValueError("indicar sucursal_id (nombre) o id_sucursal")
        if self.fecha_corte is not None and (self.fecha_inicio is not None or self.fecha_fin is not None):
            raise ValueError("fecha_corte no se combina con fecha_inicio ni con fecha_fin: para una fecha pasada, usar fecha_inicio")
        if self.fecha_inicio is not None and self.fecha_fin is not None and self.fecha_fin < self.fecha_inicio:
            raise ValueError("fecha_fin es anterior a fecha_inicio")
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


class TramoRango(BaseModel):
    desde: str = Field(..., description="Primer día hábil del tramo.")
    hasta: str = Field(..., description="Último día hábil del tramo.")
    dias_habiles: int = Field(..., description="Días hábiles del tramo (15 o menos).")
    prediccion_q50_aproximada: float = Field(..., description="Mediana de su ventana por días hábiles / 15.")
    ventas_reales: float | None = Field(None, description="Unidades vendidas en el tramo, solo si está entero en la historia.")


class RangoPronostico(BaseModel):
    desde: str = Field(..., description="Primer día hábil del rango.")
    hasta: str = Field(..., description="Último día hábil del rango.")
    dias_habiles: int = Field(..., description="Días hábiles del rango (máximo 90).")
    prediccion_q50_aproximada: float = Field(..., description="Mediana aproximada del rango: la suma de la de sus tramos.")
    metodo: str = Field(..., description="«reparto» (15 días hábiles o menos) o «ventanas_encadenadas».")
    ventanas: list[TramoRango] = Field(..., description="Una entrada por ventana de 15 días hábiles, recortada al rango.")
    ventas_reales: float | None = Field(None, description="Unidades vendidas en el rango, solo si está entero en la historia.")
    fuera_de_lo_medido: bool = Field(
        ..., description="La última ventana empieza más de 90 días hábiles después del dato con que se pronostica.")
    aproximado: bool = Field(True, description="Siempre verdadero: sin cantidad de reposición (INV-80 traerá 7 y 30 días).")


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
    fecha_datos: str | None = Field(None, description="INV-62: último día con datos de ventas (igual que fecha_features).")
    fecha_operacion: str | None = Field(
        None, description="INV-62: fecha desde la que se pronostica (hoy en Bogotá, o FECHA_OPERACION); nunca antes de fecha_datos.")
    ventana_desde: str | None = Field(None, description="INV-62: primer día hábil de la ventana del pronóstico.")
    ventana_hasta: str | None = Field(None, description="INV-62: último día hábil de la ventana del pronóstico.")
    dias_habiles_sin_datos: int | None = Field(
        None, description="INV-62: días hábiles entre fecha_datos y fecha_operacion (0 si los datos están al día).")
    fuera_de_lo_medido: bool | None = Field(
        None, description="INV-62: verdadero si los días hábiles sin datos pasan de 90, lo que cubrió la medición del desfase.")
    ventas_reales_ventana: float | None = Field(
        None, description="INV-79: unidades vendidas en la ventana, solo si está entera en la historia (fecha pasada).")
    rango: RangoPronostico | None = Field(None, description="INV-79: solo con fecha_fin.")
