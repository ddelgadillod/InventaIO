"""INV-72 (recibido de INV-82) — /api/reportes/ventas/analisis y la búsqueda tolerante contra la bodega real (operación al
30-sep-2026, venta sin IVA): las cifras se comparan con sumas a mano sobre dw.fact_ventas, con la misma regla del endpoint (sin
devoluciones). Se salta sin Postgres o sin el seed. Correr dentro del contenedor:
docker exec <contenedor del api> python -m pytest -m integracion tests/test_analisis_ventas_integracion.py"""
from itertools import combinations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from core.database import SessionLocal
from reportes.analisis import DIMENSIONES

pytestmark = pytest.mark.integracion
PRINCIPAL, GLORIETA = 1, 3
GRUPO = ["P626", "P627"]


@pytest.fixture(scope="module")
def http():
    from main import app

    with TestClient(app) as client:
        yield client


def _token(http, email: str) -> dict:
    try:
        r = http.post("/api/auth/login", json={"email": email, "password": "admin123"})
    except Exception as exc:                                  # Postgres caído
        pytest.skip(f"sin bodega: {exc}")
    if r.status_code != 200:
        pytest.skip(f"usuario de prueba {email} no disponible (falta el seed)")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def tok(http):
    return {"gerente": _token(http, "gerente@inventaio.co"), "principal": _token(http, "admin.principal@inventaio.co")}


def _analisis(http, auth, codigo=200, **params):
    r = http.get("/api/reportes/ventas/analisis", params=params, headers=auth)
    assert r.status_code == codigo, r.text
    return r.json()


def _suma(condicion: str = "", **params) -> tuple[float, float]:
    """(unidades, venta) sin devoluciones con la condición dada sobre v, t y p."""
    with SessionLocal() as db:
        fila = db.execute(text(
            "SELECT COALESCE(SUM(v.cantidad), 0), COALESCE(SUM(v.valor_total), 0) FROM dw.fact_ventas v "
            "JOIN dw.dim_producto p ON p.id_producto = v.id_producto JOIN dw.dim_tiempo t ON t.id_tiempo = v.id_tiempo "
            f"WHERE NOT v.es_devolucion {condicion}"), params).one()
    return float(fila[0]), float(fila[1])


def _distintos(expresion: str, condicion: str = "", **params) -> int:
    with SessionLocal() as db:
        return db.execute(text(
            f"SELECT COUNT(DISTINCT ({expresion})) FROM dw.fact_ventas v "
            "JOIN dw.dim_producto p ON p.id_producto = v.id_producto JOIN dw.dim_tiempo t ON t.id_tiempo = v.id_tiempo "
            "JOIN dw.dim_sucursal s ON s.id_sucursal = v.id_sucursal "
            f"WHERE NOT v.es_devolucion {condicion}"), params).scalar()


DE_2025 = "AND t.anio = 2025"
PEDIDAS = [[d] for d in DIMENSIONES] + [list(par) for par in combinations(DIMENSIONES, 2)]


@pytest.mark.parametrize("dims", PEDIDAS, ids=lambda d: "-".join(d))
def test_cada_dimension_y_cada_par_suman_lo_mismo(http, tok, dims):
    body = _analisis(http, tok["gerente"], dimensiones=",".join(dims), anios="2025")
    unidades, venta = _suma(DE_2025)
    assert body["total"]["cantidad"] == pytest.approx(unidades)
    assert body["total"]["valor_total"] == pytest.approx(venta)
    combinada = " || '|' || ".join(f"({DIMENSIONES[d]})" for d in dims)
    assert body["filas_totales"] == _distintos(combinada, DE_2025)
    if body["filas_totales"] <= 200:
        assert sum(f["valor_total"] for f in body["filas"]) == pytest.approx(venta)


def test_mismo_mes_en_varios_anios_por_sucursal(http, tok):
    body = _analisis(http, tok["gerente"], dimensiones="anio,sucursal", meses="9", anios="2024,2025,2026")
    assert {f["dimensiones"]["anio"] for f in body["filas"]} == {"2024", "2025", "2026"}
    fila = next(f for f in body["filas"] if f["dimensiones"] == {"anio": "2025", "sucursal": "PRINCIPAL"})
    unidades, venta = _suma("AND t.anio = 2025 AND t.mes = 9 AND v.id_sucursal = :s", s=PRINCIPAL)
    assert fila["cantidad"] == pytest.approx(unidades) and fila["valor_total"] == pytest.approx(venta)


def test_grupo_de_productos_por_mes_y_el_mejor_primero(http, tok):
    body = _analisis(http, tok["gerente"], dimensiones="mes", productos=",".join(GRUPO), orden="cantidad", limite=3)
    assert [p["codigo"] for p in body["productos"]] == GRUPO
    unidades, _ = _suma("AND p.codigo_item = ANY(:g)", g=GRUPO)
    assert body["total"]["cantidad"] == pytest.approx(unidades) and body["filas_totales"] > 3
    cantidades = [f["cantidad"] for f in body["filas"]]
    assert cantidades == sorted(cantidades, reverse=True) and len(cantidades) == 3
    mejor = body["filas"][0]["dimensiones"]["mes"]
    assert cantidades[0] == pytest.approx(_suma("AND p.codigo_item = ANY(:g) AND TO_CHAR(t.fecha, 'YYYY-MM') = :m",
                                                g=GRUPO, m=mejor)[0])


def test_comparar_con_el_anio_anterior(http, tok):
    body = _analisis(http, tok["gerente"], dimensiones="sucursal", meses="9", anios="2026", comparar="true")
    fila = next(f for f in body["filas"] if f["dimensiones"]["sucursal"] == "GLORIETA")
    _, antes = _suma("AND t.anio = 2025 AND t.mes = 9 AND v.id_sucursal = :s", s=GLORIETA)
    assert fila["anterior"]["valor_total"] == pytest.approx(antes)
    assert fila["variacion_valor_pct"] == pytest.approx(100 * (fila["valor_total"] - antes) / antes, abs=0.01)


def test_margen_sin_iva_estable_por_anio(http, tok):
    """INV-82: con la venta sin IVA, el margen no salta entre años con y sin IVA en el reporte de origen.
    Sin cifras del negocio: solo la distancia entre el mayor y el menor."""
    margenes = [f["margen_pct"] for f in _analisis(http, tok["gerente"], dimensiones="anio")["filas"]]
    assert max(margenes) - min(margenes) < 2.5


def test_admin_de_sucursal_solo_la_suya(http, tok):
    body = _analisis(http, tok["principal"], dimensiones="sucursal", anios="2025")
    assert [f["dimensiones"]["sucursal"] for f in body["filas"]] == ["PRINCIPAL"] and body["sucursal"] == "PRINCIPAL"
    _analisis(http, tok["principal"], 403, dimensiones="anio", sucursal_id=GLORIETA)


def test_busqueda_tolerante(http, tok):
    r = http.get("/api/consulta/productos", params={"busqueda": "arrox", "tolerante": "true"}, headers=tok["gerente"])
    body = r.json()
    assert body["busqueda_corregida"] == "arroz" and body["total"] > 0
    assert all("ARROZ" in i["nombre"] or "ARROZ" in i["familia"] for i in body["items"])
    sin = http.get("/api/consulta/productos", params={"busqueda": "arrox"}, headers=tok["gerente"]).json()
    assert sin["total"] == 0 and sin["busqueda_corregida"] is None
