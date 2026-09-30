"""INV-22 — Motor de transferencias sobre una bodega en memoria con inventario
y pronósticos fijos (sin modelos). Un test por caso de la tabla "Casos de
prueba" de la especificación, más los bordes de urgencia, llegada y catálogo.

Sucursales de BodegaFalsa: PRINCIPAL, LA 21 y GLORIETA (físicas) y
BODEGA_CENTRAL. Mientras no se diga otra cosa: políticas del repo (margen 50 %
en no perecederos, exhibición 2, mínimo 6, traslado a 2 días hábiles).
"""
import json

import pandas as pd
import pytest

from core.config import get_settings
from tests.conftest import BodegaFalsa, PronosticosFijos
from transferencias.motor import FotoSinVentas, calcular_llegada, recomendar_transferencias
from transferencias.politicas import cargar_politicas

POLITICAS = cargar_politicas(get_settings().POLITICAS_TRANSFERENCIAS_PATH)
BODEGA = "BODEGA_CENTRAL"


def escenario(stock: dict, pronosticos: dict, producto: str = "X1", politicas=None, bodega=None, **marcas) -> dict:
    """Corre el motor para un producto: `stock` {ubicación: stock},
    `pronosticos` {sucursal: (q50, límite superior)}."""
    bodega = bodega or BodegaFalsa()
    bodega.agregar_producto(producto, **marcas)
    for ubicacion, s in stock.items():
        bodega.agregar_stock(producto, ubicacion, s)
    fijos = PronosticosFijos({(producto, suc): v for suc, v in pronosticos.items()})
    return recomendar_transferencias(bodega, fijos, politicas or POLITICAS, productos=[producto])


def movimientos(r: dict) -> list:
    return [(t["origen"], t["destino"], t["cantidad"]) for t in r["traslados"]]


def fila(r: dict, ubicacion: str) -> dict:
    return next(b for b in r["balance"] if b["sucursal"] == ubicacion)


# ── Casos de la tabla de la especificación ─────────────────────────────────

def test_excedente_sin_deficit_no_traslada_y_reporta_el_excedente():
    r = escenario({"PRINCIPAL": 100, "LA 21": 10}, {"PRINCIPAL": (10, 12), "LA 21": (10, 12)})
    assert movimientos(r) == []
    origen = fila(r, "PRINCIPAL")
    assert origen["estado"] == "origen"
    assert origen["maximo"] == 18.0                     # 12 × 1,5
    assert origen["excedente"] == 82.0
    assert origen["excedente_sin_destino"] == 82.0      # P12: se queda donde está
    assert fila(r, "LA 21")["estado"] == "equilibrio"


def test_deficit_sin_excedente_pasa_completo_al_neto():
    r = escenario({"PRINCIPAL": 10, "LA 21": 2}, {"PRINCIPAL": (10, 12), "LA 21": (10, 12)})
    assert movimientos(r) == []
    destino = fila(r, "LA 21")
    assert (destino["estado"], destino["deficit"], destino["recibido"], destino["deficit_neto"]) == ("destino", 8, 0, 8)


def test_empate_exacto_un_traslado_por_el_total():
    r = escenario({BODEGA: 10}, {"LA 21": (10, 12)})
    assert movimientos(r) == [(BODEGA, "LA 21", 10)]
    assert fila(r, "LA 21")["deficit_neto"] == 0
    assert fila(r, BODEGA)["excedente_sin_destino"] == 0


def test_desempate_por_mayor_q50_con_la_misma_cobertura():
    # Ambos destinos sin stock (cobertura 0); el excedente alcanza para uno.
    r = escenario({BODEGA: 6}, {"LA 21": (30, 40), "GLORIETA": (60, 80)})
    assert movimientos(r) == [(BODEGA, "GLORIETA", 6)]


def test_nivelacion_deja_las_coberturas_parejas():
    r = escenario({BODEGA: 40}, {"LA 21": (30, 40), "GLORIETA": (45, 60)})
    la21, glorieta = fila(r, "LA 21"), fila(r, "GLORIETA")
    assert la21["recibido"] + glorieta["recibido"] == 40
    cobertura = lambda b, q50: b["recibido"] / (q50 / 15)          # noqa: E731 (stock 0)
    # menos de un día de venta de diferencia
    assert abs(cobertura(la21, 30) - cobertura(glorieta, 45)) < 1


