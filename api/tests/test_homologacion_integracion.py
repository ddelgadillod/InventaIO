"""INV-25 — Endpoints del Core API homologados contra la bodega real (foto al
2025-12-31) con los usuarios de prueba. Confirma "Resultados esperados" de
docs/INV-25-requerimientos.md. Las rutas de Release 1 son SQL directo contra
la base, así que esta es su prueba principal. Se salta sin Postgres o sin el
seed de usuarios. Correr dentro del contenedor:
docker exec inventaio-api python -m pytest -m integracion"""
import httpx
import pytest
from fastapi.testclient import TestClient

from core.config import get_settings

pytestmark = pytest.mark.integracion

P1632, P3937, A00008 = 91, 171, 3814          # id_producto
PRINCIPAL, LA21, GLORIETA, SIN_SUCURSAL, BODEGA = 1, 2, 3, 4, 5


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


def _get(http, auth, ruta, codigo=200, **params):
    r = http.get(f"/api/{ruta}", params=params, headers=auth)
    assert r.status_code == codigo, r.text
    return r.json()


# ── Consulta (P1, P6) ───────────────────────────────

def test_productos_con_codigos_de_texto_y_ceros(http, tok):
    body = _get(http, tok["principal"], "consulta/productos", page_size=100)
    assert body["total"] == 4449 and all(isinstance(p["codigo_item"], str) for p in body["items"])
    assert _get(http, tok["gerente"], f"consulta/productos/{A00008}")["codigo_item"] == "00008"


def test_detalle_de_producto_y_de_proveedor_desde_producto_proveedor(http, tok):
    huevos = _get(http, tok["gerente"], f"consulta/productos/{P1632}")
    assert (huevos["codigo_item"], huevos["proveedores"]) == ("P1632", ["Lácteos del Cauca Ltda."])
    proveedor = _get(http, tok["gerente"], "consulta/proveedores/1")
    assert (proveedor["razon_social"], proveedor["total_productos"]) == ("Distribuidora Valle S.A.S.", 1978)


def test_sucursales_sin_sin_sucursal_y_con_nulos(http, tok):
    body = _get(http, tok["bodega"], "consulta/sucursales")
    assert [(s["nombre"], s["tipo"]) for s in body["items"]] == [
        ("PRINCIPAL", "principal"), ("LA 21", "estandar"), ("GLORIETA", "estandar"), ("BODEGA_CENTRAL", "bodega_central")]
    assert body["items"][0]["ciudad"] is None and body["items"][3]["factor_volumen"] is None


# ── Inventario (P2, P4, P5) ─────────────────────────

def test_inventario_trae_tipo_ubicacion_y_stock_bodega(http, tok):
    body = _get(http, tok["gerente"], "consulta/inventario", page_size=100)
    assert body["total"] == 11101
    for fila in body["items"]:
        es_bodega = fila["sucursal"] == "BODEGA_CENTRAL"
        assert fila["tipo_ubicacion"] == ("bodega_central" if es_bodega else "sucursal")
        assert (fila["stock_bodega"] is None) == es_bodega


def test_admin_sucursal_ve_su_inventario_y_el_stock_de_la_bodega(http, tok):
    propio = _get(http, tok["principal"], "consulta/inventario")
    assert propio["total"] == 4046 and {f["sucursal"] for f in propio["items"]} == {"PRINCIPAL"}
    bodega = _get(http, tok["principal"], "consulta/inventario", sucursal_id=BODEGA)
    assert bodega["total"] == 1973 and {f["tipo_ubicacion"] for f in bodega["items"]} == {"bodega_central"}
    _get(http, tok["principal"], "consulta/inventario", 403, sucursal_id=LA21)
    arroz = _get(http, tok["principal"], "consulta/inventario/detalle", id_producto=P3937, id_sucursal=PRINCIPAL)
    assert (arroz["stock_actual"], arroz["dias_cobertura"], arroz["stock_bodega"]) == (556.0, 5.3, 4024.0)
    en_bodega = _get(http, tok["principal"], "consulta/inventario/detalle", id_producto=P3937, id_sucursal=BODEGA)
    assert (en_bodega["tipo_ubicacion"], en_bodega["stock_actual"], en_bodega["stock_bodega"]) == (
        "bodega_central", 4024.0, None)
    huevos = _get(http, tok["principal"], "consulta/inventario/detalle", id_producto=P1632, id_sucursal=PRINCIPAL)
    assert huevos["stock_bodega"] == 0.0                       # la Bodega no tiene fila (R3)


def test_admin_bodega_ve_el_detalle_de_cualquier_sucursal(http, tok):
    body = _get(http, tok["bodega"], "consulta/inventario/detalle", id_producto=P1632, id_sucursal=PRINCIPAL)
    assert (body["sucursal"], body["stock_actual"], len(body["historial"])) == ("PRINCIPAL", 489.0, 1)


