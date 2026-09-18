#!/usr/bin/env python3
"""
INV-17 -- Entrena los 3 modelos campeones de Nivel 1 (pronóstico de
demanda acumulada a 15 días) sobre TODO el histórico disponible en
`matriz_as_of.parquet` (07), y los serializa para uso futuro por un
endpoint de predicción (HU aparte, no incluida acá).

Reusa exactamente la configuración de `08_nivel1_demanda.ipynb`
(`MODELOS_POR_RAMA`, `CONFORMAL_QNEG_RAMAS`, `COSTOS_SUPUESTOS`) --
copiada literal, no reinventada -- porque esa notebook es donde se
decidió, con evidencia (5 rondas de búsqueda en MLflow, ver
docs/INV-17-modelo-baseline.md), cuál modelo usar en cada rama. A
diferencia de la notebook, que evalúa con walk-forward (train = folds
anteriores, test = fold actual, para poder medir WAPE contra el piso),
este script entrena sobre el 100% de las filas disponibles -- el
objetivo aquí no es medir desempeño (ya se midió en 08), es producir el
mejor modelo posible para producción con toda la historia.

Cada rama se serializa como un único diccionario (joblib) que trae todo
lo necesario para predecir sin volver a leer este script: el/los modelo(s)
entrenado(s), el peso de ensamble si aplica, el factor empírico de
Tweedie para el cuantil de negocio, y el offset de recalibración
conformal si la rama lo requiere (None si no).
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common_priorizacion import PARAMS, DW, registrar_huella, verificar_huella  # noqa: E402

import joblib
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.linear_model import TweedieRegressor

import mlflow

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
SEMILLA = 42
FRACCION_CALIB_CONFORMAL = 0.2
EXPERIMENTO_MLFLOW = "INV-17-inventaio-modelos-produccion"

FEATURES = [
    'trail_15', 'trail_15_prev', 'nivel_medio_60d', 'dias_desde_ultima_venta',
    'frecuencia_as_of', 'adi_as_of', 'cv2_as_of', 'racha_max_as_of',
    'factor_calendario_ventana',
    'cond1_espacio_bodega', 'cond2_perecedero', 'cond3_refrigerado',
    'cond4_papel_higienico', 'cond5_temporada',
]
TARGET = 'target_demanda_15d'

# -- Copiado literal de 08_nivel1_demanda.ipynb (secciones 1 y 4) --
COSTOS_SUPUESTOS = {
    'no_perecedero': {'Cu': 0.25, 'Co': 0.03, 'fuente': 'SUPUESTO -- pendiente de validar con el negocio'},
    'perecedero':    {'Cu': 0.20, 'Co': 1.00, 'fuente': 'SUPUESTO -- Co=1.0 asume merma total en <=15 días'},
}
ALPHA_NEGOCIO = {k: round(v['Cu'] / (v['Cu'] + v['Co']), 3) for k, v in COSTOS_SUPUESTOS.items()}

CONFORMAL_QNEG_RAMAS = {'suave_no_perecedero', 'suave_perecedero'}

MODELOS_POR_RAMA = {
    'intermitente': dict(
        tipo='lightgbm',
        hparams=dict(n_estimators=434, learning_rate=0.024519102885452573, num_leaves=78,
                      min_child_samples=15, subsample=0.9970808772067912,
                      colsample_bytree=0.9481956384345176, reg_alpha=0.007967207011040096,
                      reg_lambda=0.005279685262967796),
    ),
    'suave_no_perecedero': dict(
        tipo='ensamble', peso_tweedie=0.5,
        hparams_tweedie=dict(power=0.0, alpha=0.02308885287766703, max_iter=500),
        hparams_lgb=dict(n_estimators=300, num_leaves=38, learning_rate=0.07533347347563407,
                          min_child_samples=4, subsample=0.9358084517750064,
                          colsample_bytree=0.8791853785599868, reg_alpha=0.016628468861294637,
                          reg_lambda=0.00775652478047546),
    ),
    'suave_perecedero': dict(
        tipo='ensamble', peso_tweedie=0.6,
        hparams_tweedie=dict(power=0.0, alpha=9.544801633403491, max_iter=500),
        hparams_lgb=dict(n_estimators=148, num_leaves=51, learning_rate=0.04741977651875821,
                          min_child_samples=3, subsample=0.9485653138965411,
                          colsample_bytree=0.6423041259413171, reg_alpha=0.009274600398466618,
                          reg_lambda=0.0014308289072610312),
    ),
}

RAMA_A_CONDICION = {
    'suave_no_perecedero': lambda d: (d['familia_modelo'] == 'suave') & (d['cond2_perecedero'] == 0),
    'suave_perecedero': lambda d: (d['familia_modelo'] == 'suave') & (d['cond2_perecedero'] == 1),
    'intermitente': lambda d: d['familia_modelo'] == 'intermitente',
}


def _alpha_negocio_de(rama: str) -> float:
    if 'perecedero' in rama and 'no_' not in rama:
        return ALPHA_NEGOCIO['perecedero']
    return ALPHA_NEGOCIO['no_perecedero']


def _entrena_tweedie_completo(X, y, hparams, alpha_neg):
    modelo = TweedieRegressor(**hparams)
    modelo.fit(X, y)
    pred_media = np.clip(modelo.predict(X), 1e-6, None)
    factor_qneg = float(np.quantile(y.to_numpy() / pred_media, alpha_neg))
    return modelo, factor_qneg


def _entrena_lightgbm_q(X, y, alpha, hparams):
    m = lgb.LGBMRegressor(objective='quantile', alpha=alpha, subsample_freq=1,
                           random_state=SEMILLA, verbose=-1, **hparams)
    m.fit(X, y)
    return m


def _prediccion_qneg_para_calibracion(X_fit, y_fit, X_calib, alpha_neg, modelo_spec):
    """Reentrena SOLO sobre `fit` (no el modelo final) para medir residuales
    de calibración sobre `calib` sin fuga -- igual método que 08."""
    if modelo_spec['tipo'] == 'lightgbm':
        mneg = _entrena_lightgbm_q(X_fit, y_fit, alpha_neg, modelo_spec['hparams'])
        return mneg.predict(X_calib)
    w = modelo_spec['peso_tweedie']
    tw, factor = _entrena_tweedie_completo(X_fit, y_fit, modelo_spec['hparams_tweedie'], alpha_neg)
    pred_tw = np.clip(tw.predict(X_calib), 0, None) * factor
    mneg_lgb = _entrena_lightgbm_q(X_fit, y_fit, alpha_neg, modelo_spec['hparams_lgb'])
    return w * pred_tw + (1 - w) * mneg_lgb.predict(X_calib)


def _offset_conformal(datos_rama, alpha_neg, modelo_spec, fraccion_calib=FRACCION_CALIB_CONFORMAL):
    """Split-CQR sobre el 100% del histórico de la rama: separa
    cronológicamente (por fecha_origen) en fit (80%)/calib (20% más
    reciente), mide el residual del cuantil de negocio en calib con un
    modelo entrenado solo en fit, y devuelve el cuantil alpha de esos
    residuales -- mismo método que `08_nivel1_demanda.ipynb` sección 4,
    aplicado aquí sobre toda la historia en vez de sobre cada fold."""
    fechas = np.sort(datos_rama['fecha_origen'].unique())
    corte = fechas[int(len(fechas) * (1 - fraccion_calib))]
    fit = datos_rama.loc[datos_rama['fecha_origen'] < corte]
    calib = datos_rama.loc[datos_rama['fecha_origen'] >= corte]
    if len(fit) < 100 or len(calib) < 30:
        print(f'    AVISO: fit/calib insuficiente para conformal (fit={len(fit)}, calib={len(calib)}) -- offset=None')
        return None
    pred_calib = _prediccion_qneg_para_calibracion(fit[FEATURES], fit[TARGET], calib[FEATURES], alpha_neg, modelo_spec)
    residuales = calib[TARGET].to_numpy() - pred_calib
    n = len(residuales)
    nivel_ajustado = min(1.0, np.ceil((n + 1) * alpha_neg) / n)
    return float(np.quantile(residuales, nivel_ajustado))


def entrenar_rama_final(rama: str, datos_rama: pd.DataFrame) -> dict:
    """Entrena el modelo final de una rama sobre el 100% de sus filas
    disponibles. Devuelve el paquete completo a serializar."""
    modelo_spec = MODELOS_POR_RAMA[rama]
    alpha_neg = _alpha_negocio_de(rama)
    X, y = datos_rama[FEATURES], datos_rama[TARGET]

    print(f'  {rama} ({modelo_spec["tipo"]}): entrenando sobre {len(datos_rama):,} filas '
          f'(alpha_negocio={alpha_neg})')

    if modelo_spec['tipo'] == 'lightgbm':
        modelo_q50 = _entrena_lightgbm_q(X, y, 0.5, modelo_spec['hparams'])
        modelo_qneg = _entrena_lightgbm_q(X, y, alpha_neg, modelo_spec['hparams'])
        paquete = {
            'tipo': 'lightgbm',
            'modelo_q50': modelo_q50,
            'modelo_qneg': modelo_qneg,
        }
    elif modelo_spec['tipo'] == 'ensamble':
        w = modelo_spec['peso_tweedie']
        modelo_tweedie, factor_qneg_tweedie = _entrena_tweedie_completo(X, y, modelo_spec['hparams_tweedie'], alpha_neg)
        modelo_lgb_q50 = _entrena_lightgbm_q(X, y, 0.5, modelo_spec['hparams_lgb'])
        modelo_lgb_qneg = _entrena_lightgbm_q(X, y, alpha_neg, modelo_spec['hparams_lgb'])
        paquete = {
            'tipo': 'ensamble',
            'peso_tweedie': w,
            'modelo_tweedie': modelo_tweedie,
            'factor_qneg_tweedie': factor_qneg_tweedie,
            'modelo_lgb_q50': modelo_lgb_q50,
            'modelo_lgb_qneg': modelo_lgb_qneg,
        }
    else:
        raise ValueError(f"tipo de modelo desconocido: {modelo_spec['tipo']}")

    offset_conformal = None
    if rama in CONFORMAL_QNEG_RAMAS:
        offset_conformal = _offset_conformal(datos_rama, alpha_neg, modelo_spec)
        print(f'    offset conformal (q_negocio): {offset_conformal}')

    paquete.update({
        'rama': rama,
        'alpha_negocio': alpha_neg,
        'offset_conformal_qneg': offset_conformal,
        'features': FEATURES,
        'target': TARGET,
        'hparams': modelo_spec,
        'n_filas_entrenamiento': len(datos_rama),
    })
    return paquete


def main():
    verificar_huella('huella_07.json', ['matriz_as_of.parquet', 'piso_interno_por_patron.csv'])
    matriz = pd.read_parquet(f'{DW}/matriz_as_of.parquet')
    faltantes = [c for c in FEATURES if c not in matriz.columns]
    assert not faltantes, f'features ausentes en la matriz: {faltantes}'

    resultados_por_rama_path = DW / "resultados_nivel_1_por_rama.csv"
    metricas_walk_forward = {}
    if resultados_por_rama_path.is_file():
        metricas_walk_forward = (
            pd.read_csv(resultados_por_rama_path, index_col=0).to_dict('index')
        )
    else:
        print('AVISO: no se encontró resultados_nivel_1_por_rama.csv -- '
              'corré 08_nivel1_demanda.ipynb antes para tener las métricas de referencia.')

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    tracking_uri = os.environ.get('MLFLOW_TRACKING_URI', 'http://127.0.0.1:5000')
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(EXPERIMENTO_MLFLOW)
    print(f'MLflow tracking URI: {tracking_uri} | experimento: {EXPERIMENTO_MLFLOW}')

    metadata = {
        'hu': 'INV-17',
        'fecha_generacion': datetime.now(timezone.utc).isoformat(),
        'features': FEATURES,
        'target': TARGET,
        'costos_supuestos': COSTOS_SUPUESTOS,
        'alpha_negocio': ALPHA_NEGOCIO,
        'conformal_qneg_ramas': sorted(CONFORMAL_QNEG_RAMAS),
        'entrada_matriz': registrar_huella(['matriz_as_of.parquet']),
        'metricas_walk_forward_referencia': metricas_walk_forward,
        'nota_metricas': (
            'Las métricas de arriba vienen de la validación walk-forward de '
            '08_nivel1_demanda.ipynb (train=folds anteriores, test=fold actual) -- '
            'NO son el desempeño del modelo exportado acá, que se reentrena sobre el '
            '100% del histórico para producción y no tiene un conjunto de test propio.'
        ),
        'ramas': {},
    }

    for rama, condicion in RAMA_A_CONDICION.items():
        datos_rama = matriz.loc[condicion(matriz)].copy()
        paquete = entrenar_rama_final(rama, datos_rama)

        modelo_path = MODELS_DIR / f'nivel1_{rama}.joblib'
        joblib.dump(paquete, modelo_path)
        print(f'    guardado: {modelo_path}')

        metadata['ramas'][rama] = {
            'archivo': modelo_path.name,
            'tipo_modelo': paquete['tipo'],
            'alpha_negocio': paquete['alpha_negocio'],
            'offset_conformal_qneg': paquete['offset_conformal_qneg'],
            'n_filas_entrenamiento': paquete['n_filas_entrenamiento'],
        }

        with mlflow.start_run(run_name=f'nivel1_{rama}_produccion'):
            mlflow.set_tags({'hu': 'INV-17', 'rama': rama, 'tipo_modelo': paquete['tipo']})
            mlflow.log_params({
                'alpha_negocio': paquete['alpha_negocio'],
                'n_filas_entrenamiento': paquete['n_filas_entrenamiento'],
                'offset_conformal_qneg': paquete['offset_conformal_qneg'],
            })
            if rama in metricas_walk_forward:
                for k, v in metricas_walk_forward[rama].items():
                    if isinstance(v, (int, float)) and not pd.isna(v):
                        mlflow.log_metric(f'walkforward_{k}', float(v))
            mlflow.log_artifact(str(modelo_path))

    metadata_path = MODELS_DIR / "nivel1_metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False, default=str)
    print(f'\nguardado: {metadata_path}')
    print('\nListo. Endpoint de predicción que consuma estos .joblib: HU aparte (no incluida acá).')


if __name__ == "__main__":
    main()
