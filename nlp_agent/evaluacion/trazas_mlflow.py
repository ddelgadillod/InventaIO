"""
Trazas en MLflow de cada pregunta de una corrida del arnés (INV-33, decisión M2 del 21-oct).

    cd nlp_agent
    python -m evaluacion.trazas_mlflow evaluacion/resultados/2026-10-21_local-decisiones/*.jsonl
    python -m evaluacion.correr … --mlflow --historia INV-33          # también las arma al registrar

Las trazas se arman después de la corrida, con lo que guardó el arnés; el agente no se instrumenta (eso sería
la fase 2, en el chat). Cada pregunta × corrida es una traza ligada al run de su archivo:

- **Raíz (AGENT):** la pregunta, el rol y la sucursal del usuario; la respuesta y su estado.
- **Rondas del modelo (LLM) y llamadas (TOOL):** en el orden en que ocurrieron, con los argumentos y el
  resultado que leyó el modelo. Con el Core API real, el guardado (sin pesos, `privacidad.py`); con resultados
  sintéticos, se recalcula con el ejecutor sintético si el conjunto y el catálogo son los de la corrida. Los
  tiempos de cada span son aproximados: el arnés guarda el total y el del modelo, no el de cada ronda.
- **Evaluaciones:** la calificación de cada criterio como feedback (fuente: el calificador) y lo esperado
  (herramientas y hechos) como expectativas, para filtrar en la vista de trazas.

Es idempotente: un archivo cuyas trazas ya están (etiqueta `archivo_sha256`) no se repite.
"""
import argparse
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

from evaluacion import registro_mlflow as rm
from evaluacion.arnes import EjecutorSintetico
from evaluacion.conjunto import cargar
from evaluacion.privacidad import sin_pesos

CRITERIOS = ("acierto", "herramienta", "fidelidad", "hechos", "prohibido", "aclaracion", "rechazo", "sin_error")
FUENTE = "evaluacion/calificacion.py"


