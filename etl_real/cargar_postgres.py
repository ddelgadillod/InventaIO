#!/usr/bin/env python3
"""
INV-60 — Carga los CSV de data/processed_real/ al Postgres del esquema
estrella (database/init.sql), reemplazando por completo el dataset
simulado de InventaIO.

    pip install -r requirements.txt
    psql "$DATABASE_URL" -f ../database/init.sql
    DATABASE_URL=postgresql://usuario:clave@host:5432/inventaio python cargar_postgres.py

INV-20 — estrategia de carga reescrita (la versión anterior nunca se había
corrido contra un Postgres real y tenía tres problemas):

  1. Hacía TRUNCATE ... RESTART IDENTITY CASCADE sobre las dimensiones. El
     CASCADE también vaciaba app.usuarios y app.config_alertas (tienen FK a
     dw.dim_sucursal), así que cada recarga borraba los usuarios, y los
     id_* cambiaban de una carga a otra. Ahora las dimensiones se actualizan
     por su clave de negocio (INSERT ... ON CONFLICT DO UPDATE) y se borran
     solo las filas que ya no están en el CSV: los id_* se conservan y
     app.* no se toca. Los hechos, dim_evento y producto_proveedor (que
     nadie referencia) sí se vacían y se recargan completos.
  2. Una fila de hechos sin producto/sucursal/fecha en las dimensiones se
     omitía con un simple print. Ahora aborta la carga, salvo que se pase
     --permitir-huerfanas (entonces se omite y se reporta).
  3. Cada tabla hacía su propio commit: un error a mitad de camino dejaba
     la base a medio cargar. Ahora todo va en una sola transacción.

Además carga dw.producto_proveedor y las columnas nuevas de dim_tiempo,
dim_producto y dim_sucursal, y al final compara el conteo de cada tabla
contra su CSV.
"""
import argparse
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

CHUNK = 50_000

DIMENSIONES = [
    # (tabla, CSV, clave de negocio, columnas del CSV que se cargan)
    ("dw.dim_tiempo", "dim_tiempo.csv", "fecha", [
        "fecha", "anio", "mes", "dia", "dia_semana", "nombre_dia", "semana_iso",
        "trimestre", "es_fin_semana", "es_festivo", "nombre_festivo",
        "es_puente_festivo", "es_quincena", "temporada",
        "es_semana_santa", "es_periodo_prima", "bloque_diciembre", "es_cierre_programado",
    ]),
    ("dw.dim_sucursal", "dim_sucursal.csv", "codigo_tienda", [
        "codigo_tienda", "nombre", "ciudad", "departamento", "tipo", "cluster",
        "factor_volumen", "volumen_real_cop",
    ]),
    ("dw.dim_proveedor", "dim_proveedor.csv", "codigo", [
        "codigo", "razon_social", "nit", "ciudad", "telefono", "email",
        "lead_time_dias", "categorias", "calificacion",
    ]),
    ("dw.dim_producto", "dim_producto.csv", "codigo_item", [
        "codigo_item", "nombre", "familia", "clase", "categoria",
        "es_perecedero", "unidad_medida", "precio_base", "costo_base",
        "margen_pct", "iva_pct",
        "volumen_cm3", "peso_g", "tamano_inferido", "requiere_espacio_bodega",
        "es_perecedero_estricto", "es_refrigerado", "rollos_paquete",
        "es_papel_higienico_grande", "es_temporada",
        "requiere_frio", "se_vende_por_kilo",  # INV-22
    ]),
]
# Filas de dimensión que no se borran aunque ya no estén en el CSV, porque
# las referencia una tabla de la aplicación (app.*), que esta carga no toca.
REFERENCIAS_APP = {
    "dw.dim_sucursal": ("app.usuarios", "id_sucursal"),
}
TABLAS_RECARGA_COMPLETA = ["dw.fact_ventas", "dw.fact_inventario", "dw.producto_proveedor", "dw.dim_evento"]


class CargaAbortada(Exception):
    pass


def get_conn():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("Falta la variable de entorno DATABASE_URL.", file=sys.stderr)
        sys.exit(1)
    return psycopg2.connect(dsn)


def contar_filas_csv(path: Path) -> int:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return sum(1 for _ in csv.DictReader(f))


def _transformar(tabla: str, row: dict) -> dict:
    if tabla == "dw.dim_proveedor":
        # "Abarrotes|Bebidas" -> literal de arreglo TEXT[] de Postgres
        row = dict(row, categorias="{" + ",".join(f'"{c}"' for c in row["categorias"].split("|")) + "}")
    return row


def _copy(cur, tabla: str, columnas: list, filas) -> int:
    """COPY de un iterable de filas (listas). Un campo vacío se carga como NULL."""
    n, buf = 0, io.StringIO()
    w = csv.writer(buf)
    sql = f"COPY {tabla} ({', '.join(columnas)}) FROM STDIN WITH (FORMAT csv)"
    for fila in filas:
        w.writerow(fila)
        n += 1
        if n % CHUNK == 0:
            buf.seek(0)
            cur.copy_expert(sql, buf)
            buf = io.StringIO()
            w = csv.writer(buf)
    buf.seek(0)
    cur.copy_expert(sql, buf)
    return n


