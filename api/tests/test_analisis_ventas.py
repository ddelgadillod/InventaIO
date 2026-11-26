"""INV-72 (recibido de INV-82, decisión 3 y T3) — /api/reportes/ventas/analisis sin Postgres.

Las piezas puras de reportes/analisis.py (validación, SQL, orden, comparación con el año anterior) y el endpoint con una sesión
falsa que responde según la consulta. Las cifras contra la bodega real están en test_analisis_ventas_integracion.py."""
from datetime import date
from types import SimpleNamespace as NS

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from reportes import analisis
from tests.conftest import usuario

# ── Piezas puras ────────────────────────────────────


@pytest.mark.parametrize("pedidas,esperadas", [
    (["anio"], ["anio"]),
    (["anio,sucursal"], ["anio", "sucursal"]),
    (["Mes", " producto "], ["mes", "producto"]),
])
def test_dimensiones_validas(pedidas, esperadas):
    assert analisis.normalizar_dimensiones(pedidas) == esperadas


@pytest.mark.parametrize("pedidas,texto", [
    ([], "una o dos"),
    (["anio,mes,sucursal"], "una o dos"),
    (["dia"], "no válida: dia"),
    (["anio", "anio"], "repetir"),
])
def test_dimensiones_invalidas_dan_422(pedidas, texto):
    with pytest.raises(HTTPException) as e:
        analisis.normalizar_dimensiones(pedidas)
    assert e.value.status_code == 422 and texto in e.value.detail


def test_meses_y_anios():
    assert analisis.normalizar_enteros(["9", "9,10"], "meses", 1, 12) == [9, 10]
    assert analisis.normalizar_enteros(None, "meses", 1, 12) is None
    for malos in (["13"], ["0"], ["sep"]):
        with pytest.raises(HTTPException) as e:
            analisis.normalizar_enteros(malos, "meses", 1, 12)
        assert e.value.status_code == 422


def test_productos_sin_repetidos_y_con_tope():
    assert analisis.normalizar_productos(["P2,P1", "P2"]) == ["P2", "P1"]
    assert analisis.normalizar_productos(None) is None
    with pytest.raises(HTTPException) as e:
        analisis.normalizar_productos([",".join(f"P{i}" for i in range(51))])
    assert e.value.status_code == 422


def test_orden_y_sentido_por_defecto():
    assert analisis.normalizar_orden("natural", None) == ("natural", True)
    assert analisis.normalizar_orden("valor", None) == ("valor", False)        # una medida: de mayor a menor
    assert analisis.normalizar_orden("Margen_pct", True) == ("margen_pct", True)
    with pytest.raises(HTTPException):
        analisis.normalizar_orden("precio", None)


def test_un_anio_antes_y_despues():
    assert analisis.un_anio_antes(date(2026, 9, 30)) == date(2025, 9, 30)
    assert analisis.un_anio_antes(date(2024, 2, 29)) == date(2023, 2, 28)
    assert analisis.un_anio_despues("anio", "2025") == "2026"
    assert analisis.un_anio_despues("mes", "2025-09") == "2026-09"
    assert analisis.un_anio_despues("trimestre", "2025-T3") == "2026-T3"
    assert analisis.un_anio_despues("sucursal", "PRINCIPAL") == "PRINCIPAL"


def test_sql_con_y_sin_limite():
    con = analisis.sql_analisis(["anio", "sucursal"], " AND t.mes = ANY(:meses)", "g.d0 ASC, g.d1 ASC")
    assert "TO_CHAR(t.fecha, 'YYYY') AS d0" in con and "s.nombre AS d1" in con
    assert "JOIN dw.dim_sucursal s" in con and "GROUP BY 1, 2" in con
    assert "COUNT(*) OVER () AS filas_totales" in con and "LIMIT :limite" in con
    assert "AND t.mes = ANY(:meses)" in con and "NOT v.es_devolucion" in con
    sin = analisis.sql_analisis(["producto"], "", None)
    assert "dim_sucursal" not in sin and "LIMIT" not in sin and "OVER" not in sin
    assert "MIN(p.nombre) AS producto_nombre" in sin


