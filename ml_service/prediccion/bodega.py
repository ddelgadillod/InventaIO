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


class Bodega(Protocol):
    def calendario(self) -> Calendario: ...
    def producto(self, codigo_item: Optional[str] = None, id_producto: Optional[int] = None) -> Optional[dict]: ...
    def sucursal(self, nombre: Optional[str] = None, id_sucursal: Optional[int] = None) -> Optional[dict]: ...
    def ventas_diarias(self, codigo_item: str, sucursal: str, hasta) -> pd.Series: ...
    def disponible(self) -> bool: ...


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

    def disponible(self) -> bool:
        try:
            with self.engine.connect() as con:
                con.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
