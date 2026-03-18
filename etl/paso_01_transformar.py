"""
InventAI/o — Paso 1: Transformar datos de Favorita
===================================================
Entrada:  data/raw/train.csv, items.csv, stores.csv, holidays_events.csv
Salida:   data/processed/ventas_filtradas.parquet
          data/processed/productos_mapeados.parquet
          data/processed/tiempos.parquet
"""
import sys
import pandas as pd
import numpy as np
from pathlib import Path
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (
    DATA_RAW, DATA_PROCESSED, RANDOM_SEED, SUCURSALES,
    FAMILIA_A_CATEGORIA, CATEGORIAS_OBJETIVO, PRODUCTOS_POR_CATEGORIA,
    FESTIVOS_COLOMBIA,
)


def cargar_favorita():
    """Carga los CSVs de Favorita desde data/raw/."""
    print("📂 Cargando CSVs de Favorita...")

    items = pd.read_csv(DATA_RAW / "items.csv")
    stores = pd.read_csv(DATA_RAW / "stores.csv")
    holidays = pd.read_csv(DATA_RAW / "holidays_events.csv")

    print("   ⏳ Leyendo train.csv (esto puede tomar unos minutos)...")
    train_chunks = pd.read_csv(
        DATA_RAW / "train.csv",
        dtype={"id": "int64", "store_nbr": "int16", "item_nbr": "int32",
               "unit_sales": "float32", "onpromotion": "object"},
        parse_dates=["date"],
        chunksize=5_000_000,
    )
    return items, stores, holidays, train_chunks


def seleccionar_tiendas(stores: pd.DataFrame) -> dict:
    """Selecciona 3 tiendas de Favorita para mapear a nuestras sucursales."""
    np.random.seed(RANDOM_SEED)
    tipo_a = stores[stores["type"] == "A"]["store_nbr"].values
    tipo_d = stores[stores["type"].isin(["D", "C"])]["store_nbr"].values

    tienda_principal = np.random.choice(tipo_a, 1)[0]
    tiendas_pequenas = np.random.choice(tipo_d, 2, replace=False)

    mapeo = {
        int(tienda_principal): 1,
        int(tiendas_pequenas[0]): 2,
        int(tiendas_pequenas[1]): 3,
    }
    print(f"   🏪 Tiendas seleccionadas: {list(mapeo.keys())}")
    print(f"      → Principal (store {tienda_principal}), "
          f"Norte (store {tiendas_pequenas[0]}), Sur (store {tiendas_pequenas[1]})")
    return mapeo


def seleccionar_productos(items: pd.DataFrame) -> pd.DataFrame:
    """Selecciona ~200 productos balanceados por categoría."""
    np.random.seed(RANDOM_SEED)
    items["categoria"] = items["family"].map(FAMILIA_A_CATEGORIA).fillna("Abarrotes")
    items_filtrados = items[items["categoria"].isin(CATEGORIAS_OBJETIVO)].copy()

    seleccionados = []
    for cat, n in PRODUCTOS_POR_CATEGORIA.items():
        pool = items_filtrados[items_filtrados["categoria"] == cat]
        if len(pool) == 0:
            print(f"   ⚠️  Sin productos para '{cat}', saltando.")
            continue
        muestra = pool.sample(n=min(n, len(pool)), random_state=RANDOM_SEED)
        seleccionados.append(muestra)

    productos = pd.concat(seleccionados, ignore_index=True)
    print(f"   📦 Productos seleccionados: {len(productos)} en "
          f"{productos['categoria'].nunique()} categorías")
    return productos


def filtrar_ventas(train_chunks, mapeo_tiendas: dict, item_nbrs: set) -> pd.DataFrame:
    """Filtra train.csv: solo tiendas y productos seleccionados."""
    tiendas_fav = set(mapeo_tiendas.keys())
    frames = []
    print("   🔍 Filtrando ventas...")
    for chunk in tqdm(train_chunks, desc="   Procesando chunks"):
        mask = chunk["store_nbr"].isin(tiendas_fav) & chunk["item_nbr"].isin(item_nbrs)
        filtered = chunk[mask].copy()
        if len(filtered) > 0:
            filtered["codigo_tienda"] = filtered["store_nbr"].map(mapeo_tiendas)
            frames.append(filtered)

    ventas = pd.concat(frames, ignore_index=True)
    print(f"   ✅ Ventas filtradas: {len(ventas):,} registros")
    return ventas


