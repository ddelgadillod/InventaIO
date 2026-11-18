"""INV-62 — Pronóstico al día presente: fecha de operación, días hábiles sin datos y ventana, en el endpoint de pronóstico,
los traslados y las compras. La bodega falsa tiene ventas hasta el 2025-06-30 y dim_tiempo hasta el 2025-09-30, con el
2025-07-04 como cierre programado."""
from datetime import datetime

import pandas as pd
import pytest

from prediccion import operacion
from prediccion.operacion import (
    ZONA_BOGOTA,
    dias_habiles_entre,
    fecha_operacion,
    fuera_de_lo_medido,
    ventana,
)
from tests.conftest import PronosticosFijos


@pytest.fixture()
def calendario(bodega_falsa):
    return bodega_falsa.calendario()


def test_fecha_operacion_de_la_variable_y_nunca_antes_del_ultimo_dato(calendario, monkeypatch):
    monkeypatch.setenv("FECHA_OPERACION", "2025-07-10")
    assert fecha_operacion(calendario) == pd.Timestamp("2025-07-10")
    monkeypatch.setenv("FECHA_OPERACION", "2025-01-15")
    assert fecha_operacion(calendario) == pd.Timestamp("2025-06-30")


def test_sin_variable_es_hoy_en_bogota(calendario, monkeypatch):
    monkeypatch.delenv("FECHA_OPERACION", raising=False)
    # a las 22:00 del 18-nov en Bogotá ya es 19-nov en UTC: cuenta la fecha de Bogotá
    assert fecha_operacion(calendario, ahora=datetime(2025, 8, 18, 22, 0, tzinfo=ZONA_BOGOTA)) == pd.Timestamp("2025-08-18")
    assert fecha_operacion(calendario) >= calendario.ultima_fecha


def test_dias_habiles_sin_datos_descuentan_los_cierres(calendario):
    assert dias_habiles_entre(calendario, "2025-06-30", "2025-07-10") == 9      # 1 al 10 de julio sin el cierre del 4
    assert dias_habiles_entre(calendario, "2025-06-30", "2025-06-30") == 0
    assert dias_habiles_entre(calendario, "2025-06-20", "2025-06-30") == 10     # dentro de la historia


def test_ventana_son_los_dias_habiles_siguientes(calendario):
    assert ventana(calendario, "2025-07-10", 15) == (pd.Timestamp("2025-07-11"), pd.Timestamp("2025-07-25"))
    assert ventana(calendario, "2025-07-01", 5) == (pd.Timestamp("2025-07-02"), pd.Timestamp("2025-07-07"))


def test_predict_al_dia_presente_dice_la_ventana_y_los_dias_sin_datos(app_client, monkeypatch):
    monkeypatch.setenv("FECHA_OPERACION", "2025-07-10")
    body = app_client.post("/api/predict", json={"producto_id": "P1", "sucursal_id": "PRINCIPAL", "horizonte": 15}).json()
    assert (body["fecha_features"], body["fecha_datos"], body["fecha_operacion"]) == ("2025-06-30", "2025-06-30", "2025-07-10")
    assert (body["ventana_desde"], body["ventana_hasta"], body["dias_habiles_sin_datos"]) == ("2025-07-11", "2025-07-25", 9)
    assert body["fuera_de_lo_medido"] is False


def test_predict_sin_desfase_conserva_la_ventana_de_siempre(app_client):
    body = app_client.post("/api/predict", json={"producto_id": "P1", "sucursal_id": "PRINCIPAL", "horizonte": 15}).json()
    assert (body["fecha_operacion"], body["ventana_desde"], body["dias_habiles_sin_datos"]) == ("2025-06-30", "2025-07-01", 0)


def test_predict_con_fecha_corte_pronostica_desde_esa_fecha(app_client, monkeypatch):
    monkeypatch.setenv("FECHA_OPERACION", "2025-07-10")
    body = app_client.post("/api/predict", json={"producto_id": "P1", "sucursal_id": "PRINCIPAL", "horizonte": 15,
                                                 "fecha_corte": "2025-05-15"}).json()
    assert (body["fecha_operacion"], body["ventana_desde"], body["dias_habiles_sin_datos"]) == ("2025-05-15", "2025-05-16", 0)


