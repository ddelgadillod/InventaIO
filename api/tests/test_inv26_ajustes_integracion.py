"""INV-26 fix (A8) — Ajustes contra la bodega real (foto al 2025-12-31): el
estado inconsistencia del semáforo (K3) y el KPI en riesgo que cuadra con él
(K9), la unidad en la lista de inventario (J5) y la paginación de alertas (K2). Se salta sin Postgres o sin el seed de
usuarios. Correr dentro del contenedor:
docker exec inventaio-api python -m pytest -m integracion"""
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integracion

CEPILLO, ARROZ = 941, 171            # CEPILLO LAVA-AUTOS (stock -44 en GLORIETA), P3937
PRINCIPAL, GLORIETA, BODEGA = 1, 3, 5


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
            "principal": _token(http, "admin.principal@inventaio.co")}


def _get(http, auth, ruta, codigo=200, **params):
    r = http.get(f"/api/{ruta}", params=params, headers=auth)
    assert r.status_code == codigo, r.text
    return r.json()


# ── Semáforo con inconsistencia (K3) ────────────────

def test_resumen_con_inconsistencia_cuadra_con_alertas(http, tok):
    g = _get(http, tok["gerente"], "consulta/inventario/resumen")["global_"]
    assert g == {"ok": 9381, "bajo": 386, "critico": 1114, "inconsistencia": 220, "total": 11101}
    alertas = _get(http, tok["gerente"], "alertas/resumen")["por_tipo"]
    assert (g["critico"], g["inconsistencia"]) == (alertas["stock_critico"], alertas["inconsistencia_inventario"])


@pytest.mark.parametrize("sucursal_id, esperado", [
    (PRINCIPAL, {"ok": 3611, "bajo": 138, "critico": 202, "inconsistencia": 95, "total": 4046}),
    (BODEGA, {"ok": 1287, "bajo": 79, "critico": 592, "inconsistencia": 15, "total": 1973}),
])
def test_resumen_por_ubicacion(http, tok, sucursal_id, esperado):
    assert _get(http, tok["gerente"], "consulta/inventario/resumen", sucursal_id=sucursal_id)["global_"] == esperado


@pytest.mark.parametrize("sucursal_id, en_riesgo", [(None, 1500), (PRINCIPAL, 340), (GLORIETA, 282), (BODEGA, 671)])
def test_kpi_en_riesgo_es_bajo_mas_critico(http, tok, sucursal_id, en_riesgo):
    """K9: el KPI cuenta los tramos bajo y crítico; antes (cobertura < 7) daba 1.702
    porque sumaba 202 filas con stock negativo."""
    params = {"sucursal_id": sucursal_id} if sucursal_id else {}
    kpis = _get(http, tok["gerente"], "reportes/kpis", **params)
    resumen = _get(http, tok["gerente"], "consulta/inventario/resumen", **params)["global_"]
    assert kpis["productos_en_riesgo"] == resumen["bajo"] + resumen["critico"] == en_riesgo


@pytest.mark.parametrize("estado", ["ok", "bajo", "critico", "inconsistencia"])
def test_filtro_por_estado_cuadra_con_el_resumen(http, tok, estado):
    total = _get(http, tok["gerente"], "consulta/inventario/resumen")["global_"][estado]
    body = _get(http, tok["gerente"], "consulta/inventario", semaforo=estado, page_size=100)
    assert body["total"] == total and {f["semaforo"] for f in body["items"]} == {estado}
    negativos = [f for f in body["items"] if f["stock_disponible"] < 0]
    assert bool(negativos) == (estado == "inconsistencia")


def test_detalle_con_stock_negativo(http, tok):
    det = _get(http, tok["gerente"], "consulta/inventario/detalle", id_producto=CEPILLO, id_sucursal=GLORIETA)
    assert (det["stock_actual"], det["semaforo"], det["historial"][0]["semaforo"]) == (-44.0, "inconsistencia",
                                                                                        "inconsistencia")


# ── Unidad en la lista (J5) ─────────────────────────

def test_lista_de_inventario_trae_la_unidad(http, tok):
    papa = _get(http, tok["gerente"], "consulta/inventario", busqueda="PAPA PASTUSA")["items"]
    assert {(f["sucursal"], f["unidad"]) for f in papa} == {("PRINCIPAL", "kg"), ("LA 21", "kg"), ("GLORIETA", "kg")}
    arroz = _get(http, tok["gerente"], "consulta/inventario", busqueda="ARROZ ZULIA *500")["items"]
    assert {f["unidad"] for f in arroz} == {"unidad"}


