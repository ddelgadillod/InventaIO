"""INV-23 — GET /api/ml/recomendaciones/compras sobre la respuesta falsa de
POST /api/compras (conftest.py): filtros, vista desde la sucursal (R1) y
resumen (R4). Permisos, caché y errores en sus propios archivos."""
import re

import pytest

from tests.conftest import BODEGA, compras_ml


def _ids(filas):
    return [f["producto_id"] for f in filas]


def test_sin_filtros_devuelve_lo_de_ml_service_enriquecido(ctx):
    r = ctx.get("compras")
    assert r.status_code == 200, r.text
    body, original = r.json(), compras_ml()
    assert _ids(body["compras"]) == _ids(original["compras"])
    assert _ids(body["cubrir_con_traslado"]) == ["L1"] and len(body["alertas"]) == 2
    for campo in ("fecha_inventario", "fecha_pronostico", "lead_time_dias", "politicas", "calendario", "no_encontrados"):
        assert body[campo] == original[campo]
    p1 = body["compras"][0]
    assert (p1["nombre_producto"], p1["categoria"], p1["necesidad_sucursal"]) == ("HUEVOS *UND", "Huevos", None)
    assert body["compras"][1]["detalle"] == original["compras"][1]["detalle"]          # detalle completo
    assert body["alertas"][1]["nombre_producto"] == "VASO TUC 7 OZ *UND"
    # R4: sin filtros, los totales son los de ml_service
    res, res_ml = body["resumen"], original["resumen"]
    for campo in ("lineas", "lineas_sucursal", "lineas_bodega", "cantidad", "cubiertos_por_bodega", "alertas"):
        assert res[campo] == res_ml[campo]
    assert res["cantidad_directa"] == {"unidad": 53, "kg": 8} and res["cantidad_bodega"] == {"unidad": 67, "kg": 0}
    assert res["necesidad_via_bodega"] is None and res["productos"] == 6
    assert body["filtros_aplicados"] == {"sucursal": None, "sucursal_por_rol": False, "categoria": None,
                                         "urgencia": None}
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", body["calculado_en"])
    assert ctx.ml.cuerpos["/api/compras"] == {"incluir_detalle": True}


def test_sucursal_fisica_trae_sus_directas_y_las_de_la_bodega_vistas_desde_ella(ctx):
    body = ctx.get("compras", sucursal="PRINCIPAL").json()
    p1, p2 = body["compras"]
    assert (p1["producto_id"], p1["tipo_destino"], p1["necesidad_sucursal"]) == ("P1", "sucursal", 49.3)
    # P2 es urgente por LA 21; desde PRINCIPAL es normal, con su detalle y su parte de la necesidad
    assert (p2["producto_id"], p2["destino"], p2["urgencia"], p2["dias_hasta_agotarse"]) == ("P2", BODEGA, "normal", 10.5)
    assert (p2["llega_tarde"], p2["motivo"], p2["necesidad_sucursal"]) == (False, "reposicion", 36.95)
    assert [d["sucursal"] for d in p2["detalle"]] == ["PRINCIPAL"]
    assert (p2["cantidad"], p2["necesidad"], p2["sobrante_bodega"]) == (47, 46.86, 0.0)   # la compra completa
    cubrir = body["cubrir_con_traslado"][0]
    assert (cubrir["urgencia"], cubrir["dias_hasta_agotarse"], cubrir["necesidad_sucursal"]) == ("normal", 14.0, 12.0)
    assert body["alertas"] == []
    assert body["resumen"] == {
        "productos": 3, "lineas": 2, "lineas_sucursal": 1, "lineas_bodega": 1,
        "cantidad": {"unidad": 97, "kg": 0}, "cantidad_directa": {"unidad": 50, "kg": 0},
        "cantidad_bodega": {"unidad": 47, "kg": 0}, "necesidad_via_bodega": {"unidad": 36.95, "kg": 0.0},
        "cubiertos_por_bodega": 1, "alertas": 0}


@pytest.mark.parametrize("sucursal, urgencia_p2", [(None, "urgente"), ("PRINCIPAL", "normal"), ("LA 21", "urgente")])
def test_la_urgencia_de_una_compra_de_la_bodega_es_la_de_la_sucursal_filtrada(ctx, sucursal, urgencia_p2):
    params = {"sucursal": sucursal} if sucursal else {}
    p2 = next(f for f in ctx.get("compras", **params).json()["compras"] if f["producto_id"] == "P2")
    assert p2["urgencia"] == urgencia_p2
    con_filtro = ctx.get("compras", urgencia="urgente", **params).json()["compras"]
    assert ("P2" in _ids(con_filtro)) == (urgencia_p2 == "urgente")