def test_sql_del_orden():
    assert analisis.orden_sql(["anio", "sucursal"], "natural", True) == "g.d0 ASC, g.d1 ASC"
    assert analisis.orden_sql(["mes"], "margen_pct", False) == (
        "(g.valor - g.costo) / NULLIF(g.valor, 0) DESC NULLS LAST, g.d0")


def _fila(*dims, cantidad=10.0, valor=1000.0, costo=850.0, transacciones=4, **extra):
    campos = {f"d{i}": d for i, d in enumerate(dims)}
    return NS(**campos, cantidad=cantidad, valor=valor, costo=costo, transacciones=transacciones, **extra)


def test_fila_con_el_anio_anterior():
    dims = ["anio", "sucursal"]
    previas = analisis.indexar_anteriores([_fila("2024", "PRINCIPAL", valor=800.0, cantidad=8.0)], dims)
    fila = analisis.armar_fila(_fila("2025", "PRINCIPAL"), dims, previas)
    assert fila["dimensiones"] == {"anio": "2025", "sucursal": "PRINCIPAL"}
    assert fila["margen"] == 150.0 and fila["margen_pct"] == 15.0
    assert fila["anterior"]["valor_total"] == 800.0
    assert fila["variacion_valor_pct"] == 25.0 and fila["variacion_cantidad_pct"] == 25.0
    # Sin fila el año anterior, no hay comparación
    sola = analisis.armar_fila(_fila("2025", "GLORIETA"), dims, previas)
    assert "anterior" not in sola


def test_fila_de_producto_y_sin_venta():
    fila = analisis.armar_fila(_fila("P1", valor=0.0, costo=0.0, producto_nombre="HUEVOS *UND", producto_por_kilo=False),
                               ["producto"], None)
    assert fila["producto_nombre"] == "HUEVOS *UND" and fila["unidad"] == "unidad"
    assert fila["margen_pct"] is None


# ── Endpoint con una sesión falsa ───────────────────

UBICACIONES = [NS(id_sucursal=1, nombre="PRINCIPAL", tipo="sucursal"), NS(id_sucursal=3, nombre="GLORIETA", tipo="sucursal"),
               NS(id_sucursal=5, nombre="BODEGA_CENTRAL", tipo="bodega_central")]
PRODUCTOS = {"P1": NS(codigo_item="P1", nombre="ARROZ ZULIA *500 GR", se_vende_por_kilo=False),
             "P2": NS(codigo_item="P2", nombre="ARROZ DIANA *500 GR", se_vende_por_kilo=False)}


class Resultado:
    def __init__(self, filas):
        self.filas = filas

    def fetchall(self):
        return self.filas

    def fetchone(self):
        return self.filas[0] if self.filas else None

    def scalar(self):
        return self.filas[0] if self.filas else None


class SesionFalsa:
    """Responde según el texto de la consulta y guarda cada consulta de análisis con sus parámetros."""

    def __init__(self, filas, previas=()):
        self.filas, self.previas, self.consultas = filas, list(previas), []

    def execute(self, sql, params=None):
        texto = str(sql)
        if "MIN(t.fecha) AS desde" in texto:
            return Resultado([NS(desde=date(2022, 1, 2), hasta=date(2026, 9, 30))])
        if "sin_terminal" in texto:
            return Resultado(UBICACIONES)
        if "codigo_item = ANY(:codigos)" in texto:
            return Resultado([PRODUCTOS[c] for c in params["codigos"] if c in PRODUCTOS])
        self.consultas.append((texto, params))
        return Resultado(self.filas if "WITH g AS" in texto else self.previas)

    def close(self):
        pass


def _con_totales(filas, kilo=False):
    total = dict(filas_totales=len(filas) + 3, total_cantidad=99.0, total_valor=10000.0, total_costo=8500.0,
                 total_transacciones=40, total_hay_kilo=kilo, total_hay_unidad=True)
    return [NS(**vars(f), hay_kilo=kilo, hay_unidad=True, **total) for f in filas]