def actualizar_dimension(cur, tabla: str, csv_nombre: str, clave: str, columnas: list) -> dict:
    """Inserta o actualiza por clave de negocio y borra lo que ya no está en el CSV."""
    path = config.SALIDA_DIR / csv_nombre
    tmp = "tmp_" + tabla.split(".")[1]
    cols = ", ".join(columnas)
    cur.execute(f"CREATE TEMP TABLE {tmp} ON COMMIT DROP AS SELECT {cols} FROM {tabla} WITH NO DATA")
    with open(path, newline="", encoding="utf-8-sig") as f:
        n = _copy(cur, tmp, columnas,
                  ([_transformar(tabla, row)[c] for c in columnas] for row in csv.DictReader(f)))

    cur.execute(f"SELECT COUNT(*) FROM {tabla} d JOIN {tmp} t ON t.{clave} = d.{clave}")
    existentes = cur.fetchone()[0]
    asignaciones = ", ".join(f"{c} = EXCLUDED.{c}" for c in columnas if c != clave)
    cur.execute(f"INSERT INTO {tabla} ({cols}) SELECT {cols} FROM {tmp} "
                f"ON CONFLICT ({clave}) DO UPDATE SET {asignaciones}")

    condicion_app = ""
    if tabla in REFERENCIAS_APP:
        tabla_app, col_app = REFERENCIAS_APP[tabla]
        pk = f"id_{tabla.split('_', 1)[1]}"
        condicion_app = f" AND NOT EXISTS (SELECT 1 FROM {tabla_app} a WHERE a.{col_app} = d.{pk})"
    cur.execute(f"DELETE FROM {tabla} d WHERE NOT EXISTS "
                f"(SELECT 1 FROM {tmp} t WHERE t.{clave} = d.{clave}){condicion_app}")
    borradas = cur.rowcount
    resumen = {"csv": n, "nuevas": n - existentes, "actualizadas": existentes, "borradas": borradas}
    print(f"{tabla}: {resumen}")
    return resumen


def cargar_dim_evento(cur) -> int:
    columnas = ["fecha", "tipo", "nombre", "descripcion", "ambito", "es_transferido"]
    with open(config.SALIDA_DIR / "dim_evento.csv", newline="", encoding="utf-8-sig") as f:
        n = _copy(cur, "dw.dim_evento", columnas, ([row[c] for c in columnas] for row in csv.DictReader(f)))
    print(f"dw.dim_evento: {n:,} filas")
    return n


def obtener_mapeos(cur) -> dict:
    cur.execute("SELECT fecha, id_tiempo FROM dw.dim_tiempo")
    tiempo = {fecha.isoformat(): id_ for fecha, id_ in cur.fetchall()}
    cur.execute("SELECT codigo_item, id_producto FROM dw.dim_producto")
    producto = dict(cur.fetchall())
    cur.execute("SELECT nombre, id_sucursal FROM dw.dim_sucursal")
    sucursal = dict(cur.fetchall())
    cur.execute("SELECT codigo, id_proveedor FROM dw.dim_proveedor")
    proveedor = dict(cur.fetchall())
    return {"tiempo": tiempo, "producto": producto, "sucursal": sucursal, "proveedor": proveedor}


