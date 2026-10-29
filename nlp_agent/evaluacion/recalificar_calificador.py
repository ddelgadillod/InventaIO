"""
Recalifica las corridas guardadas con el calificador vigente y actualiza sus runs de MLflow (INV-33, decisión
del 23-oct: «se recalifican todas las corridas anteriores para que la comparación siga siendo justa»).

    cd nlp_agent
    python -m evaluacion.recalificar_calificador evaluacion/resultados/*/*.jsonl

Dos pasos, en este orden:

1. **Archivos.** Cada `.jsonl` se recalifica en su lugar (`calificacion.recalificar_archivo`): sin el modelo,
   con los resultados que se guardaron (reales) o los sintéticos del conjunto. Primero todos, porque la
   comparación de cada run con su línea base lee el archivo de la línea base.
2. **MLflow.** El run de cada archivo se busca por el sha256 que tenía antes de recalificar y se le
   **actualizan** las métricas y las etiquetas: `archivo_sha256` (el nuevo), `calificador` (la huella del
   calificador y el verificador) y `recalificado` (la fecha). MLflow guarda la historia de cada métrica, así
   que el valor anterior queda a la vista. No se crean runs nuevos. Las trazas conservan la evaluación con que
   se corrieron.
"""
import argparse
import hashlib
import os
import sys
from datetime import date
from pathlib import Path

from evaluacion import calificacion
from evaluacion import registro_mlflow as rm

RAIZ = Path(__file__).resolve().parents[1]
FUENTES_CALIFICADOR = ("evaluacion/calificacion.py", "agente/fidelidad.py", "evaluacion/conjunto.py")


def huella_calificador() -> str:
    """De qué código salen las calificaciones: el calificador, el verificador y las reglas del conjunto."""
    h = hashlib.sha256()
    for relativa in FUENTES_CALIFICADOR:
        h.update((RAIZ / relativa).read_bytes())
    return h.hexdigest()[:12]


def recalificar(rutas: list[Path], cliente: rm.Cliente | None = None) -> list[dict]:
    """Recalifica los archivos y, con `cliente`, actualiza sus runs. Devuelve, por archivo, lo que cambió."""
    rutas = [Path(r) for r in rutas]
    previos = {r: rm._huella(r.read_text(encoding="utf-8")) for r in rutas}
    informe = []
    for r in rutas:
        cambios = calificacion.recalificar_archivo(r)
        informe.append({"archivo": f"{r.parent.name}/{r.name}", "cambios": cambios, "run": None})
    if cliente is None:
        return informe
    huella, hoy = huella_calificador(), date.today().isoformat()
    for r, fila in zip(rutas, informe, strict=True):
        run = rm.run_de_archivo(r)
        experimento = cliente.experimento(rm.EXPERIMENTO.format(version=run["version"]),
                                          rm.DESCRIPCION_EXPERIMENTO.get(run["version"]))
        run_id = cliente.ya_registrado(experimento, previos[r]) or cliente.ya_registrado(experimento, run["tags"]["archivo_sha256"])
        if run_id is None:
            print(f"{fila['archivo']}: no estaba registrado en MLflow; solo se recalificó el archivo")
            continue
        etiquetas = {k: v for k, v in run["tags"].items() if k not in ("historia", "mlflow.runName")}
        cliente.completar(run_id, run["metricas"], {**etiquetas, "calificador": huella, "recalificado": hoy})
        rm._subir_artefactos(cliente, run_id, r, run)
        fila["run"] = run_id
        print(f"{fila['archivo']}: {fila['cambios']} calificaciones nuevas → run {run_id} actualizado")
    return informe


def main(argv=None) -> list[dict]:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("archivos", nargs="+")
    a.add_argument("--sin-mlflow", action="store_true", help="solo los archivos")
    a.add_argument("--tracking-uri", default=os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000"))
    args = a.parse_args(argv)
    if not args.sin_mlflow and not args.tracking_uri.startswith(("http://127.0.0.1", "http://localhost", "sqlite:", "file:")):
        sys.exit("El registro es local (D22, N9): usa el servidor de scripts/mlflow_wsl.sh")
    return recalificar([Path(x) for x in args.archivos], None if args.sin_mlflow else rm.ClienteMlflow(args.tracking_uri))


if __name__ == "__main__":
    main()
