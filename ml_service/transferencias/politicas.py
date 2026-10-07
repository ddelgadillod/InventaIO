"""
InventAI/o — ML Service: políticas de transferencias (INV-22, P1-P15)
Se leen de politicas_inv22.json, versionado en el repo, y se validan al
arrancar el servicio: un archivo inválido detiene el arranque en vez de
recomendar con reglas equivocadas.

Los valores numéricos (márgenes, reserva, mínimo, descuento en kilos,
umbrales de urgencia, días de traslado) se cambian en el JSON sin tocar
código. Los campos de texto nombran la regla que implementa el motor: hoy
cada uno admite un solo valor, y otro valor se rechaza porque exigiría
código nuevo. Ver docs/INV-22-transferencias.md.
"""
import json
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

DIAS_SEMANA = {"lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2, "jueves": 3, "viernes": 4,
               "sabado": 5, "sábado": 5, "domingo": 6}
DiaSemana = Literal["lunes", "martes", "miercoles", "miércoles", "jueves", "viernes", "sabado", "sábado", "domingo"]


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StockMaximo(_Estricto):
    """P1: máximo = qα(15) × (1 + margen); el origen conserva unidades_exhibicion."""
    margen_perecedero: float = Field(ge=0)
    margen_no_perecedero: float = Field(ge=0)
    unidades_exhibicion: float = Field(ge=0)


class Perecederos(_Estricto):
    """P4: directo entre sucursales, solo hacia sucursales con q50 > 0."""
    traslado: Literal["directo"]
    solo_con_venta: Literal[True]


class Frio(_Estricto):
    """P5: directo entre sucursales; nunca entra a la Bodega (A3)."""
    traslado: Literal["directo"]
    entra_a_bodega: Literal[False]


class Reparticion(_Estricto):
    """P9: nivelar cobertura, desempate por mayor q50."""
    metodo: Literal["nivelar_cobertura"]
    desempate: Literal["q50"]


class Cantidades(_Estricto):
    """P11: enteros hacia abajo; kilos con descuento; mínimo por traslado."""
    minimo: int = Field(ge=1)
    descuento_kilos: float = Field(ge=0, lt=1)


class Urgencia(_Estricto):
    """P13: días hábiles hasta agotarse (sobre q50)."""
    urgente_dias: float = Field(ge=0)
    alta_dias: float = Field(ge=0)
    llega_tarde: Literal["trasladar_y_marcar"]

    @model_validator(mode="after")
    def _orden(self):
        if self.alta_dias < self.urgente_dias:
            raise ValueError("urgencia.alta_dias no puede ser menor que urgencia.urgente_dias")
        return self


class Traslado(_Estricto):
    """P13 / Q7: días fijos de salida; sin ellos, N días hábiles después de la foto."""
    dias_semana: list[DiaSemana]
    dias_habiles_si_no_hay_dias_fijos: int = Field(ge=1)

    def dias_semana_iso(self) -> set:
        """Los días fijos como números de weekday() (lunes = 0)."""
        return {DIAS_SEMANA[d] for d in self.dias_semana}


class Politicas(_Estricto):
    version: int = Field(ge=1)
    fecha: date
    horizonte_dias: Literal[15]  # A1: los modelos solo predicen 15 días hábiles
    stock_maximo: StockMaximo
    objetivo_destino: Literal["q50"]                       # P2
    reserva_bodega: float = Field(ge=0)                     # P3
    perecederos: Perecederos                                # P4
    frio: Frio                                              # P5
    sin_pronostico: Literal["excluir"]                      # P6
    stock_negativo: Literal["como_cero"]                    # P7
    foto_sin_ventas: Literal["bloquear"]                    # P8
    reparticion: Reparticion                                # P9
    origenes: Literal["bodega_primero"]                     # P10
    cantidades: Cantidades                                  # P11
    excedente_sin_destino: Literal["se_queda"]              # P12
    urgencia: Urgencia                                      # P13
    traslado: Traslado                                      # P13 / Q7
    q50_cero: Literal["solo_sobrante"]                      # P14
    compras_descuenta: Literal["sugeridos"]                 # P15


def cargar_politicas(path) -> Politicas:
    """Lee y valida el archivo de políticas. ValueError si falta o no es válido."""
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"Falta el archivo de políticas de transferencias: {path}")
    try:
        return Politicas.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValidationError) as e:
        raise ValueError(f"Políticas de transferencias inválidas en {path}: {e}") from e
