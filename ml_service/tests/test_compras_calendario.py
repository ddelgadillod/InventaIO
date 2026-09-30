"""INV-21 — Calendario de pedidos (compras/calendario.py) sobre el calendario de
BodegaFalsa: días hábiles todos los días, foto el lunes 2025-06-30 y cierre
programado el viernes 2025-07-04. Traslado desde la Bodega: 2 días hábiles
(políticas de INV-22 del repo)."""
from itertools import islice

import pandas as pd
import pytest

from compras.calendario import (clasificar, combinaciones, fechas_fijas, habil_en_o_despues, habiles_entre,
                                planes_de_pedido)
from compras.politicas import FechasPedido
from prediccion.features import CalendarioInsuficiente
from tests.conftest import BodegaFalsa
from tests.test_compras_motor import POLITICAS, POLITICAS_TRASLADOS, politicas_con

FOTO = pd.Timestamp("2025-06-30")
T = pd.Timestamp


@pytest.fixture()
def calendario():
    return BodegaFalsa().calendario()


def test_planes_con_las_politicas_del_repo(calendario):
    planes = planes_de_pedido(calendario, FOTO, POLITICAS, POLITICAS_TRASLADOS)
    assert set(planes) == {("quincenal", "bodega_central"), ("semanal", "sucursal")}

    q = planes[("quincenal", "bodega_central")]
    # pedido el 2; 5 días hábiles sin el cierre del 4 -> llega el 8 a la Bodega y el 10 a la sucursal
    assert (q.fecha_pedido, q.fecha_llegada, q.fecha_llegada_sucursal) == (T("2025-07-02"), T("2025-07-08"),
                                                                            T("2025-07-10"))
    # el pedido siguiente (16) llega el 21 a la Bodega y el 23 a la sucursal: P = 23 días - el cierre
    assert (q.pedido_siguiente, q.cubre_hasta, q.dias_cubiertos, q.dias_hasta_llegada) == (T("2025-07-16"),
                                                                                          T("2025-07-23"), 22, 9)
    s = planes[("semanal", "sucursal")]
    # martes 1 -> llega el 7 (sin el 4); martes 8 -> llega el 13
    assert (s.fecha_pedido, s.fecha_llegada, s.fecha_llegada_sucursal) == (T("2025-07-01"), T("2025-07-07"),
                                                                            T("2025-07-07"))
    assert (s.pedido_siguiente, s.cubre_hasta, s.dias_cubiertos, s.dias_hasta_llegada) == (T("2025-07-08"),
                                                                                          T("2025-07-13"), 12, 6)


def test_fecha_fija_en_cierre_pasa_al_siguiente_dia_habil(calendario):
    politicas = politicas_con(lambda d: d["calendario_pedidos"]["quincenal"].update(dias_mes=[4]))
    q = planes_de_pedido(calendario, FOTO, politicas, POLITICAS_TRASLADOS)[("quincenal", "bodega_central")]
    assert (q.fecha_pedido, q.pedido_siguiente) == (T("2025-07-05"), T("2025-08-04"))


def test_foto_en_dia_de_pedido_pide_ese_mismo_dia(calendario):
    politicas = politicas_con(lambda d: d["calendario_pedidos"]["semanal"].update(dias_semana=["lunes"]))
    s = planes_de_pedido(calendario, FOTO, politicas, POLITICAS_TRASLADOS)[("semanal", "sucursal")]
    assert (s.fecha_pedido, s.pedido_siguiente) == (FOTO, T("2025-07-07"))


def test_perecederos_semanales_y_frio_quincenal_directo(calendario):
    politicas = politicas_con(lambda d: d.update(grupo_semanal=["perecedero"]))
    assert combinaciones(politicas) == [("quincenal", "bodega_central"), ("semanal", "sucursal"),
                                        ("quincenal", "sucursal")]
    assert clasificar({"requiere_frio": True}, politicas) == ("quincenal", "sucursal")
    q = planes_de_pedido(calendario, FOTO, politicas, POLITICAS_TRASLADOS)[("quincenal", "sucursal")]
    # directo: sin el traslado desde la Bodega
    assert (q.fecha_llegada_sucursal, q.cubre_hasta, q.dias_cubiertos, q.dias_hasta_llegada) == (T("2025-07-08"),
                                                                                               T("2025-07-21"), 20, 7)


def test_sin_grupo_semanal_todo_es_quincenal(calendario):
    politicas = politicas_con(lambda d: d.update(grupo_semanal=[]))
    assert combinaciones(politicas) == [("quincenal", "bodega_central"), ("quincenal", "sucursal")]
    assert clasificar({"es_perecedero_estricto": True}, politicas) == ("quincenal", "sucursal")


def test_clasificar_con_las_politicas_del_repo():
    assert clasificar({}, POLITICAS) == ("quincenal", "bodega_central")
    assert clasificar({"es_perecedero_estricto": True}, POLITICAS) == ("semanal", "sucursal")
    assert clasificar({"requiere_frio": True}, POLITICAS) == ("semanal", "sucursal")


def test_fechas_fijas_del_mes_cruzan_de_mes():
    assert list(islice(fechas_fijas(FechasPedido(dias_mes=[16, 2]), "2025-06-20"), 3)) == [
        T("2025-07-02"), T("2025-07-16"), T("2025-08-02")]
    assert list(islice(fechas_fijas(FechasPedido(dias_mes=[2, 16]), "2025-12-31"), 2)) == [
        T("2026-01-02"), T("2026-01-16")]


def test_fechas_fijas_de_la_semana():
    assert list(islice(fechas_fijas(FechasPedido(dias_semana=["martes"]), FOTO), 2)) == [T("2025-07-01"),
                                                                                         T("2025-07-08")]


def test_habiles_entre_y_habil_en_o_despues(calendario):
    assert habiles_entre(calendario, FOTO, "2025-07-05") == 4           # 1, 2, 3 y 5
    assert habiles_entre(calendario, FOTO, FOTO) == 0
    assert habiles_entre(calendario, "2025-06-20", "2025-07-02") == 12  # cruza el último dato
    assert habil_en_o_despues(calendario, "2025-07-04") == T("2025-07-05")
    assert habil_en_o_despues(calendario, "2025-07-03") == T("2025-07-03")


def test_calendario_que_no_alcanza(calendario):
    with pytest.raises(CalendarioInsuficiente):
        habiles_entre(calendario, FOTO, "2025-12-31")
    politicas = politicas_con(lambda d: d.update(lead_time_dias=120))
    with pytest.raises(CalendarioInsuficiente):
        planes_de_pedido(calendario, FOTO, politicas, POLITICAS_TRASLADOS)
