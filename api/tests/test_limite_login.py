"""INV-66 (CA 5) — Límite de intentos fallidos de login (docs/INV-66-requerimientos.md, P9 a P13).
Sin Redis ni Postgres: un reloj falso, un Redis en memoria con la misma interfaz y una sesión falsa."""
import logging

import pytest
import redis
from fastapi import HTTPException
from fastapi.testclient import TestClient

from auth import limite_login as modulo
from auth.limite_login import (
    ContadorMemoria,
    ContadorRedis,
    LimiteLogin,
    get_limite_login,
)
from core.database import get_db
from core.security import hash_password
from main import app
from models.usuario import Usuario

EMAIL, CLAVE, IP = "gerente@inventaio.co", "Clave-2026", "10.0.0.7"


class Reloj:
    def __init__(self):
        self.ahora = 1000.0

    def __call__(self):
        return self.ahora


class RedisFalso:
    """GET, TTL, INCR, EXPIRE NX y DELETE en un pipeline, con el reloj falso; `caido` imita la falta de conexión."""

    def __init__(self, reloj):
        self.reloj, self.datos, self.caido, self.llamadas = reloj, {}, False, 0

    def pipeline(self):
        return PipelineFalso(self)

    def _vigente(self, clave):
        valor, vence = self.datos.get(clave, (None, None))
        if vence is not None and vence <= self.reloj():
            self.datos.pop(clave)
            return None, None
        return valor, vence

    def _revisar(self):
        self.llamadas += 1
        if self.caido:
            raise redis.ConnectionError("Error 111 connecting to redis:6379. Connection refused.")

    def delete(self, clave):
        self._revisar()
        self.datos.pop(clave, None)


class PipelineFalso:
    def __init__(self, r):
        self.r, self.ops = r, []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def __getattr__(self, nombre):
        def encolar(*args, **kwargs):
            self.ops.append((nombre, args, kwargs))
            return self
        return encolar

    def execute(self):
        self.r._revisar()
        salida = []
        for nombre, args, kwargs in self.ops:
            clave = args[0]
            valor, vence = self.r._vigente(clave)
            if nombre == "get":
                salida.append(None if valor is None else str(valor).encode())
            elif nombre == "ttl":
                salida.append(-2 if valor is None else (-1 if vence is None else int(vence - self.r.reloj())))
            elif nombre == "incr":
                self.r.datos[clave] = ((valor or 0) + 1, vence)
                salida.append((valor or 0) + 1)
            elif nombre == "expire":
                if kwargs.get("nx") and vence is not None:
                    salida.append(False)
                else:
                    self.r.datos[clave] = (valor, self.r.reloj() + args[1])
                    salida.append(True)
        return salida


@pytest.fixture
def reloj():
    return Reloj()


@pytest.fixture
def redis_falso(reloj):
    return RedisFalso(reloj)


@pytest.fixture
def limite(redis_falso, reloj):
    return LimiteLogin(ContadorRedis(redis_falso), max_usuario_ip=5, max_ip=20, ventana=900, reloj=reloj)


def bloquea(limite, email=EMAIL, ip=IP) -> HTTPException | None:
    try:
        limite.verificar(email, ip)
    except HTTPException as e:
        return e
    return None


# ── Reglas (P9 a P12) ───────────────────────────────

def test_el_quinto_fallo_bloquea_con_429_y_retry_after(limite, reloj):
    for _ in range(4):
        limite.registrar_fallo(EMAIL, IP)
    assert bloquea(limite) is None
    limite.registrar_fallo(EMAIL, IP)
    reloj.ahora += 60
    e = bloquea(limite)
    assert e.status_code == 429
    assert e.headers["Retry-After"] == "840"
    assert e.detail == "Demasiados intentos fallidos. Intenta de nuevo en 14 minutos."


def test_el_bloqueo_es_por_email_e_ip(limite):
    for _ in range(5):
        limite.registrar_fallo(EMAIL, IP)
    assert bloquea(limite) is not None
    assert bloquea(limite, ip="10.0.0.8") is None
    assert bloquea(limite, email="bodega@inventaio.co") is None
    assert bloquea(limite, email=" Gerente@Inventaio.CO ") is not None


def test_al_vencer_la_ventana_vuelve_a_aceptar(limite, reloj):
    for _ in range(5):
        limite.registrar_fallo(EMAIL, IP)
    reloj.ahora += 899
    assert bloquea(limite).headers["Retry-After"] == "1"
    reloj.ahora += 1
    assert bloquea(limite) is None


def test_la_ventana_empieza_con_el_primer_fallo(limite, reloj):
    limite.registrar_fallo(EMAIL, IP)
    reloj.ahora += 800
    for _ in range(4):
        limite.registrar_fallo(EMAIL, IP)
    assert bloquea(limite).headers["Retry-After"] == "100"


def test_veinte_fallos_desde_una_ip_con_emails_distintos_bloquean_la_ip(limite):
    for i in range(20):
        limite.registrar_fallo(f"u{i}@inventaio.co", IP)
    e = bloquea(limite, email="nuevo@inventaio.co")
    assert e.status_code == 429
    assert bloquea(limite, email="nuevo@inventaio.co", ip="10.0.0.8") is None


