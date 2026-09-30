"""
InventAI/o — ML Service: router de predicción
INV-20: POST /api/predict. Desde el fix de la bodega, las features se
calculan en cada petición leyendo dw.* (ver prediccion/features.py y
prediccion/bodega.py), no desde un extracto de la matriz de entrenamiento.
"""
import pandas as pd
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError

from core.config import get_settings
from prediccion.features import CalendarioInsuficiente, HistoriaInsuficiente
from prediccion.interpretacion import generar_interpretacion
from prediccion.servicio import pronosticar_par
from schemas.prediccion import IntervaloConfianza, PrediccionRequest, PrediccionResponse

router = APIRouter(prefix="/api", tags=["Predicción"])


def _no_disponible(detalle: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detalle)


def _calendario_insuficiente(e: CalendarioInsuficiente) -> HTTPException:
    return _no_disponible(f"Calendario de la bodega insuficiente: {e}")


def _sin_historia(producto: dict, sucursal: dict, e: HistoriaInsuficiente) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=(f"No hay historia suficiente para producto_id={producto['codigo_item']}, "
                f"sucursal_id={sucursal['nombre']}: {e}"),
    )


@router.post(
    "/predict",
    response_model=PrediccionResponse,
    summary="Predicción de demanda acumulada a 15 días hábiles",
    description=(
        "Predice la demanda acumulada de un producto en una sucursal física para los próximos 15 días "
        "hábiles (Nivel 1, INV-17), con features calculadas desde la bodega de datos a la fecha del último "
        "dato (o a `fecha_corte`). El producto y la sucursal se indican por clave de negocio "
        "(codigo_item, nombre) o por el SERIAL de Postgres (id_producto, id_sucursal)."
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

    bodega = request.app.state.bodega
    modelo_loader = request.app.state.modelo_loader
    parametros = modelo_loader.parametros_features

    try:
        producto = bodega.producto(codigo_item=payload.producto_id, id_producto=payload.id_producto)
        if producto is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Producto no encontrado en la bodega: {payload.producto_id or payload.id_producto}")
        sucursal = bodega.sucursal(nombre=payload.sucursal_id, id_sucursal=payload.id_sucursal)
        if sucursal is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Sucursal no encontrada en la bodega: {payload.sucursal_id or payload.id_sucursal}")
        if sucursal["tipo"] not in parametros["tipos_sucursal_modelo"]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(f"La sucursal {sucursal['nombre']} ({sucursal['tipo']}) no es una sucursal física: "
                        "el modelo solo se entrenó con PRINCIPAL, LA 21 y GLORIETA."),
            )

        calendario = bodega.calendario()
        if payload.fecha_corte is not None and pd.Timestamp(payload.fecha_corte) > calendario.ultima_fecha:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(f"fecha_corte={payload.fecha_corte} es posterior al último dato de la bodega "
                        f"({calendario.ultima_fecha.date()})."),
            )
        fecha = calendario.ultimo_habil(payload.fecha_corte or calendario.ultima_fecha)
        unidades = bodega.ventas_diarias(producto["codigo_item"], sucursal["nombre"], hasta=fecha)
    except HistoriaInsuficiente as e:
        raise _sin_historia(producto, sucursal, e)
    except CalendarioInsuficiente as e:
        raise _calendario_insuficiente(e)
    except (SQLAlchemyError, LookupError) as e:
        raise _no_disponible(f"Bodega de datos no disponible: {type(e).__name__}: {e}")

    # INV-22: el cálculo vive en prediccion/servicio.py (lo comparte la
    # recomendación de transferencias); mismos errores que antes.
    try:
        pronostico = pronosticar_par(modelo_loader, producto, sucursal["nombre"], unidades, calendario, fecha)
    except HistoriaInsuficiente as e:
        raise _sin_historia(producto, sucursal, e)
    except CalendarioInsuficiente as e:
        raise _calendario_insuficiente(e)

    interpretacion = generar_interpretacion(
        rama=pronostico.rama,
        prediccion_q50=pronostico.q50,
        limite_superior=pronostico.limite_superior,
        alpha_negocio=pronostico.alpha_negocio,
        horizonte=payload.horizonte,
    )

    return PrediccionResponse(
        producto_id=producto["codigo_item"],
        id_producto=producto["id_producto"],
        sucursal_id=sucursal["nombre"],
        id_sucursal=sucursal["id_sucursal"],
        horizonte_dias=payload.horizonte,
        rama=pronostico.rama,
        prediccion_q50=round(pronostico.q50, 2),
        intervalo_confianza=IntervaloConfianza(
            limite_inferior=0.0,
            limite_superior=round(pronostico.limite_superior, 2),
            alpha_negocio=pronostico.alpha_negocio,
        ),
        interpretacion=interpretacion,
        fecha_features=fecha.date().isoformat(),
        modelo_entrenado_en=modelo_loader.fecha_entrenamiento,
    )
