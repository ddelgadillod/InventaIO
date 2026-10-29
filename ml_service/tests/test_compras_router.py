"""INV-21 — POST /api/compras con TestClient sobre la bodega en memoria y
pronósticos fijos, y la validación del archivo de políticas. La prueba contra
Postgres real está en test_compras_integracion.py."""
import json

import pandas as pd
import pytest

from compras.politicas import cargar_politicas_compras
from core.config import get_settings
from tests.conftest import PronosticosFijos

BODEGA = "BODEGA_CENTRAL"


@pytest.fixture()
def cliente(app_client, bodega_falsa):
    """T1 (seco): 10 en la Bodega, LA 21 con su mediana justa y stock negativo
    en GLORIETA. T2 (perecedero): LA 21 sin stock."""
    from main import app

    bodega_falsa.agregar_producto("T1")
    bodega_falsa.agregar_stock("T1", BODEGA, 10)
    bodega_falsa.agregar_stock("T1", "LA 21", 30)
    bodega_falsa.agregar_stock("T1", "GLORIETA", -2)
    bodega_falsa.agregar_producto("T2", es_perecedero_estricto=True)
    bodega_falsa.agregar_stock("T2", "LA 21", 0)
    app.state.pronosticador = PronosticosFijos({("T1", "LA 21"): (30, 30), ("T1", "GLORIETA"): (5, 8),
                                                ("T2", "LA 21"): (12, 15)})
    yield app_client


def test_compras_devuelve_lineas_calendario_y_alertas(cliente):
    r = cliente.post("/api/compras", json={"productos": ["T1", "T2", "NO-EXISTE"]})
    assert r.status_code == 200, r.text
    body = r.json()
    # T1: LA 21 necesita 44 − 30 = 14 y GLORIETA 8 × 22/15 = 11,73; menos los 10 de la Bodega -> 16
    assert [(c["producto_id"], c["destino"], c["cantidad"], c["motivo"]) for c in body["compras"]] == [
        ("T1", BODEGA, 16, "stock_negativo"), ("T2", "LA 21", 12, "reposicion")]
    assert body["politicas"]["inv21"] == {"version": 1, "fecha": "2026-09-30"}
    assert body["no_encontrados"] == ["NO-EXISTE"]
    assert [(a["producto_id"], a["sucursal"], a["accion"]) for a in body["alertas"]] == [
        ("T1", "GLORIETA", "compra_urgente")]
    assert [(p["grupo"], p["fecha_pedido"]) for p in body["calendario"]] == [("quincenal", "2025-07-02"),
                                                                            ("semanal", "2025-07-01")]
    assert body["resumen"]["cantidad"] == {"unidad": 28, "kg": 0}
    assert len(body["compras"][0]["detalle"]) == 2


def test_sin_detalle_las_lineas_no_traen_el_calculo(cliente):
    r = cliente.post("/api/compras", json={"productos": ["T1", "T2"], "incluir_detalle": False})
    assert r.status_code == 200
    body = r.json()
    assert body["compras"] and all("detalle" not in c for c in body["compras"])
    assert body["compras"][0]["sobrante_bodega"] == 10
    assert body["compras"][1]["sobrante_bodega"] is None                # directo: el campo viene, nulo


def test_sin_lista_procesa_el_catalogo_de_la_foto(cliente):
    r = cliente.post("/api/compras", json={})
    assert r.status_code == 200
    assert r.json()["resumen"]["productos"] == 2


def test_foto_sin_ventas_da_409(cliente, bodega_falsa):
    bodega_falsa._fecha_inventario = bodega_falsa.calendario().ultima_fecha + pd.Timedelta(days=2)
    r = cliente.post("/api/compras", json={"productos": ["T1"]})
    assert r.status_code == 409
    assert "faltan las ventas de 2 día(s)" in r.json()["detail"]


@pytest.mark.parametrize("cuerpo", [{"productos": []}, {"productos": "T1"}, {"incluir_detalle": "quizas"}])
def test_cuerpo_invalido_da_422(cliente, cuerpo):
    assert cliente.post("/api/compras", json=cuerpo).status_code == 422


def test_bodega_caida_da_503(cliente, bodega_falsa):
    from sqlalchemy.exc import OperationalError

    def caida(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("conexión rechazada"))

    bodega_falsa.fecha_inventario = caida
    r = cliente.post("/api/compras", json={"productos": ["T1"]})
    assert r.status_code == 503


def test_calendario_insuficiente_da_503(cliente, bodega_falsa):
    from prediccion.features import Calendario

    cal = bodega_falsa.calendario()
    # alcanza para INV-22 (traslados a 2 días hábiles), no para el pedido siguiente
    bodega_falsa._calendario = Calendario(habiles=cal.habiles, marcas=cal.marcas.loc[:"2025-07-15"])
    r = cliente.post("/api/compras", json={"productos": ["T1"]})
    assert r.status_code == 503
    assert "Calendario" in r.json()["detail"]


def test_openapi_expone_compras_transferencias_y_predict(cliente):
    paths = cliente.get("/api/openapi.json").json()["paths"]
    assert {"/api/compras", "/api/transferencias", "/api/predict"} <= set(paths)


# ── Archivo de políticas ────────────────────────────────────────────────────

def _politicas_con(tmp_path, cambio):
    datos = json.loads(open(get_settings().POLITICAS_COMPRAS_PATH, encoding="utf-8").read())
    cambio(datos)
    path = tmp_path / "politicas.json"
    path.write_text(json.dumps(datos), encoding="utf-8")
    return path


def test_politicas_del_repo_son_validas():
    p = cargar_politicas_compras(get_settings().POLITICAS_COMPRAS_PATH)
    assert (p.version, p.lead_time_dias, p.minimo_linea) == (1, 5, 1)
    assert p.calendario_pedidos.quincenal.dias_mes == [2, 16]
    assert p.calendario_pedidos.semanal.dias_semana_iso() == {1}          # martes


@pytest.mark.parametrize("cambio", [
    lambda d: d.update(destino_directo=["perecedero"]),                   # frío a la Bodega (A3)
    lambda d: d.update(grupo_semanal=["seco"]),
    lambda d: d.update(nivel="qalfa"),                                    # regla no implementada
    lambda d: d.update(horizonte_modelo_dias=30),
    lambda d: d.update(lead_time_dias=0),
    lambda d: d.update(minimo_linea=0),
    lambda d: d["calendario_pedidos"]["quincenal"].update(dias_mes=[30]),  # no existe en todos los meses
    lambda d: d["calendario_pedidos"]["semanal"].update(dias_mes=[2]),     # dias_mes y dias_semana a la vez
    lambda d: d["calendario_pedidos"]["semanal"].pop("dias_semana"),       # ninguno
    lambda d: d["calendario_pedidos"]["semanal"].update(dias_semana=["feriado"]),
    lambda d: d["urgencia"].update(urgente_dias=12),                      # más que alta_dias
    lambda d: d["bodega"].update(descontar_sobrante=False),
    lambda d: d.update(campo_desconocido=1),
    lambda d: d.pop("calendario_pedidos"),
])
def test_politicas_invalidas_se_rechazan(tmp_path, cambio):
    with pytest.raises(ValueError):
        cargar_politicas_compras(_politicas_con(tmp_path, cambio))


def test_politicas_inexistentes_o_mal_formadas(tmp_path):
    with pytest.raises(ValueError):
        cargar_politicas_compras(tmp_path / "no-existe.json")
    (tmp_path / "roto.json").write_text("{", encoding="utf-8")
    with pytest.raises(ValueError):
        cargar_politicas_compras(tmp_path / "roto.json")
