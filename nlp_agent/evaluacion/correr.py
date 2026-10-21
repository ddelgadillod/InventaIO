"""
Corre el examen del spike contra un modelo y guarda cada corrida (INV-30, criterio 8).

    cd nlp_agent
    python -m evaluacion.correr --modelo qwen3:8b                        # GPU, 3 corridas, las 43 preguntas
    python -m evaluacion.correr --modelo qwen3:8b --modo cpu --timeout 300
    python -m evaluacion.correr --modelo qwen3:8b --preguntas v0-01,v0-15 --corridas 1
    LLM_BASE_URL=http://… python -m evaluacion.correr --modelo … --variante colab --entorno colab
    INVENTAIO_CLAVE_PRUEBA=… python -m evaluacion.correr --modelo qwen3:8b --core-api http://localhost:8000
    python -m evaluacion.correr --modelo qwen3:8b --conjunto v1 [--incluir-pendientes]
    python -m evaluacion.correr --modelo qwen3:8b --conjunto v1 --mlflow --historia INV-33   # y lo registra

Con `--core-api` (INV-32, T17), las herramientas son las reales del catálogo v1
contra el Core API, con el usuario de prueba del rol de cada pregunta
(api/scripts/seed_usuarios.py; la clave va en INVENTAIO_CLAVE_PRUEBA), y el
prompt es el del agente. Sin él, las del spike con resultados sintéticos.

`--conjunto v1` (INV-31) usa el catálogo y el prompt del agente también con
resultados sintéticos, y califica los hechos con los datos reales cuando va
contra el Core API. Sus preguntas `pendiente` (herramientas que todavía no
existen) se saltan, salvo con `--incluir-pendientes`.

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
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx

from agente.bucle import EjecutorCoreAPI
from agente.prompt import PLANTILLA, prompt_sistema, quien
from core.config import Settings
from evaluacion.arnes import PROMPT_SPIKE, correr_pregunta
from evaluacion.conjunto import cargar, herramientas
from herramientas.catalogo import esquemas
from herramientas.contexto import Contexto
from herramientas.core_api import ClienteCoreAPI
from llm.cliente import ClienteOllama

RESULTADOS = Path(__file__).resolve().parent / "resultados"
# Los usuarios de prueba de api/scripts/seed_usuarios.py, por rol y sucursal
USUARIOS_PRUEBA = {
    ("gerente", None): "gerente@inventaio.co",
    ("admin_bodega", None): "bodega@inventaio.co",
    ("admin_sucursal", "PRINCIPAL"): "admin.principal@inventaio.co",
    ("admin_sucursal", "LA 21"): "admin.norte@inventaio.co",
    ("admin_sucursal", "GLORIETA"): "admin.sur@inventaio.co",
}


class UsuariosPrueba:
    """Inicia sesión en el Core API con el usuario del rol de cada pregunta. Cada pregunta
    pide un token nuevo: una corrida completa dura más que un token."""

    def __init__(self, core_api: str, clave: str, transport=None):
        self._http = httpx.Client(base_url=core_api, timeout=30, transport=transport)
        self._clave = clave

    def autorizacion(self, rol: str, sucursal: str | None) -> str:
        email = USUARIOS_PRUEBA[(rol, sucursal if rol == "admin_sucursal" else None)]
        r = self._http.post("/api/auth/login", json={"email": email, "password": self._clave})
        if r.status_code != 200:
            sys.exit(f"No se pudo iniciar sesión con {email}: {r.status_code}")
        return f"Bearer {r.json()['access_token']}"


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


def archivo_salida(entorno: str, modelo: str, modo: str, razonamiento: bool, base: Path = RESULTADOS,
                   real: bool = False) -> Path:
    nombre = (modelo.replace(":", "_").replace("/", "_") + f"_{modo}" + ("_razonamiento" if razonamiento else "")
              + ("_real" if real else ""))
    return base / f"{datetime.now().strftime('%Y-%m-%d')}_{entorno}" / f"{nombre}.jsonl"


async def correr(args, transport: httpx.MockTransport | None = None) -> Path:
    base = args.base_url.rstrip("/")
    http = httpx.Client(base_url=base, transport=transport)
    ajustes = Settings(OLLAMA_BASE_URL=base, LLM_MODELO=args.modelo, LLM_TIMEOUT_S=args.timeout,
                       LLM_RAZONAMIENTO=args.razonamiento, LLM_NUM_CTX=args.num_ctx)
    conjunto = cargar(args.variante, args.conjunto)
    real = bool(args.core_api)
    catalogo = esquemas() if real else herramientas(args.variante, args.conjunto)
    con_agente = real or args.conjunto != "v0"          # prompt del agente; el v0 sintético, el del spike
    if real:
        if args.variante != "local":
            sys.exit("--core-api usa los datos reales: solo con la variante local")
        clave = os.environ.get("INVENTAIO_CLAVE_PRUEBA")
        if not clave:
            sys.exit("Define INVENTAIO_CLAVE_PRUEBA con la clave de los usuarios de prueba (api/scripts/seed_usuarios.py)")
        usuarios = UsuariosPrueba(args.core_api, clave, transport=transport)
        core = ClienteCoreAPI(Settings(CORE_API_URL=args.core_api), transport=transport)
    preguntas = [p for p in conjunto.preguntas if args.incluir_pendientes or not p.pendiente]
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

    salida = archivo_salida(args.entorno, args.modelo, args.modo, args.razonamiento,
                            Path(args.salida) if args.salida else RESULTADOS, real=real)
    salida.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "meta": True,
        "modelo": args.modelo, "modelo_info": _modelo_info(http, args.modelo), "modo": args.modo,
        "razonamiento": args.razonamiento, "num_ctx": args.num_ctx, "corridas": args.corridas,
        "ollama": await cliente.version(), "entorno": args.entorno, "equipo": platform.node(), "gpu": _gpu(),
        "conjunto": f"{conjunto.version} ({'real' if real else args.variante}, {len(preguntas)} preguntas)",
        "huella_conjunto": _huella(conjunto.model_dump()), "huella_catalogo": _huella(catalogo),
        "huella_prompt": _huella(PLANTILLA if con_agente else PROMPT_SPIKE), "carga_s": carga_s, "memoria": memoria,
        **({"core_api": args.core_api} if real else {}),
        "inicio": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    with salida.open("w", encoding="utf-8") as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
        for n in range(1, args.corridas + 1):
            for p in preguntas:
                if real:
                    ctx = Contexto(core, usuarios.autorizacion(p.rol, p.sucursal_usuario), uuid.uuid4().hex)
                    c = await correr_pregunta(cliente, p, catalogo, conjunto.fecha_datos, corrida=n, opciones=opciones,
                                              ejecutor=EjecutorCoreAPI(ctx),
                                              prompt=prompt_sistema(quien(p.rol, p.sucursal_usuario)))
                else:
                    prompt = prompt_sistema(quien(p.rol, p.sucursal_usuario)) if con_agente else None
                    c = await correr_pregunta(cliente, p, catalogo, conjunto.fecha_datos, corrida=n, opciones=opciones,
                                              prompt=prompt)
                f.write(json.dumps(c.como_dict(), ensure_ascii=False) + "\n")
                f.flush()
                cal = c.calificacion
                print(f"[{n}/{args.corridas}] {p.id:7} {'OK ' if cal['acierto'] else '-- '}"
                      f"herr={'s' if cal['herramienta'] else 'n'} fid={'s' if cal['fidelidad'] else 'n'} "
                      f"{c.ms_total / 1000:6.1f}s {c.error or ''}", flush=True)
    await cliente.cerrar()
    if real:
        await core.cerrar()
    print(f"Resultados: {salida}")
    if args.mlflow:
        from evaluacion import registro_mlflow
        uri = os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000")
        registro_mlflow.registrar([salida], registro_mlflow.ClienteMlflow(uri), args.historia)
    return salida


def main(argv=None, transport: httpx.MockTransport | None = None) -> Path:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--modelo", required=True)
    a.add_argument("--modo", choices=["gpu", "cpu"], default="gpu")
    a.add_argument("--corridas", type=int, default=3)
    a.add_argument("--preguntas", help="ids separados por coma; por defecto todas")
    a.add_argument("--conjunto", choices=["v0", "v1"], default="v0", help="conjunto de referencia (v1: INV-31)")
    a.add_argument("--incluir-pendientes", action="store_true", help="v1: también las preguntas de herramientas que faltan")
    a.add_argument("--variante", choices=["local", "colab"], default="local")
    a.add_argument("--entorno", default="local", help="etiqueta de la carpeta de resultados (local, colab-l4…)")
    a.add_argument("--base-url", default=os.environ.get("LLM_BASE_URL", "http://localhost:11434"))
    a.add_argument("--timeout", type=float, default=120.0, help="segundos por llamada al modelo")
    a.add_argument("--num-ctx", type=int, default=8192)
    a.add_argument("--razonamiento", action="store_true", help="W4: solo para medir la latencia con razonamiento")
    a.add_argument("--salida", help="carpeta base de los resultados")
    a.add_argument("--core-api", help="INV-32: herramientas reales contra este Core API (p. ej. http://localhost:8000)")
    a.add_argument("--mlflow", action="store_true", help="INV-31: registra la corrida en MLflow (MLFLOW_TRACKING_URI, local)")
    a.add_argument("--historia", help="con --mlflow: la HU que produce la corrida (INV-33…)")
    return asyncio.run(correr(a.parse_args(argv), transport))


if __name__ == "__main__":
    main()
