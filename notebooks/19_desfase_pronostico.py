#!/usr/bin/env python3
"""
INV-62 — Medición preregistrada del desfase del pronóstico al día presente (`preregistro_desfase_2026.json`).

Cuando no hay ventas recientes, el pronóstico de hoy usa features calculadas con el último dato y una ventana que empieza
varios días hábiles después. Aquí se mide, con el historial de 2026, cuánto cambian la cobertura del cuantil de negocio, el
WAPE de la mediana y el costo para desfases de 0 a 90 días hábiles. Para cada desfase se estima un ajuste conformal por
rama y estrato (ene-abr 2026) y se evalúa (may-jul 2026); el ajuste entra si la regla del preregistro lo pide.

Salidas en `<dw>/reentrenamiento_2026/` (agregados) y, si algún ajuste entra, la tabla `ajuste_desfase.json` para
`models/`. Run `medicion_desfase` en MLflow.

    python notebooks/19_desfase_pronostico.py --dw RUTA_DW_INV63
"""
import argparse
import importlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluar_nivel1 as ev  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

hold = importlib.import_module("16_holdout_2026")
expl = importlib.import_module("17_exploracion_2026")

RUTA_PREREGISTRO = Path(__file__).resolve().parent / "preregistro_desfase_2026.json"
EXPERIMENTO = "INV-62-reentrenamiento-nivel1"
H = 15
ESTRATOS = ("cabeza", "medio", "cola")
MINIMO = 200
TOLERANCIA = 0.05
COSTOS = {"intermitente": (0.25, 0.03), "suave_no_perecedero": (0.25, 0.03), "suave_perecedero": (0.20, 1.00)}


