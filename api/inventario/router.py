"""
InventAI/o — Inventario Router
INV-005: Consulta de inventario y stock con semáforo.
Queries against fact_inventario using raw SQL.
RBAC (INV-25, core/ubicaciones.py): gerente/admin_bodega ven todo;
admin_sucursal ve su sucursal y, a pedido, el stock de la Bodega Central.
"""
import math

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from core.database import get_db
from core.productos import unidad_venta
from core.semaforo import SEMAFORO_CONDICION, SEMAFORO_SQL
from core.ubicaciones import SQL_TIPO_UBICACION, STOCK, filtro_sucursal
from models.usuario import Usuario
from schemas.inventario import (
    InventarioDetalle,
    InventarioHistorialDia,
    InventarioItem,
    InventarioList,
    InventarioResumen,
    InventarioResumenList,
    SemaforoContador,
    ValorizadoItem,
    ValorizadoList,
)

router = APIRouter(prefix="/api/consulta/inventario", tags=["Inventario"])

DESC_SUCURSAL = ("Filtrar por sucursal. admin_sucursal: la suya o la Bodega Central; "
                 "otra da 403. Un id inexistente o SIN_SUCURSAL da 422.")

# ── Helpers ──────────────────────────────────────────

# INV-25 (D2, R3): stock de la Bodega Central para el mismo producto y fecha;
# 0 si la Bodega no tiene fila, nulo en las filas de la propia Bodega.
SQL_JOIN_BODEGA = """
    LEFT JOIN (
        SELECT fb.id_producto, fb.id_tiempo, fb.stock_disponible
        FROM dw.fact_inventario fb
        JOIN dw.dim_sucursal sb ON sb.id_sucursal = fb.id_sucursal AND sb.tipo = 'bodega_central'
    ) b ON b.id_producto = fi.id_producto AND b.id_tiempo = fi.id_tiempo
"""
SQL_STOCK_BODEGA = "CASE WHEN s.tipo = 'bodega_central' THEN NULL ELSE COALESCE(b.stock_disponible, 0) END"


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


def _float(valor) -> float | None:
    return float(valor) if valor is not None else None


