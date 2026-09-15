#!/usr/bin/env python3
"""
INV-60 — Construye dw.dim_evento a partir de festivos_colombia_2022_2026.csv
(ya validado contra el generador independiente de InventaIO, ver
docs/INV-60-compatibilidad-datos.md), acotado al rango real de dim_tiempo.

es_transferido=True cuando el nombre del festivo trae "(observado)" --
así se marca el corrimiento de la Ley Emiliani sin tener que recalcularlo.
"""
import csv
import sys
from pathlib import Path

import config  # noqa: E402


def construir():
    dim_tiempo_path = config.SALIDA_DIR / "dim_tiempo.csv"
    if not dim_tiempo_path.is_file():
        print("Falta dim_tiempo.csv -- correr construir_dim_tiempo.py primero.")
        sys.exit(1)

    with open(dim_tiempo_path, newline="", encoding="utf-8-sig") as f:
        fechas_rango = {row["fecha"] for row in csv.DictReader(f)}

    filas = []
    with open(config.FESTIVOS_CSV, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            fecha = row["fecha"]
            if fecha not in fechas_rango:
                continue
            nombre = row["nombre_festivo"]
            filas.append({
                "fecha": fecha,
                "tipo": "festivo",
                "nombre": nombre,
                "descripcion": f"Festivo nacional: {nombre}",
                "ambito": "nacional",
                "es_transferido": "(observado)" in nombre,
            })

    config.SALIDA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = config.SALIDA_DIR / "dim_evento.csv"
    fieldnames = ["fecha", "tipo", "nombre", "descripcion", "ambito", "es_transferido"]
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(filas)

    print(f"dim_evento: {len(filas)} eventos -> {out_path}")


if __name__ == "__main__":
    construir()
