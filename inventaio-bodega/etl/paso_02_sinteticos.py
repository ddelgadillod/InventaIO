"""
InventAI/o — Paso 2: Generar datos sintéticos
==============================================
Genera precios, proveedores e inventario diario coherente con ventas.
Salida: productos_con_precios, proveedores, fact_ventas_completa,
        fact_inventario, eventos (todos .parquet)
"""
import sys
import pandas as pd
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (
    DATA_PROCESSED, RANDOM_SEED, SUCURSALES,
    MARGENES_POR_CATEGORIA, PRECIOS_BASE_RANGO,
    PROVEEDORES_SEED, INVENTARIO_PARAMS, FESTIVOS_COLOMBIA,
)


def generar_precios(productos: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED)
    precios = []
    for _, prod in productos.iterrows():
        cat = prod["categoria"]
        p_min, p_max = PRECIOS_BASE_RANGO.get(cat, (2000, 20000))
        margen = MARGENES_POR_CATEGORIA.get(cat, 0.30)
        precio = int(round(rng.integers(p_min, p_max) / 50) * 50)
        costo = round(precio * (1 - margen), 2)
        exento = cat in ["Frutas y verduras", "Huevos", "Cárnicos", "Avícola", "Mariscos", "Lácteos"]
        precios.append({
            "item_nbr": prod["item_nbr"], "precio_base": precio,
            "costo_base": costo, "margen_pct": round(margen * 100, 2),
            "iva_pct": 0.0 if exento else 19.0,
        })
    productos = productos.merge(pd.DataFrame(precios), on="item_nbr", how="left")
    print(f"   💰 Precios generados: ${productos['precio_base'].min():,.0f} – ${productos['precio_base'].max():,.0f} COP")
    return productos


def generar_proveedores() -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED)
    prov = pd.DataFrame(PROVEEDORES_SEED)
    prov["telefono"] = [f"+57 {rng.integers(300,320)}{rng.integers(1000000,9999999)}" for _ in range(len(prov))]
    prov["email"] = [f"ventas@{r['razon_social'].split()[0].lower()}.com.co" for _, r in prov.iterrows()]
    prov["calificacion"] = rng.uniform(3.5, 5.0, size=len(prov)).round(2)
    print(f"   🏭 Proveedores generados: {len(prov)}")
    return prov


def asignar_proveedor(productos: pd.DataFrame, proveedores: pd.DataFrame) -> dict:
    rng = np.random.default_rng(RANDOM_SEED)
    mapeo = {}
    for _, prod in productos.iterrows():
        cat = prod["categoria"]
        candidatos = proveedores[proveedores["categorias"].apply(lambda cats: cat in cats)]
        if len(candidatos) > 0:
            idx = rng.choice(candidatos.index)
            mapeo[prod["item_nbr"]] = int(candidatos.loc[idx, "codigo"].replace("PROV-", ""))
        else:
            mapeo[prod["item_nbr"]] = 1
    return mapeo


def generar_fact_ventas(ventas: pd.DataFrame, productos: pd.DataFrame, mapeo_prov: dict) -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED)
    precios_df = productos[["item_nbr", "precio_base", "costo_base"]].copy()
    ventas = ventas.merge(precios_df, on="item_nbr", how="left")

    variacion = rng.normal(1.0, 0.03, size=len(ventas))
    ventas["valor_unitario"] = (ventas["precio_base"] * variacion).round(2)
    ventas["costo_unitario"] = ventas["costo_base"]
    ventas["cantidad"] = ventas["unit_sales"].clip(lower=0).round(0)
    ventas["es_devolucion"] = ventas["unit_sales"] < 0
    ventas.loc[ventas["es_devolucion"], "cantidad"] = ventas.loc[ventas["es_devolucion"], "unit_sales"].abs().round(0)
    ventas["valor_total"] = (ventas["cantidad"] * ventas["valor_unitario"]).round(2)
    ventas["costo_total"] = (ventas["cantidad"] * ventas["costo_unitario"]).round(2)
    ventas["id_proveedor"] = ventas["item_nbr"].map(mapeo_prov)
    ventas["en_promocion"] = ventas["onpromotion"].fillna("False").astype(str).str.lower() == "true"

    result = ventas[["date", "codigo_tienda", "item_nbr", "cantidad", "valor_unitario",
                      "valor_total", "costo_unitario", "costo_total", "en_promocion",
                      "es_devolucion", "id_proveedor"]].copy()
    print(f"   🧾 fact_ventas: {len(result):,} registros, ${result['valor_total'].sum():,.0f} COP")
    return result


