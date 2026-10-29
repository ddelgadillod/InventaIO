"""
InventAI/o — Pronóstico Router
INV-25 (D8): POST /api/ml/predict en el Core API, con token y permisos, sobre
el cliente de INV-23. Mismo contrato que POST /api/predict de ml_service, que
queda como servicio interno. RBAC: gerente y admin_bodega pronostican
cualquier sucursal física; admin_sucursal solo la suya.
Ver docs/INV-25-requerimientos.md.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from auth.dependencies import get_current_user
from ml.catalogo import CatalogoBodega, get_catalogo
from ml.cliente import ClienteML, get_cliente_ml
from models.usuario import Usuario
from schemas.prediccion import PrediccionRequest, PrediccionResponse

router = APIRouter(prefix="/api/ml", tags=["Pronóstico"])


def verificar_sucursal(user: Usuario, catalogo: CatalogoBodega, pedido: PrediccionRequest) -> None:
    """admin_sucursal solo pronostica su sucursal. Como en ml_service, el
    nombre (sucursal_id) manda sobre el id (id_sucursal)."""
    if user.rol != "admin_sucursal":
        return
    sucursales = catalogo.sucursales()
    propia = sucursales.get(user.id_sucursal)
    if pedido.sucursal_id is not None:
        es_propia = propia is not None and pedido.sucursal_id == propia
    else:
        es_propia = pedido.id_sucursal is not None and pedido.id_sucursal == user.id_sucursal
    if not es_propia:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Solo puede pronosticar su sucursal ({propia})")


@router.post(
    "/predict",
    response_model=PrediccionResponse,
    summary="Pronóstico de demanda a 15 días hábiles",
    description=(
        "Pronostica la demanda acumulada de un producto en una sucursal física (POST /api/predict de "
        "ml_service, mismo contrato). Producto por producto_id o id_producto; sucursal por sucursal_id "
        "(nombre) o id_sucursal. RBAC: admin_sucursal solo su sucursal (403). Errores de la petición de "
        "ml_service pasan tal cual: 404 producto o sucursal desconocidos o historia insuficiente; 422 "
        "horizonte distinto de 15, sucursal no física (la Bodega) o cuerpo inválido. 503 ml_service o la "
        "bodega no disponibles; 504 sin respuesta en 120 s; 502 otro error."
    ),
)
def predecir(
    pedido: PrediccionRequest,
    user: Usuario = Depends(get_current_user),
    catalogo: CatalogoBodega = Depends(get_catalogo),
    cliente: ClienteML = Depends(get_cliente_ml),
):
    verificar_sucursal(user, catalogo, pedido)
    return cliente.predecir(pedido.model_dump(mode="json", exclude_none=True))
