"""INV-25 — Regla de permisos por ubicación (core/ubicaciones.py), sin base:
D1 (admin_bodega ve todo), D2 (admin_sucursal ve el stock de la Bodega),
R1 (otra ubicación pedida explícitamente: 403) y R2 (inexistente o
SIN_SUCURSAL: 422)."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from core.ubicaciones import ALERTAS, STOCK, VENTAS, filtro_sucursal, resolver_sucursal
from tests.conftest import usuario

UBICACIONES = {1: {"nombre": "PRINCIPAL", "tipo": "principal"}, 2: {"nombre": "LA 21", "tipo": "estandar"},
               3: {"nombre": "GLORIETA", "tipo": "estandar"}, 5: {"nombre": "BODEGA_CENTRAL", "tipo": "bodega_central"}}
DATOS = [STOCK, ALERTAS, VENTAS]


def _codigo(user, sucursal_id, dato):
    with pytest.raises(HTTPException) as exc:
        resolver_sucursal(UBICACIONES, user, sucursal_id, dato)
    return exc.value.status_code, exc.value.detail


@pytest.mark.parametrize("rol, id_sucursal", [("gerente", None), ("admin_bodega", 5)])
@pytest.mark.parametrize("dato", DATOS)
def test_gerente_y_admin_bodega_ven_todo_y_filtran_cualquier_ubicacion(rol, id_sucursal, dato):
    user = usuario(rol, id_sucursal)
    assert resolver_sucursal(UBICACIONES, user, None, dato) is None
    for suc in (1, 2, 3, 5):
        assert resolver_sucursal(UBICACIONES, user, suc, dato) == suc


@pytest.mark.parametrize("dato", DATOS)
def test_admin_sucursal_sin_parametro_o_con_la_suya_ve_su_sucursal(dato):
    user = usuario("admin_sucursal", 2)
    assert resolver_sucursal(UBICACIONES, user, None, dato) == 2
    assert resolver_sucursal(UBICACIONES, user, 2, dato) == 2


def test_admin_sucursal_ve_el_stock_de_la_bodega_pero_no_sus_alertas_ni_ventas():
    user = usuario("admin_sucursal", 1)
    assert resolver_sucursal(UBICACIONES, user, 5, STOCK) == 5
    for dato in (ALERTAS, VENTAS):
        assert _codigo(user, 5, dato) == (
            403, "Solo puede consultar su sucursal (PRINCIPAL); la Bodega Central, solo en el stock")


@pytest.mark.parametrize("dato", DATOS)
def test_admin_sucursal_con_otra_sucursal_403(dato):
    assert _codigo(usuario("admin_sucursal", 1), 3, dato) == (403, "Solo puede consultar su sucursal (PRINCIPAL)")


@pytest.mark.parametrize("id_sucursal", [None, 4, 5])          # sin sucursal, SIN_SUCURSAL o la Bodega
def test_admin_sucursal_sin_sucursal_fisica_403(id_sucursal):
    assert _codigo(usuario("admin_sucursal", id_sucursal), None, STOCK) == (
        403, "El usuario no tiene una sucursal asignada")


@pytest.mark.parametrize("rol", ["gerente", "admin_bodega", "admin_sucursal"])
@pytest.mark.parametrize("sucursal_id", [4, 99])               # SIN_SUCURSAL o inexistente
def test_sucursal_invalida_422_antes_que_el_permiso(rol, sucursal_id):
    codigo, detalle = _codigo(usuario(rol, 1), sucursal_id, STOCK)
    assert codigo == 422 and detalle.startswith(f"sucursal_id inválido: {sucursal_id}.")
    assert "5 (BODEGA_CENTRAL)" in detalle


class DbFalsa:
    """Responde a SQL_UBICACIONES con las filas de UBICACIONES."""

    def execute(self, *args, **kwargs):
        return self

    def fetchall(self):
        return [SimpleNamespace(id_sucursal=i, **u) for i, u in UBICACIONES.items()]


def test_filtro_sucursal_arma_la_condicion_sql():
    assert filtro_sucursal(DbFalsa(), usuario("gerente"), None, VENTAS, "v") == ("", {})
    assert filtro_sucursal(DbFalsa(), usuario("admin_sucursal", 3), None, VENTAS, "v") == (
        "AND v.id_sucursal = :suc_permitida", {"suc_permitida": 3})
