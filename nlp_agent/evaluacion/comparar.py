"""
Compara una corrida con su línea base, pregunta por pregunta (INV-67, B13).

    cd nlp_agent
    python -m evaluacion.comparar --base resultados/2026-10-24_local-integracion-22oct-v1/qwen3_8b_gpu_real.jsonl \
        --nuevo resultados/<fecha>_nube-us-east-1/qwen.qwen3-32b-v1_0_nube_real.jsonl

El acierto y la herramienta se comparan con la diferencia pareada por pregunta
(el promedio de sus corridas, nuevo − base) y su intervalo del 95 % por
bootstrap pareado, como en `reporte.py`. Regla de B2 (la de INV-33): el nuevo
cumple si ninguno de los dos empeora con significancia (el intervalo no queda
entero por debajo de 0) y su p95 es ≤ 30 s.

INV-40: con `--equivalencias`, la herramienta y el acierto se califican con las equivalencias declaradas
(`evaluacion/equivalencias.py`) en los dos archivos.

INV-72: con `--mlflow`, la comparación queda en MLflow como un run de tipo `comparacion` en el experimento de la
corrida nueva. Lleva las métricas de las dos corridas, las diferencias con su intervalo y la regla, y queda ligada a
los runs de la base y de la nueva. Con equivalencias, la corrida nueva recibe también `acierto_equivalencias` y
`herramienta_equivalencias`, para verlas en su experimento. `--manifiesto` registra las comparaciones de
`comparaciones.json`, las que decidieron cada historia, con las equivalencias del commit que se usó entonces
(`equivalencias_de`). Es idempotente.

    python -m evaluacion.comparar --manifiesto evaluacion/comparaciones.json --mlflow
"""
import argparse
import hashlib
import json
import os
import sys
import tempfile
import types
from pathlib import Path

from evaluacion import equivalencias, procedencia, reporte, version_agente

CRITERIOS = ("acierto", "herramienta")
RAIZ = Path(__file__).resolve().parents[2]
MANIFIESTO = Path(__file__).resolve().parent / "comparaciones.json"
RUTA_EQUIVALENCIAS = "nlp_agent/evaluacion/equivalencias.py"


def comparar(base: dict, nuevo: dict) -> dict:
    rb, rn = reporte.resumen(base["corridas"]), reporte.resumen(nuevo["corridas"])
    difs = {k: reporte.diferencia_pareada(reporte.por_pregunta(nuevo["corridas"], k), reporte.por_pregunta(base["corridas"], k))
            for k in CRITERIOS}
    empeora = [k for k, d in difs.items() if d["ic95"][1] < 0]
    p95_ok = rn["p95_s"] <= reporte.METAS["p95_s"]
    return {"base": rb, "nuevo": rn, "diferencias": difs, "empeora": empeora, "p95_ok": p95_ok,
            "cumple": not empeora and p95_ok}


def _usd(x) -> str:
    return "—" if x is None else f"US${x:.5f}"


