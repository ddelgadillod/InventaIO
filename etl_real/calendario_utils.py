#!/usr/bin/env python3
"""
INV-60 — Utilidades de calendario para etl_real/.

Duplicado intencional de cargar_festivos()/construir_dias_puente() de
parse_ventas_dir.py (repo ventas2) -- para que este pipeline no dependa
de otro repo en tiempo de ejecución. Si se corrige la lógica de puentes
allá, hay que replicar el cambio aquí a mano (son ~15 líneas, no vale
la pena una dependencia cruzada entre repos por esto).
"""
import csv
from datetime import date, timedelta
from pathlib import Path


def cargar_festivos(path: Path) -> dict:
    """Carga el CSV de festivos (columnas fecha,nombre_festivo) a un dict
    {fecha_iso: nombre_festivo}."""
    festivos = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            festivos[row["fecha"]] = row["nombre_festivo"]
    return festivos


def construir_dias_puente(festivos: dict) -> set:
    """Si el festivo cae lunes, sábado y domingo anteriores son puente.
    Si no cae lunes, solo el día calendario inmediato anterior."""
    puente = set()
    for fecha_iso in festivos:
        d = date.fromisoformat(fecha_iso)
        if d.isoweekday() == 1:  # lunes
            puente.add((d - timedelta(days=1)).isoformat())
            puente.add((d - timedelta(days=2)).isoformat())
        else:
            puente.add((d - timedelta(days=1)).isoformat())
    return puente
