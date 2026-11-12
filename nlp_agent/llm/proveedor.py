"""El cliente del modelo según LLM_PROVEEDOR (INV-67, criterio 5): el agente no sabe cuál usa."""
from core.config import Settings
from llm.bedrock import ClienteBedrock
from llm.cliente import ClienteLLM, ClienteOllama


def crear_cliente(settings: Settings) -> ClienteLLM:
    if settings.LLM_PROVEEDOR == "bedrock":
        return ClienteBedrock(settings)
    return ClienteOllama(settings)
