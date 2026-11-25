"""INV-41 (criterio 3) — Lista negra de refresh tokens en Redis (docs/INV-41-requerimientos.md, H3 a H5, D2, T1 a T3).
Sin Redis ni Postgres: un Redis en memoria con SET NX EX y EXISTS, un reloj falso y una sesión falsa."""
import logging

import pytest
import redis
from fastapi.testclient import TestClient

from auth.lista_negra import PREFIJO, ListaNegra, get_lista_negra
from core.database import get_db
from core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
)
from main import app
from models.usuario import Usuario

EMAIL, CLAVE = "gerente@inventaio.co", "Clave-2026"


class Reloj:
    def __init__(self):
        self.ahora = 1_800_000_000.0

    def __call__(self):
        return self.ahora


class RedisFalso:
    """SET con NX y EX, y EXISTS, con vencimiento por el reloj falso; `caido` imita la falta de conexión.
    Lo comparten varias ListaNegra, como dos procesos del Core API o uno antes y otro después de reiniciar."""

    def __init__(self, reloj):
        self.reloj, self.datos, self.caido = reloj, {}, False

    def _revisar(self):
        if self.caido:
            raise redis.ConnectionError("Error 111 connecting to redis:6379. Connection refused.")

    def _vigente(self, clave):
        valor, vence = self.datos.get(clave, (None, None))
        if vence is not None and vence <= self.reloj():
            self.datos.pop(clave)
            return None
        return valor

    def set(self, clave, valor, nx=False, ex=None):
        self._revisar()
        if nx and self._vigente(clave) is not None:
            return None
        self.datos[clave] = (valor, None if ex is None else self.reloj() + ex)
        return True

    def exists(self, clave):
        self._revisar()
        return int(self._vigente(clave) is not None)


@pytest.fixture
def reloj():
    return Reloj()


@pytest.fixture
def redis_falso(reloj):
    return RedisFalso(reloj)


@pytest.fixture
def lista(redis_falso, reloj):
    return ListaNegra(redis_falso, reloj=reloj)


# ── ListaNegra ──────────────────────────────────────

def test_revocar_marca_una_sola_vez_hasta_el_vencimiento(lista, reloj):
    exp = reloj.ahora + 600
    assert lista.revocar("token-a", exp) is True
    assert lista.revocar("token-a", exp) is False
    assert lista.revocado("token-a")
    reloj.ahora += 599
    assert lista.revocado("token-a")
    reloj.ahora += 1
    assert not lista.revocado("token-a")


def test_guarda_la_huella_y_no_el_token(lista, redis_falso, reloj):
    lista.revocar("token-secreto", reloj.ahora + 60)
    (clave,) = redis_falso.datos
    assert clave.startswith(PREFIJO) and len(clave) == len(PREFIJO) + 64
    assert "token-secreto" not in clave


def test_un_token_ya_vencido_se_guarda_al_menos_un_segundo(lista, redis_falso, reloj):
    lista.revocar("viejo", reloj.ahora - 100)
    (valor, vence), = redis_falso.datos.values()
    assert vence == reloj.ahora + 1


def test_los_errores_de_redis_no_se_ocultan(lista, redis_falso, reloj):
    redis_falso.caido = True
    with pytest.raises(redis.RedisError):
        lista.revocar("token-a", reloj.ahora + 60)
    with pytest.raises(redis.RedisError):
        lista.revocado("token-a")


def test_get_lista_negra_usa_redis_de_la_configuracion():
    get_lista_negra.cache_clear()
    try:
        cliente = get_lista_negra().cliente
        assert isinstance(cliente, redis.Redis)
        assert cliente.connection_pool.connection_kwargs["socket_timeout"] == 0.5
    finally:
        get_lista_negra.cache_clear()


# ── Endpoints ───────────────────────────────────────

class SesionFalsa:
    """Responde por id o por email, que es como buscan el login, la renovación y get_current_user."""

    def __init__(self, *usuarios):
        self.usuarios = usuarios

    def query(self, _modelo):
        return self

    def filter(self, condicion):
        self._campo, self._valor = condicion.left.key, condicion.right.value
        return self

    def first(self):
        return next((u for u in self.usuarios if str(getattr(u, self._campo)) == str(self._valor)), None)


def usuario(id_, email, activo=True):
    return Usuario(id=id_, email=email, nombre="Prueba", rol="gerente", id_sucursal=None, activo=activo,
                   password_hash=hash_password(CLAVE))


@pytest.fixture
def gerente():
    return usuario(1, EMAIL)


