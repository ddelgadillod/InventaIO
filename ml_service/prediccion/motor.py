"""
InventAI/o — ML Service: motor de predicción
INV-20: función PURA de predicción -- misma lógica de blending que
notebooks/exportar_modelos_nivel1.py (INV-17), pero solo la mitad de
PREDECIR (los modelos ya vienen entrenados y cargados, no se reentrenan
acá). Sin I/O, fácil de testear con modelos falsos (ver tests/test_motor.py).
"""
import numpy as np
import pandas as pd


def predecir(paquete: dict, fila_features: pd.DataFrame) -> tuple:
    """Devuelve (pred_q50, pred_q_negocio) para una fila de features (1
    fila, columnas = paquete['features']), aplicando el offset de
    recalibración conformal si la rama lo tiene (INV-17)."""
    X = fila_features[paquete["features"]]

    if paquete["tipo"] == "lightgbm":
        p50 = float(paquete["modelo_q50"].predict(X)[0])
        pneg = float(paquete["modelo_qneg"].predict(X)[0])
    elif paquete["tipo"] == "ensamble":
        w = paquete["peso_tweedie"]
        pred_tw = np.clip(paquete["modelo_tweedie"].predict(X), 0, None)
        p50 = float(w * pred_tw[0] + (1 - w) * paquete["modelo_lgb_q50"].predict(X)[0])
        pneg_tw = pred_tw[0] * paquete["factor_qneg_tweedie"]
        pneg = float(w * pneg_tw + (1 - w) * paquete["modelo_lgb_qneg"].predict(X)[0])
    else:
        raise ValueError(f"tipo de modelo desconocido: {paquete['tipo']}")

    offset = paquete.get("offset_conformal_qneg")
    if offset:
        pneg = pneg + offset

    return max(0.0, p50), max(0.0, pneg)
