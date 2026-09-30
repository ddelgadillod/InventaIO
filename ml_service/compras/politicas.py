"""
InventAI/o — ML Service: políticas de compras (INV-21, B1-B13)
Se leen de politicas_inv21.json, versionado en el repo, y se validan al
arrancar el servicio, igual que las de transferencias (INV-22): un archivo
inválido detiene el arranque en vez de recomendar con reglas equivocadas.

Los números (lead time, días de pedido, mínimo por línea, umbrales de
urgencia) y el grupo semanal se cambian en el JSON sin tocar código. Los
campos de texto nombran la regla que implementa el motor: otro valor se
rechaza porque exigiría código nuevo. Ver docs/INV-21-compras.md.
"""
import json
from datetime import date
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from transferencias.politicas import DIAS_SEMANA, DiaSemana

Marca = Literal["perecedero", "requiere_frio"]


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FechasPedido(_Estricto):
    """B2: días fijos del mes (1 a 28, para que existan en todos los meses) o de la semana."""
    dias_mes: Optional[List[int]] = Field(None, min_length=1)
    dias_semana: Optional[List[DiaSemana]] = Field(None, min_length=1)

    @model_validator(mode="after")
    def _uno_de_los_dos(self):
        if (self.dias_mes is None) == (self.dias_semana is None):
            raise ValueError("indicar dias_mes o dias_semana, no ambos")
        if self.dias_mes is not None and not all(1 <= d <= 28 for d in self.dias_mes):
            raise ValueError("dias_mes admite días del 1 al 28")
        return self

    def dias_semana_iso(self) -> set:
        return {DIAS_SEMANA[d] for d in self.dias_semana or []}


class CalendarioPedidos(_Estricto):
    quincenal: FechasPedido
    semanal: FechasPedido


class Bodega(_Estricto):
    """B9: la compra para la Bodega descuenta el sobrante que ya tiene."""
    descontar_sobrante: Literal[True]


class Urgencia(_Estricto):
    """B12: días hábiles hasta agotarse (sobre q50)."""
    urgente_dias: float = Field(ge=0)
    alta_dias: float = Field(ge=0)

    @model_validator(mode="after")
    def _orden(self):
        if self.alta_dias < self.urgente_dias:
            raise ValueError("urgencia.alta_dias no puede ser menor que urgencia.urgente_dias")
        return self


class PoliticasCompras(_Estricto):
    version: int = Field(ge=1)
    fecha: date
    horizonte_modelo_dias: Literal[15]          # los modelos solo predicen 15 días hábiles
    lead_time_dias: int = Field(ge=1)           # B1
    calendario_pedidos: CalendarioPedidos       # B2
    grupo_semanal: List[Marca]                  # B7: qué marcas piden cada semana
    destino_directo: List[Marca]                # B8
    punto_pedido: Literal["q50"]                # B4
    nivel: Literal["max_qalfa_q50"]             # B5
    redondeo: Literal["arriba"]                 # B6
    minimo_linea: int = Field(ge=1)             # B6
    bodega: Bodega                              # B9
    stock_negativo: Literal["alerta_y_compra_si_hay_pronostico"]   # B11
    q50_cero: Literal["sin_compra"]             # B10
    sin_pronostico: Literal["sin_compra"]       # B10
    urgencia: Urgencia                          # B12

    @model_validator(mode="after")
    def _frio_y_perecederos_nunca_a_la_bodega(self):
        # A3 y A5 de INV-22: la Bodega no tiene frío y los perecederos no entran.
        if set(self.destino_directo) != {"perecedero", "requiere_frio"}:
            raise ValueError("destino_directo debe incluir perecedero y requiere_frio (A3 y A5 de INV-22)")
        return self


def cargar_politicas_compras(path) -> PoliticasCompras:
    """Lee y valida el archivo de políticas. ValueError si falta o no es válido."""
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"Falta el archivo de políticas de compras: {path}")
    try:
        return PoliticasCompras.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValidationError) as e:
        raise ValueError(f"Políticas de compras inválidas en {path}: {e}") from e
