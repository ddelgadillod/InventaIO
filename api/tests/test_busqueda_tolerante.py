"""INV-72 (recibido de INV-82, decisión 5 y T4) — Búsqueda de productos tolerante a errores de escritura, sin Postgres."""
from collections import Counter
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from core import busqueda_tolerante as bt
from tests.conftest import usuario

NOMBRES = [("ARROZ DIANA *500 GR", "ARROZ"), ("ARROZ ZULIA *500 GR", "ARROZ"), ("AV TARRO INST *400GR", "AVENAS"),
           ("AZÚCAR MANUELITA *1 LB", "AZUCAR"), ("PANELA MI CAÑITA", "PANELA"), ("LECHE ENTERA *1100ML", "LACTEOS")]
VOCABULARIO = bt.contar_palabras(NOMBRES)


def test_vocabulario_sin_tildes_y_con_frecuencia():
    assert VOCABULARIO["arroz"] == 2 and VOCABULARIO["azucar"] == 1 and VOCABULARIO["canita"] == 1
    assert "gr" not in VOCABULARIO and "500" not in VOCABULARIO      # cortas y números no cuentan


@pytest.mark.parametrize("busqueda,corregida", [
    ("arrox", "arroz"),                   # empata en parecido con «tarro»: gana la misma primera letra
    ("ARROX * 500 g", "arroz * 500 g"),   # el resto de la búsqueda queda igual
    ("pamela", "panela"),
    ("azucr", "azucar"),
    ("lehce entera", "leche entera"),
])
def test_corrige_una_letra(busqueda, corregida):
    assert bt.corregir(busqueda, VOCABULARIO) == corregida


@pytest.mark.parametrize("busqueda", ["arroz", "Azúcar", "xqzw", "500 gr", "P626"])
def test_no_toca_palabras_que_existen_ni_inventa(busqueda):
    assert bt.corregir(busqueda, VOCABULARIO) is None


def test_desempate_por_frecuencia():
    vocabulario = Counter({"mango": 1, "manto": 9})     # el mismo parecido y la misma primera letra
    assert bt.mas_parecida("manxo", vocabulario) == "manto"


# ── Endpoint con una sesión falsa ───────────────────

def _producto(codigo, nombre):
    return NS(id_producto=1, codigo_item=codigo, nombre=nombre, familia="ARROZ", clase=None, categoria="Arroz",
              es_perecedero=False, unidad_medida="g", precio_base=2500.0, costo_base=2000.0, margen_pct=20.0,
              iva_pct=0.0, se_vende_por_kilo=False)


class Resultado:
    def __init__(self, filas):
        self.filas = filas

    def fetchall(self):
        return self.filas

    def scalar(self):
        return self.filas[0]


class SesionFalsa:
    """El catálogo de NOMBRES: busca con ILIKE a mano y guarda cada búsqueda hecha."""

    def __init__(self):
        self.busquedas = []

    def execute(self, sql, params=None):
        texto = str(sql)
        if "pg_stat_user_tables" in texto:
            return Resultado([1])
        if texto.strip() == str(bt.SQL_NOMBRES):
            return Resultado(NOMBRES)
        patron = params["busqueda"].strip("%").lower()
        hallados = [_producto(f"P{i}", n) for i, (n, _) in enumerate(NOMBRES) if patron in n.lower()]
        if "COUNT(*)" in texto:
            self.busquedas.append(patron)
            return Resultado([len(hallados)])
        return Resultado(hallados)

    def close(self):
        pass


@pytest.fixture()
def cliente(monkeypatch):
    from auth.dependencies import get_current_user
    from core.database import get_db
    from main import app

    monkeypatch.setattr(bt, "_vocabulario", None)
    sesion = SesionFalsa()
    app.dependency_overrides.update({get_current_user: lambda: usuario("gerente"), get_db: lambda: sesion})
    with TestClient(app) as http:
        yield http, sesion
    app.dependency_overrides.clear()


def test_endpoint_corrige_solo_si_no_encuentra(cliente):
    http, sesion = cliente
    body = http.get("/api/consulta/productos", params={"busqueda": "arrox", "tolerante": "true"}).json()
    assert body["busqueda_corregida"] == "arroz" and body["total"] == 2
    assert [i["nombre"] for i in body["items"]] == ["ARROZ DIANA *500 GR", "ARROZ ZULIA *500 GR"]
    assert sesion.busquedas == ["arrox", "arroz"]


def test_endpoint_sin_tolerante_no_corrige(cliente):
    http, sesion = cliente
    body = http.get("/api/consulta/productos", params={"busqueda": "arrox"}).json()
    assert body["total"] == 0 and body["busqueda_corregida"] is None and sesion.busquedas == ["arrox"]


def test_endpoint_con_resultados_no_corrige(cliente):
    http, sesion = cliente
    body = http.get("/api/consulta/productos", params={"busqueda": "arroz", "tolerante": "true"}).json()
    assert body["total"] == 2 and body["busqueda_corregida"] is None and sesion.busquedas == ["arroz"]
