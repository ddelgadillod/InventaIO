"""Petición de `POST /chat` (contrato interno v0, docs/INV-30-requerimientos.md §4.3)."""
from typing import Literal

from pydantic import BaseModel, Field


class Mensaje(BaseModel):
    rol: Literal["usuario", "agente"]
    texto: str = Field(min_length=1)


class ChatPeticion(BaseModel):
    # Los últimos turnos de la conversación; el último es la pregunta del usuario
    mensajes: list[Mensaje] = Field(min_length=1)