def test_bodega_primero_aunque_una_sucursal_tenga_mas_excedente():
    r = escenario({BODEGA: 10, "PRINCIPAL": 100}, {"PRINCIPAL": (10, 12), "LA 21": (10, 12)})
    assert movimientos(r) == [(BODEGA, "LA 21", 10)]
    assert fila(r, "PRINCIPAL")["enviado"] == 0


def test_perecedero_solo_hacia_sucursales_con_q50_positivo():
    r = escenario({BODEGA: 50}, {"LA 21": (20, 25), "GLORIETA": (0, 10)}, es_perecedero_estricto=True)
    assert movimientos(r) == [(BODEGA, "LA 21", 20)]
    assert fila(r, "GLORIETA")["estado"] == "vigilancia"
    assert fila(r, "GLORIETA")["recibido"] == 0
    assert all(t["destino"] != BODEGA for t in r["traslados"])


def test_frio_sale_de_la_bodega_y_nunca_entra():
    # Un origen en sucursal con mucho excedente y ningún destino: tampoco va a la Bodega.
    r = escenario({BODEGA: 30, "PRINCIPAL": 200}, {"PRINCIPAL": (10, 12), "LA 21": (12, 15)}, requiere_frio=True)
    assert movimientos(r) == [(BODEGA, "LA 21", 12)]
    assert all(t["destino"] != BODEGA for t in r["traslados"])
    assert fila(r, "PRINCIPAL")["excedente_sin_destino"] == 182.0


def test_intermitente_con_q50_cero_solo_recibe_el_sobrante():
    r = escenario({BODEGA: 30}, {"LA 21": (10, 12), "GLORIETA": (0, 12)})
    assert movimientos(r) == [(BODEGA, "LA 21", 10), (BODEGA, "GLORIETA", 12)]
    vigilancia = fila(r, "GLORIETA")
    assert (vigilancia["estado"], vigilancia["urgencia"]) == ("vigilancia", "vigilancia")
    assert (vigilancia["deficit"], vigilancia["deficit_vigilancia"], vigilancia["deficit_neto"]) == (0, 12, 0)
    traslado = next(t for t in r["traslados"] if t["destino"] == "GLORIETA")
    assert (traslado["urgencia"], traslado["llega_tarde"]) == ("vigilancia", False)


def test_intermitente_con_q50_cero_no_recibe_si_no_sobra():
    r = escenario({BODEGA: 10}, {"LA 21": (10, 12), "GLORIETA": (0, 12)})
    assert movimientos(r) == [(BODEGA, "LA 21", 10)]


def test_q50_cero_no_es_origen_aunque_tenga_stock():
    r = escenario({"GLORIETA": 100}, {"GLORIETA": (0, 5), "LA 21": (10, 12)})
    assert movimientos(r) == []
    assert fila(r, "GLORIETA")["estado"] == "vigilancia"


def test_stock_negativo_no_se_traslada_y_pide_pedido_urgente():
    r = escenario({BODEGA: 50, "LA 21": -4}, {"LA 21": (10, 12)})
    assert movimientos(r) == []
    assert r["alertas"] == [{"producto_id": "X1", "sucursal": "LA 21", "tipo": "stock_negativo", "stock": -4.0,
                             "accion": "pedido_urgente", "detalle": r["alertas"][0]["detalle"]}]
    negativo = fila(r, "LA 21")
    # P7: para el pedido el stock se toma como 0
    assert (negativo["estado"], negativo["deficit"], negativo["deficit_neto"]) == ("stock_negativo", 10, 10)
    assert negativo["urgencia"] == "urgente"


def test_sin_pronostico_no_participa_y_su_stock_no_es_excedente():
    r = escenario({"PRINCIPAL": 100}, {"LA 21": (10, 12)})
    assert movimientos(r) == []
    assert fila(r, "PRINCIPAL")["estado"] == "sin_pronostico"
    assert fila(r, "PRINCIPAL")["excedente"] is None
    assert [(a["sucursal"], a["tipo"], a["accion"]) for a in r["alertas"]] == [("PRINCIPAL", "sin_pronostico", "ninguna")]
    # GLORIETA no tiene fila en la foto ni pronóstico: no se lista.
    assert "GLORIETA" not in {b["sucursal"] for b in r["balance"]}


