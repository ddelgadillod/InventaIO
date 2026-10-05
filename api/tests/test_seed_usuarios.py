"""INV-26 fix (K8) — Seed de usuarios de prueba, sin base: crea los cinco
usuarios con admin123 y su ubicación, es idempotente y restablece claves."""
from types import SimpleNamespace

import pytest

from core.security import hash_password, verify_password
from models.usuario import Usuario
from scripts.seed_usuarios import CLAVE, USUARIOS, sembrar

UBICACIONES = {"PRINCIPAL": 1, "LA 21": 2, "GLORIETA": 3, "SIN_SUCURSAL": 4, "BODEGA_CENTRAL": 5}


class SesionFalsa:
    """Lo que usa sembrar(): las ubicaciones, buscar un usuario por email, add y commit."""

    def __init__(self, ubicaciones=UBICACIONES, usuarios=()):
        self.ubicaciones = ubicaciones
        self.usuarios = {u.email: u for u in usuarios}
        self.commits = 0

    def execute(self, _sql):
        return [SimpleNamespace(id_sucursal=i, nombre=n) for n, i in self.ubicaciones.items()]

    def query(self, _modelo):
        return self

    def filter(self, condicion):
        self._email = condicion.right.value
        return self

    def first(self):
        return self.usuarios.get(self._email)

    def add(self, usuario):
        self.usuarios[usuario.email] = usuario

    def commit(self):
        self.commits += 1


def test_crea_los_cinco_usuarios_con_su_ubicacion_y_admin123():
    db = SesionFalsa()
    assert sembrar(db) == [(email, "creado") for email, *_ in USUARIOS]
    assert db.commits == 1
    resumen = {u.email: (u.rol, u.id_sucursal, u.activo) for u in db.usuarios.values()}
    assert resumen == {
        "gerente@inventaio.co": ("gerente", None, True),
        "admin.principal@inventaio.co": ("admin_sucursal", 1, True),
        "admin.norte@inventaio.co": ("admin_sucursal", 2, True),
        "admin.sur@inventaio.co": ("admin_sucursal", 3, True),
        "bodega@inventaio.co": ("admin_bodega", 5, True),
    }
    assert all(verify_password(CLAVE, u.password_hash) for u in db.usuarios.values())


def test_es_idempotente_y_restablece_la_clave():
    cambiado = Usuario(email="admin.principal@inventaio.co", nombre="Otro", rol="gerente", id_sucursal=None,
                       activo=False, password_hash=hash_password("Prueba2026"))
    db = SesionFalsa(usuarios=[cambiado])
    primera = dict(sembrar(db))
    assert primera["admin.principal@inventaio.co"] == "restablecido"
    assert (cambiado.nombre, cambiado.rol, cambiado.id_sucursal, cambiado.activo) == ("Laura Gómez", "admin_sucursal", 1, True)
    assert verify_password(CLAVE, cambiado.password_hash)
    assert set(dict(sembrar(db)).values()) == {"restablecido"}
    assert len(db.usuarios) == 5


def test_sin_las_ubicaciones_en_la_bodega_se_detiene():
    db = SesionFalsa(ubicaciones={"PRINCIPAL": 1})
    with pytest.raises(SystemExit, match="BODEGA_CENTRAL"):
        sembrar(db)
    assert db.usuarios == {} and db.commits == 0
