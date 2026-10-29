"""INV-20 — Features calculadas desde la bodega (prediccion/features.py).

El test central contrasta features_par con una réplica del cálculo de
notebooks/07_matriz_as_of.ipynb (rejilla de días hábiles con ceros,
rolling de pandas, motor as-of por train_end y factor de calendario con
rolling(15).mean().shift(-15)) sobre series sintéticas: si alguien cambia una
fórmula del servicio, deja de coincidir con la de entrenamiento y falla acá.
La paridad con la matriz REAL está en test_paridad_matriz.py (necesita la bodega).
"""
import numpy as np
import pandas as pd
import pytest

from prediccion.features import (
    Calendario,
    CalendarioInsuficiente,
    HistoriaInsuficiente,
    determinar_rama,
    factor_calendario,
    features_par,
)
from tests.conftest import marcas_calendario

PARAMETROS = {
    "horizonte": 15, "ventana_trail": 15, "ventana_nivel": 60, "min_periodos_nivel": 20,
    "min_frecuencia_as_of": 30, "adi_corte": 1.32, "cv2_corte": 0.49,
    "eventos_calendario": [
        {"evento": "Quincena", "factor": 0.9, "columna": "es_quincena", "operador": "verdadero"},
        {"evento": "Inicio de mes", "factor": 1.3, "columna": "dia", "operador": "<=", "valor": 3},
        {"evento": "Fin de mes", "factor": 0.93, "columna": "dia", "operador": ">=", "valor": 28},
    ],
    "condiciones_producto": {"cond1_espacio_bodega": "requiere_espacio_bodega", "cond2_perecedero": "es_perecedero_estricto",
                             "cond3_refrigerado": "es_refrigerado", "cond4_papel_higienico": "es_papel_higienico_grande",
                             "cond5_temporada": "es_temporada"},
}
ATRIBUTOS = {"requiere_espacio_bodega": True, "es_perecedero_estricto": False, "es_refrigerado": True,
             "es_papel_higienico_grande": False, "es_temporada": False}


def replica_07(serie: pd.Series, habiles: pd.DatetimeIndex, marcas: pd.DataFrame, origen, train_end) -> dict:
    """Cálculo de 07_matriz_as_of.ipynb para una columna de la rejilla ancha."""
    ancha = serie.reindex(habiles, fill_value=0).astype("float32").to_frame("x")
    trail = ancha["x"].rolling(15, min_periods=15).sum()
    prev = trail.shift(15)
    nivel = ancha["x"].rolling(60, min_periods=20).mean()
    arr = ancha["x"].to_numpy()
    idx = np.arange(len(arr))
    ultimo = np.maximum.accumulate(np.where(arr > 0, idx, -1))
    dsv = pd.Series(np.where(ultimo < 0, np.nan, idx - ultimo), index=habiles)

    sub = ancha.loc[ancha.index <= train_end, "x"].to_numpy()
    pos = np.flatnonzero(sub > 0)
    adi = cv2 = np.nan
    if pos.size >= 2:
        adi = np.diff(pos).mean()
        vals = sub[pos]
        m = vals.mean()
        if m > 0:
            cv2 = (vals.std(ddof=1) / m) ** 2 if vals.size > 1 else 0.0
    ceros = (sub == 0).astype(np.int8)
    racha = 0.0
    if ceros.any():
        d = np.diff(np.concatenate(([0], ceros, [0])))
        racha = float((np.flatnonzero(d == -1) - np.flatnonzero(d == 1)).max())

    cal = marcas.reindex(habiles)
    factor_diario = pd.Series(1.0, index=habiles)
    factor_diario[cal["es_quincena"].to_numpy()] *= 0.9
    factor_diario[(cal["dia"] <= 3).to_numpy()] *= 1.3
    factor_diario[(cal["dia"] >= 28).to_numpy()] *= 0.93
    factor_rolling = factor_diario.rolling(15, min_periods=15).mean().shift(-15)
    return {"trail_15": trail[origen], "trail_15_prev": prev[origen], "nivel_medio_60d": nivel[origen],
            "dias_desde_ultima_venta": dsv[origen], "frecuencia_as_of": float(pos.size), "adi_as_of": adi,
            "cv2_as_of": cv2, "racha_max_as_of": racha, "factor_calendario_ventana": factor_rolling[origen]}


@pytest.fixture()
def calendario_con_hueco():
    """Rejilla con días sin venta en el negocio (huecos), como la real."""
    todas = pd.date_range("2024-01-01", "2024-12-31", freq="D")
    habiles = todas[~todas.isin(pd.to_datetime(["2024-01-01", "2024-03-29", "2024-05-10", "2024-05-11"]))]
    return Calendario(habiles=habiles, marcas=marcas_calendario(todas))


