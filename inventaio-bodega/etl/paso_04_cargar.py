"""
InventAI/o — Paso 4: Carga a PostgreSQL
========================================
Carga idempotente al esquema estrella (schema dw + app).
"""
import sys
import pandas as pd
import numpy as np
from pathlib import Path
from sqlalchemy import create_engine, text
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DATA_PROCESSED, DATABASE_URL


def get_engine():
    return create_engine(DATABASE_URL, echo=False)


def truncar_hechos(engine):
    print("   🗑️  Truncando tablas de hechos...")
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE dw.fact_inventario CASCADE"))
        conn.execute(text("TRUNCATE TABLE dw.fact_ventas CASCADE"))
        conn.execute(text("TRUNCATE TABLE dw.dim_evento CASCADE"))


def cargar_dim_tiempo(engine):
    tiempos = pd.read_parquet(DATA_PROCESSED / "tiempos.parquet")
    with engine.begin() as conn:
        tiempos.to_sql("_tmp_tiempo", conn, schema="dw", if_exists="replace", index=False)
        conn.execute(text("""
            INSERT INTO dw.dim_tiempo (fecha, anio, mes, dia, dia_semana, nombre_dia,
                semana_iso, trimestre, es_fin_semana, es_festivo, nombre_festivo, es_quincena, temporada)
            SELECT fecha, anio, mes, dia, dia_semana, nombre_dia,
                semana_iso, trimestre, es_fin_semana, es_festivo, nombre_festivo, es_quincena, temporada
            FROM dw._tmp_tiempo
            ON CONFLICT (fecha) DO UPDATE SET
                es_festivo = EXCLUDED.es_festivo, nombre_festivo = EXCLUDED.nombre_festivo,
                es_quincena = EXCLUDED.es_quincena, temporada = EXCLUDED.temporada
        """))
        conn.execute(text("DROP TABLE IF EXISTS dw._tmp_tiempo"))
    print(f"   📅 dim_tiempo: {len(tiempos)} fechas")


def cargar_dim_producto(engine):
    productos = pd.read_parquet(DATA_PROCESSED / "productos_con_precios.parquet")
    registros = productos.rename(columns={"item_nbr": "codigo_item", "family": "familia",
                                           "class": "clase", "perishable": "es_perecedero"})
    registros = registros[["codigo_item", "familia", "clase", "categoria", "es_perecedero",
                            "precio_base", "costo_base", "margen_pct", "iva_pct"]].copy()
    registros["nombre"] = registros.apply(lambda r: f"{r['categoria']} - Item {r['codigo_item']}", axis=1)
    registros["unidad_medida"] = "unidad"
    registros["es_perecedero"] = registros["es_perecedero"].astype(bool)

    with engine.begin() as conn:
        registros.to_sql("_tmp_producto", conn, schema="dw", if_exists="replace", index=False)
        conn.execute(text("""
            INSERT INTO dw.dim_producto (codigo_item, nombre, familia, clase, categoria,
                es_perecedero, unidad_medida, precio_base, costo_base, margen_pct, iva_pct)
            SELECT codigo_item, nombre, familia, clase, categoria,
                es_perecedero, unidad_medida, precio_base, costo_base, margen_pct, iva_pct
            FROM dw._tmp_producto
            ON CONFLICT (codigo_item) DO UPDATE SET
                precio_base = EXCLUDED.precio_base, costo_base = EXCLUDED.costo_base
        """))
        conn.execute(text("DROP TABLE IF EXISTS dw._tmp_producto"))
    print(f"   📦 dim_producto: {len(registros)} productos")


def cargar_dim_proveedor(engine):
    proveedores = pd.read_parquet(DATA_PROCESSED / "proveedores.parquet")
    proveedores["categorias"] = proveedores["categorias"].apply(
        lambda x: "{" + ",".join(f'"{c}"' for c in x) + "}")
    with engine.begin() as conn:
        for _, row in proveedores.iterrows():
            conn.execute(text("""
                INSERT INTO dw.dim_proveedor (codigo, razon_social, nit, ciudad, telefono,
                    email, lead_time_dias, categorias, calificacion)
                VALUES (:codigo, :razon_social, :nit, :ciudad, :telefono,
                    :email, :lead_time_dias, :categorias, :calificacion)
                ON CONFLICT (codigo) DO UPDATE SET
                    telefono = EXCLUDED.telefono, calificacion = EXCLUDED.calificacion
            """), dict(row))
    print(f"   🏭 dim_proveedor: {len(proveedores)} proveedores")


