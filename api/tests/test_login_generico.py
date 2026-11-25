"""INV-41 (criterio 4) — El login no distingue entre un correo inexistente, una clave incorrecta y una cuenta
desactivada (docs/INV-41-requerimientos.md, H1, H2, D4 y T4). Sin Postgres ni Redis."""
import pytest
from fastapi.testclient import TestClient

from auth import router as modulo
from auth.limite_login import ContadorMemoria, LimiteLogin, get_limite_login
from core.database import get_db
from core.security import hash_password
from main import app
from models.usuario import Usuario

CLAVE, IP = "Clave-2026", "10.0.0.7"
ACTIVO, DESACTIVADO = "gerente@inventaio.co", "bodega@inventaio.co"


class SesionFalsa:
    def __init__(self, *usuarios):
        self.usuarios = {u.email: u for u in usuarios}

    def query(self, _modelo):
        return self

    def filter(self, condicion):
        self._email = condicion.right.value
        return self

    def first(self):
        return self.usuarios.get(self._email)


@pytest.fixture
def limite():
    return LimiteLogin(ContadorMemoria(), max_usuario_ip=5, max_ip=20, ventana=900)


@pytest.fixture
def http(limite):
    usuarios = [Usuario(id=i, email=e, nombre="Prueba", rol="gerente", id_sucursal=None, activo=a,
                        password_hash=hash_password(CLAVE))
                for i, (e, a) in enumerate([(ACTIVO, True), (DESACTIVADO, False)], start=1)]
    app.dependency_overrides[get_db] = lambda: SesionFalsa(*usuarios)
    app.dependency_overrides[get_limite_login] = lambda: limite
    try:
        yield TestClient(app, client=(IP, 50000))
    finally:
        app.dependency_overrides.clear()


def login(http, email, clave):
    return http.post("/api/auth/login", json={"email": email, "password": clave})


def test_las_tres_fallas_dan_el_mismo_401(http):
    respuestas = [
        login(http, "nadie@inventaio.co", CLAVE),   # correo inexistente
        login(http, ACTIVO, "errada"),               # clave incorrecta
        login(http, DESACTIVADO, CLAVE),             # cuenta desactivada, con la clave correcta
    ]
    assert [r.status_code for r in respuestas] == [401, 401, 401]
    assert {r.json()["detail"] for r in respuestas} == {"Credenciales inválidas"}
    assert len({tuple(sorted(r.headers)) for r in respuestas}) == 1


def test_la_cuenta_desactivada_cuenta_como_fallo(http, limite):
    for _ in range(5):
        assert login(http, DESACTIVADO, CLAVE).status_code == 401
    assert login(http, DESACTIVADO, CLAVE).status_code == 429


def test_con_un_correo_inexistente_verifica_contra_el_hash_ficticio(http, monkeypatch):
    verificados = []
    original = modulo.verify_password
    monkeypatch.setattr(modulo, "verify_password", lambda clave, h: verificados.append(h) or original(clave, h))
    login(http, "nadie@inventaio.co", CLAVE)
    assert verificados == [modulo._hash_ficticio()]
    assert verificados[0].startswith("$2b$")     # bcrypt, el mismo costo que los reales


def test_la_clave_correcta_de_una_cuenta_activa_entra(http):
    r = login(http, ACTIVO, CLAVE)
    assert r.status_code == 200
    assert {"access_token", "refresh_token"} <= set(r.json())
