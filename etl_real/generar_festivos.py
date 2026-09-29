#!/usr/bin/env python3
"""
INV-20 — Genera etl_real/festivos_colombia_2022_2027.csv con la librería
`holidays` (festivos oficiales de Colombia, con el corrimiento de la Ley
Emiliani marcado como "(observado)").

Es la misma fuente del festivos_colombia_2022_2026.csv que produce el repo
ventas2 (ver su README): para 2022-2026 este script reproduce ese archivo
fecha por fecha y nombre por nombre, y agrega 2027 para que dim_tiempo
cubra el horizonte de pronóstico. El CSV resultante SÍ se versiona (son
datos públicos, no del negocio), así que este script solo hace falta para
extender el rango -- `holidays` no es dependencia del pipeline.

    python -m pip install holidays
    python generar_festivos.py 2022 2027
"""
import csv
import sys
from pathlib import Path

SALIDA = Path(__file__).resolve().parent / "festivos_colombia_2022_2027.csv"


def generar(anio_inicio: int, anio_fin: int) -> list:
    import holidays

    co = holidays.country_holidays("CO", years=range(anio_inicio, anio_fin + 1), language="es")
    return [{"fecha": d.isoformat(), "nombre_festivo": nombre} for d, nombre in sorted(co.items())]


def main():
    anio_inicio, anio_fin = (int(a) for a in sys.argv[1:3]) if len(sys.argv) >= 3 else (2022, 2027)
    filas = generar(anio_inicio, anio_fin)
    salida = SALIDA.with_name(f"festivos_colombia_{anio_inicio}_{anio_fin}.csv")
    with open(salida, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["fecha", "nombre_festivo"])
        w.writeheader()
        w.writerows(filas)
    print(f"{len(filas)} festivos {anio_inicio}-{anio_fin} -> {salida}")


if __name__ == "__main__":
    main()
