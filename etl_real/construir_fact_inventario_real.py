#!/usr/bin/env python3
"""
INV-61 — Construye dw.fact_inventario a partir del inventario físico real
por ítem x bodega a corte 2025-12-31 (`data/raw_real/inventario/inventarioooo.xlsx`,
`config.INVENTARIO_XLSX`), reemplazando la simulación
(`simular_fact_inventario.py`, camino aleatorio con reposición -- se deja
intacta en el repo como referencia histórica, ya no forma parte de la
cadena de construcción).

Corre DESPUÉS de `validar_inventario.py` y de la segunda pasada de
`construir_dim_producto.py`/`construir_fact_ventas.py` (que ya filtraron
los productos `sin_inventario_dic2025`) -- así el universo de productos
que llega aquí ya es exactamente la intersección ventas ∩ inventario, sin
tener que repetir la doble validación.

Es una FOTO a una sola fecha, no una serie diaria como la simulación --
por diseño no puede alimentar el mismo tipo de diagnóstico histórico que
el dataset simulado sostenía. Ver `06_diagnostico_inventario.ipynb`, que
re-evalúa el "Nivel 2 supervisado" honestamente contra esta limitación
real (una sola fecha) en vez de contra el random walk simulado.

## Mapeo de bodega -> sucursal (igual que `validar_inventario.py`)

"BODEGA PRINCIPAL" -> BODEGA_CENTRAL, no la sucursal PRINCIPAL: es el
acopio central, el producto existe pero no se ha movilizado a ninguna
sucursal. Fila nueva en `dim_sucursal.csv` (`construir_dim_sucursal.py`),
tipo `bodega_central`, no vende directo al público.

## stock_minimo/maximo/punto_reorden/dias_cobertura

El Excel solo trae `stock_disponible` (real). Los otros 4 campos son
NOT NULL en el DDL y no vienen en el Excel: se derivan con la MISMA
fórmula de política que usaba la simulación (`config.INVENTARIO_PARAMS`),
aplicada a la tasa de demanda REAL observada en `fact_ventas.csv`, no a
una serie inventada -- aproximación de política, documentada; solo
`stock_disponible` y `fecha` son 100% reales acá.

Para BODEGA_CENTRAL (no vende directo, no tiene demanda propia por
sucursal) se usa como proxy la demanda total de la empresa para ese
producto (suma de las 3 sucursales reales) -- aproximación explícita.

`dias_cobertura = stock/demanda` si `demanda > 0`; si la demanda
observada es 0 en esa sucursal puntual se usa el centinela `999.0`,
misma convención que ya usaba `simular_fact_inventario.py` (y que
06_diagnostico_inventario.ipynb ya reconoce como "sin límite práctico").

stock_disponible negativo (235 filas del Excel real) se conserva tal
cual -- es una señal real del sistema de inventario del negocio
(backorder/descuadre), no se corrige a 0 sin evidencia de que sea un
error de captura.
"""
import csv
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

import pandas as pd

FECHA_CORTE = "2025-12-31"
SUCURSAL_BODEGA_CENTRAL = "BODEGA_CENTRAL"

BODEGA_A_SUCURSAL = {
    "ALMACEN PRINCIPAL": "PRINCIPAL",
    "ALMACEN LA GLORIETA": "GLORIETA",
    "ALMACEN LA 21": "LA 21",
    "BODEGA PRINCIPAL": SUCURSAL_BODEGA_CENTRAL,
}


def _float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def cargar_inventario_valido(codigos_catalogo):
    df = pd.read_excel(config.INVENTARIO_XLSX, sheet_name="Hoja1", header=3)
    df = df.rename(columns={"Referencia": "codigo_item", "Detalle": "nombre",
                             "Bodega": "bodega_cruda", "Cantidad": "cantidad"})
    df = df[df["codigo_item"].notna()].copy()
    df["codigo_item"] = df["codigo_item"].astype(str).str.strip()
    df["bodega_cruda"] = df["bodega_cruda"].astype(str).str.strip()
    df["cantidad"] = df["cantidad"].map(_float)
    df["sucursal"] = df["bodega_cruda"].map(BODEGA_A_SUCURSAL)

    df = df[df["sucursal"].notna() & df["codigo_item"].isin(codigos_catalogo)]
    return (df.groupby(["codigo_item", "sucursal"], as_index=False)
            .agg(cantidad=("cantidad", "sum")))


