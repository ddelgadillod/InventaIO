"""
Registra en MLflow las corridas del arnés del agente (INV-31, trazabilidad del v0, el v1 y lo que siga).

    bash scripts/mlflow_wsl.sh iniciar                       # servidor local, solo en 127.0.0.1
    cd nlp_agent
    MLFLOW_TRACKING_URI=http://127.0.0.1:5000 python -m evaluacion.registro_mlflow \\
        evaluacion/resultados/2026-10-21_local/*.jsonl --historia INV-31
    python -m evaluacion.registro_mlflow evaluacion/resultados/*/*.jsonl --actualizar   # completa los ya registrados
    python -m evaluacion.correr … --mlflow --historia INV-33      # registra al terminar la corrida

Un archivo de resultados (un modelo, un modo, un conjunto, un entorno) es un run:

- **Experimento:** uno por conjunto (`agente-conjunto-v0`, `agente-conjunto-v1`, `agente-conjunto-holdout`), para que solo se comparen
  corridas sobre las mismas preguntas. Cada experimento lleva una descripción de cómo leerlo.
- **Parámetros:** modelo y digest, Ollama, modo, razonamiento, contexto, corridas, entorno, datos
  (sintético, colab o Core API real), conjunto y huellas del conjunto, el catálogo y el prompt.
- **Métricas:**
  - las de `reporte.resumen` (acierto, pass^3, herramienta, fidelidad, abstención, fugas, p50, p95, tokens);
  - la tasa de cada criterio de la calificación;
  - el acierto por bloque (v1) y por tipo de pregunta;
  - si cumple cada meta (`cumple_meta_*`);
  - la comparación con la línea base de su conjunto y tipo de datos: diferencias y la diferencia pareada del
    acierto con su intervalo del 95 % (`base_*`).
- **Descripción del run** (la nota de MLflow): las métricas frente a las metas, los bloques, la comparación
  con la línea base, las preguntas que fallan, las advertencias y cómo reproducirlo.
- **Dataset:** el conjunto, con su huella, como entrada del run.
- **Artefactos:** el archivo de resultados, su reporte, una tabla por pregunta y el detalle de las fallas.
- **Prompt:** si el prompt actual tiene la huella del run, se registra en el registro de prompts de MLflow y
  se liga al run. Si no (corridas viejas con otro prompt), queda solo la huella.

Es idempotente: un archivo ya registrado (misma huella SHA-256) no se vuelve a subir; con `--actualizar` se
completan sus métricas, etiquetas, descripción y artefactos. MLflow no va en la imagen del agente ni en el CI
(`requirements-evaluacion.txt`); las pruebas usan un cliente simulado.
"""
import argparse
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Protocol

from evaluacion import procedencia, reporte

RESULTADOS = Path(__file__).resolve().parent / "resultados"
EXPERIMENTO = "agente-conjunto-{version}"
TIPO_EXPERIMENTO = "custom_model_development"
PROMPTS = {
    "agente-prompt-spike": Path(__file__).resolve().parent / "prompt_spike.md",
    "agente-prompt-sistema": Path(__file__).resolve().parents[1] / "prompts" / "v1" / "sistema.md",
    # INV-33 (Z3, Z8): el v2 son varios archivos; se registra el prompt entero de cada perfil (agente.prompt.plantilla)
    "agente-prompt-v2": Path(__file__).resolve().parents[1] / "prompts" / "v2",
    "agente-prompt-v2-corto": Path(__file__).resolve().parents[1] / "prompts" / "v2" / "corto.md",
}


def texto_prompt(nombre: str) -> str:
    """El texto que se registra de cada prompt: su archivo o, en el v2, el prompt entero del perfil."""
    if nombre.startswith("agente-prompt-v2"):
        from agente.prompt import plantilla
        return plantilla("v2", "corto" if nombre.endswith("corto") else "completo")
    return PROMPTS[nombre].read_text(encoding="utf-8")
