"""INV-20 — Endpoint con TestClient (lifespan real: carga los modelos reales)
sobre la bodega en memoria de conftest.py. La prueba contra Postgres real está
en test_bodega_integracion.py."""


def test_health_ok(app_client):
    r = app_client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["bodega"] == "ok"
    assert set(body["modelos_cargados"]) == {"intermitente", "suave_no_perecedero", "suave_perecedero"}


def test_health_trae_foto_y_politicas_para_la_cache_del_core_api(app_client, bodega_falsa):
    """INV-23: el Core API arma la clave de su caché con estos campos."""
    body = app_client.get("/api/health").json()
    assert body["fecha_inventario"] == bodega_falsa.fecha_inventario().date().isoformat()
    assert body["politicas"] == {"inv21": {"version": 1, "fecha": "2026-09-30"},
                                 "inv22": {"version": 1, "fecha": "2026-09-30"}}


def test_health_sin_bodega_o_sin_foto_deja_la_fecha_nula(app_client, bodega_falsa, monkeypatch):
    def sin_foto():
        raise LookupError("dw.fact_inventario vacía")

    monkeypatch.setattr(bodega_falsa, "fecha_inventario", sin_foto)
    body = app_client.get("/api/health").json()
    assert (body["status"], body["fecha_inventario"]) == ("ok", None)
    monkeypatch.setattr(bodega_falsa, "disponible", lambda: False)
    body = app_client.get("/api/health").json()
    assert (body["status"], body["bodega"], body["fecha_inventario"]) == ("degradado", "sin conexión", None)
    assert body["politicas"]["inv21"]["version"] == 1


def test_predict_par_con_historia_devuelve_200(app_client):
    r = app_client.post("/api/predict", json={"producto_id": "P1", "sucursal_id": "PRINCIPAL", "horizonte": 15})
    assert r.status_code == 200
    body = r.json()
    assert body["prediccion_q50"] >= 0
    assert body["rama"] == "suave_no_perecedero"
    assert body["intervalo_confianza"]["limite_superior"] >= body["intervalo_confianza"]["limite_inferior"]
    assert body["fecha_features"] == "2025-06-30"
    assert (body["id_producto"], body["id_sucursal"]) == (1, 1)
    assert isinstance(body["interpretacion"], str) and len(body["interpretacion"]) > 0


def test_predict_por_ids_de_postgres_da_lo_mismo(app_client):
    por_codigo = app_client.post("/api/predict", json={"producto_id": "P2", "sucursal_id": "PRINCIPAL", "horizonte": 15})
    por_id = app_client.post("/api/predict", json={"id_producto": 2, "id_sucursal": 1, "horizonte": 15})
    assert por_codigo.status_code == por_id.status_code == 200
    assert por_codigo.json() == por_id.json()
    assert por_id.json()["rama"] == "intermitente"


def test_predict_con_fecha_corte_usa_esa_fecha(app_client):
    r = app_client.post("/api/predict", json={"producto_id": "P1", "sucursal_id": "PRINCIPAL", "horizonte": 15,
                                              "fecha_corte": "2025-05-15"})
    assert r.status_code == 200
    assert r.json()["fecha_features"] == "2025-05-15"


def test_fecha_corte_posterior_al_ultimo_dato_da_422(app_client):
    r = app_client.post("/api/predict", json={"producto_id": "P1", "sucursal_id": "PRINCIPAL", "horizonte": 15,
                                              "fecha_corte": "2025-08-01"})
    assert r.status_code == 422


def test_predict_horizonte_invalido_da_422(app_client):
    r = app_client.post("/api/predict", json={"producto_id": "P1", "sucursal_id": "PRINCIPAL", "horizonte": 30})
    assert r.status_code == 422


def test_sin_identificadores_da_422(app_client):
    r = app_client.post("/api/predict", json={"sucursal_id": "PRINCIPAL", "horizonte": 15})
    assert r.status_code == 422


def test_sucursal_no_fisica_da_422(app_client):
    r = app_client.post("/api/predict", json={"producto_id": "P1", "sucursal_id": "SIN_SUCURSAL", "horizonte": 15})
    assert r.status_code == 422
    assert "no es una sucursal física" in r.json()["detail"]


def test_producto_inexistente_da_404(app_client):
    r = app_client.post("/api/predict", json={"producto_id": "NO-EXISTE-999", "sucursal_id": "PRINCIPAL", "horizonte": 15})
    assert r.status_code == 404


def test_sucursal_inexistente_da_404(app_client):
    r = app_client.post("/api/predict", json={"producto_id": "P1", "sucursal_id": "NINGUNA", "horizonte": 15})
    assert r.status_code == 404


def test_par_sin_historia_suficiente_da_404(app_client):
    r = app_client.post("/api/predict", json={"producto_id": "P3", "sucursal_id": "PRINCIPAL", "horizonte": 15})
    assert r.status_code == 404
    assert "historia suficiente" in r.json()["detail"]


def test_bodega_caida_da_503(app_client, bodega_falsa):
    from sqlalchemy.exc import OperationalError

    def caida(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("conexión rechazada"))

    bodega_falsa.producto = caida
    r = app_client.post("/api/predict", json={"producto_id": "P1", "sucursal_id": "PRINCIPAL", "horizonte": 15})
    assert r.status_code == 503


def test_openapi_disponible(app_client):
    r = app_client.get("/api/openapi.json")
    assert r.status_code == 200
    assert "/api/predict" in r.json()["paths"]
