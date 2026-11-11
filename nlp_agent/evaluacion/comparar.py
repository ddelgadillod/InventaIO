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
"""
import argparse
from pathlib import Path

from evaluacion import reporte

CRITERIOS = ("acierto", "herramienta")


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


def main(argv=None) -> str:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--base", type=Path, required=True)
    a.add_argument("--nuevo", type=Path, required=True)
    args = a.parse_args(argv)
    base, nuevo = reporte.leer([args.base])[0], reporte.leer([args.nuevo])[0]
    texto = markdown(base, nuevo, comparar(base, nuevo))
    print(texto)
    return texto


if __name__ == "__main__":
    main()