@pytest.fixture()
def cliente():
    from auth.dependencies import get_current_user
    from core.database import get_db
    from main import app

    estado = {"usuario": usuario("gerente"), "sesion": SesionFalsa([])}
    app.dependency_overrides.update({get_current_user: lambda: estado["usuario"], get_db: lambda: estado["sesion"]})
    with TestClient(app) as http:
        yield http, estado
    app.dependency_overrides.clear()


def test_endpoint_mismo_mes_en_varios_anios(cliente):
    http, estado = cliente
    estado["sesion"] = SesionFalsa(_con_totales([_fila("2024", "PRINCIPAL"), _fila("2025", "PRINCIPAL")]))
    r = http.get("/api/reportes/ventas/analisis",
                 params={"dimensiones": "anio,sucursal", "meses": "9", "anios": "2024,2025"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dimensiones"] == ["anio", "sucursal"] and len(body["filas"]) == 2
    assert body["filas_totales"] == 5 and body["total"]["valor_total"] == 10000.0 and body["total"]["margen_pct"] == 15.0
    assert body["fecha_inicio"] == "2022-01-02" and body["fecha_fin"] == "2026-09-30"
    assert body["meses"] == [9] and body["anios"] == [2024, 2025] and body["sucursal"] is None
    assert body["orden"] == "natural" and body["ascendente"] is True and body["unidades_mixtas"] is False
    texto, params = estado["sesion"].consultas[0]
    assert params["meses"] == [9] and params["anios"] == [2024, 2025] and params["limite"] == 200
    assert "suc" not in params


def test_endpoint_admin_de_sucursal_ve_la_suya(cliente):
    http, estado = cliente
    estado["usuario"] = usuario("admin_sucursal", 1)
    estado["sesion"] = SesionFalsa(_con_totales([_fila("PRINCIPAL")]))
    body = http.get("/api/reportes/ventas/analisis", params={"dimensiones": "sucursal"}).json()
    assert body["sucursal"] == "PRINCIPAL" and estado["sesion"].consultas[0][1]["suc"] == 1
    r = http.get("/api/reportes/ventas/analisis", params={"dimensiones": "anio", "sucursal_id": 3})
    assert r.status_code == 403


def test_endpoint_grupo_de_productos_y_comparar(cliente):
    http, estado = cliente
    estado["sesion"] = SesionFalsa(
        _con_totales([_fila("P1", producto_nombre="ARROZ ZULIA *500 GR", producto_por_kilo=False)], kilo=True),
        previas=[_fila("P1", valor=500.0)])
    r = http.get("/api/reportes/ventas/analisis",
                 params={"dimensiones": "producto", "productos": "P1,P2", "anios": "2026", "orden": "valor",
                         "comparar": "true", "limite": 10})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [p["codigo"] for p in body["productos"]] == ["P1", "P2"] and body["unidades_mixtas"] is True
    assert body["filas"][0]["variacion_valor_pct"] == 100.0 and body["ascendente"] is False
    (_, actual), (texto_previo, previo) = estado["sesion"].consultas
    assert actual["prods"] == ["P1", "P2"] and actual["limite"] == 10
    assert previo["anios"] == [2025] and previo["codigos_filas"] == ["P1"]
    assert previo["fi"] == date(2021, 1, 2) and "LIMIT" not in texto_previo


def test_endpoint_errores(cliente):
    http, _ = cliente
    pedir = lambda **p: http.get("/api/reportes/ventas/analisis", params=p)   # noqa: E731
    assert pedir(dimensiones="anio", productos="P1,NO-EXISTE").status_code == 404
    assert pedir(dimensiones="dia").status_code == 422
    assert pedir(dimensiones="anio", orden="precio").status_code == 422
    assert pedir(dimensiones="anio", limite=201).status_code == 422
    assert pedir(dimensiones="anio", fecha_inicio="2026-01-01", fecha_fin="2025-01-01").status_code == 422
    assert pedir().status_code == 422


def test_endpoint_sin_filas(cliente):
    http, _ = cliente
    body = http.get("/api/reportes/ventas/analisis", params={"dimensiones": "anio", "comparar": "true"}).json()
    assert body["filas"] == [] and body["filas_totales"] == 0 and body["total"]["valor_total"] == 0
    assert body["total"]["margen_pct"] is None and body["unidades_mixtas"] is False