@pytest.mark.parametrize("sucursal_id", [SIN_SUCURSAL, 99])
def test_sucursal_invalida_422(http, tok, sucursal_id):
    _get(http, tok["gerente"], "consulta/inventario", 422, sucursal_id=sucursal_id)
    _get(http, tok["gerente"], "alertas", 422, sucursal_id=sucursal_id)
    _get(http, tok["gerente"], "reportes/kpis", 422, sucursal_id=sucursal_id)


def test_resumen_y_valorizado_filtran_por_sucursal(http, tok):
    resumen = _get(http, tok["gerente"], "consulta/inventario/resumen", sucursal_id=LA21)
    assert [(i["sucursal"], i["tipo_ubicacion"]) for i in resumen["items"]] == [("LA 21", "sucursal")]
    assert resumen["global_"]["total"] == 1888
    bodega = _get(http, tok["principal"], "consulta/inventario/resumen", sucursal_id=BODEGA)
    assert bodega["global_"]["total"] == 1973
    valor = _get(http, tok["gerente"], "consulta/inventario/valorizado", sucursal_id=PRINCIPAL)
    assert valor["total_valor"] == pytest.approx(350588181.351)
    assert {i["tipo_ubicacion"] for i in valor["items"]} == {"sucursal"}


# ── Alertas (P2, P3, P4, P5) ────────────────────────

def test_alertas_con_las_reglas_de_d4(http, tok):
    resumen = _get(http, tok["gerente"], "alertas/resumen")
    assert resumen["por_tipo"] == {"inconsistencia_inventario": 220, "stock_critico": 1114, "stock_bajo": 386,
                                   "sin_movimiento": 2453, "rotacion_baja": 279}
    assert resumen["global_"]["total"] == 4452
    alertas = _get(http, tok["bodega"], "alertas")["items"]
    de_la_bodega = {a["tipo"] for a in alertas if a["tipo_ubicacion"] == "bodega_central"}
    assert de_la_bodega == {"inconsistencia_inventario", "stock_critico", "stock_bajo"}
    assert all(a["valor"] < 0 for a in alertas if a["tipo"] == "inconsistencia_inventario")
    assert all(a["valor"] >= 0 for a in alertas if a["tipo"] == "stock_critico")
    assert _get(http, tok["gerente"], "alertas", tipo="inconsistencia_inventario")["total"] == 220


def test_admin_sucursal_solo_ve_sus_alertas(http, tok):
    resumen = _get(http, tok["principal"], "alertas/resumen")
    assert resumen["global_"]["total"] == 1308 and resumen["por_tipo"]["inconsistencia_inventario"] == 95
    _get(http, tok["principal"], "alertas", 403, sucursal_id=BODEGA)
    _get(http, tok["principal"], "alertas/resumen", 403, sucursal_id=GLORIETA)
    filtrado = _get(http, tok["gerente"], "alertas/resumen", sucursal_id=GLORIETA)
    assert [i["sucursal"] for i in filtrado["items"]] == ["GLORIETA"]


# ── Reportes (P2, R6) ───────────────────────────────

def test_admin_bodega_ve_los_reportes_del_gerente(http, tok):
    assert _get(http, tok["bodega"], "reportes/kpis") == _get(http, tok["gerente"], "reportes/kpis")
    ventas = _get(http, tok["bodega"], "reportes/ventas")
    assert ventas["total_valor"] == pytest.approx(737879055.35)
    assert _get(http, tok["bodega"], "reportes/ventas", sucursal_id=PRINCIPAL)["total_valor"] == pytest.approx(
        471756931.58)


def test_admin_sucursal_solo_ve_sus_ventas(http, tok):
    assert _get(http, tok["principal"], "reportes/ventas")["total_valor"] == pytest.approx(471756931.58)
    for ruta in ("reportes/kpis", "reportes/ventas", "reportes/tendencias"):
        _get(http, tok["principal"], ruta, 403, sucursal_id=BODEGA)
        _get(http, tok["principal"], ruta, 403, sucursal_id=GLORIETA)


def test_tendencias_acepta_dias(http, tok):
    body = _get(http, tok["gerente"], "reportes/tendencias", dias=7)
    assert body["fecha_inicio"] == "2025-12-24" and len(body["series"][0]["puntos"]) == 8
    assert _get(http, tok["gerente"], "reportes/tendencias")["fecha_inicio"] == "2025-12-01"


# ── Regresión de lo que no cambió (cifras de la auditoría) ──

