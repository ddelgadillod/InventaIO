#!/usr/bin/env python3
"""
INV-60 — Carga los CSV de data/processed_real/ al Postgres del esquema
estrella (database/init.sql, ya migrado), reemplazando por completo el
dataset simulado de InventaIO.

NO se ejecutó en esta sesión (no hay Postgres disponible en este
entorno -- se va a levantar en otro servidor). Queda listo para
correrse allá -- ver docs/INV-60-tutorial-migracion.md para el
procedimiento completo. Resumen:

    pip install psycopg2-binary
    DATABASE_URL=postgresql://usuario:clave@host:5432/inventaio \
        python cargar_postgres.py

Pasos:
  1. Corre database/init.sql contra la base (psql -f database/init.sql).
  2. TRUNCATE de todas las tablas dw.* (reemplazo total, no fusión --
     ver docs/INV-60-compatibilidad-datos.md).
  3. Carga dimensiones (dim_tiempo, dim_sucursal, dim_proveedor,
     dim_producto, dim_evento) con COPY.
  4. Resuelve FKs por lookup (codigo_item/nombre_sucursal/fecha/
     codigo_proveedor -> id_*) y carga fact_ventas / fact_inventario
     en chunks con COPY.
"""
import csv
import io
import os
import sys
from pathlib import Path

try:
    import psycopg2
except ImportError:
    print("Falta psycopg2 (pip install psycopg2-binary).", file=sys.stderr)
    sys.exit(1)

import config  # noqa: E402

TABLAS_HECHOS_Y_EVENTO = [
    "dw.fact_inventario", "dw.fact_ventas", "dw.dim_evento",
]
TABLAS_DIMENSION = [
    "dw.dim_producto", "dw.dim_sucursal", "dw.dim_proveedor", "dw.dim_tiempo",
]


def get_conn():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("Falta la variable de entorno DATABASE_URL.", file=sys.stderr)
        sys.exit(1)
    return psycopg2.connect(dsn)


def truncar_todo(conn):
    with conn.cursor() as cur:
        todas = ", ".join(TABLAS_HECHOS_Y_EVENTO + TABLAS_DIMENSION)
        cur.execute(f"TRUNCATE TABLE {todas} RESTART IDENTITY CASCADE")
    conn.commit()
    print("Tablas truncadas (reemplazo total del dataset simulado).")


def copy_csv(conn, csv_path: Path, tabla: str, columnas: list):
    with open(csv_path, newline="", encoding="utf-8-sig") as f, conn.cursor() as cur:
        reader = csv.reader(f)
        next(reader)  # descarta encabezado del CSV, se pasa columnas explícito
        buf = io.StringIO()
        w = csv.writer(buf)
        for row in reader:
            w.writerow(row)
        buf.seek(0)
        cols = ", ".join(columnas)
        cur.copy_expert(f"COPY {tabla} ({cols}) FROM STDIN WITH (FORMAT csv)", buf)
    conn.commit()


def cargar_dim_tiempo(conn):
    copy_csv(conn, config.SALIDA_DIR / "dim_tiempo.csv", "dw.dim_tiempo", [
        "fecha", "anio", "mes", "dia", "dia_semana", "nombre_dia", "semana_iso",
        "trimestre", "es_fin_semana", "es_festivo", "nombre_festivo",
        "es_puente_festivo", "es_quincena", "temporada",
    ])
    print("dim_tiempo cargada.")


def cargar_dim_sucursal(conn):
    with open(config.SALIDA_DIR / "dim_sucursal.csv", newline="", encoding="utf-8-sig") as f, \
         conn.cursor() as cur:
        for row in csv.DictReader(f):
            cur.execute(
                """INSERT INTO dw.dim_sucursal
                   (codigo_tienda, nombre, ciudad, departamento, tipo, cluster, factor_volumen)
                   VALUES (%s, %s, NULLIF(%s,''), NULLIF(%s,''), %s, %s, %s)""",
                (row["codigo_tienda"], row["nombre"], row["ciudad"], row["departamento"],
                 row["tipo"], row["cluster"] or None, row["factor_volumen"] or None),
            )
    conn.commit()
    print("dim_sucursal cargada.")


