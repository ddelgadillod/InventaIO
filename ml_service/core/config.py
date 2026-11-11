"""
InventAI/o — ML Service Configuration
INV-20: rutas y conexión configurables por variable de entorno (mismo patrón
que api/core/config.py, mismas variables POSTGRES_*). Los defaults asumen que
se corre localmente desde ml_service/ con el repo completo al lado; en Docker
se sobreescriben vía docker-compose.yml.
"""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent

# INV-66 (H1, H7): la contraseña de desarrollo está en el repositorio público; solo vale con ENTORNO=desarrollo
CLAVE_BD_DESARROLLO = "inventaio_pass_2025"


class Settings(BaseSettings):
    # INV-66 (H1): sin la variable se asume producción, y entonces la contraseña de la base es obligatoria
    ENTORNO: Literal["desarrollo", "staging", "produccion"] = "produccion"

    # Modelos de Nivel 1 (INV-17) y sus parámetros de features, cargados
    # LOCALMENTE -- no desde MLflow en runtime (docs/INV-20-ml-service.md).
    MODELOS_DIR: str = str(BASE_DIR.parent / "models")

    # Bodega de datos (INV-20 fix): el servicio calcula las features leyendo
    # dw.* en Postgres, la misma base que usa api/.
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "inventaio"
    POSTGRES_USER: str = "inventaio_user"
    POSTGRES_PASSWORD: str = CLAVE_BD_DESARROLLO
    # El calendario (días hábiles + dim_tiempo) es global: se relee de la
    # bodega cada tantos segundos para tomar cargas nuevas sin reiniciar.
    CACHE_CALENDARIO_SEGUNDOS: int = 600

    # Los modelos solo se entrenaron para demanda acumulada a 15 días
    # hábiles (HORIZONTE en 07_matriz_as_of.ipynb / 08_nivel1_demanda.ipynb) --
    # no hay forma honesta de generalizar sin reentrenar.
    HORIZONTE_SOPORTADO: int = 15

    # INV-22: políticas de la recomendación de transferencias (P1-P15),
    # versionadas en el repo y validadas al arrancar.
    POLITICAS_TRANSFERENCIAS_PATH: str = str(BASE_DIR / "transferencias" / "politicas_inv22.json")
    # INV-21: políticas de la recomendación de compras (B1-B13), igual patrón.
    POLITICAS_COMPRAS_PATH: str = str(BASE_DIR / "compras" / "politicas_inv21.json")

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @model_validator(mode="after")
    def _secretos_fuera_de_desarrollo(self) -> "Settings":
        """INV-66 (CA 1): fuera de desarrollo no arranca con la contraseña vacía o la del repositorio."""
        if self.ENTORNO != "desarrollo" and self.POSTGRES_PASSWORD in ("", CLAVE_BD_DESARROLLO):
            raise ValueError(f"ENTORNO={self.ENTORNO}: POSTGRES_PASSWORD no está definida o es la del repositorio")
        return self

    class Config:
        env_file = ".env"
        extra = "ignore"
        # INV-66: el error de validación no copia las variables de entrada, que traen los secretos, al log
        hide_input_in_errors = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
