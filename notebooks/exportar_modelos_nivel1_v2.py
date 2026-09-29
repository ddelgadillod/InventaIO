#!/usr/bin/env python3
"""
INV-17 v2 -- exporta los modelos de Nivel 1 con la política decidida en la fase E del fix del EDA
(docs/FIX-EDA-MODELADO-NIVEL1.md). Reemplaza a `exportar_modelos_nivel1.py` (v1, que sigue disponible
para regenerar la variante baseline) y escribe en los mismos archivos que consume `ml_service`
(`models/nivel1_<rama>.joblib` + `models/nivel1_metadata.json`).

Política (decisión del usuario del 2026-09-24 sobre las recomendaciones de la fase E):

- `intermitente` -> tipo `relativo`: LightGBM cuantílico sobre el target relativo `y/base`
  (`base = nivel_medio_60d * H + 1`), q50 y cuantil de negocio (0.893), con **recalibración conformal
  por estrato** del cuantil de negocio (offsets relativos por estrato de volumen, `--sin-calibracion` la
  desactiva). La calibración es una decisión del usuario para garantizar cobertura por estrato: en
  `14_calibracion_conformal_estrato` logró la cobertura nominal (cabeza 0.82 -> 0.895) pero NO mejoró el
  costo con IC95 ni fue estable en el fold 5, así que la regla pre-registrada no la adoptaba. Antes de
  exportar se verifica que el procedimiento reproduce los offsets del fold 5 de ese notebook. Los
  hiperparámetros salen de `decision_15.json` (los de la re-búsqueda con purge solo si la regla los
  adoptó; si no, los vigentes).
- `suave_no_perecedero` y `suave_perecedero` -> tipo `baseline_cuantil`: sin modelo entrenado. q50 =
  media móvil (`nivel_medio_60d * H`) y cuantil de negocio = `(media_movil + 1) * Q_alpha(razon)`, con
  `razon = y/(media_movil+1)` calculada sobre TODAS las filas de la rama y **por estrato de volumen**
  (cabeza/medio/cola, definidos as-of a la fecha del último dato). En la fase E el cuantil de producción
  de estas ramas (ensamble + conformal) no superó a esta base, que además está calibrada.

Cada paquete es un diccionario serializado con joblib (ver `ml_service/prediccion/motor.py` para cómo
se usa cada `tipo`). No se recalibra ni se evalúa aquí: la evaluación walk-forward vive en los notebooks
09-15 y sus `decision_*.json`, que este script cita como referencia en la metadata.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common_priorizacion import (DW, registrar_huella, verificar_huella, estratos_as_of,  # noqa: E402
                                 leer_calendario_habil, fin_ventana_de, purgar_entrenamiento)
from modelos_nivel1 import offsets_conformal_relativos  # noqa: E402
from exportar_modelos_nivel1 import (FEATURES, RAMA_A_CONDICION, COSTOS_SUPUESTOS, MODELOS_POR_RAMA,  # noqa: E402
                                     ALPHA_NEGOCIO, _alpha_negocio_de, MODELS_DIR, SEMILLA)

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import mlflow

EXPERIMENTO_MLFLOW = "INV-17-inventaio-modelos-produccion-v2"
HORIZONTE = 15
MIN_FILAS_ESTRATO = 30
TARGET = "target_demanda_15d"
ESTRATOS = ("cabeza", "medio", "cola")
CALIBRAR_INTERMITENTE = "--sin-calibracion" not in sys.argv
POLITICA = {
    "intermitente": "relativo",
    "suave_no_perecedero": "baseline_cuantil",
    "suave_perecedero": "baseline_cuantil",
}
FUENTE_POLITICA = "decision del usuario 2026-09-24 sobre las recomendaciones de la fase E (docs/FIX-EDA-MODELADO-NIVEL1.md)"


def _lgb_q(X, y, alpha, hparams):
    mod = lgb.LGBMRegressor(objective="quantile", alpha=alpha, subsample_freq=1, random_state=SEMILLA,
                            verbose=-1, **hparams)
    mod.fit(X, y)
    return mod


def hparams_intermitente():
    """Hiperparámetros de la rama intermitente: los de la re-búsqueda con purge solo si la regla
    de `15_busqueda_hparams_relativo` los adoptó; si no, los vigentes de `MODELOS_POR_RAMA`."""
    vigentes = dict(MODELOS_POR_RAMA["intermitente"]["hparams"])
    ruta = DW / "decision_15.json"
    if not ruta.is_file():
        print("AVISO: no existe decision_15.json -- se usan los hiperparámetros vigentes.")
        return vigentes, "vigentes (sin decision_15.json)"
    d = json.loads(ruta.read_text())
    if d.get("adopta"):
        hp = dict(d["hparams_mejores"])
        return {k: (int(v) if k in ("n_estimators", "num_leaves", "min_child_samples") else float(v))
                for k, v in hp.items()}, "re-busqueda con purge (15), adoptada por la regla"
    return vigentes, "vigentes (la re-busqueda 15 no fue adoptada por la regla)"


def entrenar_relativo(datos_rama, rama, hparams, estrato_por_par, calibrar=True):
    """`tipo='relativo'`: cuantiles LightGBM sobre `y/base`; se predice `base * q`. Con `calibrar`, agrega
    offsets conformales relativos por estrato para el cuantil de negocio (se suman a `q` antes de multiplicar por la base)."""
    alpha = _alpha_negocio_de(rama)
    base = datos_rama["nivel_medio_60d"] * HORIZONTE + 1.0
    X, y_rel = datos_rama[FEATURES], datos_rama[TARGET] / base
    print(f"  {rama} (relativo): entrenando sobre {len(datos_rama):,} filas (alpha_negocio={alpha})")
    paquete = {
        "tipo": "relativo",
        "modelo_q50": _lgb_q(X, y_rel, 0.5, hparams),
        "modelo_qneg": _lgb_q(X, y_rel, alpha, hparams),
        "horizonte": HORIZONTE,
        "base_offset": 1.0,
        "offset_conformal_qneg": None,     # offset absoluto de los paquetes v1: no aplica a este tipo
        "hparams": hparams,
        "estrato_por_par": estrato_por_par,
    }
    if calibrar:
        estrato_fila = [estrato_por_par.get(k, "cola")
                        for k in zip(datos_rama["codigo_item"].astype(str), datos_rama["sucursal"].astype(str))]
        cal = offsets_conformal_relativos(datos_rama, estrato_fila, alpha, hparams, FEATURES, TARGET, HORIZONTE,
                                          min_calib_estrato=MIN_FILAS_ESTRATO)
        paquete["offset_relativo_por_estrato"] = cal["por_estrato"]
        paquete["offset_relativo_global"] = cal["global_"]
        paquete["calibracion"] = {"metodo": "split-CQR por estrato (14_calibracion_conformal_estrato)", "fraccion_calib": 0.2,
                                  "n_fit": cal["n_fit"], "n_calib": cal["n_calib"], "corte_fecha_origen": cal["corte"],
                                  "n_calib_por_estrato": cal["n_calib_por_estrato"]}
        print("    calibración conformal por estrato (offsets relativos): "
              + ", ".join(f"{e} {cal['por_estrato'][e]:+.3f} (n={cal['n_calib_por_estrato'][e]})" for e in ESTRATOS)
              + f" | global {cal['global_']:+.3f} | corte fit/calib {cal['corte']}")
    return paquete


def verificar_contra_14(matriz, hparams):
    """Reproduce los offsets del fold 5 de `14_calibracion_conformal_estrato.ipynb` con la misma función y falla si difieren."""
    ruta = DW / "decision_14.json"
    if not ruta.is_file():
        print("AVISO: no existe decision_14.json -- se omite la verificación contra el notebook 14.")
        return
    esperado = [o for o in json.loads(ruta.read_text())["offsets"] if o["fold_id"] == 5]
    dr = matriz.loc[RAMA_A_CONDICION["intermitente"](matriz)]
    tr = purgar_entrenamiento(dr, 5, verbose=False)
    e5 = pd.read_parquet(DW / "estratos_por_fold_12.parquet")
    e5 = e5[e5["fold_id"] == 5]
    mapa = {(str(r.codigo_item), str(r.sucursal)): r.estrato for r in e5.itertuples()}
    estrato_fila = [mapa[k] for k in zip(tr["codigo_item"].astype(str), tr["sucursal"].astype(str))]
    cal = offsets_conformal_relativos(tr, estrato_fila, _alpha_negocio_de("intermitente"), hparams, FEATURES, TARGET, HORIZONTE,
                                      min_calib_estrato=MIN_FILAS_ESTRATO)
    for o in esperado:
        assert abs(cal["por_estrato"][o["estrato"]] - o["offset_rel"]) < 1e-3, (o, cal["por_estrato"])
        assert abs(cal["global_"] - o["offset_global"]) < 1e-3, (o, cal["global_"])
    print("verificación OK: los offsets por estrato del fold 5 reproducen los de 14_calibracion_conformal_estrato "
          + str({e: round(v, 3) for e, v in cal["por_estrato"].items()}))


def entrenar_baseline(datos_rama, rama, estrato_por_par):
    """`tipo='baseline_cuantil'`: sin modelo. Cuantiles empíricos de `y/(media_movil+1)` por estrato."""
    alpha = _alpha_negocio_de(rama)
    piso = datos_rama["nivel_medio_60d"] * HORIZONTE
    razon = (datos_rama[TARGET] / (piso + 1.0)).to_numpy()
    clave = list(zip(datos_rama["codigo_item"].astype(str), datos_rama["sucursal"].astype(str)))
    est = np.array([estrato_por_par.get(k, "cola") for k in clave])
    global_q = float(np.quantile(razon, alpha))
    por_estrato, n_estrato = {}, {}
    for e in ESTRATOS:
        r = razon[est == e]
        n_estrato[e] = int(len(r))
        por_estrato[e] = float(np.quantile(r, alpha)) if len(r) >= MIN_FILAS_ESTRATO else global_q
    print(f"  {rama} (baseline_cuantil): {len(datos_rama):,} filas | razón Q_{alpha} por estrato: "
          + ", ".join(f"{e} {por_estrato[e]:.3f} (n={n_estrato[e]})" for e in ESTRATOS) + f" | global {global_q:.3f}")
    return {
        "tipo": "baseline_cuantil",
        "horizonte": HORIZONTE,
        "razon_cuantil_por_estrato": por_estrato,
        "razon_cuantil_global": global_q,
        "filas_por_estrato": n_estrato,
        "estrato_por_par": estrato_por_par,
        "offset_conformal_qneg": None,
    }


def referencia_evaluacion():
    """Cifras de evaluación (con purge) que respaldan la política, leídas de los artefactos de los notebooks."""
    ref = {"documento": "docs/FIX-EDA-MODELADO-NIVEL1.md", "protocolo": "walk-forward con purge, folds 2-5, IC95 por bootstrap de productos"}
    ruta = DW / "cuantiles_produccion_vs_base_13.csv"
    if ruta.is_file():
        p = pd.read_csv(ruta)
        for rama in POLITICA:
            fila = p[(p["rama"] == rama) & (p["estrato"] == "todos")]
            if len(fila):
                f = fila.iloc[0]
                ref[rama] = {"alpha": float(f["alpha"]), "cobertura_cuantil_produccion_anterior": float(f["cob_produccion"]),
                             "cobertura_lgb_relativo": float(f["cob_lgb_relativo"]), "cobertura_base_por_estrato": float(f["cob_base_estrato"]),
                             "costo_produccion_anterior_vs_base": float(f["prod_vs_base"]),
                             "costo_lgb_relativo_vs_produccion_anterior": float(f["lgbrel_vs_prod"]),
                             "ic_lgb_relativo_vs_produccion_anterior": [float(f["lgbrel_lo"]), float(f["lgbrel_hi"])]}
    return ref


def main():
    verificar_huella("huella_07.json", ["matriz_as_of.parquet"])
    matriz = pd.read_parquet(f"{DW}/matriz_as_of.parquet")
    faltantes = [c for c in FEATURES + ["nivel_medio_60d", "codigo_item", "sucursal"] if c not in matriz.columns]
    assert not faltantes, f"columnas ausentes en la matriz: {faltantes}"
    matriz["fin_ventana"] = fin_ventana_de(matriz, HORIZONTE)

    fechas_habiles, _ = leer_calendario_habil()
    fecha_corte = fechas_habiles.max()
    estr = estratos_as_of(fecha_corte)
    estrato_por_par = {(r.codigo_item, r.sucursal): r.estrato for r in estr.itertuples()}
    print(f"estratos as-of {fecha_corte.date()}: {estr['estrato'].value_counts().to_dict()}")

    hp_int, fuente_hp = hparams_intermitente()
    if CALIBRAR_INTERMITENTE:
        verificar_contra_14(matriz, hp_int)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000")
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(EXPERIMENTO_MLFLOW)
    print(f"MLflow: {tracking_uri} | experimento {EXPERIMENTO_MLFLOW} | hparams intermitente: {fuente_hp}")

    metadata = {
        "hu": "INV-17-v2",
        "fecha_generacion": datetime.now(timezone.utc).isoformat(),
        "features": FEATURES,
        "target": TARGET,
        "horizonte": HORIZONTE,
        "costos": COSTOS_SUPUESTOS,
        "alpha_negocio": ALPHA_NEGOCIO,
        "politica": {rama: tipo for rama, tipo in POLITICA.items()},
        "fuente_politica": FUENTE_POLITICA,
        "hparams_intermitente": {"fuente": fuente_hp, "valores": hp_int},
        "calibracion_intermitente": ("conformal por estrato (decisión del usuario; la regla pre-registrada de 14 no la adoptaba)"
                                     if CALIBRAR_INTERMITENTE else "sin calibración"),
        "estratos": {"fecha_corte": str(fecha_corte.date()), "ventana_dias_habiles": 365, "cortes_volumen_acumulado": [0.5, 0.8],
                     "pares_por_estrato": {k: int(v) for k, v in estr["estrato"].value_counts().items()}},
        "entrada_matriz": registrar_huella(["matriz_as_of.parquet"]),
        "referencia_evaluacion": referencia_evaluacion(),
        "nota": ("Estos modelos se entrenan sobre el 100% del histórico y no tienen conjunto de test propio; la evaluación "
                 "(walk-forward con purge) está en los notebooks 09-15."),
        "ramas": {},
    }

    for rama, condicion in RAMA_A_CONDICION.items():
        datos_rama = matriz.loc[condicion(matriz)].copy()
        tipo = POLITICA[rama]
        paquete = (entrenar_relativo(datos_rama, rama, hp_int, estrato_por_par, CALIBRAR_INTERMITENTE) if tipo == "relativo"
                   else entrenar_baseline(datos_rama, rama, estrato_por_par))
        paquete.update({"rama": rama, "alpha_negocio": _alpha_negocio_de(rama), "features": FEATURES,
                        "target": TARGET, "n_filas_entrenamiento": len(datos_rama)})
        ruta = MODELS_DIR / f"nivel1_{rama}.joblib"
        joblib.dump(paquete, ruta)
        print(f"    guardado: {ruta}")
        metadata["ramas"][rama] = {"archivo": ruta.name, "tipo_modelo": tipo, "alpha_negocio": paquete["alpha_negocio"],
                                   "n_filas_entrenamiento": len(datos_rama)}
        if "offset_relativo_por_estrato" in paquete:
            metadata["ramas"][rama]["offset_relativo_por_estrato"] = paquete["offset_relativo_por_estrato"]
            metadata["ramas"][rama]["offset_relativo_global"] = paquete["offset_relativo_global"]
            metadata["ramas"][rama]["calibracion"] = paquete["calibracion"]
        with mlflow.start_run(run_name=f"nivel1_{rama}_produccion_v2"):
            mlflow.set_tags({"hu": "INV-17-v2", "rama": rama, "tipo_modelo": tipo, "protocolo": "con_purge"})
            mlflow.log_params({"alpha_negocio": paquete["alpha_negocio"], "n_filas_entrenamiento": len(datos_rama),
                               "tipo_modelo": tipo, "fecha_corte_estratos": str(fecha_corte.date())})
            mlflow.log_artifact(str(ruta))

    ruta_meta = MODELS_DIR / "nivel1_metadata.json"
    with open(ruta_meta, "w") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nguardado: {ruta_meta}")


if __name__ == "__main__":
    main()
