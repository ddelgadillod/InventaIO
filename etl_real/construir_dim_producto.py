#!/usr/bin/env python3
"""
INV-60 — Construye dw.dim_producto a partir del catálogo real observado en
ventas_tidy.csv, no del catálogo sintético de InventaIO (~200 productos de
Favorita). codigo_item se trata como VARCHAR (ver dw/schema_dw.sql) porque
los códigos reales de Siigo son alfanuméricos.

precio_base/costo_base se derivan de la ÚLTIMA venta real observada por
producto (unitario = valor_venta/cantidad de esa fila) -- a diferencia de
InventaIO, que los inventa con rangos aleatorios por categoría. iva_pct se
deriva igual, de la última fila con valor_venta>0.

INV-61 -- se ejecuta DOS veces en la cadena: la primera pasada produce el
catálogo completo que `validar_inventario.py` necesita para la doble
validación contra el inventario real (2025-12-31); la segunda pasada (tras
correr `validar_inventario.py`) excluye del catálogo los productos con
motivo `sin_inventario_dic2025` en `productos_excluidos.csv` -- a
diferencia de otros motivos ahí (ej. `ancheta_no_recurrente`), que sólo se
excluyen de `fact_ventas` y siguen en `dim_producto.csv` como referencia,
estos se eliminan del catálogo por pedido explícito del negocio (el
inventario real es la fuente de verdad de qué sigue vigente).
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402


def cargar_clasificacion(path_csv: Path) -> dict:
    clasif = {}
    with open(path_csv, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            clasif[row["codigo_producto"]] = row
    return clasif


def _float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def extraer_precio_costo_iva(path_csv: Path) -> dict:
    """Última observación válida (cantidad>0, venta no devolución) de
    valor_unitario/costo_unitario/iva_pct por codigo_producto."""
    ultimo = {}  # codigo -> (fecha, dict)
    with open(path_csv, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            cod = row.get("codigo_producto")
            if not cod:
                continue
            cantidad = _float(row.get("cantidad"))
            if cantidad <= 0:
                continue  # solo ventas reales, no devoluciones ni ceros
            valor = _float(row.get("valor_venta"))
            costo = _float(row.get("costo"))
            iva = _float(row.get("valor_iva"))
            fecha = row.get("fecha_venta") or row.get("fecha_reporte") or ""

            precio_unit = round(valor / cantidad, 2)
            costo_unit = round(costo / cantidad, 2)
            iva_pct = round(100 * iva / valor, 2) if valor else 0.0

            actual = ultimo.get(cod)
            if actual is None or fecha >= actual[0]:
                ultimo[cod] = (fecha, {
                    "precio_base": precio_unit,
                    "costo_base": costo_unit,
                    "iva_pct": iva_pct,
                })
    return {cod: v for cod, (_, v) in ultimo.items()}


def cargar_codigos_sin_inventario(path: Path) -> set:
    if not path.is_file():
        return set()
    with open(path, newline="", encoding="utf-8-sig") as f:
        return {row["codigo_producto"] for row in csv.DictReader(f)
                if row["motivo"] == "sin_inventario_dic2025"}


def construir():
    clasif_path = config.SALIDA_DIR / "clasificacion_productos.csv"
    if not clasif_path.is_file():
        print("Falta clasificacion_productos.csv -- correr clasificar_productos.py primero.")
        sys.exit(1)

    clasificacion = cargar_clasificacion(clasif_path)
    precios = extraer_precio_costo_iva(config.VENTAS_TIDY_CSV)
    sin_inventario = cargar_codigos_sin_inventario(config.PRODUCTOS_EXCLUIDOS_CSV)
    if sin_inventario:
        print(f"Excluidos del catálogo por no existir en el inventario real "
              f"(motivo sin_inventario_dic2025): {len(sin_inventario)}")

    filas = []
    sin_precio = 0
    for cod, clasif in clasificacion.items():
        if cod in sin_inventario:
            continue
        precio_info = precios.get(cod)
        if precio_info is None:
            sin_precio += 1
            # iva_pct es NOT NULL DEFAULT 19.00 en el DDL -- mismo default
            # ahi para productos sin ninguna venta con cantidad>0 observada.
            precio_info = {"precio_base": None, "costo_base": None, "iva_pct": 19.00}

        filas.append({
            "codigo_item": cod,
            "nombre": clasif["nombre_producto"],
            "familia": clasif["familia"],
            "clase": "",
            "categoria": clasif["categoria"],
            "es_perecedero": clasif["es_perecedero"],
            "unidad_medida": clasif["unidad_medida"],
            "precio_base": precio_info["precio_base"],
            "costo_base": precio_info["costo_base"],
            "margen_pct": (
                round(100 * (precio_info["precio_base"] - precio_info["costo_base"]) / precio_info["precio_base"], 2)
                if precio_info["precio_base"] else None
            ),
            "iva_pct": precio_info["iva_pct"],
        })

    config.SALIDA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = config.SALIDA_DIR / "dim_producto.csv"
    fieldnames = ["codigo_item", "nombre", "familia", "clase", "categoria",
                  "es_perecedero", "unidad_medida", "precio_base", "costo_base",
                  "margen_pct", "iva_pct"]
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(filas)

    print(f"dim_producto: {len(filas)} productos")
    print(f"  Sin ninguna venta con cantidad>0 (precio/costo quedan NULL): {sin_precio}")
    print(f"Guardado en {out_path}")


if __name__ == "__main__":
    construir()
