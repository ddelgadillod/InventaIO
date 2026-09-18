"""INV-20 — Matemática pura de blending (motor.py), sin cargar modelos reales."""
import numpy as np
import pandas as pd
import pytest

from prediccion.motor import predecir


class _ModeloFalso:
    """Stub con .predict() determinístico, para no depender de un modelo real."""

    def __init__(self, valor):
        self.valor = valor

    def predict(self, X):
        return np.full(len(X), self.valor)


def _fila():
    return pd.DataFrame([{"f1": 1.0, "f2": 2.0}])


def test_lightgbm_devuelve_q50_y_qneg_directos():
    paquete = {
        "tipo": "lightgbm",
        "features": ["f1", "f2"],
        "modelo_q50": _ModeloFalso(10.0),
        "modelo_qneg": _ModeloFalso(25.0),
        "offset_conformal_qneg": None,
    }
    p50, pneg = predecir(paquete, _fila())
    assert p50 == 10.0
    assert pneg == 25.0


def test_ensamble_combina_tweedie_y_lightgbm_con_el_peso():
    paquete = {
        "tipo": "ensamble",
        "features": ["f1", "f2"],
        "peso_tweedie": 0.6,
        "modelo_tweedie": _ModeloFalso(10.0),
        "factor_qneg_tweedie": 2.0,
        "modelo_lgb_q50": _ModeloFalso(20.0),
        "modelo_lgb_qneg": _ModeloFalso(30.0),
        "offset_conformal_qneg": None,
    }
    p50, pneg = predecir(paquete, _fila())
    # p50 = 0.6*10 + 0.4*20 = 14
    assert p50 == pytest.approx(14.0)
    # pneg_tweedie = 10*2 = 20; pneg = 0.6*20 + 0.4*30 = 24
    assert pneg == pytest.approx(24.0)


def test_offset_conformal_se_suma():
    paquete = {
        "tipo": "lightgbm",
        "features": ["f1", "f2"],
        "modelo_q50": _ModeloFalso(5.0),
        "modelo_qneg": _ModeloFalso(10.0),
        "offset_conformal_qneg": 3.0,
    }
    _, pneg = predecir(paquete, _fila())
    assert pneg == pytest.approx(13.0)


def test_offset_conformal_negativo_no_baja_de_cero():
    paquete = {
        "tipo": "lightgbm",
        "features": ["f1", "f2"],
        "modelo_q50": _ModeloFalso(5.0),
        "modelo_qneg": _ModeloFalso(1.0),
        "offset_conformal_qneg": -10.0,
    }
    _, pneg = predecir(paquete, _fila())
    assert pneg == 0.0


def test_tipo_de_modelo_desconocido_lanza_error():
    paquete = {"tipo": "otro", "features": ["f1", "f2"]}
    with pytest.raises(ValueError):
        predecir(paquete, _fila())
