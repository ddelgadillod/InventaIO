"""
INV-20 — Fixtures compartidos. Los tests usan los modelos y datos
REALES generados por scripts/generar_datos_locales.py (no mocks para el
motor de predicción) -- si no corriste ese script antes, estos fixtures
se saltan con un mensaje claro, no con un traceback confuso.
"""
from pathlib import Path

import pandas as pd
import pytest

from core.modelo_loader import ModeloLoader
from prediccion.features import FeatureStore

BASE_DIR = Path(__file__).resolve().parent.parent
MODELOS_DIR = BASE_DIR.parent / "models"
SNAPSHOT_PATH = BASE_DIR / "data" / "features_snapshot.parquet"
CASOS_PRUEBA_PATH = BASE_DIR / "tests" / "fixtures" / "casos_prueba.parquet"


@pytest.fixture(scope="session")
def modelo_loader():
    if not (MODELOS_DIR / "nivel1_intermitente.joblib").is_file():
        pytest.skip(f"Faltan los modelos en {MODELOS_DIR} -- correr notebooks/exportar_modelos_nivel1.py (INV-17).")
    loader = ModeloLoader(MODELOS_DIR)
    loader.cargar_todos()
    return loader


@pytest.fixture(scope="session")
def feature_store():
    if not SNAPSHOT_PATH.is_file():
        pytest.skip(f"Falta {SNAPSHOT_PATH} -- correr scripts/generar_datos_locales.py primero.")
    return FeatureStore(SNAPSHOT_PATH)


@pytest.fixture(scope="session")
def casos_prueba() -> pd.DataFrame:
    if not CASOS_PRUEBA_PATH.is_file():
        pytest.skip(f"Falta {CASOS_PRUEBA_PATH} -- correr scripts/generar_datos_locales.py primero.")
    return pd.read_parquet(CASOS_PRUEBA_PATH)


@pytest.fixture()
def app_client(modelo_loader, feature_store):
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app) as client:
        yield client