def test_minimo_de_6_descarta_una_asignacion_de_5():
    r = escenario({BODEGA: 20, "LA 21": 5}, {"LA 21": (10, 12)})     # déficit 5
    assert movimientos(r) == []
    assert fila(r, "LA 21")["deficit_neto"] == 5


def test_minimo_de_6_origen_con_5_no_despacha():
    r = escenario({BODEGA: 5}, {"LA 21": (10, 12)})
    assert movimientos(r) == []
    assert fila(r, "LA 21")["deficit_neto"] == 10
    assert fila(r, BODEGA)["excedente_sin_destino"] == 5


def test_kilos_descuentan_10_por_ciento_y_redondean_hacia_abajo():
    r = escenario({BODEGA: 10.0}, {"LA 21": (20, 25)}, se_vende_por_kilo=True)
    assert movimientos(r) == [(BODEGA, "LA 21", 9)]
    assert r["traslados"][0]["unidad"] == "kg"


def test_exhibicion_el_origen_conserva_2_unidades():
    r = escenario({"PRINCIPAL": 3}, {"PRINCIPAL": (0.2, 1 / 3)})
    origen = fila(r, "PRINCIPAL")
    assert origen["maximo"] == 0.5
    assert origen["excedente"] == 1.0


def test_llega_tarde_si_se_agota_antes_del_traslado():
    # LA 21: 1 día hábil de cobertura; GLORIETA: 3. El traslado tarda 2.
    r = escenario({BODEGA: 100, "LA 21": 1, "GLORIETA": 9}, {"LA 21": (15, 20), "GLORIETA": (45, 60)})
    tarde = {t["destino"]: t["llega_tarde"] for t in r["traslados"]}
    assert tarde == {"LA 21": True, "GLORIETA": False}
    la21 = next(t for t in r["traslados"] if t["destino"] == "LA 21")
    assert (la21["urgencia"], la21["dias_hasta_agotarse"], la21["dias_habiles_llegada"]) == ("urgente", 1.0, 2)


def test_foto_mas_nueva_que_las_ventas_no_recomienda():
    bodega = BodegaFalsa()
    bodega._fecha_inventario = bodega.calendario().ultima_fecha + pd.Timedelta(days=3)
    with pytest.raises(FotoSinVentas) as e:
        escenario({BODEGA: 10}, {"LA 21": (10, 12)}, bodega=bodega)
    assert e.value.dias == 3


def test_cambiar_el_margen_en_el_json_cambia_el_maximo(tmp_path):
    datos = json.loads(open(get_settings().POLITICAS_TRANSFERENCIAS_PATH, encoding="utf-8").read())
    datos["stock_maximo"]["margen_no_perecedero"] = 1.0
    datos["version"] = 2
    (tmp_path / "politicas.json").write_text(json.dumps(datos), encoding="utf-8")
    politicas = cargar_politicas(tmp_path / "politicas.json")
    antes = escenario({"PRINCIPAL": 100}, {"PRINCIPAL": (10, 12)})
    despues = escenario({"PRINCIPAL": 100}, {"PRINCIPAL": (10, 12)}, politicas=politicas)
    assert (fila(antes, "PRINCIPAL")["maximo"], fila(despues, "PRINCIPAL")["maximo"]) == (18.0, 24.0)
    assert despues["politicas"]["version"] == 2


# ── Criterios de aceptación: bordes ────────────────────────────────────────

def test_margen_de_perecederos_es_25_por_ciento():
    r = escenario({"PRINCIPAL": 100}, {"PRINCIPAL": (10, 12)}, es_perecedero_estricto=True)
    assert fila(r, "PRINCIPAL")["maximo"] == 15.0


def test_maximo_nunca_menor_que_el_objetivo():
    r = escenario({"PRINCIPAL": 100}, {"PRINCIPAL": (20, 10)})     # qα × 1,5 = 15 < q50
    assert fila(r, "PRINCIPAL")["maximo"] == 20.0


@pytest.mark.parametrize("stock, urgencia", [(5, "urgente"), (5.5, "alta"), (10, "alta"), (10.5, "normal")])
def test_urgencia_por_dias_hasta_agotarse(stock, urgencia):
    # q50 = 15: un día de venta por día hábil, así que los días son el stock.
    r = escenario({"LA 21": stock}, {"LA 21": (15, 20)})
    assert fila(r, "LA 21")["urgencia"] == urgencia


