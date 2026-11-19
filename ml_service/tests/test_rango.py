"""INV-79 — Pronóstico para una fecha o un rango elegidos. La bodega falsa tiene ventas diarias del 2025-01-01 al 2025-06-30,
dim_tiempo hasta el 2025-09-30 y el 2025-07-04 como cierre programado. En la historia, todos los días son hábiles."""
import pandas as pd
import pytest

from prediccion.features import HistoriaInsuficiente
from prediccion.rango import (
    FechaInvalida,
    Tramo,
    armar_rango,
    resolver_inicio,
    tramos_rango,
    ventas_en,
)

T = pd.Timestamp


@pytest.fixture()
def calendario(bodega_falsa):
    return bodega_falsa.calendario()


def test_resolver_inicio_sin_fecha_pasada_y_futura(calendario):
    assert resolver_inicio(calendario, None, T("2025-07-10")) == (T("2025-06-30"), T("2025-07-10"))
    # pasada: con lo que se sabía el día hábil anterior
    assert resolver_inicio(calendario, "2025-06-10", T("2025-07-10")) == (T("2025-06-09"), T("2025-06-09"))
    # futura: datos al último día y operación el día anterior a la fecha pedida
    assert resolver_inicio(calendario, "2025-07-10", None) == (T("2025-06-30"), T("2025-07-09"))
    assert resolver_inicio(calendario, "2025-07-01", None) == (T("2025-06-30"), T("2025-06-30"))


def test_resolver_inicio_fuera_del_calendario_o_sin_historia(calendario):
    with pytest.raises(FechaInvalida, match="posterior al calendario"):
        resolver_inicio(calendario, "2025-10-01", None)
    with pytest.raises(HistoriaInsuficiente):
        resolver_inicio(calendario, "2025-01-01", None)


def test_tramos_reparto_y_ventanas_encadenadas(calendario):
    corto = tramos_rango(calendario, T("2025-06-09"), "2025-06-13")
    assert corto == [Tramo(T("2025-06-10"), T("2025-06-13"), 4, T("2025-06-09"))]
    # del 1-jul al 10-ago: 41 días sin el cierre del 4-jul = 40, en ventanas de 15, 15 y 10
    largo = tramos_rango(calendario, T("2025-06-30"), "2025-08-10")
    assert [t.dias_habiles for t in largo] == [15, 15, 10]
    assert (largo[0].desde, largo[0].hasta, largo[0].inicio) == (T("2025-07-01"), T("2025-07-16"), T("2025-06-30"))
    assert (largo[1].desde, largo[1].inicio) == (T("2025-07-17"), T("2025-07-16"))
    assert largo[2].hasta == T("2025-08-10")


def test_tramos_invalidos(calendario):
    with pytest.raises(FechaInvalida, match="anterior al primer día de la ventana"):
        tramos_rango(calendario, T("2025-06-30"), "2025-06-15")
    with pytest.raises(FechaInvalida, match="máximo es 10"):
        tramos_rango(calendario, T("2025-06-30"), "2025-07-20", maximo=10)
    with pytest.raises(FechaInvalida, match="fecha_fin"):
        tramos_rango(calendario, T("2025-06-30"), "2025-12-31")


def test_ventas_en_solo_con_el_tramo_entero_en_la_historia():
    unidades = pd.Series(2.0, index=pd.date_range("2025-06-01", "2025-06-30"))
    assert ventas_en(unidades, "2025-06-10", "2025-06-14", T("2025-06-30")) == 10.0
    assert ventas_en(unidades, "2025-06-25", "2025-07-05", T("2025-06-30")) is None
    assert ventas_en(None, "2025-06-10", "2025-06-14", T("2025-06-30")) is None


def test_armar_rango_suma_las_partes_y_marca_aproximado(calendario):
    tramos = tramos_rango(calendario, T("2025-06-30"), "2025-08-10")
    rango = armar_rango(calendario, tramos, [30.0, 45.0, 15.0], None, T("2025-06-30"))
    assert [v["prediccion_q50_aproximada"] for v in rango["ventanas"]] == [30.0, 45.0, 10.0]
    assert (rango["prediccion_q50_aproximada"], rango["dias_habiles"], rango["metodo"]) == (85.0, 40, "ventanas_encadenadas")
    assert (rango["ventas_reales"], rango["fuera_de_lo_medido"], rango["aproximado"]) == (None, False, True)
    corto = armar_rango(calendario, tramos_rango(calendario, T("2025-06-09"), "2025-06-13"), [30.0],
                        pd.Series(1.0, index=pd.date_range("2025-06-01", "2025-06-30")), T("2025-06-09"))
    assert (corto["prediccion_q50_aproximada"], corto["metodo"], corto["ventas_reales"]) == (8.0, "reparto", 4.0)


