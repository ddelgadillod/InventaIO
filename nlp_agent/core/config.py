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
    # Comentario SSE «: ping» tras este silencio (X5-c de INV-36): la carga del modelo en frío
    # tardó 64 s sin eventos el 21-oct, y un balanceador corta a los 60 s (INV-34)
    CHAT_PING_S: float = 15.0

    # Lo usan las herramientas de INV-32, siempre con el token del usuario
    CORE_API_URL: str = "http://api:8000"
    # Por llamada: cubre los 39,7 s de las alertas con IA en frío (T10), dentro de LLM_TIMEOUT_S
    CORE_API_TIMEOUT_S: float = 60.0

    # Límite de lo que se acepta en /chat: los mismos que valida el Core API
    # (X2 de INV-36: 6 turnos y la pregunta), para no responder 422 a lo que él aceptó
    MAX_MENSAJES: int = 13
    MAX_CARACTERES_MENSAJE: int = 2000

    # INV-33: el prompt (v1 de INV-32 o v2 por rol; Z3), su perfil (Z8), la verificación de la respuesta antes de
    # mostrarla (Z1) y el presupuesto del historial (Z7; 1.500 tokens, 500 con el perfil corto). Se activan por
    # medición (decisión del usuario del 21-oct): el 22-oct cumplieron la verificación con el v1 y el v2.1 con
    # verificación (acierto 73,8 % frente a 68,3 %, herramienta 83,6 % frente a 83,1 %, borrador 95,1 %)
    PROMPT_VERSION: str = "v2"
    PERFIL_PROMPT: str = "completo"
    FIDELIDAD_RETENER: bool = True
    HISTORIAL_PRESUPUESTO: int | None = None  # en tokens; sin valor, el del perfil
    # INV-33 (§3f, 23-oct): las mejoras del bucle (agente/mejoras.py). Se activan si el holdout-2 lo justifica
    MEJORAS: str = "ninguna"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
