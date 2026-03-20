"""
InventAI/o — Core API
FastAPI application entry point.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from auth.router import router as auth_router
from consulta.router import router as consulta_router

app = FastAPI(
    title="InventAI/o API",
    description=(
        "API del sistema inteligente de consulta y gestión logística "
        "para distribuidores de abarrotes."
    ),
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS (permisivo para desarrollo)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router)
app.include_router(consulta_router)


@app.get("/api/health", tags=["Health"])
def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "inventaio-api"}