def cargar_demanda_diaria_por_par():
    """(codigo_item, sucursal) -> demanda_diaria real: ventas / días de
    ventana activa (misma fórmula que usaba la simulación). También arma
    demanda_producto_total (suma de las 3 sucursales reales), proxy de
    demanda para BODEGA_CENTRAL."""
    fact_ventas_path = config.SALIDA_DIR / "fact_ventas.csv"
    if not fact_ventas_path.is_file():
        print("Falta fact_ventas.csv -- correr construir_fact_ventas.py primero.")
        sys.exit(1)

    ventas_por_par = defaultdict(dict)
    min_fecha, max_fecha = {}, {}
    with open(fact_ventas_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            suc = row["sucursal"]
            if suc == config.SUCURSAL_SIN_TERMINAL or row["es_devolucion"] == "True":
                continue
            cod, fecha = row["codigo_item"], row["fecha"]
            cantidad = float(row["cantidad"])
            par = (cod, suc)
            ventas_por_par[par][fecha] = ventas_por_par[par].get(fecha, 0.0) + cantidad
            if par not in min_fecha or fecha < min_fecha[par]:
                min_fecha[par] = fecha
            if par not in max_fecha or fecha > max_fecha[par]:
                max_fecha[par] = fecha

    demanda_par = {}
    demanda_producto_total = defaultdict(float)
    for par, ventas_dia in ventas_por_par.items():
        cod, suc = par
        d0, d1 = date.fromisoformat(min_fecha[par]), date.fromisoformat(max_fecha[par])
        dias_ventana = (d1 - d0).days + 1
        demanda = sum(ventas_dia.values()) / dias_ventana if dias_ventana > 0 else 0.0
        demanda_par[par] = demanda
        demanda_producto_total[cod] += demanda

    return demanda_par, demanda_producto_total


def cargar_catalogo_final():
    path = config.SALIDA_DIR / "dim_producto.csv"
    if not path.is_file():
        print("Falta dim_producto.csv -- correr construir_dim_producto.py primero.")
        sys.exit(1)
    with open(path, newline="", encoding="utf-8-sig") as f:
        return {row["codigo_item"] for row in csv.DictReader(f)}


def construir():
    codigos_catalogo = cargar_catalogo_final()
    inv_valido = cargar_inventario_valido(codigos_catalogo)
    demanda_par, demanda_producto_total = cargar_demanda_diaria_por_par()
    params = config.INVENTARIO_PARAMS

    out_path = config.SALIDA_DIR / "fact_inventario.csv"
    fieldnames = ["codigo_item", "sucursal", "fecha", "stock_disponible",
                  "stock_minimo", "stock_maximo", "punto_reorden", "dias_cobertura"]

    n_centinela = 0
    n_stock_negativo = 0
    with open(out_path, "w", newline="", encoding="utf-8-sig") as fout:
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()
        for row in inv_valido.itertuples(index=False):
            cod, suc, stock = row.codigo_item, row.sucursal, row.cantidad
            if suc == SUCURSAL_BODEGA_CENTRAL:
                demanda = demanda_producto_total.get(cod, 0.0)
            else:
                demanda = demanda_par.get((cod, suc), 0.0)

            stock_min = max(1, round(demanda * params["dias_stock_minimo"]))
            stock_max = max(stock_min + 5, round(demanda * params["dias_stock_maximo"]))
            punto_reorden = max(stock_min + 1, round(demanda * params["dias_punto_reorden"]))
            if demanda > 0:
                dias_cob = round(stock / demanda, 1)
            else:
                dias_cob = 999.0
                n_centinela += 1
            if stock < 0:
                n_stock_negativo += 1

            writer.writerow({
                "codigo_item": cod, "sucursal": suc, "fecha": FECHA_CORTE,
                "stock_disponible": stock, "stock_minimo": stock_min,
                "stock_maximo": stock_max, "punto_reorden": punto_reorden,
                "dias_cobertura": dias_cob,
            })

    print(f"fact_inventario: {len(inv_valido):,} filas (foto única a {FECHA_CORTE}) -> {out_path}")
    print(f"  Pares con demanda observada 0 en esa sucursal (dias_cobertura centinela 999.0): {n_centinela:,}")
    print(f"  Filas con stock_disponible negativo (dato real, no se corrige): {n_stock_negativo:,}")
    print(f"  sucursales/bodegas en la salida: {sorted(inv_valido['sucursal'].unique())}")


if __name__ == "__main__":
    construir()
