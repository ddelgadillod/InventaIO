"""
Corre el examen del spike contra un modelo y guarda cada corrida (INV-30, criterio 8).

    cd nlp_agent
    python -m evaluacion.correr --modelo qwen3:8b                        # GPU, 3 corridas, las 43 preguntas
    python -m evaluacion.correr --modelo qwen3:8b --modo cpu --timeout 300
    python -m evaluacion.correr --modelo qwen3:8b --preguntas v0-01,v0-15 --corridas 1
    LLM_BASE_URL=http://… python -m evaluacion.correr --modelo … --variante colab --entorno colab

Escribe `resultados/<fecha>_<entorno>/<modelo>_<modo>.jsonl`: una primera línea
`meta` (versión de Ollama, digest del modelo, catálogo, conjunto, equipo) y una
línea por corrida. Sin Docker: solo httpx, pydantic y pydantic-settings.
"""
import argparse
import asyncio
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from core.config import Settings
from evaluacion.arnes import PROMPT_SPIKE, correr_pregunta
from evaluacion.conjunto import cargar, herramientas
from llm.cliente import ClienteOllama

RESULTADOS = Path(__file__).resolve().parent / "resultados"


def _huella(objeto) -> str:
    return hashlib.sha256(json.dumps(objeto, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]


def _gpu() -> str | None:
    try:
        salida = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                                capture_output=True, text=True, timeout=10)
        return salida.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _modelo_info(http: httpx.Client, modelo: str) -> dict:
    tags = http.get("/api/tags", timeout=10).json().get("models", [])
    nombre = modelo if ":" in modelo else f"{modelo}:latest"
    m = next((x for x in tags if x.get("name") == nombre), None)
    if m is None:
        sys.exit(f"El modelo {nombre} no está descargado en {http.base_url}")
    return {"digest": m["digest"][:12], "tamano_gb": round(m.get("size", 0) / 1e9, 2), **m.get("details", {})}


def archivo_salida(entorno: str, modelo: str, modo: str, razonamiento: bool, base: Path = RESULTADOS) -> Path:
    nombre = modelo.replace(":", "_").replace("/", "_") + f"_{modo}" + ("_razonamiento" if razonamiento else "")
    return base / f"{datetime.now().strftime('%Y-%m-%d')}_{entorno}" / f"{nombre}.jsonl"


async def correr(args, transport: httpx.MockTransport | None = None) -> Path:
    base = args.base_url.rstrip("/")
    http = httpx.Client(base_url=base, transport=transport)
    ajustes = Settings(OLLAMA_BASE_URL=base, LLM_MODELO=args.modelo, LLM_TIMEOUT_S=args.timeout,
                       LLM_RAZONAMIENTO=args.razonamiento, LLM_NUM_CTX=args.num_ctx)
    conjunto = cargar(args.variante)
    catalogo = herramientas(args.variante)
    preguntas = conjunto.preguntas
    if args.preguntas:
        ids = set(args.preguntas.split(","))
        preguntas = [p for p in preguntas if p.id in ids]
    opciones = {"num_gpu": 0} if args.modo == "cpu" else None
    cliente = ClienteOllama(ajustes, transport=transport)

    # Calentamiento: carga el modelo (en el modo pedido) antes de medir; su tiempo queda en meta
    inicio = time.monotonic()
    await cliente.chat([{"role": "user", "content": "Responde solo: listo"}], opciones=opciones)
    carga_s = round(time.monotonic() - inicio, 1)
    ps = http.get("/api/ps", timeout=10).json().get("models", [])
    memoria = next(({"total_gb": round(m["size"] / 1e9, 2), "vram_gb": round(m.get("size_vram", 0) / 1e9, 2)}
                    for m in ps if m.get("name", "").startswith(args.modelo)), {})

    salida = archivo_salida(args.entorno, args.modelo, args.modo, args.razonamiento, Path(args.salida) if args.salida else RESULTADOS)
    salida.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "meta": True,
        "modelo": args.modelo, "modelo_info": _modelo_info(http, args.modelo), "modo": args.modo,
        "razonamiento": args.razonamiento, "num_ctx": args.num_ctx, "corridas": args.corridas,
        "ollama": await cliente.version(), "entorno": args.entorno, "equipo": platform.node(), "gpu": _gpu(),
        "conjunto": f"{conjunto.version} ({args.variante}, {len(preguntas)} preguntas)",
        "huella_conjunto": _huella(conjunto.model_dump()), "huella_catalogo": _huella(catalogo),
        "huella_prompt": _huella(PROMPT_SPIKE), "carga_s": carga_s, "memoria": memoria,
        "inicio": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    with salida.open("w", encoding="utf-8") as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
        for n in range(1, args.corridas + 1):
            for p in preguntas:
                c = await correr_pregunta(cliente, p, catalogo, conjunto.fecha_datos, corrida=n, opciones=opciones)
                f.write(json.dumps(c.como_dict(), ensure_ascii=False) + "\n")
                f.flush()
                cal = c.calificacion
                print(f"[{n}/{args.corridas}] {p.id:7} {'OK ' if cal['acierto'] else '-- '}"
                      f"herr={'s' if cal['herramienta'] else 'n'} fid={'s' if cal['fidelidad'] else 'n'} "
                      f"{c.ms_total / 1000:6.1f}s {c.error or ''}", flush=True)
    await cliente.cerrar()
    print(f"Resultados: {salida}")
    return salida


def main(argv=None, transport: httpx.MockTransport | None = None) -> Path:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--modelo", required=True)
    a.add_argument("--modo", choices=["gpu", "cpu"], default="gpu")
    a.add_argument("--corridas", type=int, default=3)
    a.add_argument("--preguntas", help="ids separados por coma; por defecto todas")
    a.add_argument("--variante", choices=["local", "colab"], default="local")
    a.add_argument("--entorno", default="local", help="etiqueta de la carpeta de resultados (local, colab-l4…)")
    a.add_argument("--base-url", default=os.environ.get("LLM_BASE_URL", "http://localhost:11434"))
    a.add_argument("--timeout", type=float, default=120.0, help="segundos por llamada al modelo")
    a.add_argument("--num-ctx", type=int, default=8192)
    a.add_argument("--razonamiento", action="store_true", help="W4: solo para medir la latencia con razonamiento")
    a.add_argument("--salida", help="carpeta base de los resultados")
    return asyncio.run(correr(a.parse_args(argv), transport))


if __name__ == "__main__":
    main()
