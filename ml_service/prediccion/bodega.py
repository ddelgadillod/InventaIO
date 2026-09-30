"""
InventAI/o — ML Service: acceso a la bodega de datos (Postgres, esquema dw)
INV-20 (fix): de dónde salen los datos para calcular las features. Solo
lectura. `BodegaPostgres` es la implementación real; los tests usan una
bodega en memoria con la misma interfaz (tests/conftest.py).

Claves de negocio (codigo_item, nombre de sucursal) o SERIAL de Postgres
(id_producto, id_sucursal): el servicio acepta las dos y responde con ambas.
"""
import time
from typing import Optional, Protocol

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from prediccion.features import Calendario

COLUMNAS_ATRIBUTOS = ["requiere_espacio_bodega", "es_perecedero_estricto", "es_refrigerado",
                      "es_papel_higienico_grande", "es_temporada"]

SQL_HABILES = text("""
    SELECT t.fecha FROM dw.dim_tiempo t
    WHERE EXISTS (SELECT 1 FROM dw.fact_ventas v
                  WHERE v.id_tiempo = t.id_tiempo AND NOT v.es_devolucion AND v.cantidad > 0)
    ORDER BY t.fecha
""")
SQL_MARCAS = text("""
    SELECT fecha, dia, es_festivo, es_puente_festivo, es_semana_santa, es_periodo_prima,
           es_quincena, bloque_diciembre, es_cierre_programado
    FROM dw.dim_tiempo ORDER BY fecha
""")
SQL_PRODUCTO = """
    SELECT id_producto, codigo_item, nombre, categoria, {atributos}
    FROM dw.dim_producto WHERE {condicion}
""".replace("{atributos}", ", ".join(COLUMNAS_ATRIBUTOS))
SQL_SUCURSAL = "SELECT id_sucursal, nombre, tipo FROM dw.dim_sucursal WHERE {condicion}"
SQL_VENTAS = text("""
    SELECT fecha, unidades FROM dw.v_ventas_diarias_netas
    WHERE codigo_item = :codigo AND sucursal = :sucursal AND fecha <= :hasta
    ORDER BY fecha
""")

# INV-22: lecturas por lote para la recomendación de transferencias (unas
# pocas consultas para todo el catálogo, nunca una por par).
COLUMNAS_LOGISTICA = ["es_perecedero_estricto", "requiere_frio", "se_vende_por_kilo"]
SQL_FECHA_INVENTARIO = text("""
    SELECT MAX(t.fecha) AS fecha FROM dw.fact_inventario fi JOIN dw.dim_tiempo t ON t.id_tiempo = fi.id_tiempo
""")
SQL_INVENTARIO = """
    SELECT p.codigo_item, s.nombre AS sucursal, s.tipo AS tipo_sucursal, SUM(fi.stock_disponible) AS stock
    FROM dw.fact_inventario fi
    JOIN dw.dim_tiempo t ON t.id_tiempo = fi.id_tiempo
    JOIN dw.dim_producto p ON p.id_producto = fi.id_producto
    JOIN dw.dim_sucursal s ON s.id_sucursal = fi.id_sucursal
    WHERE t.fecha = :fecha {filtro}
    GROUP BY p.codigo_item, s.nombre, s.tipo
"""
SQL_PRODUCTOS = """
    SELECT id_producto, codigo_item, nombre, categoria, {columnas} FROM dw.dim_producto {filtro}
""".replace("{columnas}", ", ".join(dict.fromkeys(COLUMNAS_ATRIBUTOS + COLUMNAS_LOGISTICA)))
SQL_SUCURSALES = text("SELECT id_sucursal, nombre, tipo FROM dw.dim_sucursal ORDER BY id_sucursal")
SQL_VENTAS_LOTE = text("""
    SELECT codigo_item, sucursal, fecha, unidades FROM dw.v_ventas_diarias_netas
    WHERE codigo_item = ANY(:codigos) AND sucursal = ANY(:sucursales) AND fecha <= :hasta
    ORDER BY codigo_item, sucursal, fecha
""")


class Bodega(Protocol):
    def calendario(self) -> Calendario: ...
    def producto(self, codigo_item: Optional[str] = None, id_producto: Optional[int] = None) -> Optional[dict]: ...
    def sucursal(self, nombre: Optional[str] = None, id_sucursal: Optional[int] = None) -> Optional[dict]: ...
    def ventas_diarias(self, codigo_item: str, sucursal: str, hasta) -> pd.Series: ...
    def disponible(self) -> bool: ...
    # INV-22
    def fecha_inventario(self) -> pd.Timestamp: ...
    def inventario(self, fecha, codigos: Optional[list] = None) -> list: ...
    def ventas_diarias_lote(self, codigos: list, sucursales: list, hasta) -> dict: ...
    def productos(self, codigos: Optional[list] = None) -> dict: ...
    def sucursales(self) -> list: ...


