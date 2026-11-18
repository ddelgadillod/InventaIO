#!/usr/bin/env python3
"""
INV-63 — Exploración preregistrada de features y algoritmos para la rama intermitente (decidida por el usuario
el 17-nov, después del veredicto de la evaluación; ver docs/INV-63-requerimientos.md, sección 8).

Sigue `preregistro_exploracion_2026.json` (registrado en MLflow, run `preregistro_exploracion_v1`, antes de
entrenar ningún candidato). Identificadores que usan el JSON, el código y MLflow:
    candidatos  C0 receta vigente reentrenada; C1 con features de calendario y estacionalidad; C2 con features de
                demanda intermitente (Croston-SBA, TSB y otras); C3 con las dos familias; C4 CatBoost con las dos
                familias; C5 TSB clásico con razón por estrato, sin ML.
    periodos    F1, F2 y F3 son los tres periodos de prueba de la búsqueda (jul-dic 2025, ene-feb 2026 y mar a
                3-may 2026).
    criterios   E1 costo frente al paquete congelado con intervalo de confianza del 95 % por encima de 0; E2 WAPE
                no peor; E3 cobertura a ±0,05 de 0,893.

Tres etapas, en orden:

    matriz        rejilla 2022 a 2026 de los pares del universo principal (productos en las dos fotos de
                  inventario), con las 14 features del paquete (calculadas con features.py), las nuevas de
                  `exploracion_2026.py`, el objetivo y el fin de la ventana. Comprueba que las filas de 2026
                  coinciden con las de la evaluación.
    busqueda      los seis candidatos en los tres periodos de prueba, con purge; aplica la regla de selección y la
                  registra.
    confirmacion  una sola vez: el candidato elegido, entrenado con las ventanas que terminan hasta el 18-may-2026,
                  frente al paquete congelado en los 9 orígenes de confirmación, con los tres criterios.

Las filas quedan en `<dw>/exploracion_2026/`, fuera de git; a MLflow van solo agregados.

Uso, desde la raíz del repo, con MLflow en el 5000:
    python notebooks/17_exploracion_2026.py matriz --inventario-dic RUTA.xlsx --inventario-sep RUTA.xlsx
    python notebooks/17_exploracion_2026.py busqueda
    python notebooks/17_exploracion_2026.py confirmacion
"""
import argparse
import importlib
import json
import os
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluar_nivel1 as ev  # noqa: E402
import exploracion_2026 as ex  # noqa: E402
import joblib  # noqa: E402
import lightgbm as lgb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from modelos_nivel1 import offset_conformal  # noqa: E402

hold = importlib.import_module("16_holdout_2026")   # compuertas y armado de filas del holdout (mismo código)

RUTA_PREREGISTRO = Path(__file__).resolve().parent / "preregistro_exploracion_2026.json"
EXPERIMENTO = "EDA-fix-nivel1-17-exploracion-2026"
SEMILLA, B = 0, 2000
ESTRATOS = ("cabeza", "medio", "cola")
FRACCION_CALIB = 0.2
COSTO_CU, COSTO_CO = 0.25, 0.03


def cargar_paquetes():
    return {r: joblib.load(RAIZ / "models" / f"nivel1_{r}.joblib") for r in hold.RAMAS}


def mlflow_cliente():
    import mlflow
    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", ev.MLFLOW_URI_DEFECTO))
    return mlflow


def runs_previos(mlflow, nombre):
    exp = mlflow.set_experiment(EXPERIMENTO)
    return mlflow.search_runs([exp.experiment_id], filter_string=f"tags.mlflow.runName = '{nombre}'")


