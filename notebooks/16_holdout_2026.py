#!/usr/bin/env python3
"""
INV-63 — Evaluación de los modelos de Nivel 1 con las ventas de 2026 (holdout; paso 16 del preregistro).

Evalúa el paquete congelado del 25-sep-2026 (`models/`, entrenado y exportado en el servidor segovia: runs de
INV-17 v2) con las ventas de 2026 y aplica sin cambios las cuatro reglas de `preregistro_holdout_2026.json`
(explicadas en `docs/PREREGISTRO-HOLDOUT-2026.md`; requerimientos y glosario en `docs/INV-63-requerimientos.md`).
En el JSON y en MLflow las reglas se llaman R1 (precisión de la mediana frente a la media móvil), R2 (costo del
cuantil de negocio frente a la referencia simple), R3 (calibración: cobertura a ±0,05 de su objetivo) y R4
(calibración por estrato frente a la predicción sin ajuste). Las dos desviaciones registradas antes de evaluar
se llaman D1 (universo: productos presentes en las fotos de inventario de dic-2025 y sep-2026) y D2 (features
calculadas con el código del servicio).

1. Compuertas, antes de predecir: SHA-256 del paquete y de los parámetros de features (`models/SHA256SUMS`);
   serie diaria neta 2022-2025 idéntica a la del DW vigente (lo exige D2); fotos de inventario con los mismos
   conteos que se midieron al registrar D1.
2. Orígenes: la rejilla mecánica de 2026 (`holdout_2026.origenes_holdout`) y el control de empalme del
   notebook 07 (ninguna ventana puede saltar un bloque sin datos).
3. Features con `ml_service/prediccion/features.py` y los parámetros congelados, con las estáticas a la fecha de
   cada origen, como el servicio. Predicción con `ml_service/prediccion/motor.py` (el motor congelado),
   comprobada fila a fila contra `predecir` en una muestra de 1000 filas.
4. Las cuatro reglas sobre el universo principal (decide) y el universo original del preregistro
   (sensibilidad), y los análisis secundarios, sin decisión.
5. Run en MLflow, experimento `EDA-fix-nivel1-16-holdout-2026`, con las desviaciones y la trazabilidad de los
   runs de segovia.

Las filas (productos, ventas) se quedan en `<dw>/holdout_2026/`, fuera de git; a MLflow van solo agregados.

Uso, desde la raíz del repo, con MLflow en el 5000 (scripts/mlflow_wsl.sh):
    python notebooks/16_holdout_2026.py --dw data/processed_real \\
        --inventario-dic RUTA/foto_2025-12-31.xlsx --inventario-sep RUTA/foto_2026-09-30.xlsx
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(RAIZ / "ml_service"))
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "etl_real"))   # construir_fact_inventario_real importa config de etl_real
import evaluar_nivel1 as ev  # noqa: E402
import holdout_2026 as h  # noqa: E402
import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from etl_real.construir_fact_inventario_real import BODEGA_A_SUCURSAL  # noqa: E402

from prediccion.features import (  # noqa: E402
    Calendario,
    HistoriaInsuficiente,
    determinar_rama,
    factor_calendario,
    features_par,
)
from prediccion.motor import predecir, predecir_lote  # noqa: E402

RUTA_PREREGISTRO = Path(__file__).resolve().parent / "preregistro_holdout_2026.json"
RUTA_PARAMETROS = RAIZ / "models" / "nivel1_parametros_features.json"
EXPERIMENTO_MLFLOW = "EDA-fix-nivel1-16-holdout-2026"
NOMBRE_RUN = "evaluacion_holdout_2026"
RAMAS = ("intermitente", "suave_no_perecedero", "suave_perecedero")
CORTE_HISTORIA = pd.Timestamp("2025-12-31")
ULTIMO_ORIGEN_ENTRENAMIENTO = pd.Timestamp("2025-12-12")   # compuerta de identidad de la matriz congelada
TOLERANCIA_EMPALME = 1.6           # 07: 15 días hábiles no deben abarcar más de 15 * 1,6 días naturales
COSTOS = {"no_perecedero": (0.25, 0.03), "perecedero": (0.20, 1.00)}   # (Cu, Co), métricas del preregistro
SERIE_2022_2025 = dict(registros=1804732, dias_habiles=1362, huella="82d3a820b3d9")   # D2, compuerta_integridad
MUESTRA_MOTOR = 1000
B, SEMILLA = 2000, 0


def sha(ruta, n=12):
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()[:n]


def commit_actual():
    corto = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ, capture_output=True, text=True).stdout.strip()
    sucio = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=RAIZ,
                           capture_output=True, text=True).stdout.strip()
    return corto + ("-con-cambios" if sucio else "")


# ── 1. Compuertas ────────────────────────────────────
def compuerta_paquete(pre):
    sumas = {}
    for linea in (RAIZ / "models" / "SHA256SUMS").read_text().splitlines():
        if linea.strip():
            valor, nombre = linea.split()
            sumas[f"models/{nombre}"] = valor
    distintos = h.verificar_huellas(pre["congelado"]["archivos_sha256"], RAIZ) + h.verificar_huellas(sumas, RAIZ)
    assert not distintos, f"el paquete no es el congelado: {sorted(set(distintos))}"
    print(f"paquete congelado verificado ({len(sumas)} archivos de SHA256SUMS y {len(pre['congelado']['archivos_sha256'])} del preregistro)")
    return sumas


def ventas_netas(dw):
    """Venta diaria neta por par: la definición de dw.v_ventas_diarias_netas (sin devoluciones, cantidad > 0)."""
    v = pd.read_csv(dw / "fact_ventas.csv", usecols=["codigo_item", "sucursal", "fecha", "cantidad", "es_devolucion"],
                    dtype={"codigo_item": str}, parse_dates=["fecha"])
    v = v[(~v["es_devolucion"]) & (v["cantidad"] > 0)]
    return (v.groupby(["codigo_item", "sucursal", "fecha"], as_index=False)["cantidad"].sum()
            .sort_values(["codigo_item", "sucursal", "fecha"]).reset_index(drop=True))


def compuerta_serie(netas):
    g = netas[netas["fecha"] <= CORTE_HISTORIA].reset_index(drop=True)
    obtenido = dict(registros=len(g), dias_habiles=int(g["fecha"].nunique()),
                    huella=hashlib.sha256(pd.util.hash_pandas_object(g, index=False).to_numpy().tobytes()).hexdigest()[:12])
    assert obtenido == SERIE_2022_2025, f"la serie 2022-2025 cambió: {obtenido} frente a {SERIE_2022_2025}"
    print(f"serie diaria neta 2022-2025 idéntica a la del DW vigente: {obtenido}")
    return obtenido


def leer_foto(ruta):
    d = pd.read_excel(ruta, sheet_name="Hoja1", header=3)
    d = d[d["Referencia"].notna()].copy()
    d["codigo_item"] = d["Referencia"].astype(str).str.strip()
    d["sucursal"] = d["Bodega"].astype(str).str.strip().map(BODEGA_A_SUCURSAL)
    return d.groupby(["codigo_item", "sucursal"], as_index=False)["Cantidad"].sum()


def compuerta_d1(pre, foto_dic, foto_sep, estrato_por_par):
    medido = next(d for d in pre["desviaciones"] if d["id"] == "D1")["efecto_medido"]
    productos = set(foto_dic["codigo_item"]) & set(foto_sep["codigo_item"])
    pares_d1 = {p for p in estrato_por_par if p[0] in productos}
    obtenido = dict(productos_en_ambas_fotos=len(productos), pares_universo_preregistrado=len(estrato_por_par),
                    pares_universo_d1=len(pares_d1))
    esperado = {k: medido[k] for k in obtenido}
    assert obtenido == esperado, f"las fotos no son las que midió D1: {obtenido} frente a {esperado}"
    print(f"D1: {obtenido}")
    return productos


# ── 2 y 3. Orígenes, features, objetivo y predicción ─
def origenes_diciembre(habiles, horizonte):
    """Análisis secundario: la rejilla de 07 continuada desde el último origen de entrenamiento, con origen en
    diciembre de 2025 y ventana objetivo en 2026."""
    i = int(np.searchsorted(habiles.values, np.datetime64(ULTIMO_ORIGEN_ENTRENAMIENTO)))
    return pd.DatetimeIndex([habiles[j] for j in range(i + horizonte, len(habiles), horizonte)
                             if habiles[j] <= CORTE_HISTORIA and j + horizonte < len(habiles)])


def control_empalme(habiles, origenes, horizonte):
    filas = []
    for o in origenes:
        i = habiles.get_loc(o)
        ventana = habiles[i + 1:i + 1 + horizonte]
        filas.append(dict(fecha_origen=o, inicio=ventana[0], fin=ventana[-1], dias_naturales=(ventana[-1] - ventana[0]).days + 1))
    tabla = pd.DataFrame(filas)
    malos = tabla[tabla["dias_naturales"] > horizonte * TOLERANCIA_EMPALME]
    assert malos.empty, f"ventanas que empalman un bloque sin datos: {malos.to_dict('records')}"
    return tabla


def construir_filas(series, atributos, calendario, origenes, parametros):
    filas, saltos = [], Counter()
    for origen in origenes:
        t0 = time.time()
        factor = factor_calendario(calendario, origen, parametros)
        n0 = len(filas)
        for (codigo, sucursal), serie in series.items():
            if serie.index[0] > origen:
                saltos["sin_venta_hasta_el_origen"] += 1
                continue
            if codigo not in atributos:
                saltos["sin_dim_producto"] += 1
                continue
            try:
                f = features_par(serie, calendario, origen, origen, parametros, atributos[codigo], factor)
            except HistoriaInsuficiente:
                saltos["historia_insuficiente"] += 1
                continue
            f["codigo_item"], f["sucursal"] = codigo, sucursal
            filas.append(f)
        print(f"  origen {origen.date()}: {len(filas) - n0:,} filas ({time.time() - t0:.0f} s)")
    return pd.DataFrame(filas), dict(saltos)


def agregar_objetivo(filas, netas, habiles, horizonte):
    partes = []
    for origen, g in filas.groupby("fecha_origen", sort=True):
        i = habiles.get_loc(origen)
        ventana = netas[netas["fecha"].isin(habiles[i + 1:i + 1 + horizonte])]
        y = ventana.groupby(["codigo_item", "sucursal"])["cantidad"].sum().rename("y")
        partes.append(g.join(y, on=["codigo_item", "sucursal"]))
    out = pd.concat(partes, ignore_index=True)
    out["y"] = out["y"].fillna(0.0)
    return out


def predecir_filas(filas, paquetes, referencia):
    filas = filas.copy()
    filas["rama"] = [determinar_rama(r) for r in filas[["familia_modelo", "cond2_perecedero"]].to_dict("records")]
    estrato_por_par = paquetes["intermitente"]["estrato_por_par"]
    claves = list(zip(filas["codigo_item"], filas["sucursal"]))
    filas["estrato"] = [estrato_por_par.get(c) for c in claves]
    filas["piso"] = filas["nivel_medio_60d"] * paquetes["intermitente"]["horizonte"]
    for col in ("p50", "pneg", "pneg_sin_cal", "q_ref"):
        filas[col] = np.nan
    for rama in RAMAS:
        m = (filas["rama"] == rama).to_numpy()
        if not m.any():
            continue
        p50, pneg = predecir_lote(paquetes[rama], filas.loc[m])
        filas.loc[m, "p50"], filas.loc[m, "pneg"] = p50, pneg
        filas.loc[m, "alpha"] = paquetes[rama]["alpha_negocio"]
        cu, co = COSTOS["perecedero" if rama == "suave_perecedero" else "no_perecedero"]
        filas.loc[m, "cu"], filas.loc[m, "co"] = cu, co
        if rama == "intermitente":
            sin_cal = {k: v for k, v in paquetes[rama].items() if k not in ("offset_relativo_global", "offset_relativo_por_estrato")}
            filas.loc[m, "pneg_sin_cal"] = predecir_lote(sin_cal, filas.loc[m])[1]
            razon = filas.loc[m, "estrato"].map(referencia["razon_cuantil_por_estrato"]).fillna(referencia["razon_cuantil_global"])
            filas.loc[m, "q_ref"] = razon.to_numpy() * (filas.loc[m, "piso"].to_numpy() + 1.0)
    filas["cubre"] = filas["y"] <= filas["pneg"]
    filas["cubre_sin_cal"] = filas["y"] <= filas["pneg_sin_cal"]
    filas["costo_modelo"] = ev.costo_asimetrico(filas["y"], filas["pneg"], filas["cu"], filas["co"])
    filas["costo_ref"] = ev.costo_asimetrico(filas["y"], filas["q_ref"], filas["cu"], filas["co"])
    filas["costo_sin_cal"] = ev.costo_asimetrico(filas["y"], filas["pneg_sin_cal"], filas["cu"], filas["co"])
    return filas


def comprobar_motor(filas, paquetes):
    """Preregistro (congelado.prediccion): el lote debe coincidir con `predecir` fila a fila (|dif| < 1e-9)."""
    muestra = filas.sample(min(MUESTRA_MOTOR, len(filas)), random_state=SEMILLA)
    peor = 0.0
    for _, fila in muestra.iterrows():
        p50, pneg = predecir(paquetes[fila["rama"]], fila.to_frame().T.infer_objects())
        peor = max(peor, abs(p50 - fila["p50"]), abs(pneg - fila["pneg"]))
    assert peor < 1e-9, f"el lote no coincide con el motor: {peor}"
    print(f"motor: lote = predecir fila a fila en {len(muestra)} filas (máx |dif| = {peor:.1e})")
    return peor


# ── 4. Reglas y análisis secundarios ─────────────────
def resumen(g, b=B):
    """Métricas sin decisión de un grupo de filas: WAPE del q50 frente al piso, cobertura y sesgo del q50."""
    m = ev.mejora_con_ic(g, "y", "p50", "piso", b, SEMILLA)
    y = g["y"].sum()
    return dict(n_filas=len(g), n_pares=int(g[["codigo_item", "sucursal"]].drop_duplicates().shape[0]),
                n_productos=m["n_productos"], wape_modelo=m["wape_modelo"], wape_piso=m["wape_piso"],
                mejora_wape=m["mejora_rel"], ic_bajo=m["ic_bajo"], ic_alto=m["ic_alto"],
                cobertura=float(g["cubre"].mean()) if len(g) else np.nan,
                sesgo_q50=float((g["p50"].sum() - y) / y) if y else np.nan)


def mejora_costo(g, b=B):
    return ev.mejora_perdida_con_ic(g, g["costo_modelo"], g["costo_ref"], b, SEMILLA)


def tabla_reglas(resultado, universo):
    filas = []
    for r in resultado["reglas"]:
        base = dict(universo=universo, regla=r["regla"], estado=r["estado"], cumple=r["cumple"], accion=r["accion"])
        if r["regla"] in ("R1", "R2"):
            base.update(mejora=r["mejora_rel"], ic_bajo=r["ic_bajo"], ic_alto=r["ic_alto"])
        elif r["regla"] == "R4":
            base.update(mejora=r["mejora_costo_rel"], ic_bajo=r["ic_bajo"], ic_alto=r["ic_alto"],
                        detalle=f"{r['estratos_mas_cerca']} de {r['estratos_evaluables']} estratos evaluables mas cerca de 0.893")
        else:
            base.update(detalle=f"ramas que fallan: {r['ramas_que_fallan']}")
        filas.append(base)
    return pd.DataFrame(filas)


def por_estrato_r4(filas):
    inter = filas[filas["rama"] == "intermitente"]
    return pd.DataFrame([dict(estrato=e, n_filas=len(g), cobertura_cal=g["cubre"].mean(),
                              cobertura_sin_cal=g["cubre_sin_cal"].mean(), costo_cal=g["costo_modelo"].sum(),
                              costo_sin_cal=g["costo_sin_cal"].sum(), costo_ref=g["costo_ref"].sum())
                         for e, g in inter.groupby("estrato", sort=True)])


def secundarios(d1, nuevos, dic, n_dic, stock):
    """Todo lo que el preregistro y la ficha piden reportar sin decisión."""
    out = {}
    inter = d1[d1["rama"] == "intermitente"]

    out["wape_por_estrato"] = pd.DataFrame([dict(rama=r, estrato=e, alpha=g["alpha"].iloc[0], **resumen(g))
                                            for (r, e), g in d1.groupby(["rama", "estrato"], sort=True)])
    filas = []
    for o, g in d1.groupby("fecha_origen", sort=True):
        gi = g[g["rama"] == "intermitente"]
        c = mejora_costo(gi)
        filas.append(dict(fecha_origen=o.date().isoformat(), **{f"int_{k}": v for k, v in resumen(gi).items()},
                          int_mejora_costo=c["mejora_rel"], int_costo_ic_bajo=c["ic_bajo"], int_costo_ic_alto=c["ic_alto"],
                          **{f"cobertura_{r}": g.loc[g["rama"] == r, "cubre"].mean() for r in RAMAS}))
    out["por_origen"] = pd.DataFrame(filas)
    filas = []
    for mes, g in d1.groupby(d1["fecha_origen"].dt.to_period("M"), sort=True):
        gi = g[g["rama"] == "intermitente"]
        c = mejora_costo(gi)
        filas.append(dict(mes=str(mes), n_origenes=g["fecha_origen"].nunique(), **{f"int_{k}": v for k, v in resumen(gi).items()},
                          int_mejora_costo=c["mejora_rel"], int_costo_ic_bajo=c["ic_bajo"], int_costo_ic_alto=c["ic_alto"],
                          **{f"cobertura_{r}": g.loc[g["rama"] == r, "cubre"].mean() for r in RAMAS}))
    out["por_mes"] = pd.DataFrame(filas)

    peor_wape = ev.mejora_sin_peor_producto(inter, "y", "p50", "piso", B, SEMILLA)
    exceso = (inter["costo_modelo"] - inter["costo_ref"]).groupby(inter["codigo_item"]).sum().sort_values(ascending=False)
    sin = inter[inter["codigo_item"] != exceso.index[0]]
    peor_costo = dict(producto_excluido=str(exceso.index[0]), **mejora_costo(sin))
    out["sin_peor_producto"] = pd.DataFrame([dict(metrica="R1_wape", **peor_wape), dict(metrica="R2_costo", **peor_costo)])

    out["pares_nuevos"] = pd.DataFrame([dict(rama=r, **resumen(g)) for r, g in nuevos.groupby("rama", sort=True)]
                                       + [dict(rama="todas", **resumen(nuevos))]) if len(nuevos) else pd.DataFrame()

    if len(dic):
        r_dic = h.evaluar_universo(dic, n_dic, B, SEMILLA)
        out["origenes_diciembre_2025"] = tabla_reglas(r_dic, "D1_diciembre_2025").assign(nota="sin decision")
        out["origenes_diciembre_2025_resumen"] = pd.DataFrame([dict(rama=r, **resumen(g)) for r, g in dic.groupby("rama", sort=True)])

    filas = []
    for grupo, mascara in stock.items():
        g = d1[mascara(d1)]
        filas.append(dict(grupo=grupo, rama="todas", **resumen(g)))
        filas += [dict(grupo=grupo, rama=r, **resumen(gr)) for r, gr in g.groupby("rama", sort=True)]
    out["senales_stock"] = pd.DataFrame(filas)
    return out


def _claves(codigos, sucursales):
    return pd.Index(pd.Series(codigos, dtype=str).to_numpy() + "|" + pd.Series(sucursales, dtype=str).to_numpy())


def senales_stock(dw, foto_dic, foto_sep):
    inv = pd.read_csv(dw / "fact_inventario.csv", dtype={"codigo_item": str}, parse_dates=["fecha"])
    inv = inv[(inv["fecha"] == CORTE_HISTORIA) & (inv["stock_disponible"] <= 0)]
    sin_stock = set(_claves(inv["codigo_item"], inv["sucursal"]))
    neg_dic = set(_claves(*foto_dic.loc[foto_dic["Cantidad"] < 0, ["codigo_item", "sucursal"]].T.values))
    neg_sep = set(_claves(*foto_sep.loc[foto_sep["Cantidad"] < 0, ["codigo_item", "sucursal"]].T.values))

    def en(conjunto):
        return lambda d: _claves(d["codigo_item"], d["sucursal"]).isin(conjunto)
    return {
        "stock_<=0_al_2025-12-31": en(sin_stock),
        "stock_>0_al_2025-12-31": lambda d: ~en(sin_stock)(d),
        "negativo_en_las_dos_fotos": en(neg_dic & neg_sep),
        "negativo_solo_en_dic": en(neg_dic - neg_sep),
        "negativo_solo_en_sep": en(neg_sep - neg_dic),
        "sin_negativo": lambda d: ~en(neg_dic | neg_sep)(d),
    }, dict(pares_stock_le_0_dic=len(sin_stock), pares_negativo_dos_fotos=len(neg_dic & neg_sep),
            pares_negativo_solo_dic=len(neg_dic - neg_sep), pares_negativo_solo_sep=len(neg_sep - neg_dic))


# ── 5. MLflow ────────────────────────────────────────
def a_json(x):
    if isinstance(x, pd.DataFrame):
        return x.to_dict("records")
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.floating):
        return None if np.isnan(x) else float(x)
    if isinstance(x, pd.Timestamp):
        return x.date().isoformat()
    if isinstance(x, float) and np.isnan(x):
        return None
    if isinstance(x, dict):
        return {str(k): a_json(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [a_json(v) for v in x]
    return x


def metricas_mlflow(res, prefijo):
    m = {}
    for r in res["reglas"]:
        k = f"{prefijo}_{r['regla']}"
        if r["regla"] in ("R1", "R2"):
            m |= {f"{k}_mejora": r["mejora_rel"], f"{k}_ic_bajo": r["ic_bajo"], f"{k}_ic_alto": r["ic_alto"]}
        elif r["regla"] == "R4":
            m |= {f"{k}_mejora_costo": r["mejora_costo_rel"], f"{k}_ic_bajo": r["ic_bajo"], f"{k}_ic_alto": r["ic_alto"],
                  f"{k}_estratos_mas_cerca": r["estratos_mas_cerca"], f"{k}_estratos_evaluables": r["estratos_evaluables"]}
        else:
            for fila in r["detalle"].to_dict("records"):
                sufijo = fila["rama"] + ("" if fila["estrato"] is None else f"_{fila['estrato']}")
                m[f"{k}_cobertura_{sufijo}"] = fila["cobertura"]
        m[f"{k}_cumple"] = float(r["cumple"])
    return m


def registrar(args, contexto, resultados, tablas, salida):
    import mlflow
    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", ev.MLFLOW_URI_DEFECTO))
    exp = mlflow.set_experiment(EXPERIMENTO_MLFLOW)
    previos = mlflow.search_runs([exp.experiment_id], filter_string=f"tags.mlflow.runName = '{NOMBRE_RUN}'")
    mlflow.set_experiment_tags({"mlflow.note.content": (
        "Holdout limpio con ventas 2026 de los modelos de Nivel 1 (politica v2, INV-63). El preregistro (run "
        "preregistro_v1) y los runs de entrenamiento y exportacion de INV-17 v2 estan en el MLflow del servidor "
        "segovia, donde se entrenaron los modelos; este experimento local guarda la evaluacion con los mismos "
        "nombres e identificadores para la trazabilidad.")})
    pre, d1 = contexto["preregistro"], resultados["D1"]
    with mlflow.start_run(run_name=NOMBRE_RUN) as run:
        mlflow.set_tags({
            "protocolo": "con_purge", "fase": "16-holdout-2026", "hu": "INV-63", "datos_2026_vistos": "si",
            "universo_decision": "D1", "estado": d1["estado"], "veredicto": d1["veredicto"],
            "acciones": " | ".join(d1["acciones"]) or "ninguna", "intento": str(len(previos) + 1),
            "desviaciones": "D1 universo (productos en las fotos 2025-12-31 y 2026-09-30); D2 features con ml_service/prediccion/features.py",
            "commit_congelado": pre["congelado"]["commit"], "commit_evaluacion": contexto["commit"],
            "origen_modelos": "entrenados y exportados en el servidor segovia (INV-17 v2, 2026-09-25)",
            "mlflow_modelos": f"servidor segovia, experimento {pre['congelado']['runs_exportacion_mlflow']['experimento']}",
            "preregistro_run": args.preregistro_run or f"servidor segovia, experimento {EXPERIMENTO_MLFLOW}, run preregistro_v{pre['version']}",
            "fecha_preregistro": pre["fecha_preregistro"],
            **{f"run_exportacion_{r}": v for r, v in pre["congelado"]["runs_exportacion_mlflow"].items() if r != "experimento"},
        })
        mlflow.log_params({
            "version_preregistro": pre["version"], "horizonte": contexto["horizonte"], "n_origenes": d1["n_origenes"],
            "primer_origen": contexto["origenes"][0], "ultimo_origen": contexto["origenes"][-1],
            "origenes_diciembre_2025": ",".join(contexto["origenes_dic"]) or "ninguno",
            "bootstrap": f"productos, B={B}, semilla={SEMILLA}", "min_origenes_veredicto": h.MINIMO_ORIGENES,
            "features": "ml_service/prediccion/features.py, parametros congelados, estaticas a la fecha del origen (D2)",
            "prediccion": "ml_service/prediccion/motor.py::predecir_lote (comprobado contra predecir)",
            **{f"sha256_{Path(k).name}": v[:16] for k, v in contexto["sumas"].items()},
            **{f"dw_{k}": v for k, v in contexto["huellas_dw"].items()},
            **({"parser_ventas_md5": contexto["parser_md5"]} if contexto.get("parser_md5") else {}),
        })
        metricas = metricas_mlflow(d1, "D1") | metricas_mlflow(resultados["v1"], "v1")
        metricas |= {f"n_filas_{k}": v for k, v in contexto["n_filas"].items()}
        metricas |= {f"conteo_{k}": v for k, v in contexto["conteos"].items()}
        metricas["motor_max_dif"] = contexto["motor_max_dif"]
        for k, v in metricas.items():
            if v is not None and not (isinstance(v, float) and np.isnan(v)):
                mlflow.log_metric(k, float(v))
        mlflow.log_artifact(str(salida / "resultado_holdout_2026.json"))
        for nombre in tablas:
            mlflow.log_artifact(str(salida / f"{nombre}.csv"), artifact_path="tablas")
        mlflow.log_artifact(str(RUTA_PREREGISTRO), artifact_path="preregistro")
        for doc in ("docs/PREREGISTRO-HOLDOUT-2026.md", "docs/INV-63-requerimientos.md"):
            if (RAIZ / doc).is_file():
                mlflow.log_artifact(str(RAIZ / doc), artifact_path="preregistro")
        print(f"MLflow: experimento {EXPERIMENTO_MLFLOW}, run {NOMBRE_RUN} = {run.info.run_id} (intento {len(previos) + 1})")
        return run.info.run_id


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dw", type=Path, default=RAIZ / "data" / "processed_real", help="DW en CSV con las ventas 2022-2026")
    ap.add_argument("--inventario-dic", type=Path, required=True, help="foto de inventario del 2025-12-31 (xlsx)")
    ap.add_argument("--inventario-sep", type=Path, required=True, help="foto de inventario del 2026-09-30 (xlsx)")
    ap.add_argument("--parser", type=Path, help="parse_ventas_dir.py ajustado (formato E), para registrar su md5")
    ap.add_argument("--preregistro-run", help="run_id del preregistro en el MLflow de segovia, si se conoce")
    ap.add_argument("--sin-mlflow", action="store_true", help="no registra en MLflow (corrida de prueba)")
    args = ap.parse_args()
    t0 = time.time()
    dw = args.dw.resolve()
    salida = dw / "holdout_2026"
    salida.mkdir(exist_ok=True)

    pre = json.loads(RUTA_PREREGISTRO.read_text())
    parametros = json.loads(RUTA_PARAMETROS.read_text())
    horizonte = parametros["horizonte"]
    sumas = compuerta_paquete(pre)
    paquetes = {r: joblib.load(RAIZ / "models" / f"nivel1_{r}.joblib") for r in RAMAS}
    estrato_por_par = paquetes["intermitente"]["estrato_por_par"]
    assert all(paquetes[r]["estrato_por_par"] == estrato_por_par for r in RAMAS), "los paquetes no comparten estratos"

    netas = ventas_netas(dw)
    serie = compuerta_serie(netas)
    foto_dic, foto_sep = leer_foto(args.inventario_dic), leer_foto(args.inventario_sep)
    productos_d1 = compuerta_d1(pre, foto_dic, foto_sep, estrato_por_par)

    habiles = pd.DatetimeIndex(sorted(netas["fecha"].unique()))
    marcas = pd.read_csv(dw / "dim_tiempo.csv", parse_dates=["fecha"]).set_index("fecha")
    calendario = Calendario(habiles=habiles, marcas=marcas)
    origenes = h.origenes_holdout(habiles, horizonte=horizonte)
    dic = origenes_diciembre(habiles, horizonte)
    empalme = control_empalme(habiles, origenes.append(dic), horizonte)
    print(f"orígenes 2026: {len(origenes)} ({origenes[0].date()} a {origenes[-1].date()}); "
          f"diciembre 2025: {[d.date().isoformat() for d in dic]}; días hábiles hasta {habiles[-1].date()}")

    tipos = pd.read_csv(dw / "dim_sucursal.csv").set_index("nombre")["tipo"]
    modeladas = set(tipos[tipos.isin(parametros["tipos_sucursal_modelo"])].index)
    netas_mod = netas[netas["sucursal"].isin(modeladas)]
    series = {k: pd.Series(g["cantidad"].to_numpy(), index=pd.DatetimeIndex(g["fecha"]))
              for k, g in netas_mod.groupby(["codigo_item", "sucursal"], sort=True)}
    productos = pd.read_csv(dw / "dim_producto.csv", dtype={"codigo_item": str}).set_index("codigo_item")
    columnas = list(parametros["condiciones_producto"].values())
    assert not productos[columnas].isna().any().any(), "atributos del modelo con nulos en dim_producto"
    atributos = productos[columnas].to_dict("index")
    print(f"pares con venta en sucursales modeladas ({sorted(modeladas)}): {len(series):,}")

    filas, saltos = construir_filas(series, atributos, calendario, origenes.append(dic), parametros)
    filas = agregar_objetivo(filas, netas_mod[netas_mod["fecha"] > ULTIMO_ORIGEN_ENTRENAMIENTO], habiles, horizonte)
    filas = predecir_filas(filas, paquetes, pre["referencia_intermitente_baseline_cuantil"])
    motor_max_dif = comprobar_motor(filas, paquetes)
    filas["en_v1"] = filas["estrato"].notna()
    filas["en_d1"] = filas["en_v1"] & filas["codigo_item"].isin(productos_d1)
    filas.to_parquet(salida / "filas_holdout_2026.parquet", index=False)

    es_2026 = filas["fecha_origen"] >= pd.Timestamp("2026-01-01")
    d1, v1 = filas[es_2026 & filas["en_d1"]], filas[es_2026 & filas["en_v1"]]
    nuevos = filas[es_2026 & ~filas["en_v1"]]
    resultados = {"D1": h.evaluar_universo(d1, d1["fecha_origen"].nunique(), B, SEMILLA),
                  "v1": h.evaluar_universo(v1, v1["fecha_origen"].nunique(), B, SEMILLA)}
    stock, conteos_stock = senales_stock(dw, foto_dic, foto_sep)
    sec = secundarios(d1, nuevos, filas[~es_2026 & filas["en_d1"]], len(dic), stock)

    tablas = {"reglas": pd.concat([tabla_reglas(resultados["D1"], "D1"), tabla_reglas(resultados["v1"], "v1_sensibilidad")]),
              "coberturas_r3": pd.concat([resultados[u]["reglas"][2]["detalle"].assign(universo=u) for u in resultados]),
              "r4_por_estrato": pd.concat([por_estrato_r4(x).assign(universo=u) for u, x in (("D1", d1), ("v1", v1))]),
              "resumen_por_rama": pd.DataFrame([dict(universo=u, rama=r, **resumen(g)) for u, x in (("D1", d1), ("v1", v1))
                                                for r, g in x.groupby("rama", sort=True)]),
              "ventanas_objetivo": empalme.astype(str), **sec}
    tablas["sin_peor_producto"] = tablas["sin_peor_producto"].drop(columns="producto_excluido")   # sin códigos en MLflow
    for nombre, tabla in tablas.items():
        tabla.to_csv(salida / f"{nombre}.csv", index=False)

    contexto = dict(preregistro=pre, horizonte=horizonte, sumas=sumas, commit=commit_actual(),
                    origenes=[o.date().isoformat() for o in origenes], origenes_dic=[o.date().isoformat() for o in dic],
                    huellas_dw={n: sha(dw / n) for n in ("fact_ventas.csv", "dim_producto.csv", "dim_tiempo.csv",
                                                        "fact_inventario.csv", "dim_sucursal.csv")}
                    | {"foto_dic": sha(args.inventario_dic), "foto_sep": sha(args.inventario_sep)},
                    parser_md5=hashlib.md5(args.parser.read_bytes()).hexdigest() if args.parser else None,
                    n_filas=dict(total=len(filas), d1=len(d1), v1=len(v1), nuevos=len(nuevos), dic_2025=int((~es_2026 & filas["en_d1"]).sum())),
                    conteos={**saltos, **conteos_stock}, motor_max_dif=motor_max_dif, serie_2022_2025=serie)
    resultado = dict(
        fecha=pd.Timestamp.now().isoformat(timespec="seconds"), experimento=EXPERIMENTO_MLFLOW,
        preregistro_version=pre["version"], desviaciones=[d["id"] for d in pre["desviaciones"]],
        **{u: dict(estado=r["estado"], veredicto=r["veredicto"], acciones=r["acciones"], n_origenes=r["n_origenes"],
                   reglas=[{k: v for k, v in x.items() if k != "detalle"} for x in r["reglas"]]) for u, r in resultados.items()},
        contexto={k: v for k, v in contexto.items() if k != "preregistro"})
    (salida / "resultado_holdout_2026.json").write_text(json.dumps(a_json(resultado), ensure_ascii=False, indent=2))

    print("\n== Reglas ==")
    print(tablas["reglas"].to_string(index=False))
    print("\n== R3: coberturas ==")
    print(tablas["coberturas_r3"].to_string(index=False))
    for u, r in resultados.items():
        print(f"\n{u}: {r['estado']} · {r['veredicto']} · acciones: {r['acciones'] or 'ninguna'}")
    if not args.sin_mlflow:
        resultado["run_id"] = registrar(args, contexto, resultados, tablas, salida)
        (salida / "resultado_holdout_2026.json").write_text(json.dumps(a_json(resultado), ensure_ascii=False, indent=2))
    print(f"\nlisto en {time.time() - t0:.0f} s; tablas en {salida}")


if __name__ == "__main__":
    main()
