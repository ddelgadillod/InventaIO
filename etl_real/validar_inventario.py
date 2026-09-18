#!/usr/bin/env python3
"""
INV-61 — Doble validación entre el catálogo de ventas (`dim_producto.csv`,
corrida SIN filtrar por inventario todavía) y el inventario físico real a
corte 2025-12-31 (`data/raw_real/inventario/inventarioooo.xlsx`,
`config.INVENTARIO_XLSX`).

Corre DESPUÉS de la primera pasada de `construir_dim_producto.py` y ANTES
de la segunda (la que produce el `dim_producto.csv` final) -- así rompe la
dependencia circular: para decidir qué excluir del catálogo hace falta el
catálogo completo primero, y `construir_fact_inventario_real.py` necesita
el catálogo YA filtrado para no inventar demanda de productos que se
acaban de eliminar.

## Mapeo de bodega -> sucursal

- "ALMACEN PRINCIPAL"      -> PRINCIPAL   (sucursal física real)
- "ALMACEN LA GLORIETA"    -> GLORIETA    (sucursal física real)
- "ALMACEN LA 21"          -> LA 21       (sucursal física real)
- "BODEGA PRINCIPAL"       -> BODEGA_CENTRAL (NO es la sucursal PRINCIPAL:
  es el acopio central -- el producto existe pero no se ha movilizado a
  ninguna sucursal todavía).
- "ALMACEN SABOYA" (1 fila) -- ubicación fuera de las 3 sucursales + bodega
  central conocidas. No se fuerza a ninguna de las anteriores: queda en
  `inventario_ubicaciones_excluidas.csv`.
- Fila de totales del reporte (codigo_item/bodega nulos) -- footer, no un
  registro, se descarta sin auditar.

## Doble validación pedida por el negocio

1. Ítems de VENTAS que no existen en el inventario a corte 2025-12-31 se
   **eliminan del catálogo**: se agregan a `productos_excluidos.csv` con
   motivo `sin_inventario_dic2025` (mismo mecanismo que ya excluía las
   Anchetas de `fact_ventas`) -- la segunda pasada de
   `construir_dim_producto.py` los quita de `dim_producto.csv` (a
   diferencia de las Anchetas, que sí siguen en el catálogo).
2. Ítems del INVENTARIO que no existen en ninguna venta de los 3 años de
   histórico violan la expectativa del negocio ("todos los ítems en
   inventario deberían existir en ventas") -- se documentan en
   `productos_inventario_sin_ventas.csv` (código, nombre, cantidad total)
   y quedan fuera de `fact_inventario.csv` porque no hay una fila válida
   de `dim_producto` para el FK (no se inventa una).
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

import pandas as pd

BODEGA_A_SUCURSAL = {
    "ALMACEN PRINCIPAL": "PRINCIPAL",
    "ALMACEN LA GLORIETA": "GLORIETA",
    "ALMACEN LA 21": "LA 21",
    "BODEGA PRINCIPAL": "BODEGA_CENTRAL",
}


def _float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def cargar_inventario_crudo():
    df = pd.read_excel(config.INVENTARIO_XLSX, sheet_name="Hoja1", header=3)
    df = df.rename(columns={"Referencia": "codigo_item", "Detalle": "nombre",
                             "Bodega": "bodega_cruda", "Cantidad": "cantidad"})
    df = df[df["codigo_item"].notna()].copy()  # footer de totales
    df["codigo_item"] = df["codigo_item"].astype(str).str.strip()
    df["nombre"] = df["nombre"].astype(str).str.strip()
    df["bodega_cruda"] = df["bodega_cruda"].astype(str).str.strip()
    df["cantidad"] = df["cantidad"].map(_float)
    df["sucursal"] = df["bodega_cruda"].map(BODEGA_A_SUCURSAL)

    ubicacion_excluida = df[df["sucursal"].isna()].copy()
    df_valido = (df[df["sucursal"].notna()]
                 .groupby(["codigo_item", "sucursal"], as_index=False)
                 .agg(nombre=("nombre", "first"), cantidad=("cantidad", "sum")))
    return df_valido, ubicacion_excluida


def cargar_catalogo_ventas():
    path = config.SALIDA_DIR / "dim_producto.csv"
    if not path.is_file():
        print("Falta dim_producto.csv -- correr construir_dim_producto.py (primera pasada) primero.")
        sys.exit(1)
    with open(path, newline="", encoding="utf-8-sig") as f:
        return {row["codigo_item"] for row in csv.DictReader(f)}


def fusionar_exclusiones(excl_existentes: list, candidatos: list, motivo: str) -> tuple:
    """Combina las exclusiones ya existentes (de OTROS motivos) con los
    códigos nuevos a excluir por `motivo`, sin duplicar un `codigo_producto`
    que ya esté excluido por un motivo distinto (ej. `ancheta_no_recurrente`)
    -- se conserva el motivo original, no se agrega una segunda fila para el
    mismo código. Idempotente respecto a este `motivo`: `excl_existentes` ya
    debe venir filtrado sin las filas del propio `motivo` (se recalculan
    completas en cada corrida, no se acumulan entre corridas).

    Devuelve (filas_finales, solapan_con_otro_motivo)."""
    ya_excluidos = {r["codigo_producto"] for r in excl_existentes}
    solapan = sorted(set(candidatos) & ya_excluidos)
    nuevas = [{"codigo_producto": c, "motivo": motivo}
              for c in candidatos if c not in ya_excluidos]
    return excl_existentes + nuevas, solapan


def construir():
    if not config.INVENTARIO_XLSX.is_file():
        print(f"Falta {config.INVENTARIO_XLSX}.")
        sys.exit(1)

    codigos_ventas = cargar_catalogo_ventas()
    inv_valido, inv_ubicacion_excluida = cargar_inventario_crudo()
    codigos_inventario = set(inv_valido["codigo_item"].unique())

    # ── Validación 1: ventas sin inventario -> eliminar del catálogo ──
    sin_inventario = sorted(codigos_ventas - codigos_inventario)
    excl_path = config.PRODUCTOS_EXCLUIDOS_CSV
    excl_existentes = []
    if excl_path.is_file():
        with open(excl_path, newline="", encoding="utf-8-sig") as f:
            excl_existentes = [r for r in csv.DictReader(f)
                                if r["motivo"] != "sin_inventario_dic2025"]  # idempotente: recalcula
    # No se duplica la fila si el código ya está excluido por otro motivo
    # (ej. Anchetas) -- se documenta el solape en vez de escribir dos filas
    # para el mismo codigo_producto.
    filas_finales, solapan_con_otro_motivo = fusionar_exclusiones(
        excl_existentes, sin_inventario, "sin_inventario_dic2025")
    with open(excl_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["codigo_producto", "motivo"])
        w.writeheader()
        w.writerows(filas_finales)
    print(f"Validación 1 -- ventas sin inventario (eliminados del catálogo): "
          f"{len(sin_inventario)} de {len(codigos_ventas)} productos -> {excl_path}")
    if solapan_con_otro_motivo:
        print(f"  ({len(solapan_con_otro_motivo)} de esos ya estaban excluidos por otro motivo "
              f"-- ej. Anchetas -- se conserva el motivo original, no se duplica la fila)")

    # ── Validación 2: inventario sin ventas -> documentar y excluir de fact_inventario ──
    sin_ventas = sorted(codigos_inventario - codigos_ventas)
    huerfanos_path = config.SALIDA_DIR / "productos_inventario_sin_ventas.csv"
    resumen = (inv_valido[inv_valido["codigo_item"].isin(sin_ventas)]
               .groupby("codigo_item")
               .agg(nombre=("nombre", "first"), cantidad_total=("cantidad", "sum"))
               .reset_index().sort_values("cantidad_total", ascending=False))
    resumen.to_csv(huerfanos_path, index=False, encoding="utf-8-sig")
    print(f"Validación 2 -- inventario sin ninguna venta en 3 años (excluidos de "
          f"fact_inventario): {len(sin_ventas)} de {len(codigos_inventario)} -> {huerfanos_path}")

    if len(inv_ubicacion_excluida):
        ubic_path = config.SALIDA_DIR / "inventario_ubicaciones_excluidas.csv"
        inv_ubicacion_excluida.to_csv(ubic_path, index=False, encoding="utf-8-sig")
        print(f"Ubicaciones fuera del mapeo conocido (ej. ALMACEN SABOYA): "
              f"{len(inv_ubicacion_excluida)} fila(s) -> {ubic_path}")

    print("\nSiguiente paso: volver a correr construir_dim_producto.py (segunda "
          "pasada) para que dim_producto.csv quede sin los codigos "
          "sin_inventario_dic2025, y luego el resto de la cadena.")


if __name__ == "__main__":
    construir()
