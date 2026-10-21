"""INV-33 (B4) — /api/reportes/ventas con el filtro de producto y las agrupaciones por trimestre y año, contra
la bodega real (foto al 2025-12-31): las cifras se comparan con una suma a mano sobre dw.fact_ventas, con la
misma regla del endpoint (sin devoluciones). Se salta sin Postgres o sin el seed. Correr dentro del contenedor:
docker exec <contenedor del api> python -m pytest -m integracion tests/test_reportes_ventas_producto_integracion.py"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from core.database import SessionLocal

pytestmark = pytest.mark.integracion
PRINCIPAL, GLORIETA = 1, 3


@pytest.fixture(scope="module")
def http():
    from main import app

    with TestClient(app) as client:
        yield client


def _token(http, email: str) -> dict:
    try:
        r = http.post("/api/auth/login", json={"email": email, "password": "admin123"})
    except Exception as exc:                                  # Postgres caído
        pytest.skip(f"sin bodega: {exc}")
    if r.status_code != 200:
        pytest.skip(f"usuario de prueba {email} no disponible (falta el seed)")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def tok(http):
    return {"gerente": _token(http, "gerente@inventaio.co"), "principal": _token(http, "admin.principal@inventaio.co")}


def _ventas(http, auth, codigo=200, **params):
    r = http.get("/api/reportes/ventas", params=params, headers=auth)
    assert r.status_code == codigo, r.text
    return r.json()


def _suma(codigo_item: str, desde: str, hasta: str, sucursal: int | None = None) -> float:
    with SessionLocal() as db:
        return float(db.execute(text(
            "SELECT COALESCE(SUM(v.cantidad), 0) FROM dw.fact_ventas v "
            "JOIN dw.dim_producto p ON p.id_producto = v.id_producto JOIN dw.dim_tiempo t ON t.id_tiempo = v.id_tiempo "
            "WHERE p.codigo_item = :c AND NOT v.es_devolucion AND t.fecha BETWEEN :d AND :h"
            + (" AND v.id_sucursal = :s" if sucursal else "")),
            {"c": codigo_item, "d": desde, "h": hasta, "s": sucursal}).scalar())


def test_trimestres_de_un_producto(http, tok):
    body = _ventas(http, tok["gerente"], producto="P626", agrupacion="trimestre", fecha_inicio="2022-01-01",
                   fecha_fin="2025-12-31")
    assert body["producto"] == {"codigo": "P626", "nombre": "ARROZ DIANA *500 GR", "unidad": "unidad"}
    assert body["agrupacion"] == "trimestre" and len(body["items"]) == 16
    assert body["items"][-1]["periodo"] == "2025-T4"
    assert body["total_cantidad"] == pytest.approx(_suma("P626", "2022-01-01", "2025-12-31"))
    assert body["items"][-1]["cantidad"] == pytest.approx(_suma("P626", "2025-10-01", "2025-12-31"))
    assert all(i["margen"] == pytest.approx(i["valor_total"] - i["costo_total"]) for i in body["items"])


def test_anio_y_sucursal(http, tok):
    body = _ventas(http, tok["gerente"], producto="P626", agrupacion="anio", fecha_inicio="2024-01-01",
                   fecha_fin="2025-12-31", sucursal_id=PRINCIPAL)
    assert [i["periodo"] for i in body["items"]] == ["2024", "2025"]
    assert body["items"][1]["cantidad"] == pytest.approx(_suma("P626", "2025-01-01", "2025-12-31", PRINCIPAL))


def test_producto_inexistente_404(http, tok):
    r = http.get("/api/reportes/ventas", params={"producto": "NO-EXISTE"}, headers=tok["gerente"])
    assert r.status_code == 404 and "NO-EXISTE" in r.json()["detail"]


def test_permisos_del_rol_con_producto(http, tok):
    """El filtro de producto no cambia los permisos de INV-25: el admin de PRINCIPAL ve solo su sucursal."""
    propia = _ventas(http, tok["principal"], producto="P626", agrupacion="anio", fecha_inicio="2025-01-01",
                     fecha_fin="2025-12-31")
    assert propia["total_cantidad"] == pytest.approx(_suma("P626", "2025-01-01", "2025-12-31", PRINCIPAL))
    _ventas(http, tok["principal"], codigo=403, producto="P626", sucursal_id=GLORIETA)


def test_sin_producto_no_cambia(http, tok):
    """Sin los parámetros nuevos, la respuesta es la de antes (y producto viene vacío)."""
    body = _ventas(http, tok["gerente"], fecha_inicio="2025-12-01", fecha_fin="2025-12-31", agrupacion="mes")
    assert [i["periodo"] for i in body["items"]] == ["2025-12"] and body["producto"] is None