def test_un_login_correcto_limpia_el_contador_del_email_y_no_el_de_la_ip(limite, redis_falso):
    for _ in range(4):
        limite.registrar_fallo(EMAIL, IP)
    limite.registrar_exito(EMAIL, IP)
    for _ in range(4):
        limite.registrar_fallo(EMAIL, IP)
    assert bloquea(limite) is None
    assert redis_falso.datos["login:fallos:ip:10.0.0.7"][0] == 8


def test_un_minuto_se_escribe_en_singular(limite, reloj):
    for _ in range(5):
        limite.registrar_fallo(EMAIL, IP)
    reloj.ahora += 850
    assert bloquea(limite).detail == "Demasiados intentos fallidos. Intenta de nuevo en 1 minuto."


# ── Redis caído (P13) ───────────────────────────────

def test_sin_redis_cuenta_en_memoria_y_avisa_una_vez(limite, redis_falso, reloj, caplog):
    redis_falso.caido = True
    with caplog.at_level(logging.WARNING, logger="auth.limite_login"):
        for _ in range(5):
            limite.registrar_fallo(EMAIL, IP)
        e = bloquea(limite)
    assert e.status_code == 429
    avisos = [r.getMessage() for r in caplog.records]
    assert len(avisos) == 1 and "cuenta en memoria" in avisos[0]


def test_sin_redis_no_lo_reintenta_en_cada_login_sino_a_los_30_s(limite, redis_falso, reloj, caplog):
    redis_falso.caido = True
    limite.registrar_fallo(EMAIL, IP)
    assert redis_falso.llamadas == 1
    limite.registrar_fallo(EMAIL, IP)
    bloquea(limite)
    assert redis_falso.llamadas == 1

    redis_falso.caido = False
    reloj.ahora += modulo.REINTENTO_REDIS_S
    with caplog.at_level(logging.WARNING, logger="auth.limite_login"):
        limite.registrar_fallo(EMAIL, IP)
    assert redis_falso.llamadas > 1
    assert "vuelve a contar en Redis" in caplog.records[-1].getMessage()


def test_la_memoria_purga_las_claves_vencidas_al_pasar_el_tope(monkeypatch, reloj):
    monkeypatch.setattr(modulo, "MAX_CLAVES_EN_MEMORIA", 3)
    memoria = ContadorMemoria(reloj)
    for i in range(4):
        memoria.sumar(f"k{i}", 10)
    reloj.ahora += 10
    memoria.sumar("nueva", 10)
    assert list(memoria.claves) == ["nueva"]


def test_get_limite_login_usa_redis_y_la_configuracion():
    get_limite_login.cache_clear()
    try:
        limite = get_limite_login()
        assert isinstance(limite.principal, ContadorRedis)
        assert (limite.max_usuario_ip, limite.max_ip, limite.ventana) == (5, 20, 900)
    finally:
        get_limite_login.cache_clear()


# ── POST /api/auth/login ────────────────────────────

class SesionFalsa:
    def __init__(self, usuario):
        self.usuario = usuario
        self.consultas = 0

    def query(self, _modelo):
        return self

    def filter(self, condicion):
        self._email = condicion.right.value
        return self

    def first(self):
        self.consultas += 1
        return self.usuario if self._email == self.usuario.email else None


@pytest.fixture
def cliente(limite):
    usuario = Usuario(id=1, email=EMAIL, nombre="Carlos Martínez", rol="gerente", id_sucursal=None, activo=True,
                      password_hash=hash_password(CLAVE))
    sesion = SesionFalsa(usuario)
    app.dependency_overrides[get_db] = lambda: sesion
    app.dependency_overrides[get_limite_login] = lambda: limite
    try:
        yield TestClient(app, client=(IP, 50000)), sesion
    finally:
        app.dependency_overrides.clear()


def test_login_bloquea_al_sexto_intento_aun_con_la_clave_correcta(cliente):
    http, sesion = cliente
    for _ in range(5):
        assert http.post("/api/auth/login", json={"email": EMAIL, "password": "errada"}).status_code == 401
    consultas = sesion.consultas

    r = http.post("/api/auth/login", json={"email": EMAIL, "password": CLAVE})
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0
    assert r.json()["detail"].startswith("Demasiados intentos fallidos")
    assert sesion.consultas == consultas          # el bloqueo se revisa antes de ir a la base


def test_login_correcto_limpia_y_un_email_inexistente_cuenta(cliente, redis_falso):
    http, _ = cliente
    for _ in range(4):
        http.post("/api/auth/login", json={"email": EMAIL, "password": "errada"})
    assert http.post("/api/auth/login", json={"email": EMAIL, "password": CLAVE}).status_code == 200
    assert f"login:fallos:usuario_ip:{IP}:{EMAIL}" not in redis_falso.datos

    assert http.post("/api/auth/login", json={"email": "nadie@inventaio.co", "password": "x"}).status_code == 401
    assert redis_falso.datos[f"login:fallos:usuario_ip:{IP}:nadie@inventaio.co"][0] == 1