# ── Paginación de alertas (K2) ──────────────────────

def test_sin_pagina_responde_como_en_inv25(http, tok):
    body = _get(http, tok["gerente"], "alertas")
    assert set(body) == {"items", "total", "fecha_inventario"} and len(body["items"]) == body["total"] == 4452


def test_paginas_de_50(http, tok):
    todas = _get(http, tok["gerente"], "alertas")["items"]
    p1 = _get(http, tok["gerente"], "alertas", page=1)
    assert (len(p1["items"]), p1["total"], p1["page"], p1["page_size"], p1["pages"]) == (50, 4452, 1, 50, 90)
    assert p1["items"] == todas[:50]
    ultima = _get(http, tok["gerente"], "alertas", page=90)
    assert ultima["items"] == todas[-2:]
    grande = _get(http, tok["gerente"], "alertas", page=2, page_size=100)
    assert grande["items"] == todas[100:200] and grande["pages"] == 45


def test_paginas_con_filtros_y_permisos(http, tok):
    inc = _get(http, tok["gerente"], "alertas", tipo="inconsistencia_inventario", page=5)
    assert (len(inc["items"]), inc["total"], inc["pages"]) == (20, 220, 5)
    propia = _get(http, tok["principal"], "alertas", page=1)
    assert (propia["total"], propia["pages"]) == (1308, 27)
    assert {a["sucursal"] for a in propia["items"]} == {"PRINCIPAL"}


@pytest.mark.parametrize("params", [{"page": 0}, {"page_size": 0}, {"page_size": 501}])
def test_pagina_invalida_422(http, tok, params):
    _get(http, tok["gerente"], "alertas", 422, **params)


# ── Reportes para la vista nueva (A9) ───────────────

def test_ventas_trae_el_rango_de_datos(http, tok):
    body = _get(http, tok["gerente"], "reportes/ventas")
    assert (body["datos_desde"], body["datos_hasta"]) == ("2022-01-02", "2025-12-31")
    assert (body["fecha_inicio"], body["fecha_fin"]) == ("2025-12-01", "2025-12-31")


def test_comparativa_con_fechas_del_periodo_anterior_y_categoria(http, tok):
    total = _get(http, tok["gerente"], "reportes/ventas/comparativa")["resumen"]
    assert total["periodo_anterior"] == "2025-10-31 / 2025-11-30"
    assert (total["valor_actual"], total["variacion_pct"]) == (737879055.35, 50.1)       # como en INV-25
    licores = _get(http, tok["gerente"], "reportes/ventas/comparativa", categoria="Licores")["resumen"]
    distribucion = _get(http, tok["gerente"], "reportes/distribucion-categorias")["items"]
    assert licores["valor_actual"] == pytest.approx(
        next(c["valor_total"] for c in distribucion if c["categoria"] == "Licores"))


def test_tendencia_con_categoria_y_agrupacion(http, tok):
    mensual = _get(http, tok["gerente"], "reportes/tendencias", por_sucursal="true", agrupacion="mes",
                   categoria="Licores", fecha_inicio="2025-01-01", fecha_fin="2025-12-31")
    assert sorted(s["sucursal"] for s in mensual["series"]) == ["GLORIETA", "LA 21", "PRINCIPAL"]
    for serie in mensual["series"]:
        assert [p["fecha"] for p in serie["puntos"]][:2] == ["2025-01", "2025-02"] and len(serie["puntos"]) == 12
        assert all(p["promedio_movil_7d"] is None for p in serie["puntos"])
    diciembre = sum(s["puntos"][-1]["valor_total"] for s in mensual["series"])
    licores = _get(http, tok["gerente"], "reportes/ventas/comparativa", categoria="Licores")["resumen"]["valor_actual"]
    assert diciembre == pytest.approx(licores)
    semanal = _get(http, tok["gerente"], "reportes/tendencias", agrupacion="semana")
    assert semanal["series"][0]["puntos"][0]["fecha"].startswith("2025-W")
    diaria = _get(http, tok["gerente"], "reportes/tendencias")["series"][0]["puntos"]
    assert diaria[0]["promedio_movil_7d"] is not None                                    # sin cambios por defecto
