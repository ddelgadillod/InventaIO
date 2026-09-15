#!/usr/bin/env python3
"""
INV-60 — Simula dw.fact_inventario para las 3 sucursales reales.

No existe fuente real de inventario (ver docs/INV-60-compatibilidad-datos.md
y docs/INV-14-recomendaciones-eda.md) -- ni en nuestros datos ni, pese al
nombre, en los "reales" de InventaIO (también 100% sintéticos). Se adapta
el método de etl/paso_02_sinteticos.py::generar_fact_inventario() de
InventaIO (demanda promedio -> stock_min/max/punto_reorden, camino
aleatorio con reposición), con dos correcciones ya documentadas en
INV-14:

1. demanda_diaria se calcula dividiendo entre TODOS los días de la
   ventana activa (primera a última venta real observada para ese par
   producto x sucursal), no solo entre los días con venta registrada
   (ese conteo era el sesgo al alza del método original).
2. La grilla diaria simulada solo cubre esa ventana activa, no el rango
   global del dataset -- no se inventa stock de productos que una
   sucursal nunca vendió.

SIN_SUCURSAL (terminal FV2, facturación electrónica) se excluye: no es
una ubicación física que sostenga inventario.
"""
import csv
import random
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import config  # noqa: E402


def construir():
    fact_ventas_path = config.SALIDA_DIR / "fact_ventas.csv"
    if not fact_ventas_path.is_file():
        print("Falta fact_ventas.csv -- correr construir_fact_ventas.py primero.")
        sys.exit(1)

    ventas_por_par = defaultdict(dict)  # (cod,suc) -> {fecha_iso: cantidad}
    min_fecha = {}
    max_fecha = {}

    print("Agregando ventas reales por (producto, sucursal, día)...")
    with open(fact_ventas_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            suc = row["sucursal"]
            if suc == config.SUCURSAL_SIN_TERMINAL:
                continue
            if row["es_devolucion"] == "True":
                continue
            cod = row["codigo_item"]
            fecha = row["fecha"]
            cantidad = float(row["cantidad"])
            par = (cod, suc)
            ventas_por_par[par][fecha] = ventas_por_par[par].get(fecha, 0.0) + cantidad
            if par not in min_fecha or fecha < min_fecha[par]:
                min_fecha[par] = fecha
            if par not in max_fecha or fecha > max_fecha[par]:
                max_fecha[par] = fecha

    print(f"Pares (producto, sucursal) con ventas reales: {len(ventas_por_par)}")

    params = config.INVENTARIO_PARAMS
    rng = random.Random(config.RANDOM_SEED)

    out_path = config.SALIDA_DIR / "fact_inventario.csv"
    fieldnames = ["codigo_item", "sucursal", "fecha", "stock_disponible",
                  "stock_minimo", "stock_maximo", "punto_reorden", "dias_cobertura"]

    n_filas = 0
    pares_ordenados = sorted(ventas_por_par.keys())

    with open(out_path, "w", newline="", encoding="utf-8-sig") as fout:
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()

        for idx, par in enumerate(pares_ordenados, start=1):
            cod, suc = par
            ventas_dia = ventas_por_par[par]
            d0 = date.fromisoformat(min_fecha[par])
            d1 = date.fromisoformat(max_fecha[par])
            dias_ventana = (d1 - d0).days + 1

            demanda = max(0.5, sum(ventas_dia.values()) / dias_ventana)
            stock_min = max(1, round(demanda * params["dias_stock_minimo"]))
            stock_max = max(stock_min + 5, round(demanda * params["dias_stock_maximo"]))
            punto_reorden = max(stock_min + 1, round(demanda * params["dias_punto_reorden"]))
            stock = round(stock_max * rng.uniform(0.6, 0.8))

            d = d0
            while d <= d1:
                fecha_iso = d.isoformat()
                venta = ventas_dia.get(fecha_iso, 0.0)

                stock = max(0, stock - venta)
                if stock <= punto_reorden:
                    stock += max(0, round(stock_max * rng.uniform(0.8, 0.95) - stock))

                variacion = rng.gauss(0, demanda * params["variacion_stock_pct"])
                stock = max(0, round(stock + variacion))
                dias_cob = round(stock / demanda, 1) if demanda > 0 else 999.0

                writer.writerow({
                    "codigo_item": cod, "sucursal": suc, "fecha": fecha_iso,
                    "stock_disponible": stock, "stock_minimo": stock_min,
                    "stock_maximo": stock_max, "punto_reorden": punto_reorden,
                    "dias_cobertura": dias_cob,
                })
                n_filas += 1
                d += timedelta(days=1)

            if idx % 1000 == 0:
                print(f"  Progreso: {idx}/{len(pares_ordenados)} pares, {n_filas:,} filas")

    print(f"fact_inventario: {n_filas:,} filas -> {out_path}")


if __name__ == "__main__":
    construir()
