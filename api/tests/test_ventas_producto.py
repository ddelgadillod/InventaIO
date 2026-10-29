"""INV-26 (fix, A1) — Ventas por producto en ventanas de 15 días hábiles, sin
base: armar_ventanas y el endpoint con una bodega falsa (G1, G3, la regla de
permisos de INV-25 y los errores). La prueba contra la bodega real está en
test_ventas_producto_integracion.py."""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from consulta.router import SQL_ULTIMOS_HABILES, SQL_VENTAS_PRODUCTO, armar_ventanas
from core.ubicaciones import SQL_UBICACIONES
from tests.conftest import usuario

INICIO = date(2025, 8, 1)
UBICACIONES = [(1, "PRINCIPAL", "principal"), (2, "LA 21", "estandar"), (3, "GLORIETA", "estandar"),
               (5, "BODEGA_CENTRAL", "bodega_central")]
PRODUCTOS = {91: ("P1632", "HUEVOS *UND", "Huevos", False), 92: ("P0002", "SIN VENTAS", "Hogar", False),
             321: ("P1814", "PAPA PASTUSA *KL", "Frutas y verduras", True)}   # (codigo, nombre, categoria, por kilo)


def _dias(n: int) -> list:
    return [INICIO + timedelta(days=i) for i in range(n)]


class Resultado(list):
    def fetchall(self):
        return list(self)

    def fetchone(self):
        return self[0] if self else None


class BodegaFalsa:
    """Responde las consultas del endpoint: ubicaciones, producto, días hábiles
    (los últimos n, del más reciente al más antiguo) y ventas del par."""

    def __init__(self, habiles: list, ventas: dict):
        self.habiles = habiles                      # orden cronológico
        self.ventas = ventas                        # {(codigo, sucursal, fecha): unidades}
        self.consultas = []

    def execute(self, sql, params=None):
        self.consultas.append((sql, params))
        if sql is SQL_UBICACIONES:
            return Resultado(SimpleNamespace(id_sucursal=i, nombre=n, tipo=t) for i, n, t in UBICACIONES)
        if sql is SQL_ULTIMOS_HABILES:
            return Resultado(SimpleNamespace(fecha=f) for f in reversed(self.habiles[-params["n"]:]))
        if sql is SQL_VENTAS_PRODUCTO:
            return Resultado(SimpleNamespace(fecha=f, unidades=u) for (c, s, f), u in self.ventas.items()
                             if (c, s) == (params["codigo"], params["sucursal"])
                             and params["desde"] <= f <= params["hasta"])
        producto = PRODUCTOS.get(params["id"])
        return Resultado([SimpleNamespace(id_producto=params["id"], codigo_item=producto[0], nombre=producto[1],
                                          categoria=producto[2], se_vende_por_kilo=producto[3])] if producto else [])


@pytest.fixture()
def api():
    from auth.dependencies import get_current_user
    from core.database import get_db
    from main import app

    habiles = _dias(130)
    ventas = {("P1632", "PRINCIPAL", f): 10.0 for f in habiles}
    ventas.update({("P1632", "LA 21", habiles[-1]): 7.0, ("P1632", "PRINCIPAL", habiles[-1]): 25.0})
    estado = {"usuario": usuario("gerente"), "db": BodegaFalsa(habiles, ventas)}
    app.dependency_overrides.update({get_current_user: lambda: estado["usuario"], get_db: lambda: estado["db"]})
    with TestClient(app) as http:
        yield SimpleNamespace(http=http, estado=estado, habiles=habiles)
    app.dependency_overrides.clear()


def _get(api, rol, id_sucursal=None, producto=91, **params):
    api.estado["usuario"] = usuario(rol, id_sucursal)
    return api.http.get(f"/api/consulta/productos/{producto}/ventas", params=params)


# ── armar_ventanas (G1) ─────────────────────────────

def test_agrupa_de_15_en_15_y_termina_en_el_ultimo_dia_habil():
    dias = _dias(30)
    ventanas = armar_ventanas(dias, {dias[0]: 4.0, dias[14]: 1.0, dias[15]: 2.0, dias[29]: 3.0}, 15)
    assert [(v.desde, v.hasta, v.unidades) for v in ventanas] == [(dias[0], dias[14], 5.0), (dias[15], dias[29], 5.0)]


def test_descarta_la_ventana_incompleta_del_principio():
    dias = _dias(32)
    ventanas = armar_ventanas(dias, {dias[0]: 100.0, dias[1]: 100.0}, 15)
    assert [(v.desde, v.hasta) for v in ventanas] == [(dias[2], dias[16]), (dias[17], dias[31])]
    assert sum(v.unidades for v in ventanas) == 0.0


def test_un_dia_sin_venta_cuenta_cero_y_con_menos_dias_que_el_horizonte_no_hay_ventanas():
    assert [v.unidades for v in armar_ventanas(_dias(45), {}, 15)] == [0.0, 0.0, 0.0]
    assert armar_ventanas(_dias(14), {}, 15) == []


