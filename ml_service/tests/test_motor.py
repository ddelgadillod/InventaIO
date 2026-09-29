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


def _fila_completa():
    return pd.DataFrame([{"f1": 1.0, "f2": 2.0, "nivel_medio_60d": 4.0, "codigo_item": "P1", "sucursal": "PRINCIPAL"}])


def test_relativo_escala_la_prediccion_por_la_base():
    paquete = {
        "tipo": "relativo",
        "features": ["f1", "f2"],
        "horizonte": 15,
        "base_offset": 1.0,
        "modelo_q50": _ModeloFalso(1.0),
        "modelo_qneg": _ModeloFalso(1.5),
        "offset_conformal_qneg": None,
    }
    p50, pneg = predecir(paquete, _fila_completa())
    # base = 4*15 + 1 = 61
    assert p50 == pytest.approx(61.0)
    assert pneg == pytest.approx(91.5)


def test_relativo_ignora_offset_conformal_absoluto():
    """El offset conformal de los paquetes v1 está en unidades absolutas: un paquete relativo no lo aplica."""
    paquete = {
        "tipo": "relativo", "features": ["f1", "f2"], "horizonte": 15, "base_offset": 1.0,
        "modelo_q50": _ModeloFalso(1.0), "modelo_qneg": _ModeloFalso(1.0), "offset_conformal_qneg": 1000.0,
    }
    _, pneg = predecir(paquete, _fila_completa())
    assert pneg == pytest.approx(61.0)


def _paquete_baseline():
    return {
        "tipo": "baseline_cuantil",
        "horizonte": 15,
        "razon_cuantil_por_estrato": {"cabeza": 1.2, "medio": 1.5, "cola": 2.0},
        "razon_cuantil_global": 1.7,
        "estrato_por_par": {("P1", "PRINCIPAL"): "medio"},
    }


def test_baseline_cuantil_usa_la_razon_del_estrato_del_par():
    p50, pneg = predecir(_paquete_baseline(), _fila_completa())
    # piso = 4*15 = 60; pneg = 1.5 * (60 + 1)
    assert p50 == pytest.approx(60.0)
    assert pneg == pytest.approx(91.5)


def test_baseline_cuantil_par_sin_estrato_usa_la_razon_global():
    fila = _fila_completa().assign(codigo_item="P999")
    p50, pneg = predecir(_paquete_baseline(), fila)
    assert p50 == pytest.approx(60.0)
    assert pneg == pytest.approx(1.7 * 61.0)


def test_baseline_cuantil_sin_ventas_recientes_da_cero_de_q50():
    fila = _fila_completa().assign(nivel_medio_60d=0.0)
    p50, pneg = predecir(_paquete_baseline(), fila)
    assert p50 == 0.0
    assert pneg == pytest.approx(1.5)


def _paquete_relativo_calibrado(**extra):
    paquete = {
        "tipo": "relativo", "features": ["f1", "f2"], "horizonte": 15, "base_offset": 1.0,
        "modelo_q50": _ModeloFalso(1.0), "modelo_qneg": _ModeloFalso(1.5), "offset_conformal_qneg": None,
        "estrato_por_par": {("P1", "PRINCIPAL"): "cabeza"},
        "offset_relativo_por_estrato": {"cabeza": 0.2, "medio": 0.1, "cola": 0.0},
        "offset_relativo_global": 0.05,
    }
    paquete.update(extra)
    return paquete


def test_relativo_calibrado_suma_el_offset_del_estrato_antes_de_escalar():
    p50, pneg = predecir(_paquete_relativo_calibrado(), _fila_completa())
    # base = 61; q50 no se calibra; pneg = (1.5 + 0.2) * 61
    assert p50 == pytest.approx(61.0)
    assert pneg == pytest.approx(1.7 * 61.0)


def test_relativo_calibrado_par_sin_estrato_usa_el_offset_global():
    fila = _fila_completa().assign(codigo_item="P999")
    _, pneg = predecir(_paquete_relativo_calibrado(), fila)
    assert pneg == pytest.approx(1.55 * 61.0)


def test_relativo_calibrado_offset_negativo_grande_no_baja_de_cero():
    paquete = _paquete_relativo_calibrado(offset_relativo_por_estrato={"cabeza": -5.0})
    _, pneg = predecir(paquete, _fila_completa())
    assert pneg == 0.0


def test_relativo_sin_offsets_relativos_no_se_calibra():
    paquete = _paquete_relativo_calibrado()
    del paquete["offset_relativo_por_estrato"], paquete["offset_relativo_global"]
    _, pneg = predecir(paquete, _fila_completa())
    assert pneg == pytest.approx(1.5 * 61.0)