def cuantil_conformal(v, nivel):
    n = len(v)
    return float(np.quantile(v, min(1.0, np.ceil((n + 1) * nivel) / n)))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dw", type=Path, required=True)
    args = ap.parse_args()
    t0 = time.time()
    pre = json.loads(RUTA_PREREGISTRO.read_text())
    dw = args.dw.resolve()
    salida = dw / "reentrenamiento_2026"
    salida.mkdir(exist_ok=True)
    paquetes = expl.cargar_paquetes()
    parametros = json.loads(hold.RUTA_PARAMETROS.read_text())

    m = pd.read_parquet(dw / "exploracion_2026" / "matriz_exploracion.parquet")
    m = m[m["fecha_origen"] >= "2026-01-01"].reset_index(drop=True)
    netas = hold.ventas_netas(dw)
    habiles = pd.DatetimeIndex(sorted(netas["fecha"].unique()))
    marcas = pd.read_csv(dw / "dim_tiempo.csv", parse_dates=["fecha"]).set_index("fecha")
    calendario = hold.Calendario(habiles=habiles, marcas=marcas)
    pares = sorted(set(m["par"]))
    clave = netas["codigo_item"] + "|" + netas["sucursal"]
    x = (netas[clave.isin(set(pares))].assign(par=clave).pivot_table(index="fecha", columns="par", values="cantidad", aggfunc="sum")
         .reindex(index=habiles, columns=pares).fillna(0.0).to_numpy(dtype=float))
    acum = np.vstack([np.zeros((1, x.shape[1])), np.cumsum(x, axis=0)])        # acum[k] = suma de las filas 0..k-1
    col = {p: j for j, p in enumerate(pares)}
    m["i"] = habiles.get_indexer(m["fecha_origen"])
    m["j"] = m["par"].map(col)
    ultimo = len(habiles) - 1

    filas = []
    for G in pre["desfases_dias_habiles"]:
        d = m[m["i"] + G + H <= ultimo].copy()
        d["yG"] = acum[d["i"] + G + H + 1, d["j"]] - acum[d["i"] + G + 1, d["j"]]
        factores = {o: hold.factor_calendario(calendario, habiles[i + G], parametros) for o, i in d.groupby("fecha_origen")["i"].first().items()}
        d["factor_calendario_ventana"] = d["fecha_origen"].map(factores)
        d["periodo"] = np.where(d["fecha_origen"] <= "2026-04-30", "estimacion", np.where(d["fecha_origen"] <= "2026-07-31", "evaluacion", "fuera"))
        d = d[d["periodo"] != "fuera"]
        for rama, g in d.groupby("rama", sort=True):
            paq = paquetes[rama]
            p50, pneg = hold.predecir_lote(paq, g)
            alpha = paq["alpha_negocio"]
            piso = g["nivel_medio_60d"].to_numpy() * H
            if paq["tipo"] == "relativo":
                base = piso + paq.get("base_offset", 1.0)
                q = np.asarray(paq["modelo_qneg"].predict(g[paq["features"]]), dtype=float)
                residuo = g["yG"].to_numpy() / base - q
            else:
                base, q = piso + 1.0, None
                residuo = g["yG"].to_numpy() / base
            est = g["periodo"].to_numpy() == "estimacion"
            estrato = g["estrato"].fillna("cola").to_numpy()
            calc = (lambda v: cuantil_conformal(v, alpha)) if paq["tipo"] == "relativo" else (lambda v: float(np.quantile(v, alpha)))
            glob = calc(residuo[est]) if est.any() else np.nan
            ajuste = {e: (calc(residuo[est & (estrato == e)]) if (est & (estrato == e)).sum() >= MINIMO else glob) for e in ESTRATOS}
            off = np.array([ajuste[e] for e in estrato])
            pneg_aj = np.clip(base * (q + off), 0, None) if q is not None else np.clip(off * base, 0, None)
            cu, co = COSTOS[rama]
            for periodo in ("estimacion", "evaluacion"):
                s = g["periodo"].to_numpy() == periodo
                if not s.any():
                    continue
                y = g["yG"].to_numpy()[s]
                for e in (None, *ESTRATOS):
                    k = s if e is None else s & (estrato == e)
                    if k.sum() == 0:
                        continue
                    yk = g["yG"].to_numpy()[k]
                    filas.append(dict(desfase=G, rama=rama, periodo=periodo, estrato=e or "rama", alpha=alpha, n_filas=int(k.sum()),
                                      cobertura_sin=float((yk <= pneg[k]).mean()), cobertura_con=float((yk <= pneg_aj[k]).mean()),
                                      wape=ev.wape(yk, p50[k]), costo_sin=float(ev.costo_asimetrico(yk, pneg[k], cu, co).sum()),
                                      costo_con=float(ev.costo_asimetrico(yk, pneg_aj[k], cu, co).sum()),
                                      ajuste={k2: round(v, 6) for k2, v in ajuste.items()} if e is None and periodo == "estimacion" else None,
                                      ajuste_global=round(glob, 6) if e is None and periodo == "estimacion" else None,
                                      tipo=paq["tipo"]))
                del y
        print(f"desfase {G}: {len(d):,} filas ({time.time() - t0:.0f} s)")
    tabla = pd.DataFrame(filas)
    tabla.to_csv(salida / "desfase_tabla.csv", index=False)

    decisiones, ajustes = [], {}
    for G, g in tabla[(tabla["periodo"] == "evaluacion") & (tabla["estrato"] == "rama")].groupby("desfase"):
        fuera_sin = (g["cobertura_sin"] - g["alpha"]).abs() > TOLERANCIA
        dentro_con = (g["cobertura_con"] - g["alpha"]).abs() <= TOLERANCIA
        entra = bool(fuera_sin.any() and dentro_con.all())
        decisiones.append(dict(desfase=int(G), ramas_fuera_sin_ajuste=sorted(g.loc[fuera_sin, "rama"]), con_ajuste_todas_dentro=bool(dentro_con.all()),
                               entra_ajuste=entra, n_filas=int(g["n_filas"].sum())))
        if entra:
            est = tabla[(tabla["desfase"] == G) & (tabla["periodo"] == "estimacion") & (tabla["estrato"] == "rama")]
            ajustes[str(int(G))] = {r["rama"]: {"tipo": r["tipo"], "por_estrato": r["ajuste"], "global": r["ajuste_global"]} for r in est.to_dict("records")}
    sin_evaluacion = sorted(set(pre["desfases_dias_habiles"]) - {d["desfase"] for d in decisiones})
    resultado = dict(decisiones=decisiones, desfases_sin_evaluacion=sin_evaluacion, ajustes=ajustes)
    (salida / "desfase_resultado.json").write_text(json.dumps(hold.a_json(resultado), ensure_ascii=False, indent=2))
    if ajustes:
        (salida / "ajuste_desfase.json").write_text(json.dumps({"version": 1, "fecha": "2026-11-18", "hu": "INV-62",
                                                                 "regla": pre["regla"], "ajustes": ajustes}, ensure_ascii=False, indent=2))
    pd.set_option("display.width", 220)
    vista = tabla[(tabla["estrato"] == "rama")][["desfase", "rama", "periodo", "n_filas", "alpha", "cobertura_sin", "cobertura_con", "wape"]]
    print(vista.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(json.dumps(hold.a_json(decisiones), ensure_ascii=False))
    mlflow = expl.mlflow_cliente()
    mlflow.set_experiment(EXPERIMENTO)
    with mlflow.start_run(run_name="medicion_desfase") as run:
        mlflow.set_tags({"hu": "INV-62", "etapa": "medicion_desfase", "commit": hold.commit_actual(),
                         "ajustes_que_entran": ",".join(ajustes) or "ninguno"})
        for f in tabla[(tabla["estrato"] == "rama") & (tabla["periodo"] == "evaluacion")].to_dict("records"):
            mlflow.log_metric(f"G{f['desfase']}_{f['rama']}_cobertura_sin", f["cobertura_sin"])
            mlflow.log_metric(f"G{f['desfase']}_{f['rama']}_cobertura_con", f["cobertura_con"])
            mlflow.log_metric(f"G{f['desfase']}_{f['rama']}_wape", f["wape"])
        for a in ("desfase_tabla.csv", "desfase_resultado.json"):
            mlflow.log_artifact(str(salida / a))
        print(f"MLflow: run medicion_desfase = {run.info.run_id}")
    print(f"listo en {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
