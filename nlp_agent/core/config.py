"""
InventAI/o — NLP Agent: configuración
INV-30: todo por variables de entorno (criterio 10), con pydantic-settings como
api/ y ml_service/. El agente no tiene credenciales propias: no hay POSTGRES_*
ni usuario del Core API (criterio 6); actúa con el token de quien pregunta.
Valores y motivos en docs/INV-30-requerimientos.md (sección 4.2).
"""
from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings

# La versión del producto (desde v2.1.0 es la misma en todos los servicios): scripts/version.py
VERSION = "2.1.0"

# INV-67 (B5): Qwen3-32B en Bedrock. El id cambia con la superficie (B6): bedrock-runtime rechaza el
# corto con «The provided model identifier is invalid» (sonda del 11-nov)
MODELOS_BEDROCK = {"runtime": "qwen.qwen3-32b-v1:0", "mantle": "qwen.qwen3-32b"}


class Settings(BaseSettings):
    # INV-67: dónde corre el modelo. `bedrock` usa ClienteBedrock (llm/bedrock.py) con las
    # credenciales de la cadena estándar de AWS; nunca van en el repositorio ni en el compose
    LLM_PROVEEDOR: Literal["ollama", "bedrock"] = "ollama"

    # Ollama nativo en WSL (W1) o el contenedor del perfil `llm` (N6). Fuera de
    # Docker, localhost; el compose lo cambia a host.docker.internal o a ollama.
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # Tag fijo; lo decide el spike (N2) y queda con su digest en docs/NLP-AGENT.md.
    # Con LLM_PROVEEDOR=bedrock y sin valor propio, el de MODELOS_BEDROCK según BEDROCK_ENDPOINT
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
    # INV-33 (24-oct): tope de lo que genera el modelo por ronda, en tokens (num_predict de Ollama). La respuesta final llega a ~450 (p95); el tope solo corta una
    # generación desbocada (34.873 tokens en 16 min en una corrida del 24-oct)
    LLM_TOPE_RESPUESTA: int = 2048
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
    # INV-33 (§3f a §3g): las mejoras del bucle (agente/mejoras.py), apagadas: en el holdout-3 no superaron al agente
    # del 22-oct (24-oct). «final» reproduce la configuración F para el Sprint 7
    MEJORAS: str = "ninguna"

    # INV-67 (B6): Chat Completions de Bedrock. `runtime` es bedrock-runtime…/openai/v1 (permiso
    # bedrock:InvokeModel*); `mantle`, bedrock-mantle…/v1 (bedrock-mantle:CreateInference)
    BEDROCK_REGION: str = "us-east-1"
    BEDROCK_ENDPOINT: Literal["runtime", "mantle"] = "runtime"
    # B11: US$ por millón de tokens, para el costo del arnés. Estimados de la ruta (§5, fuentes de
    # terceros): se reconcilian con la factura antes de cerrar INV-67
    BEDROCK_PRECIO_ENTRADA: float = 0.15
    BEDROCK_PRECIO_SALIDA: float = 0.60
    # B14: campos que se agregan a cada petición (p. ej. para apagar el razonamiento si la sonda lo ve)
    BEDROCK_CUERPO_EXTRA: dict = {}

    @model_validator(mode="after")
    def _modelo_del_proveedor(self):
        if self.LLM_PROVEEDOR == "bedrock" and "LLM_MODELO" not in self.model_fields_set:
            self.LLM_MODELO = MODELOS_BEDROCK[self.BEDROCK_ENDPOINT]
        return self

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