# ── Etapa 1: matriz ──────────────────────────────────
def etapa_matriz(args, salida):
    t0 = time.time()
    pre_h = json.loads(hold.RUTA_PREREGISTRO.read_text())
    parametros = json.loads(hold.RUTA_PARAMETROS.read_text())
    hold.compuerta_paquete(pre_h)
    paquetes = cargar_paquetes()
    epp = paquetes["intermitente"]["estrato_por_par"]
    dw = args.dw.resolve()
    netas = hold.ventas_netas(dw)
    hold.compuerta_serie(netas)
    productos_d1 = hold.compuerta_d1(pre_h, hold.leer_foto(args.inventario_dic), hold.leer_foto(args.inventario_sep), epp)
    pares = sorted(p for p in epp if p[0] in productos_d1)

    habiles = pd.DatetimeIndex(sorted(netas["fecha"].unique()))
    marcas = pd.read_csv(dw / "dim_tiempo.csv", parse_dates=["fecha"]).set_index("fecha")
    calendario = hold.Calendario(habiles=habiles, marcas=marcas)
    idx = ex.rejilla(habiles)
    span = np.array([(habiles[i + ex.HORIZONTE] - habiles[i + 1]).days + 1 for i in idx])
    descartados = habiles[idx[span > ex.HORIZONTE * hold.TOLERANCIA_EMPALME]]
    idx = idx[span <= ex.HORIZONTE * hold.TOLERANCIA_EMPALME]
    origenes = habiles[idx]
    print(f"rejilla: {len(idx)} orígenes ({origenes[0].date()} a {origenes[-1].date()}); "
          f"descartados por empalme: {[d.date().isoformat() for d in descartados]}")

    clave = netas["codigo_item"] + "|" + netas["sucursal"]
    pares_txt = [f"{c}|{s}" for c, s in pares]
    netas_d1 = netas[clave.isin(set(pares_txt))]
    series = {k: pd.Series(g["cantidad"].to_numpy(), index=pd.DatetimeIndex(g["fecha"]))
              for k, g in netas_d1.groupby(["codigo_item", "sucursal"], sort=True)}
    productos = pd.read_csv(dw / "dim_producto.csv", dtype={"codigo_item": str}).set_index("codigo_item")
    atributos = productos[list(parametros["condiciones_producto"].values())].to_dict("index")
    filas, saltos = hold.construir_filas(series, atributos, calendario, origenes, parametros)

    ancha = (netas_d1.assign(par=clave[clave.isin(set(pares_txt))])
             .pivot_table(index="fecha", columns="par", values="cantidad", aggfunc="sum")
             .reindex(index=habiles, columns=pares_txt).fillna(0.0))
    x = ancha.to_numpy(dtype=float)
    acumulada = np.cumsum(x, axis=0)
    sba, tsb_, ewm_ = ex.croston_sba(x), ex.tsb(x), ex.ewm(x)
    extra = []
    for i in idx:
        origen = habiles[i]
        dias = calendario.proximos_habiles(origen, ex.HORIZONTE)
        venta_aa = ex.venta_anio_anterior(acumulada, habiles, dias[0], dias[-1])
        trail_aa = ex.trail_anio_anterior(acumulada, habiles, origen)
        bloque = pd.DataFrame({"par": pares_txt, "fecha_origen": origen,
                               "y": x[i + 1:i + 1 + ex.HORIZONTE].sum(axis=0), "fin_ventana": habiles[i + ex.HORIZONTE],
                               "venta_aa": venta_aa, "razon_aa": venta_aa / (trail_aa + 1.0),
                               "mes_origen": origen.month, "dias_naturales_ventana": (dias[-1] - origen).days,
                               **ex.marcas_ventana(marcas, dias), **ex.features_c2(x, i, sba, tsb_, ewm_)})
        extra.append(bloque)
    extra = pd.concat(extra, ignore_index=True)
    filas["par"] = filas["codigo_item"] + "|" + filas["sucursal"]
    filas = filas.merge(extra, on=["par", "fecha_origen"], how="left", validate="one_to_one")
    filas["rama"] = [hold.determinar_rama(r) for r in filas[["familia_modelo", "cond2_perecedero"]].to_dict("records")]
    filas["estrato"] = [epp.get((c, s)) for c, s in zip(filas["codigo_item"], filas["sucursal"])]

    # las filas de 2026 deben coincidir con las del holdout (mismo código, mismos datos)
    ruta_holdout = dw / "holdout_2026" / "filas_holdout_2026.parquet"
    if ruta_holdout.is_file():
        ho = pd.read_parquet(ruta_holdout)
        ho = ho[ho["en_d1"] & (ho["fecha_origen"] >= "2026-01-01")]
        cols = ["trail_15", "nivel_medio_60d", "frecuencia_as_of", "cv2_as_of", "factor_calendario_ventana", "y"]
        cruce = filas.merge(ho[["codigo_item", "sucursal", "fecha_origen", *cols]], on=["codigo_item", "sucursal", "fecha_origen"],
                            suffixes=("", "_h"))
        assert len(cruce) == len(ho), f"filas 2026 distintas del holdout: {len(cruce)} frente a {len(ho)}"
        dif = max(float(np.nanmax(np.abs(cruce[c] - cruce[f"{c}_h"]))) for c in cols)
        assert dif < 1e-9, f"features o objetivo distintos del holdout: {dif}"
        print(f"filas 2026 = holdout: {len(cruce):,} filas, máx |dif| = {dif:.1e}")
    filas.to_parquet(salida / "matriz_exploracion.parquet", index=False)
    print(f"matriz: {len(filas):,} filas ({(filas['rama'] == 'intermitente').mean():.1%} intermitente), saltos {saltos}; "
          f"{time.time() - t0:.0f} s")


