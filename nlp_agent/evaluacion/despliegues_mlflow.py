"""
Los despliegues a staging en MLflow (INV-72, trazabilidad del agente). Un run por cada despliegue de develop que
hizo GitHub Actions (el trabajo «Desplegar staging» del flujo Imágenes), con:

- el commit, el PR y la historia, sacados del mensaje del merge;
- el resultado y la duración del trabajo;
- el código del agente desplegado (`huella_codigo`), las mejoras que enciende el despliegue de ese commit y las
  versiones del experimento `agente-evolucion` que tienen ese código y esas mejoras.

Las pruebas de humo del chat (`humo_chat.py`) van al mismo experimento, ligadas al despliegue de su commit. Los
despliegues anteriores a ese trabajo se hacían a mano, sin registro en Actions, y no aparecen.

    cd nlp_agent
    python -m evaluacion.despliegues_mlflow           # los que falten; idempotente por el id del trabajo

Usa `gh` con la sesión del equipo y solo lee los metadatos de las corridas, no sus registros.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime

from evaluacion import version_agente

EXPERIMENTO = "inventaio-despliegues"
FLUJO = "images.yml"
TRABAJO = re.compile(r"(?i)^desplegar")
MEJORAS_K8S = re.compile(r"MEJORAS=(\S+)")
MEJORAS_COMPOSE = re.compile(r"MEJORAS:\s*\$\{MEJORAS:-([^}]*)\}")
DESCRIPCION = """**Despliegues (INV-72)**: un run por cada despliegue de develop a staging que hizo GitHub Actions, y las pruebas de humo del chat de cada uno.

