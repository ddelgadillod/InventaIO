"""
Rendimiento de un modelo (INV-30, criterio 3): carga en frío, latencia al primer
token, velocidad de lectura del prompt y de generación, y memoria, con GPU o sin
ella (W12: el mismo Ollama con num_gpu=0).

La lectura del prompt se calcula con los tokens que Ollama leyó de verdad: el
comienzo que ya tenía en caché (prompt_eval_cached_count) no cuenta.

Mide la ronda que el usuario ve en streaming: la respuesta final después de una
herramienta, con el prompt del spike, el catálogo y el resultado (5 preguntas
del conjunto). Con --razonamiento mide la latencia con razonamiento (W4).

    cd nlp_agent && python -m evaluacion.smoke --modelo qwen3:8b [--modo cpu] [--razonamiento]
    python scripts/smoke_llm.py --modelo qwen3:8b          # lo mismo desde la raíz
"""
import argparse
import json
import os
import statistics
import time
from datetime import datetime
from pathlib import Path

import httpx

from evaluacion.arnes import prompt_sistema
from evaluacion.conjunto import cargar, herramientas, resultado_para
from evaluacion.correr import RESULTADOS

PREGUNTAS = ["v0-01", "v0-02", "v0-08", "v0-11", "v0-13"]


def _argumentos(esperados: dict) -> dict:
    return {k: (v["contiene"] if isinstance(v, dict) else v) for k, v in esperados.items()}


def conversaciones(variante: str = "local") -> list[list[dict]]:
    """La conversación hasta el resultado de la herramienta esperada, lista para la respuesta final."""
    c = cargar(variante)
    salida = []
    for id_ in PREGUNTAS:
        p = c.por_id(id_)
        e = p.esperado[0]
        args = _argumentos(e.argumentos)
        resultado = resultado_para(p, e.herramienta, args, c.fecha_datos)
        salida.append([
            {"role": "system", "content": prompt_sistema(p, c.fecha_datos)},
            {"role": "user", "content": p.pregunta},
            {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": e.herramienta, "arguments": args}}]},
            {"role": "tool", "tool_name": e.herramienta, "content": json.dumps(resultado, ensure_ascii=False)},
        ])
    return salida


def medir(http: httpx.Client, modelo: str, mensajes: list[dict], catalogo: list[dict], opciones: dict, razonamiento: bool) -> dict:
    cuerpo = {"model": modelo, "messages": mensajes, "tools": catalogo, "stream": True, "think": razonamiento,
              "keep_alive": "30m", "options": {"temperature": 0, "seed": 42, "num_ctx": 8192, **opciones}}
    inicio = time.monotonic()
    primero = None
    final: dict = {}
    with http.stream("POST", "/api/chat", json=cuerpo, timeout=600) as r:
        r.raise_for_status()
        for linea in r.iter_lines():
            if not linea.strip():
                continue
            d = json.loads(linea)
            if primero is None and (d.get("message", {}).get("content") or d.get("message", {}).get("tool_calls")):
                primero = time.monotonic() - inicio
            if d.get("done"):
                final = d
    s = lambda clave: final.get(clave, 0) / 1e9  # noqa: E731
    # Ollama reutiliza el comienzo del prompt que ya leyó (sistema y catálogo): la
    # velocidad de lectura se calcula solo con los tokens que leyó de verdad
    leidos = final.get("prompt_eval_count", 0) - final.get("prompt_eval_cached_count", 0)
    return {
        "primer_token_s": round(primero if primero is not None else time.monotonic() - inicio, 2),
        "total_s": round(time.monotonic() - inicio, 2),
        "carga_s": round(s("load_duration"), 2),
        "tokens_prompt": final.get("prompt_eval_count", 0),
        "tokens_reutilizados": final.get("prompt_eval_cached_count", 0),
        "lectura_prompt_tok_s": round(leidos / s("prompt_eval_duration"), 1) if leidos > 50 and s("prompt_eval_duration") else None,
        "tokens_respuesta": final.get("eval_count", 0),
        "generacion_tok_s": round(final.get("eval_count", 0) / s("eval_duration"), 1) if s("eval_duration") else None,
    }


def correr(args, transport: httpx.BaseTransport | None = None) -> dict:
    http = httpx.Client(base_url=args.base_url.rstrip("/"), transport=transport)
    opciones = {"num_gpu": 0} if args.modo == "cpu" else {}
    catalogo = herramientas(args.variante)
    # Carga en frío: se descarga el modelo y la primera medición incluye la carga
    http.post("/api/generate", json={"model": args.modelo, "keep_alive": 0}, timeout=120)
    mediciones = [medir(http, args.modelo, m, catalogo, opciones, args.razonamiento) for m in conversaciones(args.variante)]
    ps = http.get("/api/ps", timeout=10).json().get("models", [])
    cargado = next((m for m in ps if m.get("name", "").startswith(args.modelo)), {})
    calientes = mediciones[1:]                       # sin la primera, que incluye la carga
    lecturas = [m["lectura_prompt_tok_s"] for m in mediciones if m["lectura_prompt_tok_s"]]

    def mediana(clave):
        valores = [m[clave] for m in calientes if m[clave] is not None]
        return round(statistics.median(valores), 2) if valores else None

    resumen = {
        "modelo": args.modelo, "modo": args.modo, "razonamiento": args.razonamiento,
        "ollama": http.get("/api/version", timeout=10).json().get("version"),
        "carga_en_frio_s": mediciones[0]["carga_s"],
        "primer_token_s": mediana("primer_token_s"), "total_s": mediana("total_s"),
        "lectura_prompt_tok_s": round(statistics.median(lecturas), 1) if lecturas else None,
        "generacion_tok_s": mediana("generacion_tok_s"),
        "tokens_prompt": mediana("tokens_prompt"),
        "memoria_gb": round(cargado.get("size", 0) / 1e9, 2), "vram_gb": round(cargado.get("size_vram", 0) / 1e9, 2),
        "mediciones": mediciones,
    }
    base = Path(args.salida) if args.salida else RESULTADOS
    nombre = f"smoke_{args.modelo.replace(':', '_')}_{args.modo}" + ("_razonamiento" if args.razonamiento else "") + ".json"
    destino = base / f"{datetime.now().strftime('%Y-%m-%d')}_{args.entorno}" / nombre
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(resumen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in resumen.items() if k != "mediciones"}, ensure_ascii=False, indent=2))
    print(f"Resultados: {destino}")
    return resumen


def main(argv=None, transport: httpx.BaseTransport | None = None) -> dict:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--modelo", required=True)
    a.add_argument("--modo", choices=["gpu", "cpu"], default="gpu")
    a.add_argument("--razonamiento", action="store_true")
    a.add_argument("--variante", choices=["local", "colab"], default="local")
    a.add_argument("--entorno", default="local")
    a.add_argument("--base-url", default=os.environ.get("LLM_BASE_URL", "http://localhost:11434"))
    a.add_argument("--salida")
    return correr(a.parse_args(argv), transport)


if __name__ == "__main__":
    main()
