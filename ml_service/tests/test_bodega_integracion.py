"""INV-20 — El servicio contra la bodega REAL en Postgres (se salta si no hay
conexión o la bodega está vacía).

Además del endpoint de punta a punta, contrasta la predicción con la demanda
que de verdad ocurrió: con `fecha_corte` en el pasado, el servicio predice
como lo habría hecho ese día y la bodega tiene los 15 días hábiles siguientes.
Son cotas de sanidad (el WAPE documentado en INV-17 dice cuánto error es
esperable), no una evaluación: la evaluación está en los notebooks 09-15.
Reemplaza al contraste anterior, que dependía de un parquet no versionado.
"""
import numpy as np
import pandas as pd
import pytest
from sqlalchemy import text

pytestmark = pytest.mark.bodega

DIAS_ANTES_DEL_ULTIMO_DATO = 60
N_PARES = 150


def _par_con_mas_ventas(bodega) -> tuple:
    with bodega.engine.connect() as con:
        fila = con.execute(text("""
            SELECT codigo_item, sucursal FROM dw.v_ventas_diarias_netas
            WHERE tipo_sucursal IN ('principal', 'estandar')
            GROUP BY codigo_item, sucursal ORDER BY COUNT(*) DESC, codigo_item LIMIT 1
        """)).first()
    return fila.codigo_item, fila.sucursal


def _pares_activos(bodega, desde, n: int) -> list:
    """Pares de sucursales físicas con venta en al menos 60 días desde `desde`,
    en un orden pseudoaleatorio pero reproducible."""
    with bodega.engine.connect() as con:
        filas = con.execute(text("""
            SELECT codigo_item, sucursal FROM dw.v_ventas_diarias_netas
            WHERE tipo_sucursal IN ('principal', 'estandar') AND fecha >= :desde
            GROUP BY codigo_item, sucursal HAVING COUNT(*) >= 60
            ORDER BY md5(codigo_item || sucursal) LIMIT :n
        """), {"desde": desde, "n": n}).all()
    return [(f.codigo_item, f.sucursal) for f in filas]


def test_health_con_bodega_real(app_client_real):
    assert app_client_real.get("/api/health").json()["bodega"] == "ok"


def test_predict_con_bodega_real_por_codigo_y_por_id(app_client_real, bodega_real):
    codigo, sucursal = _par_con_mas_ventas(bodega_real)
    r = app_client_real.post("/api/predict", json={"producto_id": codigo, "sucursal_id": sucursal, "horizonte": 15})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fecha_features"] == bodega_real.calendario().ultima_fecha.date().isoformat()
    assert body["prediccion_q50"] > 0
    r_id = app_client_real.post("/api/predict", json={"id_producto": body["id_producto"],
                                                      "id_sucursal": body["id_sucursal"], "horizonte": 15})
    assert r_id.json() == body


def test_prediccion_en_orden_de_magnitud_de_la_demanda_real(app_client_real, bodega_real):
    calendario = bodega_real.calendario()
    fecha_corte = calendario.habiles[-DIAS_ANTES_DEL_ULTIMO_DATO]
    ventana = calendario.proximos_habiles(fecha_corte, 15)
    razones = {}
    for codigo, sucursal in _pares_activos(bodega_real, fecha_corte - pd.Timedelta(days=365), N_PARES):
        r = app_client_real.post("/api/predict", json={"producto_id": codigo, "sucursal_id": sucursal, "horizonte": 15,
                                                       "fecha_corte": fecha_corte.date().isoformat()})
        if r.status_code == 404:      # sin historia suficiente a esa fecha
            continue
        assert r.status_code == 200, r.text
        body = r.json()
        assert 0 <= body["prediccion_q50"]
        real = bodega_real.ventas_diarias(codigo, sucursal, hasta=ventana[-1]).reindex(ventana, fill_value=0).sum()
        if real > 0:
            razones.setdefault(body["rama"], []).append(body["prediccion_q50"] / real)
    assert razones, "ningún par con demanda real para contrastar"
    for rama, valores in razones.items():
        mediana = float(np.median(valores))
        assert 0.2 <= mediana <= 5.0, (
            f"mediana de pred/real={mediana:.2f} en {rama} ({len(valores)} pares): el modelo estaría "
            "groseramente desviado de la demanda real, más allá del WAPE documentado")
