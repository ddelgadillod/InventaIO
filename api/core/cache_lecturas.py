"""
InventAI/o — Caché de lecturas en Redis (INV-41, docs/INV-41-requerimientos.md H16 y D5)

Las lecturas de inventario, alertas por reglas y reportes recorren la bodega en cada petición: unos 0,3 s de CPU
cada una, y con 10 usuarios la t3.medium de staging llegó al 100 %. Sus datos solo cambian al recargar la bodega,
así que la respuesta se guarda en Redis y se reutiliza.

- **La clave** combina el endpoint con sus parámetros y el rol y la sucursal del usuario, que es todo aquello de lo
  que dependen los permisos (core/ubicaciones.py). Dos usuarios con el mismo rol y la misma sucursal ven lo mismo.
- **La versión de los datos** forma parte de la clave. Es un contador de los cambios en el esquema dw
  (pg_stat_user_tables), junto con la fecha de hoy en Bogotá. Una recarga cambia la clave, y lo viejo vence solo.
  La versión se consulta a lo sumo cada VERSION_S segundos.
- **Antes de responder** se resuelve al usuario igual que get_current_user: con un token inválido o una cuenta
  desactivada no hay caché, y el endpoint responde su 401 o 403.
- **Qué se guarda:** solo las respuestas 200.
- **Si Redis no responde**, se responde sin caché: los permisos ya se validaron, así que no hay riesgo.
- **CACHE_LECTURAS_S** es la vida de cada entrada. En 0 (el valor por defecto, en desarrollo y en las pruebas) la
  caché está apagada.
"""
import hashlib
import inspect
import logging
import time
from collections.abc import Callable
from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

import redis
from fastapi import HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.routing import APIRoute
from sqlalchemy import text

from auth.dependencies import resolver_usuario
from core.config import get_settings
from core.database import get_db

log = logging.getLogger(__name__)

PREFIJO = "api:lectura:"
BOGOTA = ZoneInfo("America/Bogota")
VERSION_S = 30
SQL_VERSION = text("""
    SELECT COALESCE(SUM(n_tup_ins + n_tup_upd + n_tup_del), 0) FROM pg_stat_user_tables WHERE schemaname = 'dw'
""")


class CacheLecturas:
    def __init__(self, cliente: redis.Redis | None, vida_s: int, reloj: Callable[[], float] = time.monotonic):
        self.cliente = cliente
        self.vida_s = vida_s
        self.reloj = reloj
        self._version: tuple[float, str] | None = None   # (cuándo se consultó, versión)
        self._avisado = False

    @property
    def activa(self) -> bool:
        return self.cliente is not None and self.vida_s > 0

    def version(self, db) -> str:
        if self._version and self.reloj() - self._version[0] < VERSION_S:
            return self._version[1]
        cambios = db.execute(SQL_VERSION).scalar()
        version = f"{cambios}:{datetime.now(BOGOTA).date()}"
        self._version = (self.reloj(), version)
        return version

    @staticmethod
    def clave(version: str, rol: str, id_sucursal, ruta: str, consulta: str) -> str:
        parametros = "&".join(sorted(p for p in consulta.split("&") if p))
        huella = hashlib.sha256(f"{version}|{rol}|{id_sucursal}|{ruta}?{parametros}".encode()).hexdigest()
        return PREFIJO + huella

    def _redis(self, metodo: str, *args):
        try:
            resultado = getattr(self.cliente, metodo)(*args)
        except redis.RedisError as e:
            if not self._avisado:
                log.warning("Redis no responde (%s): las lecturas se responden sin caché", e)
                self._avisado = True
            return None
        self._avisado = False
        return resultado

    def leer(self, clave: str) -> bytes | None:
        return self._redis("get", clave)

    def guardar(self, clave: str, cuerpo: bytes) -> None:
        self._redis("setex", clave, self.vida_s, cuerpo)


@lru_cache
def get_cache_lecturas() -> CacheLecturas:
    s = get_settings()
    if s.CACHE_LECTURAS_S <= 0:
        return CacheLecturas(None, 0)
    cliente = redis.Redis(host=s.REDIS_HOST, port=s.REDIS_PORT, socket_timeout=0.5, socket_connect_timeout=0.5)
    return CacheLecturas(cliente, s.CACHE_LECTURAS_S)


def _clave_de(request: Request, cache: CacheLecturas) -> str | None:
    """La clave de esta petición, o None si no hay usuario válido (el endpoint responde su 401 o 403)."""
    autorizacion = request.headers.get("authorization", "")
    if not autorizacion.lower().startswith("bearer "):
        return None
    # Como FastAPI: get_db es un generador, y su reemplazo en las pruebas puede devolver la sesión directamente
    recurso = request.app.dependency_overrides.get(get_db, get_db)()
    db = next(recurso) if inspect.isgenerator(recurso) else recurso
    try:
        usuario, _ = resolver_usuario(autorizacion[7:], db)
        version = cache.version(db)
    except HTTPException:
        return None
    finally:
        if inspect.isgenerator(recurso):
            recurso.close()
    return cache.clave(version, usuario.rol, usuario.id_sucursal, request.url.path, request.url.query)


class RutaConCache(APIRoute):
    """Para los routers de solo lectura: sus GET pasan por la caché (APIRouter(route_class=RutaConCache))."""

    def get_route_handler(self):
        original = super().get_route_handler()
        if "GET" not in self.methods:
            return original

        async def con_cache(request: Request) -> Response:
            cache = request.app.dependency_overrides.get(get_cache_lecturas, get_cache_lecturas)()
            if not cache.activa:
                return await original(request)
            clave = await run_in_threadpool(_clave_de, request, cache)
            if clave is None:
                return await original(request)
            guardado = await run_in_threadpool(cache.leer, clave)
            if guardado is not None:
                return Response(guardado, media_type="application/json", headers={"X-Cache": "hit"})
            respuesta = await original(request)
            if respuesta.status_code == 200 and getattr(respuesta, "body", None):
                await run_in_threadpool(cache.guardar, clave, bytes(respuesta.body))
                respuesta.headers["X-Cache"] = "miss"
            return respuesta

        return con_cache