def _huella(objeto) -> str:
    return hashlib.sha256(json.dumps(objeto, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]


def _variante_y_version(meta: dict) -> tuple[str, str]:
    texto = str(meta.get("conjunto", ""))
    return ("colab" if "colab" in texto else "local"), texto.split(" ")[0] or "v0"


def _ejecutor_sintetico(meta: dict):
    """El ejecutor sintético de la corrida, si el conjunto y el catálogo son los mismos; si no, None."""
    variante, version = _variante_y_version(meta)
    try:
        conjunto = cargar(variante, version)
    except FileNotFoundError:
        return None
    from evaluacion.conjunto import herramientas
    catalogo = herramientas(variante, version)
    if meta.get("huella_conjunto") != _huella(conjunto.model_dump()) or meta.get("huella_catalogo") != _huella(catalogo):
        return None
    por_id = {p.id: p for p in conjunto.preguntas}
    return lambda id_: EjecutorSintetico(por_id[id_], conjunto.fecha_datos, catalogo) if id_ in por_id else None


async def _resultados_sinteticos(ejecutor, llamadas: list[dict]) -> list:
    salida = []
    for ll in llamadas:
        p = ejecutor.preparar(ll["herramienta"], ll["argumentos"])
        if p.error is not None:
            salida.append({"error": str(p.error)})
        else:
            salida.append((await ejecutor.ejecutar(p)).para_modelo)
    return salida


def plan_de_traza(corrida: dict, resultados: list | None, inicio_ns: int) -> dict:
    """Los spans de una pregunta × corrida, con tiempos aproximados: cada ronda del modelo y sus llamadas."""
    ms_total = float(corrida.get("ms_total") or 0)
    ms_modelo = float(corrida.get("ms_modelo") or 0)
    rondas = max(int(corrida.get("rondas") or 1), 1)
    llamadas = corrida.get("llamadas") or []
    por_ronda = {r: [i for i, ll in enumerate(llamadas) if ll["ronda"] == r] for r in range(1, rondas + 1)}
    ms_ronda = ms_modelo / rondas
    ms_llamada = max(ms_total - ms_modelo, 0) / len(llamadas) if llamadas else 0
    spans, t = [], inicio_ns
    for r in range(1, rondas + 1):
        fin = t + int(ms_ronda * 1e6)
        spans.append({"nombre": f"modelo · ronda {r}", "tipo": "LLM", "inicio": t, "fin": fin,
                      "salida": {"llamadas": [llamadas[i]["herramienta"] for i in por_ronda[r]]} if por_ronda[r]
                      else {"texto": corrida.get("texto", "")}})
        t = fin
        for i in por_ronda[r]:
            fin = t + int(ms_llamada * 1e6)
            resultado = resultados[i] if resultados is not None and i < len(resultados) else None
            spans.append({"nombre": llamadas[i]["herramienta"], "tipo": "TOOL", "inicio": t, "fin": fin,
                          "entrada": llamadas[i]["argumentos"],
                          "salida": sin_pesos(resultado) if resultado is not None else None,
                          "sin_resultado": resultado is None})
            t = fin
    return {"inicio": inicio_ns, "fin": max(t, inicio_ns + int(ms_total * 1e6)), "spans": spans}


def armar(ruta: Path, run_id: str, uri: str, historia: str | None = None) -> int:
    """Las trazas del archivo, ligadas a `run_id`. Devuelve cuántas creó (0 si ya estaban)."""
    import mlflow
    from mlflow import MlflowClient
    from mlflow.entities import AssessmentSource

    mlflow.set_tracking_uri(uri)
    c = MlflowClient(uri)
    texto = ruta.read_text(encoding="utf-8")
    lineas = [json.loads(x) for x in texto.splitlines() if x.strip()]
    meta, corridas = lineas[0], lineas[1:]
    sha = rm._huella(texto)
    experimento = c.get_run(run_id).info.experiment_id
    if c.search_traces([experimento], filter_string=f"tags.archivo_sha256 = '{sha}'", max_results=1, flush=True):
        return 0
    real = bool(meta.get("core_api"))
    ejecutor_de = None if real else _ejecutor_sintetico(meta)
    variante, version = _variante_y_version(meta)
    try:
        preguntas = {p.id: p for p in cargar(variante, version).preguntas}
    except FileNotFoundError:
        preguntas = {}
    fuente = AssessmentSource(source_type="CODE", source_id=FUENTE)
    t = (rm._ms(meta.get("inicio")) or 0) * 1_000_000
    creadas, evaluaciones = 0, []
    for corrida in corridas:
        if real:
            resultados = corrida.get("resultados")
        elif ejecutor_de and (e := ejecutor_de(corrida["id"])):
            resultados = asyncio.run(_resultados_sinteticos(e, corrida.get("llamadas") or []))
        else:
            resultados = None
        plan = plan_de_traza(corrida, resultados, t)
        t = plan["fin"]
        p = preguntas.get(corrida["id"])
        etiquetas = {"archivo_sha256": sha, "archivo": f"{ruta.parent.name}/{ruta.name}", "pregunta": corrida["id"],
                     "corrida": str(corrida["corrida"]), "tipo_pregunta": str(corrida.get("tipo")),
                     "modelo": meta["modelo"], "datos": "real" if real else variante, "conjunto": version,
                     "acierto": str(bool(corrida["calificacion"].get("acierto"))).lower(),
                     **({"bloque": p.bloque} if p is not None and getattr(p, "bloque", None) else {}),
                     **({"historia": historia} if historia else {})}
        raiz = c.start_trace(f"{corrida['id']} · corrida {corrida['corrida']}", span_type="AGENT",
                             inputs={"pregunta": p.pregunta if p is not None else None, "rol": corrida.get("rol"),
                                     "sucursal_usuario": getattr(p, "sucursal_usuario", None),
                                     **({"turnos_previos": [t.model_dump() for t in p.turnos_previos]}
                                        if p is not None and p.turnos_previos else {})},
                             attributes={"rondas": corrida.get("rondas"), "tokens_prompt_max": corrida.get("tokens_prompt_max"),
                                         "tokens_respuesta": corrida.get("tokens_respuesta"), "ms_total": corrida.get("ms_total"),
                                         "tiempos": "aproximados por ronda (el arnés guarda totales)"},
                             tags=etiquetas, experiment_id=experimento, start_time_ns=plan["inicio"], run_id=run_id)
        for s in plan["spans"]:
            span = c.start_span(s["nombre"], trace_id=raiz.trace_id, parent_id=raiz.span_id, span_type=s["tipo"],
                                inputs=s.get("entrada"), start_time_ns=s["inicio"],
                                attributes={"resultado": "no disponible: el conjunto o el catálogo cambiaron"}
                                if s.get("sin_resultado") else None)
            c.end_span(raiz.trace_id, span.span_id, outputs=s.get("salida"), end_time_ns=s["fin"])
        c.end_trace(raiz.trace_id, outputs={"respuesta": corrida.get("texto", "")},
                    status="ERROR" if corrida.get("error") else "OK", end_time_ns=plan["fin"])
        evaluaciones.append((raiz.trace_id, corrida["calificacion"], p))
        creadas += 1
    # Las trazas se exportan en segundo plano: las evaluaciones van cuando ya están escritas
    mlflow.flush_trace_async_logging()
    for trace_id, k, p in evaluaciones:
        for criterio in CRITERIOS:
            if criterio in k:
                razon = (f"cifras sin respaldo: {', '.join(k.get('cifras_sin_respaldo') or [])}"
                         if criterio == "fidelidad" and k.get("cifras_sin_respaldo") else None)
                mlflow.log_feedback(trace_id=trace_id, name=criterio, value=bool(k[criterio]), source=fuente,
                                    rationale=razon)
        if p is not None:
            esperado = [{"herramienta": e.herramienta, "argumentos": e.argumentos} for e in p.esperado]
            mlflow.log_expectation(trace_id=trace_id, name="herramientas_esperadas", value=esperado)
            hechos = (p.hechos_reales if real else None) or p.hechos_clave
            if hechos:
                mlflow.log_expectation(trace_id=trace_id, name="hechos", value=list(hechos))
    return creadas


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("archivos", nargs="+")
    a.add_argument("--historia")
    a.add_argument("--tracking-uri", default=os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000"))
    args = a.parse_args(argv)
    if not args.tracking_uri.startswith(("http://127.0.0.1", "http://localhost", "sqlite:", "file:")):
        sys.exit("El registro es local (D22, N9): usa el servidor de scripts/mlflow_wsl.sh")
    total = 0
    cliente = rm.ClienteMlflow(args.tracking_uri)
    for ruta in map(Path, args.archivos):
        [run_id] = rm.registrar([ruta], cliente, args.historia)          # el run del archivo (ya registrado: su id)
        n = armar(ruta, run_id, args.tracking_uri, args.historia)
        print(f"{ruta}: {n} trazas" if n else f"{ruta}: las trazas ya estaban")
        total += n
    return total


if __name__ == "__main__":
    main()