METRICAS = ("acierto", "pass3", "herramienta", "herramienta_ejecutada", "pass3_herramienta", "fidelidad", "abstencion",
            "fugas", "errores", "sin_datos_con_contenido", "p50_s", "p95_s", "tokens_ronda_p95", "tokens_ronda_max")
CRITERIOS = ("hechos", "prohibido", "aclaracion", "rechazo", "sin_error")
# La línea base de cada conjunto y tipo de datos: contra ella se compara cada run (mismas preguntas)
LINEAS_BASE = {
    ("v0", "sintetico"): "2026-10-17_local/qwen3_8b_gpu.jsonl",                        # spike de INV-30
    ("v0", "colab"): "2026-10-18_local-variante-colab/qwen3_8b_gpu.jsonl",             # la variante colab en el equipo
    ("v0", "real"): "2026-10-18_local/qwen3_8b_gpu_real_linea-base.jsonl",             # INV-32 antes de ajustar
    ("v1", "sintetico"): "2026-10-21_local/qwen3_8b_gpu.jsonl",                        # antes de INV-33
    ("v1", "real"): "2026-10-21_local/qwen3_8b_gpu_real.jsonl",
}
DESCRIPCION_EXPERIMENTO = {
    "v0": """**Conjunto v0 del spike (INV-30)**: 43 preguntas (20 base y 23 variantes del usuario), congelado el 17-oct-2026.

Es el conjunto de **desarrollo**: con él se eligió el modelo (INV-30) y se ajustaron las descripciones del catálogo (INV-32), así que ya no mide sin sesgo. El examen es el v1.

- **Datos** (parámetro `datos`): `sintetico` (resultados del spike), `colab` (sucursales y fecha ficticias, N9) y `real` (herramientas de INV-32 contra el Core API; en el v0 **no se califican hechos**, así que su acierto no se compara con el sintético).
- **Líneas base** (etiqueta `linea_base`): el spike del 17-oct (sintético), la variante colab en el equipo (18-oct) y la línea base de INV-32 (real). Las métricas `base_*` comparan cada run con la suya.
- **Metas:** herramienta ≥ 85 %, fidelidad ≥ 95 %, cero fugas y p95 ≤ 30 s.
- **Cómo compararlos:** vista «Model training», «Columns» para agregar métricas, y «Group by» por `datos` o `entorno`. Cada run trae su descripción, el reporte y el detalle de las fallas.
- **Documentos:** `docs/INV-30-nlp-agent-service.md`, `docs/INV-32-herramientas-agente.md` y `docs/PLN-conjunto-referencia.md`.""",
    "v1": """**Conjunto v1 (INV-31)**: 61 preguntas nuevas escritas por el usuario, congelado el 20-oct-2026. Es el **examen** del agente: no se ajusta nada mirando sus preguntas una por una.

- **Bloques** (métricas `acierto_bloque_*`): A una herramienta, B varios pasos, C glosario y capacidades que no tiene, D ambiguas, E abstención, F adversariales.
- **Preguntas activas:** las que tienen su herramienta. Las pendientes (brechas del catálogo, dentro de INV-33) se activan cuando cada herramienta llega.
- **Datos:** `sintetico` (resultados reales escalados, apto para Colab) y `real` (Core API, con los hechos reales al 31-dic-2025).
- **Líneas base** (etiqueta `linea_base`): las corridas de qwen3:8b del 21-oct, antes de INV-33. Las métricas `base_*` comparan cada run con la suya, con la diferencia pareada y su intervalo.
- **Metas:** herramienta ≥ 85 %, fidelidad ≥ 95 %, cero fugas y p95 ≤ 30 s.
- **Documentos:** `docs/PLN-conjunto-referencia.md` (diseño y resultados) y `docs/INV-31-requerimientos.md`.""",
    "holdout": """**Holdout de INV-33**: 15 preguntas nuevas escritas por el usuario y congeladas el 23-oct-2026, **antes de medir**. Mide si lo que mejoró el prompt v2 en el v1 generaliza a preguntas que ni el agente ni quien ajustó el prompt habían visto.

- **Reglas:** se corre con el prompt vigente y **solo se reporta**; no se ajusta nada mirando sus preguntas. Si después de verlo cambia el prompt, el holdout deja de ser limpio y se dice así.
- **Bloques** (métricas `acierto_bloque_*`): A 3, B 1, C 3, D 4, E 2, F 2. Una pregunta (h-06) trae turnos previos: mide el multi-turno.
- **Datos:** solo `real` (Core API, con los hechos al 31-dic-2025). No tiene línea base ni variante sintética.
- **Metas:** las del v1 (herramienta ≥ 85 %, fidelidad ≥ 95 %, cero fugas y p95 ≤ 30 s), con la cautela de 15 preguntas.
- **Documentos:** `docs/INV-33-requerimientos.md` y `nlp_agent/evaluacion/conjuntos/holdout/LEEME.md`.""",
    "holdout-2": """**Holdout-2 de INV-33**: 15 preguntas nuevas escritas por el usuario y congeladas el 23-oct-2026, **antes de medir**. Mide las mejoras del desempeño (§3f): el código de las palancas se congeló en `4e6bca4` antes de abrir la plantilla, y su activación se decidió solo con el v1 (preregistro).

- **Corridas** (etiqueta `entorno`): la línea base del 22-oct (prompt v2.1, sin las mejoras), el código nuevo sin palancas, el código nuevo con las palancas activadas y el prompt v1 sobre la línea base. Solo se reportan.
- **Bloques:** A 4, B 4, C 2, D 2, E 1, F 2. h2-07 trae turnos previos.
- **Datos:** solo `real`. Sin línea base fija: se comparan entre sí, con la diferencia pareada.
- **Documentos:** `nlp_agent/evaluacion/conjuntos/holdout-2/LEEME.md` y su `PREREGISTRO.md`.""",
}
NOMBRE_BLOQUE = {"A": "una herramienta", "B": "varios pasos", "C": "glosario y capacidades", "D": "ambiguas",
                 "E": "abstención", "F": "adversariales"}


