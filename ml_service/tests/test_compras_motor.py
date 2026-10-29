"""INV-21 — Motor de compras sobre una bodega en memoria con inventario y
pronósticos fijos (sin modelos). Un test por caso de la tabla "Casos de prueba"
de docs/INV-21-requerimientos.md.

Con la foto de BodegaFalsa (lunes 2025-06-30, cierre el 2025-07-04) y las
políticas del repo, los plazos son (ver test_compras_calendario.py):
- quincenal por la Bodega (lo seco): P = 22 días hábiles; llega a la sucursal
  a los 9 días hábiles de la foto;
- semanal directo (perecederos y frío): P = 12; llega a los 6.
"""
import json

import pandas as pd
import pytest

from compras.motor import recomendar_compras
from compras.politicas import PoliticasCompras, cargar_politicas_compras
from core.config import get_settings
from tests.conftest import BodegaFalsa, PronosticosFijos
from transferencias.motor import FotoSinVentas
from transferencias.politicas import cargar_politicas

POLITICAS = cargar_politicas_compras(get_settings().POLITICAS_COMPRAS_PATH)
POLITICAS_TRASLADOS = cargar_politicas(get_settings().POLITICAS_TRANSFERENCIAS_PATH)
BODEGA = "BODEGA_CENTRAL"


def politicas_con(cambio) -> PoliticasCompras:
    datos = json.loads(open(get_settings().POLITICAS_COMPRAS_PATH, encoding="utf-8").read())
    cambio(datos)
    return PoliticasCompras.model_validate(datos)


def escenario(stock: dict, pronosticos: dict, producto: str = "X1", politicas=None, bodega=None, **marcas) -> dict:
    """Corre el motor para un producto: `stock` {ubicación: stock},
    `pronosticos` {sucursal: (q50, límite superior)}."""
    bodega = bodega or BodegaFalsa()
    bodega.agregar_producto(producto, **marcas)
    for ubicacion, s in stock.items():
        bodega.agregar_stock(producto, ubicacion, s)
    fijos = PronosticosFijos({(producto, suc): v for suc, v in pronosticos.items()})
    return recomendar_compras(bodega, fijos, politicas or POLITICAS, POLITICAS_TRASLADOS, productos=[producto])


def lineas(r: dict) -> list:
    return [(c["destino"], c["cantidad"]) for c in r["compras"]]


def unica(r: dict) -> dict:
    assert len(r["compras"]) == 1, r["compras"]
    return r["compras"][0]


# ── Casos de la tabla de la especificación ─────────────────────────────────

def test_alcanza_hasta_el_pedido_siguiente_no_compra():
    r = escenario({"LA 21": 100}, {"LA 21": (30, 40)})               # punto de pedido 30 × 22/15 = 44
    assert r["compras"] == [] and r["cubrir_con_traslado"] == []


def test_cubre_15_dias_pero_no_el_plazo_compra_hasta_el_nivel():
    # stock = q50: INV-22 no ve déficit (equilibrio), pero no alcanza hasta el 23 de julio
    c = unica(escenario({"LA 21": 30}, {"LA 21": (30, 40)}))
    assert (c["destino"], c["tipo_destino"], c["grupo"]) == (BODEGA, "bodega_central", "quincenal")
    assert c["necesidad"] == 28.67                                     # 40 × 22/15 − 30
    assert c["cantidad"] == 29                                         # B6: hacia arriba
    assert (c["fecha_pedido"], c["fecha_llegada"], c["fecha_llegada_sucursal"]) == ("2025-07-02", "2025-07-08",
                                                                                      "2025-07-10")
    d = c["detalle"][0]
    assert (d["posicion"], d["punto_pedido"], d["nivel"], d["dias_hasta_agotarse"]) == (30, 44, 58.67, 15.0)
    assert (c["urgencia"], c["llega_tarde"], c["sobrante_bodega"]) == ("normal", False, 0)


def test_la_posicion_incluye_lo_recibido_en_traslados():
    # INV-22 manda los 10 de la Bodega a LA 21 (déficit 20); compras parte de 10
    c = unica(escenario({BODEGA: 10, "LA 21": 0}, {"LA 21": (20, 25)}))
    assert c["detalle"][0]["posicion"] == 10
    assert (c["necesidad"], c["sobrante_bodega"], c["cantidad"]) == (26.67, 0, 27)      # 25 × 22/15 − 10


