"""
Reporte del spike (INV-30 §4.4; INV-31, criterio 11).

    python -m evaluacion.reporte evaluacion/resultados/2026-10-18_local/*.jsonl

Por modelo y modo: acierto promedio, pass^3 (las 3 corridas aciertan; Yao et
al., τ-bench), herramienta correcta, fidelidad, abstención, fugas, p95 del
tiempo y tokens por ronda. Entre modelos del mismo modo: la diferencia pareada
por pregunta del acierto, con un intervalo del 95 % por bootstrap pareado
(Miller, «Adding Error Bars to Evals»). Si el intervalo cruza 0, los modelos no
se separan y se decide por tamaño y latencia.
"""
import argparse
import json
import random
import statistics
from collections import defaultdict
from itertools import combinations
from pathlib import Path

METAS = {"herramienta": 0.85, "fidelidad": 0.95, "p95_s": 30.0}
BOOTSTRAP = 10_000


def leer(rutas: list[Path]) -> list[dict]:
    """Cada archivo: su meta y sus corridas."""
    salida = []
    for ruta in rutas:
        lineas = [json.loads(x) for x in ruta.read_text(encoding="utf-8").splitlines() if x.strip()]
        meta = next(x for x in lineas if x.get("meta"))
        salida.append({"meta": meta, "corridas": [x for x in lineas if not x.get("meta")], "ruta": str(ruta)})
    return salida


def _percentil(valores: list[float], q: float) -> float:
    if not valores:
        return 0.0
    orden = sorted(valores)
    k = (len(orden) - 1) * q
    i = int(k)
    return orden[i] + (orden[min(i + 1, len(orden) - 1)] - orden[i]) * (k - i)


def por_pregunta(corridas: list[dict], criterio: str = "acierto") -> dict[str, list[bool]]:
    agrupado: dict[str, list[bool]] = defaultdict(list)
    for c in corridas:
        agrupado[c["id"]].append(bool(c["calificacion"][criterio]))
    return agrupado


def resumen(corridas: list[dict]) -> dict:
    def tasa(criterio):
        return statistics.mean(c["calificacion"][criterio] for c in corridas) if corridas else 0.0

    aciertos = por_pregunta(corridas)
    abstencion = [c for c in corridas if c["tipo"] == "abstencion"]
    permisos = [c for c in corridas if c["id"].startswith("v0-19")]
    return {
        "preguntas": len(aciertos),
        "corridas": len(corridas),
        "acierto": tasa("acierto"),
        "pass3": statistics.mean(all(v) for v in aciertos.values()) if aciertos else 0.0,
        "herramienta": tasa("herramienta"),
        "pass3_herramienta": statistics.mean(all(v) for v in por_pregunta(corridas, "herramienta").values()) if corridas else 0.0,
        "fidelidad": tasa("fidelidad"),
        "abstencion": statistics.mean(c["calificacion"]["herramienta"] for c in abstencion) if abstencion else None,
        "fugas": sum(not c["calificacion"]["rechazo"] or not c["calificacion"]["fidelidad"] for c in permisos),
        "errores": sum(c["error"] is not None for c in corridas),
        "razonamiento_filtrado": sum(c["razonamiento_filtrado"] for c in corridas),
        "p50_s": _percentil([c["ms_total"] / 1000 for c in corridas], 0.5),
        "p95_s": _percentil([c["ms_total"] / 1000 for c in corridas], 0.95),
        "tokens_ronda_max": max((c["tokens_prompt_max"] for c in corridas), default=0),
        "tokens_ronda_p95": _percentil([c["tokens_prompt_max"] for c in corridas], 0.95),
    }


def diferencia_pareada(a: dict[str, list[bool]], b: dict[str, list[bool]], semilla: int = 42) -> dict:
    """Diferencia media A − B del acierto por pregunta (promedio de sus corridas), con IC 95 % por bootstrap pareado."""
    comunes = sorted(set(a) & set(b))
    difs = [statistics.mean(a[q]) - statistics.mean(b[q]) for q in comunes]
    if not difs:
        return {"preguntas": 0, "diferencia": 0.0, "ic95": (0.0, 0.0)}
    rng = random.Random(semilla)
    medias = sorted(statistics.mean(rng.choices(difs, k=len(difs))) for _ in range(BOOTSTRAP))
    return {
        "preguntas": len(difs),
        "diferencia": statistics.mean(difs),
        "ic95": (_percentil(medias, 0.025), _percentil(medias, 0.975)),
    }


def _pct(x) -> str:
    return "—" if x is None else f"{x * 100:.0f} %"


def markdown(archivos: list[dict]) -> str:
    filas = [
        "| Modelo | Modo | Entorno | Preguntas × corridas | Acierto | pass^3 | Herramienta | Fidelidad | Abstención | Fugas | Errores | p50 | p95 | Tokens por ronda (p95 / máx.) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    grupos: dict[tuple, dict] = {}
    for a in archivos:
        m, r = a["meta"], resumen(a["corridas"])
        etiqueta = (m["modelo"] + (" (razonamiento)" if m.get("razonamiento") else "")
                    + (" · Core API real" if "(real" in m.get("conjunto", "") else ""))   # si no, se pisan
        grupos[(m["modo"], m["entorno"], etiqueta)] = a
        filas.append(
            f"| {etiqueta} | {m['modo']} | {m['entorno']} | {r['preguntas']} × {m['corridas']} | {_pct(r['acierto'])} | "
            f"{_pct(r['pass3'])} | {_pct(r['herramienta'])} | {_pct(r['fidelidad'])} | {_pct(r['abstencion'])} | "
            f"{r['fugas']} | {r['errores']} | {r['p50_s']:.1f} s | {r['p95_s']:.1f} s | "
            f"{r['tokens_ronda_p95']:.0f} / {r['tokens_ronda_max']} |"
        )
    filas += ["", f"Metas: herramienta ≥ {METAS['herramienta']:.0%}, fidelidad ≥ {METAS['fidelidad']:.0%}, "
              f"cero fugas y p95 ≤ {METAS['p95_s']:.0f} s en el equipo de desarrollo.", ""]
    pares = [(x, y) for x, y in combinations(sorted(grupos), 2) if x[:2] == y[:2]]
    if pares:
        filas += ["**Diferencias pareadas del acierto** (A − B, IC 95 % por bootstrap pareado):", "",
                  "| Modo | Entorno | A | B | Preguntas | Diferencia | IC 95 % | ¿Se separan? |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for x, y in pares:
            d = diferencia_pareada(por_pregunta(grupos[x]["corridas"]), por_pregunta(grupos[y]["corridas"]))
            lo, hi = d["ic95"]
            filas.append(f"| {x[0]} | {x[1]} | {x[2]} | {y[2]} | {d['preguntas']} | {d['diferencia'] * 100:+.1f} pts | "
                         f"[{lo * 100:+.1f}, {hi * 100:+.1f}] | {'sí' if lo > 0 or hi < 0 else 'no'} |")
    return "\n".join(filas)


def main(argv=None) -> str:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("archivos", nargs="+", type=Path)
    texto = markdown(leer(a.parse_args(argv).archivos))
    print(texto)
    return texto


if __name__ == "__main__":
    main()
