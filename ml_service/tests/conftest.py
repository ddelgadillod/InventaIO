"""
INV-20 — Fixtures compartidos.

- `modelo_loader`: los modelos REALES de models/ (no mocks para el motor).
- `bodega_falsa` / `app_client`: una bodega en memoria con la misma interfaz
  que prediccion.bodega.BodegaPostgres, para probar el endpoint sin Postgres.
- `bodega_real`: la bodega en Postgres configurada por POSTGRES_* (ver
  core/config.py). Los tests marcados `bodega` se saltan con un mensaje claro
  si no hay conexión o la bodega está vacía (p. ej. en un clon sin cargar).
"""
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import pytest

from core.modelo_loader import ModeloLoader
from prediccion.features import Calendario

BASE_DIR = Path(__file__).resolve().parent.parent
MODELOS_DIR = BASE_DIR.parent / "models"
MATRIZ_AS_OF = BASE_DIR.parent / "data" / "processed_real" / "matriz_as_of.parquet"


@pytest.fixture(scope="session")
def modelo_loader():
    if not (MODELOS_DIR / "nivel1_intermitente.joblib").is_file():
        pytest.skip(f"Faltan los modelos en {MODELOS_DIR} -- correr notebooks/exportar_modelos_nivel1_v2.py (INV-17).")
    loader = ModeloLoader(MODELOS_DIR)
    loader.cargar_todos()
    return loader


def marcas_calendario(fechas: pd.DatetimeIndex, cierres=()) -> pd.DataFrame:
    """Marcas de dim_tiempo mínimas para un rango de fechas (sin eventos salvo los tramos del mes)."""
    return pd.DataFrame({
        "dia": fechas.day,
        "es_festivo": False, "es_puente_festivo": False, "es_semana_santa": False, "es_periodo_prima": False,
        "es_quincena": (fechas.day == 15) | fechas.is_month_end,
        "bloque_diciembre": "ninguno",
        "es_cierre_programado": fechas.isin(pd.DatetimeIndex(cierres)),
    }, index=fechas)


class BodegaFalsa:
    """Bodega en memoria: 3 productos en PRINCIPAL (uno estable, uno
    intermitente y uno sin historia suficiente) y una sucursal no física."""

    def __init__(self):
        habiles = pd.date_range("2025-01-01", "2025-06-30", freq="D")
        todas = pd.date_range("2025-01-01", "2025-09-30", freq="D")
        self._calendario = Calendario(habiles=habiles, marcas=marcas_calendario(todas, cierres=["2025-07-04"]))
        rng = np.random.default_rng(0)
        self._ventas = {
            ("P1", "PRINCIPAL"): pd.Series(rng.poisson(20, len(habiles)).astype(float) + 1, index=habiles),
            ("P2", "PRINCIPAL"): pd.Series(3.0, index=habiles[::4]),
            ("P3", "PRINCIPAL"): pd.Series(1.0, index=habiles[-5:]),
        }
        base = {"requiere_espacio_bodega": False, "es_perecedero_estricto": False, "es_refrigerado": False,
                "es_papel_higienico_grande": False, "es_temporada": False, "categoria": "Abarrotes"}
        self._productos = {cod: {"id_producto": i, "codigo_item": cod, "nombre": f"PRODUCTO {cod}", **base}
                           for i, cod in enumerate(["P1", "P2", "P3"], start=1)}
        self._sucursales = {"PRINCIPAL": {"id_sucursal": 1, "nombre": "PRINCIPAL", "tipo": "principal"},
                            "SIN_SUCURSAL": {"id_sucursal": 4, "nombre": "SIN_SUCURSAL", "tipo": "sin_terminal"}}

    def calendario(self) -> Calendario:
        return self._calendario

    def producto(self, codigo_item=None, id_producto=None) -> Optional[dict]:
        if codigo_item is not None:
            return self._productos.get(codigo_item)
        return next((p for p in self._productos.values() if p["id_producto"] == id_producto), None)

    def sucursal(self, nombre=None, id_sucursal=None) -> Optional[dict]:
        if nombre is not None:
            return self._sucursales.get(nombre)
        return next((s for s in self._sucursales.values() if s["id_sucursal"] == id_sucursal), None)

    def ventas_diarias(self, codigo_item, sucursal, hasta) -> pd.Series:
        serie = self._ventas.get((codigo_item, sucursal), pd.Series(dtype=float))
        return serie[serie.index <= pd.Timestamp(hasta)]

    def disponible(self) -> bool:
        return True


@pytest.fixture()
def bodega_falsa():
    return BodegaFalsa()


@pytest.fixture()
def app_client(modelo_loader, bodega_falsa):
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app) as client:
        app.state.bodega = bodega_falsa
        yield client


@pytest.fixture(scope="session")
def bodega_real():
    from core.config import get_settings
    from core.database import crear_engine
    from prediccion.bodega import BodegaPostgres

    settings = get_settings()
    bodega = BodegaPostgres(crear_engine(settings.DATABASE_URL))
    if not bodega.disponible():
        pytest.skip(f"Sin conexión a la bodega ({settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}) -- "
                    "levantar Postgres y cargarla con etl_real/cargar_postgres.py.")
    try:
        bodega.calendario()
    except LookupError as e:
        pytest.skip(f"Bodega vacía: {e}")
    return bodega


@pytest.fixture()
def app_client_real(modelo_loader, bodega_real):
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app) as client:
        app.state.bodega = bodega_real
        yield client
