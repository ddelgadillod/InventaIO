"""
InventAI/o — NLP Agent: configuración
INV-30: todo por variables de entorno (criterio 10), con pydantic-settings como
api/ y ml_service/. El agente no tiene credenciales propias: no hay POSTGRES_*
ni usuario del Core API (criterio 6); actúa con el token de quien pregunta.
Valores y motivos en docs/INV-30-requerimientos.md (sección 4.2).
"""
from functools import lru_cache

from pydantic_settings import BaseSettings

VERSION = "0.1.0"


class Settings(BaseSettings):
    # Ollama nativo en WSL (W1) o el contenedor del perfil `llm` (N6). Fuera de
    # Docker, localhost; el compose lo cambia a host.docker.internal o a ollama.
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # Tag fijo; lo decide el spike (N2) y queda con su digest en docs/NLP-AGENT.md
    LLM_MODELO: str = "qwen3:8b"
    LLM_NUM_CTX: int = 8192
    LLM_KEEP_ALIVE: str = "30m"           # evita recargar varios GB entre preguntas
    # Determinista para las herramientas (criterio 5); aun así Ollama no repite
    # exacto, por eso el spike corre cada pregunta 3 veces
    LLM_TEMPERATURA: float = 0.0
    LLM_TOP_P: float = 1.0
    LLM_SEMILLA: int = 42
    LLM_RAZONAMIENTO: bool = False        # W4: Qwen3 sin razonamiento
    LLM_TIMEOUT_S: float = 120.0          # el mismo límite que el chat del Core API (INV-36)

    # Lo usan las herramientas de INV-32, siempre con el token del usuario
    CORE_API_URL: str = "http://api:8000"

    # Límite de lo que se acepta en /chat; el Core API valida antes (422, INV-36)
    MAX_MENSAJES: int = 12
    MAX_CARACTERES_MENSAJE: int = 2000

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
