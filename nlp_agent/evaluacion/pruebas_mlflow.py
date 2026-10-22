"""
Corre las pruebas sin modelo y las registra en MLflow (INV-33, decisión M1 del 21-oct).

    bash scripts/mlflow_wsl.sh iniciar
    cd nlp_agent
    python -m evaluacion.pruebas_mlflow --historia INV-33                          # las tres suites
    python -m evaluacion.pruebas_mlflow --historia INV-33 --suites newman --base-url http://localhost:8010 \\
        --colecciones INV-33,INV-25
    python -m evaluacion.pruebas_mlflow --historia INV-33 --suites api --api-contenedor inventaio-api-inv33

Experimento `inventaio-pruebas`, un run por suite y ejecución:

- **nlp_agent:** pytest del agente (sin las del modelo real), con su reporte JUnit.
- **api:** pytest del Core API dentro de su contenedor, con su reporte JUnit.
- **newman · <colección>:** una colección Postman contra el Core API, con un resumen de las verificaciones (sin
  los cuerpos de las respuestas: pueden traer cifras reales).

Cada run lleva la procedencia de git (commit, rama, cambios sin commit), la historia, el entorno, las cifras
(pruebas, fallidas, duración; peticiones y verificaciones en newman) y una nota con las fallas.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from evaluacion import procedencia

EXPERIMENTO = "inventaio-pruebas"
DESCRIPCION = (
    "Pruebas sin modelo de InventaIO (INV-33, M1): pytest del agente y del Core API y colecciones Postman con "
    "newman. Un run por suite y ejecución, con el commit del que salen (mlflow.source.git.commit), la historia y "
    "las fallas en la nota. Las mediciones del agente con el modelo están en agente-conjunto-v0 y -v1.")
COLECCIONES = ("INV-33", "INV-25", "INV-26-fix", "INV-28")
RAIZ = procedencia.RAIZ


def leer_junit(xml: str) -> dict:
    """Cifras y fallas de un reporte JUnit de pytest."""
    raiz = ET.fromstring(xml)
    suite = raiz if raiz.tag == "testsuite" else raiz.find("testsuite")
    fallas = []
    for caso in suite.iter("testcase"):
        for tipo in ("failure", "error"):
            if (f := caso.find(tipo)) is not None:
                fallas.append(f"{caso.get('classname')}::{caso.get('name')} — {(f.get('message') or '')[:200]}")
    pruebas, fallidas = int(suite.get("tests", 0)), int(suite.get("failures", 0))
    errores, omitidas = int(suite.get("errors", 0)), int(suite.get("skipped", 0))
    return {"metricas": {"pruebas": pruebas, "pasadas": pruebas - fallidas - errores - omitidas, "fallidas": fallidas,
                         "errores": errores, "omitidas": omitidas, "duracion_s": round(float(suite.get("time", 0)), 2)},
            "fallas": fallas}


def leer_newman(reporte: dict) -> dict:
    """Cifras, fallas y un resumen por petición del reporte JSON de newman, sin las respuestas."""
    run = reporte["run"]
    stats = run["stats"]
    ejecuciones = [{"peticion": e["item"]["name"], "codigo": (e.get("response") or {}).get("code"),
                    "verificaciones": [{"nombre": a["assertion"], "ok": "error" not in a} for a in e.get("assertions", [])]}
                   for e in run.get("executions", [])]
    fallas = [f"{f['source']['name']} — {f['error'].get('test') or f['error'].get('message', '')}"[:250]
              for f in run.get("failures", [])]
    t = run.get("timings", {})
    return {"metricas": {"peticiones": stats["requests"]["total"], "peticiones_fallidas": stats["requests"]["failed"],
                         "verificaciones": stats["assertions"]["total"],
                         "verificaciones_fallidas": stats["assertions"]["failed"],
                         "duracion_s": round((t.get("completed", 0) - t.get("started", 0)) / 1000, 2)},
            "fallas": fallas, "resumen": {"coleccion": reporte["collection"]["info"]["name"], "ejecuciones": ejecuciones}}


def _correr(comando: list[str], cwd: Path) -> tuple[int, str]:
    p = subprocess.run(comando, cwd=cwd, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr)[-6000:]


def suite_nlp_agent(tmp: Path) -> dict:
    junit = tmp / "junit-nlp_agent.xml"
    comando = [sys.executable, "-m", "pytest", "-q", "-m", "not llm", f"--junitxml={junit}"]
    codigo, salida = _correr(comando, RAIZ / "nlp_agent")
    return {"suite": "nlp_agent", "entorno": "pytest local", "comando": " ".join(comando[1:]), "codigo": codigo,
            "salida": salida, **leer_junit(junit.read_text(encoding="utf-8")), "artefactos": [junit]}


def suite_api(tmp: Path, contenedor: str) -> dict:
    comando = ["docker", "exec", contenedor, "python", "-m", "pytest", "-q", "--junitxml=/tmp/junit-api.xml"]
    codigo, salida = _correr(comando, RAIZ)
    junit = tmp / "junit-api.xml"
    subprocess.run(["docker", "cp", f"{contenedor}:/tmp/junit-api.xml", str(junit)], check=True, capture_output=True)
    return {"suite": "api", "entorno": f"contenedor {contenedor}", "comando": " ".join(comando), "codigo": codigo,
            "salida": salida, **leer_junit(junit.read_text(encoding="utf-8")), "artefactos": [junit]}


def suite_newman(tmp: Path, coleccion: str, base_url: str) -> dict:
    reporte = tmp / f"newman-{coleccion}.json"
    ruta = f"api/tests/postman/{coleccion}.postman_collection.json"
    # npx viene de nvm: hace falta una shell interactiva
    comando = (f"npx --yes newman run {ruta} --env-var baseUrl={base_url} --reporters cli,json "
               f"--reporter-json-export {reporte}")
    codigo, salida = _correr(["bash", "-ic", f"cd {RAIZ} && {comando}"], RAIZ)
    datos = leer_newman(json.loads(reporte.read_text(encoding="utf-8")))
    resumen = tmp / f"newman-{coleccion}-resumen.json"
    resumen.write_text(json.dumps(datos["resumen"], ensure_ascii=False, indent=1), encoding="utf-8")
    return {"suite": f"newman · {coleccion}", "entorno": base_url, "comando": comando, "codigo": codigo,
            "salida": salida, "metricas": datos["metricas"], "fallas": datos["fallas"], "artefactos": [resumen]}


def nota(r: dict, git: dict, historia: str | None) -> str:
    m = r["metricas"]
    if "verificaciones" in m:
        cifras = (f"{m['peticiones']} peticiones, {m['verificaciones']} verificaciones, "
                  f"{m['verificaciones_fallidas']} fallidas")
    else:
        cifras = f"{m['pruebas']} pruebas: {m['pasadas']} pasan, {m['fallidas']} fallan, {m['errores']} con error, {m['omitidas']} omitidas"
    lineas = [f"**{r['suite']}** · {cifras} · {m['duracion_s']} s · {r['entorno']}"
              + (f" · historia {historia}" if historia else ""),
              "", f"**Código:** `{git.get('commit', '?')[:7]}` en `{git.get('rama', '?')}`"
              + (" (con cambios sin commit)" if git.get("sucio") else ""),
              "", f"**Reproducir:** `{r['comando']}`"]
    if r["fallas"]:
        lineas += ["", f"**Fallas ({len(r['fallas'])}):**", *[f"- {f}" for f in r["fallas"][:30]]]
    return "\n".join(lineas)


def registrar(resultados: list[dict], uri: str, historia: str | None) -> list[str]:
    from mlflow import MlflowClient
    from mlflow.entities import Metric, Param, RunTag
    c = MlflowClient(uri)
    e = c.get_experiment_by_name(EXPERIMENTO)
    experimento = e.experiment_id if e else c.create_experiment(EXPERIMENTO, tags={"proyecto": "InventaIO"})
    c.set_experiment_tag(experimento, "mlflow.experimentKind", "custom_model_development")
    c.set_experiment_tag(experimento, "mlflow.note.content", DESCRIPCION)
    git = procedencia.git()
    ids = []
    for r in resultados:
        nombre = f"{r['suite']} · {datetime.fromtimestamp(r['inicio'] / 1000):%Y-%m-%d %H:%M}"
        run = c.create_run(experimento, start_time=r["inicio"], run_name=nombre)
        ok = r["codigo"] == 0 and not r["fallas"]
        tags = {"suite": r["suite"].split(" · ")[0], "coleccion": r["suite"].split(" · ")[1] if " · " in r["suite"] else "",
                "entorno": r["entorno"], "resultado": "pasa" if ok else "falla", "tipo": "pruebas",
                **procedencia.etiquetas(git), **({"historia": historia} if historia else {}),
                "mlflow.note.content": nota(r, git, historia)}
        c.log_batch(run.info.run_id, metrics=[Metric(k, float(v), r["inicio"], 0) for k, v in r["metricas"].items()],
                    params=[Param("comando", r["comando"][:500])], tags=[RunTag(k, v) for k, v in tags.items() if v])
        with tempfile.TemporaryDirectory() as tmp:
            salida = Path(tmp) / "salida.txt"
            salida.write_text(r["salida"], encoding="utf-8")
            for a in (*r["artefactos"], salida):
                c.log_artifact(run.info.run_id, str(a))
        c.set_terminated(run.info.run_id, status="FINISHED" if ok else "FAILED", end_time=r["fin"])
        print(f"{r['suite']}: {'pasa' if ok else 'FALLA'} → {run.info.run_id}")
        ids.append(run.info.run_id)
    return ids


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--suites", default="nlp_agent,api,newman")
    a.add_argument("--historia")
    a.add_argument("--api-contenedor", default="inventaio-api")
    a.add_argument("--base-url", default="http://localhost:8000", help="Core API de las colecciones newman")
    a.add_argument("--colecciones", default=",".join(COLECCIONES))
    a.add_argument("--tracking-uri", default=os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000"))
    args = a.parse_args(argv)
    if not args.tracking_uri.startswith(("http://127.0.0.1", "http://localhost", "sqlite:", "file:")):
        sys.exit("El registro es local (D22, N9): usa el servidor de scripts/mlflow_wsl.sh")
    suites = args.suites.split(",")
    resultados = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        tareas = []
        if "nlp_agent" in suites:
            tareas.append(lambda: suite_nlp_agent(tmp))
        if "api" in suites:
            tareas.append(lambda: suite_api(tmp, args.api_contenedor))
        if "newman" in suites:
            tareas += [lambda c=c: suite_newman(tmp, c, args.base_url) for c in args.colecciones.split(",")]
        for tarea in tareas:
            inicio = int(time.time() * 1000)
            r = tarea()
            resultados.append({**r, "inicio": inicio, "fin": int(time.time() * 1000)})
        registrar(resultados, args.tracking_uri, args.historia)
    return 0 if all(r["codigo"] == 0 and not r["fallas"] for r in resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
