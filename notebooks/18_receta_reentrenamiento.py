#!/usr/bin/env python3
"""
INV-62 — Evaluación preregistrada de la receta del reentrenamiento (`preregistro_receta_2026.json`).

Dos etapas:
    receta       la receta vigente frente a la misma con features de calendario, las dos con la máscara de demanda
                 censurada, en tres temporadas altas y tres periodos del resto del año (walk-forward con purge); aplica la
                 regla del calendario y mide el efecto de la máscara. Run `evaluacion_receta`.
    calibracion  simula el ajuste fijo, el deslizante y el adaptativo de la calibración sobre las predicciones del
                 holdout de 2026, por estrato. Solo se reporta. Run `simulacion_calibracion`.

Usa la matriz de la exploración de INV-63 (`<dw>/exploracion_2026/matriz_exploracion.parquet`) y las filas del holdout
(`<dw>/holdout_2026/filas_holdout_2026.parquet`); a MLflow van solo agregados.

    python notebooks/18_receta_reentrenamiento.py receta --dw RUTA_DW --inventario-dic RUTA.xlsx --inventario-sep RUTA.xlsx
    python notebooks/18_receta_reentrenamiento.py calibracion --dw RUTA_DW
"""
import argparse
import importlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluar_nivel1 as ev  # noqa: E402
import exploracion_2026 as ex  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import reentrenamiento as re_  # noqa: E402

hold = importlib.import_module("16_holdout_2026")
expl = importlib.import_module("17_exploracion_2026")

RUTA_PREREGISTRO = Path(__file__).resolve().parent / "preregistro_receta_2026.json"
EXPERIMENTO = "INV-62-reentrenamiento-nivel1"
B, SEMILLA = 2000, 0
ESTRATOS = ("cabeza", "medio", "cola")


def eventos_de_censura(dw, rutas_fotos):
    netas = hold.ventas_netas(dw)
    habiles = pd.DatetimeIndex(sorted(netas["fecha"].unique()))
    eventos = []
    for fecha, ruta in rutas_fotos:
        foto = hold.leer_foto(ruta).rename(columns={"Cantidad": "cantidad"})
        ultima = (netas[netas["fecha"] <= fecha].groupby(["codigo_item", "sucursal"], as_index=False)["fecha"].max()
                  .rename(columns={"fecha": "ultima"}))
        eventos.append(re_.eventos_censura(foto, ultima, fecha, habiles))
    return pd.concat(eventos, ignore_index=True)


def evaluar_particion(tr, te, specs, hparams, ids):
    te = te.copy()
    for cid in ids:
        modelo = expl.entrenar(cid, specs[cid], tr, hparams)
        te[f"p50_{cid}"], te[f"pneg_{cid}"] = expl.predecir(modelo, te)
        te[f"costo_{cid}"] = expl.costo(te["y"], te[f"pneg_{cid}"])
    return te


