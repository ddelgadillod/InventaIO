"""
InventAI/o — Límite de flujos de chat (INV-36, X3)
Un flujo por usuario y CHAT_MAX_FLUJOS en total: el modelo local atiende una
petición a la vez (OLLAMA_NUM_PARALLEL=1, 8 GB de VRAM). Si no hay cupo, 429
inmediato con Retry-After; el panel muestra «en cola» y reintenta (INV-35).
Los contadores viven en memoria porque el Core API corre en un solo proceso
(C4); con varios procesos (INV-34) pasan a Redis.
"""
from functools import lru_cache

from fastapi import HTTPException, status

from core.config import get_settings


class Limitador:
    def __init__(self, max_total: int, retry_after: int):
        self.max_total = max_total
        self.retry_after = retry_after
        self.activos: set[int] = set()

    def reservar(self, usuario_id: int) -> None:
        # Sin await entre la consulta y el registro: en un solo proceso, es atómico
        cabeceras = {"Retry-After": str(self.retry_after)}
        if usuario_id in self.activos:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Ya hay una respuesta en curso", headers=cabeceras)
        if len(self.activos) >= self.max_total:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "El asistente está atendiendo otra consulta",
                                headers=cabeceras)
        self.activos.add(usuario_id)

    def liberar(self, usuario_id: int) -> None:
        self.activos.discard(usuario_id)


@lru_cache
def get_limitador() -> Limitador:
    s = get_settings()
    return Limitador(s.CHAT_MAX_FLUJOS, s.CHAT_RETRY_AFTER_S)