def _resolver_hechos(path: Path, mapeos: dict, columnas_valor: list, huerfanas: dict, con_proveedor: bool):
    """Genera las filas del hecho con sus FK resueltas; cuenta en `huerfanas`
    las que no encuentran producto, sucursal o fecha (y no las emite)."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            ids = {
                "producto": mapeos["producto"].get(row["codigo_item"]),
                "sucursal": mapeos["sucursal"].get(row["sucursal"]),
                "tiempo": mapeos["tiempo"].get(row["fecha"]),
            }
            faltan = [k for k, v in ids.items() if v is None]
            if faltan:
                for k in faltan:
                    huerfanas[k] = huerfanas.get(k, 0) + 1
                if len(huerfanas.setdefault("_ejemplos", [])) < 5:
                    huerfanas["_ejemplos"].append((row["codigo_item"], row["sucursal"], row["fecha"]))
                continue
            fila = [ids["producto"], ids["sucursal"], ids["tiempo"]]
            if con_proveedor:
                id_prov = mapeos["proveedor"].get(row["codigo_proveedor"])
                if id_prov is None:
                    huerfanas["proveedor_sin_match"] = huerfanas.get("proveedor_sin_match", 0) + 1
                fila.append(id_prov if id_prov is not None else "")
            yield fila + [row[c] for c in columnas_valor]


def cargar_hecho(cur, tabla: str, csv_nombre: str, columnas_valor: list, mapeos: dict,
                 con_proveedor: bool, permitir_huerfanas: bool) -> int:
    huerfanas = {}
    columnas = ["id_producto", "id_sucursal", "id_tiempo"] + (["id_proveedor"] if con_proveedor else []) + columnas_valor
    n = _copy(cur, tabla, columnas,
              _resolver_hechos(config.SALIDA_DIR / csv_nombre, mapeos, columnas_valor, huerfanas, con_proveedor))
    sin_fk = {k: v for k, v in huerfanas.items() if k in ("producto", "sucursal", "tiempo")}
    print(f"{tabla}: {n:,} filas" + (f" | sin FK: {sin_fk}, ejemplos {huerfanas['_ejemplos']}" if sin_fk else "")
          + (f" | proveedor sin match: {huerfanas['proveedor_sin_match']:,}" if "proveedor_sin_match" in huerfanas else ""))
    if sin_fk and not permitir_huerfanas:
        raise CargaAbortada(f"{tabla}: filas sin producto/sucursal/fecha en las dimensiones {sin_fk} "
                            f"(ejemplos {huerfanas['_ejemplos']}). Revisar el ETL o usar --permitir-huerfanas.")
    return n


def cargar_producto_proveedor(cur, mapeos: dict) -> int:
    sin_match = 0

    def filas():
        nonlocal sin_match
        with open(config.SALIDA_DIR / "producto_proveedor.csv", newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                id_p = mapeos["producto"].get(row["codigo_item"])
                id_v = mapeos["proveedor"].get(row["codigo_proveedor"])
                if id_p is None or id_v is None:
                    sin_match += 1
                    continue
                yield [id_p, id_v]

    n = _copy(cur, "dw.producto_proveedor", ["id_producto", "id_proveedor"], filas())
    print(f"dw.producto_proveedor: {n:,} filas" + (f" ({sin_match} sin producto/proveedor)" if sin_match else ""))
    if sin_match:
        raise CargaAbortada(f"producto_proveedor: {sin_match} filas no encuentran producto o proveedor")
    return n


def verificar_conteos(cur, esperados: dict):
    """Compara el conteo final de cada tabla contra lo esperado del CSV."""
    print("\n" + "=" * 60 + "\nREPORTE DE CARGA (base vs. CSV)\n" + "=" * 60)
    errores = []
    for tabla, esperado in esperados.items():
        cur.execute(f"SELECT COUNT(*) FROM {tabla}")
        real = cur.fetchone()[0]
        estado = "OK" if real == esperado else "DIFIERE"
        print(f"  {tabla:<25} base {real:>12,} | CSV {esperado:>12,}  {estado}")
        if real != esperado:
            errores.append(tabla)
    if errores:
        raise CargaAbortada(f"conteos distintos al CSV en {errores}")


def run(permitir_huerfanas: bool = False):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"TRUNCATE TABLE {', '.join(TABLAS_RECARGA_COMPLETA)} RESTART IDENTITY")
            esperados = {}
            for tabla, csv_nombre, clave, columnas in DIMENSIONES:
                actualizar_dimension(cur, tabla, csv_nombre, clave, columnas)
                esperados[tabla] = contar_filas_csv(config.SALIDA_DIR / csv_nombre)
            esperados["dw.dim_evento"] = cargar_dim_evento(cur)
            mapeos = obtener_mapeos(cur)
            esperados["dw.producto_proveedor"] = cargar_producto_proveedor(cur, mapeos)
            n_ventas = cargar_hecho(cur, "dw.fact_ventas", "fact_ventas.csv",
                                    ["cantidad", "valor_unitario", "valor_total", "costo_unitario",
                                     "costo_total", "en_promocion", "es_devolucion"],
                                    mapeos, con_proveedor=True, permitir_huerfanas=permitir_huerfanas)
            n_inv = cargar_hecho(cur, "dw.fact_inventario", "fact_inventario.csv",
                                 ["stock_disponible", "stock_minimo", "stock_maximo", "punto_reorden", "dias_cobertura"],
                                 mapeos, con_proveedor=False, permitir_huerfanas=permitir_huerfanas)
            # Con --permitir-huerfanas se esperan las filas efectivamente cargadas
            esperados["dw.fact_ventas"] = n_ventas if permitir_huerfanas else contar_filas_csv(config.SALIDA_DIR / "fact_ventas.csv")
            esperados["dw.fact_inventario"] = n_inv if permitir_huerfanas else contar_filas_csv(config.SALIDA_DIR / "fact_inventario.csv")
            verificar_conteos(cur, esperados)
        conn.commit()
        print("\nCarga confirmada (una sola transacción).")
    except CargaAbortada as e:
        conn.rollback()
        print(f"\nCARGA ABORTADA, la base queda como estaba: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Carga data/processed_real/*.csv al esquema dw de Postgres.")
    ap.add_argument("--permitir-huerfanas", action="store_true",
                    help="Omite (y reporta) las filas de hechos sin producto/sucursal/fecha en vez de abortar.")
    run(permitir_huerfanas=ap.parse_args().permitir_huerfanas)
