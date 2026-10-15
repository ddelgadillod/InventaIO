"""
InventAI/o — Alertas con IA Router (INV-28)
GET /api/alertas/ml: riesgo de desabastecimiento y sobrestock previsto a partir
del balance de traslados de INV-22. Endpoint aparte (V1) para que /api/alertas,
/api/alertas/resumen y el Dashboard no esperen al ML Service. Reutiliza el
cliente y la caché de INV-23 (V8): comparte la entrada de la caché con
Recomendaciones. Permisos de INV-25 (V7). Ver docs/INV-28-requerimientos.md.
"""
import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from alertas.ml import generar_alertas_ml, resumen_alertas_ml
from alertas.router import ALERTAS_POR_PAGINA, UMBRAL_BAJO, UMBRAL_CRITICO
from auth.dependencies import get_current_user
from core.database import get_db
from core.ubicaciones import ALERTAS, cargar_ubicaciones, resolver_sucursal
from ml.cache import CacheRecomendaciones, get_cache
from ml.catalogo import CatalogoBodega, get_catalogo
from ml.cliente import ClienteML, get_cliente_ml
from ml.router import DESC_ERRORES, obtener_recomendaciones
from models.usuario import Usuario
from schemas.alertas import AlertaMLList, OrigenAlertaML, TipoAlertaML, UrgenciaAlerta

router = APIRouter(prefix="/api/alertas", tags=["Alertas"])


class ReglasInventario:
    """Lo que las alertas con IA leen de la bodega: las ubicaciones (permisos de
    INV-25) y los pares que las reglas ya marcan en riesgo (V2)."""

    def __init__(self, db: Session):
        self._db = db

    def ubicaciones(self) -> dict[int, dict]:
        return cargar_ubicaciones(self._db)

    def pares_riesgo(self, fecha: str) -> set[tuple[int, int]]:
        """(id_sucursal, id_producto) con stock_critico o stock_bajo en la foto,
        con las mismas condiciones que /api/alertas."""
        rows = self._db.execute(text(f"""
            SELECT fi.id_sucursal, fi.id_producto
            FROM dw.fact_inventario fi
            JOIN dw.dim_tiempo t ON fi.id_tiempo = t.id_tiempo
            WHERE t.fecha = :fecha
              AND ((fi.dias_cobertura < {UMBRAL_CRITICO} AND fi.stock_disponible >= 0)
                   OR (fi.dias_cobertura >= {UMBRAL_CRITICO} AND fi.dias_cobertura < {UMBRAL_BAJO}))
        """), {"fecha": fecha}).fetchall()
        return {(r.id_sucursal, r.id_producto) for r in rows}


def get_reglas(db: Session = Depends(get_db)) -> ReglasInventario:
    return ReglasInventario(db)


# ── GET /api/alertas/ml ─────────────────────────────
@router.get(
    "/ml",
    response_model=AlertaMLList,
    response_model_exclude_unset=True,
    summary="Alertas con IA: riesgo de desabastecimiento y sobrestock previsto (INV-28)",
    description=(
        "Alertas calculadas con el pronóstico de demanda a 15 días hábiles (balance de POST /api/transferencias "
        "de ml_service), solo en sucursales físicas. riesgo_desabastecimiento_ml: el stock alcanza ≤ 5 días "
        "hábiles (critica) o ≤ 10 (alta), con q50 ≥ 1 y stock ≥ 0. sobrestock_previsto_ml (media): stock > 2 × "
        "el máximo de INV-22, con q50 > 0. origen=ambos si las reglas ya marcan el par con stock_critico o "
        "stock_bajo. tipo, urgencia y origen se pueden repetir para pedir varios valores. El resumen cuenta lo filtrado. La primera llamada tras una foto nueva tarda 20 a 40 s; "
        "comparte la caché con /api/ml/recomendaciones/transferencias. " + DESC_ERRORES
    ),
)
def listar_alertas_ml(
    sucursal_id: int | None = Query(
        None, description="Filtrar por sucursal. admin_sucursal: solo la suya; otra da 403. Inexistente o SIN_SUCURSAL, 422"),
    # V13: cada filtro se puede repetir para pedir varios valores (tipo=a&tipo=b)
    tipo: list[TipoAlertaML] | None = Query(None, description="riesgo_desabastecimiento_ml o sobrestock_previsto_ml; repetible"),
    urgencia: list[UrgenciaAlerta] | None = Query(None, description="critica, alta o media; repetible"),
    origen: list[OrigenAlertaML] | None = Query(None, description="ml (solo las ve el modelo) o ambos; repetible"),
    page: int | None = Query(None, ge=1, description="Página. Sin page ni page_size: todas"),
    page_size: int | None = Query(
        None, ge=1, le=500, description=f"Alertas por página; {ALERTAS_POR_PAGINA} si solo se envía page"),
    user: Usuario = Depends(get_current_user),
    reglas: ReglasInventario = Depends(get_reglas),
    catalogo: CatalogoBodega = Depends(get_catalogo),
    cliente: ClienteML = Depends(get_cliente_ml),
    cache: CacheRecomendaciones = Depends(get_cache),
):
    ubicaciones = reglas.ubicaciones()
    # Permisos antes de llamar al ML Service: 422 sucursal inválida, 403 ajena o la Bodega (V7)
    suc = resolver_sucursal(ubicaciones, user, sucursal_id, ALERTAS)
    datos = obtener_recomendaciones("transferencias", cliente, cache, catalogo)
    respuesta = datos["respuesta"]
    alertas = generar_alertas_ml(
        respuesta, catalogo.ids_producto(), {u["nombre"]: i for i, u in ubicaciones.items()},
        reglas.pares_riesgo(respuesta["fecha_inventario"]))
    alertas = [a for a in alertas
               if (suc is None or a["id_sucursal"] == suc) and (not tipo or a["tipo"] in tipo)
               and (not urgencia or a["urgencia"] in urgencia) and (not origen or a["origen"] in origen)]
    cuerpo = {"total": len(alertas), "resumen": resumen_alertas_ml(alertas),
              "fecha_inventario": respuesta["fecha_inventario"], "politicas": respuesta["politicas"],
              "calculado_en": datos["calculado_en"]}
    if page is None and page_size is None:
        return {**cuerpo, "items": alertas}
    page, page_size = page or 1, page_size or ALERTAS_POR_PAGINA
    inicio = (page - 1) * page_size
    return {**cuerpo, "items": alertas[inicio:inicio + page_size], "page": page, "page_size": page_size,
            "pages": math.ceil(len(alertas) / page_size)}
