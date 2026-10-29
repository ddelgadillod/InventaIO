"""INV-64 e INV-65 — Lista de inventario sin base: el semáforo inválido da 422 y la
consulta ordena primero lo que se vende, con ventas_30d y desempate estable.
La prueba contra la bodega real está en test_inventario_orden_integracion.py."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from core.semaforo import SEMAFORO_CONDICION
from core.ubicaciones import SQL_UBICACIONES
from inventario.router import SQL_ORDEN_INVENTARIO, SQL_VENTAS
from tests.conftest import usuario

UBICACIONES = [SimpleNamespace(id_sucursal=i, nombre=n, tipo=t) for i, n, t in
               [(1, "PRINCIPAL", "principal"), (2, "LA 21", "estandar"), (3, "GLORIETA", "estandar"),
                (5, "BODEGA_CENTRAL", "bodega_central")]]
FILA = SimpleNamespace(id_producto=1, nombre="BIANCHI MINI BOMBON * 30", categoria="Confitería", es_perecedero=False,
                       se_vende_por_kilo=False, sucursal="GLORIETA", id_sucursal=3, tipo_ubicacion="sucursal",
                       stock_disponible=0, stock_bodega=0, stock_minimo=1, stock_maximo=3, punto_reorden=1,
                       dias_cobertura=0, semaforo="critico", ventas_30d=13, fecha="2025-12-31")


class Respuesta:
    def __init__(self, filas=(), escalar=None):
        self.filas, self.escalar = list(filas), escalar

    def fetchall(self):
        return self.filas

    def fetchone(self):
        return self.filas[0] if self.filas else None

    def scalar(self):
        return self.escalar


class BodegaFalsa:
    def __init__(self):
        self.consultas = []

    def execute(self, sql, params=None):
        texto = str(sql)
        self.consultas.append((texto, params))
        if sql is SQL_UBICACIONES:
            return Respuesta(UBICACIONES)
        if "ORDER BY t.fecha DESC" in texto:
            return Respuesta([SimpleNamespace(fecha="2025-12-31")])
        if "COUNT(*)" in texto:
            return Respuesta(escalar=1)
        return Respuesta([FILA])


@pytest.fixture()
def api():
    from auth.dependencies import get_current_user
    from core.database import get_db
    from main import app

    db = BodegaFalsa()
    app.dependency_overrides.update({get_current_user: lambda: usuario("gerente"), get_db: lambda: db})
    with TestClient(app) as http:
        yield SimpleNamespace(http=http, db=db)
    app.dependency_overrides.clear()


@pytest.mark.parametrize("valor", ["xx", "rojo", "CRITICO", ""])
def test_semaforo_invalido_da_422(api, valor):                       # INV-64
    r = api.http.get("/api/consulta/inventario", params={"semaforo": valor})
    assert r.status_code == 422 and "critico" in r.text
    assert not api.db.consultas                                      # no llega a la bodega


def test_semaforo_valido_y_orden_por_venta_reciente(api):          # INV-65
    r = api.http.get("/api/consulta/inventario", params={"semaforo": "critico", "sucursal_id": 3, "page_size": 10})
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert (item["nombre_producto"], item["ventas_30d"]) == ("BIANCHI MINI BOMBON * 30", 13.0)
    sql, params = next((q, p) for q, p in api.db.consultas if "LIMIT :limit" in q)
    assert SEMAFORO_CONDICION["critico"] in sql and f"ORDER BY {SQL_ORDEN_INVENTARIO}" in sql
    assert "NOT fv.es_devolucion" in sql and params["fecha"] == "2025-12-31"


def test_el_orden_pone_primero_lo_que_se_vende_y_desempata():
    assert SQL_ORDEN_INVENTARIO == (f"({SQL_VENTAS} > 0) DESC, fi.dias_cobertura ASC, {SQL_VENTAS} DESC, "
                                    "p.nombre ASC, fi.id_sucursal ASC")    # el nombre y la sucursal: paginación estable
    assert "v30_red" in SQL_VENTAS                                         # la Bodega, con las ventas de la red
