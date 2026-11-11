"""
InventAI/o — Core API Configuration
Reads settings from environment variables / .env file.
"""
from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings

# INV-66 (H1, H7): los valores de desarrollo están en el repositorio público; solo valen con ENTORNO=desarrollo
CLAVE_JWT_DESARROLLO = "inventaio-secret-key-change-in-production"
CLAVE_BD_DESARROLLO = "inventaio_pass_2025"
GENERAR_CLAVE = 'python -c "import secrets; print(secrets.token_urlsafe(48))"'


class Settings(BaseSettings):
    # INV-66 (H1): sin la variable se asume producción, y entonces los secretos son obligatorios
    ENTORNO: Literal["desarrollo", "staging", "produccion"] = "produccion"

    # Database
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "inventaio"
    POSTGRES_USER: str = "inventaio_user"
    POSTGRES_PASSWORD: str = CLAVE_BD_DESARROLLO

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # JWT
    JWT_SECRET_KEY: str = CLAVE_JWT_DESARROLLO
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # INV-66 (H5): orígenes permitidos, separados por comas. Vacía, sin CORS: el navegador llega por el
    # mismo origen, por el proxy de Vite en desarrollo y por Nginx en la imagen web
    CORS_ORIGENES: str = ""

    # INV-66 (H3): intentos fallidos de login por email e IP y por IP, en una ventana fija (auth/limite_login.py)
    LOGIN_MAX_FALLOS_USUARIO_IP: int = 5
    LOGIN_MAX_FALLOS_IP: int = 20
    LOGIN_VENTANA_S: int = 900

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
    def ORIGENES_CORS(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGENES.split(",") if o.strip()]

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    @model_validator(mode="after")
    def _secretos_fuera_de_desarrollo(self) -> "Settings":
        """INV-66 (CA 1): fuera de desarrollo no arranca con secretos vacíos o del repositorio."""
        if self.ENTORNO == "desarrollo":
            return self
        errores = []
        if self.JWT_SECRET_KEY == CLAVE_JWT_DESARROLLO or len(self.JWT_SECRET_KEY.encode()) < 32:
            errores.append("JWT_SECRET_KEY no está definida o es la del repositorio (mínimo 32 bytes). "
                           f"Generar una con: {GENERAR_CLAVE}")
        if self.POSTGRES_PASSWORD in ("", CLAVE_BD_DESARROLLO):
            errores.append("POSTGRES_PASSWORD no está definida o es la del repositorio")
        if "*" in self.ORIGENES_CORS:
            errores.append("CORS_ORIGENES no admite * fuera de desarrollo")
        if errores:
            raise ValueError(f"ENTORNO={self.ENTORNO}: " + "; ".join(errores))
        return self

    class Config:
        env_file = ".env"
        extra = "ignore"
        # INV-66: el error de validación no copia las variables de entrada, que traen los secretos, al log
        hide_input_in_errors = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
