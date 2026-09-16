"""
InventAI/o — Inventario Router
INV-005: Consulta de inventario y stock con semáforo.
Queries against fact_inventario (1.47M records) using raw SQL.
RBAC: admin_sucursal/admin_bodega see only their sucursal.
"""
import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import text

from core.database import get_db
from auth.dependencies import get_current_user
from models.usuario import Usuario
from schemas.inventario import (
    SEMAFORO_OK_MIN, SEMAFORO_BAJO_MIN,
    InventarioItem, InventarioList,
    InventarioDetalle, InventarioHistorialDia,
    InventarioResumen, InventarioResumenList, SemaforoContador,
    ValorizadoItem, ValorizadoList,
)

router = APIRouter(prefix="/api/consulta/inventario", tags=["Inventario"])

# ── Helpers ──────────────────────────────────────────

SEMAFORO_SQL = f"""
    CASE
        WHEN fi.dias_cobertura >= {SEMAFORO_OK_MIN} THEN 'ok'
        WHEN fi.dias_cobertura >= {SEMAFORO_BAJO_MIN} THEN 'bajo'
        ELSE 'critico'
    END
"""

def _get_fecha_inventario(db: Session) -> str:
    """Get the latest date with inventory data."""
    row = db.execute(text("""
        SELECT t.fecha
        FROM dw.fact_inventario fi
        JOIN dw.dim_tiempo t ON fi.id_tiempo = t.id_tiempo
        ORDER BY t.fecha DESC
        LIMIT 1
    """)).fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay datos de inventario disponibles",
        )
    return str(row.fecha)


def _sucursal_filter(user: Usuario) -> tuple:
    """Returns (SQL condition, params dict) for RBAC sucursal filtering."""
    if user.rol in ("gerente", "admin_bodega"):  # ← agregar admin_bodega
        return "", {}
    return "AND fi.id_sucursal = :user_sucursal", {"user_sucursal": user.id_sucursal}