# ── Endpoint ────────────────────────────────────────

def test_gerente_con_una_sucursal_fisica(api):
    r = _get(api, "gerente", sucursal_id=1)
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["codigo_item"], body["sucursal"], body["horizonte_dias_habiles"]) == ("P1632", "PRINCIPAL", 15)
    assert body["unidad"] == "unidad" and "unidad_medida" not in body
    assert body["fecha_fin"] == api.habiles[-1].isoformat()
    assert len(body["ventanas"]) == 8                                   # por defecto
    assert body["ventanas"][0]["desde"] == api.habiles[-120].isoformat()
    assert [v["unidades"] for v in body["ventanas"]] == [150.0] * 7 + [165.0]
    _, params = api.estado["db"].consultas[-1]
    assert (params["codigo"], params["sucursal"]) == ("P1632", "PRINCIPAL")


def test_ventanas_pedidas(api):
    body = _get(api, "gerente", sucursal_id=2, ventanas=2).json()
    assert [(v["desde"], v["unidades"]) for v in body["ventanas"]] == [
        (api.habiles[-30].isoformat(), 0.0), (api.habiles[-15].isoformat(), 7.0)]


def test_producto_sin_ventas_en_la_sucursal(api):
    body = _get(api, "gerente", producto=92, sucursal_id=1, ventanas=3).json()
    assert [v["unidades"] for v in body["ventanas"]] == [0.0, 0.0, 0.0]


def test_un_producto_que_se_vende_por_kilo_va_en_kg(api):
    assert _get(api, "gerente", producto=321, sucursal_id=1).json()["unidad"] == "kg"


@pytest.mark.parametrize("rol, id_sucursal", [("gerente", None), ("admin_bodega", 5)])
def test_gerente_y_admin_bodega_sin_sucursal_id_422(api, rol, id_sucursal):
    r = _get(api, rol, id_sucursal)
    assert r.status_code == 422
    assert r.json()["detail"] == "sucursal_id es obligatorio. Válidos: 1 (PRINCIPAL), 2 (LA 21), 3 (GLORIETA)"


@pytest.mark.parametrize("rol, id_sucursal", [("gerente", None), ("admin_bodega", 5)])
def test_la_bodega_no_vende_422(api, rol, id_sucursal):
    r = _get(api, rol, id_sucursal, sucursal_id=5)
    assert r.status_code == 422 and "no vende" in r.json()["detail"]


def test_admin_bodega_filtra_cualquier_sucursal_fisica(api):
    assert _get(api, "admin_bodega", 5, sucursal_id=3).json()["sucursal"] == "GLORIETA"


@pytest.mark.parametrize("sucursal_id", [4, 99])
def test_sucursal_inexistente_o_sin_sucursal_422(api, sucursal_id):
    r = _get(api, "gerente", sucursal_id=sucursal_id)
    assert r.status_code == 422 and f"sucursal_id inválido: {sucursal_id}" in r.json()["detail"]


def test_admin_sucursal_ve_su_sucursal(api):
    assert _get(api, "admin_sucursal", 2).json()["sucursal"] == "LA 21"
    assert _get(api, "admin_sucursal", 2, sucursal_id=2).json()["id_sucursal"] == 2


@pytest.mark.parametrize("sucursal_id, extra", [(1, ""), (5, "; la Bodega Central, solo en el stock")])
def test_admin_sucursal_con_otra_sucursal_o_la_bodega_403(api, sucursal_id, extra):
    r = _get(api, "admin_sucursal", 2, sucursal_id=sucursal_id)
    assert r.status_code == 403 and r.json()["detail"] == f"Solo puede consultar su sucursal (LA 21){extra}"


def test_producto_inexistente_404_despues_de_validar_la_sucursal(api):
    r = _get(api, "gerente", producto=999, sucursal_id=1)
    assert r.status_code == 404 and r.json()["detail"] == "Producto 999 no encontrado"
    assert _get(api, "admin_sucursal", 2, producto=999, sucursal_id=1).status_code == 403


@pytest.mark.parametrize("ventanas", [0, 25])
def test_ventanas_fuera_de_rango_422(api, ventanas):
    assert _get(api, "gerente", sucursal_id=1, ventanas=ventanas).status_code == 422


def test_bodega_sin_ventas_cargadas_503(api):
    api.estado["db"] = BodegaFalsa([], {})
    r = _get(api, "gerente", sucursal_id=1)
    assert r.status_code == 503 and r.json()["detail"] == "La bodega no tiene ventas cargadas"


def test_openapi_documenta_el_endpoint(api):
    op = api.http.get("/api/openapi.json").json()["paths"]["/api/consulta/productos/{id_producto}/ventas"]["get"]
    assert op["tags"] == ["Consulta"] and op["security"] == [{"HTTPBearer": []}]
    assert {p["name"] for p in op["parameters"]} == {"id_producto", "sucursal_id", "ventanas"}
