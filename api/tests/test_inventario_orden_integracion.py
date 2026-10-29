"""INV-64 e INV-65 contra la bodega real (foto al 2025-12-31): el semáforo
inválido da 422, los productos con venta reciente van primero, la paginación
es estable y la Bodega Central lleva las ventas de la red. Cifras del análisis
del 19-oct (INV-65). Se salta sin Postgres o sin el seed de usuarios. Correr
dentro del contenedor: docker exec inventaio-api python -m pytest -m integracion"""
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integracion

GLORIETA, BODEGA = 3, 5


@pytest.fixture(scope="module")
def http():
    from main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="module")
def tok(http):
    try:
        r = http.post("/api/auth/login", json={"email": "gerente@inventaio.co", "password": "admin123"})
    except Exception as exc:                                  # Postgres caído
        pytest.skip(f"sin bodega: {exc}")
    if r.status_code != 200:
        pytest.skip("usuario de prueba no disponible (falta el seed: docker exec inventaio-api python -m scripts.seed_usuarios)")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _lista(http, tok, **params) -> dict:
    r = http.get("/api/consulta/inventario", params=params, headers=tok)
    assert r.status_code == 200, r.text
    return r.json()


def test_semaforo_invalido_da_422(http, tok):                                  # INV-64
    assert http.get("/api/consulta/inventario", params={"semaforo": "xx"}, headers=tok).status_code == 422


def test_criticos_de_glorieta_primero_los_que_se_venden(http, tok):           # INV-65
    filas = []
    for pagina in (1, 2):
        filas += _lista(http, tok, sucursal_id=GLORIETA, semaforo="critico", page=pagina, page_size=100)["items"]
    assert len(filas) == 173 and len({(f["id_producto"], f["id_sucursal"]) for f in filas}) == 173   # sin repetidos
    con_venta = [f for f in filas if f["ventas_30d"] > 0]
    assert len(con_venta) == 68 and filas[:68] == con_venta                    # los 105 sin ventas, al final
    for a, b in zip(con_venta, con_venta[1:]):
        assert (a["dias_cobertura"], -a["ventas_30d"]) <= (b["dias_cobertura"], -b["ventas_30d"])
    assert [(f["nombre_producto"], f["ventas_30d"]) for f in filas[:3]] == [
        ("BIANCHI MINI BOMBON * 30", 13.0), ("MASMELO MILLOWS IND 290GR * 50UN", 12.0), ("JUGO HIT PET *1.5ML", 11.0)]


def test_la_pagina_es_estable(http, tok):
    a = _lista(http, tok, semaforo="critico", page=3, page_size=50)["items"]
    b = _lista(http, tok, semaforo="critico", page=3, page_size=50)["items"]
    assert [(f["id_producto"], f["id_sucursal"]) for f in a] == [(f["id_producto"], f["id_sucursal"]) for f in b]


def test_la_bodega_lleva_las_ventas_de_la_red(http, tok):
    filas = _lista(http, tok, busqueda="SAL REFISAL *1000GR", page_size=10)["items"]
    por_sucursal = {f["sucursal"]: f["ventas_30d"] for f in filas}
    assert por_sucursal["BODEGA_CENTRAL"] == 1176.0
    assert por_sucursal["BODEGA_CENTRAL"] == pytest.approx(sum(v for s, v in por_sucursal.items() if s != "BODEGA_CENTRAL"))
