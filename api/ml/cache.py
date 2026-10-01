"""
InventAI/o — Caché en memoria de las recomendaciones (INV-23, C3)
La clave es (endpoint, fecha de la foto, versiones de políticas): una foto o
unas políticas nuevas cambian la clave y se recalcula. El TTL cubre lo que la
clave no ve (un modelo reentrenado). Un candado por clave hace que las
peticiones simultáneas esperen un solo cálculo. Vive en el proceso: un
reinicio la vacía.
"""
import threading
import time
from functools import lru_cache
from typing import Callable

from core.config import get_settings


class CacheRecomendaciones:
    def __init__(self, ttl_segundos: float, reloj: Callable[[], float] = time.monotonic):
        self.ttl_segundos = ttl_segundos
        self._reloj = reloj
        self._datos: dict = {}                # clave -> (instante, valor)
        self._candados: dict = {}             # clave -> Lock
        self._candado = threading.Lock()

    def obtener(self, clave: tuple, calcular: Callable[[], object]):
        """Devuelve el valor vigente de `clave` o lo calcula. El primer
        elemento de la clave es el endpoint. Si `calcular` lanza una
        excepción, no se guarda nada."""
        with self._candado:
            candado = self._candados.setdefault(clave, threading.Lock())
        with candado:
            entrada = self._datos.get(clave)
            if entrada is not None and self._reloj() - entrada[0] < self.ttl_segundos:
                return entrada[1]
            valor = calcular()
            with self._candado:
                # una foto nueva deja obsoleta la anterior del mismo endpoint
                for vieja in [c for c in self._datos if c[0] == clave[0] and c != clave]:
                    del self._datos[vieja]
                self._datos[clave] = (self._reloj(), valor)
            return valor

    def claves(self) -> list:
        return list(self._datos)


@lru_cache
def get_cache() -> CacheRecomendaciones:
    return CacheRecomendaciones(get_settings().ML_CACHE_TTL_SEGUNDOS)
