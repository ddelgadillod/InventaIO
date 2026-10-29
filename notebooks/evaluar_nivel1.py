"""
Arnés de evaluación robusta para los experimentos de Nivel 1 (fase A del
roadmap de modelado, rama fix/eda-modelado-nivel1).

Existe porque las rondas 1-5 de búsqueda (383 corridas) compartieron los
mismos 4 folds con los que se reporta, y las diferencias frente al piso
(media móvil) son de 0.5-2.5%: sin un intervalo de confianza no se puede
distinguir mejora real de ruido. Todo experimento posterior (07b, 10, 11,
12, 13) debe reportar con estas funciones, no con un WAPE agregado suelto.

Unidad de remuestreo = `codigo_item`: las filas de un mismo producto
(varias sucursales, varios orígenes) están correlacionadas, así que
remuestrear filas sueltas subestimaría la incertidumbre.

Política de holdout (ver `POLITICA_HOLDOUT`): la búsqueda de
hiperparámetros solo puede usar los folds de `FOLDS_BUSQUEDA`; el
`FOLD_HOLDOUT` se reporta una sola vez al cierre de cada fase. LIMITACIÓN
HONESTA: el fold 5 ya fue visto por las rondas 1-5, así que no es un
holdout virgen; solo protege de la contaminación que se agregue a partir
de ahora. Un holdout limpio requiere ventas posteriores a 2025-12-31.
"""
import os

import numpy as np
import pandas as pd

MIN_FILAS_ENTRENAMIENTO = 200   # misma regla que 08: con menos filas de entrenamiento la combinación rama x fold se omite
FOLDS_BUSQUEDA = (2, 3, 4)
FOLD_HOLDOUT = 5
POLITICA_HOLDOUT = {
    'folds_busqueda': list(FOLDS_BUSQUEDA),
    'fold_holdout': FOLD_HOLDOUT,
    'holdout_virgen': False,
    'nota': 'fold 5 fue usado por las rondas 1-5 de busqueda (INV-62/63); '
            'solo protege contra contaminacion nueva. Holdout limpio = ventas 2026.',
}
MLFLOW_URI_DEFECTO = 'http://127.0.0.1:5000'


def wape(y, yhat):
    y, yhat = np.asarray(y, dtype=float), np.asarray(yhat, dtype=float)
    denom = np.abs(y).sum()
    return float(np.abs(y - yhat).sum() / denom) if denom else np.nan


def _sumas_por_producto(df, col_y, col_modelo, col_piso):
    g = pd.DataFrame({
        'item': df['codigo_item'].to_numpy(),
        'e_m': (df[col_y] - df[col_modelo]).abs().to_numpy(),
        'e_b': (df[col_y] - df[col_piso]).abs().to_numpy(),
        'y': df[col_y].abs().to_numpy(),
    }).groupby('item', observed=True).sum()
    return g['e_m'].to_numpy(), g['e_b'].to_numpy(), g['y'].to_numpy()


def mejora_con_ic(df, col_y, col_modelo, col_piso, B=2000, semilla=0):
    """Mejora relativa del modelo sobre el piso, (WAPE_piso - WAPE_modelo)/WAPE_piso,
    con IC 95% por bootstrap de productos. Positivo = el modelo gana."""
    e_m, e_b, y = _sumas_por_producto(df, col_y, col_modelo, col_piso)
    n = len(y)
    if n < 2 or y.sum() == 0:
        return dict(n_filas=len(df), n_productos=n, wape_modelo=np.nan, wape_piso=np.nan,
                    mejora_rel=np.nan, ic_bajo=np.nan, ic_alto=np.nan, p_mejora_positiva=np.nan)
    rng = np.random.default_rng(semilla)
    idx = rng.integers(0, n, size=(B, n))
    den = y[idx].sum(axis=1)
    w_m, w_b = e_m[idx].sum(axis=1) / den, e_b[idx].sum(axis=1) / den
    mej = (w_b - w_m) / w_b
    wm, wb = e_m.sum() / y.sum(), e_b.sum() / y.sum()
    return dict(n_filas=len(df), n_productos=n, wape_modelo=float(wm), wape_piso=float(wb),
                mejora_rel=float((wb - wm) / wb),
                ic_bajo=float(np.quantile(mej, 0.025)), ic_alto=float(np.quantile(mej, 0.975)),
                p_mejora_positiva=float((mej > 0).mean()))


def evaluar_rama(df_rama, col_y, col_modelo, col_piso, B=2000, semilla=0):
    """Tabla: total, por fold, y dejando cada fold afuera (leave-one-fold-out)."""
    filas = [dict(corte='todos', **mejora_con_ic(df_rama, col_y, col_modelo, col_piso, B, semilla))]
    for f in sorted(df_rama['fold_id'].unique()):
        sub = df_rama[df_rama['fold_id'] == f]
        filas.append(dict(corte=f'solo_fold_{f}', **mejora_con_ic(sub, col_y, col_modelo, col_piso, B, semilla)))
    for f in sorted(df_rama['fold_id'].unique()):
        sub = df_rama[df_rama['fold_id'] != f]
        filas.append(dict(corte=f'sin_fold_{f}', **mejora_con_ic(sub, col_y, col_modelo, col_piso, B, semilla)))
    return pd.DataFrame(filas)