def _predict(app_client, **campos):
    return app_client.post("/api/predict", json={"producto_id": "P1", "sucursal_id": "PRINCIPAL", "horizonte": 15, **campos})


def test_predict_sin_fechas_no_cambia(app_client):
    body = _predict(app_client).json()
    assert (body["ventana_desde"], body["ventas_reales_ventana"], body["rango"]) == ("2025-07-01", None, None)


def test_predict_fecha_pasada_compara_con_lo_vendido(app_client, bodega_falsa):
    body = _predict(app_client, fecha_inicio="2025-06-10", fecha_fin="2025-06-14").json()
    assert (body["fecha_datos"], body["fecha_operacion"], body["dias_habiles_sin_datos"]) == ("2025-06-09", "2025-06-09", 0)
    assert (body["ventana_desde"], body["ventana_hasta"]) == ("2025-06-10", "2025-06-24")
    serie = bodega_falsa.ventas_diarias("P1", "PRINCIPAL", hasta="2025-06-30")
    assert body["ventas_reales_ventana"] == round(float(serie["2025-06-10":"2025-06-24"].sum()), 2)
    rango = body["rango"]
    assert (rango["metodo"], rango["dias_habiles"], rango["aproximado"]) == ("reparto", 5, True)
    assert rango["prediccion_q50_aproximada"] == pytest.approx(body["prediccion_q50"] * 5 / 15, abs=0.01)
    assert rango["ventas_reales"] == round(float(serie["2025-06-10":"2025-06-14"].sum()), 2)
    # el pronóstico pasado es el mismo que con fecha_corte el día anterior
    corte = _predict(app_client, fecha_corte="2025-06-09").json()
    assert corte["prediccion_q50"] == body["prediccion_q50"]


def test_predict_fecha_futura_y_rango_largo(app_client):
    body = _predict(app_client, fecha_inicio="2025-07-10", fecha_fin="2025-08-20").json()
    assert (body["fecha_datos"], body["fecha_operacion"], body["ventana_desde"]) == ("2025-06-30", "2025-07-09", "2025-07-10")
    assert (body["dias_habiles_sin_datos"], body["ventas_reales_ventana"]) == (8, None)       # 1 al 9 de julio sin el 4
    rango = body["rango"]
    assert (rango["metodo"], rango["dias_habiles"], [v["dias_habiles"] for v in rango["ventanas"]]) == (
        "ventanas_encadenadas", 42, [15, 15, 12])
    assert rango["ventanas"][0]["prediccion_q50_aproximada"] == pytest.approx(body["prediccion_q50"], abs=0.01)
    assert rango["prediccion_q50_aproximada"] == pytest.approx(sum(v["prediccion_q50_aproximada"] for v in rango["ventanas"]),
                                                                abs=0.02)
    assert rango["ventas_reales"] is None and rango["fuera_de_lo_medido"] is False


def test_predict_un_dia_puntual(app_client):
    body = _predict(app_client, fecha_inicio="2025-07-15", fecha_fin="2025-07-15").json()
    assert (body["rango"]["dias_habiles"], body["rango"]["desde"], body["rango"]["hasta"]) == (1, "2025-07-15", "2025-07-15")
    assert body["rango"]["prediccion_q50_aproximada"] == pytest.approx(body["prediccion_q50"] / 15, abs=0.01)


def test_predict_solo_fecha_fin_arranca_en_la_ventana_por_defecto(app_client):
    body = _predict(app_client, fecha_fin="2025-07-05").json()
    assert (body["rango"]["desde"], body["rango"]["dias_habiles"]) == ("2025-07-01", 4)


@pytest.mark.parametrize("campos, mensaje", [
    ({"fecha_corte": "2025-06-01", "fecha_inicio": "2025-06-10"}, "fecha_corte no se combina"),
    ({"fecha_inicio": "2025-07-10", "fecha_fin": "2025-07-01"}, "anterior a fecha_inicio"),
    ({"fecha_fin": "2025-06-15"}, "anterior al primer día de la ventana"),
    ({"fecha_inicio": "2025-04-01", "fecha_fin": "2025-09-30"}, "el máximo es 90"),
    ({"fecha_inicio": "2025-12-01"}, "posterior al calendario"),
])
def test_predict_fechas_invalidas_dan_422(app_client, campos, mensaje):
    r = _predict(app_client, **campos)
    assert r.status_code == 422 and mensaje in r.text


def test_predict_fecha_pasada_sin_historia_da_404(app_client):
    assert _predict(app_client, fecha_inicio="2025-01-01").status_code == 404
