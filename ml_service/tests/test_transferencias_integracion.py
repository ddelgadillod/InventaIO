"""INV-22 — Transferencias contra la bodega REAL en Postgres y los modelos
reales (se salta si no hay conexión o la bodega está vacía).

Corre el catálogo completo una vez (fixture de módulo), mide su tiempo y
cuenta las consultas a la bodega: debe leerla por lotes, nunca una consulta
por par. Contrasta el balance con /api/predict y con dw.fact_inventario, y
verifica un escenario real Bodega -> sucursal recalculándolo aparte.
"""
import math
import time

import pytest
from sqlalchemy import event, text

from core.config import get_settings
from transferencias.motor import recomendar_transferencias
from transferencias.politicas import cargar_politicas

pytestmark = pytest.mark.bodega

MAX_CONSULTAS_CATALOGO = 10
N_MUESTRA = 15


@pytest.fixture(scope="module")
def catalogo(bodega_real, modelo_loader):
    politicas = cargar_politicas(get_settings().POLITICAS_TRANSFERENCIAS_PATH)
    bodega_real._calendario = None                  # que el conteo incluya el calendario
    consultas = []

    def contar(*args, **kwargs):
        consultas.append(1)

    event.listen(bodega_real.engine, "before_cursor_execute", contar)
    inicio = time.perf_counter()
    try:
        resultado = recomendar_transferencias(bodega_real, modelo_loader, politicas)
    finally:
        event.remove(bodega_real.engine, "before_cursor_execute", contar)
    segundos = time.perf_counter() - inicio
    print(f"\nINV-22 catálogo completo: {resultado['resumen']} en {segundos:.1f} s con {len(consultas)} consultas")
    return resultado, len(consultas), segundos