class Cliente(Protocol):
    def experimento(self, nombre: str, descripcion: str | None = None) -> str: ...
    def ya_registrado(self, experimento_id: str, huella: str) -> str | None: ...
    def crear_run(self, experimento_id: str, nombre: str, inicio_ms: int | None, params: dict, metricas: dict,
                  tags: dict) -> str: ...
    def completar(self, run_id: str, metricas: dict, tags: dict) -> None: ...
    def dataset(self, run_id: str, nombre: str, huella: str, url: str) -> None: ...
    def subir(self, run_id: str, ruta: Path) -> None: ...
    def prompt(self, nombre: str, texto: str, run_id: str) -> str: ...
    def terminar(self, run_id: str, fin_ms: int | None) -> None: ...


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


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.0f} %"


def _url_repositorio(relativa: str) -> str:
    """La URL del archivo en GitHub (rama develop); solo es una referencia, no se descarga."""
    try:
        origen = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, timeout=5,
                                cwd=Path(__file__).parent).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        origen = ""
    base = origen.removesuffix(".git").replace("git@github.com:", "https://github.com/")
    return f"{base}/blob/develop/{relativa}" if base else relativa


def _advertencias(meta: dict, version: str, datos: str) -> list[str]:
    avisos = []
    if str(meta.get("ollama", "")).startswith("0.4."):
        avisos.append(f"Ollama {meta['ollama']} (no 0.40.5) y, en Colab el 18-oct, modelos qwen2.5: no se compara "
                      "modelo a modelo con las corridas de 0.40.5 (INV-30, §2.3).")
    if version == "v0" and datos == "real":
        avisos.append("Modo real del v0: los hechos no se califican (T17 de INV-32); el acierto no se compara con el sintético.")
    if not meta.get("huella_prompt"):
        avisos.append("La corrida no guardó la huella del prompt: no se puede ligar a una versión del registro de prompts.")
    return avisos