def veredicto(tabla):
    """Reglas mecánicas (no escritas a mano): 'supera_con_ic' exige IC95 > 0
    sobre todos los folds; 'robusto' exige además que IC95 > 0 sin el fold
    más favorable (el de mayor mejora puntual)."""
    total = tabla[tabla['corte'] == 'todos'].iloc[0]
    solo = tabla[tabla['corte'].str.startswith('solo_fold_')]
    mejor_fold = int(solo.loc[solo['mejora_rel'].idxmax(), 'corte'].split('_')[-1])
    sin = tabla[tabla['corte'] == f'sin_fold_{mejor_fold}'].iloc[0]
    return dict(
        mejora_rel=float(total['mejora_rel']), ic_bajo=float(total['ic_bajo']), ic_alto=float(total['ic_alto']),
        supera_con_ic=bool(total['ic_bajo'] > 0),
        fold_mas_favorable=mejor_fold,
        mejora_sin_fold_favorable=float(sin['mejora_rel']),
        ic_bajo_sin_fold_favorable=float(sin['ic_bajo']),
        robusto=bool(total['ic_bajo'] > 0 and sin['ic_bajo'] > 0),
    )


def registrar_mlflow(experimento, run_name, params=None, metrics=None, tags=None, artefactos=()):
    """Registro obligatorio de cada fase en MLflow (mismo servidor que INV-17).
    Falla en voz alta si el servidor no responde: un experimento sin registro
    no debe pasar como hecho."""
    import mlflow
    uri = os.environ.get('MLFLOW_TRACKING_URI', MLFLOW_URI_DEFECTO)
    mlflow.set_tracking_uri(uri)
    mlflow.set_experiment(experimento)
    with mlflow.start_run(run_name=run_name) as run:
        # protocolo: desde la corrección del purge todo run nuevo lo declara; los anteriores quedan como 'sin_purge_obsoleto'
        mlflow.set_tags({k: str(v) for k, v in {'protocolo': 'con_purge', **(tags or {})}.items()})
        if params:
            mlflow.log_params({k: (v if isinstance(v, (int, float, str, bool)) else str(v))
                               for k, v in params.items()})
        for k, v in (metrics or {}).items():
            if v is not None and not (isinstance(v, float) and np.isnan(v)):
                mlflow.log_metric(k, float(v))
        for a in artefactos:
            mlflow.log_artifact(str(a))
        return run.info.run_id


def exceso_por_producto(df, col_y, col_modelo, col_piso):
    """Error absoluto del modelo menos el del piso, sumado por producto.
    Positivo = el modelo pierde en ese producto."""
    e_m = (df[col_y] - df[col_modelo]).abs()
    e_b = (df[col_y] - df[col_piso]).abs()
    return (e_m - e_b).groupby(df['codigo_item'].to_numpy()).sum().sort_values(ascending=False)


def concentracion_exceso(df, col_y, col_modelo, col_piso, k=10):
    """Por fold: qué parte del exceso de error positivo concentran los k peores
    productos, y si el peor solo explica más que el exceso neto del fold."""
    filas = []
    for f, sub in df.groupby('fold_id'):
        ex = exceso_por_producto(sub, col_y, col_modelo, col_piso)
        pos = ex.clip(lower=0).sum()
        filas.append(dict(fold_id=int(f), exceso_neto=float(ex.sum()), exceso_positivo=float(pos),
                          peor_producto=str(ex.index[0]), exceso_peor_producto=float(ex.iloc[0]),
                          share_top_k=float(ex.head(k).sum() / pos) if pos else np.nan,
                          peor_explica_mas_que_neto=bool(ex.iloc[0] > ex.sum() > 0)))
    return pd.DataFrame(filas)


def mejora_sin_peor_producto(df, col_y, col_modelo, col_piso, B=2000, semilla=0):
    """Sensibilidad: mejora con IC quitando el producto que más exceso de error concentra."""
    peor = exceso_por_producto(df, col_y, col_modelo, col_piso).index[0]
    r = mejora_con_ic(df[df['codigo_item'] != peor], col_y, col_modelo, col_piso, B, semilla)
    return dict(producto_excluido=str(peor), **r)


def pinball(y, q, alpha):
    """Pérdida pinball (cuantil `alpha`) por fila. Con Cu=alpha y Co=1-alpha coincide con el costo del vendedor de periódicos."""
    d = np.asarray(y, dtype=float) - np.asarray(q, dtype=float)
    return np.maximum(alpha * d, (alpha - 1.0) * d)


def costo_asimetrico(y, q, Cu, Co):
    """Costo por fila: Cu por unidad de demanda no cubierta, Co por unidad sobrante."""
    d = np.asarray(y, dtype=float) - np.asarray(q, dtype=float)
    return Cu * np.maximum(d, 0.0) + Co * np.maximum(-d, 0.0)


def mejora_perdida_con_ic(df, perdida_modelo, perdida_base, B=2000, semilla=0):
    """Mejora relativa de una pérdida agregada (suma) del modelo sobre una base, (L_base - L_modelo)/L_base,
    con IC95 por bootstrap de productos. `perdida_*` son arreglos alineados con `df`. Positivo = el modelo pierde menos."""
    g = pd.DataFrame({'item': df['codigo_item'].to_numpy(), 'm': np.asarray(perdida_modelo, dtype=float),
                      'b': np.asarray(perdida_base, dtype=float)}).groupby('item', observed=True).sum()
    lm, lb, n = g['m'].to_numpy(), g['b'].to_numpy(), len(g)
    if n < 2 or lb.sum() == 0:
        return dict(n_productos=n, perdida_modelo=np.nan, perdida_base=np.nan, mejora_rel=np.nan, ic_bajo=np.nan, ic_alto=np.nan)
    idx = np.random.default_rng(semilla).integers(0, n, size=(B, n))
    mej = 1.0 - lm[idx].sum(axis=1) / lb[idx].sum(axis=1)
    return dict(n_productos=n, perdida_modelo=float(lm.sum()), perdida_base=float(lb.sum()), mejora_rel=float(1.0 - lm.sum() / lb.sum()),
                ic_bajo=float(np.quantile(mej, 0.025)), ic_alto=float(np.quantile(mej, 0.975)))