def test_sucursal_bodega_trae_solo_sus_compras_con_el_detalle_completo(ctx):
    body = ctx.get("compras", sucursal="bodega_central").json()
    assert _ids(body["compras"]) == ["P2", "P3"]
    assert len(body["compras"][0]["detalle"]) == 2 and body["compras"][0]["urgencia"] == "urgente"
    assert _ids(body["cubrir_con_traslado"]) == ["L1"] and len(body["cubrir_con_traslado"][0]["detalle"]) == 2
    assert [(a["producto_id"], a["sucursal"]) for a in body["alertas"]] == [("H1", BODEGA)]
    assert body["resumen"]["necesidad_via_bodega"] is None
    assert body["filtros_aplicados"]["sucursal"] == BODEGA


@pytest.mark.parametrize("valor", ["lacteos", " LÁCTEOS ", "Lácteos"])
def test_categoria_sin_mayusculas_ni_acentos(ctx, valor):
    body = ctx.get("compras", categoria=valor).json()
    assert body["compras"] == [] and _ids(body["cubrir_con_traslado"]) == ["L1"]
    assert body["filtros_aplicados"]["categoria"] == "Lácteos"


def test_los_kilos_van_a_kg_en_el_resumen(ctx):
    body = ctx.get("compras", categoria="frutas y verduras").json()
    assert _ids(body["compras"]) == ["K1"]
    assert body["resumen"]["cantidad"] == {"unidad": 0, "kg": 8}


def test_la_urgencia_no_filtra_las_alertas(ctx):
    body = ctx.get("compras", urgencia="normal").json()
    assert _ids(body["compras"]) == ["K1", "X9"]
    assert body["cubrir_con_traslado"] == []
    assert len(body["alertas"]) == 2 and body["resumen"]["alertas"] == 2


def test_tres_filtros_combinados(ctx):
    body = ctx.get("compras", sucursal="glorieta", categoria="ARROZ", urgencia="alta").json()
    assert _ids(body["compras"]) == ["P3"]
    assert body["resumen"]["necesidad_via_bodega"] == {"unidad": 25.5, "kg": 0.0}
    assert body["filtros_aplicados"] == {"sucursal": "GLORIETA", "sucursal_por_rol": False,
                                         "categoria": "Arroz", "urgencia": "alta"}


@pytest.mark.parametrize("params", [{"sucursal": "LA 21", "categoria": "Huevos"},
                                    {"categoria": "Anchetas", "urgencia": "urgente"}])
def test_combinacion_valida_sin_filas_da_listas_vacias(ctx, params):
    r = ctx.get("compras", **params)
    assert r.status_code == 200
    body = r.json()
    assert body["compras"] == body["cubrir_con_traslado"] == body["alertas"] == []
    res = body["resumen"]
    assert (res["productos"], res["lineas"], res["cantidad"], res["cubiertos_por_bodega"]) == (0, 0, {"unidad": 0, "kg": 0}, 0)


def test_sin_detalle_no_cambia_lo_guardado_en_la_cache(ctx):
    body = ctx.get("compras", sucursal="PRINCIPAL", incluir_detalle="false").json()
    assert all("detalle" not in f for f in body["compras"] + body["cubrir_con_traslado"])
    assert body["compras"][1]["urgencia"] == "normal"                  # la vista desde la sucursal sigue
    assert len(ctx.get("compras").json()["compras"][1]["detalle"]) == 2
    assert ctx.ml.llamadas["/api/compras"] == 1


def test_producto_sin_fila_en_dim_producto(ctx):
    body = ctx.get("compras").json()
    x9 = next(f for f in body["compras"] if f["producto_id"] == "X9")
    assert (x9["nombre_producto"], x9["categoria"]) == (None, None)
    assert "X9" not in _ids(ctx.get("compras", sucursal="GLORIETA", categoria="Arroz").json()["compras"])


@pytest.mark.parametrize("params", [{"sucursal": "CALLE 80"}, {"sucursal": "SIN_SUCURSAL"}, {"sucursal": ""},
                                    {"categoria": "Abarrotes"}, {"urgencia": "vigilancia"},
                                    {"incluir_detalle": "quizas"}])
def test_parametros_invalidos_dan_422(ctx, params):
    r = ctx.get("compras", **params)
    assert r.status_code == 422, r.text
    assert ctx.ml.llamadas["/api/compras"] == 0


def test_mensaje_de_sucursal_desconocida_lista_las_validas(ctx):
    detalle = ctx.get("compras", sucursal="Norte").json()["detail"]
    assert detalle == "Sucursal desconocida: 'Norte'. Válidas: PRINCIPAL, LA 21, GLORIETA, BODEGA_CENTRAL"
