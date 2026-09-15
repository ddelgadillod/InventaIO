#!/usr/bin/env python3
"""
INV-60 — Clasifica el catálogo real (codigo_producto/nombre_producto) en
categoria/familia/es_perecedero/unidad_medida usando una heurística de
palabras clave sobre nombre_producto (config.CATEGORIA_KEYWORDS).

El reporte Siigo no trae categoría/familia/perecedero -- esto es un
best-effort documentado, NO una clasificación validada por negocio. Cada
fila queda con `regla_aplicada` para que se pueda auditar/corregir a mano
después (ver docs/INV-60-notas-migracion-dw.md).
"""
import csv
import re
import sys
from collections import Counter
from pathlib import Path

import config  # noqa: E402


def extraer_codigos_nombres(path_csv: Path) -> dict:
    """Un nombre por codigo_producto: el observado en la venta más reciente."""
    ultimo = {}  # codigo -> (fecha, nombre)
    with open(path_csv, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            cod = row.get("codigo_producto")
            nom = row.get("nombre_producto")
            if not cod or not nom:
                continue
            fecha = row.get("fecha_venta") or row.get("fecha_reporte") or ""
            actual = ultimo.get(cod)
            if actual is None or fecha >= actual[0]:
                ultimo[cod] = (fecha, nom)
    return {cod: nom for cod, (_, nom) in ultimo.items()}


def clasificar_categoria(nombre: str) -> tuple:
    """Devuelve (categoria, regla_aplicada). Primera keyword que matchea
    gana; si ninguna matchea, cae al default documentado."""
    nombre_up = nombre.upper()
    for categoria, keywords in config.CATEGORIA_KEYWORDS:
        for kw in keywords:
            if kw in nombre_up:
                return categoria, kw.strip()
    return config.DEFAULT_CATEGORIA, "default_sin_match"


def clasificar_unidad_medida(nombre: str) -> str:
    nombre_up = nombre.upper()
    for unidad, patron in config.UNIDAD_MEDIDA_PATTERNS:
        if re.search(patron, nombre_up):
            return unidad
    return config.DEFAULT_UNIDAD_MEDIDA


def construir():
    nombres = extraer_codigos_nombres(config.VENTAS_TIDY_CSV)
    print(f"Productos distintos a clasificar: {len(nombres)}")

    filas = []
    contador_regla = Counter()
    for cod, nombre in nombres.items():
        categoria, regla = clasificar_categoria(nombre)
        unidad = clasificar_unidad_medida(nombre)
        es_perecedero = categoria in config.CATEGORIAS_PERECEDERAS
        filas.append({
            "codigo_producto": cod,
            "nombre_producto": nombre,
            "categoria": categoria,
            "familia": categoria,  # Siigo no trae subfamilia; se duplica el nivel
            "es_perecedero": es_perecedero,
            "unidad_medida": unidad,
            "regla_aplicada": regla,
        })
        contador_regla[regla] += 1

    config.SALIDA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = config.SALIDA_DIR / "clasificacion_productos.csv"
    fieldnames = ["codigo_producto", "nombre_producto", "categoria", "familia",
                  "es_perecedero", "unidad_medida", "regla_aplicada"]
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(filas)

    n_default = contador_regla["default_sin_match"]
    pct_default = 100 * n_default / len(filas) if filas else 0
    print(f"Sin match de ninguna regla (van a '{config.DEFAULT_CATEGORIA}' por defecto): "
          f"{n_default} ({pct_default:.1f}%)")

    por_categoria = Counter(f["categoria"] for f in filas)
    print("Distribución por categoría:")
    for cat, n in por_categoria.most_common():
        print(f"  {cat:<20} {n}")
    print(f"Guardado en {out_path}")


if __name__ == "__main__":
    construir()
