"""INV-63 — Pruebas de la exploración preregistrada (P11 de docs/INV-63-requerimientos.md), con series sintéticas
cuyo resultado se calcula a mano. Ninguna usa datos del negocio. Correr desde la raíz: python -m pytest notebooks/tests -q"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import exploracion_2026 as ex  # noqa: E402


# ── Rejilla y purge ──────────────────────────────────
def test_rejilla_anclada_y_con_ventana_completa():
    fechas = pd.date_range("2025-11-01", "2026-02-28")
    idx = ex.rejilla(fechas, ancla="2026-01-02", hasta="2026-02-28")
    ancla = fechas.get_loc(pd.Timestamp("2026-01-02"))
    assert ancla in idx and all((i - ancla) % 15 == 0 for i in idx)
    assert idx.min() < 15 and all(i + 15 <= len(fechas) - 1 for i in idx)


def test_particion_purga_las_ventanas_que_tocan_la_prueba():
    origen = pd.to_datetime(["2026-01-01", "2026-01-10", "2026-01-20", "2026-02-01"])
    fin = pd.to_datetime(["2026-01-16", "2026-01-25", "2026-02-04", "2026-02-16"])
    tr, te = ex.particion(origen, fin, "2026-01-20", "2026-02-28")
    assert list(te) == [False, False, True, True]
    assert list(tr) == [True, False, False, False]      # la de 01-10 termina el 25, después del 20
    tr, te = ex.particion(origen, fin, "2027-01-01", "2027-02-01")
    assert not te.any() and not tr.any()


# ── C2 ───────────────────────────────────────────────
def test_croston_sba_a_mano():
    x = np.array([[0.0], [4.0], [0.0], [0.0], [2.0]])
    s = ex.croston_sba(x, alfa=0.5)
    assert np.isnan(s[0, 0])
    # primera venta en el día 2: z = 4, p = 2 -> 0,75 * 4 / 2
    assert s[1, 0] == pytest.approx(0.75 * 4 / 2)
    assert s[3, 0] == pytest.approx(0.75 * 4 / 2)       # sin venta no cambia
    # día 5: intervalo 3, z = 4 + 0,5(2-4) = 3, p = 2 + 0,5(3-2) = 2,5
    assert s[4, 0] == pytest.approx(0.75 * 3 / 2.5)


def test_tsb_a_mano():
    x = np.array([[0.0], [4.0], [0.0], [2.0]])
    s = ex.tsb(x, alfa=0.5, beta=0.5)
    assert np.isnan(s[0, 0])
    assert s[1, 0] == pytest.approx(0.5 * 4)            # p = 1/2, z = 4
    assert s[2, 0] == pytest.approx(0.25 * 4)           # p decae a 0,25
    assert s[3, 0] == pytest.approx(0.625 * 3)          # p = 0,25 + 0,5(1-0,25), z = 4 + 0,5(2-4)


def test_ewm_y_features_c2():
    x = np.array([[2.0, 0.0], [0.0, 0.0], [4.0, 3.0]])
    e = ex.ewm(x, span=3)                               # alfa 0,5
    assert e[2, 0] == pytest.approx(0.5 * 1 + 0.5 * 4) and e[2, 1] == pytest.approx(1.5)
    f = ex.features_c2(x, 2, ex.croston_sba(x), ex.tsb(x), e, horizonte=15)
    assert list(f["trail_60"]) == [6.0, 3.0]
    assert f["frac_ceros_60"][0] == pytest.approx(1 / 3) and f["frac_ceros_60"][1] == pytest.approx(2 / 3)
    assert list(f["edad_habiles"]) == [2.0, 0.0]
    assert f["ewm_15"][0] == pytest.approx(e[2, 0] * 15)


# ── C1 ───────────────────────────────────────────────
def test_marcas_ventana():
    dias = pd.date_range("2025-12-20", periods=4)
    marcas = pd.DataFrame({c: [True, False, False, False] for c in ex.MARCAS_VENTANA.values()}, index=dias)
    marcas["bloque_diciembre"] = ["novena", "novena", "ninguno", "nochebuena_navidad"]
    m = ex.marcas_ventana(marcas, dias)
    assert m["frac_festivo"] == 0.25 and m["frac_bloque_dic"] == 0.75


def test_venta_y_trail_del_anio_anterior():
    fechas = pd.DatetimeIndex(["2025-01-01", "2025-01-02", "2025-01-05", "2026-01-01"])
    x = np.array([[1.0], [2.0], [4.0], [8.0]])
    acum = np.cumsum(x, axis=0)
    # un año (364 días) antes de 2026-01-01..2026-01-04 = 2025-01-02..2025-01-05 -> 2 + 4
    assert ex.venta_anio_anterior(acum, fechas, "2026-01-01", "2026-01-04")[0] == 6.0
    assert ex.venta_anio_anterior(acum, fechas, "2027-06-01", "2027-06-02")[0] == 0.0
    assert np.isnan(ex.venta_anio_anterior(acum, fechas, "2025-06-01", "2025-06-02")[0])   # antes de la historia
    assert ex.trail_anio_anterior(acum, fechas, "2026-01-04", horizonte=2)[0] == 6.0
    assert np.isnan(ex.trail_anio_anterior(acum, fechas, "2025-06-01", horizonte=2)[0])


# ── Reglas ───────────────────────────────────────────
def _c(i, costo, ic_bajo, wape_ic_alto, cobertura):
    return dict(id=i, costo=costo, costo_ic_bajo=ic_bajo, wape_ic_alto=wape_ic_alto, cobertura=cobertura)


def test_seleccion_elige_el_mas_barato_entre_los_que_cumplen():
    elegido, t = ex.regla_seleccion([_c("C1", 90, 0.01, 0.0, 0.90), _c("C2", 80, 0.02, -0.01, 0.90),
                                     _c("C3", 85, 0.03, 0.01, 0.89), _c("C4", 70, 0.05, 0.02, 0.80)])
    assert elegido == "C3"                              # C2 empeora el WAPE y C4 se descalibra
    assert t.set_index("id").loc["C4", "cumple_cobertura"] == False  # noqa: E712


def test_seleccion_sin_candidatos_que_cumplan_es_c0():
    assert ex.regla_seleccion([_c("C1", 90, -0.01, 0.0, 0.90)])[0] == "C0"


def test_reglas_confirmacion():
    cob = [dict(estrato=None, n_filas=5000, cobertura=0.90), dict(estrato="cabeza", n_filas=150, cobertura=0.70)]
    ok = ex.reglas_confirmacion(dict(mejora_rel=0.05, ic_bajo=0.01, ic_alto=0.09),
                                dict(mejora_rel=0.0, ic_bajo=-0.01, ic_alto=0.01), cob)
    assert ok["cumple"] and ok["E3"]                    # la cabeza con 150 filas no decide
    falla = ex.reglas_confirmacion(dict(mejora_rel=0.01, ic_bajo=-0.01, ic_alto=0.03),
                                   dict(mejora_rel=0.0, ic_bajo=-0.01, ic_alto=0.01), cob)
    assert not falla["cumple"] and not falla["E1"]