# ── Candidatos ───────────────────────────────────────
def especificacion(features_base):
    c1, c2 = features_base + ex.FEATURES_C1, features_base + ex.FEATURES_C2
    todas = features_base + ex.FEATURES_C1 + ex.FEATURES_C2
    return {"C0": ("lgb", features_base), "C1": ("lgb", c1), "C2": ("lgb", c2), "C3": ("lgb", todas),
            "C4": ("catboost", todas), "C5": ("tsb", ["tsb_15"])}


def ajustar(tipo, X, y, alpha, hparams):
    if tipo == "lgb":
        m = lgb.LGBMRegressor(objective="quantile", alpha=alpha, subsample_freq=1, random_state=SEMILLA, verbose=-1, **hparams)
    else:
        from catboost import CatBoostRegressor
        m = CatBoostRegressor(loss_function=f"Quantile:alpha={alpha}", depth=6, learning_rate=0.05, iterations=800,
                              random_seed=SEMILLA, verbose=0, thread_count=-1, allow_writing_files=False)
    return m.fit(X, y)


def base_de(d):
    return d["nivel_medio_60d"].to_numpy() * ex.HORIZONTE + 1.0


def por_estrato(valores, estratos, calcular, minimo=ex.MINIMO_FILAS_ESTRATO):
    global_ = calcular(valores)
    offs, n = {}, {}
    for e in ESTRATOS:
        v = valores[estratos == e]
        n[e] = int(len(v))
        offs[e] = calcular(v) if len(v) >= minimo else global_
    return offs, global_, n


def entrenar(cid, spec, tr, hparams):
    tipo, feats = spec
    estr = tr["estrato"].fillna("cola").to_numpy()
    if tipo == "tsb":
        q50 = np.clip(np.nan_to_num(tr["tsb_15"].to_numpy()), 0, None)
        razon = tr["y"].to_numpy() / (q50 + 1.0)
        offs, global_, n = por_estrato(razon, estr, lambda v: float(np.quantile(v, ex.ALPHA)))
        return dict(id=cid, tipo=tipo, razon=offs, razon_global=global_, n_calib=n)
    base = base_de(tr)
    y_rel = tr["y"].to_numpy() / base
    m50 = ajustar(tipo, tr[feats], y_rel, 0.5, hparams)
    mneg = ajustar(tipo, tr[feats], y_rel, ex.ALPHA, hparams)
    # split-CQR por estrato: el 20 % más reciente del entrenamiento calibra un modelo ajustado (con purge) en el resto
    fechas = np.sort(tr["fecha_origen"].unique())
    corte = fechas[int(len(fechas) * (1 - FRACCION_CALIB))]
    en_fit = ((tr["fecha_origen"] < corte) & (tr["fin_ventana"] < corte)).to_numpy()
    en_cal = (tr["fecha_origen"] >= corte).to_numpy()
    mfit = ajustar(tipo, tr.loc[en_fit, feats], y_rel[en_fit], ex.ALPHA, hparams)
    residual = y_rel[en_cal] - mfit.predict(tr.loc[en_cal, feats])
    offs, global_, n = por_estrato(residual, estr[en_cal], lambda v: offset_conformal(v, ex.ALPHA))
    return dict(id=cid, tipo=tipo, feats=feats, m50=m50, mneg=mneg, offsets=offs, offset_global=global_, n_calib=n,
                corte_calib=str(pd.Timestamp(corte).date()))