UMBRAL_SONDA = 40                    # las corridas viejas no dicen su tipo: con menos preguntas, una sonda


def tipo_de(meta: dict, preguntas: int) -> str:
    """completa | sonda | smoke | recalificacion (INV-33, M3). Solo las completas se comparan con la línea base."""
    return meta.get("tipo") or ("sonda" if preguntas < UMBRAL_SONDA else "completa")


def _comparacion(ruta: Path, version: str, datos: str, corridas: list[dict], r: dict) -> tuple[dict, dict, str | None]:
    """Métricas `base_*` frente a la línea base de su conjunto y tipo de datos."""
    relativa = LINEAS_BASE.get((version, datos))
    if not relativa or not (RESULTADOS / relativa).is_file():
        return {}, {}, None
    if (RESULTADOS / relativa).resolve() == ruta.resolve():
        return {}, {"linea_base": "sí"}, None
    base = reporte.leer([RESULTADOS / relativa])[0]
    rb = reporte.resumen(base["corridas"])
    d = reporte.diferencia_pareada(reporte.por_pregunta(corridas), reporte.por_pregunta(base["corridas"]))
    lo, hi = d["ic95"]
    metricas = {
        "base_dif_acierto": round(d["diferencia"], 4), "base_ic95_inf": round(lo, 4), "base_ic95_sup": round(hi, 4),
        "base_se_separa": float(lo > 0 or hi < 0), "base_preguntas_pareadas": float(d["preguntas"]),
        "base_delta_herramienta": round(r["herramienta"] - rb["herramienta"], 4),
        "base_delta_fidelidad": round(r["fidelidad"] - rb["fidelidad"], 4),
        "base_delta_p95_s": round(r["p95_s"] - rb["p95_s"], 3),
    }
    texto = (f"Frente a la línea base (`{relativa}`): acierto {d['diferencia'] * 100:+.1f} puntos, "
             f"IC 95 % [{lo * 100:+.1f}; {hi * 100:+.1f}] en {d['preguntas']} preguntas pareadas: "
             f"{'se separa' if lo > 0 or hi < 0 else 'no se separa'}. Herramienta "
             f"{metricas['base_delta_herramienta'] * 100:+.1f} puntos; p95 {metricas['base_delta_p95_s']:+.1f} s.")
    return metricas, {"comparado_con": relativa}, texto


def _fallas(corridas: list[dict], conjunto) -> tuple[list[tuple[str, list[str]]], str]:
    """Las preguntas que fallan en la primera corrida, con su detalle (para la nota y el artefacto)."""
    filas, md = [], ["# Preguntas que fallan (corrida 1)", ""]
    for c in corridas:
        if c["corrida"] != 1 or c["calificacion"]["acierto"]:
            continue
        k = c["calificacion"]
        criterios = [x for x in ("herramienta", "fidelidad", *CRITERIOS) if k.get(x) is False]
        filas.append((c["id"], criterios))
        p = conjunto.por_id(c["id"]) if conjunto else None
        llamadas = "; ".join(f"{x['herramienta']} {json.dumps(x['argumentos'], ensure_ascii=False)}"
                             for x in c["llamadas"] if x["ronda"] == 1) or "ninguna"
        md += [f"## {c['id']}" + (f" · bloque {p.bloque}" if p and p.bloque else "") + f" · falla: {', '.join(criterios)}", ""]
        if p:
            esperado = " o ".join(e.herramienta for e in p.esperado) or "ninguna (abstención)"
            md += [f"- **Pregunta:** {p.pregunta}", f"- **Esperado en la 1.ª ronda:** {esperado}"]
            if p.nota:
                md.append(f"- **Qué debe hacer:** {p.nota}")
        md += [f"- **Llamó en la 1.ª ronda:** {llamadas}"]
        if k.get("cifras_sin_respaldo"):
            md.append(f"- **Cifras sin respaldo:** {', '.join(k['cifras_sin_respaldo'])}")
        md += [f"- **Respuesta:** {(c.get('texto') or '').strip()[:600]}", ""]
    return filas, "\n".join(md) + "\n"


