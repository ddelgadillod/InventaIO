"""
Variantes de modelo de Nivel 1 usadas por las fases C y D (rama fix/eda-modelado-nivel1).

Misma configuración (`MODELOS_POR_RAMA`, sin búsqueda) que el baseline de 08 / exportar_modelos_nivel1.py;
lo único que cambia entre variantes es la forma del target. Parametrizado por horizonte `H` y por los
nombres de columna, porque en `matriz_as_of_h{H}.parquet` el target y los lags se llaman `..._{H}d`.

Modos:
  v1      -- aprende `y` (replica 08 exactamente)
  rel_w   -- aprende `y/base` con peso `base` en la pérdida (equivale al mismo L1 en unidades originales)
  rel     -- aprende `y/base` sin pesos (error relativo)
  res_mm  -- aprende `y - media_movil`
con base = nivel_medio_60d * H + 1.
"""
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.linear_model import TweedieRegressor

from exportar_modelos_nivel1 import (MODELOS_POR_RAMA, _entrena_lightgbm_q, _entrena_tweedie_completo,
                                     _alpha_negocio_de, SEMILLA)

MODOS = ('v1', 'rel_w', 'rel', 'res_mm')


def _lgb(X, y, alpha, hp, w=None):
    mod = lgb.LGBMRegressor(objective='quantile', alpha=alpha, subsample_freq=1, random_state=SEMILLA,
                            verbose=-1, **hp)
    mod.fit(X, y, sample_weight=w)
    return mod


def _tw(X, y, hp, w=None):
    mod = TweedieRegressor(**hp)
    mod.fit(X, y, sample_weight=w)
    return mod


def predecir_q50(rama, modo, tr, te, cols, y_col, piso_col, H):
    """Predicción q50 en unidades originales del target acumulado a H días."""
    spec = MODELOS_POR_RAMA[rama]
    base_tr, base_te = tr['nivel_medio_60d'] * H + 1.0, te['nivel_medio_60d'] * H + 1.0
    X, Xt = tr[cols], te[cols]
    if modo == 'v1':
        y = tr[y_col]
        if spec['tipo'] == 'lightgbm':
            return _entrena_lightgbm_q(X, y, 0.5, spec['hparams']).predict(Xt)
        tw, _ = _entrena_tweedie_completo(X, y, spec['hparams_tweedie'], _alpha_negocio_de(rama))
        lg = _entrena_lightgbm_q(X, y, 0.5, spec['hparams_lgb'])
        w = spec['peso_tweedie']
        return w * np.clip(tw.predict(Xt), 0, None) + (1 - w) * lg.predict(Xt)
    if modo == 'rel_w':
        y, w, inv = tr[y_col] / base_tr, base_tr, (lambda p: p * base_te)
    elif modo == 'rel':
        y, w, inv = tr[y_col] / base_tr, None, (lambda p: p * base_te)
    elif modo == 'res_mm':
        y, w, inv = tr[y_col] - tr[piso_col], None, (lambda p: te[piso_col].to_numpy() + p)
    else:
        raise ValueError(f'modo desconocido: {modo}')
    if spec['tipo'] == 'lightgbm':
        p = _lgb(X, y, 0.5, spec['hparams'], w).predict(Xt)
    else:
        wt = spec['peso_tweedie']
        p = (wt * _tw(X, y, spec['hparams_tweedie'], w).predict(Xt)
             + (1 - wt) * _lgb(X, y, 0.5, spec['hparams_lgb'], w).predict(Xt))
    return np.clip(np.asarray(inv(p), dtype=float), 0, None)


def offset_conformal(residuales, alpha):
    """Cuantil conformal de muestra finita (split-CQR): nivel `ceil((n+1)*alpha)/n` de los residuales firmados."""
    n = len(residuales)
    return float(np.quantile(residuales, min(1.0, np.ceil((n + 1) * alpha) / n)))


def offsets_conformal_relativos(datos, estrato_fila, alpha, hparams, features, target, horizonte=15,
                                fraccion_calib=0.2, min_calib_estrato=30, estratos=('cabeza', 'medio', 'cola')):
    """Recalibración split-CQR del cuantil relativo (`y/base`), con un offset por estrato.

    Separa `datos` cronológicamente (por `fecha_origen`) en fit / calib, **con purge** (la ventana objetivo de las
    filas de fit, `fin_ventana`, no toca el periodo de calib); entrena el LightGBM cuantílico en fit, mide el
    residual `y/base - q` en calib y lo resume por estrato. Un estrato con menos de `min_calib_estrato` filas de
    calib usa el offset global. Es exactamente el procedimiento de `14_calibracion_conformal_estrato.ipynb`.
    `datos` debe traer `fecha_origen`, `fin_ventana`, `nivel_medio_60d`, `features` y `target`;
    `estrato_fila` es un arreglo con el estrato de cada fila de `datos`.
    Devuelve dict(por_estrato, global_, n_calib_por_estrato, n_fit, n_calib, corte)."""
    estrato_fila = np.asarray(estrato_fila)
    base = (datos['nivel_medio_60d'] * horizonte + 1.0).to_numpy()
    fechas = np.sort(datos['fecha_origen'].unique())
    corte = fechas[int(len(fechas) * (1 - fraccion_calib))]
    en_fit = ((datos['fecha_origen'] < corte) & (datos['fin_ventana'] < corte)).to_numpy()
    en_cal = (datos['fecha_origen'] >= corte).to_numpy()
    y_rel = datos[target].to_numpy() / base
    mod = _lgb(datos.loc[en_fit, features], y_rel[en_fit], alpha, hparams)
    residual = y_rel[en_cal] - mod.predict(datos.loc[en_cal, features])
    global_ = offset_conformal(residual, alpha)
    por_estrato, n_est = {}, {}
    for e in estratos:
        r = residual[estrato_fila[en_cal] == e]
        n_est[e] = int(len(r))
        por_estrato[e] = offset_conformal(r, alpha) if len(r) >= min_calib_estrato else global_
    return dict(por_estrato=por_estrato, global_=global_, n_calib_por_estrato=n_est, n_fit=int(en_fit.sum()),
                n_calib=int(en_cal.sum()), corte=str(pd.Timestamp(corte).date()))
