"""INV-23 — GET /api/ml/recomendaciones/transferencias sobre la respuesta falsa
de POST /api/transferencias (conftest.py): filtros, balance opcional (C4) y
resumen por unidad (R4)."""
import pytest

from tests.conftest import BODEGA, transferencias_ml


def _ids(filas):
    return [f["producto_id"] for f in filas]


def test_sin_filtros_sin_balance_y_con_las_sin_pronostico_solo_contadas(ctx):
    r = ctx.get("transferencias")
    assert r.status_code == 200, r.text
    body, original = r.json(), transferencias_ml()
    assert "balance" not in body
    assert _ids(body["traslados"]) == ["P1", "P2", "P3", "K1"]
    assert body["traslados"][0]["nombre_producto"] == "HUEVOS *UND"
    assert [a["tipo"] for a in body["alertas"]] == ["stock_negativo"]
    for campo in ("fecha_inventario", "fecha_pronostico", "horizonte_dias", "politicas", "no_encontrados"):
        assert body[campo] == original[campo]
    res, res_ml = body["resumen"], original["resumen"]
    assert res == {"productos": 6, "traslados": 4, "cantidad_trasladada": {"unidad": 20, "kg": 3},
                   "filas_balance": 7, "deficit_total": {"unidad": 28.0, "kg": 4.5},
                   "deficit_neto": {"unidad": 12.0, "kg": 1.5}, "excedente_sin_destino": {"unidad": 5.0, "kg": 0.0},
                   "alertas": 1, "alertas_stock_negativo": 1, "alertas_sin_pronostico": 1}
    # R4: separadas por unidad, suman lo que ml_service mezcla
    for campo in ("cantidad_trasladada", "deficit_total", "deficit_neto", "excedente_sin_destino"):
        assert sum(res[campo].values()) == pytest.approx(res_ml[campo])
    assert res["productos"] == res_ml["productos"] and res["alertas_stock_negativo"] + res["alertas_sin_pronostico"] == res_ml["alertas"]
    assert ctx.ml.cuerpos["/api/transferencias"] == {"incluir_balance": True}


def test_con_balance_llegan_las_filas_y_las_alertas_sin_pronostico(ctx):
    body = ctx.get("transferencias", incluir_balance="true").json()
    assert len(body["balance"]) == 7 and body["balance"][0]["nombre_producto"] == "HUEVOS *UND"
    assert [a["tipo"] for a in body["alertas"]] == ["stock_negativo", "sin_pronostico"]
    assert body["resumen"]["alertas"] == 2


def test_sucursal_filtra_traslados_por_origen_o_destino(ctx):
    body = ctx.get("transferencias", sucursal="la 21", incluir_balance="true").json()
    assert [(t["origen"], t["destino"]) for t in body["traslados"]] == [
        ("GLORIETA", "LA 21"), ("LA 21", "PRINCIPAL"), (BODEGA, "LA 21")]
    assert {b["sucursal"] for b in body["balance"]} == {"LA 21"} and len(body["balance"]) == 2
    assert body["alertas"] == []
    assert body["resumen"]["cantidad_trasladada"] == {"unidad": 10, "kg": 3}


def test_sucursal_bodega(ctx):
    body = ctx.get("transferencias", sucursal="BODEGA_CENTRAL").json()
    assert _ids(body["traslados"]) == ["P1", "K1"]
    assert body["resumen"]["filas_balance"] == 1
    assert body["resumen"]["excedente_sin_destino"] == {"unidad": 5.0, "kg": 0.0}


def test_urgencia_vigilancia_y_las_alertas_no_se_filtran(ctx):
    body = ctx.get("transferencias", urgencia="vigilancia", incluir_balance="true").json()
    assert body["traslados"] == []
    assert _ids(body["balance"]) == ["L1"]
    assert len(body["alertas"]) == 2


def test_la_urgencia_nula_no_pasa_el_filtro(ctx):
    body = ctx.get("transferencias", urgencia="urgente", incluir_balance="true").json()
    assert [(b["producto_id"], b["sucursal"]) for b in body["balance"]] == [("P1", "PRINCIPAL"), ("K1", "LA 21")]
    assert _ids(body["traslados"]) == ["P1", "K1"]


def test_categoria_filtra_balance_y_alertas(ctx):
    body = ctx.get("transferencias", categoria="aseo HOGAR").json()
    assert body["traslados"] == [] and body["alertas"] == []
    assert body["resumen"]["filas_balance"] == 1 and body["resumen"]["alertas_sin_pronostico"] == 1
    body = ctx.get("transferencias", categoria="aseo hogar", incluir_balance="true").json()
    assert _ids(body["balance"]) == ["S1"] and _ids(body["alertas"]) == ["S1"]


def test_tres_filtros_combinados_y_combinacion_vacia(ctx):
    body = ctx.get("transferencias", sucursal="PRINCIPAL", categoria="arroz", urgencia="normal").json()
    assert [(t["producto_id"], t["origen"]) for t in body["traslados"]] == [("P3", "LA 21")]
    body = ctx.get("transferencias", sucursal="GLORIETA", categoria="Huevos").json()
    assert body["traslados"] == [] and body["alertas"] == []
    assert body["resumen"]["productos"] == 0 and body["resumen"]["deficit_total"] == {"unidad": 0, "kg": 0}


@pytest.mark.parametrize("params", [{"sucursal": "SIN_SUCURSAL"}, {"categoria": "Abarrotes"},
                                    {"urgencia": "media"}, {"incluir_balance": "talvez"}])
def test_parametros_invalidos_dan_422(ctx, params):
    assert ctx.get("transferencias", **params).status_code == 422
