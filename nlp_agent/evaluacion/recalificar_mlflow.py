"""
Pasa el verificador del agente (`agente/fidelidad.py`) por las respuestas ya guardadas de una corrida y lo
registra en MLflow como un run de tipo `recalificacion` (INV-33, Z12 y M3). Sin el modelo ni la GPU.

    cd nlp_agent
    python -m evaluacion.recalificar_mlflow evaluacion/resultados/2026-10-21_local-decisiones/*.jsonl --historia INV-33

Por cada respuesta: si el verificador está de acuerdo con la fidelidad guardada (la del calificador), si
pediría un reintento (cifras sin respaldo o un total omitido) y si le faltaría la fecha (el cierre fijo de Z2).
Es la medida de partida del bucle de INV-33: cuántas respuestas reintentaría el agente y por qué.
"""
import argparse
import asyncio
import csv
import io
import json
import os
import sys
import tempfile
from pathlib import Path

from agente.fidelidad import verificar
from evaluacion import procedencia
from evaluacion import registro_mlflow as rm
from evaluacion.arnes import EjecutorSintetico, contexto_de
from evaluacion.calificacion import _prompt_agente
from evaluacion.conjunto import cargar, herramientas


async def _sinteticos(ejecutor, llamadas):
    salida = []
    for ll in llamadas:
        p = ejecutor.preparar(ll["herramienta"], ll["argumentos"])
        salida.append({"error": str(p.error)} if p.error is not None else (await ejecutor.ejecutar(p)).para_modelo)
    return salida


def filas(ruta: Path) -> tuple[dict, list[dict]]:
    """El meta del archivo y, por respuesta, lo que dice el verificador."""
    lineas = [json.loads(x) for x in ruta.read_text(encoding="utf-8").splitlines() if x.strip()]
    meta = lineas[0]
    version = meta["conjunto"].split()[0]
    if version == "v0":
        sys.exit("El verificador usa el prompt y el catálogo del agente: solo para el v1")
    real = "(real" in meta["conjunto"]
    variante = "colab" if "(colab" in meta["conjunto"] else "local"
    conjunto = cargar("local" if real else variante, version)
    catalogo = herramientas("local" if real else variante, version)
    salida = []
    for c in lineas[1:]:
        p = conjunto.por_id(c["id"])
        resultados = (c.get("resultados") or [] if real
                      else asyncio.run(_sinteticos(EjecutorSintetico(p, conjunto.fecha_datos, catalogo), c["llamadas"])))
        referencia = f"{p.pregunta}\n{contexto_de(_prompt_agente(p, meta), catalogo)}"
        v = verificar(c["texto"], referencia, resultados)
        recortadas = [r for r in resultados if isinstance(r, dict) and isinstance(r.get("total"), int)
                      and r["total"] > r.get("mostrando", r["total"])]
        con_fecha = any(isinstance(r, dict) and r.get("fecha_dato") for r in resultados)
        salida.append({"id": c["id"], "corrida": c["corrida"], "fidelidad_guardada": c["calificacion"]["fidelidad"],
                       "fidelidad_verificador": not v.cifras_sin_respaldo, "reintento": not v.ok,
                       "cifras_sin_respaldo": " ".join(v.cifras_sin_respaldo),
                       "lista_recortada": bool(recortadas), "total_omitido": bool(v.totales_omitidos),
                       "con_datos": con_fecha, "fecha_omitida": v.fecha is not None})
    return meta, salida


def metricas(f: list[dict]) -> dict:
    def tasa(clave, sobre=None):
        base = [x for x in f if sobre is None or x[sobre]]
        return round(sum(x[clave] for x in base) / len(base), 4) if base else 0.0
    return {"respuestas": float(len(f)), "fidelidad_guardada": tasa("fidelidad_guardada"),
            "fidelidad_verificador": tasa("fidelidad_verificador"),
            "cambian_fidelidad": float(sum(x["fidelidad_guardada"] != x["fidelidad_verificador"] for x in f)),
            "tasa_reintento": tasa("reintento"),
            "con_lista_recortada": float(sum(x["lista_recortada"] for x in f)),
            "tasa_total_omitido": tasa("total_omitido", "lista_recortada"),
            "con_datos": float(sum(x["con_datos"] for x in f)), "tasa_fecha_omitida": tasa("fecha_omitida", "con_datos")}


