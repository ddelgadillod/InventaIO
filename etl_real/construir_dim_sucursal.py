#!/usr/bin/env python3
"""
INV-60 — Construye dw.dim_sucursal con las 3 sucursales reales
(PRINCIPAL, LA 21, GLORIETA, del crosswalk terminal_pos->sucursal de
INV-61) más SIN_SUCURSAL como fila placeholder para las ventas de FV2
(facturación electrónica sin punto de venta) -- así fact_ventas siempre
tiene un FK válido, sin descartar esas filas en silencio.

No hay ciudad/departamento real disponible en el reporte Siigo (se deja
vacío, a diferencia de InventaIO que inventa Cali/Palmira/Tuluá).
factor_volumen se calcula del volumen real observado, no se fuerza a 5.0.
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

import config  # noqa: E402


def calcular_volumen_por_sucursal(path_csv: Path) -> dict:
    """Suma valor_venta (solo ventas, cantidad>=0) por sucursal real."""
    volumen = defaultdict(float)
    conocidas = set(config.SUCURSALES_REALES) | {config.SUCURSAL_SIN_TERMINAL}
    with open(path_csv, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            suc = row.get("sucursal")
            if suc not in conocidas:
                continue
            try:
                cantidad = float(row["cantidad"] or 0)
                valor = float(row["valor_venta"] or 0)
            except ValueError:
                continue
            if cantidad < 0:
                continue  # devolución, no cuenta para volumen de venta
            volumen[suc] += valor
    return volumen


def construir():
    volumen = calcular_volumen_por_sucursal(config.VENTAS_TIDY_CSV)
    volumen_reales = {k: v for k, v in volumen.items() if k in config.SUCURSALES_REALES}
    baseline = min(volumen_reales.values()) if volumen_reales else 1.0
    principal_nombre = max(volumen_reales, key=volumen_reales.get) if volumen_reales else "PRINCIPAL"

    filas = []
    for i, nombre in enumerate(config.SUCURSALES_REALES, start=1):
        vol = volumen.get(nombre, 0.0)
        filas.append({
            "codigo_tienda": i,
            "nombre": nombre,
            "ciudad": "",
            "departamento": "",
            "tipo": "principal" if nombre == principal_nombre else "estandar",
            "cluster": 1 if nombre == principal_nombre else 2,
            "factor_volumen": round(vol / baseline, 2) if baseline else 1.0,
            "volumen_real_cop": round(vol, 2),
        })

    # Fila placeholder para ventas sin sucursal física (terminal FV2).
    filas.append({
        "codigo_tienda": len(config.SUCURSALES_REALES) + 1,
        "nombre": config.SUCURSAL_SIN_TERMINAL,
        "ciudad": "",
        "departamento": "",
        "tipo": "sin_terminal",
        "cluster": 0,
        "factor_volumen": None,
        "volumen_real_cop": round(volumen.get(config.SUCURSAL_SIN_TERMINAL, 0.0), 2),
    })

    config.SALIDA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = config.SALIDA_DIR / "dim_sucursal.csv"
    fieldnames = ["codigo_tienda", "nombre", "ciudad", "departamento", "tipo",
                  "cluster", "factor_volumen", "volumen_real_cop"]
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(filas)

    print("dim_sucursal:")
    for r in filas:
        print(f"  {r['nombre']:<15} tipo={r['tipo']:<12} factor_volumen={r['factor_volumen']} "
              f"volumen_real=${r['volumen_real_cop']:,.0f} COP")
    print(f"Guardado en {out_path}")


if __name__ == "__main__":
    construir()