def test_perecedero_va_directo_a_la_sucursal_cada_semana():
    c = unica(escenario({"LA 21": 0}, {"LA 21": (12, 15)}, es_perecedero_estricto=True))
    assert (c["destino"], c["tipo_destino"], c["grupo"], c["cantidad"]) == ("LA 21", "sucursal", "semanal", 12)
    assert (c["fecha_pedido"], c["fecha_llegada"], c["sobrante_bodega"]) == ("2025-07-01", "2025-07-07", None)


def test_frio_no_perecedero_va_directo_igual_que_el_perecedero():
    c = unica(escenario({"LA 21": 0}, {"LA 21": (12, 15)}, requiere_frio=True))
    assert (c["destino"], c["grupo"], c["cantidad"]) == ("LA 21", "semanal", 12)


def test_seco_en_dos_sucursales_una_sola_linea_para_la_bodega():
    c = unica(escenario({"LA 21": 0, "GLORIETA": 0}, {"LA 21": (15, 15), "GLORIETA": (30, 30)}))
    assert (c["destino"], c["cantidad"], c["necesidad"]) == (BODEGA, 66, 66)          # 22 + 44
    assert {d["sucursal"] for d in c["detalle"]} == {"LA 21", "GLORIETA"}


def test_sobrante_suficiente_en_la_bodega_no_compra():
    r = escenario({BODEGA: 100, "LA 21": 30}, {"LA 21": (30, 30)})
    assert r["compras"] == []
    cubrir = r["cubrir_con_traslado"]
    assert [(x["producto_id"], x["necesidad"], x["sobrante_bodega"]) for x in cubrir] == [("X1", 14, 100)]
    assert r["resumen"]["cubiertos_por_bodega"] == 1


def test_sobrante_parcial_compra_la_diferencia():
    c = unica(escenario({BODEGA: 10, "LA 21": 30}, {"LA 21": (30, 30)}))
    assert (c["necesidad"], c["sobrante_bodega"], c["cantidad"]) == (14, 10, 4)


def test_q50_cero_no_compra():
    assert escenario({"LA 21": 0}, {"LA 21": (0, 3)})["compras"] == []


def test_sin_pronostico_no_compra_y_se_cuenta():
    r = escenario({"LA 21": 5}, {})
    assert r["compras"] == [] and r["alertas"] == []
    assert r["resumen"]["pares_sin_pronostico"] == 1


def test_stock_negativo_con_pronostico_alerta_y_compra_urgente():
    r = escenario({"LA 21": -4}, {"LA 21": (15, 15)})
    assert [(a["sucursal"], a["tipo"], a["accion"], a["stock"]) for a in r["alertas"]] == [
        ("LA 21", "posible_inconsistencia_inventario", "compra_urgente", -4)]
    c = unica(r)
    assert (c["cantidad"], c["motivo"], c["urgencia"], c["llega_tarde"]) == (22, "stock_negativo", "urgente", True)
    assert c["detalle"][0]["posicion"] == 0                             # el stock negativo cuenta como 0


def test_stock_negativo_sin_pronostico_solo_alerta():
    r = escenario({BODEGA: -3, "LA 21": -4}, {})
    assert r["compras"] == []
    assert {(a["sucursal"], a["accion"]) for a in r["alertas"]} == {(BODEGA, "verificar_conteo"),
                                                                     ("LA 21", "verificar_conteo")}


def test_perecedero_con_qalfa_bajo_la_mediana_sube_hasta_la_mediana():
    # rama suave_perecedero: qα (20) < q50 (30); nivel = q50 × 12/15
    c = unica(escenario({"LA 21": 0}, {"LA 21": (30, 20, "suave_perecedero")}, es_perecedero_estricto=True))
    assert (c["detalle"][0]["nivel"], c["cantidad"]) == (24, 24)


def test_kilos_redondea_hacia_arriba_sin_descuento():
    c = unica(escenario({"LA 21": 0}, {"LA 21": (9, 9)}, es_perecedero_estricto=True, se_vende_por_kilo=True))
    assert (c["necesidad"], c["cantidad"], c["unidad"]) == (7.2, 8, "kg")


def test_kilos_en_la_bodega_descuentan_la_perdida_del_traslado():
    c = unica(escenario({BODEGA: 10, "LA 21": 30}, {"LA 21": (30, 30)}, se_vende_por_kilo=True))
    assert (c["sobrante_bodega"], c["cantidad"], c["unidad"]) == (9, 5, "kg")         # 14 − 10 × 0,9


