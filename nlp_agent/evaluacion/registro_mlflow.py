"""
Registra en MLflow las corridas del arnés del agente (INV-31, trazabilidad del v0, el v1 y lo que siga).

    bash scripts/mlflow_wsl.sh iniciar                       # servidor local, solo en 127.0.0.1
    cd nlp_agent
    MLFLOW_TRACKING_URI=http://127.0.0.1:5000 python -m evaluacion.registro_mlflow \\
        evaluacion/resultados/2026-10-21_local/*.jsonl --historia INV-31
    python -m evaluacion.correr … --mlflow --historia INV-33      # registra al terminar la corrida

Un archivo de resultados (un modelo, un modo, un conjunto, un entorno) es un run:

- **Experimento:** uno por conjunto (`agente-conjunto-v0`, `agente-conjunto-v1`), para que solo se comparen
  corridas sobre las mismas preguntas.
- **Parámetros:** modelo y digest, Ollama, modo, razonamiento, contexto, corridas, entorno, datos
  (sintético, colab o Core API real), conjunto y huellas del conjunto, el catálogo y el prompt.
- **Métricas:** las de `reporte.resumen` (acierto, pass^3, herramienta, fidelidad, abstención, fugas, p50,
  p95, tokens) y el acierto por bloque (v1) y por tipo de pregunta.
- **Artefactos:** el archivo de resultados, su reporte en Markdown y una tabla por pregunta.
- **Prompt:** si el prompt actual tiene la huella del run, se registra en el registro de prompts de MLflow y
  se liga al run. Si no (corridas viejas con otro prompt), queda solo la huella.

Es idempotente: un archivo ya registrado (misma huella SHA-256) no se vuelve a subir. MLflow no va en la
imagen del agente ni en el CI (`requirements-evaluacion.txt`); las pruebas usan un cliente simulado.
"""
import argparse
import csv
import hashlib
import io
import json
import os
import sys
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Protocol

from evaluacion import reporte

EXPERIMENTO = "agente-conjunto-{version}"
PROMPTS = {
    "agente-prompt-spike": Path(__file__).resolve().parent / "prompt_spike.md",
    "agente-prompt-sistema": Path(__file__).resolve().parents[1] / "prompts" / "v1" / "sistema.md",
}
METRICAS = ("acierto", "pass3", "herramienta", "pass3_herramienta", "fidelidad", "abstencion", "fugas", "errores",
            "p50_s", "p95_s", "tokens_ronda_p95", "tokens_ronda_max")


class Cliente(Protocol):
    def experimento(self, nombre: str) -> str: ...
    def ya_registrado(self, experimento_id: str, huella: str) -> str | None: ...
    def crear_run(self, experimento_id: str, nombre: str, inicio_ms: int | None, params: dict, metricas: dict,
                  tags: dict) -> str: ...
    def subir(self, run_id: str, ruta: Path) -> None: ...
    def prompt(self, nombre: str, texto: str, run_id: str) -> str: ...
    def terminar(self, run_id: str) -> None: ...


