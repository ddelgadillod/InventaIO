"""
InventAI/o — NLP Agent
INV-30: servicio del agente conversacional sobre un modelo autoalojado con
Ollama (D22). Interno: solo lo llama el Core API (N3, INV-36) y no publica su
puerto. No tiene credenciales propias; las herramientas de INV-32 consultan el
Core API con el token del usuario. Ver docs/NLP-AGENT.md.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from chat.router import router as chat_router
from core.config import VERSION, get_settings
from llm.cliente import ClienteLLM, ClienteOllama, ErrorLLM

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def crear_app(cliente: ClienteLLM | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.llm = cliente or ClienteOllama(get_settings())
        yield
        await app.state.llm.cerrar()

    app = FastAPI(
        title="InventAI/o NLP Agent",
        description="Agente conversacional interno sobre un modelo autoalojado con Ollama (INV-30).",
        version=VERSION,
        lifespan=lifespan,
    )
    app.include_router(chat_router)

    @app.get("/health", tags=["Salud"])
    async def health():
        """El proceso vive. Es lo único que verifica el CI de imágenes (criterio 2)."""
        return {"status": "ok", "servicio": "nlp-agent", "version": VERSION}

    @app.get("/ready", tags=["Salud"])
    async def ready():
        """Ollama responde y el modelo configurado está descargado; si no, 503 con el motivo."""
        modelo = get_settings().LLM_MODELO
        try:
            version_ollama = await app.state.llm.version()
            if not await app.state.llm.modelo_disponible(modelo):
                raise ErrorLLM("modelo_no_descargado", modelo)
        except ErrorLLM as exc:
            motivo = "modelo_no_descargado" if exc.codigo == "modelo_no_descargado" else "ollama_no_alcanzable"
            return JSONResponse(status_code=503, content={"status": "no_listo", "modelo": modelo, "motivo": motivo})
        return {"status": "listo", "modelo": modelo, "version_ollama": version_ollama, "version": VERSION}

    return app


app = crear_app()
