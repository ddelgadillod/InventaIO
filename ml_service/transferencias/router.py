"""
InventAI/o — ML Service: router de transferencias (INV-22)
POST /api/transferencias. La lógica vive en transferencias/motor.py; aquí
solo se traduce el resultado y los errores a HTTP.
"""
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError

from prediccion.features import CalendarioInsuficiente
from schemas.transferencias import TransferenciasRequest, TransferenciasResponse
from transferencias.motor import FotoSinVentas, recomendar_transferencias

router = APIRouter(prefix="/api", tags=["Transferencias"])


@router.post(
    "/transferencias",
    response_model=TransferenciasResponse,
    response_model_exclude_unset=True,
    summary="Traslados sugeridos entre sucursales y desde la Bodega Central",
    description=(
        "Recomienda traslados de stock entre sucursales físicas y desde la Bodega Central antes de comprar a "
        "proveedor, con la foto de inventario más reciente y el pronóstico a 15 días hábiles. Devuelve los "
        "traslados, el balance por producto y ubicación (déficit, recibido y déficit neto para INV-21) y las "
        "alertas. Las reglas salen del archivo de políticas versionado (la respuesta dice qué versión usó)."
    ),
)
def transferencias(payload: TransferenciasRequest, request: Request) -> TransferenciasResponse:
    try:
        resultado = recomendar_transferencias(request.app.state.bodega, request.app.state.pronosticador,
                                              request.app.state.politicas, productos=payload.productos)
    except FotoSinVentas as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except CalendarioInsuficiente as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=f"Calendario de la bodega insuficiente: {e}")
    except (SQLAlchemyError, LookupError) as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=f"Bodega de datos no disponible: {type(e).__name__}: {e}")
    if not payload.incluir_balance:
        del resultado["balance"]
    return TransferenciasResponse(**resultado)
