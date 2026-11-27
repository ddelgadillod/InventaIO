"""
Prueba de humo del chat de Vera contra un despliegue (INV-72, trazabilidad en MLflow).

Hace unas preguntas, cada una en una conversación nueva, por el mismo camino que el navegador: inicio de sesión
en el Core API y `/api/chat/message` con eventos SSE. Guarda lo que respondió, las herramientas, la fidelidad y el
tiempo. El archivo va fuera del repositorio, porque las respuestas traen cifras del negocio. En MLflow queda un
run de tipo `humo-chat` en el experimento `inventaio-despliegues`, ligado al despliegue de su commit, sin cifras
en pesos.

    cd nlp_agent
    INVENTAIO_CLAVES_PRUEBA=~/.config/inventaio/claves-staging.json python -m evaluacion.humo_chat \\
        --url https://<staging> --salida ~/InventaIO/evidencias/humo-chat/<fecha>.json --mlflow --historia INV-72
    python -m evaluacion.humo_chat --registrar ~/InventaIO/evidencias/humo-chat/<fecha>.json   # uno ya guardado

Una pregunta pasa si el chat termina sin error, las herramientas responden y la fidelidad no falla. Lo que dice la
respuesta se revisa a mano.
"""
import argparse
import json
import os
import statistics
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from evaluacion.privacidad import sin_pesos

EXPERIMENTO = "inventaio-despliegues"
# Las del despliegue de INV-72: un periodo relativo y un histórico por año (rol, sucursal, pregunta)
PREGUNTAS = (
    ("gerente", None, "¿Cuánto vendimos el mes pasado?"),
    ("gerente", None, "Dame un reporte del historico de ventas de Arroz Diana * 500"),
)


def eventos(texto: str):
    """Los eventos de una respuesta SSE: (nombre, datos)."""
    for bloque in texto.split("\n\n"):
        nombre, datos = None, []
        for linea in bloque.splitlines():
            if linea.startswith("event:"):
                nombre = linea[6:].strip()
            elif linea.startswith("data:"):
                datos.append(linea[5:].strip())
        if nombre:
            yield nombre, json.loads("\n".join(datos)) if datos else None


def turno(pregunta: str, rol: str, sucursal: str | None, texto_sse: str) -> dict:
    """Lo que se guarda de una respuesta del chat."""
    respuesta, herramientas, datos, meta, final = "", [], [], {}, {}
    for nombre, d in eventos(texto_sse):
        if nombre == "meta":
            meta = {k: d.get(k) for k in ("modelo", "version_prompt")}
        elif nombre == "token":
            respuesta += d.get("texto", "")
        elif nombre == "tool" and d.get("estado") == "inicio":
            herramientas.append({"nombre": d.get("nombre"), "etiqueta": d.get("etiqueta")})
        elif nombre == "tool":
            herramientas.append({k: d.get(k) for k in ("nombre", "estado", "codigo", "ms")})
        elif nombre == "data":
            datos.append({"titulo": d.get("titulo"), "filas": len(d.get("filas") or [])})
        elif nombre in ("done", "error"):
            final = {"evento": nombre, **{k: d.get(k) for k in ("rondas", "fidelidad", "respaldo", "ms_total",
                                                                  "fechas_datos", "codigo", "mensaje")}}
    errores = [h for h in herramientas if h.get("estado") not in (None, "ok")]
    pasa = final.get("evento") == "done" and not errores and final.get("fidelidad") in (None, "ok")
    return {"pregunta": pregunta, "rol": rol, "sucursal": sucursal, "meta": meta, "respuesta": respuesta,
            "herramientas": herramientas, "datos": datos, "final": final, "pasa": pasa}


def correr(url: str, preguntas=PREGUNTAS, transport=None) -> dict:
    import httpx

    from evaluacion.correr import UsuariosPrueba, claves_prueba
    usuarios = UsuariosPrueba(url, claves_prueba(), transport=transport)
    http = httpx.Client(base_url=url, timeout=140, transport=transport)
    salud = http.get("/api/health").json()
    turnos = []
    for rol, sucursal, pregunta in preguntas:
        cabeceras = {"Authorization": usuarios.autorizacion(rol, sucursal), "Accept": "text/event-stream"}
        r = http.post("/api/chat/message", json={"mensajes": [{"rol": "usuario", "texto": pregunta}]}, headers=cabeceras)
        turnos.append(turno(pregunta, rol, sucursal, r.text) if r.status_code == 200 else
                      {"pregunta": pregunta, "rol": rol, "sucursal": sucursal, "final": {"evento": "http", "codigo": r.status_code},
                       "herramientas": [], "datos": [], "respuesta": "", "pasa": False})
    return {"meta": {"url": url, "commit": salud.get("commit"), "version": salud.get("version"),
                     "inicio": datetime.now(UTC).isoformat(timespec="seconds")}, "turnos": turnos}


def metricas(resultado: dict) -> dict[str, float]:
    t = resultado["turnos"]
    ms = [x["final"]["ms_total"] for x in t if x["final"].get("ms_total") is not None]
    return {"preguntas": float(len(t)), "pasan": float(sum(x["pasa"] for x in t)),
            "tasa_pasa": round(sum(x["pasa"] for x in t) / len(t), 4) if t else 0.0,
            "respaldos": float(sum(bool(x["final"].get("respaldo")) for x in t)),
            **({"ms_p50": float(statistics.median(ms)), "ms_max": float(max(ms))} if ms else {})}