def predecir(modelo, te):
    estr = te["estrato"].fillna("cola")
    if modelo["tipo"] == "tsb":
        q50 = np.clip(np.nan_to_num(te["tsb_15"].to_numpy()), 0, None)
        razon = estr.map(modelo["razon"]).fillna(modelo["razon_global"]).to_numpy()
        return q50, razon * (q50 + 1.0)
    base = base_de(te)
    off = estr.map(modelo["offsets"]).fillna(modelo["offset_global"]).to_numpy()
    p50 = base * modelo["m50"].predict(te[modelo["feats"]])
    pneg = base * (modelo["mneg"].predict(te[modelo["feats"]]) + off)
    return np.clip(p50, 0, None), np.clip(pneg, 0, None)


def costo(y, q):
    return ev.costo_asimetrico(y, q, COSTO_CU, COSTO_CO)


def coberturas(df, col):
    filas = [dict(estrato=None, n_filas=len(df), cobertura=float((df["y"] <= df[col]).mean()))]
    filas += [dict(estrato=e, n_filas=len(g), cobertura=float((g["y"] <= g[col]).mean()))
              for e, g in df.groupby("estrato", sort=True)]
    return filas


def leer_intermitente(salida):
    m = pd.read_parquet(salida / "matriz_exploracion.parquet")
    return m[m["rama"] == "intermitente"].reset_index(drop=True)