def test_entre_sucursales_sale_primero_la_de_mas_excedente():
    r = escenario({"PRINCIPAL": 40, "GLORIETA": 60}, {"PRINCIPAL": (10, 12), "GLORIETA": (10, 12), "LA 21": (10, 12)})
    assert movimientos(r) == [("GLORIETA", "LA 21", 10)]


def test_destino_sin_fila_en_la_foto_tiene_stock_cero():
    r = escenario({BODEGA: 30}, {"LA 21": (10, 12)})
    assert fila(r, "LA 21")["stock"] == 0.0
    assert movimientos(r) == [(BODEGA, "LA 21", 10)]


def test_bodega_con_stock_negativo_alerta_y_no_despacha():
    r = escenario({BODEGA: -3}, {"LA 21": (10, 12)})
    assert movimientos(r) == []
    assert fila(r, BODEGA)["estado"] == "stock_negativo"
    assert [(a["sucursal"], a["tipo"]) for a in r["alertas"]] == [(BODEGA, "stock_negativo")]


def test_un_resto_menor_al_minimo_se_queda_en_el_origen():
    # Bodega 7 y PRINCIPAL con 20 de excedente; LA 21 necesita 10: salen 7 de la
    # Bodega y el resto (3) es menor al mínimo, así que no sale de PRINCIPAL.
    r = escenario({BODEGA: 7, "PRINCIPAL": 38}, {"PRINCIPAL": (10, 12), "LA 21": (10, 12)})
    assert movimientos(r) == [(BODEGA, "LA 21", 7)]
    assert fila(r, "LA 21")["deficit_neto"] == 3


def test_un_sobrante_menor_al_minimo_no_abre_otro_destino():
    # LA 21 (cobertura 0) llena sus 6; quedan 4 < 6 y GLORIETA no puede recibir un traslado válido.
    r = escenario({BODEGA: 10, "GLORIETA": 2}, {"LA 21": (6, 8), "GLORIETA": (20, 25)})
    assert movimientos(r) == [(BODEGA, "LA 21", 6)]
    assert fila(r, "GLORIETA")["deficit_neto"] == 18
    assert fila(r, BODEGA)["excedente_sin_destino"] == 4


def test_respuesta_expone_deficit_recibido_neto_y_politicas():
    r = escenario({BODEGA: 12, "LA 21": 3}, {"LA 21": (20.1, 31)})
    destino = fila(r, "LA 21")
    assert (destino["deficit"], destino["recibido"], destino["deficit_neto"]) == (17.1, 12, 5.1)
    assert r["politicas"] == {"version": 1, "fecha": "2026-09-30"}
    assert r["resumen"] == {"productos": 1, "traslados": 1, "cantidad_trasladada": 12, "deficit_total": 17.1,
                            "deficit_neto": 5.1, "excedente_sin_destino": 0.0, "alertas": 0}
    assert (r["fecha_inventario"], r["fecha_pronostico"], r["horizonte_dias"]) == ("2025-06-30", "2025-06-30", 15)


def test_codigo_desconocido_va_a_no_encontrados():
    bodega = BodegaFalsa()
    r = recomendar_transferencias(bodega, PronosticosFijos({}), POLITICAS, productos=["P1", "NO-EXISTE", "P1"])
    assert r["no_encontrados"] == ["NO-EXISTE"]
    assert r["resumen"]["productos"] == 1


def test_sin_lista_procesa_todos_los_productos_con_fila_en_la_foto():
    bodega = BodegaFalsa()
    for codigo in ["A1", "A2"]:
        bodega.agregar_producto(codigo)
        bodega.agregar_stock(codigo, BODEGA, 10)
    bodega.agregar_producto("SIN_FOTO")
    fijos = PronosticosFijos({("A1", "LA 21"): (10, 12), ("A2", "LA 21"): (10, 12), ("SIN_FOTO", "LA 21"): (10, 12)})
    r = recomendar_transferencias(bodega, fijos, POLITICAS)
    assert r["resumen"]["productos"] == 2
    assert {t["producto_id"] for t in r["traslados"]} == {"A1", "A2"}


def test_traslados_ordenados_por_urgencia():
    bodega = BodegaFalsa()
    for codigo, stock in [("NORMAL", 22), ("URGENTE", 1)]:          # 11 y 0,5 días de cobertura
        bodega.agregar_producto(codigo)
        bodega.agregar_stock(codigo, BODEGA, 100)
        bodega.agregar_stock(codigo, "LA 21", stock)
    fijos = PronosticosFijos({("NORMAL", "LA 21"): (30, 40), ("URGENTE", "LA 21"): (30, 40)})
    r = recomendar_transferencias(bodega, fijos, POLITICAS)
    assert [t["producto_id"] for t in r["traslados"]] == ["URGENTE", "NORMAL"]


