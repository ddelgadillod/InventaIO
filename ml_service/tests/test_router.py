"""INV-20 — Test end-to-end del endpoint, con TestClient (lifespan real:
carga modelos y snapshot reales)."""


def test_health_ok(app_client):
    r = app_client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert set(body["modelos_cargados"]) == {"intermitente", "suave_no_perecedero", "suave_perecedero"}


def test_predict_par_existente_devuelve_200(app_client, feature_store):
    alguna_fila = feature_store._df.iloc[0]
    payload = {
        "producto_id": alguna_fila["codigo_item"],
        "sucursal_id": alguna_fila["sucursal"],
        "horizonte": 15,
    }
    r = app_client.post("/api/predict", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["prediccion_q50"] >= 0
    assert body["rama"] in ("intermitente", "suave_no_perecedero", "suave_perecedero")
    assert body["intervalo_confianza"]["limite_superior"] >= body["intervalo_confianza"]["limite_inferior"]
    assert isinstance(body["interpretacion"], str) and len(body["interpretacion"]) > 0


def test_predict_horizonte_invalido_da_422(app_client, feature_store):
    alguna_fila = feature_store._df.iloc[0]
    payload = {
        "producto_id": alguna_fila["codigo_item"],
        "sucursal_id": alguna_fila["sucursal"],
        "horizonte": 30,
    }
    r = app_client.post("/api/predict", json=payload)
    assert r.status_code == 422


def test_predict_par_inexistente_da_404(app_client):
    payload = {"producto_id": "NO-EXISTE-999", "sucursal_id": "NINGUNA", "horizonte": 15}
    r = app_client.post("/api/predict", json=payload)
    assert r.status_code == 404


def test_openapi_disponible(app_client):
    r = app_client.get("/api/openapi.json")
    assert r.status_code == 200
    assert "/api/predict" in r.json()["paths"]
