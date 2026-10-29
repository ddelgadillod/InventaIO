"""INV-26 (fix, A1) — Ventas por producto contra la bodega real (foto al
2025-12-31) con los usuarios de prueba: las cifras de los requerimientos, la
suma a mano sobre dw.v_ventas_diarias_netas y los permisos. Se salta sin
Postgres o sin el seed de usuarios. Correr dentro del contenedor:
docker exec inventaio-api python -m pytest -m integracion"""
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from core.config import get_settings
from core.database import SessionLocal

pytestmark = pytest.mark.integracion

P1632, PAPA = 91, 321                  # PAPA PASTUSA *KL (P1814) se vende por kilo
PRINCIPAL, LA21, SIN_SUCURSAL, BODEGA = 1, 2, 4, 5


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
        pytest.skip(f"usuario de prueba {email} no disponible (falta el seed: docker exec inventaio-api python -m scripts.seed_usuarios)")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def tok(http):
    return {"gerente": _token(http, "gerente@inventaio.co"),
            "principal": _token(http, "admin.principal@inventaio.co"),
            "bodega": _token(http, "bodega@inventaio.co")}


def _ventas(http, auth, producto=P1632, codigo=200, **params):
    r = http.get(f"/api/consulta/productos/{producto}/ventas", params=params, headers=auth)
    assert r.status_code == codigo, r.text
    return r.json()


def _suma_a_mano(codigo_item: str, sucursal: str, desde: str, hasta: str) -> float:
    with SessionLocal() as db:
        return float(db.execute(text(
            "SELECT COALESCE(SUM(unidades), 0) FROM dw.v_ventas_diarias_netas "
            "WHERE codigo_item = :c AND sucursal = :s AND fecha BETWEEN :d AND :h"),
            {"c": codigo_item, "s": sucursal, "d": desde, "h": hasta}).scalar())


def test_p1632_en_principal_como_en_los_requerimientos(http, tok):
    body = _ventas(http, tok["gerente"], sucursal_id=PRINCIPAL, ventanas=3)
    assert (body["codigo_item"], body["nombre_producto"], body["unidad"]) == ("P1632", "HUEVOS *UND", "unidad")
    assert body["fecha_fin"] == "2025-12-31"
    assert [(v["desde"], v["hasta"], v["unidades"]) for v in body["ventanas"]] == [
        ("2025-11-17", "2025-12-01", 2426.0), ("2025-12-02", "2025-12-16", 3522.0), ("2025-12-17", "2025-12-31", 4608.0)]


def test_cada_ventana_coincide_con_la_suma_a_mano(http, tok):
    body = _ventas(http, tok["gerente"], sucursal_id=PRINCIPAL)
    assert len(body["ventanas"]) == 8 and body["ventanas"][0]["desde"] == "2025-09-02"
    for anterior, ventana in zip(body["ventanas"], body["ventanas"][1:]):
        assert anterior["hasta"] < ventana["desde"]                 # consecutivas, sin solaparse
    for v in body["ventanas"]:
        assert v["unidades"] == pytest.approx(_suma_a_mano("P1632", "PRINCIPAL", v["desde"], v["hasta"]))


def test_producto_sin_ventas_en_la_sucursal(http, tok):
    with SessionLocal() as db:
        sin_ventas = db.execute(text(
            "SELECT p.id_producto FROM dw.dim_producto p WHERE NOT EXISTS ("
            "SELECT 1 FROM dw.v_ventas_diarias_netas v WHERE v.codigo_item = p.codigo_item "
            "AND v.sucursal = 'PRINCIPAL') ORDER BY p.id_producto LIMIT 1")).scalar()
    body = _ventas(http, tok["gerente"], producto=sin_ventas, sucursal_id=PRINCIPAL, ventanas=4)
    assert [v["unidades"] for v in body["ventanas"]] == [0.0] * 4


def test_unidad_de_venta_en_el_historico_y_en_los_productos(http, tok):
    """unidad sale de se_vende_por_kilo; unidad_medida es la de la presentación
    (la papa P1814 tiene unidad_medida "unidad" y se vende por kilo)."""
    assert _ventas(http, tok["gerente"], producto=PAPA, sucursal_id=PRINCIPAL, ventanas=1)["unidad"] == "kg"
    papa = http.get(f"/api/consulta/productos/{PAPA}", headers=tok["gerente"]).json()
    assert (papa["codigo_item"], papa["unidad_medida"], papa["unidad"]) == ("P1814", "unidad", "kg")
    arroz = http.get("/api/consulta/productos/171", headers=tok["gerente"]).json()
    assert (arroz["unidad_medida"], arroz["unidad"]) == ("g", "unidad")
    lista = http.get("/api/consulta/productos", params={"busqueda": "PAPA PASTUSA"}, headers=tok["gerente"]).json()
    assert {p["unidad"] for p in lista["items"] if p["codigo_item"] == "P1814"} == {"kg"}
    proveedor = http.get("/api/consulta/proveedores/1", headers=tok["gerente"]).json()
    assert {p["unidad"] for p in proveedor["productos"]} <= {"unidad", "kg"}


def test_permisos_de_inv25(http, tok):
    assert _ventas(http, tok["principal"])["sucursal"] == "PRINCIPAL"
    assert _ventas(http, tok["bodega"], sucursal_id=LA21)["sucursal"] == "LA 21"
    assert "obligatorio" in _ventas(http, tok["gerente"], codigo=422)["detail"]
    assert "no vende" in _ventas(http, tok["bodega"], codigo=422, sucursal_id=BODEGA)["detail"]
    _ventas(http, tok["gerente"], codigo=422, sucursal_id=SIN_SUCURSAL)
    _ventas(http, tok["principal"], codigo=403, sucursal_id=LA21)
    _ventas(http, tok["principal"], codigo=403, sucursal_id=BODEGA)
    _ventas(http, tok["gerente"], producto=999999, codigo=404, sucursal_id=PRINCIPAL)
    _ventas(http, tok["gerente"], codigo=422, sucursal_id=PRINCIPAL, ventanas=25)


def test_fecha_fin_alineada_con_el_pronostico(http, tok):
    try:
        disponible = httpx.get(f"{get_settings().ML_SERVICE_URL}/api/health", timeout=5).status_code == 200
    except httpx.HTTPError:
        disponible = False
    if not disponible:
        pytest.skip("ml_service no disponible")
    pronostico = http.post("/api/ml/predict", json={"id_producto": P1632, "id_sucursal": PRINCIPAL, "horizonte": 15},
                           headers=tok["principal"])
    assert pronostico.status_code == 200, pronostico.text
    assert _ventas(http, tok["principal"])["fecha_fin"] == pronostico.json()["fecha_features"]
