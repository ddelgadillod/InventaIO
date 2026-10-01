"""INV-23 — Integración con ml_service, Postgres y los usuarios de prueba
reales (foto al 2025-12-31). Confirma las cifras de "Resultados esperados" de
docs/INV-23-requerimientos.md. Se salta si falta alguno de los servicios.
Correr dentro del contenedor: docker compose exec api pytest -m integracion"""
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from core.config import get_settings

pytestmark = pytest.mark.integracion


@pytest.fixture(scope="module")
def http():
    try:
        salud = httpx.get(f"{get_settings().ML_SERVICE_URL}/api/health", timeout=5).json()
    except httpx.HTTPError:
        pytest.skip("ml_service no disponible")
    if salud.get("status") != "ok" or "politicas" not in salud:
        pytest.skip("ml_service degradado o anterior a INV-23")
    from main import app

    with TestClient(app) as client:
        yield client


def _token(http, email: str) -> dict:
    try:
        r = http.post("/api/auth/login", json={"email": email, "password": "admin123"})
    except Exception as exc:                                  # Postgres caído
        pytest.skip(f"sin bodega: {exc}")
    if r.status_code != 200:
        pytest.skip(f"usuario de prueba {email} no disponible (falta el seed de usuarios)")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def gerente(http):
    return _token(http, "gerente@inventaio.co")


def _get(http, auth, ruta, **params):
    r = http.get(f"/api/ml/recomendaciones/{ruta}", params=params, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def test_compras_sin_filtros_cuadra_con_ml_service(http, gerente):
    body = _get(http, gerente, "compras", incluir_detalle="false")
    res = body["resumen"]
    assert (res["lineas"], res["lineas_sucursal"], res["lineas_bodega"]) == (1340, 449, 891)
    assert res["cantidad"] == {"unidad": 41952, "kg": 3169}
    assert (res["cubiertos_por_bodega"], res["alertas"], res["productos"]) == (277, 220, 1411)
    assert body["fecha_inventario"] == "2025-12-31"


def test_compras_desde_principal(http, gerente):
    body = _get(http, gerente, "compras", sucursal="PRINCIPAL", incluir_detalle="false")
    res = body["resumen"]
    assert (res["lineas"], res["lineas_sucursal"], res["lineas_bodega"]) == (814, 164, 650)
    assert res["necesidad_via_bodega"]["unidad"] == pytest.approx(19637.39)
    assert (res["cubiertos_por_bodega"], res["alertas"]) == (172, 95)
    lineas = {f["producto_id"]: f for f in body["compras"]}
    assert (lineas["P1632"]["nombre_producto"], lineas["P1632"]["cantidad"]) == ("HUEVOS *UND", 4735)
    agua = lineas["00008"]                                    # urgente por LA 21, normal desde PRINCIPAL
    assert (agua["urgencia"], agua["necesidad_sucursal"], agua["cantidad"]) == ("normal", 36.95, 47)


def test_la_cache_caliente_responde_en_menos_de_un_segundo(http, gerente):
    _get(http, gerente, "compras")
    inicio = time.perf_counter()
    body = _get(http, gerente, "compras", sucursal="GLORIETA", categoria="arroz", urgencia="urgente")
    assert time.perf_counter() - inicio < 1
    assert [(f["producto_id"], f["cantidad"]) for f in body["compras"]] == [("P1938", 4), ("P4570", 20)]


def test_transferencias(http, gerente):
    res = _get(http, gerente, "transferencias")["resumen"]
    assert (res["traslados"], res["filas_balance"], res["productos"]) == (119, 11710, 4419)
    assert res["cantidad_trasladada"] == {"unidad": 4623, "kg": 0}
    assert sum(res["deficit_total"].values()) == pytest.approx(20677.18)
    assert (res["alertas"], res["alertas_sin_pronostico"]) == (220, 2762)
    res = _get(http, gerente, "transferencias", sucursal="LA 21")["resumen"]
    assert (res["traslados"], res["alertas"], res["alertas_sin_pronostico"]) == (10, 40, 697)
    arroz = _get(http, gerente, "transferencias", categoria="arroz")["traslados"]
    assert sorted((t["destino"], t["cantidad"]) for t in arroz if t["producto_id"] == "P3937") == [
        ("GLORIETA", 572), ("PRINCIPAL", 695)]


def test_permisos_con_usuarios_reales(http):
    norte = _token(http, "admin.norte@inventaio.co")
    body = _get(http, norte, "compras", incluir_detalle="false")
    assert body["filtros_aplicados"]["sucursal"] == "LA 21" and body["filtros_aplicados"]["sucursal_por_rol"]
    assert body["resumen"]["lineas"] == 337
    r = http.get("/api/ml/recomendaciones/compras", params={"sucursal": "PRINCIPAL"}, headers=norte)
    assert r.status_code == 403