- **Despliegue** (etiqueta `tipo` = `despliegue`): commit, PR e historia (del mensaje del merge), resultado y duración del trabajo, el código del agente desplegado (`huella_codigo`), las mejoras que enciende y las versiones de `agente-evolucion` con ese código (`versiones_agente`).
- **Prueba de humo del chat** (`tipo` = `humo-chat`): unas preguntas al chat desplegado, cada una en una conversación nueva, ligadas al despliegue de su commit (`despliegue_run`). Lo que responde, sin cifras en pesos, va en `turnos.json`.
- **Antes del despliegue automático** (24-nov-2026), los despliegues se hacían a mano y no tienen registro aquí.
- **Se arma con** `python -m evaluacion.despliegues_mlflow` y `python -m evaluacion.humo_chat` (desde `nlp_agent/`)."""


def _gh(*args: str):
    try:
        r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        sys.exit(f"No pude usar gh: {exc}")
    if r.returncode != 0:
        sys.exit(f"gh {' '.join(args[:3])}…: {r.stderr.strip()[:300]}")
    return json.loads(r.stdout or "null")


def _ms(iso: str | None) -> int | None:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000) if iso else None


def desde() -> str | None:
    """La fecha del commit que agregó el despliegue a staging al flujo de imágenes: antes no hay que buscar."""
    salida = version_agente._git("log", "-S", "desplegar-staging:", "--reverse", "--format=%cI", "--",
                                 f".github/workflows/{FLUJO}")
    return salida.splitlines()[0] if salida else None


def mejoras_en(commit: str) -> str:
    """Las mejoras que enciende el despliegue de ese commit (k8s; si no, el compose de producción)."""
    for ruta, patron in (("k8s/base/kustomization.yaml", MEJORAS_K8S), ("docker-compose.prod.yml", MEJORAS_COMPOSE)):
        texto = version_agente._git("show", f"{commit}:{ruta}") or ""
        if m := patron.search(texto):
            return m.group(1).strip() or "ninguna"
    return "ninguna"


def datos_commit(commit: str) -> dict:
    mensaje = version_agente._git("log", "-1", "--format=%B", commit) or ""
    return {"mensaje": mensaje.strip(), "prs": version_agente.prs_de(mensaje), "historias": version_agente.historias_de(mensaje),
            "huella_codigo": version_agente.huella_codigo(commit) or "", "mejoras": mejoras_en(commit),
            "version_app": (version_agente._git("show", f"{commit}:VERSION") or "").strip()}


def experimento(c) -> str:
    e = c.get_experiment_by_name(EXPERIMENTO)
    exp_id = e.experiment_id if e else c.create_experiment(EXPERIMENTO, tags={"proyecto": "InventaIO"})
    c.set_experiment_tag(exp_id, "mlflow.experimentKind", "custom_model_development")
    c.set_experiment_tag(exp_id, "mlflow.note.content", DESCRIPCION)
    return exp_id


def run_del_commit(c, exp_id: str, commit: str) -> str | None:
    """El despliegue más reciente de ese commit."""
    if not commit:
        return None
    runs = c.search_runs([exp_id], filter_string="tags.tipo = 'despliegue'", max_results=1000,
                         order_by=["attributes.start_time DESC"])
    return next((r.info.run_id for r in runs if r.data.tags.get("mlflow.source.git.commit", "").startswith(commit)
                 or commit.startswith(r.data.tags.get("mlflow.source.git.commit", "-"))), None)


def versiones_con(c, huella: str, mejoras: str) -> list[str]:
    from evaluacion.documentar_mlflow import EVOLUCION
    e = c.get_experiment_by_name(EVOLUCION)
    if e is None or not huella:
        return []
    runs = c.search_runs([e.experiment_id], filter_string=f"params.huella_codigo = '{huella}'", max_results=1000)
    return sorted(r.data.tags.get("version", "?") for r in runs if r.data.params.get("mejoras", "ninguna") == mejoras)


def nota(d: dict, trabajo: dict, corrida: dict, versiones: list[str]) -> str:
    asunto = d["mensaje"].splitlines()
    titulo = asunto[-1] if len(asunto) > 1 else (asunto[0] if asunto else "")
    return "\n".join([
        f"**Despliegue a staging** del commit `{corrida['headSha'][:7]}` · {trabajo.get('conclusion') or 'sin resultado'}"
        + (f" · PR {', '.join(f'#{n}' for n in d['prs'])}" if d["prs"] else "")
        + (f" · {', '.join(d['historias'])}" if d["historias"] else ""), "",
        f"- **Qué entró:** {titulo or 'sin mensaje'}",
        f"- **Versión de la aplicación:** {d['version_app'] or 'sin dato'}",
        f"- **Código del agente:** `{d['huella_codigo'] or 'sin dato'}`, con las mejoras «{d['mejoras']}»"
        + (f": versiones {', '.join(versiones)} de agente-evolucion." if versiones
           else ": ninguna versión medida tiene ese código y esas mejoras."),
        f"- **Trabajo de Actions:** [{trabajo.get('name')}]({trabajo.get('url')})",
    ])


def registrar(uri: str, limite: int = 200) -> list[str]:
    from mlflow import MlflowClient
    from mlflow.entities import Metric, RunTag
    c = MlflowClient(uri)
    exp_id = experimento(c)
    inicio = desde()
    corridas = _gh("run", "list", "--workflow", FLUJO, "--branch", "develop", "--event", "push", "--limit", str(limite),
                   "--json", "databaseId,headSha,createdAt,conclusion,url")
    hechos = []
    for corrida in sorted(corridas, key=lambda x: x["createdAt"]):
        if inicio and _ms(corrida["createdAt"]) < _ms(inicio):
            continue                       # el flujo aún no desplegaba
        trabajos = [t for t in _gh("run", "view", str(corrida["databaseId"]), "--json", "jobs")["jobs"]
                    if TRABAJO.match(t.get("name", ""))]
        for t in trabajos:
            if not t.get("completedAt") or t.get("conclusion") in (None, "", "skipped"):
                continue                   # en curso o saltado: se registra cuando termine
            id_trabajo = str(t.get("databaseId"))
            if c.search_runs([exp_id], filter_string=f"tags.gh_trabajo = '{id_trabajo}'", max_results=1):
                continue
            d = datos_commit(corrida["headSha"])
            versiones = versiones_con(c, d["huella_codigo"], d["mejoras"])
            ini, fin = _ms(t.get("startedAt")), _ms(t.get("completedAt"))
            nombre = (f"{corrida['createdAt'][:10]} · staging · {corrida['headSha'][:7]}"
                      + (f" · PR #{d['prs'][-1]}" if d["prs"] else "") + (f" · {d['historias'][-1]}" if d["historias"] else ""))
            run = c.create_run(exp_id, start_time=ini, run_name=nombre)
            exito = t.get("conclusion") == "success"
            tags = {"tipo": "despliegue", "ambiente": "staging", "gh_trabajo": id_trabajo, "gh_corrida": str(corrida["databaseId"]),
                    "gh_url": t.get("url", ""), "resultado": t.get("conclusion", ""), "mlflow.source.git.commit": corrida["headSha"],
                    "mlflow.source.git.branch": "develop", "prs": ", ".join(f"#{n}" for n in d["prs"]),
                    "historia": ", ".join(d["historias"]), "huella_codigo": d["huella_codigo"], "mejoras": d["mejoras"],
                    "version_app": d["version_app"], "versiones_agente": ", ".join(versiones),
                    "mlflow.note.content": nota(d, t, corrida, versiones)}
            metricas = {"exito": float(exito), **({"duracion_s": round((fin - ini) / 1000, 1)} if ini and fin else {})}
            c.log_batch(run.info.run_id, metrics=[Metric(k, v, ini or 0, 0) for k, v in metricas.items()],
                        tags=[RunTag(k, v) for k, v in tags.items() if v])
            c.set_terminated(run.info.run_id, status="FINISHED" if exito else "FAILED", end_time=fin)
            print(f"Registrado: {nombre} → {run.info.run_id}")
            hechos.append(run.info.run_id)
    return hechos


def main(argv=None) -> list[str]:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--limite", type=int, default=200, help="cuántas corridas del flujo revisar, de la más nueva hacia atrás")
    a.add_argument("--tracking-uri", default=os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000"))
    args = a.parse_args(argv)
    if not args.tracking_uri.startswith(("http://127.0.0.1", "http://localhost", "sqlite:", "file:")):
        sys.exit("El registro es local (D22, N9): usa el servidor de scripts/mlflow_wsl.sh")
    return registrar(args.tracking_uri, args.limite)


if __name__ == "__main__":
    main()