def cargar_dim_evento(engine):
    eventos = pd.read_parquet(DATA_PROCESSED / "eventos.parquet")
    with engine.begin() as conn:
        for _, row in eventos.iterrows():
            conn.execute(text("""
                INSERT INTO dw.dim_evento (fecha, tipo, nombre, descripcion, ambito, es_transferido)
                VALUES (:fecha, :tipo, :nombre, :descripcion, :ambito, :es_transferido)
            """), dict(row))
    print(f"   🎉 dim_evento: {len(eventos)} eventos")


def _obtener_mapeos(engine):
    with engine.connect() as conn:
        tiempo_map = dict(conn.execute(text("SELECT fecha, id_tiempo FROM dw.dim_tiempo")).fetchall())
        producto_map = dict(conn.execute(text("SELECT codigo_item, id_producto FROM dw.dim_producto")).fetchall())
        sucursal_map = dict(conn.execute(text("SELECT codigo_tienda, id_sucursal FROM dw.dim_sucursal")).fetchall())
        proveedor_map = dict(conn.execute(text(
            "SELECT CAST(REPLACE(codigo, 'PROV-', '') AS INTEGER), id_proveedor FROM dw.dim_proveedor"
        )).fetchall())
    return tiempo_map, producto_map, sucursal_map, proveedor_map


def _mapear_tiempo(df, col_fecha, tiempo_map):
    """Intenta mapear fecha → id_tiempo con múltiples formatos."""
    # Intentar con date objects
    df["id_tiempo"] = df[col_fecha].dt.date.map(
        {k if not hasattr(k, 'isoformat') else k: v for k, v in tiempo_map.items()})
    if df["id_tiempo"].isna().sum() > len(df) * 0.5:
        # Fallback: mapeo directo
        df["id_tiempo"] = df[col_fecha].map(tiempo_map)
    return df


def cargar_fact_ventas(engine):
    ventas = pd.read_parquet(DATA_PROCESSED / "fact_ventas_completa.parquet")
    tiempo_map, producto_map, sucursal_map, proveedor_map = _obtener_mapeos(engine)

    ventas = _mapear_tiempo(ventas, "date", tiempo_map)
    ventas["id_producto"] = ventas["item_nbr"].map(producto_map)
    ventas["id_sucursal"] = ventas["codigo_tienda"].map(sucursal_map)
    ventas["id_proveedor_fk"] = ventas["id_proveedor"].map(proveedor_map)

    antes = len(ventas)
    ventas = ventas.dropna(subset=["id_tiempo", "id_producto", "id_sucursal"])
    if len(ventas) < antes:
        print(f"   ⚠️  {antes - len(ventas)} filas sin mapeo FK eliminadas")

    fact = ventas[["id_producto", "id_sucursal", "id_tiempo", "id_proveedor_fk",
                    "cantidad", "valor_unitario", "valor_total", "costo_unitario",
                    "costo_total", "en_promocion", "es_devolucion"]].rename(
        columns={"id_proveedor_fk": "id_proveedor"}).copy()

    for col in ["id_producto", "id_sucursal", "id_tiempo"]:
        fact[col] = fact[col].astype(int)
    fact["id_proveedor"] = fact["id_proveedor"].astype("Int64")

    print(f"   🧾 Cargando fact_ventas ({len(fact):,} registros)...")
    chunk_size = 50_000
    with engine.begin() as conn:
        for i in tqdm(range(0, len(fact), chunk_size), desc="   fact_ventas"):
            fact.iloc[i:i+chunk_size].to_sql("fact_ventas", conn, schema="dw",
                                              if_exists="append", index=False, method="multi")
    print(f"   ✅ fact_ventas: {len(fact):,} registros cargados")


