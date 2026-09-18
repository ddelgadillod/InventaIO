"""
InventAI/o — ML Service Configuration
INV-20: rutas configurables por variable de entorno (mismo patrón que
api/core/config.py). Los defaults asumen que se corre localmente desde
ml_service/ (repo checkout completo al lado); en Docker se sobreescriben
vía docker-compose.yml (montajes de solo lectura de models/ y data/).
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Modelos de Nivel 1 (INV-17), cargados LOCALMENTE -- no desde MLflow
    # en runtime (decisión documentada en docs/INV-20-ml-service.md).
    MODELOS_DIR: str = str(BASE_DIR.parent / "models")

    # Extracto local de matriz_as_of.parquet (INV-15), generado por
    # scripts/generar_datos_locales.py -- ver ese script y el docstring
    # de prediccion/features.py.
    FEATURES_SNAPSHOT_PATH: str = str(BASE_DIR / "data" / "features_snapshot.parquet")

    # Los modelos solo se entrenaron para demanda acumulada a 15 días
    # hábiles (HORIZONTE en 07_matriz_as_of.ipynb / 08_nivel1_demanda.ipynb) --
    # no hay forma honesta de generalizar sin reentrenar.
    HORIZONTE_SOPORTADO: int = 15

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