@pytest.mark.parametrize("semilla", range(8))
def test_features_iguales_a_la_replica_de_07(calendario_con_hueco, semilla):
    rng = np.random.default_rng(semilla)
    habiles = calendario_con_hueco.habiles
    probabilidad = rng.uniform(0.15, 0.95)
    dias = habiles[rng.random(len(habiles)) < probabilidad]
    serie = pd.Series(rng.integers(1, 30, len(dias)).astype(float), index=dias)
    for _ in range(10):
        i = int(rng.integers(120, len(habiles) - 20))
        origen = habiles[i]
        train_end = habiles[i - int(rng.integers(0, 60))]
        esperado = replica_07(serie, habiles, calendario_con_hueco.marcas, origen, train_end)
        if esperado["frecuencia_as_of"] < PARAMETROS["min_frecuencia_as_of"]:
            continue
        obtenido = features_par(serie, calendario_con_hueco, origen, train_end, PARAMETROS, ATRIBUTOS)
        for k, v in esperado.items():
            assert obtenido[k] == pytest.approx(v, rel=1e-6, abs=1e-6, nan_ok=True), (k, origen)


def test_atributos_de_producto_pasan_a_cond(calendario_con_hueco):
    serie = pd.Series(5.0, index=calendario_con_hueco.habiles)
    f = features_par(serie, calendario_con_hueco, calendario_con_hueco.habiles[200], calendario_con_hueco.habiles[200],
                     PARAMETROS, ATRIBUTOS)
    assert (f["cond1_espacio_bodega"], f["cond2_perecedero"], f["cond3_refrigerado"]) == (1, 0, 1)
    assert f["familia_modelo"] == "suave"


def test_serie_esparsa_es_intermitente(calendario_con_hueco):
    habiles = calendario_con_hueco.habiles
    serie = pd.Series(4.0, index=habiles[::5])
    f = features_par(serie, calendario_con_hueco, habiles[300], habiles[300], PARAMETROS, ATRIBUTOS)
    assert f["adi_as_of"] == pytest.approx(5.0)
    assert f["familia_modelo"] == "intermitente"


def test_poca_historia_es_cold_start(calendario_con_hueco):
    habiles = calendario_con_hueco.habiles
    serie = pd.Series(1.0, index=habiles[100:110])
    with pytest.raises(HistoriaInsuficiente):
        features_par(serie, calendario_con_hueco, habiles[200], habiles[200], PARAMETROS, ATRIBUTOS)


def test_origen_que_no_es_dia_habil_falla(calendario_con_hueco):
    serie = pd.Series(5.0, index=calendario_con_hueco.habiles)
    with pytest.raises(ValueError):
        features_par(serie, calendario_con_hueco, "2024-03-29", "2024-03-29", PARAMETROS, ATRIBUTOS)


def test_proyeccion_futura_salta_los_cierres():
    habiles = pd.date_range("2025-12-01", "2025-12-31", freq="D")
    todas = pd.date_range("2025-12-01", "2026-02-28", freq="D")
    cal = Calendario(habiles=habiles, marcas=marcas_calendario(todas, cierres=["2026-01-01"]))
    dias = cal.proximos_habiles("2025-12-31", 15)
    assert dias[0] == pd.Timestamp("2026-01-02")
    assert pd.Timestamp("2026-01-01") not in dias
    assert len(dias) == 15


def test_proyeccion_combina_historia_y_futuro():
    habiles = pd.date_range("2025-12-01", "2025-12-31", freq="D")
    todas = pd.date_range("2025-12-01", "2026-02-28", freq="D")
    cal = Calendario(habiles=habiles, marcas=marcas_calendario(todas, cierres=["2026-01-01"]))
    dias = cal.proximos_habiles("2025-12-25", 15)
    assert list(dias[:6]) == list(pd.date_range("2025-12-26", "2025-12-31"))
    assert dias[6] == pd.Timestamp("2026-01-02")


def test_calendario_sin_horizonte_suficiente_falla():
    habiles = pd.date_range("2025-12-01", "2025-12-31", freq="D")
    cal = Calendario(habiles=habiles, marcas=marcas_calendario(pd.date_range("2025-12-01", "2026-01-05")))
    with pytest.raises(CalendarioInsuficiente):
        factor_calendario(cal, "2025-12-31", PARAMETROS)


def test_determinar_rama_intermitente():
    assert determinar_rama(pd.Series({"familia_modelo": "intermitente", "cond2_perecedero": 0})) == "intermitente"


def test_determinar_rama_suave_perecedero():
    assert determinar_rama(pd.Series({"familia_modelo": "suave", "cond2_perecedero": 1})) == "suave_perecedero"


def test_determinar_rama_suave_no_perecedero():
    assert determinar_rama(pd.Series({"familia_modelo": "suave", "cond2_perecedero": 0})) == "suave_no_perecedero"