def cargar_dim_proveedor(conn):
    with open(config.SALIDA_DIR / "dim_proveedor.csv", newline="", encoding="utf-8-sig") as f, \
         conn.cursor() as cur:
        for row in csv.DictReader(f):
            categorias = "{" + ",".join(f'"{c}"' for c in row["categorias"].split("|")) + "}"
            cur.execute(
                """INSERT INTO dw.dim_proveedor
                   (codigo, razon_social, nit, ciudad, telefono, email,
                    lead_time_dias, categorias, calificacion)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (row["codigo"], row["razon_social"], row["nit"], row["ciudad"],
                 row["telefono"], row["email"], row["lead_time_dias"],
                 categorias, row["calificacion"]),
            )
    conn.commit()
    print("dim_proveedor cargada.")


def cargar_dim_producto(conn):
    copy_csv(conn, config.SALIDA_DIR / "dim_producto.csv", "dw.dim_producto", [
        "codigo_item", "nombre", "familia", "clase", "categoria",
        "es_perecedero", "unidad_medida", "precio_base", "costo_base",
        "margen_pct", "iva_pct",
    ])
    print("dim_producto cargada.")


def cargar_dim_evento(conn):
    copy_csv(conn, config.SALIDA_DIR / "dim_evento.csv", "dw.dim_evento", [
        "fecha", "tipo", "nombre", "descripcion", "ambito", "es_transferido",
    ])
    print("dim_evento cargada.")


def _obtener_mapeos(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT fecha, id_tiempo FROM dw.dim_tiempo")
        tiempo_map = {row[0].isoformat(): row[1] for row in cur.fetchall()}
        cur.execute("SELECT codigo_item, id_producto FROM dw.dim_producto")
        producto_map = dict(cur.fetchall())
        cur.execute("SELECT nombre, id_sucursal FROM dw.dim_sucursal")
        sucursal_map = dict(cur.fetchall())
        cur.execute("SELECT codigo, id_proveedor FROM dw.dim_proveedor")
        proveedor_map = dict(cur.fetchall())
    return tiempo_map, producto_map, sucursal_map, proveedor_map


def cargar_fact_ventas(conn, chunk_size=50_000):
    tiempo_map, producto_map, sucursal_map, proveedor_map = _obtener_mapeos(conn)
    path = config.SALIDA_DIR / "fact_ventas.csv"

    n_ok, n_sin_fk = 0, 0
    with open(path, newline="", encoding="utf-8-sig") as f, conn.cursor() as cur:
        buf = io.StringIO()
        w = csv.writer(buf)
        pendientes = 0

        def flush():
            nonlocal buf, pendientes
            if pendientes == 0:
                return
            buf.seek(0)
            cur.copy_expert(
                """COPY dw.fact_ventas
                   (id_producto, id_sucursal, id_tiempo, id_proveedor, cantidad,
                    valor_unitario, valor_total, costo_unitario, costo_total,
                    en_promocion, es_devolucion)
                   FROM STDIN WITH (FORMAT csv)""", buf)
            buf = io.StringIO()
            w_holder[0] = csv.writer(buf)
            pendientes = 0

        w_holder = [w]
        for row in csv.DictReader(f):
            id_producto = producto_map.get(row["codigo_item"])
            id_sucursal = sucursal_map.get(row["sucursal"])
            id_tiempo = tiempo_map.get(row["fecha"])
            if id_producto is None or id_sucursal is None or id_tiempo is None:
                n_sin_fk += 1
                continue
            id_proveedor = proveedor_map.get(row["codigo_proveedor"], "")
            w_holder[0].writerow([
                id_producto, id_sucursal, id_tiempo, id_proveedor or "",
                row["cantidad"], row["valor_unitario"], row["valor_total"],
                row["costo_unitario"], row["costo_total"],
                row["en_promocion"], row["es_devolucion"],
            ])
            pendientes += 1
            n_ok += 1
            if pendientes >= chunk_size:
                flush()
        flush()
    conn.commit()
    print(f"fact_ventas cargada: {n_ok:,} filas ({n_sin_fk} sin FK completa, omitidas).")


def cargar_fact_inventario(conn, chunk_size=50_000):
    tiempo_map, producto_map, sucursal_map, _ = _obtener_mapeos(conn)
    path = config.SALIDA_DIR / "fact_inventario.csv"

    n_ok, n_sin_fk = 0, 0
    with open(path, newline="", encoding="utf-8-sig") as f, conn.cursor() as cur:
        buf = io.StringIO()
        w_holder = [csv.writer(buf)]
        pendientes = 0

        def flush():
            nonlocal buf, pendientes
            if pendientes == 0:
                return
            buf.seek(0)
            cur.copy_expert(
                """COPY dw.fact_inventario
                   (id_producto, id_sucursal, id_tiempo, stock_disponible,
                    stock_minimo, stock_maximo, punto_reorden, dias_cobertura)
                   FROM STDIN WITH (FORMAT csv)""", buf)
            buf = io.StringIO()
            w_holder[0] = csv.writer(buf)
            pendientes = 0

        for row in csv.DictReader(f):
            id_producto = producto_map.get(row["codigo_item"])
            id_sucursal = sucursal_map.get(row["sucursal"])
            id_tiempo = tiempo_map.get(row["fecha"])
            if id_producto is None or id_sucursal is None or id_tiempo is None:
                n_sin_fk += 1
                continue
            w_holder[0].writerow([
                id_producto, id_sucursal, id_tiempo, row["stock_disponible"],
                row["stock_minimo"], row["stock_maximo"], row["punto_reorden"],
                row["dias_cobertura"],
            ])
            pendientes += 1
            n_ok += 1
            if pendientes >= chunk_size:
                flush()
        flush()
    conn.commit()
    print(f"fact_inventario cargada: {n_ok:,} filas ({n_sin_fk} sin FK completa, omitidas).")


def reporte_final(conn):
    print("\n" + "=" * 60)
    print("REPORTE DE CARGA")
    print("=" * 60)
    with conn.cursor() as cur:
        for tabla in ["dw.dim_tiempo", "dw.dim_producto", "dw.dim_sucursal",
                      "dw.dim_proveedor", "dw.dim_evento", "dw.fact_ventas",
                      "dw.fact_inventario"]:
            cur.execute(f"SELECT COUNT(*) FROM {tabla}")
            print(f"  {tabla:<25} {cur.fetchone()[0]:>12,}")


def run():
    conn = get_conn()
    truncar_todo(conn)
    cargar_dim_tiempo(conn)
    cargar_dim_sucursal(conn)
    cargar_dim_proveedor(conn)
    cargar_dim_producto(conn)
    cargar_dim_evento(conn)
    cargar_fact_ventas(conn)
    cargar_fact_inventario(conn)
    reporte_final(conn)
    conn.close()


if __name__ == "__main__":
    run()
