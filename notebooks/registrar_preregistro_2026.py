#!/usr/bin/env python3
"""
Preregistro del holdout 2026 (paso previo a `16_holdout_2026`).

Congela en MLflow, ANTES de disponer de ventas 2026, los modelos de Nivel 1 exportados y las reglas de decisión con
que se van a evaluar (`preregistro_holdout_2026.json`, explicado en `docs/PREREGISTRO-HOLDOUT-2026.md`):

1. Verifica que `models/` coincide con el commit congelado y con los hashes del preregistro, y que los artefactos de los
   runs de exportación v2 en MLflow son esos mismos archivos.
2. Verifica que la matriz as-of es la de entrenamiento (hash de 07).
3. Construye la referencia `baseline_cuantil` de la rama intermitente (contra la que R2 mide el costo) con el mismo
   procedimiento que el exportador v2 y los estratos del paquete congelado; la escribe en el JSON la primera vez y, si ya
   está, comprueba que se reproduce.
4. Registra todo en el experimento `EDA-fix-nivel1-16-holdout-2026` (run `preregistro_v<version>`). Se niega a registrar
   dos veces la misma versión: un preregistro no se sobrescribe; un cambio de reglas es una versión nueva con su motivo.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common_priorizacion import DW, registrar_huella  # noqa: E402
from exportar_modelos_nivel1 import RAMA_A_CONDICION  # noqa: E402
from exportar_modelos_nivel1_v2 import entrenar_baseline  # noqa: E402

import joblib  # noqa: E402
import mlflow  # noqa: E402
import pandas as pd  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
RUTA_PREREGISTRO = Path(__file__).resolve().parent / "preregistro_holdout_2026.json"
RUTA_DOC = RAIZ / "docs" / "PREREGISTRO-HOLDOUT-2026.md"
RUTA_REFERENCIA = DW / "referencia_intermitente_baseline_cuantil_2026.joblib"
EXPERIMENTO_MLFLOW = "EDA-fix-nivel1-16-holdout-2026"
CAMPOS_REFERENCIA = ("razon_cuantil_por_estrato", "razon_cuantil_global", "filas_por_estrato")


def sha256(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def verificar_modelos(pre):
    commit = pre["congelado"]["commit"]
    # Solo los archivos congelados: models/ puede tener archivos nuevos que no son modelos
    # (p. ej. nivel1_parametros_features.json, agregado en el fix de INV-20).
    congelados = list(pre["congelado"]["archivos_sha256"])
    difiere = subprocess.run(["git", "diff", "--quiet", commit, "--", *congelados], cwd=RAIZ).returncode
    assert difiere == 0, f"los modelos congelados no coinciden con el commit {commit}"
    for rel, esperado in pre["congelado"]["archivos_sha256"].items():
        assert sha256(RAIZ / rel) == esperado, f"hash distinto en {rel}"
    print(f"models/ = commit {commit}; hashes del preregistro OK ({len(pre['congelado']['archivos_sha256'])} archivos)")


def verificar_runs_exportacion(pre):
    runs = pre["congelado"]["runs_exportacion_mlflow"]
    with tempfile.TemporaryDirectory() as tmp:
        for rama in RAMA_A_CONDICION:
            archivo = f"nivel1_{rama}.joblib"
            local = mlflow.artifacts.download_artifacts(run_id=runs[rama], artifact_path=archivo, dst_path=tmp)
            assert sha256(local) == pre["congelado"]["archivos_sha256"][f"models/{archivo}"], f"el run {runs[rama]} no guarda el modelo congelado de {rama}"
    print("los runs de exportación v2 en MLflow guardan exactamente los modelos congelados")


def construir_referencia(matriz):
    paquete = joblib.load(RAIZ / "models" / "nivel1_intermitente.joblib")
    datos = matriz.loc[RAMA_A_CONDICION["intermitente"](matriz)]
    ref = entrenar_baseline(datos, "intermitente", paquete["estrato_por_par"])
    ref.update({"rama": "intermitente", "alpha_negocio": 0.893, "n_filas_entrenamiento": len(datos),
                "nota": "referencia de R2 del preregistro del holdout 2026; no es un modelo de producción"})
    return ref


def fijar_o_comprobar_referencia(pre, ref):
    actual = {k: ref[k] for k in CAMPOS_REFERENCIA}
    guardada = pre["referencia_intermitente_baseline_cuantil"]
    if guardada["razon_cuantil_global"] is None:
        guardada.update(actual)
        RUTA_PREREGISTRO.write_text(json.dumps(pre, indent=2, ensure_ascii=False) + "\n")
        print("referencia baseline_cuantil de intermitente escrita en el preregistro")
        return
    assert abs(guardada["razon_cuantil_global"] - actual["razon_cuantil_global"]) < 1e-12
    for e, v in actual["razon_cuantil_por_estrato"].items():
        assert abs(guardada["razon_cuantil_por_estrato"][e] - v) < 1e-12, e
    print("referencia baseline_cuantil de intermitente reproducida")


def main():
    pre = json.loads(RUTA_PREREGISTRO.read_text())
    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000"))

    verificar_modelos(pre)
    verificar_runs_exportacion(pre)
    huella = registrar_huella(["matriz_as_of.parquet"])
    assert huella == pre["congelado"]["matriz_entrenamiento"], f"la matriz as-of no es la de entrenamiento: {huella}"
    print(f"matriz as-of = la de entrenamiento {huella}")

    matriz = pd.read_parquet(DW / "matriz_as_of.parquet")
    assert matriz["fecha_origen"].max() <= pd.Timestamp("2025-12-31"), "la matriz ya contiene orígenes de 2026"
    ref = construir_referencia(matriz)
    fijar_o_comprobar_referencia(pre, ref)
    joblib.dump(ref, RUTA_REFERENCIA)

    exp = mlflow.set_experiment(EXPERIMENTO_MLFLOW)
    nombre_run = f"preregistro_v{pre['version']}"
    previos = mlflow.search_runs([exp.experiment_id], filter_string=f"tags.mlflow.runName = '{nombre_run}'")
    assert previos.empty, f"ya existe {nombre_run} ({previos['run_id'].tolist()}): un preregistro no se sobrescribe"
    mlflow.set_experiment_tags({"mlflow.note.content": (
        "Holdout limpio con ventas 2026 de los modelos de Nivel 1 (política v2). El run preregistro_v* congela modelos y "
        "reglas ANTES de ver datos de 2026; los runs de evaluación de 16_holdout_2026 se comparan contra él.")})

    reglas = {r["id"]: r for r in pre["reglas"]}
    with mlflow.start_run(run_name=nombre_run) as run:
        mlflow.set_tags({"protocolo": "con_purge", "fase": "16-holdout-2026", "estado": "preregistrado",
                         "datos_2026_vistos": "no", "commit_congelado": pre["congelado"]["commit"],
                         "fecha_preregistro": pre["fecha_preregistro"]})
        mlflow.log_params({
            "version": pre["version"],
            "horizonte": pre["diseno"]["horizonte_dias_habiles"],
            "min_origenes_veredicto": 8,
            "R1_criterio": reglas["R1"]["criterio"],
            "R2_criterio": reglas["R2"]["criterio"],
            "R3_criterio": reglas["R3"]["criterio"],
            "R4_criterio": reglas["R4"]["criterio"][:250],
            "bootstrap": "productos, B=2000, semilla=0",
            **{f"run_exportacion_{r}": v for r, v in pre["congelado"]["runs_exportacion_mlflow"].items() if r != "experimento"},
            **{f"sha256_{Path(k).name}": v[:16] for k, v in pre["congelado"]["archivos_sha256"].items()},
        })
        mlflow.log_metrics({f"ref_intermitente_razon_q_{e}": v for e, v in ref["razon_cuantil_por_estrato"].items()}
                           | {"ref_intermitente_razon_q_global": ref["razon_cuantil_global"]})
        mlflow.log_artifact(str(RUTA_PREREGISTRO))
        if RUTA_DOC.is_file():
            mlflow.log_artifact(str(RUTA_DOC))
        mlflow.log_artifact(str(RUTA_REFERENCIA), artifact_path="referencia")
        for rel in pre["congelado"]["archivos_sha256"]:
            mlflow.log_artifact(str(RAIZ / rel), artifact_path="modelos_congelados")
        print(f"MLflow: experimento {EXPERIMENTO_MLFLOW}, run {nombre_run} = {run.info.run_id}")


if __name__ == "__main__":
    main()
