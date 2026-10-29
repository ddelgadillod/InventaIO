"""
InventAI/o — ML Service
INV-20: microservicio de predicción de demanda Nivel 1 (modelos de
INV-17). Carga los modelos LOCALMENTE desde models/*.joblib al arrancar
-- no depende del servidor MLflow en runtime (ver docs/INV-20-ml-service.md).
Desde el fix de la bodega, los datos de cada predicción salen de la bodega
de datos en Postgres (esquema dw), no de un extracto local.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from compras.politicas import cargar_politicas_compras
from compras.router import router as compras_router
from core.config import get_settings
from core.database import crear_engine
from core.modelo_loader import ModeloLoader
from prediccion.bodega import BodegaPostgres
from prediccion.router import router as prediccion_router
from prediccion.servicio import PronosticadorNivel1
from transferencias.politicas import cargar_politicas
from transferencias.router import router as transferencias_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    loader = ModeloLoader(Path(settings.MODELOS_DIR))
    loader.cargar_todos()
    app.state.modelo_loader = loader
    # INV-22: la recomendación de transferencias pronostica con los mismos
    # modelos, en el mismo proceso. Políticas inválidas: el servicio no arranca.
    app.state.pronosticador = PronosticadorNivel1(loader)
    app.state.politicas = cargar_politicas(settings.POLITICAS_TRANSFERENCIAS_PATH)
    # INV-21: compras, sobre el balance de transferencias; mismo criterio.
    app.state.politicas_compras = cargar_politicas_compras(settings.POLITICAS_COMPRAS_PATH)
    # El engine no abre conexiones hasta la primera consulta: el servicio
    # arranca aunque Postgres todavía no esté listo (/api/health lo reporta).
    engine = crear_engine(settings.DATABASE_URL)
    app.state.bodega = BodegaPostgres(engine, cache_segundos=settings.CACHE_CALENDARIO_SEGUNDOS)
    yield
    engine.dispose()


app = FastAPI(
    title="InventAI/o ML Service",
    description=(
        "Microservicio de predicción de demanda (Nivel 1) sobre los "
        "modelos entrenados en INV-17, con datos de la bodega (Postgres), "
        "recomendación de transferencias entre sucursales (INV-22) y de "
        "compras a proveedor (INV-21)."
    ),
    version="1.3.0",
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
app.include_router(transferencias_router)
app.include_router(compras_router)


def _version(politicas) -> dict:
    return {"version": politicas.version, "fecha": politicas.fecha.isoformat()}


@app.get("/api/health", tags=["Health"])
def health():
    loader: ModeloLoader = app.state.modelo_loader
    bodega_ok = app.state.bodega.disponible()
    # INV-23: la foto y las versiones de políticas son la clave de la caché del Core API
    fecha = None
    if bodega_ok:
        try:
            fecha = app.state.bodega.fecha_inventario().date().isoformat()
        except Exception:
            fecha = None
    return {
        "status": "ok" if bodega_ok else "degradado",
        "service": "inventaio-ml-service",
        "modelos_cargados": loader.ramas_cargadas,
        "bodega": "ok" if bodega_ok else "sin conexión",
        "fecha_inventario": fecha,
        "politicas": {"inv21": _version(app.state.politicas_compras), "inv22": _version(app.state.politicas)},
    }