def _huella(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _datos(conjunto: str) -> str:
    """«v1 (real, 49 preguntas)» → real; «v0 (colab, 43 preguntas)» → colab; si no, sintético."""
    return "real" if "(real" in conjunto else "colab" if "(colab" in conjunto else "sintetico"


def _ms(iso: str | None) -> int | None:
    try:
        return int(datetime.fromisoformat(iso).timestamp() * 1000) if iso else None
    except ValueError:
        return None


def _por_grupo(corridas: list[dict], clave) -> dict[str, float]:
    grupos = defaultdict(list)
    for c in corridas:
        if (g := clave(c)) is not None:
            grupos[g].append(bool(c["calificacion"]["acierto"]))
    return {g: round(sum(v) / len(v), 4) for g, v in sorted(grupos.items())}


def run_de_archivo(ruta: Path, historia: str | None = None) -> dict:
    """Lo que se registra de un archivo de resultados, sin tocar MLflow."""
    texto = ruta.read_text(encoding="utf-8")
    datos = reporte.leer([ruta])[0]
    meta, corridas = datos["meta"], datos["corridas"]
    version = meta.get("conjunto", "v0").split()[0]
    r = reporte.resumen(corridas)
    metricas = {k: float(r[k]) for k in METRICAS if r.get(k) is not None}
    bloques = {}
    if version != "v0":
        from evaluacion.conjunto import cargar
        bloque_de = {p.id: p.bloque for p in cargar(version=version).preguntas}
        bloques = _por_grupo(corridas, lambda c: bloque_de.get(c["id"]))
    metricas |= {f"acierto_bloque_{b}": v for b, v in bloques.items()}
    metricas |= {f"acierto_tipo_{t}": v for t, v in _por_grupo(corridas, lambda c: c.get("tipo")).items()}
    info = meta.get("modelo_info") or {}
    params = {
        "modelo": meta["modelo"], "digest": info.get("digest") or meta.get("digest"), "ollama": meta.get("ollama"),
        "modo": meta.get("modo"), "razonamiento": meta.get("razonamiento"), "num_ctx": meta.get("num_ctx"),
        "corridas": meta.get("corridas"), "entorno": meta.get("entorno"), "datos": _datos(meta.get("conjunto", "")),
        "conjunto": meta.get("conjunto"), "preguntas": r["preguntas"], "huella_conjunto": meta.get("huella_conjunto"),
        "huella_catalogo": meta.get("huella_catalogo"), "huella_prompt": meta.get("huella_prompt"),
        "equipo": meta.get("equipo"), "gpu": meta.get("gpu"), "commit": meta.get("commit"), "core_api": meta.get("core_api"),
    }
    params = {k: str(v) for k, v in params.items() if v is not None}
    tags = {"archivo_sha256": _huella(texto), "archivo": f"{ruta.parent.name}/{ruta.name}", "conjunto": version,
            "datos": params["datos"], **({"historia": historia} if historia else {})}
    nombre = f"{meta['modelo']} · {params['datos']} · {meta.get('entorno', '')} · {ruta.parent.name[:10]}"
    return {"version": version, "nombre": nombre, "inicio_ms": _ms(meta.get("inicio")), "params": params,
            "metricas": metricas, "tags": tags, "datos": datos, "huella_prompt": meta.get("huella_prompt")}


def _por_pregunta_csv(corridas: list[dict]) -> str:
    salida = io.StringIO()
    criterios = ["acierto", "herramienta", "fidelidad", "hechos", "prohibido", "aclaracion", "rechazo", "sin_error"]
    escritor = csv.writer(salida)
    escritor.writerow(["id", "corrida", "tipo", "herramientas", *criterios, "cifras_sin_respaldo", "ms_total"])
    for c in corridas:
        k = c["calificacion"]
        escritor.writerow([c["id"], c["corrida"], c.get("tipo"), " > ".join(x["herramienta"] for x in c["llamadas"]),
                           *[int(bool(k.get(x, True))) for x in criterios], " ".join(k.get("cifras_sin_respaldo", [])),
                           c.get("ms_total")])
    return salida.getvalue()


def _prompt_del_run(huella: str | None) -> tuple[str, str] | None:
    """El prompt actual cuya huella (12 caracteres, como la de correr) es la del run."""
    for nombre, ruta in PROMPTS.items():
        texto = ruta.read_text(encoding="utf-8")
        if huella and _huella(json.dumps(texto, ensure_ascii=False, sort_keys=True))[:12] == huella:
            return nombre, texto
    return None


def registrar(rutas: list[Path], cliente: Cliente, historia: str | None = None) -> list[str]:
    """Registra cada archivo como un run. Devuelve los ids, también los de los que ya estaban."""
    ids = []
    for ruta in rutas:
        run = run_de_archivo(Path(ruta), historia)
        experimento = cliente.experimento(EXPERIMENTO.format(version=run["version"]))
        if previo := cliente.ya_registrado(experimento, run["tags"]["archivo_sha256"]):
            print(f"Ya estaba: {ruta} ({previo})")
            ids.append(previo)
            continue
        run_id = cliente.crear_run(experimento, run["nombre"], run["inicio_ms"], run["params"], run["metricas"], run["tags"])
        with tempfile.TemporaryDirectory() as tmp:
            md = Path(tmp) / "reporte.md"
            md.write_text(reporte.markdown([run["datos"]]) + "\n", encoding="utf-8")
            tabla = Path(tmp) / "por_pregunta.csv"
            tabla.write_text(_por_pregunta_csv(run["datos"]["corridas"]), encoding="utf-8")
            for archivo in (Path(ruta), md, tabla):
                cliente.subir(run_id, archivo)
        if prompt := _prompt_del_run(run["huella_prompt"]):
            cliente.prompt(*prompt, run_id)
        cliente.terminar(run_id)
        print(f"Registrado: {ruta} → {run_id}")
        ids.append(run_id)
    return ids


class ClienteMlflow:
    """El cliente real, sobre MlflowClient y el registro de prompts de MLflow 3."""

    def __init__(self, tracking_uri: str):
        import mlflow
        from mlflow import MlflowClient
        mlflow.set_tracking_uri(tracking_uri)
        self._mlflow = mlflow
        self._c = MlflowClient(tracking_uri)

    def experimento(self, nombre):
        e = self._c.get_experiment_by_name(nombre)
        return e.experiment_id if e else self._c.create_experiment(nombre, tags={"proyecto": "InventaIO", "componente": "nlp_agent"})

    def ya_registrado(self, experimento_id, huella):
        runs = self._c.search_runs([experimento_id], filter_string=f"tags.archivo_sha256 = '{huella}'", max_results=1)
        return runs[0].info.run_id if runs else None

    def crear_run(self, experimento_id, nombre, inicio_ms, params, metricas, tags):
        from mlflow.entities import Metric, Param, RunTag
        run = self._c.create_run(experimento_id, start_time=inicio_ms, run_name=nombre)
        ahora = inicio_ms or int(datetime.now().timestamp() * 1000)
        self._c.log_batch(run.info.run_id, metrics=[Metric(k, v, ahora, 0) for k, v in metricas.items()],
                          params=[Param(k, v) for k, v in params.items()], tags=[RunTag(k, v) for k, v in tags.items()])
        return run.info.run_id

    def subir(self, run_id, ruta):
        self._c.log_artifact(run_id, str(ruta))

    def prompt(self, nombre, texto, run_id):
        actual = self._mlflow.genai.load_prompt(f"prompts:/{nombre}@latest", allow_missing=True)
        if actual is None or actual.template != texto:
            actual = self._mlflow.genai.register_prompt(nombre, texto, commit_message="Prompt usado por el arnés del agente")
        self._c.link_prompt_version_to_run(run_id, actual)
        self._c.set_tag(run_id, "prompt", f"{nombre}/{actual.version}")
        return f"{nombre}/{actual.version}"

    def terminar(self, run_id):
        self._c.set_terminated(run_id)


def main(argv=None) -> list[str]:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("archivos", nargs="+", help="archivos .jsonl de evaluacion/resultados/")
    a.add_argument("--historia", help="la HU que produjo las corridas (INV-30, INV-32, INV-31, INV-33…)")
    a.add_argument("--tracking-uri", default=os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000"))
    args = a.parse_args(argv)
    if not args.tracking_uri.startswith(("http://127.0.0.1", "http://localhost", "sqlite:", "file:")):
        sys.exit("El registro es local (D22, N9): usa el servidor de scripts/mlflow_wsl.sh")
    return registrar([Path(x) for x in args.archivos], ClienteMlflow(args.tracking_uri), args.historia)


if __name__ == "__main__":
    main()
