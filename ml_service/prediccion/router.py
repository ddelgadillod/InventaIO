"""
InventAI/o — ML Service: router de predicción
INV-20: POST /api/predict
"""
from fastapi import APIRouter, HTTPException, Request, status

from core.config import get_settings
from prediccion.features import determinar_rama
from prediccion.interpretacion import generar_interpretacion
from prediccion.motor import predecir
from schemas.prediccion import IntervaloConfianza, PrediccionRequest, PrediccionResponse

router = APIRouter(prefix="/api", tags=["Predicción"])


@router.post(
    "/predict",
    response_model=PrediccionResponse,
    summary="Predicción de demanda acumulada a 15 días hábiles",
    description=(
        "Predice la demanda acumulada de un producto en una sucursal para los "
        "próximos 15 días hábiles (Nivel 1, INV-17). Usa el extracto local de "
        "features más reciente para ese par (ver docs/INV-20-ml-service.md) -- "
        "no consulta Postgres en vivo. producto_id/sucursal_id son el código de "
        "negocio (codigo_item) y el nombre de sucursal, no el SERIAL de Postgres."
    ),
)
def predict(payload: PrediccionRequest, request: Request) -> PrediccionResponse:
    settings = get_settings()
    if payload.horizonte != settings.HORIZONTE_SOPORTADO:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Los modelos solo predicen demanda acumulada a "
                f"{settings.HORIZONTE_SOPORTADO} días hábiles -- "
                f"horizonte={payload.horizonte} no está soportado sin reentrenar."
            ),
        )

    feature_store = request.app.state.feature_store
    modelo_loader = request.app.state.modelo_loader

    fila = feature_store.buscar(payload.producto_id, payload.sucursal_id)
    if fila is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No hay features suficientes para producto_id={payload.producto_id}, "
                f"sucursal_id={payload.sucursal_id} -- par sin historia suficiente o inexistente."
            ),
        )

    rama = determinar_rama(fila.iloc[0])
    paquete = modelo_loader.get(rama)
    pred_q50, pred_qneg = predecir(paquete, fila)

    fecha_features = fila.iloc[0]["fecha_origen"]
    fecha_features_str = (
        fecha_features.date().isoformat() if hasattr(fecha_features, "date") else str(fecha_features)
    )

    alpha_negocio = paquete["alpha_negocio"]
    interpretacion = generar_interpretacion(
        rama=rama,
        prediccion_q50=pred_q50,
        limite_superior=pred_qneg,
        alpha_negocio=alpha_negocio,
        horizonte=payload.horizonte,
    )

    return PrediccionResponse(
        producto_id=payload.producto_id,
        sucursal_id=payload.sucursal_id,
        horizonte_dias=payload.horizonte,
        rama=rama,
        prediccion_q50=round(pred_q50, 2),
        intervalo_confianza=IntervaloConfianza(
            limite_inferior=0.0,
            limite_superior=round(pred_qneg, 2),
            alpha_negocio=alpha_negocio,
        ),
        interpretacion=interpretacion,
        fecha_features=fecha_features_str,
        modelo_entrenado_en=modelo_loader.fecha_entrenamiento,
    )
