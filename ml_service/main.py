"""
InventAI/o — ML Service
INV-20: microservicio de predicción de demanda Nivel 1 (modelos de
INV-17). Carga los modelos LOCALMENTE desde models/*.joblib al arrancar
-- no depende del servidor MLflow en runtime (ver docs/INV-20-ml-service.md).
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_settings
from core.modelo_loader import ModeloLoader
from prediccion.features import FeatureStore
from prediccion.router import router as prediccion_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    loader = ModeloLoader(Path(settings.MODELOS_DIR))
    loader.cargar_todos()
    app.state.modelo_loader = loader
    app.state.feature_store = FeatureStore(Path(settings.FEATURES_SNAPSHOT_PATH))
    yield


app = FastAPI(
    title="InventAI/o ML Service",
    description=(
        "Microservicio de predicción de demanda (Nivel 1) sobre los "
        "modelos entrenados en INV-17."
    ),
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(prediccion_router)


@app.get("/api/health", tags=["Health"])
def health():
    loader: ModeloLoader = app.state.modelo_loader
    return {
        "status": "ok",
        "service": "inventaio-ml-service",
        "modelos_cargados": loader.ramas_cargadas,
    }
