#!/usr/bin/env python3
"""
INV-60 — Construye dw.dim_tiempo a partir del rango real de fechas de
ventas_tidy.csv (2023-2025), no del rango Favorita (2013-2017).

Convención de dia_semana: ISO (1=lunes ... 7=domingo) -- la misma que
usa parse_ventas_dir.py en el repo ventas2 -- NO se adopta la
convención 0-6 del init.sql original de InventaIO (ver
docs/INV-60-notas-migracion-dw.md).

cargar_festivos()/construir_dias_puente() están duplicadas en
calendario_utils.py (mismo directorio) en vez de importarse de
ventas2 -- ver el docstring de ese archivo.
"""
import csv
from datetime import date, timedelta
from pathlib import Path

from calendario_utils import cargar_festivos, construir_dias_puente
import config

NOMBRES_DIA = {
    1: "lunes", 2: "martes", 3: "miércoles", 4: "jueves",
    5: "viernes", 6: "sábado", 7: "domingo",
}


def rango_fechas_reales(path_csv: Path) -> tuple:
    """Fecha mínima y máxima observadas en ventas_tidy.csv (fecha_venta o
    fecha_reporte). Define el rango real de dim_tiempo, no el de Favorita."""
    minima = None
    maxima = None
    with open(path_csv, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            fecha_iso = row.get("fecha_venta") or row.get("fecha_reporte")
            if not fecha_iso:
                continue
            d = date.fromisoformat(fecha_iso)
            if minima is None or d < minima:
                minima = d
            if maxima is None or d > maxima:
                maxima = d
    return minima, maxima


def ultimo_dia_mes(d: date) -> date:
    if d.month == 12:
        return date(d.year, 12, 31)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)


def clasificar_temporada(d: date) -> str:
    """Mismo criterio de etl/paso_01_transformar.py de InventaIO
    (clasificar_temporada), adaptado a fechas reales en vez de Favorita."""
    m, dia = d.month, d.day
    if m == 12 or (m == 1 and dia <= 6):
        return "navidad"
    if m in (1, 2) and dia > 6:
        return "escolar_inicio"
    if m in (3, 4):
        return "semana_santa"
    if m in (6, 7):
        return "vacaciones_mitad"
    if m == 10 and dia >= 20:
        return "halloween"
    if m == 11:
        return "black_friday"
    return "regular"


def construir():
    minima, maxima = rango_fechas_reales(config.VENTAS_TIDY_CSV)
    print(f"Rango real de fechas: {minima.isoformat()} -> {maxima.isoformat()}")

    festivos = cargar_festivos(config.FESTIVOS_CSV)
    puentes = construir_dias_puente(festivos)

    filas = []
    d = minima
    while d <= maxima:
        fecha_iso = d.isoformat()
        dia_semana = d.isoweekday()  # ISO: 1=lunes ... 7=domingo
        u_dia_mes = ultimo_dia_mes(d)
        filas.append({
            "fecha": fecha_iso,
            "anio": d.year,
            "mes": d.month,
            "dia": d.day,
            "dia_semana": dia_semana,
            "nombre_dia": NOMBRES_DIA[dia_semana],
            "semana_iso": d.isocalendar()[1],
            "trimestre": (d.month - 1) // 3 + 1,
            "es_fin_semana": dia_semana in (6, 7),
            "es_festivo": fecha_iso in festivos,
            "nombre_festivo": festivos.get(fecha_iso, ""),
            "es_puente_festivo": fecha_iso in puentes,
            "es_quincena": d.day == 15 or d == u_dia_mes,
            "temporada": clasificar_temporada(d),
        })
        d += timedelta(days=1)

    config.SALIDA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = config.SALIDA_DIR / "dim_tiempo.csv"
    fieldnames = ["fecha", "anio", "mes", "dia", "dia_semana", "nombre_dia",
                  "semana_iso", "trimestre", "es_fin_semana", "es_festivo",
                  "nombre_festivo", "es_puente_festivo", "es_quincena", "temporada"]
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(filas)

    n_festivos = sum(1 for r in filas if r["es_festivo"])
    n_quincena = sum(1 for r in filas if r["es_quincena"])
    print(f"dim_tiempo: {len(filas)} fechas ({n_festivos} festivos, {n_quincena} quincenas)")
    print(f"Guardado en {out_path}")


if __name__ == "__main__":
    construir()