# ── GET /api/consulta/inventario ─────────────────────
@router.get(
    "",
    response_model=InventarioList,
    summary="Stock actual con semáforo",
    description=(
        "Retorna el inventario más reciente por producto-sucursal con semáforo "
        "(ok >7d, bajo 3-7d, critico <3d). Filtros: categoría, semáforo, búsqueda. "
        "RBAC: admin_sucursal/admin_bodega ven solo su sucursal."
    ),
)
def listar_inventario(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    categoria: Optional[str] = Query(None, description="Filtrar por categoría"),
    semaforo: Optional[str] = Query(None, description="Filtrar: ok, bajo, critico"),
    sucursal_id: Optional[int] = Query(None, description="Filtrar por sucursal (gerente)"),
    busqueda: Optional[str] = Query(None, description="Buscar en nombre producto"),
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fecha = _get_fecha_inventario(db)
    rbac_sql, rbac_params = _sucursal_filter(user)

    # Build dynamic filters
    filters = []
    params = {"fecha": fecha, **rbac_params}

    if categoria:
        filters.append("p.categoria = :categoria")
        params["categoria"] = categoria
    if semaforo and semaforo in ("ok", "bajo", "critico"):
        if semaforo == "ok":
            filters.append(f"fi.dias_cobertura >= {SEMAFORO_OK_MIN}")
        elif semaforo == "bajo":
            filters.append(f"fi.dias_cobertura >= {SEMAFORO_BAJO_MIN} AND fi.dias_cobertura < {SEMAFORO_OK_MIN}")
        else:
            filters.append(f"fi.dias_cobertura < {SEMAFORO_BAJO_MIN}")
    if sucursal_id and user.rol in ("gerente", "admin_bodega"):
        filters.append("fi.id_sucursal = :sucursal_id")
        params["sucursal_id"] = sucursal_id
    if busqueda:
        filters.append("p.nombre ILIKE :busqueda")
        params["busqueda"] = f"%{busqueda}%"

    extra_where = (" AND " + " AND ".join(filters)) if filters else ""

    # Count
    count_sql = f"""
        SELECT COUNT(*)
        FROM dw.fact_inventario fi
        JOIN dw.dim_tiempo t ON fi.id_tiempo = t.id_tiempo
        JOIN dw.dim_producto p ON fi.id_producto = p.id_producto
        WHERE t.fecha = :fecha {rbac_sql} {extra_where}
    """
    total = db.execute(text(count_sql), params).scalar()

    # Paginated query
    offset = (page - 1) * page_size
    params["limit"] = page_size
    params["offset"] = offset

    query_sql = f"""
        SELECT fi.id_producto, p.nombre, p.categoria, p.es_perecedero,
               s.nombre AS sucursal, fi.id_sucursal,
               fi.stock_disponible, fi.stock_minimo, fi.stock_maximo,
               fi.punto_reorden, fi.dias_cobertura,
               {SEMAFORO_SQL} AS semaforo,
               t.fecha
        FROM dw.fact_inventario fi
        JOIN dw.dim_tiempo t ON fi.id_tiempo = t.id_tiempo
        JOIN dw.dim_producto p ON fi.id_producto = p.id_producto
        JOIN dw.dim_sucursal s ON fi.id_sucursal = s.id_sucursal
        WHERE t.fecha = :fecha {rbac_sql} {extra_where}
        ORDER BY fi.dias_cobertura ASC
        LIMIT :limit OFFSET :offset
    """
    rows = db.execute(text(query_sql), params).fetchall()

    items = [
        InventarioItem(
            id_producto=r.id_producto,
            nombre_producto=r.nombre,
            categoria=r.categoria,
            es_perecedero=r.es_perecedero,
            sucursal=r.sucursal,
            id_sucursal=r.id_sucursal,
            stock_disponible=float(r.stock_disponible),
            stock_minimo=float(r.stock_minimo),
            stock_maximo=float(r.stock_maximo),
            punto_reorden=float(r.punto_reorden),
            dias_cobertura=float(r.dias_cobertura),
            semaforo=r.semaforo,
            fecha=str(r.fecha),
        )
        for r in rows
    ]

    return InventarioList(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total > 0 else 0,
        fecha_inventario=fecha,
    )


# ── GET /api/consulta/inventario/detalle ─────────────
@router.get(
    "/detalle",
    response_model=InventarioDetalle,
    summary="Historial 30 días de un producto",
    description="Retorna el inventario actual y los últimos 30 días de un producto en una sucursal.",
)
def detalle_inventario(
    id_producto: int = Query(..., description="ID del producto"),
    id_sucursal: int = Query(..., description="ID de la sucursal"),
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # RBAC check
    if user.rol != "gerente" and user.id_sucursal != id_sucursal:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a esta sucursal",
        )

    fecha = _get_fecha_inventario(db)

    # Current state
    current = db.execute(text(f"""
        SELECT fi.stock_disponible, fi.stock_minimo, fi.stock_maximo,
               fi.punto_reorden, fi.dias_cobertura,
               {SEMAFORO_SQL} AS semaforo,
               p.nombre AS nombre_producto, p.categoria,
               s.nombre AS sucursal
        FROM dw.fact_inventario fi
        JOIN dw.dim_tiempo t ON fi.id_tiempo = t.id_tiempo
        JOIN dw.dim_producto p ON fi.id_producto = p.id_producto
        JOIN dw.dim_sucursal s ON fi.id_sucursal = s.id_sucursal
        WHERE t.fecha = :fecha
          AND fi.id_producto = :id_producto
          AND fi.id_sucursal = :id_sucursal
    """), {"fecha": fecha, "id_producto": id_producto, "id_sucursal": id_sucursal}).fetchone()

    if not current:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No hay inventario para producto {id_producto} en sucursal {id_sucursal}",
        )

    # 30-day history
    history_rows = db.execute(text(f"""
        SELECT t.fecha, fi.stock_disponible, fi.dias_cobertura,
               {SEMAFORO_SQL} AS semaforo
        FROM dw.fact_inventario fi
        JOIN dw.dim_tiempo t ON fi.id_tiempo = t.id_tiempo
        WHERE fi.id_producto = :id_producto
          AND fi.id_sucursal = :id_sucursal
          AND t.fecha > (CAST(:fecha AS DATE) - INTERVAL '30 days')
          AND t.fecha <= CAST(:fecha AS DATE)
        ORDER BY t.fecha ASC
    """), {"fecha": fecha, "id_producto": id_producto, "id_sucursal": id_sucursal}).fetchall()

    historial = [
        InventarioHistorialDia(
            fecha=str(r.fecha),
            stock_disponible=float(r.stock_disponible),
            dias_cobertura=float(r.dias_cobertura),
            semaforo=r.semaforo,
        )
        for r in history_rows
    ]

    return InventarioDetalle(
        id_producto=id_producto,
        nombre_producto=current.nombre_producto,
        categoria=current.categoria,
        sucursal=current.sucursal,
        id_sucursal=id_sucursal,
        stock_actual=float(current.stock_disponible),
        stock_minimo=float(current.stock_minimo),
        stock_maximo=float(current.stock_maximo),
        punto_reorden=float(current.punto_reorden),
        dias_cobertura=float(current.dias_cobertura),
        semaforo=current.semaforo,
        historial=historial,
    )


