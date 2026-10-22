"""
InventAI/o — Esquemas del chat (INV-36)
La petición tiene el mismo formato que la del agente (contrato v1, §4.3 de
docs/INV-30-requerimientos.md): el Core API solo valida y no recorta (X2).
"""
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from core.config import get_settings


class MensajeChat(BaseModel):
    rol: Literal["usuario", "agente"]
    texto: str = Field(min_length=1)


class PeticionChat(BaseModel):
    """El historial de la conversación; el último mensaje es la pregunta del usuario (X1)."""
    mensajes: list[MensajeChat] = Field(min_length=1)

    model_config = {"json_schema_extra": {"example": {"mensajes": [
        {"rol": "usuario", "texto": "¿Qué productos están críticos en GLORIETA?"},
        {"rol": "agente", "texto": "En GLORIETA hay 173 productos en estado crítico…"},
        {"rol": "usuario", "texto": "¿Y en LA 21?"},
    ]}}}

    @model_validator(mode="after")
    def _limites(self):
        s = get_settings()
        if len(self.mensajes) > s.CHAT_MAX_MENSAJES:
            raise ValueError(f"A lo sumo {s.CHAT_MAX_MENSAJES} mensajes (6 turnos y la pregunta)")
        if any(len(m.texto) > s.CHAT_MAX_CARACTERES_MENSAJE for m in self.mensajes):
            raise ValueError(f"Cada mensaje admite a lo sumo {s.CHAT_MAX_CARACTERES_MENSAJE} caracteres")
        if sum(len(m.texto) for m in self.mensajes) > s.CHAT_MAX_CARACTERES_TOTAL:
            raise ValueError(f"La conversación admite a lo sumo {s.CHAT_MAX_CARACTERES_TOTAL} caracteres")
        if self.mensajes[-1].rol != "usuario":
            raise ValueError("El último mensaje debe ser del usuario")
        return self


class SaludChat(BaseModel):
    estado: Literal["listo"]
    modelo: str
    version: str
    flujos_activos: int
    limite: int