def cargar_fact_inventario(engine):
    inventario = pd.read_parquet(DATA_PROCESSED / "fact_inventario.parquet")
    tiempo_map, producto_map, sucursal_map, _ = _obtener_mapeos(engine)

    inventario = _mapear_tiempo(inventario, "fecha", tiempo_map)
    inventario["id_producto"] = inventario["item_nbr"].map(producto_map)
    inventario["id_sucursal"] = inventario["codigo_tienda"].map(sucursal_map)

    antes = len(inventario)
    inventario = inventario.dropna(subset=["id_tiempo", "id_producto", "id_sucursal"])
    if len(inventario) < antes:
        print(f"   ⚠️  {antes - len(inventario)} filas sin mapeo FK eliminadas")

    fact = inventario[["id_producto", "id_sucursal", "id_tiempo", "stock_disponible",
                        "stock_minimo", "stock_maximo", "punto_reorden", "dias_cobertura"]].copy()
    for col in ["id_producto", "id_sucursal", "id_tiempo"]:
        fact[col] = fact[col].astype(int)

    print(f"   📦 Cargando fact_inventario ({len(fact):,} registros)...")
    chunk_size = 50_000
    with engine.begin() as conn:
        for i in tqdm(range(0, len(fact), chunk_size), desc="   fact_inventario"):
            fact.iloc[i:i+chunk_size].to_sql("fact_inventario", conn, schema="dw",
                                              if_exists="append", index=False, method="multi")
    print(f"   ✅ fact_inventario: {len(fact):,} registros cargados")


def cargar_usuarios_seed(engine):
    with engine.begin() as conn:
        sucursales = dict(conn.execute(text("SELECT nombre, id_sucursal FROM dw.dim_sucursal")).fetchall())
        usuarios = [
            ("gerente@inventaio.co", "$2b$12$placeholder_hash_gerente", "Carlos Martínez", "gerente", None),
            ("admin.principal@inventaio.co", "$2b$12$placeholder_hash_admin1", "Laura Gómez", "admin_sucursal", sucursales.get("Sucursal Principal")),
            ("admin.norte@inventaio.co", "$2b$12$placeholder_hash_admin2", "Andrés Rivera", "admin_sucursal", sucursales.get("Sucursal Norte")),
            ("admin.sur@inventaio.co", "$2b$12$placeholder_hash_admin3", "María Torres", "admin_sucursal", sucursales.get("Sucursal Sur")),
            ("bodega@inventaio.co", "$2b$12$placeholder_hash_bodega", "Diego Sánchez", "admin_bodega", sucursales.get("Sucursal Principal")),
        ]
        for email, pwd, nombre, rol, suc_id in usuarios:
            conn.execute(text("""
                INSERT INTO app.usuarios (email, password_hash, nombre, rol, id_sucursal)
                VALUES (:email, :pwd, :nombre, :rol, :suc_id)
                ON CONFLICT (email) DO NOTHING
            """), {"email": email, "pwd": pwd, "nombre": nombre, "rol": rol, "suc_id": suc_id})
    print(f"   👤 Usuarios seed: {len(usuarios)} cargados")


def reporte_final(engine):
    print("\n" + "=" * 60)
    print("📊 REPORTE DE CARGA")
    print("=" * 60)
    with engine.connect() as conn:
        for tabla, desc in [("dw.dim_tiempo", "Fechas"), ("dw.dim_producto", "Productos"),
                             ("dw.dim_sucursal", "Sucursales"), ("dw.dim_proveedor", "Proveedores"),
                             ("dw.dim_evento", "Eventos"), ("dw.fact_ventas", "Ventas"),
                             ("dw.fact_inventario", "Inventario"), ("app.usuarios", "Usuarios")]:
            count = conn.execute(text(f"SELECT COUNT(*) FROM {tabla}")).scalar()
            print(f"   {desc:.<35} {count:>10,}")

        total = conn.execute(text("SELECT SUM(valor_total) FROM dw.fact_ventas WHERE NOT es_devolucion")).scalar()
        print(f"\n   💰 Valor total ventas: ${total:,.0f} COP")

        rows = conn.execute(text("""
            SELECT s.nombre, COUNT(*), SUM(v.valor_total)
            FROM dw.fact_ventas v JOIN dw.dim_sucursal s ON v.id_sucursal = s.id_sucursal
            WHERE NOT v.es_devolucion GROUP BY s.nombre ORDER BY SUM(v.valor_total) DESC
        """)).fetchall()
        print("\n   📊 Ventas por sucursal:")
        for nombre, regs, total in rows:
            print(f"      {nombre:.<30} {regs:>10,} regs | ${total:>15,.0f} COP")


def run():
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("   ✅ Conexión a PostgreSQL exitosa")

    truncar_hechos(engine)
    cargar_dim_tiempo(engine)
    cargar_dim_producto(engine)
    cargar_dim_proveedor(engine)
    cargar_dim_evento(engine)
    cargar_fact_ventas(engine)
    cargar_fact_inventario(engine)
    cargar_usuarios_seed(engine)
    reporte_final(engine)


if __name__ == "__main__":
    run()