# ── GET /api/consulta/inventario/resumen ─────────────
@router.get(
    "/resumen",
    response_model=InventarioResumenList,
    summary="Contadores por semáforo",
    description="Retorna la cantidad de productos en cada estado del semáforo, por sucursal y global.",
)
def resumen_inventario(
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fecha = _get_fecha_inventario(db)
    rbac_sql, rbac_params = _sucursal_filter(user)
    params = {"fecha": fecha, **rbac_params}

    rows = db.execute(text(f"""
        SELECT s.nombre AS sucursal, fi.id_sucursal,
               SUM(CASE WHEN fi.dias_cobertura >= {SEMAFORO_OK_MIN} THEN 1 ELSE 0 END) AS ok,
               SUM(CASE WHEN fi.dias_cobertura >= {SEMAFORO_BAJO_MIN}
                         AND fi.dias_cobertura < {SEMAFORO_OK_MIN} THEN 1 ELSE 0 END) AS bajo,
               SUM(CASE WHEN fi.dias_cobertura < {SEMAFORO_BAJO_MIN} THEN 1 ELSE 0 END) AS critico,
               COUNT(*) AS total
        FROM dw.fact_inventario fi
        JOIN dw.dim_tiempo t ON fi.id_tiempo = t.id_tiempo
        JOIN dw.dim_sucursal s ON fi.id_sucursal = s.id_sucursal
        WHERE t.fecha = :fecha {rbac_sql}
        GROUP BY s.nombre, fi.id_sucursal
        ORDER BY fi.id_sucursal
    """), params).fetchall()

    items = []
    g_ok = g_bajo = g_crit = g_total = 0

    for r in rows:
        items.append(InventarioResumen(
            sucursal=r.sucursal,
            id_sucursal=r.id_sucursal,
            contadores=SemaforoContador(
                ok=r.ok, bajo=r.bajo, critico=r.critico, total=r.total,
            ),
            fecha_inventario=fecha,
        ))
        g_ok += r.ok
        g_bajo += r.bajo
        g_crit += r.critico
        g_total += r.total

    return InventarioResumenList(
        items=items,
        global_=SemaforoContador(ok=g_ok, bajo=g_bajo, critico=g_crit, total=g_total),
        fecha_inventario=fecha,
    )


# ── GET /api/consulta/inventario/valorizado ──────────
@router.get(
    "/valorizado",
    response_model=ValorizadoList,
    summary="Valor del stock por sucursal y categoría",
    description="Retorna el valor monetario del inventario actual agrupado por sucursal y categoría.",
)
def inventario_valorizado(
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fecha = _get_fecha_inventario(db)
    rbac_sql, rbac_params = _sucursal_filter(user)
    params = {"fecha": fecha, **rbac_params}

    rows = db.execute(text(f"""
        SELECT s.nombre AS sucursal, fi.id_sucursal,
               p.categoria,
               COUNT(DISTINCT fi.id_producto) AS total_productos,
               SUM(fi.stock_disponible) AS stock_total,
               SUM(fi.stock_disponible * p.precio_base) AS valor_stock
        FROM dw.fact_inventario fi
        JOIN dw.dim_tiempo t ON fi.id_tiempo = t.id_tiempo
        JOIN dw.dim_producto p ON fi.id_producto = p.id_producto
        JOIN dw.dim_sucursal s ON fi.id_sucursal = s.id_sucursal
        WHERE t.fecha = :fecha {rbac_sql}
        GROUP BY s.nombre, fi.id_sucursal, p.categoria
        ORDER BY valor_stock DESC
    """), params).fetchall()

    items = []
    total_valor = 0.0

    for r in rows:
        val = float(r.valor_stock) if r.valor_stock else 0.0
        items.append(ValorizadoItem(
            sucursal=r.sucursal,
            id_sucursal=r.id_sucursal,
            categoria=r.categoria,
            total_productos=r.total_productos,
            stock_total=float(r.stock_total),
            valor_stock=val,
        ))
        total_valor += val

    return ValorizadoList(
        items=items,
        total_valor=total_valor,
        fecha_inventario=fecha,
    )
