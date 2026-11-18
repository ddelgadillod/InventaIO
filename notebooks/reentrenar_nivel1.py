#!/usr/bin/env python3
"""
INV-62 — Reentrenamiento programado de los modelos de pronóstico de Nivel 1 (docs/INV-62-requerimientos.md).

Lo dispara el temporizador de systemd (`scripts/reentrenar.sh`). El flujo de control es `reentrenamiento.orquestar`; aquí
están las operaciones reales:
- versión de los datos: fecha máxima y huella de `<dw>/fact_ventas.csv`; la última corrida terminada se lee de MLflow;
- matriz: orígenes cada 15 días hábiles hasta el último con la ventana completa, sobre los pares de las sucursales
  modeladas cuyo producto está en el catálogo del DW (catálogo vivo), con las features de la receta;
- evaluación: la regla de promoción walk-forward (últimos 12 orígenes, 3 cortes con purge) frente al modelo vigente;
- exportación: si pasa, los tres paquetes, los metadatos y `SHA256SUMS` en una rama local `reentrenamiento/AAAAMMDD`;
  el push y el PR los hace una persona;
- registro: un run por corrida en el experimento `INV-62-reentrenamiento-nivel1`.

Códigos de salida: 0 (sin datos nuevos, rechazado o promovible), 1 (error) y 2 (MLflow no responde).

    python notebooks/reentrenar_nivel1.py --dw RUTA_DW --repo RUTA_REPO
"""
import argparse
import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluar_nivel1 as ev  # noqa: E402
import exploracion_2026 as ex  # noqa: E402
import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import reentrenamiento as re_  # noqa: E402
from exportar_modelos_nivel1 import ALPHA_NEGOCIO, COSTOS_SUPUESTOS, _alpha_negocio_de  # noqa: E402

hold = importlib.import_module("16_holdout_2026")
expl = importlib.import_module("17_exploracion_2026")

EXPERIMENTO = "INV-62-reentrenamiento-nivel1"
RAMAS = ("intermitente", "suave_no_perecedero", "suave_perecedero")
TARGET = "target_demanda_15d"
B, SEMILLA = 2000, 0
# Receta vigente (decisión del 18-nov): LightGBM relativo con las 14 features del paquete y la máscara de censura.
# Las features de calendario se agregan aquí solo si la evaluación preregistrada de la receta lo decide.
FEATURES_EXTRA = []


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