# ── Etapa 2: búsqueda ────────────────────────────────
def etapa_busqueda(args, salida):
    t0 = time.time()
    pre = json.loads(RUTA_PREREGISTRO.read_text())
    mlflow = mlflow_cliente()
    previos = runs_previos(mlflow, "busqueda")
    assert previos.empty or args.repetir, "la búsqueda ya está registrada; repetirla exige --repetir con el motivo"
    paquetes = cargar_paquetes()
    congelado = paquetes["intermitente"]
    hparams = congelado["hparams"]
    specs = especificacion(list(congelado["features"]))
    inter = leer_intermitente(salida)
    pruebas, calib = [], []
    for fold in pre["particiones"]["busqueda"]:
        tr, te = ex.particion(inter["fecha_origen"], inter["fin_ventana"], fold["origenes_desde"], fold["origenes_hasta"])
        d_tr, d_te = inter[tr], inter[te].copy()
        print(f"{fold['fold']}: entrenamiento {len(d_tr):,} filas (hasta {d_tr['fin_ventana'].max().date()}), "
              f"prueba {len(d_te):,} filas en {d_te['fecha_origen'].nunique()} orígenes")
        for cid, spec in specs.items():
            t1 = time.time()
            modelo = entrenar(cid, spec, d_tr, hparams)
            d_te[f"p50_{cid}"], d_te[f"pneg_{cid}"] = predecir(modelo, d_te)
            calib.append(dict(fold=fold["fold"], candidato=cid, **{f"n_calib_{e}": modelo["n_calib"][e] for e in ESTRATOS},
                              **{f"offset_{e}": (modelo.get("offsets") or modelo["razon"])[e] for e in ESTRATOS}))
            print(f"  {cid}: {time.time() - t1:.0f} s")
        d_te["p50_congelado"], d_te["pneg_congelado"] = hold.predecir_lote(congelado, d_te)
        d_te["fold"] = fold["fold"]
        pruebas.append(d_te)
    prueba = pd.concat(pruebas, ignore_index=True)
    prueba.to_parquet(salida / "busqueda_predicciones.parquet", index=False)

    for cid in [*specs, "congelado"]:
        prueba[f"costo_{cid}"] = costo(prueba["y"], prueba[f"pneg_{cid}"])
    tabla, comparaciones = [], []
    for cid in specs:
        fila = dict(id=cid, costo=float(prueba[f"costo_{cid}"].sum()), wape=ev.wape(prueba["y"], prueba[f"p50_{cid}"]),
                    cobertura=float((prueba["y"] <= prueba[f"pneg_{cid}"]).mean()))
        if cid != "C0":
            c = ev.mejora_perdida_con_ic(prueba, prueba[f"costo_{cid}"], prueba["costo_C0"], B, SEMILLA)
            w = ev.mejora_con_ic(prueba, "y", f"p50_{cid}", "p50_C0", B, SEMILLA)
            fila |= dict(costo_vs_C0=c["mejora_rel"], costo_ic_bajo=c["ic_bajo"], costo_ic_alto=c["ic_alto"],
                         wape_vs_C0=w["mejora_rel"], wape_ic_bajo=w["ic_bajo"], wape_ic_alto=w["ic_alto"])
            comparaciones.append(fila)
        for f, g in prueba.groupby("fold", sort=True):
            fila[f"costo_{f}"] = float(g[f"costo_{cid}"].sum())
            fila[f"wape_{f}"] = ev.wape(g["y"], g[f"p50_{cid}"])
            fila[f"cobertura_{f}"] = float((g["y"] <= g[f"pneg_{cid}"]).mean())
        tabla.append(fila)
    elegido, detalle = ex.regla_seleccion(comparaciones)
    tabla = pd.DataFrame(tabla)
    # contexto sin decisión: el paquete congelado solo es fuera de muestra en F2 y F3 (F1 cae en su entrenamiento)
    oos = prueba[prueba["fold"].isin(["F2", "F3"])]
    contexto = {cid: ev.mejora_perdida_con_ic(oos, oos[f"costo_{cid}"], oos["costo_congelado"], B, SEMILLA) for cid in specs}
    tabla["costo_vs_congelado_F2F3"] = tabla["id"].map({k: v["mejora_rel"] for k, v in contexto.items()})
    tabla.to_csv(salida / "busqueda_candidatos.csv", index=False)
    pd.DataFrame(calib).to_csv(salida / "busqueda_calibracion.csv", index=False)
    detalle.to_csv(salida / "busqueda_seleccion.csv", index=False)
    seleccion = dict(elegido=elegido, fecha=pd.Timestamp.now().isoformat(timespec="seconds"),
                     regla=pre["regla_seleccion"], candidatos=tabla.to_dict("records"))
    (salida / "seleccion.json").write_text(json.dumps(hold.a_json(seleccion), ensure_ascii=False, indent=2))
    pd.set_option("display.width", 250)
    print(tabla[["id", "costo", "wape", "cobertura", "costo_vs_C0", "costo_ic_bajo", "costo_ic_alto", "wape_vs_C0",
                 "wape_ic_alto", "costo_vs_congelado_F2F3"]].to_string(index=False))
    print(f"\nELEGIDO: {elegido}")
    with mlflow.start_run(run_name="busqueda") as run:
        mlflow.set_tags({"hu": "INV-63", "fase": "17-exploracion-2026", "etapa": "busqueda", "elegido": elegido,
                         "commit": hold.commit_actual(), "intento": str(len(previos) + 1),
                         **({"motivo_repeticion": args.repetir} if args.repetir else {}),
                         "confirmacion_tocada": "no"})
        mlflow.log_params({"folds": "F1 2025-07..12, F2 2026-01..02, F3 2026-03..05-03", "n_filas_prueba": len(prueba),
                           "n_origenes_prueba": prueba["fecha_origen"].nunique(), "bootstrap": f"productos, B={B}, semilla={SEMILLA}",
                           "catboost": "1.2.8, depth 6, lr 0.05, 800 iteraciones"})
        for fila in tabla.to_dict("records"):
            for k, v in fila.items():
                if k != "id" and isinstance(v, (int, float)) and not np.isnan(v):
                    mlflow.log_metric(f"{fila['id']}_{k}", float(v))
        for a in ("seleccion.json", "busqueda_candidatos.csv", "busqueda_calibracion.csv", "busqueda_seleccion.csv"):
            mlflow.log_artifact(str(salida / a))
        print(f"MLflow: run busqueda = {run.info.run_id}")
    print(f"listo en {time.time() - t0:.0f} s")