def nota(resultado: dict, despliegue: str | None, historia: str | None) -> str:
    m, t = resultado["meta"], resultado["turnos"]
    lineas = [f"**Prueba de humo del chat** en `{m['url']}` · commit `{(m.get('commit') or '?')[:7]}` · versión "
              f"{m.get('version') or '?'}" + (f" · historia {historia}" if historia else "")
              + (f" · despliegue `{despliegue}`" if despliegue else ""), "",
              f"**Pasan {sum(x['pasa'] for x in t)} de {len(t)}** (terminan sin error, las herramientas responden y la "
              "fidelidad no falla). Lo que dice cada respuesta se revisa a mano en `turnos.json`.", "",
              "| Pregunta | Rol | Herramientas | Fidelidad | Tiempo | Pasa |", "| --- | --- | --- | --- | --- | --- |"]
    for x in t:
        nombres = " > ".join(h.get("etiqueta") or h["nombre"] for h in x["herramientas"] if "etiqueta" in h) or "ninguna"
        ms = x["final"].get("ms_total")
        lineas.append(f"| {x['pregunta']} | {x['rol']} | {nombres} | {x['final'].get('fidelidad') or '—'} | "
                      f"{f'{ms / 1000:.1f} s' if ms else '—'} | {'sí' if x['pasa'] else '**no**'} |")
    return "\n".join(lineas)


def registrar(ruta: Path, uri: str, historia: str | None = None) -> str:
    """El run de la prueba en MLflow (idempotente por el archivo), ligado al despliegue del mismo commit."""
    import hashlib

    from mlflow import MlflowClient
    from mlflow.entities import Metric, RunTag

    from evaluacion import despliegues_mlflow
    texto = Path(ruta).read_text(encoding="utf-8")
    resultado = json.loads(texto)
    huella = hashlib.sha256(texto.encode()).hexdigest()
    c = MlflowClient(uri)
    exp_id = despliegues_mlflow.experimento(c)
    previos = c.search_runs([exp_id], filter_string=f"tags.archivo_sha256 = '{huella}'", max_results=1)
    if previos:
        print(f"Ya estaba: {ruta} ({previos[0].info.run_id})")
        return previos[0].info.run_id
    commit = resultado["meta"].get("commit") or ""
    despliegue = despliegues_mlflow.run_del_commit(c, exp_id, commit)
    inicio = int(datetime.fromisoformat(resultado["meta"]["inicio"]).timestamp() * 1000)
    nombre = f"{resultado['meta']['inicio'][:10]} · humo del chat · {commit[:7] or 'sin commit'}"
    run = c.create_run(exp_id, start_time=inicio, run_name=nombre)
    tags = {"tipo": "humo-chat", "archivo_sha256": huella, "archivo": Path(ruta).name, "url": resultado["meta"]["url"],
            "mlflow.source.git.commit": commit, "version_app": resultado["meta"].get("version") or "",
            "despliegue_run": despliegue or "", "historia": historia or "",
            "mlflow.note.content": nota(resultado, despliegue, historia)}
    c.log_batch(run.info.run_id, metrics=[Metric(k, v, inicio, 0) for k, v in metricas(resultado).items()],
                tags=[RunTag(k, v) for k, v in tags.items() if v])
    with tempfile.TemporaryDirectory() as tmp:
        archivo = Path(tmp) / "turnos.json"
        archivo.write_text(json.dumps(sin_pesos(resultado), ensure_ascii=False, indent=1), encoding="utf-8")
        c.log_artifact(run.info.run_id, str(archivo))
    fin = inicio + int(sum(x["final"].get("ms_total") or 0 for x in resultado["turnos"]))
    c.set_terminated(run.info.run_id, status="FINISHED" if all(x["pasa"] for x in resultado["turnos"]) else "FAILED",
                     end_time=fin)
    print(f"Registrada: {nombre} → {run.info.run_id}" + (f" (despliegue {despliegue})" if despliegue else ""))
    return run.info.run_id


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--url", help="la dirección del despliegue (la del navegador)")
    a.add_argument("--salida", type=Path, help="el archivo de la prueba, fuera del repositorio")
    a.add_argument("--registrar", type=Path, help="registra en MLflow una prueba ya guardada")
    a.add_argument("--mlflow", action="store_true", help="con --url: la registra al terminar")
    a.add_argument("--historia", help="la historia que se desplegó")
    a.add_argument("--tracking-uri", default=os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000"))
    args = a.parse_args(argv)
    if (args.mlflow or args.registrar) and not args.tracking_uri.startswith(("http://127.0.0.1", "http://localhost",
                                                                              "sqlite:", "file:")):
        sys.exit("El registro es local (D22, N9): usa el servidor de scripts/mlflow_wsl.sh")
    if args.registrar:
        return registrar(args.registrar, args.tracking_uri, args.historia)
    if not (args.url and args.salida):
        a.error("hacen falta --url y --salida, o --registrar")
    resultado = correr(args.url.rstrip("/"))
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    args.salida.chmod(0o600)
    for x in resultado["turnos"]:
        print(f"{'pasa' if x['pasa'] else 'FALLA'} · {x['pregunta']} · {x['final']}")
    print(f"Resultados: {args.salida}")
    if args.mlflow:
        return registrar(args.salida, args.tracking_uri, args.historia)
    return resultado


if __name__ == "__main__":
    main()