class BodegaPostgres:
    """Lee dw.* con SQLAlchemy. El calendario (días hábiles + dim_tiempo) es
    global y se cachea `cache_segundos`; lo demás se consulta por petición."""

    def __init__(self, engine: Engine, cache_segundos: int = 600):
        self.engine = engine
        self.cache_segundos = cache_segundos
        self._calendario: Optional[Calendario] = None
        self._calendario_ts = 0.0

    def calendario(self) -> Calendario:
        if self._calendario is None or time.monotonic() - self._calendario_ts > self.cache_segundos:
            with self.engine.connect() as con:
                habiles = pd.read_sql(SQL_HABILES, con, parse_dates=["fecha"])["fecha"]
                marcas = pd.read_sql(SQL_MARCAS, con, parse_dates=["fecha"]).set_index("fecha")
            if habiles.empty:
                raise LookupError("la bodega no tiene ventas cargadas (dw.fact_ventas vacía)")
            self._calendario = Calendario(habiles=pd.DatetimeIndex(habiles), marcas=marcas)
            self._calendario_ts = time.monotonic()
        return self._calendario

    def _una_fila(self, sql: str, params: dict) -> Optional[dict]:
        with self.engine.connect() as con:
            fila = con.execute(text(sql), params).mappings().first()
        return dict(fila) if fila else None

    def producto(self, codigo_item=None, id_producto=None) -> Optional[dict]:
        if codigo_item is not None:
            return self._una_fila(SQL_PRODUCTO.replace("{condicion}", "codigo_item = :v"), {"v": codigo_item})
        return self._una_fila(SQL_PRODUCTO.replace("{condicion}", "id_producto = :v"), {"v": id_producto})

    def sucursal(self, nombre=None, id_sucursal=None) -> Optional[dict]:
        if nombre is not None:
            return self._una_fila(SQL_SUCURSAL.replace("{condicion}", "nombre = :v"), {"v": nombre})
        return self._una_fila(SQL_SUCURSAL.replace("{condicion}", "id_sucursal = :v"), {"v": id_sucursal})

    def ventas_diarias(self, codigo_item: str, sucursal: str, hasta) -> pd.Series:
        with self.engine.connect() as con:
            df = pd.read_sql(SQL_VENTAS, con, params={"codigo": codigo_item, "sucursal": sucursal,
                                                      "hasta": pd.Timestamp(hasta).date()},
                             parse_dates=["fecha"])
        return df.set_index("fecha")["unidades"].astype(float)

    # ── INV-22: lecturas por lote ─────────────────────────────────────────

    def fecha_inventario(self) -> pd.Timestamp:
        """Fecha de la foto más reciente de dw.fact_inventario."""
        with self.engine.connect() as con:
            fecha = con.execute(SQL_FECHA_INVENTARIO).scalar()
        if fecha is None:
            raise LookupError("la bodega no tiene inventario cargado (dw.fact_inventario vacía)")
        return pd.Timestamp(fecha)

    def inventario(self, fecha, codigos: Optional[list] = None) -> list:
        """stock_disponible por producto y ubicación en la foto de `fecha`
        (todas las ubicaciones, con su tipo). Sin `codigos`, todo el catálogo."""
        params = {"fecha": pd.Timestamp(fecha).date()}
        filtro = ""
        if codigos is not None:
            filtro, params["codigos"] = "AND p.codigo_item = ANY(:codigos)", list(codigos)
        with self.engine.connect() as con:
            filas = con.execute(text(SQL_INVENTARIO.replace("{filtro}", filtro)), params).mappings().all()
        return [{**fila, "stock": float(fila["stock"])} for fila in filas]

    def ventas_diarias_lote(self, codigos: list, sucursales: list, hasta) -> dict:
        """Las series de venta diaria de muchos pares en una sola consulta:
        {(codigo_item, sucursal): Serie} con el mismo formato que ventas_diarias."""
        if not codigos or not sucursales:
            return {}
        with self.engine.connect() as con:
            df = pd.read_sql(SQL_VENTAS_LOTE, con, params={"codigos": list(codigos), "sucursales": list(sucursales),
                                                           "hasta": pd.Timestamp(hasta).date()},
                             parse_dates=["fecha"])
        if df.empty:
            return {}
        # La consulta viene ordenada por par: se corta en tramos contiguos
        # (mucho más rápido que un groupby con miles de grupos).
        codigo, sucursal = df["codigo_item"].to_numpy(), df["sucursal"].to_numpy()
        fechas = pd.DatetimeIndex(df["fecha"], name="fecha")
        unidades = df["unidades"].to_numpy(dtype=float)
        cortes = np.flatnonzero((codigo[1:] != codigo[:-1]) | (sucursal[1:] != sucursal[:-1])) + 1
        inicios, fines = np.r_[0, cortes], np.r_[cortes, len(df)]
        return {(codigo[i], sucursal[i]): pd.Series(unidades[i:j], index=fechas[i:j], name="unidades")
                for i, j in zip(inicios, fines)}

    def productos(self, codigos: Optional[list] = None) -> dict:
        """codigo_item -> atributos del modelo y marcas de logística. Los
        códigos que no existen simplemente no aparecen."""
        params, filtro = {}, ""
        if codigos is not None:
            filtro, params["codigos"] = "WHERE codigo_item = ANY(:codigos)", list(codigos)
        with self.engine.connect() as con:
            filas = con.execute(text(SQL_PRODUCTOS.replace("{filtro}", filtro)), params).mappings().all()
        return {fila["codigo_item"]: dict(fila) for fila in filas}

    def sucursales(self) -> list:
        with self.engine.connect() as con:
            return [dict(fila) for fila in con.execute(SQL_SUCURSALES).mappings().all()]

    def disponible(self) -> bool:
        try:
            with self.engine.connect() as con:
                con.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