class Operaciones:
    def __init__(self, args):
        self.args, self.dw, self.repo = args, args.dw.resolve(), args.repo.resolve()
        self.uri = os.environ.get("MLFLOW_TRACKING_URI", ev.MLFLOW_URI_DEFECTO)
        self.cache = Path(os.environ.get("REENTRENAMIENTO_CACHE", Path.home() / ".cache" / "inventaio" / "reentrenamiento"))
        self.cache.mkdir(parents=True, exist_ok=True)
        self.inicio = datetime.now()
        self._matriz = None

    # ── compuertas y versión ──
    def mlflow_ok(self):
        import urllib.request
        try:
            with urllib.request.urlopen(f"{self.uri}/health", timeout=10) as r:
                return r.status == 200
        except OSError:
            return False

    def version(self):
        return re_.version_datos(self.dw / "fact_ventas.csv")

    def ultima_version(self):
        mlflow = self._mlflow()
        exp = mlflow.set_experiment(EXPERIMENTO)
        runs = mlflow.search_runs([exp.experiment_id], filter_string="tags.etapa = 'corrida' and tags.estado != 'fallo' "
                                  "and tags.estado != 'sin_datos_nuevos' and tags.estado != 'prueba_exportacion'",
                                  order_by=["start_time DESC"], max_results=1)
        if runs.empty:
            return None
        fila = runs.iloc[0]
        return fila["params.version_fecha"], fila["params.version_huella"]

    # ── matriz con el catálogo vivo ──
    def matriz(self):
        if self._matriz is not None:
            return self._matriz
        t0 = time.time()
        parametros = json.loads((self.repo / "models" / "nivel1_parametros_features.json").read_text())
        netas = hold.ventas_netas(self.dw)
        habiles = pd.DatetimeIndex(sorted(netas["fecha"].unique()))
        marcas = pd.read_csv(self.dw / "dim_tiempo.csv", parse_dates=["fecha"]).set_index("fecha")
        calendario = hold.Calendario(habiles=habiles, marcas=marcas)
        ultimo = habiles[len(habiles) - 1 - ex.HORIZONTE]                     # último origen con la ventana completa
        idx = ex.rejilla(habiles, ancla=ultimo, hasta=ultimo)
        span = np.array([(habiles[i + ex.HORIZONTE] - habiles[i + 1]).days + 1 for i in idx])
        idx = idx[span <= ex.HORIZONTE * hold.TOLERANCIA_EMPALME]
        tipos = pd.read_csv(self.dw / "dim_sucursal.csv").set_index("nombre")["tipo"]
        modeladas = set(tipos[tipos.isin(parametros["tipos_sucursal_modelo"])].index)
        productos = pd.read_csv(self.dw / "dim_producto.csv", dtype={"codigo_item": str}).set_index("codigo_item")
        netas = netas[netas["sucursal"].isin(modeladas) & netas["codigo_item"].isin(productos.index)]
        series = {k: pd.Series(g["cantidad"].to_numpy(), index=pd.DatetimeIndex(g["fecha"]))
                  for k, g in netas.groupby(["codigo_item", "sucursal"], sort=True)}
        atributos = productos[list(parametros["condiciones_producto"].values())].to_dict("index")
        filas, _ = hold.construir_filas(series, atributos, calendario, habiles[idx], parametros)
        pares = [f"{c}|{s}" for c, s in series]
        clave = netas["codigo_item"] + "|" + netas["sucursal"]
        x = (netas.assign(par=clave).pivot_table(index="fecha", columns="par", values="cantidad", aggfunc="sum")
             .reindex(index=habiles, columns=pares).fillna(0.0).to_numpy(dtype=float))
        acumulada = np.cumsum(x, axis=0)
        extra = []
        for i in idx:
            origen = habiles[i]
            dias = calendario.proximos_habiles(origen, ex.HORIZONTE)
            venta_aa = ex.venta_anio_anterior(acumulada, habiles, dias[0], dias[-1])
            extra.append(pd.DataFrame({"par": pares, "fecha_origen": origen, "y": x[i + 1:i + 1 + ex.HORIZONTE].sum(axis=0),
                                       "fin_ventana": habiles[i + ex.HORIZONTE], "venta_aa": venta_aa,
                                       "razon_aa": venta_aa / (ex.trail_anio_anterior(acumulada, habiles, origen) + 1.0),
                                       "mes_origen": origen.month, "dias_naturales_ventana": (dias[-1] - origen).days,
                                       **ex.marcas_ventana(marcas, dias)}))
        filas["par"] = filas["codigo_item"] + "|" + filas["sucursal"]
        filas = filas.merge(pd.concat(extra, ignore_index=True), on=["par", "fecha_origen"], how="left", validate="one_to_one")
        filas["rama"] = [hold.determinar_rama(r) for r in filas[["familia_modelo", "cond2_perecedero"]].to_dict("records")]
        # estratos al corte (últimos 365 días hábiles) y máscara de censura con la foto del DW
        vol = pd.Series(x[-365:].sum(axis=0), index=list(series))
        self.estrato_por_par = re_.estratos_al_corte(vol)
        filas["estrato"] = [self.estrato_por_par.get((c, s), "cola") for c, s in zip(filas["codigo_item"], filas["sucursal"])]
        inv = pd.read_csv(self.dw / "fact_inventario.csv", dtype={"codigo_item": str}, parse_dates=["fecha"])
        fecha_foto = inv["fecha"].max()
        ultima = (netas[netas["fecha"] <= fecha_foto].groupby(["codigo_item", "sucursal"], as_index=False)["fecha"].max()
                  .rename(columns={"fecha": "ultima"}))
        foto = inv[inv["fecha"] == fecha_foto].rename(columns={"stock_disponible": "cantidad"})
        eventos = re_.eventos_censura(foto[["codigo_item", "sucursal", "cantidad"]], ultima, fecha_foto, habiles)
        filas["enmascarada"] = re_.mascara_censura(filas, eventos)
        self.info_matriz = dict(origenes=int(len(idx)), filas=int(len(filas)), corte=str(habiles[-1].date()),
                                ultimo_origen=str(ultimo.date()), foto_inventario=str(fecha_foto.date()),
                                filas_enmascaradas=int(filas["enmascarada"].sum()),
                                pares_por_estrato=pd.Series(self.estrato_por_par).value_counts().to_dict(), segundos=round(time.time() - t0))
        filas.to_parquet(self.cache / "matriz.parquet", index=False)
        self._matriz = filas
        return filas

    def _especificacion(self, vigente):
        return ("lgb", list(vigente["features"]) + FEATURES_EXTRA)

    # ── evaluación walk-forward frente al vigente ──
    def evaluar(self):
        m = self.matriz()
        vigente = joblib.load(self.repo / "models" / "nivel1_intermitente.joblib")
        inter = m[m["rama"] == "intermitente"].reset_index(drop=True)
        spec = self._especificacion(vigente)
        partes = []
        for desde, hasta in re_.cortes_walk_forward(inter["fecha_origen"]):
            tr, te = ex.particion(inter["fecha_origen"], inter["fin_ventana"], desde, hasta)
            modelo = expl.entrenar("candidato", spec, inter[tr & ~inter["enmascarada"].to_numpy()], vigente["hparams"])
            d = inter[te].copy()
            d["p50_cand"], d["pneg_cand"] = expl.predecir(modelo, d)
            d["p50_vig"], d["pneg_vig"] = hold.predecir_lote(vigente, d)
            partes.append(d)
        d = pd.concat(partes, ignore_index=True)
        d["costo_cand"], d["costo_vig"] = expl.costo(d["y"], d["pneg_cand"]), expl.costo(d["y"], d["pneg_vig"])
        regla = ex.reglas_confirmacion(ev.mejora_perdida_con_ic(d, d["costo_cand"], d["costo_vig"], B, SEMILLA),
                                       ev.mejora_con_ic(d, "y", "p50_cand", "p50_vig", B, SEMILLA), expl.coberturas(d, "pneg_cand"))
        forzado = bool(self.args.exportar_sin_regla)
        return dict(cumple=regla["cumple"] or forzado, cumple_regla=regla["cumple"], forzado=forzado, E1=regla["E1"], E2=regla["E2"], E3=regla["E3"], mejora_costo=regla["mejora_costo"],
                    costo_ic=regla["costo_ic"], mejora_wape=regla["mejora_wape"], wape_ic=regla["wape_ic"],
                    coberturas=regla["detalle_e3"].to_dict("records"), n_filas=int(len(d)), n_origenes=int(d["fecha_origen"].nunique()),
                    matriz=self.info_matriz)

    # ── exportación del candidato a su rama ──
    def exportar(self, evaluacion):
        from exportar_modelos_nivel1_v2 import entrenar_baseline
        m = self.matriz().copy()
        m[TARGET] = m["y"]
        vigente = joblib.load(self.repo / "models" / "nivel1_intermitente.joblib")
        entrenables = m[~m["enmascarada"]]
        features = list(vigente["features"]) + FEATURES_EXTRA
        paquetes = {}
        inter = entrenables[entrenables["rama"] == "intermitente"]
        mod = expl.entrenar("final", ("lgb", features), inter, vigente["hparams"])
        paquetes["intermitente"] = {
            "tipo": "relativo", "modelo_q50": mod["m50"], "modelo_qneg": mod["mneg"], "horizonte": ex.HORIZONTE, "base_offset": 1.0,
            "offset_conformal_qneg": None, "hparams": vigente["hparams"], "estrato_por_par": self.estrato_por_par,
            "offset_relativo_por_estrato": mod["offsets"], "offset_relativo_global": mod["offset_global"],
            "calibracion": {"metodo": "split-CQR por estrato (INV-62)", "fraccion_calib": 0.2, "corte_fecha_origen": mod["corte_calib"],
                            "n_calib_por_estrato": mod["n_calib"]}}
        for rama in ("suave_no_perecedero", "suave_perecedero"):
            paquetes[rama] = entrenar_baseline(entrenables[entrenables["rama"] == rama], rama, self.estrato_por_par)
        for rama, p in paquetes.items():
            n = int((entrenables["rama"] == rama).sum())
            p.update({"rama": rama, "alpha_negocio": _alpha_negocio_de(rama), "features": features, "target": TARGET,
                      "n_filas_entrenamiento": n})
        fecha = self.inicio.strftime("%Y%m%d")
        rama_git = f"reentrenamiento/{'prueba-' if evaluacion.get('forzado') else ''}{fecha}-{self.inicio:%H%M}"
        destino = Path(tempfile.mkdtemp(prefix="reentrenamiento-"))
        try:
            _git(self.repo, "worktree", "add", "-b", rama_git, str(destino), self.args.base)
            modelos = destino / "models"
            for rama, p in paquetes.items():
                joblib.dump(p, modelos / f"nivel1_{rama}.joblib")
            metadata = json.loads((modelos / "nivel1_metadata.json").read_text())
            metadata.update({"hu": "INV-62", "fecha_generacion": datetime.now(UTC).isoformat(), "features": features,
                             "costos": COSTOS_SUPUESTOS, "alpha_negocio": ALPHA_NEGOCIO,
                             "estratos": {"fecha_corte": evaluacion["matriz"]["corte"], "ventana_dias_habiles": 365,
                                          "cortes_volumen_acumulado": [0.5, 0.8],
                                          "pares_por_estrato": evaluacion["matriz"]["pares_por_estrato"]},
                             "entrada_datos": dict(zip(("fecha_maxima", "huella_fact_ventas"), self.version())),
                             "promocion": {k: evaluacion[k] for k in ("mejora_costo", "costo_ic", "mejora_wape", "wape_ic", "n_origenes")},
                             "nota": "Candidato del reentrenamiento programado (INV-62); se integra por PR."})
            for rama, p in paquetes.items():
                metadata.setdefault("ramas", {})[rama] = {"archivo": f"nivel1_{rama}.joblib", "tipo_modelo": p["tipo"],
                                                          "alpha_negocio": p["alpha_negocio"], "n_filas_entrenamiento": p["n_filas_entrenamiento"]}
            (modelos / "nivel1_metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False, default=str))
            sumas = []
            for archivo in sorted(modelos.glob("nivel1_*")):
                sumas.append(f"{hashlib.sha256(archivo.read_bytes()).hexdigest()}  {archivo.name}")
            (modelos / "SHA256SUMS").write_text("\n".join(sumas) + "\n")
            _git(destino, "add", "models")
            _git(destino, "-c", "user.name=ddelgadillod", "-c", "user.email=diegodelgadilloduran@gmail.com", "commit", "-q", "-m",
                 f"feat(models): candidato del reentrenamiento programado con datos hasta {evaluacion['matriz']['corte']}; costo "
                 f"{evaluacion['mejora_costo']:+.1%} frente al vigente en {evaluacion['n_origenes']} orígenes walk-forward (INV-62)")
            self.paquetes_dir = modelos
            shutil.copytree(modelos, self.cache / "candidato", dirs_exist_ok=True)
        finally:
            subprocess.run(["git", "-C", str(self.repo), "worktree", "remove", "--force", str(destino)], capture_output=True)
        return rama_git

    # ── registro ──
    def _mlflow(self):
        import mlflow
        mlflow.set_tracking_uri(self.uri)
        return mlflow

    def registrar(self, estado, info):
        mlflow = self._mlflow()
        mlflow.set_experiment(EXPERIMENTO)
        version = info.get("version", ("", ""))
        e = info.get("evaluacion")
        if e and e.get("forzado") and not e.get("cumple_regla"):
            estado = "prueba_exportacion"          # exportada solo para verificar el proceso: no es un candidato
        with mlflow.start_run(run_name=f"corrida_{self.inicio:%Y%m%d-%H%M}") as run:
            mlflow.set_tags({"hu": "INV-62", "etapa": "corrida", "estado": estado, "commit": hold.commit_actual(),
                             **({"rama_candidato": info["rama"]} if info.get("rama") else {}),
                             **({"error": info["error"][:500]} if info.get("error") else {})})
            mlflow.log_params({"version_fecha": version[0], "version_huella": version[1], "dw": str(self.dw),
                               "receta": "LightGBM relativo, 14 features" + (f" + {len(FEATURES_EXTRA)} de calendario" if FEATURES_EXTRA else "")
                               + ", máscara de censura"})
            if e:
                mlflow.log_metrics({"mejora_costo": e["mejora_costo"], "costo_ic_bajo": e["costo_ic"][0], "costo_ic_alto": e["costo_ic"][1],
                                    "mejora_wape": e["mejora_wape"], "wape_ic_alto": e["wape_ic"][1], "E1": float(e["E1"]),
                                    "E2": float(e["E2"]), "E3": float(e["E3"]), "n_origenes": e["n_origenes"], "n_filas": e["n_filas"]})
                for c in e["coberturas"]:
                    mlflow.log_metric(f"cobertura_{c['estrato'] or 'rama'}", float(c["cobertura"]))
                ruta = self.cache / "evaluacion.json"
                ruta.write_text(json.dumps(hold.a_json(e), ensure_ascii=False, indent=2))
                mlflow.log_artifact(str(ruta))
            if getattr(self, "paquetes_dir", None):
                mlflow.log_artifact(str(self.cache / "candidato" / "nivel1_metadata.json"), artifact_path="candidato")
                mlflow.log_artifact(str(self.cache / "candidato" / "SHA256SUMS"), artifact_path="candidato")
            return run.info.run_id


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dw", type=Path, required=True, help="DW en CSV (salida del ETL) con los datos al día")
    ap.add_argument("--repo", type=Path, required=True, help="repositorio con los modelos vigentes en models/")
    ap.add_argument("--base", default="develop", help="rama desde la que se crea la rama del candidato")
    ap.add_argument("--exportar-sin-regla", action="store_true",
                    help="solo para verificar el proceso: exporta el candidato aunque no cumpla la regla (rama reentrenamiento/prueba-…, "
                         "estado prueba_exportacion); nunca desde el temporizador")
    args = ap.parse_args()
    t0 = time.time()
    try:
        salida = re_.orquestar(Operaciones(args))
    except re_.MlflowNoResponde as e:
        print(f"FALLA: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 -- la falla queda registrada en MLflow por orquestar y en el journal
        print(f"FALLA: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    resumen = {k: v for k, v in salida.items() if k != "evaluacion"}
    if "evaluacion" in salida:
        e = salida["evaluacion"]
        resumen["regla"] = (f"costo {e['mejora_costo']:+.2%} [{e['costo_ic'][0]:+.2%}; {e['costo_ic'][1]:+.2%}], "
                            f"WAPE {e['mejora_wape']:+.2%}, criterios {e['E1']}/{e['E2']}/{e['E3']}")
    print(f"corrida terminada en {time.time() - t0:.0f} s: {resumen}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