def test_el_desfase_cambia_solo_el_factor_de_calendario(app_client, bodega_falsa, monkeypatch):
    """La ventana desplazada puede cambiar el pronóstico por el factor de calendario; las demás features son las del último dato."""
    from main import app
    from prediccion.features import factor_calendario
    from prediccion.servicio import pronosticar_par

    loader = app.state.modelo_loader
    cal = bodega_falsa.calendario()
    producto = bodega_falsa.producto(codigo_item="P1")
    unidades = bodega_falsa.ventas_diarias("P1", "PRINCIPAL", hasta=cal.ultima_fecha)
    sin = pronosticar_par(loader, producto, "PRINCIPAL", unidades, cal, cal.ultima_fecha)
    mismo = pronosticar_par(loader, producto, "PRINCIPAL", unidades, cal, cal.ultima_fecha, inicio=cal.ultima_fecha)
    con = pronosticar_par(loader, producto, "PRINCIPAL", unidades, cal, cal.ultima_fecha, inicio=pd.Timestamp("2025-07-10"))
    assert sin == mismo
    assert factor_calendario(cal, "2025-07-10", loader.parametros_features) > 0
    assert con.rama == sin.rama


def test_traslados_y_compras_parten_de_la_fecha_de_operacion(app_client, bodega_falsa, monkeypatch):
    from main import app

    bodega_falsa.agregar_producto("T1")
    bodega_falsa.agregar_stock("T1", "BODEGA_CENTRAL", 10)
    bodega_falsa.agregar_stock("T1", "LA 21", 30)
    app.state.pronosticador = PronosticosFijos({("T1", "LA 21"): (30, 30)})
    antes = app_client.post("/api/compras", json={"productos": ["T1"]}).json()
    monkeypatch.setenv("FECHA_OPERACION", "2025-07-10")
    traslados = app_client.post("/api/transferencias", json={"productos": ["T1"]}).json()
    compras = app_client.post("/api/compras", json={"productos": ["T1"]}).json()
    assert (traslados["fecha_inventario"], traslados["fecha_operacion"], traslados["dias_habiles_sin_datos"]) == (
        "2025-06-30", "2025-07-10", 9)
    assert (traslados["ventana_desde"], traslados["ventana_hasta"]) == ("2025-07-11", "2025-07-25")
    assert compras["fecha_operacion"] == "2025-07-10"
    # el calendario de pedidos se corre: el quincenal pasa del día 2 al 16 y el semanal del martes 1 al martes 15 de julio
    assert [(p["grupo"], p["fecha_pedido"]) for p in antes["calendario"]] == [("quincenal", "2025-07-02"), ("semanal", "2025-07-01")]
    assert [(p["grupo"], p["fecha_pedido"]) for p in compras["calendario"]] == [("quincenal", "2025-07-16"), ("semanal", "2025-07-15")]


def test_fuera_de_lo_medido_pasados_90_dias_habiles():
    assert operacion.DESFASE_MEDIDO == 90
    assert (fuera_de_lo_medido(0), fuera_de_lo_medido(90), fuera_de_lo_medido(91)) == (False, False, True)


def test_predict_traslados_y_compras_avisan_fuera_de_lo_medido(app_client, bodega_falsa, monkeypatch):
    """La bodega falsa no alcanza 90 días después del último dato con ventana completa: se baja el límite a 5."""
    from main import app

    monkeypatch.setattr(operacion, "DESFASE_MEDIDO", 5)
    monkeypatch.setenv("FECHA_OPERACION", "2025-07-10")
    body = app_client.post("/api/predict", json={"producto_id": "P1", "sucursal_id": "PRINCIPAL", "horizonte": 15}).json()
    assert (body["dias_habiles_sin_datos"], body["fuera_de_lo_medido"]) == (9, True)
    bodega_falsa.agregar_producto("T1")
    bodega_falsa.agregar_stock("T1", "LA 21", 30)
    app.state.pronosticador = PronosticosFijos({("T1", "LA 21"): (30, 30)})
    assert app_client.post("/api/transferencias", json={"productos": ["T1"]}).json()["fuera_de_lo_medido"] is True
    assert app_client.post("/api/compras", json={"productos": ["T1"]}).json()["fuera_de_lo_medido"] is True


def test_salud_trae_el_ultimo_dato_y_la_fecha_de_operacion(app_client, monkeypatch):
    monkeypatch.setenv("FECHA_OPERACION", "2025-07-10")
    body = app_client.get("/api/health").json()
    assert (body["fecha_datos"], body["fecha_operacion"]) == ("2025-06-30", "2025-07-10")
