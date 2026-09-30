"""
InventAI/o — ML Service: router de compras (INV-21)
POST /api/compras. La lógica vive en compras/motor.py; aquí solo se traduce
el resultado y los errores a HTTP, igual que en /api/transferencias.
"""
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError

from compras.motor import recomendar_compras
from prediccion.features import CalendarioInsuficiente
from schemas.compras import ComprasRequest, ComprasResponse
from transferencias.motor import FotoSinVentas

router = APIRouter(prefix="/api", tags=["Compras"])


@router.post(
    "/compras",
    response_model=ComprasResponse,
    response_model_exclude_unset=True,
    summary="Compras sugeridas a proveedor, después de las transferencias",
    description=(
        "Recomienda compras a proveedor para lo que las transferencias de INV-22 no alcanzan a cubrir: compra "
        "cuando el stock después de los traslados sugeridos no alcanza, a la mediana, hasta que llegue el pedido "
        "siguiente, y sube hasta el cuantil de negocio de ese plazo. Perecederos y frío van directo a la "
        "sucursal cada semana; lo demás, a la Bodega Central los días 2 y 16, descontando lo que ya tiene. Las "
        "reglas salen del archivo de políticas versionado (la respuesta dice qué versión usó)."
    ),
)
def compras(payload: ComprasRequest, request: Request) -> ComprasResponse:
    estado = request.app.state
    try:
        resultado = recomendar_compras(estado.bodega, estado.pronosticador, estado.politicas_compras,
                                       estado.politicas, productos=payload.productos)
    except FotoSinVentas as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except CalendarioInsuficiente as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=f"Calendario de la bodega insuficiente: {e}")
    except (SQLAlchemyError, LookupError) as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=f"Bodega de datos no disponible: {type(e).__name__}: {e}")
    if not payload.incluir_detalle:
        for linea in resultado["compras"] + resultado["cubrir_con_traslado"]:
            del linea["detalle"]
    return ComprasResponse(**resultado)