def test_llegada_con_dias_fijos_de_traslado(tmp_path):
    datos = json.loads(open(get_settings().POLITICAS_TRANSFERENCIAS_PATH, encoding="utf-8").read())
    datos["traslado"]["dias_semana"] = ["viernes"]
    (tmp_path / "p.json").write_text(json.dumps(datos), encoding="utf-8")
    calendario = BodegaFalsa().calendario()
    # 2025-06-30 es lunes: el siguiente viernes es 2025-07-04, pero es cierre
    # programado en la bodega falsa, así que sale el viernes siguiente.
    llegada = calcular_llegada(calendario, "2025-06-30", cargar_politicas(tmp_path / "p.json"))
    assert (llegada.fecha, llegada.dias_habiles) == (pd.Timestamp("2025-07-11"), 10)
    sin_fijos = calcular_llegada(calendario, "2025-06-30", POLITICAS)
    assert (sin_fijos.fecha, sin_fijos.dias_habiles) == (pd.Timestamp("2025-07-02"), 2)


def test_pronostico_en_lote_da_lo_mismo_que_par_a_par(modelo_loader, bodega_falsa):
    """P1 (suave) y P2 (intermitente) a varias fechas, P3 sin historia y un par
    sin ventas: el lote coincide exactamente con pronosticar_par."""
    from prediccion.features import HistoriaInsuficiente
    from prediccion.servicio import PronosticadorNivel1, pronosticar_par

    calendario = bodega_falsa.calendario()
    pronosticador = PronosticadorNivel1(modelo_loader)
    ramas = set()
    for fecha in [calendario.ultima_fecha, calendario.habiles[-40], calendario.habiles[-90]]:
        solicitudes = [(bodega_falsa.producto(cod), "PRINCIPAL", bodega_falsa.ventas_diarias(cod, "PRINCIPAL", fecha))
                       for cod in ["P1", "P2", "P3"]]
        solicitudes.append((bodega_falsa.producto("P1"), "LA 21", pd.Series(dtype=float)))
        for _ in range(2):                               # la segunda vez usa el factor guardado
            lote = pronosticador.pronosticar_lote(solicitudes, calendario, fecha)
            for (producto, sucursal, unidades), resultado in zip(solicitudes, lote):
                try:
                    esperado = pronosticar_par(modelo_loader, producto, sucursal, unidades, calendario, fecha)
                except HistoriaInsuficiente:
                    assert isinstance(resultado, HistoriaInsuficiente)
                    continue
                assert resultado == esperado
                ramas.add(resultado.rama)
    assert ramas == {"suave_no_perecedero", "intermitente"}
    assert len(pronosticador._factores) == 3


def test_pronosticador_limita_los_factores_guardados(modelo_loader, bodega_falsa):
    from prediccion.servicio import PronosticadorNivel1

    calendario = bodega_falsa.calendario()
    pronosticador = PronosticadorNivel1(modelo_loader)
    pronosticador.MAX_FACTORES = 1
    for fecha in [calendario.ultima_fecha, calendario.habiles[-40]]:
        pronosticador.pronosticar_lote([(bodega_falsa.producto("P1"), "PRINCIPAL",
                                         bodega_falsa.ventas_diarias("P1", "PRINCIPAL", fecha))], calendario, fecha)
    assert list(pronosticador._factores) == [(id(calendario), calendario.habiles[-40])]


def test_acepta_el_modelo_loader_directamente(modelo_loader, bodega_falsa):
    # INV-21 puede pasar el ModeloLoader: el motor lo envuelve en PronosticadorNivel1.
    bodega_falsa.agregar_stock("P1", BODEGA, 500)
    r = recomendar_transferencias(bodega_falsa, modelo_loader, POLITICAS, productos=["P1", "P3"])
    principal = fila(r, "PRINCIPAL")
    assert principal["rama"] == "suave_no_perecedero" and principal["q50"] > 0
    assert [(a["producto_id"], a["tipo"]) for a in r["alertas"]] == []      # P3 sin historia y sin foto: no se lista
