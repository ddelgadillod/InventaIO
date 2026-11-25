"""INV-41 (D5) — Caché de lecturas en Redis (core/cache_lecturas.py). Sin Redis ni Postgres: una app mínima con un
router de solo lectura, un Redis en memoria y una sesión falsa que resuelve usuarios y la versión de los datos."""
import logging

import pytest
import redis
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from auth.dependencies import get_current_user
from core import cache_lecturas as modulo
from core.cache_lecturas import CacheLecturas, RutaConCache, get_cache_lecturas
from core.database import get_db
from core.security import create_access_token
from models.usuario import Usuario


class Reloj:
    def __init__(self):
        self.ahora = 1000.0

    def __call__(self):
        return self.ahora


class RedisFalso:
    def __init__(self):
        self.datos, self.caido, self.vidas = {}, False, {}

    def _revisar(self):
        if self.caido:
            raise redis.ConnectionError("Error 111 connecting to redis:6379. Connection refused.")

    def get(self, clave):
        self._revisar()
        return self.datos.get(clave)

    def setex(self, clave, vida, valor):
        self._revisar()
        self.datos[clave], self.vidas[clave] = valor, vida


class SesionFalsa:
    """Usuarios por id, y la versión de los datos que da pg_stat_user_tables."""

    def __init__(self, usuarios, version):
        self.usuarios, self.version = {u.id: u for u in usuarios}, version

    def query(self, _modelo):
        return self

    def filter(self, condicion):
        self._id = int(condicion.right.value)
        return self

    def first(self):
        return self.usuarios.get(self._id)

    def execute(self, _sql):
        return self

    def scalar(self):
        return self.version["cambios"]


def usuario(id_, rol, sucursal=None, activo=True):
    return Usuario(id=id_, email=f"u{id_}@inventaio.co", nombre="Prueba", rol=rol, id_sucursal=sucursal,
                   activo=activo, password_hash="x")


GERENTE, PRINCIPAL, NORTE = usuario(1, "gerente"), usuario(2, "admin_sucursal", 1), usuario(3, "admin_sucursal", 2)
OTRO_PRINCIPAL = usuario(4, "admin_sucursal", 1)


def token(u):
    return {"Authorization": f"Bearer {create_access_token({'sub': str(u.id), 'email': u.email, 'rol': u.rol})}"}


@pytest.fixture
def contexto():
    llamadas = []
    router = APIRouter(prefix="/api/prueba", route_class=RutaConCache)

    @router.get("/datos")
    def datos(n: int = 0, user: Usuario = Depends(get_current_user)):
        llamadas.append(user.id)
        return {"rol": user.rol, "sucursal": user.id_sucursal, "n": n}

    @router.get("/falla")
    def falla(user: Usuario = Depends(get_current_user)):
        llamadas.append(user.id)
        raise HTTPException(403, "Sin acceso")

    @router.post("/escribe")
    def escribe(user: Usuario = Depends(get_current_user)):
        llamadas.append(user.id)
        return {"ok": True}

    app = FastAPI()
    app.include_router(router)
    r, reloj, version = RedisFalso(), Reloj(), {"cambios": 7}
    cache = CacheLecturas(r, 600, reloj=reloj)
    usuarios = [GERENTE, PRINCIPAL, NORTE, OTRO_PRINCIPAL]
    app.dependency_overrides[get_db] = lambda: SesionFalsa(usuarios, version)
    app.dependency_overrides[get_cache_lecturas] = lambda: cache
    return TestClient(app), llamadas, r, reloj, version, cache


def test_la_segunda_lectura_sale_de_redis_sin_llamar_al_endpoint(contexto):
    http, llamadas, r, *_ = contexto
    primera = http.get("/api/prueba/datos?n=1", headers=token(GERENTE))
    segunda = http.get("/api/prueba/datos?n=1", headers=token(GERENTE))
    assert (primera.headers["X-Cache-Lecturas"], segunda.headers["X-Cache-Lecturas"]) == ("miss", "hit")
    assert primera.json() == segunda.json() == {"rol": "gerente", "sucursal": None, "n": 1}
    assert llamadas == [1]
    assert list(r.vidas.values()) == [600]


def test_comparten_entrada_solo_el_mismo_rol_y_la_misma_sucursal(contexto):
    http, llamadas, r, *_ = contexto
    for u in (PRINCIPAL, OTRO_PRINCIPAL, NORTE, GERENTE):
        http.get("/api/prueba/datos", headers=token(u))
    assert llamadas == [2, 3, 1]          # el otro administrador de la misma sucursal usa la entrada del primero
    assert len(r.datos) == 3
    assert http.get("/api/prueba/datos", headers=token(NORTE)).json()["sucursal"] == 2


