"""
InventAI/o — Core API Configuration
Reads settings from environment variables / .env file.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "inventaio"
    POSTGRES_USER: str = "inventaio_user"
    POSTGRES_PASSWORD: str = "inventaio_pass_2025"

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # JWT
    JWT_SECRET_KEY: str = "inventaio-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ML Service (INV-23): recomendaciones de compras y transferencias
    ML_SERVICE_URL: str = "http://localhost:8001"
    ML_SERVICE_TIMEOUT_SEGUNDOS: float = 120
    ML_CACHE_TTL_SEGUNDOS: int = 21600

    # Chat (INV-36): el agente es interno (nlp-agent:8002, nunca publicado) y
    # solo se llega a él por /api/chat/, con el token del usuario (N3, D12)
    NLP_AGENT_URL: str = "http://localhost:8002"
    CHAT_TIMEOUT_S: float = 120            # tiempo total de un flujo (criterio 4)
    CHAT_ESPERA_INICIO_S: float = 15       # espera del primer evento del agente (X4)
    CHAT_MAX_FLUJOS: int = 1               # flujos a la vez en total; 1 por usuario siempre (X3)
    CHAT_RETRY_AFTER_S: int = 10
    CHAT_MARGEN_TOKEN_S: int = 120         # 401 si al token le queda menos (X6)
    CHAT_MAX_MENSAJES: int = 13            # 6 turnos y la pregunta (X2)
    CHAT_MAX_CARACTERES_MENSAJE: int = 2000
    CHAT_MAX_CARACTERES_TOTAL: int = 16000

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