def run_de_archivo(ruta: Path, historia: str | None = None) -> dict:
    """Lo que se registra de un archivo de resultados, sin tocar MLflow."""
    ruta = Path(ruta)
    texto = ruta.read_text(encoding="utf-8")
    datos_archivo = reporte.leer([ruta])[0]
    meta, corridas = datos_archivo["meta"], datos_archivo["corridas"]
    version = meta.get("conjunto", "v0").split()[0]
    datos = _datos(meta.get("conjunto", ""))
    r = reporte.resumen(corridas)
    metricas = {k: round(float(r[k]), 4) for k in METRICAS if r.get(k) is not None}
    metricas |= {f"tasa_{k}": round(sum(bool(c["calificacion"].get(k, True)) for c in corridas) / len(corridas), 4)
                 for k in CRITERIOS if corridas}
    # INV-33 (Z11): con --verificar, la fidelidad del borrador (la del modelo) y cuánto se reintentó o se respaldó
    verificadas = [c["verificacion"] for c in corridas if c.get("verificacion")]
    if verificadas:
        metricas |= {"fidelidad_borrador": round(sum(v["borrador_fiel"] for v in verificadas) / len(verificadas), 4),
                     "tasa_reintento": round(sum(v["resultado"] == "reintento" for v in verificadas) / len(verificadas), 4),
                     "tasa_respaldo": round(sum(v["resultado"] == "respaldo" for v in verificadas) / len(verificadas), 4)}
    conjunto = None
    try:
        from evaluacion.conjunto import cargar
        conjunto = cargar("colab" if datos == "colab" else "local", version)
    except (FileNotFoundError, ValueError):
        pass
    bloques = {}
    if conjunto and version != "v0":
        bloque_de = {p.id: p.bloque for p in conjunto.preguntas}
        bloques = _por_grupo(corridas, lambda c: bloque_de.get(c["id"]))
    metricas |= {f"acierto_bloque_{b}": v for b, v in bloques.items()}
    metricas |= {f"acierto_tipo_{t}": v for t, v in _por_grupo(corridas, lambda c: c.get("tipo")).items()}
    metas = {"herramienta": r["herramienta"] >= reporte.METAS["herramienta"],
             # Z11: la meta de fidelidad se exige al borrador cuando la corrida verifica
             "fidelidad": metricas.get("fidelidad_borrador", r["fidelidad"]) >= reporte.METAS["fidelidad"],
             "fugas": r["fugas"] == 0, "p95": r["p95_s"] <= reporte.METAS["p95_s"]}
    metricas |= {f"cumple_meta_{k}": float(v) for k, v in metas.items()}
    tipo = tipo_de(meta, r["preguntas"])
    comparacion, tags_base, texto_base = (_comparacion(ruta, version, datos, corridas, r) if tipo == "completa"
                                          else ({}, {}, f"Es una {tipo}: no se compara con la línea base."))
    metricas |= comparacion

    info = meta.get("modelo_info") or {}
    params = {
        "modelo": meta["modelo"], "digest": info.get("digest") or meta.get("digest"), "ollama": meta.get("ollama"),
        "modo": meta.get("modo"), "razonamiento": meta.get("razonamiento"), "num_ctx": meta.get("num_ctx"),
        "corridas": meta.get("corridas"), "entorno": meta.get("entorno"), "datos": datos,
        "conjunto": meta.get("conjunto"), "preguntas": r["preguntas"], "huella_conjunto": meta.get("huella_conjunto"),
        "huella_catalogo": meta.get("huella_catalogo"), "huella_prompt": meta.get("huella_prompt"),
        "equipo": meta.get("equipo"), "gpu": meta.get("gpu"), "core_api": meta.get("core_api"),
        "commit": meta.get("commit") or (meta.get("git") or {}).get("commit"),
    }
    params = {k: str(v) for k, v in params.items() if v is not None}
    modelo_base = meta["modelo"].split(" (")[0]
    avisos = _advertencias(meta, version, datos)
    fallas, fallas_md = _fallas(corridas, conjunto)
    tags = {"archivo_sha256": _huella(texto), "archivo": f"{ruta.parent.name}/{ruta.name}", "conjunto": version,
            "datos": datos, "familia": modelo_base.split(":")[0], "tamano": info.get("parameter_size") or "",
            "ollama": str(meta.get("ollama", "")), "tipo": tipo, "verificar": "sí" if meta.get("verificar") else "no",
            "version_prompt": meta.get("version_prompt", "v1" if version != "v0" else ""), **procedencia.etiquetas(meta.get("git")),
            **tags_base, **({"historia": historia} if historia else {}),
            **({"advertencia": " ".join(avisos)} if avisos else {})}
    tags = {k: v for k, v in tags.items() if v != ""}

    # La nota del run: lo que se ve primero al abrirlo
    filas_meta = [("Acierto", _pct(r["acierto"]), "—", ""), ("pass^3", _pct(r["pass3"]), "—", ""),
                  ("Herramienta", _pct(r["herramienta"]), "≥ 85 %", metas["herramienta"]),
                  *([("Fidelidad del borrador", _pct(metricas["fidelidad_borrador"]), "≥ 95 %", metas["fidelidad"]),
                     ("Fidelidad final", _pct(r["fidelidad"]), "—", ""),
                     ("Reintentos / respaldos", f"{_pct(metricas['tasa_reintento'])} / {_pct(metricas['tasa_respaldo'])}", "—", "")]
                    if verificadas else [("Fidelidad", _pct(r["fidelidad"]), "≥ 95 %", metas["fidelidad"])]),
                  ("Abstención", _pct(r["abstencion"]), "—", ""),
                  ("Fugas", str(r["fugas"]), "0", metas["fugas"]),
                  ("p95", f"{r['p95_s']:.1f} s", "≤ 30 s", metas["p95"])]
    nota = [f"**{meta['modelo']}** · conjunto {version} ({r['preguntas']} preguntas × {meta.get('corridas', '?')} corridas) · "
            f"datos {datos} · {meta.get('entorno', '')}" + (f" · {meta['gpu']}" if meta.get("gpu") else "")
            + f" · Ollama {meta.get('ollama', '?')}" + (f" · historia {historia}" if historia else ""), "",
            "| Métrica | Valor | Meta | ¿Cumple? |", "| --- | --- | --- | --- |"]
    nota += [f"| {n} | {v} | {m} | {'' if c == '' else ('sí' if c else '**no**')} |" for n, v, m, c in filas_meta]
    if bloques:
        nota += ["", "**Por bloque:** " + " · ".join(f"{b} {NOMBRE_BLOQUE.get(b, '')} {_pct(v)}" for b, v in bloques.items())]
    if tags_base.get("linea_base"):
        nota += ["", f"**Es la línea base** del conjunto {version} con datos {datos}: los demás runs se comparan con este."]
    elif texto_base:
        nota += ["", f"**{texto_base}**"]
    if fallas:
        nota += ["", f"**Fallan {len(fallas)} preguntas** (corrida 1; detalle en `fallas.md`): "
                 + ", ".join(f"{i} ({'/'.join(c)})" for i, c in fallas)]
    if avisos:
        nota += ["", "**Advertencias:** " + " ".join(avisos)]
    modo = (" --core-api http://localhost:8000" if datos == "real" else " --variante colab" if datos == "colab" else "")
    nota += ["", f"**Reproducir:** `python -m evaluacion.correr --modelo {modelo_base} --conjunto {version}{modo} "
             f"--corridas {meta.get('corridas', 3)}` (desde `nlp_agent/`).",
             "**Documentos:** `docs/PLN-conjunto-referencia.md` · `docs/INV-31-requerimientos.md`."]
    tags["mlflow.note.content"] = "\n".join(nota)

    nombre = (f"{meta['modelo']} · {datos} · {meta.get('entorno', '')} · {ruta.parent.name[:10]}"
              + ("" if tipo == "completa" else f" · {tipo}"))
    inicio = _ms(meta.get("inicio"))
    # La duración del run es la de la corrida (la suma de las preguntas), no la de su registro
    fin = inicio + int(sum(c.get("ms_total", 0) for c in corridas)) if inicio else None
    relativa = f"nlp_agent/evaluacion/conjuntos/{version}/preguntas.json"
    return {"version": version, "nombre": nombre, "inicio_ms": inicio, "fin_ms": fin, "params": params,
            "metricas": metricas, "tags": tags, "datos": datos_archivo, "huella_prompt": meta.get("huella_prompt"),
            "fallas_md": fallas_md,
            "dataset": {"nombre": f"conjunto-{version}-{datos}", "huella": meta.get("huella_conjunto") or "sin-huella",
                        "url": _url_repositorio(relativa)}}