def etapa_receta(args, salida):
    t0 = time.time()
    pre = json.loads(RUTA_PREREGISTRO.read_text())
    mlflow = expl.mlflow_cliente()
    exp = mlflow.set_experiment(EXPERIMENTO)
    previos = mlflow.search_runs([exp.experiment_id], filter_string="tags.mlflow.runName = 'evaluacion_receta'")
    assert previos.empty or args.repetir, "la evaluación de la receta ya está registrada; repetirla exige --repetir con el motivo"
    congelado = expl.cargar_paquetes()["intermitente"]
    hparams = congelado["hparams"]
    specs = expl.especificacion(list(congelado["features"]))
    dw = args.dw.resolve()
    inter = expl.leer_intermitente(dw / "exploracion_2026")
    eventos = eventos_de_censura(dw, [(pd.Timestamp("2025-12-31"), args.inventario_dic), (pd.Timestamp("2026-09-30"), args.inventario_sep)])
    mascara = re_.mascara_censura(inter, eventos)
    print(f"máscara de censura: {len(eventos)} eventos, {mascara.sum():,} filas de {len(inter):,} ({mascara.mean():.2%})")

    pruebas, efecto = [], []
    particiones = ([dict(p, tipo="alta") for p in pre["particiones"]["temporadas_altas"]]
                   + [dict(p, tipo="baja") for p in pre["particiones"]["resto_del_anio"]])
    for p in particiones:
        t1 = time.time()
        tr, te = ex.particion(inter["fecha_origen"], inter["fin_ventana"], p["desde"], p["hasta"])
        d_te = evaluar_particion(inter[tr & ~mascara], inter[te], specs, hparams, ["C0", "C1"])
        sin_mascara = evaluar_particion(inter[tr], inter[te], specs, hparams, ["C0"])
        d_te["costo_C0_sin_mascara"] = sin_mascara["costo_C0"]
        d_te["p50_C0_sin_mascara"] = sin_mascara["p50_C0"]
        d_te["enmascarada"] = mascara[te]
        d_te["particion"], d_te["tipo"] = p["id"], p["tipo"]
        efecto.append(dict(particion=p["id"], filas_entrenamiento=int(tr.sum()), filas_enmascaradas=int((tr & mascara).sum())))
        pruebas.append(d_te)
        print(f"  {p['id']}: entrenamiento {int((tr & ~mascara).sum()):,} filas, prueba {int(te.sum()):,} filas en "
              f"{d_te['fecha_origen'].nunique()} orígenes ({time.time() - t1:.0f} s)")
    todo = pd.concat(pruebas, ignore_index=True)
    todo.to_parquet(salida / "receta_predicciones.parquet", index=False)

    def mejora_costo(g):
        return ev.mejora_perdida_con_ic(g, g["costo_C1"], g["costo_C0"], B, SEMILLA)
    filas = []
    for pid, g in todo.groupby("particion", sort=False):
        c = mejora_costo(g)
        w = ev.mejora_con_ic(g, "y", "p50_C1", "p50_C0", B, SEMILLA)
        filas.append(dict(particion=pid, tipo=g["tipo"].iloc[0], n_origenes=g["fecha_origen"].nunique(), n_filas=len(g),
                          costo_mejora=c["mejora_rel"], costo_ic_bajo=c["ic_bajo"], costo_ic_alto=c["ic_alto"],
                          wape_mejora=w["mejora_rel"], wape_ic_bajo=w["ic_bajo"], wape_ic_alto=w["ic_alto"],
                          cobertura_C0=float((g["y"] <= g["pneg_C0"]).mean()), cobertura_C1=float((g["y"] <= g["pneg_C1"]).mean())))
    tabla = pd.DataFrame(filas)
    altas = {pid: mejora_costo(g) for pid, g in todo[todo["tipo"] == "alta"].groupby("particion", sort=False)}
    bajas = mejora_costo(todo[todo["tipo"] == "baja"])
    total = ex.reglas_confirmacion(mejora_costo(todo), ev.mejora_con_ic(todo, "y", "p50_C1", "p50_C0", B, SEMILLA),
                                   expl.coberturas(todo, "pneg_C1"))
    decision = re_.regla_calendario(altas, bajas, total)

    limpias = todo[~todo["enmascarada"]]
    efecto_mascara = ev.mejora_perdida_con_ic(limpias, limpias["costo_C0"], limpias["costo_C0_sin_mascara"], B, SEMILLA)
    tabla.to_csv(salida / "receta_particiones.csv", index=False)
    pd.DataFrame(efecto).to_csv(salida / "receta_mascara.csv", index=False)
    resumen = dict(entra_calendario=decision["entra"], decision=decision, resto_del_anio=bajas,
                   total={k: v for k, v in total.items() if k != "detalle_e3"}, coberturas_total=total["detalle_e3"].to_dict("records"),
                   mascara=dict(eventos=int(len(eventos)), filas=int(mascara.sum()), fraccion=float(mascara.mean()),
                                efecto_costo_en_filas_no_enmascaradas=efecto_mascara))
    (salida / "receta_resultado.json").write_text(json.dumps(hold.a_json(resumen), ensure_ascii=False, indent=2))
    pd.set_option("display.width", 220)
    print(tabla.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    print(f"\nresto del año juntos: {bajas['mejora_rel']:+.4f} [{bajas['ic_bajo']:+.4f}; {bajas['ic_alto']:+.4f}]")
    print(f"total: WAPE y cobertura {'cumplen' if decision['wape_y_cobertura'] else 'no cumplen'}")
    print(f"efecto de la máscara (C0 con frente a sin, filas no enmascaradas): {efecto_mascara['mejora_rel']:+.4f} "
          f"[{efecto_mascara['ic_bajo']:+.4f}; {efecto_mascara['ic_alto']:+.4f}]")
    print(f"\nCALENDARIO {'ENTRA' if decision['entra'] else 'NO ENTRA'} en la receta: {decision}")
    with mlflow.start_run(run_name="evaluacion_receta") as run:
        mlflow.set_tags({"hu": "INV-62", "etapa": "evaluacion_receta", "entra_calendario": str(decision["entra"]),
                         "commit": hold.commit_actual(), "intento": str(len(previos) + 1),
                         **({"motivo_repeticion": args.repetir} if args.repetir else {}),
                         "advertencia": pre["advertencia"][:250]})
        mlflow.log_params({"particiones": ", ".join(p["id"] for p in particiones), "bootstrap": f"productos, B={B}, semilla={SEMILLA}",
                           "mascara_eventos": len(eventos), "mascara_filas": int(mascara.sum())})
        for f in tabla.to_dict("records"):
            for k in ("costo_mejora", "costo_ic_bajo", "costo_ic_alto", "wape_mejora", "wape_ic_alto", "cobertura_C1"):
                mlflow.log_metric(f"{f['particion']}_{k}", float(f[k]))
        mlflow.log_metrics({"resto_del_anio_costo_mejora": bajas["mejora_rel"], "resto_del_anio_costo_ic_alto": bajas["ic_alto"],
                            "mascara_efecto_costo": efecto_mascara["mejora_rel"], "entra_calendario": float(decision["entra"])})
        for a in ("receta_resultado.json", "receta_particiones.csv", "receta_mascara.csv"):
            mlflow.log_artifact(str(salida / a))
        print(f"MLflow: run evaluacion_receta = {run.info.run_id}")
    print(f"listo en {time.time() - t0:.0f} s")


def etapa_calibracion(args, salida):
    t0 = time.time()
    congelado = expl.cargar_paquetes()["intermitente"]
    filas = pd.read_parquet(args.dw.resolve() / "holdout_2026" / "filas_holdout_2026.parquet")
    f = filas[filas["en_d1"] & (filas["fecha_origen"] >= "2026-01-01") & (filas["rama"] == "intermitente")].copy()
    f = f.sort_values("fecha_origen").reset_index(drop=True)
    base = f["nivel_medio_60d"].to_numpy() * congelado["horizonte"] + congelado.get("base_offset", 1.0)
    q_rel = np.asarray(congelado["modelo_qneg"].predict(f[congelado["features"]]), dtype=float)
    f["residuo"] = f["y"].to_numpy() / base - q_rel
    f["base"], f["q_rel"] = base, q_rel
    origenes = sorted(f["fecha_origen"].unique())
    for variante in ("fija", "deslizante", "adaptativa"):
        f[f"off_{variante}"] = np.nan
        for e in ESTRATOS:
            g = f[f["estrato"] == e]
            residuos = [g.loc[g["fecha_origen"] == o, "residuo"].to_numpy() for o in origenes]
            offs = re_.offsets_secuenciales(residuos, congelado["offset_relativo_por_estrato"][e], variante)
            for o, off in zip(origenes, offs):
                f.loc[(f["estrato"] == e) & (f["fecha_origen"] == o), f"off_{variante}"] = off
        f[f"pneg_{variante}"] = np.clip(f["base"] * (f["q_rel"] + f[f"off_{variante}"]), 0, None)
        f[f"costo_{variante}"] = expl.costo(f["y"], f[f"pneg_{variante}"])
    assert np.allclose(f["pneg_fija"], f["pneg"], atol=1e-6), "la variante fija debe reproducir el cuantil del holdout"
    filas_tabla = []
    for e in ("cabeza", "medio", "cola", None):
        g = f if e is None else f[f["estrato"] == e]
        fila = dict(estrato=e or "rama completa", n_filas=len(g))
        for variante in ("fija", "deslizante", "adaptativa"):
            fila[f"cobertura_{variante}"] = float((g["y"] <= g[f"pneg_{variante}"]).mean())
            if variante != "fija":
                c = ev.mejora_perdida_con_ic(g, g[f"costo_{variante}"], g["costo_fija"], B, SEMILLA)
                fila |= {f"costo_{variante}_mejora": c["mejora_rel"], f"costo_{variante}_ic_bajo": c["ic_bajo"],
                         f"costo_{variante}_ic_alto": c["ic_alto"]}
        filas_tabla.append(fila)
    tabla = pd.DataFrame(filas_tabla)
    tabla.to_csv(salida / "calibracion_simulacion.csv", index=False)
    pd.set_option("display.width", 220)
    print(tabla.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    mlflow = expl.mlflow_cliente()
    mlflow.set_experiment(EXPERIMENTO)
    with mlflow.start_run(run_name="simulacion_calibracion") as run:
        mlflow.set_tags({"hu": "INV-62", "etapa": "simulacion_calibracion", "decision": "solo se reporta", "commit": hold.commit_actual()})
        mlflow.log_params({"ventana_deslizante": re_.VENTANA_DESLIZANTE, "gamma_adaptativa": re_.GAMMA_ADAPTATIVA,
                           "datos": "holdout 2026, rama intermitente, universo principal, 18 orígenes"})
        for fila in tabla.to_dict("records"):
            for k, v in fila.items():
                if k not in ("estrato", "n_filas") and v == v:
                    mlflow.log_metric(f"{fila['estrato'].replace(' ', '_')}_{k}", float(v))
        mlflow.log_artifact(str(salida / "calibracion_simulacion.csv"))
        print(f"MLflow: run simulacion_calibracion = {run.info.run_id}")
    print(f"listo en {time.time() - t0:.0f} s")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("etapa", choices=["receta", "calibracion"])
    ap.add_argument("--dw", type=Path, required=True, help="DW de la evaluación de INV-63 (con exploracion_2026/ y holdout_2026/)")
    ap.add_argument("--inventario-dic", type=Path)
    ap.add_argument("--inventario-sep", type=Path)
    ap.add_argument("--repetir", help="motivo para repetir una etapa ya registrada")
    args = ap.parse_args()
    salida = args.dw.resolve() / "reentrenamiento_2026"
    salida.mkdir(exist_ok=True)
    if args.etapa == "receta":
        assert args.inventario_dic and args.inventario_sep, "la máscara necesita las fotos de dic-2025 y sep-2026"
        etapa_receta(args, salida)
    else:
        etapa_calibracion(args, salida)


if __name__ == "__main__":
    main()
