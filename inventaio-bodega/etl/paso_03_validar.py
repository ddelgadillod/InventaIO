"""
InventAI/o — Paso 3: Validación de calidad
===========================================
Valida datos procesados antes de cargar a PostgreSQL.
"""
import sys
import pandas as pd
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DATA_PROCESSED, CATEGORIAS_OBJETIVO


class ValidacionError(Exception):
    pass


def check(nombre: str, condicion: bool, detalle: str = ""):
    estado = "✅" if condicion else "❌"
    msg = f"   {estado} {nombre}"
    if detalle:
        msg += f" — {detalle}"
    print(msg)
    if not condicion:
        raise ValidacionError(f"Falló: {nombre}. {detalle}")


def validar_productos(df):
    print("\n   📦 Validando productos...")
    check("Sin nulos en item_nbr", df["item_nbr"].notna().all())
    check("Sin duplicados en item_nbr", not df["item_nbr"].duplicated().any())
    check("Categorías válidas", df["categoria"].isin(CATEGORIAS_OBJETIVO).all())
    check("Precios > 0", (df["precio_base"] > 0).all())
    check("Costos > 0 y < precio", ((df["costo_base"] > 0) & (df["costo_base"] < df["precio_base"])).all())
    check(f"~200 productos ({len(df)})", 150 <= len(df) <= 250)
    check(f"≥12 categorías ({df['categoria'].nunique()})", df["categoria"].nunique() >= 12)


def validar_proveedores(df):
    print("\n   🏭 Validando proveedores...")
    check("10 proveedores", len(df) == 10)
    check("Sin duplicados en codigo", not df["codigo"].duplicated().any())
    check("Lead times 3-15", df["lead_time_dias"].between(3, 15).all())


def validar_fact_ventas(df):
    print("\n   🧾 Validando fact_ventas...")
    check("Sin nulos en PKs", df[["date", "codigo_tienda", "item_nbr"]].notna().all().all())
    check("Solo 3 sucursales", set(df["codigo_tienda"].unique()) == {1, 2, 3})
    check("Valores unitarios > 0", (df["valor_unitario"] > 0).all())
    check(f"≥500K registros ({len(df):,})", len(df) >= 500_000)

    dist = df.groupby("codigo_tienda")["cantidad"].sum()
    ratio = dist.get(1, 0) / dist.get(2, 1) if dist.get(2, 1) > 0 else 0
    check(f"Principal ~5x Norte (ratio: {ratio:.1f})", 2.5 <= ratio <= 8.0)


def validar_fact_inventario(df):
    print("\n   📦 Validando fact_inventario...")
    check("Sin nulos en PKs", df[["fecha", "codigo_tienda", "item_nbr"]].notna().all().all())
    check("Stock ≥ 0", (df["stock_disponible"] >= 0).all())
    check("stock_minimo < stock_maximo", (df["stock_minimo"] < df["stock_maximo"]).all())
    check("punto_reorden > stock_minimo", (df["punto_reorden"] > df["stock_minimo"]).all())


def validar_tiempos(df):
    print("\n   📅 Validando dim_tiempo...")
    check("Sin nulos en fecha", df["fecha"].notna().all())
    check("Sin duplicados", not df["fecha"].duplicated().any())
    check(f"Festivos presentes ({df['es_festivo'].sum()})", df["es_festivo"].sum() > 10)
    check(f"Quincenas presentes ({df['es_quincena'].sum()})", df["es_quincena"].sum() > 20)


def run():
    errores = []
    validadores = [
        ("productos_con_precios.parquet", validar_productos),
        ("proveedores.parquet", validar_proveedores),
        ("fact_ventas_completa.parquet", validar_fact_ventas),
        ("fact_inventario.parquet", validar_fact_inventario),
        ("tiempos.parquet", validar_tiempos),
    ]
    for archivo, validador in validadores:
        try:
            df = pd.read_parquet(DATA_PROCESSED / archivo)
            validador(df)
        except FileNotFoundError:
            errores.append(f"Archivo no encontrado: {archivo}")
            print(f"   ❌ {archivo} no existe")
        except ValidacionError as e:
            errores.append(str(e))

    print("\n" + "-" * 40)
    if errores:
        print(f"   ⚠️  {len(errores)} validación(es) fallaron:")
        for e in errores:
            print(f"      • {e}")
        return False
    else:
        print("   ✅ Todas las validaciones pasaron")
        return True


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