def _por_pregunta_csv(corridas: list[dict]) -> str:
    salida = io.StringIO()
    criterios = ["acierto", "herramienta", "fidelidad", *CRITERIOS]
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
    for nombre in PROMPTS:
        texto = texto_prompt(nombre)
        if huella and _huella(json.dumps(texto, ensure_ascii=False, sort_keys=True))[:12] == huella:
            return nombre, texto
    return None


def _subir_artefactos(cliente: Cliente, run_id: str, ruta: Path, run: dict) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        archivos = {"reporte.md": reporte.markdown([run["datos"]]) + "\n",
                    "por_pregunta.csv": _por_pregunta_csv(run["datos"]["corridas"]),
                    "fallas.md": run["fallas_md"]}
        for nombre, contenido in archivos.items():
            (Path(tmp) / nombre).write_text(contenido, encoding="utf-8")
        for archivo in (ruta, *(Path(tmp) / n for n in archivos)):
            cliente.subir(run_id, archivo)


def registrar(rutas: list[Path], cliente: Cliente, historia: str | None = None, actualizar: bool = False) -> list[str]:
    """Registra cada archivo como un run. Devuelve los ids, también los de los que ya estaban (con
    `actualizar`, a esos se les completan métricas, etiquetas, descripción, dataset y artefactos)."""
    ids = []
    for ruta in map(Path, rutas):
        run = run_de_archivo(ruta, historia)
        experimento = cliente.experimento(EXPERIMENTO.format(version=run["version"]),
                                          DESCRIPCION_EXPERIMENTO.get(run["version"]))
        previo = cliente.ya_registrado(experimento, run["tags"]["archivo_sha256"])
        if previo and not actualizar:
            print(f"Ya estaba: {ruta} ({previo})")
            ids.append(previo)
            continue
        if previo:
            run_id = previo
            tags = {k: v for k, v in run["tags"].items() if k != "historia" or historia}
            cliente.completar(run_id, run["metricas"], tags)
        else:
            run_id = cliente.crear_run(experimento, run["nombre"], run["inicio_ms"], run["params"], run["metricas"],
                                       run["tags"])
        cliente.dataset(run_id, run["dataset"]["nombre"], run["dataset"]["huella"], run["dataset"]["url"])
        _subir_artefactos(cliente, run_id, ruta, run)
        if prompt := _prompt_del_run(run["huella_prompt"]):
            cliente.prompt(*prompt, run_id)
        cliente.terminar(run_id, run["fin_ms"])
        print(f"{'Actualizado' if previo else 'Registrado'}: {ruta} → {run_id}")
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

    def experimento(self, nombre, descripcion=None):
        e = self._c.get_experiment_by_name(nombre)
        experimento_id = e.experiment_id if e else self._c.create_experiment(
            nombre, tags={"proyecto": "InventaIO", "componente": "nlp_agent"})
        etiquetas = e.tags if e else {}
        # Sin esta etiqueta, la interfaz de MLflow 3 abre el experimento en la vista de trazas (GenAI), que
        # está vacía: los runs del arnés están en la pestaña de runs
        if etiquetas.get("mlflow.experimentKind") != TIPO_EXPERIMENTO:
            self._c.set_experiment_tag(experimento_id, "mlflow.experimentKind", TIPO_EXPERIMENTO)
        if descripcion and etiquetas.get("mlflow.note.content") != descripcion:
            self._c.set_experiment_tag(experimento_id, "mlflow.note.content", descripcion)
        return experimento_id

    def ya_registrado(self, experimento_id, huella):
        runs = self._c.search_runs([experimento_id], filter_string=f"tags.archivo_sha256 = '{huella}'", max_results=1)
        return runs[0].info.run_id if runs else None

    def _lote(self, run_id, metricas, tags, params=None, momento=None):
        from mlflow.entities import Metric, Param, RunTag
        ahora = momento or int(datetime.now().timestamp() * 1000)
        self._c.log_batch(run_id, metrics=[Metric(k, v, ahora, 0) for k, v in metricas.items()],
                          params=[Param(k, v) for k, v in (params or {}).items()],
                          tags=[RunTag(k, v) for k, v in tags.items()])

    def crear_run(self, experimento_id, nombre, inicio_ms, params, metricas, tags):
        run = self._c.create_run(experimento_id, start_time=inicio_ms, run_name=nombre)
        self._lote(run.info.run_id, metricas, tags, params, inicio_ms)
        return run.info.run_id

    def completar(self, run_id, metricas, tags):
        # Con el momento actual: con el mismo paso y momento, MLflow mostraría el valor mayor, no el último
        self._lote(run_id, metricas, tags)

    def dataset(self, run_id, nombre, huella, url):
        from mlflow.data.http_dataset_source import HTTPDatasetSource
        from mlflow.data.meta_dataset import MetaDataset
        from mlflow.entities import DatasetInput, InputTag
        ya = {(d.dataset.name, d.dataset.digest) for d in (self._c.get_run(run_id).inputs.dataset_inputs or [])}
        if (nombre, huella) in ya:
            return
        entidad = MetaDataset(HTTPDatasetSource(url), name=nombre, digest=huella)._to_mlflow_entity()
        self._c.log_inputs(run_id, datasets=[DatasetInput(entidad, tags=[InputTag("mlflow.data.context", "evaluacion")])])

    def subir(self, run_id, ruta):
        self._c.log_artifact(run_id, str(ruta))

    def prompt(self, nombre, texto, run_id):
        actual = self._mlflow.genai.load_prompt(f"prompts:/{nombre}@latest", allow_missing=True)
        if actual is None or actual.template != texto:
            actual = self._mlflow.genai.register_prompt(nombre, texto, commit_message="Prompt usado por el arnés del agente")
        self._c.link_prompt_version_to_run(run_id, actual)
        self._c.set_tag(run_id, "prompt", f"{nombre}/{actual.version}")
        return f"{nombre}/{actual.version}"

    def terminar(self, run_id, fin_ms):
        self._c.set_terminated(run_id, end_time=fin_ms)


def main(argv=None) -> list[str]:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("archivos", nargs="+", help="archivos .jsonl de evaluacion/resultados/")
    a.add_argument("--historia", help="la HU que produjo las corridas (INV-30, INV-32, INV-31, INV-33…)")
    a.add_argument("--actualizar", action="store_true", help="completa los runs ya registrados con lo que falte")
    a.add_argument("--tracking-uri", default=os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000"))
    args = a.parse_args(argv)
    if not args.tracking_uri.startswith(("http://127.0.0.1", "http://localhost", "sqlite:", "file:")):
        sys.exit("El registro es local (D22, N9): usa el servidor de scripts/mlflow_wsl.sh")
    return registrar([Path(x) for x in args.archivos], ClienteMlflow(args.tracking_uri), args.historia, args.actualizar)


if __name__ == "__main__":
    main()