def test_consulta_filtros_categorias_proveedores_y_404(http, tok):
    g = tok["gerente"]
    assert _get(http, g, "consulta/productos", categoria="Huevos")["total"] == 2
    assert _get(http, g, "consulta/productos", familia="Huevos")["total"] == 2
    perecederos = _get(http, g, "consulta/productos", perecedero="true", page_size=100)
    assert perecederos["total"] > 0 and all(p["es_perecedero"] for p in perecederos["items"])
    arroz = _get(http, g, "consulta/productos", busqueda="ARROZ ZULIA")["items"]
    assert "P3937" in [p["codigo_item"] for p in arroz]
    assert _get(http, g, "consulta/proveedores")["total"] == 10
    categorias = _get(http, g, "consulta/categorias")
    assert categorias["total"] == 33 and sum(c["total_productos"] for c in categorias["items"]) == 4449
    _get(http, g, "consulta/productos/999999", 404)
    _get(http, g, "consulta/proveedores/999", 404)


def test_inventario_filtros_cuadran_con_el_resumen(http, tok):
    g = tok["gerente"]
    contadores = _get(http, g, "consulta/inventario/resumen", sucursal_id=PRINCIPAL)["global_"]
    for semaforo in ("ok", "bajo", "critico"):
        body = _get(http, g, "consulta/inventario", sucursal_id=PRINCIPAL, semaforo=semaforo, page_size=100)
        assert body["total"] == contadores[semaforo]
        assert {f["semaforo"] for f in body["items"]} == {semaforo}
    huevos = _get(http, g, "consulta/inventario", categoria="Huevos", busqueda="HUEVOS")
    assert huevos["total"] > 0 and {f["categoria"] for f in huevos["items"]} == {"Huevos"}
    # los huevos son perecederos: nunca están en la Bodega (A3 de INV-22)
    _get(http, g, "consulta/inventario/detalle", 404, id_producto=P1632, id_sucursal=BODEGA)


def test_alertas_filtros_y_validacion(http, tok):
    g = tok["gerente"]
    medias = _get(http, g, "alertas", urgencia="media")
    assert medias["total"] == 2453 + 279 and {a["urgencia"] for a in medias["items"]} == {"media"}
    _get(http, g, "alertas", 400, tipo="no_existe")
    _get(http, g, "alertas", 400, urgencia="maxima")


def test_reportes_de_ventas_como_en_la_auditoria(http, tok):
    g = tok["gerente"]
    comparativa = _get(http, g, "reportes/ventas/comparativa", agrupacion="semana")
    assert (comparativa["resumen"]["valor_actual"], comparativa["resumen"]["variacion_pct"]) == (737879055.35, 50.1)
    assert _get(http, g, "reportes/ventas/comparativa", agrupacion="mes")["detalle"][0]["periodo"] == "2025-12"
    top = _get(http, g, "reportes/ventas/top-productos", limite=3, categoria="Licores")
    assert [p["nombre"] for p in top["items"]][:2] == ["VINO SANSON *750 ML", "VINO CARIÑOSO SURT *750 ML"]
    distribucion = _get(http, g, "reportes/distribucion-categorias")
    assert len(distribucion["items"]) == 32 and distribucion["total_valor"] == pytest.approx(737879055.35)
    por_semana = _get(http, g, "reportes/ventas", agrupacion="semana", categoria="Licores")
    assert por_semana["agrupacion"] == "semana" and por_semana["items"][0]["periodo"].startswith("2025-W")
    assert len(_get(http, g, "reportes/ventas", agrupacion="mes")["items"]) == 1
    series = _get(http, g, "reportes/tendencias", por_sucursal="true")["series"]
    assert sorted(s["sucursal"] for s in series) == ["GLORIETA", "LA 21", "PRINCIPAL"]


# ── Pronóstico (P7) ─────────────────────────────────

def _ml_disponible():
    try:
        return httpx.get(f"{get_settings().ML_SERVICE_URL}/api/health", timeout=5).status_code == 200
    except httpx.HTTPError:
        return False


def test_predict_con_ml_service_real(http, tok):
    if not _ml_disponible():
        pytest.skip("ml_service no disponible")
    pedido = {"producto_id": "P1632", "sucursal_id": "PRINCIPAL", "horizonte": 15}
    r = http.post("/api/ml/predict", json=pedido, headers=tok["principal"])
    assert r.status_code == 200, r.text
    assert (r.json()["prediccion_q50"], r.json()["intervalo_confianza"]["limite_superior"]) == (3366.01, 4608.72)
    assert http.post("/api/ml/predict", json={**pedido, "sucursal_id": "GLORIETA"},
                     headers=tok["principal"]).status_code == 403
    bodega = http.post("/api/ml/predict", json={**pedido, "sucursal_id": "BODEGA_CENTRAL"}, headers=tok["gerente"])
    assert bodega.status_code == 422 and "no es una sucursal física" in bodega.json()["detail"]
    corta = http.post("/api/ml/predict", json={"producto_id": "00070", "sucursal_id": "GLORIETA", "horizonte": 15},
                      headers=tok["gerente"])
    assert corta.status_code == 404 and "historia suficiente" in corta.json()["detail"]
