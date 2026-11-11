"""
InventAI/o — Límite de intentos fallidos de login (INV-66, CA 5 y H3)
Cuenta los 401 de POST /api/auth/login por email e IP (LOGIN_MAX_FALLOS_USUARIO_IP) y por IP
(LOGIN_MAX_FALLOS_IP), en una ventana fija de LOGIN_VENTANA_S que empieza con el primer fallo. Al llegar al
máximo, 429 con Retry-After hasta que la ventana vence, aunque la clave sea la correcta. Un login correcto
limpia el contador de su email e IP; el de la IP sigue, para frenar a quien prueba muchos correos.

Los contadores viven en Redis: sobreviven a un reinicio y los comparten varios procesos (INV-34). Si Redis no
responde, se cuenta en la memoria del proceso y se avisa una vez en el log: el límite sigue y nadie queda sin
entrar. Mientras tanto, Redis se vuelve a probar cada REINTENTO_REDIS_S, no en cada login. La IP es la que deja
uvicorn detrás de Nginx (H6 de docs/INV-66-requerimientos.md).
"""
import logging
import math
import time
from collections.abc import Callable
from functools import lru_cache

import redis
from fastapi import HTTPException, status

from core.config import get_settings

log = logging.getLogger(__name__)

MAX_CLAVES_EN_MEMORIA = 10_000   # al pasarlas, se purgan las vencidas
REINTENTO_REDIS_S = 30


class ContadorMemoria:
    """Ventanas fijas en un diccionario: el respaldo cuando Redis no responde."""

    def __init__(self, reloj: Callable[[], float] = time.monotonic):
        self.reloj = reloj
        self.claves: dict[str, tuple[int, float]] = {}   # clave → (fallos, cuándo vence)

    def _vigente(self, clave: str) -> tuple[int, float]:
        fallos, vence = self.claves.get(clave, (0, 0.0))
        if vence <= self.reloj():
            self.claves.pop(clave, None)
            return 0, 0.0
        return fallos, vence

    def contar(self, clave: str) -> tuple[int, int]:
        """(fallos, segundos que le quedan a la ventana)"""
        fallos, vence = self._vigente(clave)
        return fallos, math.ceil(vence - self.reloj()) if fallos else 0

    def sumar(self, clave: str, ventana: int) -> None:
        if len(self.claves) > MAX_CLAVES_EN_MEMORIA:
            for k in list(self.claves):
                self._vigente(k)
        fallos, vence = self._vigente(clave)
        self.claves[clave] = (fallos + 1, vence or self.reloj() + ventana)

    def borrar(self, clave: str) -> None:
        self.claves.pop(clave, None)


class ContadorRedis:
    """Los mismos contadores en Redis: INCR y la expiración solo con el primer fallo (EXPIRE NX)."""

    def __init__(self, cliente: redis.Redis):
        self.cliente = cliente

    def contar(self, clave: str) -> tuple[int, int]:
        with self.cliente.pipeline() as p:
            fallos, ttl = p.get(clave).ttl(clave).execute()
        return int(fallos or 0), max(ttl, 0)

    def sumar(self, clave: str, ventana: int) -> None:
        with self.cliente.pipeline() as p:
            p.incr(clave).expire(clave, ventana, nx=True).execute()

    def borrar(self, clave: str) -> None:
        self.cliente.delete(clave)


class LimiteLogin:
    def __init__(self, principal: ContadorRedis | ContadorMemoria, max_usuario_ip: int, max_ip: int,
                 ventana: int, respaldo: ContadorMemoria | None = None,
                 reloj: Callable[[], float] = time.monotonic):
        self.principal = principal
        self.respaldo = respaldo or ContadorMemoria(reloj)
        self.max_usuario_ip, self.max_ip, self.ventana = max_usuario_ip, max_ip, ventana
        self.reloj = reloj
        self.sin_redis = False
        self.reintentar_en = 0.0

    def _llamar(self, metodo: str, *args):
        if self.sin_redis and self.reloj() < self.reintentar_en:
            return getattr(self.respaldo, metodo)(*args)
        try:
            resultado = getattr(self.principal, metodo)(*args)
        except redis.RedisError as e:
            if not self.sin_redis:
                log.warning("Redis no responde (%s): el límite de login cuenta en memoria", e)
                self.sin_redis = True
            self.reintentar_en = self.reloj() + REINTENTO_REDIS_S
            return getattr(self.respaldo, metodo)(*args)
        if self.sin_redis:
            log.warning("Redis responde de nuevo: el límite de login vuelve a contar en Redis")
            self.sin_redis = False
        return resultado

    @staticmethod
    def _claves(email: str, ip: str) -> tuple[str, str]:
        return f"login:fallos:usuario_ip:{ip}:{email.strip().lower()}", f"login:fallos:ip:{ip}"

    def verificar(self, email: str, ip: str) -> None:
        """429 con Retry-After si el email desde esa IP, o la IP, ya agotó sus intentos."""
        espera = 0
        for clave, maximo in zip(self._claves(email, ip), (self.max_usuario_ip, self.max_ip), strict=True):
            fallos, ttl = self._llamar("contar", clave)
            if fallos >= maximo:
                espera = max(espera, ttl, 1)
        if espera:
            minutos = math.ceil(espera / 60)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Demasiados intentos fallidos. Intenta de nuevo en {minutos} "
                       f"{'minuto' if minutos == 1 else 'minutos'}.",
                headers={"Retry-After": str(espera)},
            )

    def registrar_fallo(self, email: str, ip: str) -> None:
        for clave in self._claves(email, ip):
            self._llamar("sumar", clave, self.ventana)

    def registrar_exito(self, email: str, ip: str) -> None:
        self._llamar("borrar", self._claves(email, ip)[0])


@lru_cache
def get_limite_login() -> LimiteLogin:
    s = get_settings()
    # Tiempos cortos: con Redis caído, el login no espera más de medio segundo antes de pasar a memoria
    cliente = redis.Redis(host=s.REDIS_HOST, port=s.REDIS_PORT, socket_timeout=0.5, socket_connect_timeout=0.5)
    return LimiteLogin(ContadorRedis(cliente), s.LOGIN_MAX_FALLOS_USUARIO_IP, s.LOGIN_MAX_FALLOS_IP,
                       s.LOGIN_VENTANA_S)
