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


def _claves_pares(filas: pd.DataFrame) -> list:
    return list(zip(filas["codigo_item"].astype(str), filas["sucursal"].astype(str)))


def _offsets_relativos(paquete: dict, filas: pd.DataFrame) -> np.ndarray:
    """Offset conformal (en unidades relativas, `y/base`) del estrato de cada par; 0 si el paquete no está calibrado."""
    if "offset_relativo_global" not in paquete:
        return np.zeros(len(filas))
    por_par = paquete.get("estrato_por_par", {})
    por_estrato = paquete.get("offset_relativo_por_estrato", {})
    return np.array([float(por_estrato.get(por_par.get(clave), paquete["offset_relativo_global"]))
                     for clave in _claves_pares(filas)])


def _nivel(filas: pd.DataFrame) -> np.ndarray:
    return filas["nivel_medio_60d"].to_numpy(dtype=float)


def _recortar_en_cero(x) -> np.ndarray:
    """Igual que max(0.0, x) elemento a elemento (también lleva NaN a 0)."""
    x = np.asarray(x, dtype=float)
    return np.where(x > 0.0, x, 0.0)


def predecir_lote(paquete: dict, filas: pd.DataFrame) -> tuple:
    """(pred_q50, pred_q_negocio) como arreglos, una posición por fila de
    features (columnas `paquete['features']` y, según el tipo, `nivel_medio_60d`,
    `codigo_item` y `sucursal`). INV-22: la recomendación de transferencias
    pronostica el catálogo completo en lote; `predecir` es este mismo cálculo
    sobre una fila, así que /api/predict y el lote no pueden divergir."""
    tipo = paquete["tipo"]

    if tipo == "lightgbm":
        X = filas[paquete["features"]]
        p50 = paquete["modelo_q50"].predict(X)
        pneg = _con_offset_conformal(np.asarray(paquete["modelo_qneg"].predict(X), dtype=float), paquete)
    elif tipo == "ensamble":
        X = filas[paquete["features"]]
        w = paquete["peso_tweedie"]
        pred_tw = np.clip(paquete["modelo_tweedie"].predict(X), 0, None)
        p50 = w * pred_tw + (1 - w) * paquete["modelo_lgb_q50"].predict(X)
        pneg_tw = pred_tw * paquete["factor_qneg_tweedie"]
        pneg = _con_offset_conformal(w * pneg_tw + (1 - w) * paquete["modelo_lgb_qneg"].predict(X), paquete)
    elif tipo == "relativo":
        X = filas[paquete["features"]]
        base = _nivel(filas) * paquete["horizonte"] + paquete.get("base_offset", 1.0)
        p50 = np.asarray(paquete["modelo_q50"].predict(X), dtype=float) * base
        pneg = (np.asarray(paquete["modelo_qneg"].predict(X), dtype=float) + _offsets_relativos(paquete, filas)) * base
    elif tipo == "baseline_cuantil":
        piso = _nivel(filas) * paquete["horizonte"]
        razon = np.array([paquete["razon_cuantil_por_estrato"].get(paquete["estrato_por_par"].get(clave),
                                                                   paquete["razon_cuantil_global"])
                          for clave in _claves_pares(filas)], dtype=float)
        p50 = piso
        pneg = razon * (piso + 1.0)
    else:
        raise ValueError(f"tipo de modelo desconocido: {tipo}")

    return _recortar_en_cero(p50), _recortar_en_cero(pneg)


def predecir(paquete: dict, fila_features: pd.DataFrame) -> tuple:
    """Devuelve (pred_q50, pred_q_negocio) para una fila de features (1 fila, con las columnas
    `paquete['features']` y, para `baseline_cuantil`, `nivel_medio_60d`, `codigo_item` y `sucursal`)."""
    p50, pneg = predecir_lote(paquete, fila_features)
    return float(p50[0]), float(pneg[0])


def _con_offset_conformal(pneg, paquete: dict):
    """Offset de recalibración conformal en unidades del target (solo paquetes v1, INV-17)."""
    offset = paquete.get("offset_conformal_qneg")
    return pneg + offset if offset else pneg