def registrar(ruta: Path, uri: str, historia: str | None) -> str:
    from mlflow import MlflowClient
    from mlflow.entities import Metric, RunTag
    [origen] = rm.registrar([ruta], rm.ClienteMlflow(uri), historia)          # el run de la corrida (ya estaba)
    c = MlflowClient(uri)
    run_origen = c.get_run(origen)
    meta, f = filas(ruta)
    m = metricas(f)
    previos = c.search_runs([run_origen.info.experiment_id],
                            filter_string=f"tags.recalifica = '{origen}' and tags.verificador = '{_huella_verificador()}'")
    if previos:
        print(f"{ruta}: ya estaba ({previos[0].info.run_id})")
        return previos[0].info.run_id
    nombre = f"{run_origen.info.run_name} · recalificación"
    run = c.create_run(run_origen.info.experiment_id, run_name=nombre)
    nota = "\n".join([
        f"**Recalificación con el verificador del agente** (`agente/fidelidad.py`) de `{ruta.parent.name}/{ruta.name}`, "
        f"sin volver a correr el modelo. Run de origen: `{origen}`.", "",
        "| Métrica | Valor |", "| --- | --- |",
        f"| Respuestas | {int(m['respuestas'])} |",
        f"| Fidelidad guardada (calificador) | {m['fidelidad_guardada'] * 100:.1f} % |",
        f"| Fidelidad del verificador | {m['fidelidad_verificador'] * 100:.1f} % ({int(m['cambian_fidelidad'])} cambian) |",
        f"| Pedirían reintento | {m['tasa_reintento'] * 100:.1f} % |",
        f"| Omiten el total (de {int(m['con_lista_recortada'])} con lista recortada) | {m['tasa_total_omitido'] * 100:.1f} % |",
        f"| Omiten la fecha (de {int(m['con_datos'])} con datos) | {m['tasa_fecha_omitida'] * 100:.1f} % |", "",
        "Si «cambian» no es 0, el verificador y el calificador ya no miden lo mismo: revisar antes de usarlo en el bucle.",
    ])
    tags = {"tipo": "recalificacion", "recalifica": origen, "verificador": _huella_verificador(),
            "archivo": f"{ruta.parent.name}/{ruta.name}", "conjunto": run_origen.data.tags.get("conjunto", ""),
            "datos": run_origen.data.tags.get("datos", ""), **procedencia.etiquetas(procedencia.git()),
            **({"historia": historia} if historia else {}), "mlflow.note.content": nota}
    c.log_batch(run.info.run_id, metrics=[Metric(k, v, run.info.start_time, 0) for k, v in m.items()],
                tags=[RunTag(k, v) for k, v in tags.items() if v])
    with tempfile.TemporaryDirectory() as tmp:
        csv_ruta = Path(tmp) / "verificador_por_respuesta.csv"
        salida = io.StringIO()
        w = csv.DictWriter(salida, fieldnames=list(f[0]))
        w.writeheader()
        w.writerows(f)
        csv_ruta.write_text(salida.getvalue(), encoding="utf-8")
        c.log_artifact(run.info.run_id, str(csv_ruta))
    c.set_terminated(run.info.run_id)
    print(f"{ruta}: {nombre} → {run.info.run_id}")
    return run.info.run_id


def _huella_verificador() -> str:
    return rm._huella((Path(__file__).resolve().parents[1] / "agente" / "fidelidad.py").read_text(encoding="utf-8"))[:12]


def main(argv=None) -> list[str]:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("archivos", nargs="+")
    a.add_argument("--historia")
    a.add_argument("--tracking-uri", default=os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000"))
    args = a.parse_args(argv)
    if not args.tracking_uri.startswith(("http://127.0.0.1", "http://localhost", "sqlite:", "file:")):
        sys.exit("El registro es local (D22, N9): usa el servidor de scripts/mlflow_wsl.sh")
    return [registrar(Path(r), args.tracking_uri, args.historia) for r in args.archivos]


if __name__ == "__main__":
    main()
