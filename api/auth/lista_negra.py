"""
InventAI/o — Lista negra de refresh tokens en Redis (INV-41, docs/INV-41-requerimientos.md H3 a H5)
Un refresh token queda revocado al renovarse (rotación) o al cerrar sesión, hasta su vencimiento. Vive en Redis,
que guarda en disco (AOF): un reinicio del Core API no lo borra y varios procesos lo comparten.

Se guarda la huella SHA-256 del token, no el token: el disco de Redis no tiene credenciales (T1). Marcar usa
SET NX, así que la rotación es atómica: de dos renovaciones simultáneas con el mismo token, solo una gana (H4).

Los errores de Redis no se ocultan: el endpoint decide. La renovación falla cerrada con 401 (D2) y el cierre de
sesión responde 503 (T3).
"""
import hashlib
import math
import time
from collections.abc import Callable
from functools import lru_cache

import redis

from core.config import get_settings

PREFIJO = "auth:revocado:"


class ListaNegra:
    def __init__(self, cliente: redis.Redis, reloj: Callable[[], float] = time.time):
        self.cliente = cliente
        self.reloj = reloj

    @staticmethod
    def clave(token: str) -> str:
        return PREFIJO + hashlib.sha256(token.encode()).hexdigest()

    def revocar(self, token: str, exp: float) -> bool:
        """Revoca el token hasta `exp` (segundos de época, el campo del JWT). True si lo revocó ahora; False si
        ya estaba revocado."""
        segundos = max(math.ceil(exp - self.reloj()), 1)
        return bool(self.cliente.set(self.clave(token), 1, nx=True, ex=segundos))

    def revocado(self, token: str) -> bool:
        return bool(self.cliente.exists(self.clave(token)))


@lru_cache
def get_lista_negra() -> ListaNegra:
    s = get_settings()
    # Los mismos tiempos cortos del límite de login: con Redis caído, la respuesta no espera más de medio segundo
    cliente = redis.Redis(host=s.REDIS_HOST, port=s.REDIS_PORT, socket_timeout=0.5, socket_connect_timeout=0.5)
    return ListaNegra(cliente)