def test_llega_tarde_y_orden_por_urgencia():
    r = escenario({"LA 21": 10, "GLORIETA": 2}, {"LA 21": (15, 15), "GLORIETA": (15, 15)},
                  es_perecedero_estricto=True)
    assert [(c["destino"], c["urgencia"], c["dias_hasta_agotarse"], c["llega_tarde"]) for c in r["compras"]] == [
        ("GLORIETA", "urgente", 2.0, True),                              # se agota antes del día 6
        ("LA 21", "alta", 10.0, False)]


def test_linea_de_la_bodega_toma_la_sucursal_mas_urgente():
    c = unica(escenario({"LA 21": 16, "GLORIETA": 1}, {"LA 21": (30, 30), "GLORIETA": (15, 15)}))
    assert (c["urgencia"], c["dias_hasta_agotarse"], c["llega_tarde"]) == ("urgente", 1.0, True)
    assert {d["sucursal"]: d["urgencia"] for d in c["detalle"]} == {"LA 21": "alta", "GLORIETA": "urgente"}


def test_cambiar_el_lead_time_cambia_el_plazo_y_la_cantidad():
    base = unica(escenario({"LA 21": 0}, {"LA 21": (15, 15)}, es_perecedero_estricto=True))
    largo = unica(escenario({"LA 21": 0}, {"LA 21": (15, 15)}, es_perecedero_estricto=True,
                            politicas=politicas_con(lambda d: d.update(lead_time_dias=10))))
    assert (base["cantidad"], base["fecha_llegada"]) == (12, "2025-07-07")      # P = 12
    assert (largo["cantidad"], largo["fecha_llegada"]) == (17, "2025-07-12")    # P = 17


def test_minimo_por_linea_sube_las_cantidades_pequenas():
    r = escenario({"LA 21": 0}, {"LA 21": (1.5, 1.5)}, es_perecedero_estricto=True)
    assert lineas(r) == [("LA 21", 2)]                                  # 1,2 hacia arriba
    r = escenario({"LA 21": 0}, {"LA 21": (1.5, 1.5)}, es_perecedero_estricto=True,
                  politicas=politicas_con(lambda d: d.update(minimo_linea=6)))
    assert lineas(r) == [("LA 21", 6)]


def test_foto_sin_ventas_no_recomienda():
    bodega = BodegaFalsa()
    bodega._fecha_inventario = bodega.calendario().ultima_fecha + pd.Timedelta(days=1)
    with pytest.raises(FotoSinVentas):
        escenario({"LA 21": 0}, {"LA 21": (15, 15)}, bodega=bodega)


# ── Respuesta completa ─────────────────────────────────────────────────────

def test_catalogo_resumen_y_politicas():
    bodega = BodegaFalsa()
    bodega.agregar_producto("S1")
    bodega.agregar_stock("S1", "LA 21", 0)
    bodega.agregar_producto("K1", es_perecedero_estricto=True, se_vende_por_kilo=True)
    bodega.agregar_stock("K1", "GLORIETA", 0)
    fijos = PronosticosFijos({("S1", "LA 21"): (15, 15), ("K1", "GLORIETA"): (9, 9)})
    r = recomendar_compras(bodega, fijos, POLITICAS, POLITICAS_TRASLADOS)
    assert r["resumen"] == {"productos": 2, "lineas": 2, "lineas_sucursal": 1, "lineas_bodega": 1,
                            "cantidad": {"unidad": 22, "kg": 8}, "cubiertos_por_bodega": 0, "alertas": 0,
                            "pares_sin_pronostico": 0}
    assert r["politicas"] == {"inv21": {"version": 1, "fecha": "2026-09-30"},
                              "inv22": {"version": 1, "fecha": "2026-09-30"}}
    assert (r["fecha_inventario"], r["lead_time_dias"]) == ("2025-06-30", 5)
    assert [(p["grupo"], p["tipo_destino"], p["dias_cubiertos"]) for p in r["calendario"]] == [
        ("quincenal", "bodega_central", 22), ("semanal", "sucursal", 12)]


def test_codigo_desconocido_va_a_no_encontrados():
    bodega = BodegaFalsa()
    r = recomendar_compras(bodega, PronosticosFijos({}), POLITICAS, POLITICAS_TRASLADOS, productos=["NO-EXISTE"])
    assert (r["no_encontrados"], r["compras"], r["resumen"]["productos"]) == (["NO-EXISTE"], [], 0)