def _muestra(filas: list, n: int) -> list:
    paso = max(1, len(filas) // n)
    return filas[::paso][:n]


def test_catalogo_completo_lee_la_bodega_por_lotes(catalogo, bodega_real):
    resultado, consultas, _ = catalogo
    assert consultas <= MAX_CONSULTAS_CATALOGO, f"{consultas} consultas: se está consultando par por par"
    with bodega_real.engine.connect() as con:
        productos_en_foto = con.execute(text("""
            SELECT COUNT(DISTINCT fi.id_producto) FROM dw.fact_inventario fi
            JOIN dw.dim_tiempo t ON t.id_tiempo = fi.id_tiempo
            WHERE t.fecha = (SELECT MAX(t2.fecha) FROM dw.fact_inventario f2 JOIN dw.dim_tiempo t2 ON t2.id_tiempo = f2.id_tiempo)
        """)).scalar()
    assert resultado["resumen"]["productos"] == productos_en_foto
    # A6 / P8: la foto y la última venta cargada son del mismo día
    assert resultado["fecha_inventario"] == resultado["fecha_pronostico"]


def test_pronostico_del_balance_coincide_con_predict(catalogo, app_client_real):
    resultado, _, _ = catalogo
    con_pronostico = [b for b in resultado["balance"] if b["q50"] is not None]
    for b in _muestra(con_pronostico, N_MUESTRA):
        r = app_client_real.post("/api/predict", json={"producto_id": b["producto_id"], "sucursal_id": b["sucursal"],
                                                       "horizonte": 15})
        assert r.status_code == 200, r.text
        body = r.json()
        assert (body["prediccion_q50"], body["intervalo_confianza"]["limite_superior"], body["rama"]) == \
            (b["q50"], b["limite_superior"], b["rama"]), b
        assert body["fecha_features"] == resultado["fecha_pronostico"]


def test_stock_del_balance_coincide_con_fact_inventario(catalogo, bodega_real):
    resultado, _, _ = catalogo
    foto = {(f["codigo_item"], f["sucursal"]): f["stock"]
            for f in bodega_real.inventario(resultado["fecha_inventario"])}
    muestra = _muestra([b for b in resultado["balance"] if (b["producto_id"], b["sucursal"]) in foto], 200)
    assert muestra
    for b in muestra:
        assert b["stock"] == foto[(b["producto_id"], b["sucursal"])]
    # Las alertas de stock negativo son exactamente las filas negativas de la foto
    negativas = {clave for clave, s in foto.items() if s < 0}
    alertas = {(a["producto_id"], a["sucursal"]) for a in resultado["alertas"] if a["tipo"] == "stock_negativo"}
    assert alertas == negativas


def test_escenario_real_de_la_bodega_a_una_sucursal(catalogo, bodega_real, app_client_real):
    """Recalcula aparte un traslado real Bodega -> sucursal: stock de la foto,
    pronóstico de /api/predict y las fórmulas de la especificación."""
    resultado, _, _ = catalogo
    desde_bodega = [t for t in resultado["traslados"]
                    if t["origen"] == "BODEGA_CENTRAL" and t["urgencia"] != "vigilancia"]
    assert desde_bodega, "ningún traslado desde la Bodega en el catálogo real"
    t = max(desde_bodega, key=lambda t: (t["cantidad"], t["producto_id"]))
    foto = {(f["codigo_item"], f["sucursal"]): f["stock"]
            for f in bodega_real.inventario(resultado["fecha_inventario"], [t["producto_id"]])}
    stock_bodega = foto[(t["producto_id"], "BODEGA_CENTRAL")]
    stock_destino = max(foto.get((t["producto_id"], t["destino"]), 0.0), 0.0)
    pred = app_client_real.post("/api/predict", json={"producto_id": t["producto_id"], "sucursal_id": t["destino"],
                                                      "horizonte": 15}).json()
    q50 = pred["prediccion_q50"]
    deficit = q50 - stock_destino
    assert 6 <= t["cantidad"] <= stock_bodega                     # P3, P11
    assert t["cantidad"] <= math.floor(deficit + 0.01)            # nunca más que el déficit
    assert t["dias_hasta_agotarse"] == round(stock_destino / (q50 / 15), 1)
    destino = next(b for b in resultado["balance"]
                   if (b["producto_id"], b["sucursal"]) == (t["producto_id"], t["destino"]))
    assert destino["estado"] == "destino"
    assert destino["recibido"] >= t["cantidad"]


def test_nada_entra_a_la_bodega_ni_sale_de_pares_excluidos(catalogo):
    resultado, _, _ = catalogo
    estado = {(b["producto_id"], b["sucursal"]): b["estado"] for b in resultado["balance"]}
    for t in resultado["traslados"]:
        assert t["destino"] != "BODEGA_CENTRAL"
        assert estado[(t["producto_id"], t["origen"])] in ("bodega", "origen")
        assert estado[(t["producto_id"], t["destino"])] in ("destino", "vigilancia")
        assert t["cantidad"] >= 6


def test_pronostico_en_lote_igual_al_del_par_con_datos_reales(bodega_real, modelo_loader):
    """200 pares reales al azar (casi todos intermitentes, como el catálogo) más
    uno conocido de cada rama suave: el lote del catálogo completo da
    exactamente el mismo pronóstico que /api/predict par a par."""
    import pandas as pd

    from prediccion.features import HistoriaInsuficiente
    from prediccion.servicio import PronosticadorNivel1, pronosticar_par

    calendario = bodega_real.calendario()
    fecha = calendario.ultima_fecha
    with bodega_real.engine.connect() as con:
        pares = [(f.codigo_item, f.sucursal) for f in con.execute(text("""
            SELECT codigo_item, sucursal FROM dw.v_ventas_diarias_netas
            WHERE tipo_sucursal IN ('principal', 'estandar')
            GROUP BY codigo_item, sucursal ORDER BY md5(codigo_item || sucursal) LIMIT 200
        """))]
    # huevos en GLORIETA (suave_perecedero) y arroz en PRINCIPAL (suave_no_perecedero)
    pares += [("P1632", "GLORIETA"), ("P3937", "PRINCIPAL")]
    productos = bodega_real.productos(sorted({c for c, _ in pares}))
    ventas = bodega_real.ventas_diarias_lote(sorted(productos), ["PRINCIPAL", "LA 21", "GLORIETA"], fecha)
    solicitudes = [(productos[c], s, ventas.get((c, s), pd.Series(dtype=float))) for c, s in pares]
    lote = PronosticadorNivel1(modelo_loader).pronosticar_lote(solicitudes, calendario, fecha)
    ramas = set()
    for (producto, sucursal, unidades), resultado in zip(solicitudes, lote):
        try:
            esperado = pronosticar_par(modelo_loader, producto, sucursal, unidades, calendario, fecha)
        except HistoriaInsuficiente:
            assert isinstance(resultado, HistoriaInsuficiente)
            continue
        assert resultado == esperado, (producto["codigo_item"], sucursal)
        ramas.add(resultado.rama)
    assert ramas == {"intermitente", "suave_perecedero", "suave_no_perecedero"}


def test_ventas_por_lote_iguales_a_las_del_par(bodega_real):
    import pandas as pd

    fecha = bodega_real.calendario().ultima_fecha
    lote = bodega_real.ventas_diarias_lote(["P1632", "P1805"], ["PRINCIPAL", "LA 21"], hasta=fecha)
    for codigo, sucursal in [("P1632", "PRINCIPAL"), ("P1632", "LA 21"), ("P1805", "LA 21")]:
        pd.testing.assert_series_equal(lote[(codigo, sucursal)], bodega_real.ventas_diarias(codigo, sucursal, fecha),
                                       check_freq=False)


def test_endpoint_con_bodega_real(app_client_real):
    r = app_client_real.post("/api/transferencias", json={"productos": ["P1632"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["politicas"]["version"] >= 1
    assert {b["sucursal"] for b in body["balance"]} >= {"PRINCIPAL", "LA 21", "GLORIETA"}