# ── Etapa 3: confirmación ────────────────────────────
def etapa_confirmacion(args, salida):
    t0 = time.time()
    pre = json.loads(RUTA_PREREGISTRO.read_text())
    mlflow = mlflow_cliente()
    assert not runs_previos(mlflow, "busqueda").empty and (salida / "seleccion.json").is_file(), \
        "la selección no está registrada: primero la etapa busqueda"
    previos = runs_previos(mlflow, "confirmacion")
    assert previos.empty or args.repetir, "la confirmación se corre una sola vez; repetirla exige --repetir con el motivo"
    elegido = json.loads((salida / "seleccion.json").read_text())["elegido"]
    paquetes = cargar_paquetes()
    congelado = paquetes["intermitente"]
    specs = especificacion(list(congelado["features"]))
    conf = pre["particiones"]["confirmacion"]
    inter = leer_intermitente(salida)
    tr, te = ex.particion(inter["fecha_origen"], inter["fin_ventana"], conf["origenes_desde"], conf["origenes_hasta"])
    d_tr, d_te = inter[tr], inter[te].copy()
    n_orig = d_te["fecha_origen"].nunique()
    assert n_orig == conf["origenes_esperados"] >= pre["minimo_origenes_confirmacion"], f"orígenes de confirmación: {n_orig}"
    print(f"confirmación: entrenamiento {len(d_tr):,} filas (hasta {d_tr['fin_ventana'].max().date()}), "
          f"prueba {len(d_te):,} filas en {n_orig} orígenes; elegido {elegido}")
    modelos = {c: entrenar(c, specs[c], d_tr, congelado["hparams"]) for c in dict.fromkeys([elegido, "C0"])}
    for c, m in modelos.items():
        d_te[f"p50_{c}"], d_te[f"pneg_{c}"] = predecir(m, d_te)
    d_te["p50_congelado"], d_te["pneg_congelado"] = hold.predecir_lote(congelado, d_te)
    referencia = json.loads(hold.RUTA_PREREGISTRO.read_text())["referencia_intermitente_baseline_cuantil"]
    d_te["piso"] = d_te["nivel_medio_60d"] * ex.HORIZONTE
    d_te["q_ref"] = d_te["estrato"].map(referencia["razon_cuantil_por_estrato"]).fillna(referencia["razon_cuantil_global"]) * (d_te["piso"] + 1)
    for c in [*modelos, "congelado", "ref"]:
        d_te[f"costo_{c}"] = costo(d_te["y"], d_te["q_ref" if c == "ref" else f"pneg_{c}"])
    d_te.to_parquet(salida / "confirmacion_predicciones.parquet", index=False)

    def comparar(c, contra):
        return ex.reglas_confirmacion(ev.mejora_perdida_con_ic(d_te, d_te[f"costo_{c}"], d_te[f"costo_{contra}"], B, SEMILLA),
                                      ev.mejora_con_ic(d_te, "y", f"p50_{c}", f"p50_{contra}", B, SEMILLA),
                                      coberturas(d_te, f"pneg_{c}"))
    principal = comparar(elegido, "congelado")
    extra = {"C0_vs_congelado": comparar("C0", "congelado")}
    if elegido != "C0":
        extra[f"{elegido}_vs_C0"] = comparar(elegido, "C0")
    r1 = ev.mejora_con_ic(d_te, "y", f"p50_{elegido}", "piso", B, SEMILLA)
    r2 = ev.mejora_perdida_con_ic(d_te, d_te[f"costo_{elegido}"], d_te["costo_ref"], B, SEMILLA)
    verdict = ("receta_recomendada_para_INV-62" if principal["cumple"] else "se_mantiene_la_receta_vigente")
    resumen = dict(elegido=elegido, veredicto=verdict, n_origenes=n_orig, n_filas=len(d_te),
                   advertencia=pre["advertencia"], principal={k: v for k, v in principal.items() if k != "detalle_e3"},
                   coberturas_elegido=principal["detalle_e3"].to_dict("records"),
                   reportes={k: {kk: vv for kk, vv in v.items() if kk != "detalle_e3"} for k, v in extra.items()},
                   r1_vs_media_movil=r1, r2_vs_referencia=r2,
                   calibracion={c: dict(n_calib=m["n_calib"], corte=m.get("corte_calib")) for c, m in modelos.items()})
    (salida / "confirmacion.json").write_text(json.dumps(hold.a_json(resumen), ensure_ascii=False, indent=2))
    print(json.dumps(hold.a_json({k: resumen[k] for k in ("elegido", "veredicto", "principal", "reportes", "coberturas_elegido")}),
                     ensure_ascii=False, indent=1))
    with mlflow.start_run(run_name="confirmacion") as run:
        mlflow.set_tags({"hu": "INV-63", "fase": "17-exploracion-2026", "etapa": "confirmacion", "elegido": elegido,
                         "veredicto": verdict, "commit": hold.commit_actual(), "intento": str(len(previos) + 1),
                         **({"motivo_repeticion": args.repetir} if args.repetir else {}),
                         "advertencia": pre["advertencia"][:250]})
        mlflow.log_params({"origenes": f"{conf['origenes_desde']} a {conf['origenes_hasta']} ({n_orig})", "n_filas": len(d_te),
                           "entrenamiento_hasta": str(d_tr["fin_ventana"].max().date())})
        metricas = {"E1": float(principal["E1"]), "E2": float(principal["E2"]), "E3": float(principal["E3"]),
                    "mejora_costo_vs_congelado": principal["mejora_costo"], "costo_ic_bajo": principal["costo_ic"][0],
                    "costo_ic_alto": principal["costo_ic"][1], "mejora_wape_vs_congelado": principal["mejora_wape"],
                    "wape_ic_bajo": principal["wape_ic"][0], "wape_ic_alto": principal["wape_ic"][1],
                    "r1_mejora": r1["mejora_rel"], "r2_mejora": r2["mejora_rel"]}
        metricas |= {f"cobertura_{f['estrato'] or 'rama'}": f["cobertura"] for f in principal["detalle_e3"].to_dict("records")}
        metricas |= {f"{k}_mejora_costo": v["mejora_costo"] for k, v in extra.items()}
        mlflow.log_metrics({k: float(v) for k, v in metricas.items() if v is not None and not np.isnan(v)})
        mlflow.log_artifact(str(salida / "confirmacion.json"))
        print(f"MLflow: run confirmacion = {run.info.run_id}")
    print(f"listo en {time.time() - t0:.0f} s")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("etapa", choices=["matriz", "busqueda", "confirmacion"])
    ap.add_argument("--dw", type=Path, default=RAIZ / "data" / "processed_real")
    ap.add_argument("--inventario-dic", type=Path)
    ap.add_argument("--inventario-sep", type=Path)
    ap.add_argument("--repetir", help="motivo para repetir una etapa ya registrada (queda en MLflow)")
    args = ap.parse_args()
    salida = args.dw.resolve() / "exploracion_2026"
    salida.mkdir(exist_ok=True)
    if args.etapa == "matriz":
        assert args.inventario_dic and args.inventario_sep, "la matriz necesita las dos fotos (D1)"
        etapa_matriz(args, salida)
    elif args.etapa == "busqueda":
        etapa_busqueda(args, salida)
    else:
        etapa_confirmacion(args, salida)


if __name__ == "__main__":
    main()
