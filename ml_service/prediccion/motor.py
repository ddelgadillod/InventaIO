"""
InventAI/o — ML Service: motor de predicción
INV-20: función PURA de predicción -- misma lógica que
notebooks/exportar_modelos_nivel1.py (v1, INV-17) y
notebooks/exportar_modelos_nivel1_v2.py (fase E del fix del EDA), pero solo la
mitad de PREDECIR (los modelos ya vienen entrenados y cargados, no se
reentrenan acá). Sin I/O, fácil de testear con modelos falsos (ver
tests/test_motor.py).

Tipos de paquete soportados:
- `lightgbm` y `ensamble`: modelos v1 sobre el target absoluto (con offset conformal opcional).
- `relativo`: LightGBM cuantílico sobre `y/base`, con `base = nivel_medio_60d * horizonte + base_offset`;
  la predicción es `base * q`. Si el paquete trae `offset_relativo_por_estrato` / `offset_relativo_global`
  (recalibración conformal por estrato de volumen), el cuantil de negocio es `base * (q + offset_estrato)`.
- `baseline_cuantil`: sin modelo entrenado. q50 = media móvil (`nivel_medio_60d * horizonte`) y cuantil de
  negocio = `razon_cuantil(estrato) * (media_movil + 1)`, con la razón empírica por estrato de volumen
  del par (`estrato_por_par`) y un valor global de respaldo si el par no tiene estrato.
"""
import numpy as np
import pandas as pd


def _clave_par(fila_features: pd.DataFrame) -> tuple:
    return (str(fila_features["codigo_item"].iloc[0]), str(fila_features["sucursal"].iloc[0]))


def _offset_relativo(paquete: dict, fila_features: pd.DataFrame) -> float:
    """Offset conformal (en unidades relativas, `y/base`) del estrato del par; 0 si el paquete no está calibrado."""
    if "offset_relativo_global" not in paquete:
        return 0.0
    estrato = paquete.get("estrato_por_par", {}).get(_clave_par(fila_features))
    return float(paquete.get("offset_relativo_por_estrato", {}).get(estrato, paquete["offset_relativo_global"]))


def _base_relativa(paquete: dict, fila_features: pd.DataFrame) -> float:
    nivel = float(fila_features["nivel_medio_60d"].iloc[0])
    return nivel * paquete["horizonte"] + paquete.get("base_offset", 1.0)


def predecir(paquete: dict, fila_features: pd.DataFrame) -> tuple:
    """Devuelve (pred_q50, pred_q_negocio) para una fila de features (1 fila, con las columnas
    `paquete['features']` y, para `baseline_cuantil`, `nivel_medio_60d`, `codigo_item` y `sucursal`)."""
    tipo = paquete["tipo"]

    if tipo == "lightgbm":
        X = fila_features[paquete["features"]]
        p50 = float(paquete["modelo_q50"].predict(X)[0])
        pneg = float(paquete["modelo_qneg"].predict(X)[0])
        pneg = _con_offset_conformal(pneg, paquete)
    elif tipo == "ensamble":
        X = fila_features[paquete["features"]]
        w = paquete["peso_tweedie"]
        pred_tw = np.clip(paquete["modelo_tweedie"].predict(X), 0, None)
        p50 = float(w * pred_tw[0] + (1 - w) * paquete["modelo_lgb_q50"].predict(X)[0])
        pneg_tw = pred_tw[0] * paquete["factor_qneg_tweedie"]
        pneg = float(w * pneg_tw + (1 - w) * paquete["modelo_lgb_qneg"].predict(X)[0])
        pneg = _con_offset_conformal(pneg, paquete)
    elif tipo == "relativo":
        X = fila_features[paquete["features"]]
        base = _base_relativa(paquete, fila_features)
        p50 = float(paquete["modelo_q50"].predict(X)[0]) * base
        pneg = (float(paquete["modelo_qneg"].predict(X)[0]) + _offset_relativo(paquete, fila_features)) * base
    elif tipo == "baseline_cuantil":
        piso = float(fila_features["nivel_medio_60d"].iloc[0]) * paquete["horizonte"]
        estrato = paquete["estrato_por_par"].get(_clave_par(fila_features))
        razon = paquete["razon_cuantil_por_estrato"].get(estrato, paquete["razon_cuantil_global"])
        p50 = piso
        pneg = razon * (piso + 1.0)
    else:
        raise ValueError(f"tipo de modelo desconocido: {tipo}")

    return max(0.0, p50), max(0.0, pneg)


def _con_offset_conformal(pneg: float, paquete: dict) -> float:
    """Offset de recalibración conformal en unidades del target (solo paquetes v1, INV-17)."""
    offset = paquete.get("offset_conformal_qneg")
    return pneg + offset if offset else pneg
