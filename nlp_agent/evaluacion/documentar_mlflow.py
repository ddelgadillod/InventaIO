"""
Documenta en MLflow las secciones Prompts, Datasets y Agent versions de los experimentos del agente (INV-31).
Todo sale de datos reales: los archivos del repositorio, su historial en git, los conjuntos y los runs ya
registrados por `registro_mlflow`. Nada se escribe a mano.

    cd nlp_agent
    MLFLOW_TRACKING_URI=http://127.0.0.1:5000 python -m evaluacion.documentar_mlflow

- **Prompts:** a cada prompt del registro, su descripción, el archivo, sus commits en git, la huella y los
  alias `spike-v0` (el del spike) y `linea-base-v1` y `vigente` (el del agente).
- **Datasets** (evaluación): el v0 y el v1 como conjuntos de evaluación de MLflow: un registro por pregunta,
  con lo que entra (pregunta, rol, sucursal) y lo que se espera (herramientas, hechos, abstención,
  aclaración, rechazo), y etiquetas de bloque, tipo y pendiente.
- **Agent versions:** una versión del agente por cada combinación real de modelo, digest, prompt, catálogo y
  razonamiento que aparece en los runs. Cada run queda ligado a su versión, y sus métricas principales se
  registran en la versión con el dataset del run, para compararlas en la tabla de versiones.

Es idempotente: lo que ya está igual no se vuelve a escribir.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from evaluacion.conjunto import cargar, herramientas
from evaluacion.registro_mlflow import EXPERIMENTO, PROMPTS, texto_prompt

RAIZ = Path(__file__).resolve().parents[2]
DESCRIPCION_PROMPT = {
    "agente-prompt-spike": ("Prompt del spike de INV-30: el que usa el arnés en el modo sintético del conjunto v0 "
                            "(catálogo provisional y resultados sintéticos). La fecha de la foto va fija en el prompt."),
    "agente-prompt-sistema": ("Prompt de sistema del agente (INV-32, prompts/v1/sistema.md): el que usa el agente en el "
                              "chat, las corridas contra el Core API y todo el conjunto v1. La fecha la da cada herramienta "
                              "(fecha_dato). INV-33 lo reemplaza por prompts/v2/."),
    "agente-prompt-v2": ("Prompt v2 del agente (INV-33, prompts/v2/): parte común (cifras, filtros, glosario, total, fecha, "
                         "aclaración y respuestas fijas) y una parte por rol. Se registra entero, con las cuatro partes."),
    "agente-prompt-v2-corto": ("Perfil corto del prompt v2 (INV-33, Z8, prompts/v2/corto.md): la parte común condensada, "
                               "sin partes por rol, para el agente en CPU."),
}
ALIAS = {"agente-prompt-spike": ("spike-v0",), "agente-prompt-sistema": ("linea-base-v1",),
         # MLflow reserva los alias con forma de versión («v2»)
         "agente-prompt-v2": ("prompt-v2", "vigente"), "agente-prompt-v2-corto": ("prompt-v2-corto",)}
DESCRIPCION_CONJUNTO = {
    "v0": ("Conjunto v0 del spike (INV-30): 20 preguntas base y 23 variantes del usuario, congelado el 17-oct-2026. "
           "Conjunto de desarrollo: con él se eligió el modelo y se ajustó el catálogo (INV-32)."),
    "v1": ("Conjunto v1 (INV-31): 61 preguntas escritas por el usuario, congelado el 20-oct-2026. Examen del agente; "
           "las preguntas `pendiente` esperan su herramienta (brechas del catálogo, dentro de INV-33)."),
    "holdout": ("Holdout de INV-33: 15 preguntas nuevas escritas por el usuario, congelado el 23-oct-2026 antes de "
                "medir. Mide si las mejoras del prompt v2 generalizan: no se ajusta nada mirándolo. Solo datos reales."),
}
CONJUNTOS = ("v0", "v1", "holdout")
METRICAS_VERSION = ("acierto", "herramienta", "fidelidad", "abstencion", "fugas", "p95_s")


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, timeout=10, cwd=RAIZ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _huella(objeto) -> str:
    """La misma huella de 12 caracteres que guarda `correr` en cada corrida."""
    return hashlib.sha256(json.dumps(objeto, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]


def info_prompt(nombre: str) -> dict:
    relativa = PROMPTS[nombre].relative_to(RAIZ).as_posix()
    texto = texto_prompt(nombre)
    commits = _git("log", "--format=%h %ad %s", "--date=short", "--", relativa)
    return {"descripcion": DESCRIPCION_PROMPT[nombre], "archivo": relativa, "huella": _huella(texto),
            "caracteres": str(len(texto)), "commits": commits.replace("\n", " | ")}


def registros(version: str) -> list[dict]:
    """Un registro por pregunta, con los datos del conjunto tal como están en el repositorio."""
    salida = []
    for p in cargar("local", version).preguntas:
        esperado = {
            "herramientas_esperadas": sorted({e.herramienta for e in p.esperado}),
            "llamadas_esperadas": [e.model_dump(exclude_defaults=True) for e in p.esperado],
            "abstencion": p.abstencion, "abstencion_valida": p.abstencion_valida, "aclaracion": p.aclaracion,
            "rechazo": p.rechazo, "hechos_clave": p.hechos_clave, "hechos_alguno": p.hechos_alguno,
            "hechos_reales": p.hechos_reales, "hechos_alguno_reales": p.hechos_alguno_reales,
            "prohibido": p.prohibido, "nota": p.nota,
        }
        etiquetas = {"id": p.id, "tipo": p.tipo, "bloque": p.bloque, "variante_de": p.variante_de, "pendiente": p.pendiente}
        salida.append({
            "inputs": {"pregunta": p.pregunta, "rol": p.rol, "sucursal_usuario": p.sucursal_usuario or "todas",
                       **({"turnos_previos": [t.model_dump() for t in p.turnos_previos]} if p.turnos_previos else {})},
            "expectations": {k: v for k, v in esperado.items() if v not in (None, [], False) or k == "abstencion"},
            "tags": {k: str(v) for k, v in etiquetas.items() if v},
        })
    return salida


def etiquetas_conjunto(version: str) -> dict:
    c = cargar("local", version)
    pendientes = sum(1 for p in c.preguntas if p.pendiente)
    relativa = f"nlp_agent/evaluacion/conjuntos/{version}/preguntas.json"
    return {"descripcion": DESCRIPCION_CONJUNTO[version], "archivo": relativa, "huella": _huella(c.model_dump()),
            "preguntas": str(len(c.preguntas)), "activas": str(len(c.preguntas) - pendientes),
            "pendientes": str(pendientes), "fecha_datos": c.fecha_datos,
            "commits": _git("log", "--format=%h %ad", "--date=short", "-3", "--", relativa).replace("\n", " | ")}


def catalogos_conocidos() -> dict[str, str]:
    """Las huellas de los catálogos que existen hoy en el código, para nombrar los de cada run."""
    from herramientas.catalogo import esquemas
    actual = esquemas()
    # La huella corta va en el nombre: cuando el catálogo cambie, la versión anterior no se confunde con la nueva
    return {
        _huella(actual): f"catálogo del agente ({len(actual)} herramientas, {_huella(actual)[:8]})",
        _huella(herramientas("local", "v0")): "catálogo del spike (local)",
        _huella(herramientas("colab", "v0")): "catálogo del spike (variante colab)",
        _huella(herramientas("colab", "v1")): f"catálogo del agente, variante colab ({len(actual)} herramientas)",
    }


def _sin_cambios_desde(commit: str, *rutas: str) -> bool:
    return bool(commit) and all(subprocess.run(["git", "diff", "--quiet", commit, "HEAD", "--", r], cwd=RAIZ).returncode == 0
                                for r in rutas)


def huellas_por_commit(params: dict) -> dict:
    """Las corridas de Colab del 19-oct guardaron el commit pero no las huellas. Si el prompt y el catálogo del spike
    no cambiaron desde ese commit (git diff), sus huellas son las de hoy; si cambiaron, quedan sin huella."""
    commit = params.get("commit", "")
    if params.get("huella_prompt") or not commit or params.get("datos") not in ("sintetico", "colab"):
        return {}
    base = "nlp_agent/evaluacion/"
    if not _sin_cambios_desde(commit, base + "prompt_spike.md", base + "catalogo_v0.py"):
        return {}
    from evaluacion.arnes import PROMPT_SPIKE
    variante = "colab" if params["datos"] == "colab" else "local"
    return {"huella_prompt": _huella(PROMPT_SPIKE), "huella_catalogo": _huella(herramientas(variante, "v0")),
            "huellas_derivadas_de": commit}


def clave_de(v: dict) -> str:
    """La identidad de una versión: solo huellas y datos del modelo, nunca los nombres legibles (que cambian)."""
    partes = {k: v.get(k, "") for k in ("modelo", "digest", "huella_prompt", "huella_catalogo", "razonamiento")}
    if not partes["huella_prompt"]:
        partes["prompt"] = v.get("prompt", "")
    return hashlib.sha256(json.dumps(partes, sort_keys=True).encode()).hexdigest()[:16]


def clave_version(params: dict, tags: dict, catalogos: dict[str, str], prompts: dict[str, str] | None = None) -> dict:
    """La versión del agente de un run: lo que define su comportamiento (no el entorno ni Ollama)."""
    modelo = params["modelo"].split(" (")[0]
    params = {**params, **huellas_por_commit(params)}
    huella_prompt, huella_catalogo = params.get("huella_prompt"), params.get("huella_catalogo")
    # `prompts`: huella → «nombre/versión» del registro de prompts (para las corridas sin la etiqueta)
    prompt = (tags.get("prompt") or (prompts or {}).get(huella_prompt or "")
              or (f"prompt {huella_prompt}" if huella_prompt else "prompt sin huella"))
    catalogo = catalogos.get(huella_catalogo or "", f"catálogo {huella_catalogo}" if huella_catalogo else "catálogo sin huella")
    etiqueta = params["modelo"].split(" (", 1)[1].rstrip(")") if " (" in params["modelo"] else ""
    if etiqueta and huella_catalogo not in catalogos:
        catalogo += f" ({etiqueta})"            # el nombre que la corrida le dio, como «línea base» en INV-32
    partes = {"modelo": modelo, "digest": params.get("digest", ""), "prompt": prompt, "huella_prompt": huella_prompt or "",
              "catalogo": catalogo, "huella_catalogo": huella_catalogo or "", "razonamiento": params.get("razonamiento", "")}
    partes["clave"] = clave_de(partes)
    partes["huellas_derivadas_de"] = params.get("huellas_derivadas_de", "")           # no es parte de la versión
    partes["descripcion"] = f"agente · {modelo} · {prompt} · {catalogo}"
    # MLflow no admite / : . % ni comillas en el nombre de una versión
    partes["nombre"] = re.sub(r"[/:.%\"']", "-", partes["descripcion"])
    return partes


class Documentador:
    def __init__(self, tracking_uri: str):
        import mlflow
        from mlflow import MlflowClient
        mlflow.set_tracking_uri(tracking_uri)
        self.mlflow, self.c = mlflow, MlflowClient(tracking_uri)

    def prompts(self) -> list[str]:
        hechos = []
        for nombre in PROMPTS:
            version = self.mlflow.genai.load_prompt(f"prompts:/{nombre}@latest", allow_missing=True)
            if version is None:
                continue                    # aún no lo usa ningún run registrado
            info = info_prompt(nombre)
            for k, v in info.items():
                self.mlflow.genai.set_prompt_tag(nombre, k, v)
            self.mlflow.genai.set_prompt_version_tag(nombre, version.version, "huella", info["huella"])
            self.mlflow.genai.set_prompt_version_tag(nombre, version.version, "commit", info["commits"].split(" ")[0])
            for alias in ALIAS[nombre]:
                self.mlflow.genai.set_prompt_alias(nombre, alias, version.version)
            hechos.append(f"{nombre}/{version.version}")
        return hechos

    def datasets(self) -> list[str]:
        from mlflow.genai import datasets as ds
        hechos = []
        for version in CONJUNTOS:
            experimento = self.c.get_experiment_by_name(EXPERIMENTO.format(version=version))
            if experimento is None:
                continue
            etiquetas = etiquetas_conjunto(version)
            nombre = f"conjunto-{version}"
            existentes = ds.search_datasets(experiment_ids=[experimento.experiment_id], filter_string=f"name = '{nombre}'")
            dataset = existentes[0] if existentes else ds.create_dataset(name=nombre, experiment_id=experimento.experiment_id,
                                                                        tags=etiquetas)
            if existentes and dataset.tags.get("huella") == etiquetas["huella"]:
                hechos.append(f"{nombre} (sin cambios)")
                continue
            ds.set_dataset_tags(dataset.dataset_id, etiquetas)
            dataset.merge_records(registros(version))
            hechos.append(f"{nombre} ({etiquetas['preguntas']} registros)")
        return hechos

    def versiones(self) -> list[str]:
        from mlflow.entities import LoggedModelInput, Metric
        catalogos, hechos = catalogos_conocidos(), []
        prompts = {}
        for nombre in PROMPTS:
            ultima = self.mlflow.genai.load_prompt(f"prompts:/{nombre}@latest", allow_missing=True)
            if ultima is not None:
                prompts[_huella(ultima.template)] = f"{nombre}/{ultima.version}"
        for version in CONJUNTOS:
            experimento = self.c.get_experiment_by_name(EXPERIMENTO.format(version=version))
            if experimento is None:
                continue
            exp_id = experimento.experiment_id
            # Las versiones creadas con una clave anterior se actualizan a la de hoy (calculada de sus parámetros)
            for m in self.c.search_logged_models([exp_id], max_results=1000):
                if m.tags.get("clave") != (nueva := clave_de(m.params)):
                    self.c.set_logged_model_tags(m.model_id, {"clave": nueva})
            grupos: dict[str, tuple[dict, list]] = {}
            for run in self.c.search_runs([exp_id], max_results=1000):
                if "modelo" not in run.data.params:
                    continue                 # una recalificación (INV-33, M3) no corre el modelo: no es una versión
                v = clave_version(run.data.params, run.data.tags, catalogos, prompts)
                grupos.setdefault(v["clave"], (v, []))[1].append(run)
                if v["huellas_derivadas_de"] and run.data.tags.get("huellas_derivadas_de") != v["huellas_derivadas_de"]:
                    self.c.set_tag(run.info.run_id, "huellas_derivadas_de", v["huellas_derivadas_de"])
            for v, runs in grupos.values():
                existentes = self.c.search_logged_models([exp_id], filter_string=f"tags.clave = '{v['clave']}'")
                if existentes:
                    modelo = existentes[0]
                else:
                    params = {k: v[k] for k in ("modelo", "digest", "prompt", "huella_prompt", "catalogo", "huella_catalogo",
                                                "razonamiento") if v[k]}
                    modelo = self.c.create_logged_model(exp_id, name=v["nombre"][:250], params=params, model_type="agent",
                                                        tags={"clave": v["clave"]})
                    self.c.finalize_logged_model(modelo.model_id, "READY")
                ya_medidos = {m.run_id for m in (self.c.get_logged_model(modelo.model_id).metrics or [])}
                historias = sorted({r.data.tags["historia"] for r in runs if r.data.tags.get("historia")})
                nota = (f"Versión del agente: {v['modelo']} (digest {v['digest'] or 'sin dato'}), {v['prompt']}, "
                        f"{v['catalogo']}, razonamiento {v['razonamiento'] or 'sin dato'}. Medida en {len(runs)} runs del "
                        f"conjunto {version} ({', '.join(sorted({r.data.params.get('datos', '?') for r in runs}))}); "
                        f"historias: {', '.join(historias) or 'sin dato'}.")
                self.c.set_logged_model_tags(modelo.model_id, {"historias": ", ".join(historias), "runs": str(len(runs)),
                                                               "descripcion": v["descripcion"], "mlflow.note.content": nota})
                for r in runs:
                    r = self.c.get_run(r.info.run_id)            # la búsqueda no trae las versiones ligadas
                    ligados = {m.model_id for m in (r.inputs.model_inputs or [])}
                    if modelo.model_id not in ligados:
                        self.c.log_inputs(r.info.run_id, models=[LoggedModelInput(modelo.model_id)])
                    dataset = next(iter(r.inputs.dataset_inputs or []), None)
                    metricas = [Metric(k, r.data.metrics[k], r.info.start_time, 0, model_id=modelo.model_id,
                                       dataset_name=dataset.dataset.name if dataset else None,
                                       dataset_digest=dataset.dataset.digest if dataset else None, run_id=r.info.run_id)
                                for k in METRICAS_VERSION if k in r.data.metrics]
                    if metricas and r.info.run_id not in ya_medidos:
                        self.c.log_batch(r.info.run_id, metrics=metricas)
                hechos.append(f"{v['nombre']} ← {len(runs)} runs")
        return hechos


def main(argv=None) -> dict:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--tracking-uri", default=os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000"))
    args = a.parse_args(argv)
    if not args.tracking_uri.startswith(("http://127.0.0.1", "http://localhost", "sqlite:", "file:")):
        sys.exit("El registro es local (D22, N9): usa el servidor de scripts/mlflow_wsl.sh")
    d = Documentador(args.tracking_uri)
    salida = {"prompts": d.prompts(), "datasets": d.datasets(), "versiones": d.versiones()}
    for seccion, hechos in salida.items():
        print(f"{seccion}:", *[f"  {h}" for h in hechos], sep="\n")
    return salida


if __name__ == "__main__":
    main()