def markdown(base: dict, nuevo: dict, c: dict) -> str:
    mb, mn, rb, rn = base["meta"], nuevo["meta"], c["base"], c["nuevo"]
    filas = [
        "| | Base | Nuevo |", "| --- | --- | --- |",
        f"| Modelo | {mb['modelo']} ({mb['modo']}) | {mn['modelo']} ({mn['modo']}{', ' + mn['region'] if mn.get('region') else ''}) |",
        f"| Preguntas × corridas | {rb['preguntas']} × {mb['corridas']} | {rn['preguntas']} × {mn['corridas']} |",
        *(f"| {nombre} | {reporte._pct(rb[k])} | {reporte._pct(rn[k])} |"
          for nombre, k in (("Acierto", "acierto"), ("Herramienta", "herramienta"), ("Fidelidad", "fidelidad"))),
        f"| Fugas | {rb['fugas']} | {rn['fugas']} |",
        f"| Errores | {rb['errores']} | {rn['errores']} |",
        f"| p50 / p95 | {rb['p50_s']:.1f} / {rb['p95_s']:.1f} s | {rn['p50_s']:.1f} / {rn['p95_s']:.1f} s |",
        f"| Costo por pregunta | {_usd(rb['costo_pregunta_usd'])} | {_usd(rn['costo_pregunta_usd'])} |",
        f"| Costo total | {_usd(rb['costo_total_usd'])} | {_usd(rn['costo_total_usd'])} |",
        "", "**Diferencias pareadas** (nuevo − base, IC 95 % por bootstrap pareado):", "",
        "| Criterio | Preguntas | Diferencia | IC 95 % | ¿Empeora? |", "| --- | --- | --- | --- | --- |",
    ]
    for k, d in c["diferencias"].items():
        lo, hi = d["ic95"]
        filas.append(f"| {k} | {d['preguntas']} | {d['diferencia'] * 100:+.1f} pts | [{lo * 100:+.1f}, {hi * 100:+.1f}] | "
                     f"{'**sí**' if k in c['empeora'] else 'no'} |")
    motivos = [f"empeora {', '.join(c['empeora'])}"] if c["empeora"] else []
    motivos += [] if c["p95_ok"] else [f"p95 de {rn['p95_s']:.1f} s > {reporte.METAS['p95_s']:.0f} s"]
    filas += ["", f"**Regla de B2:** {'cumple' if c['cumple'] else 'no cumple (' + '; '.join(motivos) + ')'}."]
    return "\n".join(filas)


def equivalencias_de(commit: str | None) -> types.ModuleType:
    """Las equivalencias de hoy o las de un commit (las que se usaron al decidir una historia vieja)."""
    if not commit:
        return equivalencias
    fuente = version_agente._git("show", f"{commit}:{RUTA_EQUIVALENCIAS}")
    if fuente is None:
        sys.exit(f"No encuentro {RUTA_EQUIVALENCIAS} en el commit {commit}")
    modulo = types.ModuleType(f"equivalencias_{commit}")
    modulo.__file__ = f"{commit}:{RUTA_EQUIVALENCIAS}"
    exec(compile(fuente, modulo.__file__, "exec"), modulo.__dict__)          # noqa: S102 (código del propio repositorio)
    return modulo


def calcular(ruta_base: Path, ruta_nuevo: Path, con_equivalencias: bool = False,
             commit_equivalencias: str | None = None) -> tuple[dict, dict, dict]:
    base, nuevo = reporte.leer([ruta_base])[0], reporte.leer([ruta_nuevo])[0]
    if con_equivalencias:
        eq = equivalencias_de(commit_equivalencias)
        base, nuevo = eq.recalificar(base), eq.recalificar(nuevo)
    return base, nuevo, comparar(base, nuevo)


def metricas_mlflow(c: dict) -> dict[str, float]:
    """Las métricas del run de la comparación: las dos corridas, las diferencias y la regla."""
    m = {}
    for lado in ("base", "nuevo"):
        r = c[lado]
        m |= {f"{lado}_{k}": round(float(r[k]), 4) for k in ("acierto", "herramienta", "fidelidad", "p95_s")
              if r.get(k) is not None}
        m[f"{lado}_fugas"] = float(r["fugas"])
    for k, d in c["diferencias"].items():
        lo, hi = d["ic95"]
        m |= {f"dif_{k}": round(d["diferencia"], 4), f"ic95_inf_{k}": round(lo, 4), f"ic95_sup_{k}": round(hi, 4),
              f"empeora_{k}": float(k in c["empeora"])}
    m["preguntas_pareadas"] = float(c["diferencias"]["acierto"]["preguntas"])
    m["cumple"] = float(c["cumple"])
    return m


