"""INV-28 — Alertas con IA contra ml_service, Postgres y los usuarios de prueba
reales (foto al 2025-12-31). Confirma las cifras y los casos P-01 a P-10 de
docs/INV-28-requerimientos.md. Se salta si falta alguno de los servicios.
Correr dentro del contenedor: docker compose exec api pytest -m integracion"""
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from core.config import get_settings

pytestmark = pytest.mark.integracion

PRINCIPAL, LA21, GLORIETA, BODEGA = 1, 2, 3, 5


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
        pytest.skip(f"usuario de prueba {email} no disponible (falta el seed: docker exec inventaio-api python -m scripts.seed_usuarios)")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def gerente(http):
    return _token(http, "gerente@inventaio.co")


@pytest.fixture(scope="module")
def todas(http, gerente):
    r = http.get("/api/alertas/ml", headers=gerente, timeout=180)
    assert r.status_code == 200, r.text
    return r.json()


def _par(body, codigo, sucursal):
    return [a for a in body["items"] if a["codigo_item"] == codigo and a["sucursal"] == sucursal]


def test_totales_de_la_foto(todas):
    """P-09: 866 de riesgo (483 críticas, 383 altas; 395 ambos) y 721 de sobrestock."""
    res = todas["resumen"]
    assert (res["riesgo_desabastecimiento_ml"], res["sobrestock_previsto_ml"]) == (866, 721)
    assert (res["critica"], res["alta"], res["media"]) == (483, 383, 721)
    assert (res["ambos"], res["ml"], res["total"], todas["total"]) == (395, 1192, 1587, 1587)
    assert todas["fecha_inventario"] == "2025-12-31"
    por_sucursal = {}
    for a in todas["items"]:
        por_sucursal.setdefault((a["sucursal"], a["tipo"]), 0)
        por_sucursal[(a["sucursal"], a["tipo"])] += 1
    assert por_sucursal == {
        ("PRINCIPAL", "riesgo_desabastecimiento_ml"): 437, ("GLORIETA", "riesgo_desabastecimiento_ml"): 246,
        ("LA 21", "riesgo_desabastecimiento_ml"): 183, ("PRINCIPAL", "sobrestock_previsto_ml"): 368,
        ("GLORIETA", "sobrestock_previsto_ml"): 216, ("LA 21", "sobrestock_previsto_ml"): 137,
    }


def test_casos_con_productos_reales(todas):
    huevos = _par(todas, "P1632", "PRINCIPAL")                          # P-01: HUEVOS *UND
    assert [(a["tipo"], a["urgencia"], a["origen"]) for a in huevos] == [
        ("riesgo_desabastecimiento_ml", "critica", "ambos")]
    assert huevos[0]["stock"] == 489 and huevos[0]["detalle"].startswith("Stock 489 unidades")
    clorox = _par(todas, "00037", "PRINCIPAL")                          # P-02: BLQ CLOROX RC1800+CLOROX RC 930
    assert [(a["urgencia"], a["origen"], a["stock"]) for a in clorox] == [("critica", "ml", 0)]
    assert _par(todas, "00002", "LA 21") == []                          # P-03: CHOCOLAT JET BURBUJA, q50 0,66
    assert _par(todas, "00008", "LA 21") == []                          # P-04: AGUA CRISTAL LITRO SPORT, stock -1
    tizon = _par(todas, "01108", "GLORIETA")                            # P-05: CONDIMENTO EL TIZON * 50 GR
    assert [(a["tipo"], a["urgencia"], a["origen"]) for a in tizon] == [("sobrestock_previsto_ml", "media", "ml")]
    # V11: HUEVOS en LA 21 alcanza 5,026 días hábiles; sin redondear es alta (Predicciones dice Urgente)
    huevos_la21 = _par(todas, "P1632", "LA 21")
    assert [(a["urgencia"], a["valor"], a["umbral"]) for a in huevos_la21] == [("alta", 5.0, 10.0)]


def test_bodega_sin_alertas_y_traslados_nombrados(todas):
    assert all(a["tipo_ubicacion"] == "sucursal" for a in todas["items"])           # P-08
    con_traslado = [a for a in todas["items"] if "traslado sugerido" in a["detalle"]]  # P-07 (V10)
    assert len(con_traslado) == 100 and all(a["tipo"] == "riesgo_desabastecimiento_ml" for a in con_traslado)


def test_admin_sucursal_de_la_21(http):
    """P-10: solo LA 21 (183 de riesgo y 137 de sobrestock); otra ubicación da 403."""
    auth = _token(http, "admin.norte@inventaio.co")
    body = http.get("/api/alertas/ml", headers=auth, timeout=180).json()
    assert {a["sucursal"] for a in body["items"]} == {"LA 21"}
    assert (body["resumen"]["riesgo_desabastecimiento_ml"], body["resumen"]["sobrestock_previsto_ml"]) == (183, 137)
    for otra in (PRINCIPAL, BODEGA):
        assert http.get("/api/alertas/ml", headers=auth, params={"sucursal_id": otra}).status_code == 403


def test_las_alertas_por_reglas_no_cambian(http, gerente, todas):
    """P-14: mismo contrato y menos de 1 s."""
    inicio = time.monotonic()
    r = http.get("/api/alertas", headers=gerente)
    assert time.monotonic() - inicio < 1.0
    body = r.json()
    assert body["total"] == 4452 and "origen" not in body["items"][0]
    assert http.get("/api/alertas/resumen", headers=gerente).json()["global_"]["total"] == 4452


def test_varios_valores_por_filtro(http, gerente):
    """V13: los filtros de /api/alertas y /api/alertas/ml aceptan varios valores repetidos."""
    def total(ruta, params):
        r = http.get(ruta, headers=gerente, params=params, timeout=180)
        assert r.status_code == 200, r.text
        return r.json()["total"]
    assert total("/api/alertas", {"tipo": ["stock_critico", "stock_bajo"]}) == 1114 + 386
    assert total("/api/alertas", {"urgencia": ["critica", "alta"]}) == 1334 + 386
    assert total("/api/alertas", {"tipo": ["stock_bajo"]}) == 386                     # un solo valor, como antes
    assert http.get("/api/alertas", headers=gerente, params={"tipo": ["stock_bajo", "otro"]}).status_code == 400
    assert total("/api/alertas/ml", {"urgencia": ["critica", "alta"]}) == 866
    assert total("/api/alertas/ml", {"tipo": ["riesgo_desabastecimiento_ml", "sobrestock_previsto_ml"]}) == 1587


def test_accion_llega_tarde_fecha_y_categoria(http, gerente, todas):
    """V14 (conciliación con la ficha de Jira): acción sugerida, traslado tarde, fecha del pronóstico y categoría."""
    assert todas["fecha_pronostico"] == "2025-12-31"
    riesgo = [a for a in todas["items"] if a["tipo"] == "riesgo_desabastecimiento_ml"]
    acciones = {}
    for a in riesgo:
        acciones[a["accion"]] = acciones.get(a["accion"], 0) + 1
    assert acciones == {"compra": 766, "traslado": 83, "traslado_y_compra": 17}
    assert sum(a["llega_tarde"] is True for a in riesgo) == 16
    assert all(a["accion"] is None for a in todas["items"] if a["tipo"] == "sobrestock_previsto_ml")
    r = http.get("/api/alertas/ml", headers=gerente, params={"categoria": ["huevos", "Arroz"]})
    assert r.status_code == 200 and r.json()["total"] == 40
    assert {a["categoria"] for a in r.json()["items"]} == {"Arroz", "Huevos"}
