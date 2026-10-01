"""
InventAI/o — Recomendaciones Router
INV-23: GET de las recomendaciones de compras (INV-21) y transferencias
(INV-22) de ml_service, con filtros, nombre y categoría del producto y un
resumen propio. ml_service calcula una vez por foto (caché, C3); los filtros
se aplican sobre lo guardado. RBAC: admin_sucursal ve solo su sucursal (C1).
Ver docs/INV-23-requerimientos.md.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from auth.dependencies import get_current_user
from ml.cache import CacheRecomendaciones, get_cache
from ml.catalogo import CatalogoBodega, buscar, get_catalogo
from ml.cliente import ClienteML, get_cliente_ml
from ml.filtros import (
    LISTAS_COMPRAS, LISTAS_TRANSFERENCIAS, Filtros,
    enriquecer, filtrar_compras, filtrar_transferencias,
)
from models.usuario import Usuario
from schemas.recomendaciones import (
    RecomendacionesCompras, RecomendacionesTransferencias,
    UrgenciaCompra, UrgenciaTraslado,
)

router = APIRouter(prefix="/api/ml/recomendaciones", tags=["Recomendaciones"])

DESC_SUCURSAL = ("PRINCIPAL, LA 21, GLORIETA o BODEGA_CENTRAL; sin distinguir mayúsculas ni acentos. "
                 "Un admin_sucursal solo puede pedir la suya, y sin el parámetro se le aplica.")
DESC_CATEGORIA = "Una categoría de dw.dim_producto (p. ej. Lácteos o lacteos); sin distinguir mayúsculas ni acentos."
DESC_URGENCIA = "Coincidencia exacta. No filtra las alertas."
DESC_ERRORES = ("Errores: 401 token inválido; 403 sin token o sucursal ajena; 409 foto posterior a la última venta; "
                "422 parámetro inválido o desconocido; 502 error inesperado de ml_service; 503 ml_service o la "
                "bodega no disponibles; 504 ml_service no respondió a tiempo.")


# ── Filtros y permisos ──────────────────────────────

def resolver_filtros(user: Usuario, catalogo: CatalogoBodega, sucursal: Optional[str],
                     categoria: Optional[str], urgencia: Optional[str]) -> Filtros:
    """Valida y normaliza los filtros (R3) y aplica los permisos por rol (C1)."""
    sucursales = catalogo.sucursales()
    canon_sucursal = None
    if sucursal is not None:
        canon_sucursal = buscar(sucursal, sucursales.values())
        if canon_sucursal is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"Sucursal desconocida: '{sucursal}'. Válidas: {', '.join(sucursales.values())}")
    por_rol = False
    if user.rol == "admin_sucursal":
        propia = sucursales.get(user.id_sucursal)
        if propia is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "El usuario no tiene una sucursal asignada")
        if canon_sucursal is None:
            canon_sucursal, por_rol = propia, True
        elif canon_sucursal != propia:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Solo puede consultar su sucursal ({propia})")
    canon_categoria = None
    if categoria is not None:
        canon_categoria = buscar(categoria, catalogo.categorias())
        if canon_categoria is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Categoría desconocida: '{categoria}'")
    return Filtros(sucursal=canon_sucursal, categoria=canon_categoria, urgencia=urgencia, sucursal_por_rol=por_rol)


def obtener_recomendaciones(endpoint: str, cliente: ClienteML, cache: CacheRecomendaciones,
                            catalogo: CatalogoBodega) -> dict:
    """El resultado completo y enriquecido de ml_service, de la caché si la
    foto y las políticas no cambiaron (C3)."""
    salud = cliente.salud()
    politicas = salud["politicas"]
    clave = (endpoint, salud["fecha_inventario"],
             politicas["inv21"]["version"], politicas["inv21"]["fecha"],
             politicas["inv22"]["version"], politicas["inv22"]["fecha"])

    def calcular() -> dict:
        if endpoint == "compras":
            respuesta, listas = cliente.compras(), LISTAS_COMPRAS
        else:
            respuesta, listas = cliente.transferencias(), LISTAS_TRANSFERENCIAS
        return {"respuesta": enriquecer(respuesta, listas, catalogo.productos()),
                "calculado_en": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}

    return cache.obtener(clave, calcular)


# ── GET /api/ml/recomendaciones/compras ─────────────
@router.get(
    "/compras",
    response_model=RecomendacionesCompras,
    response_model_exclude_unset=True,
    summary="Compras a proveedor sugeridas (INV-21), con filtros",
    description=(
        "Recomendación de compras de ml_service (POST /api/compras) para todo el catálogo, con nombre y "
        "categoría del producto. Con una sucursal física devuelve sus compras directas y las de la Bodega "
        "donde participa, vistas desde ella: su urgencia, su detalle y su parte de la necesidad "
        "(necesidad_sucursal). El resumen se recalcula sobre lo filtrado. La primera llamada tras una foto "
        "nueva tarda unos 20 s; las siguientes salen de la caché. " + DESC_ERRORES
    ),
)
def recomendaciones_compras(
    sucursal: Optional[str] = Query(None, description=DESC_SUCURSAL),
    categoria: Optional[str] = Query(None, description=DESC_CATEGORIA),
    urgencia: Optional[UrgenciaCompra] = Query(None, description=DESC_URGENCIA),
    incluir_detalle: bool = Query(True, description="Con false, las filas no traen el cálculo por sucursal."),
    user: Usuario = Depends(get_current_user),
    catalogo: CatalogoBodega = Depends(get_catalogo),
    cliente: ClienteML = Depends(get_cliente_ml),
    cache: CacheRecomendaciones = Depends(get_cache),
):
    filtros = resolver_filtros(user, catalogo, sucursal, categoria, urgencia)
    datos = obtener_recomendaciones("compras", cliente, cache, catalogo)
    cuerpo = filtrar_compras(datos["respuesta"], filtros, incluir_detalle)
    cuerpo.update(filtros_aplicados=filtros.aplicados(), calculado_en=datos["calculado_en"])
    return cuerpo


# ── GET /api/ml/recomendaciones/transferencias ──────
@router.get(
    "/transferencias",
    response_model=RecomendacionesTransferencias,
    response_model_exclude_unset=True,
    summary="Traslados sugeridos (INV-22), con filtros",
    description=(
        "Recomendación de transferencias de ml_service (POST /api/transferencias) para todo el catálogo, con "
        "nombre y categoría del producto. La sucursal filtra los traslados por origen o destino. El balance "
        "(unas 11.700 filas sin filtros) y las alertas sin_pronostico solo se listan con incluir_balance=true; "
        "el resumen los cuenta siempre. La primera llamada tras una foto nueva tarda unos 20 s; las "
        "siguientes salen de la caché. " + DESC_ERRORES
    ),
)
def recomendaciones_transferencias(
    sucursal: Optional[str] = Query(None, description=DESC_SUCURSAL),
    categoria: Optional[str] = Query(None, description=DESC_CATEGORIA),
    urgencia: Optional[UrgenciaTraslado] = Query(None, description=DESC_URGENCIA),
    incluir_balance: bool = Query(False, description="Con true, llegan el balance y las alertas sin_pronostico."),
    user: Usuario = Depends(get_current_user),
    catalogo: CatalogoBodega = Depends(get_catalogo),
    cliente: ClienteML = Depends(get_cliente_ml),
    cache: CacheRecomendaciones = Depends(get_cache),
):
    filtros = resolver_filtros(user, catalogo, sucursal, categoria, urgencia)
    datos = obtener_recomendaciones("transferencias", cliente, cache, catalogo)
    cuerpo = filtrar_transferencias(datos["respuesta"], filtros, incluir_balance)
    cuerpo.update(filtros_aplicados=filtros.aplicados(), calculado_en=datos["calculado_en"])
    return cuerpo