# ── GET /api/consulta/inventario ─────────────────────
@router.get(
    "",
    response_model=InventarioList,
    summary="Stock actual con semáforo",
    description=(
        "Retorna el inventario más reciente por producto-sucursal con semáforo "
        "(inconsistencia: stock negativo; si no, ok >7d, bajo 3-7d, critico <3d). Filtros: categoría, "
        "semáforo, búsqueda, sucursal. Cada fila trae tipo_ubicacion, stock_bodega (stock de la Bodega "
        "Central del mismo producto) y unidad ('kg' si se vende por kilo; si no, 'unidad'). "
        "RBAC: admin_sucursal ve su sucursal y, con sucursal_id, el stock de la Bodega Central."
    ),
)
def listar_inventario(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    categoria: str | None = Query(None, description="Filtrar por categoría"),
    semaforo: str | None = Query(None, description="Filtrar: ok, bajo, critico, inconsistencia"),
    sucursal_id: int | None = Query(None, description=DESC_SUCURSAL),
    busqueda: str | None = Query(None, description="Buscar en nombre producto"),
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fecha = _get_fecha_inventario(db)
    rbac_sql, rbac_params = filtro_sucursal(db, user, sucursal_id, STOCK, "fi")

    # Build dynamic filters
    filters = []
    params = {"fecha": fecha, **rbac_params}

    if categoria:
        filters.append("p.categoria = :categoria")
        params["categoria"] = categoria
    if semaforo in SEMAFORO_CONDICION:
        filters.append(SEMAFORO_CONDICION[semaforo])
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
        SELECT fi.id_producto, p.nombre, p.categoria, p.es_perecedero, p.se_vende_por_kilo,
               s.nombre AS sucursal, fi.id_sucursal,
               {SQL_TIPO_UBICACION} AS tipo_ubicacion,
               fi.stock_disponible, {SQL_STOCK_BODEGA} AS stock_bodega,
               fi.stock_minimo, fi.stock_maximo,
               fi.punto_reorden, fi.dias_cobertura,
               {SEMAFORO_SQL} AS semaforo,
               t.fecha
        FROM dw.fact_inventario fi
        JOIN dw.dim_tiempo t ON fi.id_tiempo = t.id_tiempo
        JOIN dw.dim_producto p ON fi.id_producto = p.id_producto
        JOIN dw.dim_sucursal s ON fi.id_sucursal = s.id_sucursal
        {SQL_JOIN_BODEGA}
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
            unidad=unidad_venta(r.se_vende_por_kilo),
            sucursal=r.sucursal,
            id_sucursal=r.id_sucursal,
            tipo_ubicacion=r.tipo_ubicacion,
            stock_disponible=float(r.stock_disponible),
            stock_bodega=_float(r.stock_bodega),
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
    description=(
        "Retorna el inventario actual y los últimos 30 días de un producto en una sucursal, con "
        "tipo_ubicacion y stock_bodega. Con la bodega real hay una sola foto: el historial trae un punto. "
        "RBAC: admin_sucursal, su sucursal o la Bodega Central."
    ),
)
def detalle_inventario(
    id_producto: int = Query(..., description="ID del producto"),
    id_sucursal: int = Query(..., description="ID de la sucursal"),
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # RBAC (INV-25): 403 fuera de lo permitido, 422 si la sucursal no existe
    filtro_sucursal(db, user, id_sucursal, STOCK, "fi")

    fecha = _get_fecha_inventario(db)

    # Current state
    current = db.execute(text(f"""
        SELECT fi.stock_disponible, fi.stock_minimo, fi.stock_maximo,
               fi.punto_reorden, fi.dias_cobertura,
               {SEMAFORO_SQL} AS semaforo,
               p.nombre AS nombre_producto, p.categoria,
               s.nombre AS sucursal,
               {SQL_TIPO_UBICACION} AS tipo_ubicacion,
               {SQL_STOCK_BODEGA} AS stock_bodega
        FROM dw.fact_inventario fi
        JOIN dw.dim_tiempo t ON fi.id_tiempo = t.id_tiempo
        JOIN dw.dim_producto p ON fi.id_producto = p.id_producto
        JOIN dw.dim_sucursal s ON fi.id_sucursal = s.id_sucursal
        {SQL_JOIN_BODEGA}
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
        tipo_ubicacion=current.tipo_ubicacion,
        stock_actual=float(current.stock_disponible),
        stock_bodega=_float(current.stock_bodega),
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
    description=(
        "Retorna la cantidad de productos en cada estado del semáforo (ok, bajo, critico e "
        "inconsistencia), por sucursal y global. Con sucursal_id, solo esa ubicación."
    ),
)
def resumen_inventario(
    sucursal_id: int | None = Query(None, description=DESC_SUCURSAL),
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fecha = _get_fecha_inventario(db)
    rbac_sql, rbac_params = filtro_sucursal(db, user, sucursal_id, STOCK, "fi")
    params = {"fecha": fecha, **rbac_params}

    conteos = ", ".join(f"SUM(CASE WHEN {cond} THEN 1 ELSE 0 END) AS {estado}"
                        for estado, cond in SEMAFORO_CONDICION.items())
    rows = db.execute(text(f"""
        SELECT s.nombre AS sucursal, fi.id_sucursal,
               {SQL_TIPO_UBICACION} AS tipo_ubicacion,
               {conteos},
               COUNT(*) AS total
        FROM dw.fact_inventario fi
        JOIN dw.dim_tiempo t ON fi.id_tiempo = t.id_tiempo
        JOIN dw.dim_sucursal s ON fi.id_sucursal = s.id_sucursal
        WHERE t.fecha = :fecha {rbac_sql}
        GROUP BY s.nombre, fi.id_sucursal, s.tipo
        ORDER BY fi.id_sucursal
    """), params).fetchall()

    claves = [*SEMAFORO_CONDICION, "total"]
    items = []
    global_ = dict.fromkeys(claves, 0)

    for r in rows:
        contadores = {k: getattr(r, k) for k in claves}
        items.append(InventarioResumen(
            sucursal=r.sucursal,
            id_sucursal=r.id_sucursal,
            tipo_ubicacion=r.tipo_ubicacion,
            contadores=SemaforoContador(**contadores),
            fecha_inventario=fecha,
        ))
        for k in claves:
            global_[k] += contadores[k]

    return InventarioResumenList(
        items=items,
        global_=SemaforoContador(**global_),
        fecha_inventario=fecha,
    )


# ── GET /api/consulta/inventario/valorizado ──────────
@router.get(
    "/valorizado",
    response_model=ValorizadoList,
    summary="Valor del stock por sucursal y categoría",
    description=(
        "Retorna el valor monetario del inventario actual agrupado por sucursal y categoría. "
        "Con sucursal_id, solo esa ubicación."
    ),
)
def inventario_valorizado(
    sucursal_id: int | None = Query(None, description=DESC_SUCURSAL),
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fecha = _get_fecha_inventario(db)
    rbac_sql, rbac_params = filtro_sucursal(db, user, sucursal_id, STOCK, "fi")
    params = {"fecha": fecha, **rbac_params}

    rows = db.execute(text(f"""
        SELECT s.nombre AS sucursal, fi.id_sucursal,
               {SQL_TIPO_UBICACION} AS tipo_ubicacion,
               p.categoria,
               COUNT(DISTINCT fi.id_producto) AS total_productos,
               SUM(fi.stock_disponible) AS stock_total,
               SUM(fi.stock_disponible * p.precio_base) AS valor_stock
        FROM dw.fact_inventario fi
        JOIN dw.dim_tiempo t ON fi.id_tiempo = t.id_tiempo
        JOIN dw.dim_producto p ON fi.id_producto = p.id_producto
        JOIN dw.dim_sucursal s ON fi.id_sucursal = s.id_sucursal
        WHERE t.fecha = :fecha {rbac_sql}
        GROUP BY s.nombre, fi.id_sucursal, s.tipo, p.categoria
        ORDER BY valor_stock DESC
    """), params).fetchall()

    items = []
    total_valor = 0.0

    for r in rows:
        val = float(r.valor_stock) if r.valor_stock else 0.0
        items.append(ValorizadoItem(
            sucursal=r.sucursal,
            id_sucursal=r.id_sucursal,
            tipo_ubicacion=r.tipo_ubicacion,
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
