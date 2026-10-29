"""INV-22 — POST /api/transferencias con TestClient sobre la bodega en memoria
y pronósticos fijos, y la validación del archivo de políticas. La prueba contra
Postgres real está en test_transferencias_integracion.py."""
import json

import pandas as pd
import pytest

from core.config import get_settings
from tests.conftest import PronosticosFijos
from transferencias.politicas import cargar_politicas

BODEGA = "BODEGA_CENTRAL"


@pytest.fixture()
def cliente(app_client, bodega_falsa):
    """Un producto con 30 en la Bodega, déficit en LA 21 y stock negativo en GLORIETA."""
    from main import app

    bodega_falsa.agregar_producto("T1")
    bodega_falsa.agregar_stock("T1", BODEGA, 30)
    bodega_falsa.agregar_stock("T1", "GLORIETA", -2)
    app.state.pronosticador = PronosticosFijos({("T1", "LA 21"): (20, 25), ("T1", "GLORIETA"): (5, 8)})
    yield app_client


def test_transferencias_devuelve_traslados_balance_y_alertas(cliente):
    r = cliente.post("/api/transferencias", json={"productos": ["T1", "NO-EXISTE"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [(t["origen"], t["destino"], t["cantidad"]) for t in body["traslados"]] == [(BODEGA, "LA 21", 20)]
    assert body["politicas"] == {"version": 1, "fecha": "2026-09-30"}
    assert body["no_encontrados"] == ["NO-EXISTE"]
    assert [(a["sucursal"], a["tipo"], a["accion"]) for a in body["alertas"]] == [("GLORIETA", "stock_negativo",
                                                                                   "pedido_urgente")]
    la21 = next(b for b in body["balance"] if b["sucursal"] == "LA 21")
    assert (la21["deficit"], la21["recibido"], la21["deficit_neto"], la21["estado"]) == (20, 20, 0, "destino")
    assert body["resumen"]["cantidad_trasladada"] == 20


def test_sin_balance_devuelve_solo_traslados_alertas_y_resumen(cliente):
    r = cliente.post("/api/transferencias", json={"productos": ["T1"], "incluir_balance": False})
    assert r.status_code == 200
    body = r.json()
    assert "balance" not in body
    assert body["traslados"] and body["alertas"] and body["resumen"]


def test_sin_lista_procesa_el_catalogo_de_la_foto(cliente):
    r = cliente.post("/api/transferencias", json={})
    assert r.status_code == 200
    assert r.json()["resumen"]["productos"] == 1          # solo T1 tiene fila en la foto


def test_foto_sin_ventas_da_409(cliente, bodega_falsa):
    bodega_falsa._fecha_inventario = bodega_falsa.calendario().ultima_fecha + pd.Timedelta(days=2)
    r = cliente.post("/api/transferencias", json={"productos": ["T1"]})
    assert r.status_code == 409
    assert "faltan las ventas de 2 día(s)" in r.json()["detail"]


@pytest.mark.parametrize("cuerpo", [{"productos": []}, {"productos": "T1"}, {"incluir_balance": "quizas"}])
def test_cuerpo_invalido_da_422(cliente, cuerpo):
    assert cliente.post("/api/transferencias", json=cuerpo).status_code == 422


def test_bodega_caida_da_503(cliente, bodega_falsa):
    from sqlalchemy.exc import OperationalError

    def caida(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("conexión rechazada"))

    bodega_falsa.fecha_inventario = caida
    r = cliente.post("/api/transferencias", json={"productos": ["T1"]})
    assert r.status_code == 503


def test_calendario_insuficiente_da_503(cliente, bodega_falsa):
    from prediccion.features import Calendario

    cal = bodega_falsa.calendario()
    bodega_falsa._calendario = Calendario(habiles=cal.habiles, marcas=cal.marcas.loc[:cal.ultima_fecha])
    r = cliente.post("/api/transferencias", json={"productos": ["T1"]})
    assert r.status_code == 503
    assert "Calendario" in r.json()["detail"]


def test_openapi_expone_transferencias_y_predict(cliente):
    paths = cliente.get("/api/openapi.json").json()["paths"]
    assert "/api/transferencias" in paths and "/api/predict" in paths


# ── Archivo de políticas ────────────────────────────────────────────────────

def _politicas_con(tmp_path, cambio):
    datos = json.loads(open(get_settings().POLITICAS_TRANSFERENCIAS_PATH, encoding="utf-8").read())
    cambio(datos)
    path = tmp_path / "politicas.json"
    path.write_text(json.dumps(datos), encoding="utf-8")
    return path


def test_politicas_del_repo_son_validas():
    p = cargar_politicas(get_settings().POLITICAS_TRANSFERENCIAS_PATH)
    assert (p.version, p.cantidades.minimo, p.stock_maximo.margen_no_perecedero) == (1, 6, 0.5)


@pytest.mark.parametrize("cambio", [
    lambda d: d.update(reparticion={"metodo": "proporcional", "desempate": "q50"}),   # regla no implementada
    lambda d: d.update(horizonte_dias=30),                                           # A1: solo 15
    lambda d: d["cantidades"].update(minimo=0),
    lambda d: d["urgencia"].update(urgente_dias=12),                                 # más que alta_dias
    lambda d: d["traslado"].update(dias_semana=["feriado"]),
    lambda d: d.update(campo_desconocido=1),
    lambda d: d.pop("stock_maximo"),
])
def test_politicas_invalidas_se_rechazan(tmp_path, cambio):
    with pytest.raises(ValueError):
        cargar_politicas(_politicas_con(tmp_path, cambio))


def test_politicas_inexistentes_o_mal_formadas(tmp_path):
    with pytest.raises(ValueError):
        cargar_politicas(tmp_path / "no-existe.json")
    (tmp_path / "roto.json").write_text("{", encoding="utf-8")
    with pytest.raises(ValueError):
        cargar_politicas(tmp_path / "roto.json")


def test_dias_de_traslado_con_y_sin_tilde(tmp_path):
    p = cargar_politicas(_politicas_con(tmp_path, lambda d: d["traslado"].update(dias_semana=["miércoles", "sabado"])))
    assert p.traslado.dias_semana_iso() == {2, 5}
