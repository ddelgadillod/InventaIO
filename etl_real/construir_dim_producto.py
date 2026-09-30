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

Bug real encontrado al re-ejecutar toda la cadena con datos nuevos
(2022): la primera pasada SIEMPRE filtraba por `sin_inventario_dic2025`
si `productos_excluidos.csv` ya traía ese motivo de una corrida anterior
-- entonces dejaba de ser "el catálogo completo" que pide el docstring
de arriba, y `validar_inventario.py` (que recalcula ese motivo desde
cero en cada corrida, ver su docstring) solo alcanzaba a ver los códigos
que sobrevivían al filtro de la primera pasada. Resultado: la segunda
pasada terminaba escribiendo un `sin_inventario_dic2025` mucho más chico
que el real (perdía silenciosamente exclusiones ya válidas de corridas
anteriores). Corregido con el flag `--completo` (o `completo=True`): la
primera pasada de cada corrida DEBE usarlo, para que `sin_inventario`
quede vacío sin importar qué haya en el archivo -- la segunda pasada
(sin el flag) es la única que debe filtrar, usando lo que
`validar_inventario.py` ya recalculó completo en esa misma corrida.

INV-22 -- agrega las marcas de logística requiere_frio y se_vende_por_kilo
(ver atributos_producto.marcas_logistica) y escribe
revision_marcas_logistica.csv, la lista que revisa el negocio.
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
import atributos_producto  # noqa: E402


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


def fraccion_lineas_con_decimales(path_csv: Path) -> dict:
    """INV-22: por codigo_producto, la fracción de sus líneas de venta
    (cantidad > 0) con cantidad no entera -- la base de se_vende_por_kilo."""
    lineas, con_decimales = {}, {}
    with open(path_csv, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            cod = row.get("codigo_producto")
            cantidad = _float(row.get("cantidad"))
            if not cod or cantidad <= 0:
                continue
            lineas[cod] = lineas.get(cod, 0) + 1
            if cantidad != int(cantidad):
                con_decimales[cod] = con_decimales.get(cod, 0) + 1
    return {cod: con_decimales.get(cod, 0) / n for cod, n in lineas.items()}


def cargar_codigos_sin_inventario(path: Path) -> set:
    if not path.is_file():
        return set()
    with open(path, newline="", encoding="utf-8-sig") as f:
        return {row["codigo_producto"] for row in csv.DictReader(f)
                if row["motivo"] == "sin_inventario_dic2025"}


def construir(completo: bool = False):
    clasif_path = config.SALIDA_DIR / "clasificacion_productos.csv"
    if not clasif_path.is_file():
        print("Falta clasificacion_productos.csv -- correr clasificar_productos.py primero.")
        sys.exit(1)

    clasificacion = cargar_clasificacion(clasif_path)
    precios = extraer_precio_costo_iva(config.VENTAS_TIDY_CSV)
    # INV-22: marcas de logística (regla + overrides del negocio)
    fraccion_kilo = fraccion_lineas_con_decimales(config.VENTAS_TIDY_CSV)
    overrides_frio = atributos_producto.cargar_overrides(config.OVERRIDES_REQUIERE_FRIO_CSV, "requiere_frio")
    overrides_kilo = atributos_producto.cargar_overrides(config.OVERRIDES_POR_KILO_CSV, "se_vende_por_kilo")
    # completo=True (primera pasada): ignora cualquier sin_inventario_dic2025
    # que ya exista en el archivo -- ver el bug documentado arriba. La
    # segunda pasada (completo=False, default) sí filtra, usando lo que
    # validar_inventario.py acaba de recalcular en esta misma corrida.
    sin_inventario = set() if completo else cargar_codigos_sin_inventario(config.PRODUCTOS_EXCLUIDOS_CSV)
    if completo:
        print("Pasada completa: se ignora cualquier sin_inventario_dic2025 "
              "previo en productos_excluidos.csv (se recalcula en validar_inventario.py).")
    elif sin_inventario:
        print(f"Excluidos del catálogo por no existir en el inventario real "
              f"(motivo sin_inventario_dic2025): {len(sin_inventario)}")

    filas, revision = [], []
    sin_precio = 0
    for cod, clasif in clasificacion.items():
        if cod in sin_inventario:
            continue
        atributos = atributos_producto.atributos(clasif["nombre_producto"], clasif["categoria"])
        fraccion = fraccion_kilo.get(cod, 0.0)
        logistica = atributos_producto.marcas_logistica(
            cod, clasif["nombre_producto"], atributos["es_refrigerado"], fraccion, overrides_frio, overrides_kilo)
        if atributos["es_refrigerado"] or logistica["requiere_frio"] or logistica["se_vende_por_kilo"] or fraccion > 0:
            revision.append({"codigo_item": cod, "nombre": clasif["nombre_producto"],
                             "categoria": clasif["categoria"], "es_refrigerado": atributos["es_refrigerado"],
                             "requiere_frio": logistica["requiere_frio"],
                             "origen_requiere_frio": logistica["origen_requiere_frio"],
                             "fraccion_lineas_decimales": round(fraccion, 3),
                             "se_vende_por_kilo": logistica["se_vende_por_kilo"],
                             "origen_se_vende_por_kilo": logistica["origen_se_vende_por_kilo"]})
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
            # INV-20: atributos de la regla de priorización (condiciones 1-5)
            **atributos,
            # INV-22: marcas de logística
            **{col: logistica[col] for col in atributos_producto.COLUMNAS_LOGISTICA},
        })

    config.SALIDA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = config.SALIDA_DIR / "dim_producto.csv"
    fieldnames = ["codigo_item", "nombre", "familia", "clase", "categoria",
                  "es_perecedero", "unidad_medida", "precio_base", "costo_base",
                  "margen_pct", "iva_pct"] + atributos_producto.COLUMNAS + atributos_producto.COLUMNAS_LOGISTICA
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(filas)

    # INV-22: lista para que el negocio revise las dos marcas (sus cambios
    # van a los CSV de overrides, no al código).
    revision_path = config.SALIDA_DIR / "revision_marcas_logistica.csv"
    with open(revision_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["codigo_item", "nombre", "categoria", "es_refrigerado",
                                          "requiere_frio", "origen_requiere_frio", "fraccion_lineas_decimales",
                                          "se_vende_por_kilo", "origen_se_vende_por_kilo"])
        w.writeheader()
        w.writerows(sorted(revision, key=lambda r: (r["categoria"], r["nombre"])))

    print(f"dim_producto: {len(filas)} productos")
    print(f"  Sin ninguna venta con cantidad>0 (precio/costo quedan NULL): {sin_precio}")
    for col in ["requiere_espacio_bodega", "es_perecedero_estricto", "es_refrigerado",
                "es_papel_higienico_grande", "es_temporada"] + atributos_producto.COLUMNAS_LOGISTICA:
        print(f"  {col}: {sum(1 for r in filas if r[col])}")
    print(f"  Overrides aplicados: requiere_frio {len(overrides_frio)}, se_vende_por_kilo {len(overrides_kilo)}")
    print(f"Guardado en {out_path}")
    print(f"Lista para revisión del negocio: {revision_path} ({len(revision)} productos)")


if __name__ == "__main__":
    construir(completo="--completo" in sys.argv[1:])
