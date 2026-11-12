"""
InventAI/o — Core API
FastAPI application entry point.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from alertas.router import router as alertas_router
from alertas.router_ml import router as alertas_ml_router
from auth.router import router as auth_router
from chat.router import router as chat_router
from consulta.router import router as consulta_router
from core.config import get_settings
from inventario.router import router as inventario_router
from ml.prediccion import router as prediccion_router
from ml.router import router as ml_router
from reportes.router import router as reportes_router

app = FastAPI(
    title="InventAI/o API",
    description=(
        "API del sistema inteligente de consulta y gestión logística "
        "para distribuidores de abarrotes."
    ),
    # La versión del producto: la escribe scripts/version.py desde VERSION
    version="2.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)


def configurar_cors(aplicacion: FastAPI, origenes: list[str]) -> None:
    """INV-66 (H5): CORS solo para los orígenes de CORS_ORIGENES. Sin ellos no hace falta: el navegador llega
    por el mismo origen (proxy de Vite o Nginx). El token va en Authorization, así que sin credenciales."""
    if origenes:
        aplicacion.add_middleware(CORSMiddleware, allow_origins=origenes, allow_methods=["*"], allow_headers=["*"])


configurar_cors(app, get_settings().ORIGENES_CORS)

# Routers
app.include_router(auth_router)
app.include_router(consulta_router)
app.include_router(inventario_router)
app.include_router(alertas_router)
app.include_router(alertas_ml_router)
app.include_router(reportes_router)
app.include_router(ml_router)
app.include_router(prediccion_router)
app.include_router(chat_router)


@app.get("/api/health", tags=["Health"])
def health():
    """Health check endpoint. INV-34 (B17): con el commit de la imagen, para saber qué corre en staging."""
    return {"status": "ok", "service": "inventaio-api", "version": app.version,
            "commit": get_settings().INVENTAIO_COMMIT[:7]}
