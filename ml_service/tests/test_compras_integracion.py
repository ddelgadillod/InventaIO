"""INV-21 — Compras contra la bodega REAL en Postgres y los modelos reales (se
salta si no hay conexión o la bodega está vacía).

Corre el catálogo completo una vez (fixture de módulo), mide su tiempo y
cuenta las consultas: INV-21 solo agrega la lectura de las marcas de producto
a las de INV-22. Contrasta cada línea con el balance de /api/transferencias y
verifica los ejemplos de docs/INV-21-requerimientos.md (foto al 2025-12-31).
"""
import math
import time

import pytest
from sqlalchemy import event

from compras.motor import recomendar_compras
from compras.politicas import cargar_politicas_compras
from core.config import get_settings
from transferencias.motor import recomendar_transferencias
from transferencias.politicas import cargar_politicas

pytestmark = pytest.mark.bodega

MAX_CONSULTAS_CATALOGO = 11          # las 10 de INV-22 más las marcas de producto
FOTO_DE_LOS_EJEMPLOS = "2025-12-31"


@pytest.fixture(scope="module")
def politicas():
    s = get_settings()
    return cargar_politicas_compras(s.POLITICAS_COMPRAS_PATH), cargar_politicas(s.POLITICAS_TRANSFERENCIAS_PATH)


@pytest.fixture(scope="module")
def catalogo(bodega_real, modelo_loader, politicas):
    compras, traslados = politicas
    bodega_real._calendario = None                  # que el conteo incluya el calendario
    consultas = []

    def contar(*args, **kwargs):
        consultas.append(1)

    event.listen(bodega_real.engine, "before_cursor_execute", contar)
    inicio = time.perf_counter()
    try:
        resultado = recomendar_compras(bodega_real, modelo_loader, compras, traslados)
    finally:
        event.remove(bodega_real.engine, "before_cursor_execute", contar)
    segundos = time.perf_counter() - inicio
    print(f"\nINV-21 catálogo completo: {resultado['resumen']} en {segundos:.1f} s con {len(consultas)} consultas")
    return resultado, len(consultas), segundos


def test_catalogo_completo_lee_la_bodega_por_lotes(catalogo):
    resultado, consultas, _ = catalogo
    assert consultas <= MAX_CONSULTAS_CATALOGO, f"{consultas} consultas: se está consultando par por par"
    assert resultado["resumen"]["lineas"] == len(resultado["compras"]) > 0


def test_perecederos_y_frio_nunca_se_compran_para_la_bodega(catalogo, bodega_real):
    resultado, _, _ = catalogo
    productos = bodega_real.productos(sorted({c["producto_id"] for c in resultado["compras"]}))
    for c in resultado["compras"]:
        p = productos[c["producto_id"]]
        directo = bool(p["es_perecedero_estricto"] or p["requiere_frio"])
        assert (c["tipo_destino"] == "sucursal") == directo, c
        assert c["grupo"] == ("semanal" if directo else "quincenal")
        assert c["cantidad"] >= 1


def test_cada_linea_sale_del_balance_de_transferencias(catalogo, bodega_real, modelo_loader, politicas):
    """Recalcula aparte una muestra de líneas con el balance de INV-22 y las
    fórmulas de la especificación."""
    resultado, _, _ = catalogo
    compras, traslados = politicas
    muestra = resultado["compras"][::max(1, len(resultado["compras"]) // 20)][:20]
    balance = recomendar_transferencias(bodega_real, modelo_loader, traslados,
                                        productos=sorted({c["producto_id"] for c in muestra}))["balance"]
    fila = {(b["producto_id"], b["sucursal"]): b for b in balance}
    plazo = {(p["grupo"], p["tipo_destino"]): p["dias_cubiertos"] for p in resultado["calendario"]}
    for c in muestra:
        P = plazo[(c["grupo"], c["tipo_destino"])]
        necesidad = 0.0
        for d in c["detalle"]:
            b = fila[(c["producto_id"], d["sucursal"])]
            posicion = max(b["stock"], 0) + b["recibido"]
            assert (d["posicion"], d["q50"], d["limite_superior"]) == (round(posicion, 2), b["q50"],
                                                                      b["limite_superior"])
            assert posicion < b["q50"] * P / 15                                  # B4
            necesidad += max(b["limite_superior"], b["q50"]) * P / 15 - posicion  # B5
        neto = necesidad - (c["sobrante_bodega"] or 0.0)
        assert c["cantidad"] == max(math.ceil(neto - 1e-9), compras.minimo_linea), c


def test_alertas_son_las_filas_negativas_de_la_foto(catalogo, bodega_real):
    resultado, _, _ = catalogo
    foto = bodega_real.inventario(resultado["fecha_inventario"])
    negativas = {(f["codigo_item"], f["sucursal"]) for f in foto if f["stock"] < 0}
    assert {(a["producto_id"], a["sucursal"]) for a in resultado["alertas"]} == negativas


def test_ejemplos_de_la_especificacion(app_client_real):
    r = app_client_real.post("/api/compras", json={"productos": ["P1632", "00380", "P3937", "P4650"]})
    assert r.status_code == 200, r.text
    body = r.json()
    if body["fecha_inventario"] != FOTO_DE_LOS_EJEMPLOS:
        pytest.skip(f"los ejemplos son de la foto al {FOTO_DE_LOS_EJEMPLOS}")
    linea = {(c["producto_id"], c["destino"]): c for c in body["compras"]}
    huevos = linea[("P1632", "PRINCIPAL")]
    assert (huevos["grupo"], huevos["cantidad"], huevos["urgencia"], huevos["llega_tarde"]) == ("semanal", 4735,
                                                                                               "urgente", True)
    durazno = linea[("00380", "BODEGA_CENTRAL")]
    assert (durazno["necesidad"], durazno["sobrante_bodega"], durazno["cantidad"]) == (101.28, 49.0, 53)
    assert [(x["producto_id"], x["sobrante_bodega"]) for x in body["cubrir_con_traslado"]] == [("P3937", 2757.0)]
    assert ("P4650", "LA 21", "compra_urgente") in {(a["producto_id"], a["sucursal"], a["accion"])
                                                     for a in body["alertas"]}
    quincenal = next(p for p in body["calendario"] if p["grupo"] == "quincenal")
    assert (quincenal["fecha_pedido"], quincenal["cubre_hasta"], quincenal["dias_cubiertos"]) == ("2026-01-02",
                                                                                                  "2026-01-23", 22)
