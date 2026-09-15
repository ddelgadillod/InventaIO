#!/usr/bin/env python3
"""
INV-60 — Construye dw.fact_ventas desde ventas_tidy.csv.

Mapeo verificado contra datos reales (ver docs/INV-60-notas-migracion-dw.md):
- es_devolucion = cantidad < 0 (confirmado: 1.147 filas Formato C +
  40 filas Formato A tienen cantidad<0; cero filas mixtas venta+
  devolución en la misma línea).
- cantidad final = abs(cantidad); valor_total = abs(valor_venta);
  costo_total = abs(costo).
- valor_unitario/costo_unitario = valor_total/costo_total ÷ cantidad
  (con guarda para cantidad==0).
- en_promocion no existe en el dato real -> FALSE (no NULL, coincide con
  el DEFAULT FALSE del DDL).
- id_proveedor viene de producto_proveedor.csv (dw/simular_proveedores.py).
- sucursal 'SIN_SUCURSAL' (terminal FV2) SÍ se carga -- tiene fila propia
  en dim_sucursal, no se descarta en silencio.
"""
import csv
import sys
from pathlib import Path

import config  # noqa: E402


def _float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def cargar_mapeo_proveedor(path_csv: Path) -> dict:
    mapeo = {}
    with open(path_csv, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            mapeo[row["codigo_item"]] = row["codigo_proveedor"]
    return mapeo


def construir():
    prov_path = config.SALIDA_DIR / "producto_proveedor.csv"
    if not prov_path.is_file():
        print("Falta producto_proveedor.csv -- correr simular_proveedores.py primero.")
        sys.exit(1)
    mapeo_proveedor = cargar_mapeo_proveedor(prov_path)

    out_path = config.SALIDA_DIR / "fact_ventas.csv"
    fieldnames = ["codigo_item", "sucursal", "fecha", "codigo_proveedor",
                  "cantidad", "valor_unitario", "valor_total",
                  "costo_unitario", "costo_total", "en_promocion", "es_devolucion"]

    n_total = 0
    n_cantidad_cero = 0
    n_sin_producto_o_fecha = 0

    config.SALIDA_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.VENTAS_TIDY_CSV, newline="", encoding="utf-8-sig") as fin, \
         open(out_path, "w", newline="", encoding="utf-8-sig") as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()

        for row in reader:
            cod = row.get("codigo_producto")
            fecha = row.get("fecha_venta") or row.get("fecha_reporte")
            sucursal = row.get("sucursal")
            if not cod or not fecha or not sucursal:
                n_sin_producto_o_fecha += 1
                continue

            cantidad_cruda = _float(row.get("cantidad"))
            es_devolucion = cantidad_cruda < 0
            cantidad = abs(cantidad_cruda)
            valor_total = abs(_float(row.get("valor_venta")))
            costo_total = abs(_float(row.get("costo")))

            if cantidad == 0:
                n_cantidad_cero += 1
                valor_unitario = 0.0
                costo_unitario = 0.0
            else:
                valor_unitario = round(valor_total / cantidad, 2)
                costo_unitario = round(costo_total / cantidad, 2)

            writer.writerow({
                "codigo_item": cod,
                "sucursal": sucursal,
                "fecha": fecha,
                "codigo_proveedor": mapeo_proveedor.get(cod, ""),
                "cantidad": cantidad,
                "valor_unitario": valor_unitario,
                "valor_total": valor_total,
                "costo_unitario": costo_unitario,
                "costo_total": costo_total,
                "en_promocion": False,
                "es_devolucion": es_devolucion,
            })
            n_total += 1

    print(f"fact_ventas: {n_total} filas -> {out_path}")
    print(f"  Filas con cantidad==0 (valor_unitario/costo_unitario en 0): {n_cantidad_cero}")
    print(f"  Filas descartadas por falta de producto/fecha/sucursal: {n_sin_producto_o_fecha}")


if __name__ == "__main__":
    construir()