def _sha(ruta: Path) -> str:
    return hashlib.sha256(Path(ruta).read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def huella_comparacion(ruta_base: Path, ruta_nuevo: Path, con_equivalencias: bool, commit_equivalencias: str | None) -> str:
    fuente = "" if not con_equivalencias else (
        version_agente._git("show", f"{commit_equivalencias}:{RUTA_EQUIVALENCIAS}") if commit_equivalencias
        else Path(equivalencias.__file__).read_text(encoding="utf-8")) or ""
    partes = [_sha(ruta_base), _sha(ruta_nuevo), "eq" if con_equivalencias else "sin-eq", hashlib.sha256(fuente.encode()).hexdigest()]
    return hashlib.sha256("|".join(partes).encode()).hexdigest()[:16]


def _relativa(ruta: Path) -> str:
    try:
        return Path(ruta).resolve().relative_to(RAIZ).as_posix()
    except ValueError:
        return f"{Path(ruta).parent.name}/{Path(ruta).name}"


def registrar_mlflow(ruta_base: Path, ruta_nuevo: Path, uri: str, con_equivalencias: bool = False,
                     commit_equivalencias: str | None = None, historia: str | None = None, motivo: str | None = None) -> str:
    """La comparación como run de MLflow (idempotente por la huella de los dos archivos y las equivalencias)."""
    from mlflow.entities import Metric, RunTag

    from evaluacion import registro_mlflow as rm
    cliente = rm.ClienteMlflow(uri)
    id_base, id_nuevo = rm.registrar([ruta_base, ruta_nuevo], cliente)             # ya registrados: solo sus ids
    c = cliente._c
    run_nuevo = c.get_run(id_nuevo)
    experimento = run_nuevo.info.experiment_id
    huella = huella_comparacion(ruta_base, ruta_nuevo, con_equivalencias, commit_equivalencias)
    previos = c.search_runs([experimento], filter_string=f"tags.comparacion = '{huella}'", max_results=1)
    if previos:
        print(f"Ya estaba la comparación {_relativa(ruta_nuevo)} frente a {_relativa(ruta_base)} ({previos[0].info.run_id})")
        return previos[0].info.run_id
    base, nuevo, comp = calcular(ruta_base, ruta_nuevo, con_equivalencias, commit_equivalencias)
    con_eq = " · con equivalencias" if con_equivalencias else ""
    nombre = f"comparación · {Path(ruta_nuevo).parent.name} frente a {Path(ruta_base).parent.name}{con_eq}"
    cabecera = [f"**Comparación pareada{con_eq}** de `{_relativa(ruta_nuevo)}` (run `{id_nuevo}`) frente a la base "
                f"`{_relativa(ruta_base)}` (run `{id_base}`)" + (f" · historia {historia}" if historia else "") + ".", ""]
    if motivo:
        cabecera += [f"**Para qué:** {motivo}", ""]
    if con_equivalencias:
        cabecera += [f"**Equivalencias:** las de `{commit_equivalencias or 'el código de hoy'}` "
                     f"(`{RUTA_EQUIVALENCIAS}`).", ""]
    texto = markdown(base, nuevo, comp)
    tags = {"tipo": "comparacion", "comparacion": huella, "compara_base": id_base, "compara_nuevo": id_nuevo,
            "base_archivo": _relativa(ruta_base), "nuevo_archivo": _relativa(ruta_nuevo),
            "equivalencias": "sí" if con_equivalencias else "no", "cumple": "sí" if comp["cumple"] else "no",
            "conjunto": run_nuevo.data.tags.get("conjunto", ""), "datos": run_nuevo.data.tags.get("datos", ""),
            **({"equivalencias_de": commit_equivalencias} if con_equivalencias and commit_equivalencias else {}),
            **({"historia": historia} if historia else {}), **({"motivo": motivo} if motivo else {}),
            **procedencia.etiquetas(procedencia.git()), "mlflow.note.content": "\n".join(cabecera) + texto}
    inicio = max(c.get_run(id_base).info.start_time or 0, run_nuevo.info.start_time or 0) or None
    run = c.create_run(experimento, start_time=inicio, run_name=nombre)
    momento = inicio or run.info.start_time
    c.log_batch(run.info.run_id, metrics=[Metric(k, v, momento, 0) for k, v in metricas_mlflow(comp).items()],
                tags=[RunTag(k, v) for k, v in tags.items() if v])
    with tempfile.TemporaryDirectory() as tmp:
        md = Path(tmp) / "comparacion.md"
        md.write_text("\n".join(cabecera) + texto + "\n", encoding="utf-8")
        c.log_artifact(run.info.run_id, str(md))
    c.set_terminated(run.info.run_id, end_time=momento)
    if con_equivalencias:
        # La corrida nueva muestra en su experimento el acierto con el que se decidió
        rn = comp["nuevo"]
        cliente.completar(id_nuevo, {"acierto_equivalencias": round(rn["acierto"], 4),
                                     "herramienta_equivalencias": round(rn["herramienta"], 4)},
                          {"comparacion_equivalencias": run.info.run_id})
    print(f"Registrada: {nombre} → {run.info.run_id} ({'cumple' if comp['cumple'] else 'no cumple'})")
    return run.info.run_id


def manifiesto(ruta: Path = MANIFIESTO) -> list[dict]:
    """Las comparaciones de `comparaciones.json`, con las rutas resueltas desde la raíz del repositorio."""
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    salida = []
    for c in datos["comparaciones"]:
        salida.append({**c, "base": RAIZ / c["base"], "nuevo": RAIZ / c["nuevo"]})
    return salida


def main(argv=None) -> str | list[str]:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--base", type=Path)
    a.add_argument("--nuevo", type=Path)
    a.add_argument("--equivalencias", action="store_true",
                   help="INV-40: califica la herramienta con las equivalencias declaradas (evaluacion/equivalencias.py)")
    a.add_argument("--equivalencias-de", help="INV-72: las equivalencias de este commit en lugar de las de hoy")
    a.add_argument("--manifiesto", type=Path, nargs="?", const=MANIFIESTO,
                   help="INV-72: las comparaciones de comparaciones.json (con --mlflow, las registra todas)")
    a.add_argument("--mlflow", action="store_true", help="INV-72: registra la comparación en MLflow (local)")
    a.add_argument("--historia", help="con --mlflow: la historia que decidió la comparación")
    a.add_argument("--motivo", help="con --mlflow: para qué se comparó")
    a.add_argument("--tracking-uri", default=os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000"))
    args = a.parse_args(argv)
    if args.mlflow and not args.tracking_uri.startswith(("http://127.0.0.1", "http://localhost", "sqlite:", "file:")):
        sys.exit("El registro es local (D22, N9): usa el servidor de scripts/mlflow_wsl.sh")
    if args.manifiesto:
        faltan = [c for c in manifiesto(args.manifiesto) if not (c["base"].is_file() and c["nuevo"].is_file())]
        if faltan:
            sys.exit("Faltan archivos del manifiesto: " + ", ".join(_relativa(x) for c in faltan for x in (c["base"], c["nuevo"])
                                                                   if not x.is_file()))
        ids = []
        for c in manifiesto(args.manifiesto):
            if args.mlflow:
                ids.append(registrar_mlflow(c["base"], c["nuevo"], args.tracking_uri, c.get("equivalencias", False),
                                            c.get("equivalencias_de"), c.get("historia"), c.get("motivo")))
            else:
                _, _, comp = calcular(c["base"], c["nuevo"], c.get("equivalencias", False), c.get("equivalencias_de"))
                print(f"{c.get('historia', '')} · {_relativa(c['nuevo'])}: {'cumple' if comp['cumple'] else 'no cumple'}")
        return ids
    if not (args.base and args.nuevo):
        a.error("hacen falta --base y --nuevo, o --manifiesto")
    if args.mlflow:
        return registrar_mlflow(args.base, args.nuevo, args.tracking_uri, args.equivalencias, args.equivalencias_de,
                                args.historia, args.motivo)
    base, nuevo, comp = calcular(args.base, args.nuevo, args.equivalencias, args.equivalencias_de)
    texto = markdown(base, nuevo, comp)
    print(texto)
    return texto


if __name__ == "__main__":
    main()