def generar_fact_inventario(ventas: pd.DataFrame, productos: pd.DataFrame, tiempos: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED)
    params = INVENTARIO_PARAMS
    print("   📦 Generando fact_inventario...")

    fechas_sorted = sorted(tiempos["fecha"].unique())
    items = productos["item_nbr"].unique()
    sucursales = [1, 2, 3]

    ventas_agg = ventas.groupby(["item_nbr", "codigo_tienda"])["cantidad"].agg(["sum", "count"]).reset_index()
    ventas_agg["demanda_diaria"] = (ventas_agg["sum"] / ventas_agg["count"]).clip(lower=0.5)
    demanda_map = {(r["item_nbr"], r["codigo_tienda"]): r["demanda_diaria"] for _, r in ventas_agg.iterrows()}

    registros = []
    total = len(items) * len(sucursales)
    count = 0

    for item in items:
        for suc in sucursales:
            count += 1
            if count % 100 == 0:
                print(f"      Progreso: {count}/{total}")

            demanda = demanda_map.get((item, suc), 1.0)
            stock_min = max(1, round(demanda * params["dias_stock_minimo"]))
            stock_max = max(stock_min + 5, round(demanda * params["dias_stock_maximo"]))
            punto_reorden = max(stock_min + 1, round(demanda * params["dias_punto_reorden"]))
            stock = round(stock_max * rng.uniform(0.6, 0.8))

            ventas_item = ventas[(ventas["item_nbr"] == item) & (ventas["codigo_tienda"] == suc)].set_index("date")["cantidad"]

            for fecha in fechas_sorted:
                fecha_ts = pd.Timestamp(fecha)
                venta_dia = ventas_item.get(fecha_ts, 0)
                if pd.isna(venta_dia):
                    venta_dia = 0

                stock = max(0, stock - venta_dia)
                if stock <= punto_reorden:
                    stock += max(0, round(stock_max * rng.uniform(0.8, 0.95) - stock))

                variacion = rng.normal(0, demanda * params["variacion_stock_pct"])
                stock = max(0, round(stock + variacion))
                dias_cob = round(stock / demanda, 1) if demanda > 0 else 999.0

                registros.append({
                    "fecha": fecha_ts, "item_nbr": item, "codigo_tienda": suc,
                    "stock_disponible": stock, "stock_minimo": stock_min,
                    "stock_maximo": stock_max, "punto_reorden": punto_reorden,
                    "dias_cobertura": dias_cob,
                })

    inventario = pd.DataFrame(registros)
    print(f"   ✅ fact_inventario: {len(inventario):,} registros")
    return inventario


def generar_eventos(tiempos: pd.DataFrame) -> pd.DataFrame:
    eventos = []
    for fecha_str, nombre in FESTIVOS_COLOMBIA.items():
        fecha = pd.Timestamp(fecha_str)
        if fecha in tiempos["fecha"].values:
            eventos.append({"fecha": fecha, "tipo": "festivo", "nombre": nombre,
                            "descripcion": f"Festivo nacional: {nombre}",
                            "ambito": "nacional", "es_transferido": False})
    df = pd.DataFrame(eventos).drop_duplicates(subset=["fecha", "nombre"])
    print(f"   🎉 Eventos: {len(df)}")
    return df


def run():
    print("   Cargando intermedios del paso 1...")
    ventas = pd.read_parquet(DATA_PROCESSED / "ventas_filtradas.parquet")
    productos = pd.read_parquet(DATA_PROCESSED / "productos_mapeados.parquet")
    tiempos = pd.read_parquet(DATA_PROCESSED / "tiempos.parquet")

    productos = generar_precios(productos)
    proveedores = generar_proveedores()
    mapeo_prov = asignar_proveedor(productos, proveedores)
    fact_ventas = generar_fact_ventas(ventas, productos, mapeo_prov)
    fact_inventario = generar_fact_inventario(fact_ventas, productos, tiempos)
    eventos = generar_eventos(tiempos)

    productos.to_parquet(DATA_PROCESSED / "productos_con_precios.parquet", index=False)
    proveedores.to_parquet(DATA_PROCESSED / "proveedores.parquet", index=False)
    fact_ventas.to_parquet(DATA_PROCESSED / "fact_ventas_completa.parquet", index=False)
    fact_inventario.to_parquet(DATA_PROCESSED / "fact_inventario.parquet", index=False)
    eventos.to_parquet(DATA_PROCESSED / "eventos.parquet", index=False)

    print(f"\n   💾 Archivos sintéticos guardados en {DATA_PROCESSED}/")


if __name__ == "__main__":
    run()
