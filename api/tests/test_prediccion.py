"""INV-25 (D8) — POST /api/ml/predict en el Core API sobre la respuesta falsa de
ml_service (conftest.py): permisos por rol y errores que pasan tal cual (R5).
La prueba contra el servicio real está en test_homologacion_integracion.py."""
import httpx
import pytest

from tests.conftest import prediccion_ml

PEDIDO = {"producto_id": "P1", "sucursal_id": "PRINCIPAL", "horizonte": 15}


def _post(ctx, cuerpo):
    return ctx.http.post("/api/ml/predict", json=cuerpo)


def test_devuelve_la_respuesta_de_ml_service_sin_cambios(ctx):
    r = _post(ctx, {**PEDIDO, "fecha_corte": "2025-12-31"})
    assert r.status_code == 200, r.text
    assert r.json() == prediccion_ml()
    assert ctx.ml.cuerpos["/api/predict"] == {**PEDIDO, "fecha_corte": "2025-12-31"}


@pytest.mark.parametrize("rol, id_sucursal", [("gerente", None), ("admin_bodega", 5)])
def test_gerente_y_admin_bodega_pronostican_cualquier_sucursal(ctx, rol, id_sucursal):
    ctx.como(rol, id_sucursal)
    assert _post(ctx, {**PEDIDO, "sucursal_id": "GLORIETA"}).status_code == 200
    assert _post(ctx, {"id_producto": 91, "id_sucursal": 2, "horizonte": 15}).status_code == 200


@pytest.mark.parametrize("cuerpo", [PEDIDO, {"producto_id": "P1", "id_sucursal": 1, "horizonte": 15},
                                    {"producto_id": "P1", "sucursal_id": "PRINCIPAL", "id_sucursal": 3, "horizonte": 15}])
def test_admin_sucursal_pronostica_su_sucursal(ctx, cuerpo):
    # con nombre e id, manda el nombre (como en ml_service)
    assert _post(ctx.como("admin_sucursal", 1), cuerpo).status_code == 200


@pytest.mark.parametrize("cuerpo", [{**PEDIDO, "sucursal_id": "GLORIETA"},
                                    {"producto_id": "P1", "id_sucursal": 3, "horizonte": 15},
                                    {"producto_id": "P1", "horizonte": 15}])
def test_admin_sucursal_no_pronostica_otra_sucursal(ctx, cuerpo):
    r = _post(ctx.como("admin_sucursal", 1), cuerpo)
    assert r.status_code == 403
    assert r.json()["detail"] == "Solo puede pronosticar su sucursal (PRINCIPAL)"
    assert ctx.ml.llamadas["/api/predict"] == 0


@pytest.mark.parametrize("codigo, detalle", [
    (404, "No hay historia suficiente para producto_id=00070, sucursal_id=GLORIETA"),
    (422, "La sucursal BODEGA_CENTRAL (bodega_central) no es una sucursal física"),
    (422, [{"msg": "Value error, indicar producto_id (codigo_item) o id_producto"}]),
])
def test_los_errores_de_la_peticion_pasan_tal_cual(ctx, codigo, detalle):
    ctx.ml.fallas["/api/predict"] = (codigo, {"detail": detalle})
    r = _post(ctx, PEDIDO)
    assert (r.status_code, r.json()["detail"]) == (codigo, detalle)


@pytest.mark.parametrize("falla, codigo", [
    ((503, {"detail": "Bodega de datos no disponible"}), 503),
    ((500, {"detail": "Internal Server Error"}), 502),
    (httpx.ConnectError("conexión rechazada"), 503),
    (httpx.ReadTimeout("lento"), 504),
])
def test_los_demas_errores_se_traducen_como_en_inv23(ctx, falla, codigo):
    ctx.ml.fallas["/api/predict"] = falla
    assert _post(ctx, PEDIDO).status_code == codigo


def test_error_de_peticion_sin_json_usa_el_texto():
    from fastapi import HTTPException

    from ml.cliente import ClienteML

    cliente = ClienteML("http://ml-service", timeout=5,
                        transport=httpx.MockTransport(lambda req: httpx.Response(404, text="no encontrado")))
    with pytest.raises(HTTPException) as exc:
        cliente.predecir(PEDIDO)
    assert (exc.value.status_code, exc.value.detail) == (404, "no encontrado")


def test_cuerpo_invalido_422_sin_llamar_a_ml_service(ctx):
    assert _post(ctx, {"producto_id": "P1", "sucursal_id": "PRINCIPAL"}).status_code == 422   # sin horizonte
    assert ctx.ml.llamadas["/api/predict"] == 0


def test_openapi_documenta_predict_con_el_esquema_de_auth(ctx):
    openapi = ctx.http.get("/api/openapi.json").json()
    op = openapi["paths"]["/api/ml/predict"]["post"]
    assert op["tags"] == ["Pronóstico"]
    assert op["security"] == openapi["paths"]["/api/ml/recomendaciones/compras"]["get"]["security"]
    assert {"/api/consulta/productos", "/api/alertas", "/api/reportes/kpis"} <= set(openapi["paths"])