def test_los_parametros_cuentan_y_su_orden_no(contexto):
    http, llamadas, *_ = contexto
    http.get("/api/prueba/datos?n=1&x=a", headers=token(GERENTE))
    http.get("/api/prueba/datos?x=a&n=1", headers=token(GERENTE))
    http.get("/api/prueba/datos?n=2&x=a", headers=token(GERENTE))
    assert llamadas == [1, 1]


@pytest.mark.parametrize("cabeceras", [{}, {"Authorization": "Bearer no-es-un-jwt"}])
def test_sin_usuario_valido_no_hay_cache_y_el_endpoint_responde(contexto, cabeceras):
    http, llamadas, r, *_ = contexto
    http.get("/api/prueba/datos", headers=token(GERENTE))
    respuesta = http.get("/api/prueba/datos", headers=cabeceras)
    assert respuesta.status_code in (401, 403)
    assert "X-Cache-Lecturas" not in respuesta.headers


def test_una_cuenta_desactivada_no_recibe_lo_guardado(contexto):
    http, llamadas, *_ = contexto
    desactivado = usuario(5, "gerente", activo=False)
    sesion_usuarios = [GERENTE, desactivado]
    http.app.dependency_overrides[get_db] = lambda: SesionFalsa(sesion_usuarios, {"cambios": 7})
    assert http.get("/api/prueba/datos", headers=token(GERENTE)).status_code == 200
    r = http.get("/api/prueba/datos", headers=token(desactivado))
    assert r.status_code == 403 and r.json()["detail"] == "Cuenta desactivada"


def test_solo_se_guarda_lo_que_responde_200_y_solo_los_get(contexto):
    http, llamadas, r, *_ = contexto
    assert http.get("/api/prueba/falla", headers=token(GERENTE)).status_code == 403
    assert http.get("/api/prueba/falla", headers=token(GERENTE)).status_code == 403
    assert http.post("/api/prueba/escribe", headers=token(GERENTE)).status_code == 200
    assert http.post("/api/prueba/escribe", headers=token(GERENTE)).status_code == 200
    assert llamadas == [1, 1, 1, 1] and r.datos == {}


def test_si_cambian_los_datos_la_clave_cambia(contexto):
    http, llamadas, _, reloj, version, _ = contexto
    http.get("/api/prueba/datos", headers=token(GERENTE))
    version["cambios"] = 9                                 # una recarga de la bodega
    http.get("/api/prueba/datos", headers=token(GERENTE))
    assert llamadas == [1]                                 # la versión se consulta a lo sumo cada 30 s
    reloj.ahora += modulo.VERSION_S
    http.get("/api/prueba/datos", headers=token(GERENTE))
    assert llamadas == [1, 1]


def test_sin_redis_responde_sin_cache_y_avisa_una_vez(contexto, caplog):
    http, llamadas, r, *_ = contexto
    r.caido = True
    with caplog.at_level(logging.WARNING, logger="core.cache_lecturas"):
        for _ in range(3):
            assert http.get("/api/prueba/datos", headers=token(GERENTE)).status_code == 200
    assert llamadas == [1, 1, 1]
    assert len([x for x in caplog.records if "sin caché" in x.getMessage()]) == 1


def test_apagada_no_toca_redis(contexto):
    http, llamadas, r, *_ = contexto
    http.app.dependency_overrides[get_cache_lecturas] = lambda: CacheLecturas(r, 0)
    for _ in range(2):
        assert "X-Cache-Lecturas" not in http.get("/api/prueba/datos", headers=token(GERENTE)).headers
    assert llamadas == [1, 1] and r.datos == {}


def test_get_cache_lecturas_esta_apagada_por_defecto():
    get_cache_lecturas.cache_clear()
    try:
        assert not get_cache_lecturas().activa
    finally:
        get_cache_lecturas.cache_clear()


def test_los_routers_de_lectura_usan_la_cache_y_los_demas_no():
    from alertas.router import router as alertas
    from alertas.router_ml import router as alertas_ml
    from auth.router import router as auth
    from chat.router import router as chat
    from consulta.router import router as consulta
    from inventario.router import router as inventario
    from ml.router import router as ml
    from reportes.router import router as reportes
    for router in (alertas, consulta, inventario, reportes):
        assert router.routes and all(isinstance(r, RutaConCache) for r in router.routes)
    for router in (alertas_ml, auth, chat, ml):
        assert not any(isinstance(r, RutaConCache) for r in router.routes)