@pytest.fixture
def otro():
    return usuario(2, "admin.norte@inventaio.co")


@pytest.fixture
def http(redis_falso, gerente, otro):
    sesion = SesionFalsa(gerente, otro)
    app.dependency_overrides[get_db] = lambda: sesion
    # Una ListaNegra nueva por petición sobre el mismo Redis: lo que sobrevive es lo que está en Redis
    app.dependency_overrides[get_lista_negra] = lambda: ListaNegra(redis_falso)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def tokens(u):
    datos = {"sub": str(u.id), "email": u.email, "rol": u.rol}
    return create_access_token(datos), create_refresh_token(datos)


def renovar(http, refresh):
    return http.post("/api/auth/refresh", json={"refresh_token": refresh})


def cerrar(http, access, refresh):
    return http.post("/api/auth/logout", json={"refresh_token": refresh},
                     headers={"Authorization": f"Bearer {access}"})


def test_cada_refresh_token_sirve_una_vez(http, gerente):
    _, refresh = tokens(gerente)
    r = renovar(http, refresh)
    assert r.status_code == 200
    nuevo = r.json()["refresh_token"]
    assert nuevo != refresh

    r = renovar(http, refresh)
    assert r.status_code == 401
    assert r.json()["detail"] == "Token invalidado. Inicie sesión nuevamente."
    assert renovar(http, nuevo).status_code == 200


def test_dos_logins_en_el_mismo_segundo_dan_refresh_tokens_distintos(gerente):
    assert tokens(gerente)[1] != tokens(gerente)[1]
    assert len(decode_token(tokens(gerente)[1])["jti"]) == 32


def test_un_token_cerrado_sigue_rechazado_despues_de_reiniciar(http, gerente, redis_falso):
    """Criterio 3: la lista vive en Redis, no en el proceso. Cada petición usa una ListaNegra nueva."""
    access, refresh = tokens(gerente)
    assert cerrar(http, access, refresh).status_code == 200
    assert len(redis_falso.datos) == 1
    r = renovar(http, refresh)
    assert r.status_code == 401
    assert r.json()["detail"] == "Token invalidado. Inicie sesión nuevamente."


def test_sin_redis_la_renovacion_falla_cerrada(http, gerente, redis_falso, caplog):
    _, refresh = tokens(gerente)
    redis_falso.caido = True
    with caplog.at_level(logging.WARNING, logger="auth.router"):
        r = renovar(http, refresh)
    assert r.status_code == 401
    assert r.json()["detail"] == "No se pudo renovar la sesión. Inicie sesión nuevamente."
    assert "se rechaza" in caplog.records[-1].getMessage()


def test_sin_redis_el_cierre_de_sesion_responde_503(http, gerente, redis_falso, caplog):
    access, refresh = tokens(gerente)
    redis_falso.caido = True
    with caplog.at_level(logging.ERROR, logger="auth.router"):
        r = cerrar(http, access, refresh)
    assert r.status_code == 503
    assert "no se registró el cierre" in caplog.records[-1].getMessage()


@pytest.mark.parametrize("cual", ["de otro usuario", "inválido", "de acceso"])
def test_el_cierre_de_sesion_ignora_lo_que_no_es_un_refresh_token_propio(http, gerente, otro, redis_falso, cual):
    access, _ = tokens(gerente)
    access_otro, refresh_otro = tokens(otro)
    ajeno = {"de otro usuario": refresh_otro, "inválido": "no-es-un-jwt", "de acceso": access_otro}[cual]
    assert cerrar(http, access, ajeno).status_code == 200
    assert redis_falso.datos == {}
    if cual == "de otro usuario":
        assert renovar(http, refresh_otro).status_code == 200


@pytest.mark.parametrize("token,detalle", [
    ("no-es-un-jwt", "Refresh token inválido o expirado"),
    ("acceso", "Se requiere un refresh token"),
])
def test_la_renovacion_rechaza_tokens_invalidos_sin_tocar_redis(http, gerente, redis_falso, token, detalle):
    if token == "acceso":
        token = tokens(gerente)[0]
    r = renovar(http, token)
    assert r.status_code == 401 and r.json()["detail"] == detalle
    assert redis_falso.datos == {}


def test_la_renovacion_rechaza_una_cuenta_desactivada(http, gerente, redis_falso):
    _, refresh = tokens(gerente)
    gerente.activo = False
    r = renovar(http, refresh)
    assert r.status_code == 401 and r.json()["detail"] == "Usuario no encontrado o desactivado"
    assert redis_falso.datos == {}