def aplicar_factor_volumen(ventas: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza ventas para que Sucursal Principal tenga ~5x el volumen de las demás.
    Primero calcula el ratio natural entre tiendas, luego aplica corrección.
    """
    factores_objetivo = {code: info["factor_volumen"] for code, info in SUCURSALES.items()}

    # Calcular volumen natural por sucursal
    vol_natural = ventas.groupby("codigo_tienda")["unit_sales"].sum()
    vol_norte = vol_natural.get(2, 1)
    vol_sur = vol_natural.get(3, 1)
    vol_base = (vol_norte + vol_sur) / 2  # promedio de las pequeñas
    vol_principal = vol_natural.get(1, vol_base)

    # Ratio natural (sin intervención)
    ratio_natural = vol_principal / vol_base if vol_base > 0 else 1.0
    print(f"      Ratio natural Principal/pequeñas: {ratio_natural:.1f}x")

    # Factor de corrección: queremos 5x final
    objetivo = factores_objetivo[1]  # 5.0
    factor_correccion = objetivo / ratio_natural
    print(f"      Factor de corrección aplicado: {factor_correccion:.2f}")

    # Aplicar solo a la Principal
    mask_principal = ventas["codigo_tienda"] == 1
    ventas.loc[mask_principal, "unit_sales"] = (
        ventas.loc[mask_principal, "unit_sales"] * factor_correccion
    ).round(0)

    # Verificar resultado
    vol_post = ventas.groupby("codigo_tienda")["unit_sales"].sum()
    ratio_post = vol_post.get(1, 0) / ((vol_post.get(2, 1) + vol_post.get(3, 1)) / 2)
    print(f"      Ratio final: {ratio_post:.1f}x")
    print(f"   📊 Factor de volumen normalizado (Principal ×{objetivo:.0f})")

    return ventas


def construir_dim_tiempo(ventas: pd.DataFrame) -> pd.DataFrame:
    """Construye dim_tiempo con festivos colombianos y quincenas."""
    fechas = pd.DataFrame({"fecha": ventas["date"].dt.date.unique()})
    fechas["fecha"] = pd.to_datetime(fechas["fecha"])
    fechas = fechas.sort_values("fecha").reset_index(drop=True)

    fechas["anio"] = fechas["fecha"].dt.year
    fechas["mes"] = fechas["fecha"].dt.month
    fechas["dia"] = fechas["fecha"].dt.day
    fechas["dia_semana"] = fechas["fecha"].dt.weekday
    fechas["nombre_dia"] = fechas["fecha"].dt.day_name()
    fechas["semana_iso"] = fechas["fecha"].dt.isocalendar().week.astype(int)
    fechas["trimestre"] = fechas["fecha"].dt.quarter
    fechas["es_fin_semana"] = fechas["dia_semana"].isin([5, 6])

    festivos_map = {pd.Timestamp(k): v for k, v in FESTIVOS_COLOMBIA.items()}
    fechas["es_festivo"] = fechas["fecha"].isin(festivos_map.keys())
    fechas["nombre_festivo"] = fechas["fecha"].map(festivos_map)

    ultimo_dia = fechas["fecha"] + pd.offsets.MonthEnd(0)
    fechas["es_quincena"] = (fechas["dia"] == 15) | (fechas["fecha"] == ultimo_dia)

    def clasificar_temporada(row):
        m, d = row["mes"], row["dia"]
        if m == 12 or (m == 1 and d <= 6):
            return "navidad"
        if m in [1, 2] and d > 6:
            return "escolar_inicio"
        if m in [3, 4]:
            return "semana_santa"
        if m in [6, 7]:
            return "vacaciones_mitad"
        if m == 10 and d >= 20:
            return "halloween"
        if m == 11:
            return "black_friday"
        return "regular"

    fechas["temporada"] = fechas.apply(clasificar_temporada, axis=1)
    print(f"   📅 dim_tiempo: {len(fechas)} fechas "
          f"({fechas['fecha'].min().date()} → {fechas['fecha'].max().date()})")
    return fechas


def run():
    """Ejecuta el paso 1 completo."""
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)

    items, stores, holidays, train_chunks = cargar_favorita()
    mapeo_tiendas = seleccionar_tiendas(stores)
    productos = seleccionar_productos(items)
    item_nbrs = set(productos["item_nbr"].values)
    ventas = filtrar_ventas(train_chunks, mapeo_tiendas, item_nbrs)
    ventas = aplicar_factor_volumen(ventas)
    tiempos = construir_dim_tiempo(ventas)

    ventas.to_parquet(DATA_PROCESSED / "ventas_filtradas.parquet", index=False)
    productos.to_parquet(DATA_PROCESSED / "productos_mapeados.parquet", index=False)
    tiempos.to_parquet(DATA_PROCESSED / "tiempos.parquet", index=False)

    print(f"\n   💾 Guardados en {DATA_PROCESSED}/")
    print(f"      ventas_filtradas.parquet   ({len(ventas):,} filas)")
    print(f"      productos_mapeados.parquet ({len(productos)} filas)")
    print(f"      tiempos.parquet            ({len(tiempos)} filas)")


if __name__ == "__main__":
    run()
