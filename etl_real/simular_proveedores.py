#!/usr/bin/env python3
"""
INV-60 — Simula dw.dim_proveedor y la asignación producto->proveedor.

No hay fuente real de proveedores en los reportes de venta Siigo. Se
reutiliza el patrón de etl/paso_02_sinteticos.py de InventaIO (catálogo
fijo de proveedores ficticios + asignación por categoría), pero la
asignación usa las categorías REALES clasificadas por
clasificar_productos.py, no las de Favorita.
"""
import csv
import random
import sys
from pathlib import Path

import config  # noqa: E402


def construir():
    dim_producto_path = config.SALIDA_DIR / "dim_producto.csv"
    if not dim_producto_path.is_file():
        print("Falta dim_producto.csv -- correr construir_dim_producto.py primero.")
        sys.exit(1)

    rng = random.Random(config.RANDOM_SEED)

    proveedores = []
    for i, p in enumerate(config.PROVEEDORES_SEED, start=1):
        proveedores.append({
            "id_provisional": i,
            "codigo": p["codigo"],
            "razon_social": p["razon_social"],
            "nit": p["nit"],
            "ciudad": p["ciudad"],
            "telefono": f"+57 3{rng.randint(0, 19):02d}{rng.randint(1000000, 9999999)}",
            "email": f"ventas@{p['razon_social'].split()[0].lower()}.com.co",
            "lead_time_dias": p["lead_time_dias"],
            "categorias": p["categorias"],
            "calificacion": round(rng.uniform(3.5, 5.0), 2),
        })

    config.SALIDA_DIR.mkdir(parents=True, exist_ok=True)
    prov_path = config.SALIDA_DIR / "dim_proveedor.csv"
    with open(prov_path, "w", newline="", encoding="utf-8-sig") as f:
        fieldnames = ["codigo", "razon_social", "nit", "ciudad", "telefono",
                      "email", "lead_time_dias", "categorias", "calificacion"]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for p in proveedores:
            row = {k: p[k] for k in fieldnames}
            row["categorias"] = "|".join(p["categorias"])
            w.writerow(row)
    print(f"dim_proveedor: {len(proveedores)} proveedores -> {prov_path}")

    # Asignación producto -> proveedor por categoría (candidatos = los
    # proveedores cuya lista de categorias incluye la del producto).
    asignaciones = []
    sin_candidato = 0
    with open(dim_producto_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            cat = row["categoria"]
            candidatos = [p for p in proveedores if cat in p["categorias"]]
            if not candidatos:
                sin_candidato += 1
                elegido = proveedores[0]  # fallback: primer proveedor (Abarrotes)
            else:
                elegido = rng.choice(candidatos)
            asignaciones.append({
                "codigo_item": row["codigo_item"],
                "codigo_proveedor": elegido["codigo"],
            })

    asign_path = config.SALIDA_DIR / "producto_proveedor.csv"
    with open(asign_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["codigo_item", "codigo_proveedor"])
        w.writeheader()
        w.writerows(asignaciones)

    print(f"Asignaciones producto->proveedor: {len(asignaciones)} "
          f"({sin_candidato} sin categoría con proveedor, fallback a {proveedores[0]['codigo']})")
    print(f"Guardado en {asign_path}")


if __name__ == "__main__":
    construir()
