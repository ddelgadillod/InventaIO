"""
InventAI/o — Reportes Router
INV-006: Reportes de ventas, KPIs y análisis.
Queries against fact_ventas (510K records) + fact_inventario.
RBAC: admin_sucursal/admin_bodega see only their sucursal.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from core.database import get_db
from auth.dependencies import get_current_user
from models.usuario import Usuario
from schemas.reportes import (
    KPIs,
    VentaPeriodo, VentasReporte,
    ComparativaPeriodo, VentasComparativa,
    TopProducto, TopProductosList,
    TendenciaPunto, TendenciaSerie, TendenciasReporte,
    CategoriaDistribucion, DistribucionCategorias,
)

router = APIRouter(prefix="/api/reportes", tags=["Reportes"])


# ── Helpers ──────────────────────────────────────────

def _get_fecha_max(db: Session) -> str:
    """Latest date with sales data (reference date for KPIs)."""
    row = db.execute(text("""
        SELECT t.fecha FROM dw.fact_ventas v
        JOIN dw.dim_tiempo t ON v.id_tiempo = t.id_tiempo
        ORDER BY t.fecha DESC LIMIT 1
    """)).fetchone()
    if not row:
        raise HTTPException(404, "No hay datos de ventas")
    return str(row.fecha)


def _sucursal_filter(user: Usuario, alias: str = "v") -> tuple:
    if user.rol == "gerente":
        return "", {}
    return f"AND {alias}.id_sucursal = :user_sucursal", {"user_sucursal": user.id_sucursal}


def _build_suc_filter(user: Usuario, sucursal_id: Optional[int], alias: str = "v") -> tuple:
    """Combine RBAC + optional sucursal_id filter for gerente."""
    rbac_sql, params = _sucursal_filter(user, alias)
    if sucursal_id and user.rol == "gerente":
        rbac_sql += f" AND {alias}.id_sucursal = :suc_filter"
        params["suc_filter"] = sucursal_id
    return rbac_sql, params


# ── 1. GET /api/reportes/kpis ────────────────────────
@router.get(
    "/kpis",
    response_model=KPIs,
    summary="KPIs principales",
    description="ventas_hoy, ventas_mes, productos_en_riesgo, stock_valorizado.",
)
def kpis(
    sucursal_id: Optional[int] = Query(None),
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fecha = _get_fecha_max(db)
    suc_sql, params = _build_suc_filter(user, sucursal_id)
    params["fecha"] = fecha

    # Ventas hoy
    r = db.execute(text(f"""
        SELECT COALESCE(SUM(v.valor_total), 0) AS ventas_hoy
        FROM dw.fact_ventas v
        JOIN dw.dim_tiempo t ON v.id_tiempo = t.id_tiempo
        WHERE t.fecha = :fecha AND NOT v.es_devolucion {suc_sql}
    """), params).fetchone()
    ventas_hoy = float(r.ventas_hoy)

    # Ventas mismo día semana anterior (para variación)
    r2 = db.execute(text(f"""
        SELECT COALESCE(SUM(v.valor_total), 0) AS ventas_ant
        FROM dw.fact_ventas v
        JOIN dw.dim_tiempo t ON v.id_tiempo = t.id_tiempo
        WHERE t.fecha = (CAST(:fecha AS DATE) - INTERVAL '7 days')
          AND NOT v.es_devolucion {suc_sql}
    """), params).fetchone()
    ventas_ant_dia = float(r2.ventas_ant)
    var_hoy = round((ventas_hoy - ventas_ant_dia) / ventas_ant_dia * 100, 1) if ventas_ant_dia > 0 else None

    # Ventas del mes
    r3 = db.execute(text(f"""
        SELECT COALESCE(SUM(v.valor_total), 0) AS ventas_mes
        FROM dw.fact_ventas v
        JOIN dw.dim_tiempo t ON v.id_tiempo = t.id_tiempo
        WHERE t.anio = EXTRACT(YEAR FROM CAST(:fecha AS DATE))
          AND t.mes = EXTRACT(MONTH FROM CAST(:fecha AS DATE))
          AND NOT v.es_devolucion {suc_sql}
    """), params).fetchone()
    ventas_mes = float(r3.ventas_mes)

    # Ventas mes anterior
    r4 = db.execute(text(f"""
        SELECT COALESCE(SUM(v.valor_total), 0) AS ventas_ant
        FROM dw.fact_ventas v
        JOIN dw.dim_tiempo t ON v.id_tiempo = t.id_tiempo
        WHERE t.anio = EXTRACT(YEAR FROM CAST(:fecha AS DATE) - INTERVAL '1 month')
          AND t.mes = EXTRACT(MONTH FROM CAST(:fecha AS DATE) - INTERVAL '1 month')
          AND NOT v.es_devolucion {suc_sql}
    """), params).fetchone()
    ventas_ant_mes = float(r4.ventas_ant)
    var_mes = round((ventas_mes - ventas_ant_mes) / ventas_ant_mes * 100, 1) if ventas_ant_mes > 0 else None

    # Productos en riesgo (semáforo bajo + critico)
    suc_sql_fi, params_fi = _build_suc_filter(user, sucursal_id, "fi")
    params_fi["fecha"] = fecha
    r5 = db.execute(text(f"""
        SELECT COUNT(*) AS en_riesgo
        FROM dw.fact_inventario fi
        JOIN dw.dim_tiempo t ON fi.id_tiempo = t.id_tiempo
        WHERE t.fecha = :fecha AND fi.dias_cobertura < 7.0 {suc_sql_fi}
    """), params_fi).fetchone()
    productos_en_riesgo = r5.en_riesgo

    # Stock valorizado
    r6 = db.execute(text(f"""
        SELECT COALESCE(SUM(fi.stock_disponible * p.precio_base), 0) AS valor
        FROM dw.fact_inventario fi
        JOIN dw.dim_tiempo t ON fi.id_tiempo = t.id_tiempo
        JOIN dw.dim_producto p ON fi.id_producto = p.id_producto
        WHERE t.fecha = :fecha {suc_sql_fi}
    """), params_fi).fetchone()
    stock_valorizado = float(r6.valor)

    return KPIs(
        ventas_hoy=ventas_hoy,
        ventas_mes=ventas_mes,
        productos_en_riesgo=productos_en_riesgo,
        stock_valorizado=stock_valorizado,
        fecha_referencia=fecha,
        variacion_ventas_hoy_pct=var_hoy,
        variacion_ventas_mes_pct=var_mes,
    )


# ── 2. GET /api/reportes/ventas ──────────────────────
@router.get(
    "/ventas",
    response_model=VentasReporte,
    summary="Ventas con filtros y agrupación",
    description="Filtros: fecha_inicio, fecha_fin, sucursal, categoría. Agrupación: dia, semana, mes.",
)
def ventas(
    fecha_inicio: Optional[str] = Query(None, description="YYYY-MM-DD"),
    fecha_fin: Optional[str] = Query(None, description="YYYY-MM-DD"),
    sucursal_id: Optional[int] = Query(None),
    categoria: Optional[str] = Query(None),
    agrupacion: str = Query("dia", description="dia, semana, mes"),
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fecha_max = _get_fecha_max(db)
    if not fecha_fin:
        fecha_fin = fecha_max
    if not fecha_inicio:
        fecha_inicio = f"{fecha_fin[:7]}-01"  # primer día del mes

    suc_sql, params = _build_suc_filter(user, sucursal_id)
    params["fi"] = fecha_inicio
    params["ff"] = fecha_fin

    extra = ""
    if categoria:
        extra += " AND p.categoria = :cat"
        params["cat"] = categoria

    # Agrupación SQL
    if agrupacion == "semana":
        group_expr = "TO_CHAR(t.fecha, 'IYYY') || '-W' || TO_CHAR(t.fecha, 'IW')"
    elif agrupacion == "mes":
        group_expr = "TO_CHAR(t.fecha, 'YYYY-MM')"
    else:
        group_expr = "TO_CHAR(t.fecha, 'YYYY-MM-DD')"
        agrupacion = "dia"

    rows = db.execute(text(f"""
        SELECT {group_expr} AS periodo,
               SUM(v.cantidad) AS cantidad,
               SUM(v.valor_total) AS valor_total,
               SUM(v.costo_total) AS costo_total,
               COUNT(*) AS transacciones
        FROM dw.fact_ventas v
        JOIN dw.dim_tiempo t ON v.id_tiempo = t.id_tiempo
        JOIN dw.dim_producto p ON v.id_producto = p.id_producto
        WHERE t.fecha BETWEEN :fi AND :ff
          AND NOT v.es_devolucion
          {suc_sql} {extra}
        GROUP BY {group_expr}
        ORDER BY periodo
    """), params).fetchall()

    items = [
        VentaPeriodo(
            periodo=r.periodo,
            cantidad=float(r.cantidad),
            valor_total=float(r.valor_total),
            costo_total=float(r.costo_total),
            margen=float(r.valor_total) - float(r.costo_total),
            transacciones=r.transacciones,
        )
        for r in rows
    ]

    return VentasReporte(
        items=items,
        total_cantidad=sum(i.cantidad for i in items),
        total_valor=sum(i.valor_total for i in items),
        total_margen=sum(i.margen for i in items),
        agrupacion=agrupacion,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
    )


# ── 3. GET /api/reportes/ventas/comparativa ──────────
@router.get(
    "/ventas/comparativa",
    response_model=VentasComparativa,
    summary="Comparativa periodo actual vs anterior",
    description="Compara ventas del rango dado vs el mismo rango desplazado.",
)
def ventas_comparativa(
    fecha_inicio: Optional[str] = Query(None),
    fecha_fin: Optional[str] = Query(None),
    sucursal_id: Optional[int] = Query(None),
    agrupacion: str = Query("dia"),
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fecha_max = _get_fecha_max(db)
    if not fecha_fin:
        fecha_fin = fecha_max
    if not fecha_inicio:
        fecha_inicio = f"{fecha_fin[:7]}-01"

    suc_sql, params = _build_suc_filter(user, sucursal_id)
    params["fi"] = fecha_inicio
    params["ff"] = fecha_fin

    # Calculate period length for offset
    # Actual period
    r_actual = db.execute(text(f"""
        SELECT SUM(v.valor_total) AS valor, SUM(v.cantidad) AS cantidad
        FROM dw.fact_ventas v
        JOIN dw.dim_tiempo t ON v.id_tiempo = t.id_tiempo
        WHERE t.fecha BETWEEN :fi AND :ff
          AND NOT v.es_devolucion {suc_sql}
    """), params).fetchone()

    # Previous period (same length, shifted back)
    r_ant = db.execute(text(f"""
        SELECT SUM(v.valor_total) AS valor, SUM(v.cantidad) AS cantidad
        FROM dw.fact_ventas v
        JOIN dw.dim_tiempo t ON v.id_tiempo = t.id_tiempo
        WHERE t.fecha BETWEEN
              (CAST(:fi AS DATE) - (CAST(:ff AS DATE) - CAST(:fi AS DATE)) - INTERVAL '1 day')
              AND (CAST(:fi AS DATE) - INTERVAL '1 day')
          AND NOT v.es_devolucion {suc_sql}
    """), params).fetchone()

    val_act = float(r_actual.valor or 0)
    val_ant = float(r_ant.valor or 0)
    var_pct = round((val_act - val_ant) / val_ant * 100, 1) if val_ant > 0 else 0.0

    # Detail for current period
    if agrupacion == "semana":
        group_expr = "TO_CHAR(t.fecha, 'IYYY') || '-W' || TO_CHAR(t.fecha, 'IW')"
    elif agrupacion == "mes":
        group_expr = "TO_CHAR(t.fecha, 'YYYY-MM')"
    else:
        group_expr = "TO_CHAR(t.fecha, 'YYYY-MM-DD')"
        agrupacion = "dia"

    rows = db.execute(text(f"""
        SELECT {group_expr} AS periodo,
               SUM(v.cantidad) AS cantidad,
               SUM(v.valor_total) AS valor_total,
               SUM(v.costo_total) AS costo_total,
               COUNT(*) AS transacciones
        FROM dw.fact_ventas v
        JOIN dw.dim_tiempo t ON v.id_tiempo = t.id_tiempo
        WHERE t.fecha BETWEEN :fi AND :ff
          AND NOT v.es_devolucion {suc_sql}
        GROUP BY {group_expr}
        ORDER BY periodo
    """), params).fetchall()

    detalle = [
        VentaPeriodo(
            periodo=r.periodo,
            cantidad=float(r.cantidad),
            valor_total=float(r.valor_total),
            costo_total=float(r.costo_total),
            margen=float(r.valor_total) - float(r.costo_total),
            transacciones=r.transacciones,
        )
        for r in rows
    ]

    return VentasComparativa(
        resumen=ComparativaPeriodo(
            periodo_actual=f"{fecha_inicio} / {fecha_fin}",
            periodo_anterior="periodo equivalente anterior",
            valor_actual=val_act,
            valor_anterior=val_ant,
            variacion_pct=var_pct,
            cantidad_actual=float(r_actual.cantidad or 0),
            cantidad_anterior=float(r_ant.cantidad or 0),
        ),
        detalle=detalle,
        agrupacion=agrupacion,
    )


# ── 4. GET /api/reportes/ventas/top-productos ────────
@router.get(
    "/ventas/top-productos",
    response_model=TopProductosList,
    summary="Top productos por ventas",
)
def top_productos(
    limite: int = Query(10, ge=1, le=50),
    fecha_inicio: Optional[str] = Query(None),
    fecha_fin: Optional[str] = Query(None),
    sucursal_id: Optional[int] = Query(None),
    categoria: Optional[str] = Query(None),
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fecha_max = _get_fecha_max(db)
    if not fecha_fin:
        fecha_fin = fecha_max
    if not fecha_inicio:
        fecha_inicio = f"{fecha_fin[:7]}-01"

    suc_sql, params = _build_suc_filter(user, sucursal_id)
    params["fi"] = fecha_inicio
    params["ff"] = fecha_fin
    params["limite"] = limite

    extra = ""
    if categoria:
        extra += " AND p.categoria = :cat"
        params["cat"] = categoria

    # Total for participation %
    r_total = db.execute(text(f"""
        SELECT COALESCE(SUM(v.valor_total), 0) AS total
        FROM dw.fact_ventas v
        JOIN dw.dim_tiempo t ON v.id_tiempo = t.id_tiempo
        JOIN dw.dim_producto p ON v.id_producto = p.id_producto
        WHERE t.fecha BETWEEN :fi AND :ff
          AND NOT v.es_devolucion {suc_sql} {extra}
    """), params).fetchone()
    total_valor = float(r_total.total)

    rows = db.execute(text(f"""
        SELECT v.id_producto, p.nombre, p.categoria,
               SUM(v.cantidad) AS cantidad,
               SUM(v.valor_total) AS valor_total,
               SUM(v.valor_total) - SUM(v.costo_total) AS margen
        FROM dw.fact_ventas v
        JOIN dw.dim_tiempo t ON v.id_tiempo = t.id_tiempo
        JOIN dw.dim_producto p ON v.id_producto = p.id_producto
        WHERE t.fecha BETWEEN :fi AND :ff
          AND NOT v.es_devolucion {suc_sql} {extra}
        GROUP BY v.id_producto, p.nombre, p.categoria
        ORDER BY valor_total DESC
        LIMIT :limite
    """), params).fetchall()

    items = [
        TopProducto(
            id_producto=r.id_producto,
            nombre=r.nombre,
            categoria=r.categoria,
            cantidad=float(r.cantidad),
            valor_total=float(r.valor_total),
            margen=float(r.margen),
            participacion_pct=round(float(r.valor_total) / total_valor * 100, 2) if total_valor > 0 else 0,
        )
        for r in rows
    ]

    return TopProductosList(
        items=items,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        total_valor=total_valor,
    )


# ── 5. GET /api/reportes/tendencias ──────────────────
@router.get(
    "/tendencias",
    response_model=TendenciasReporte,
    summary="Series de tiempo de ventas",
    description="Ventas diarias con promedio móvil 7 días. Por sucursal o global.",
)
def tendencias(
    fecha_inicio: Optional[str] = Query(None),
    fecha_fin: Optional[str] = Query(None),
    sucursal_id: Optional[int] = Query(None),
    por_sucursal: bool = Query(False, description="Desglosar por sucursal"),
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fecha_max = _get_fecha_max(db)
    if not fecha_fin:
        fecha_fin = fecha_max
    if not fecha_inicio:
        # Default: últimos 30 días
        fecha_inicio = str(db.execute(text(
            "SELECT CAST(:ff AS DATE) - INTERVAL '30 days'"
        ), {"ff": fecha_fin}).scalar())[:10]

    suc_sql, params = _build_suc_filter(user, sucursal_id)
    params["fi"] = fecha_inicio
    params["ff"] = fecha_fin

    if por_sucursal:
        group_cols = "s.nombre, t.fecha"
        select_extra = "s.nombre AS sucursal,"
        join_extra = "JOIN dw.dim_sucursal s ON v.id_sucursal = s.id_sucursal"
    else:
        group_cols = "t.fecha"
        select_extra = "NULL AS sucursal,"
        join_extra = ""

    rows = db.execute(text(f"""
        SELECT {select_extra}
               t.fecha,
               SUM(v.valor_total) AS valor_total,
               SUM(v.cantidad) AS cantidad
        FROM dw.fact_ventas v
        JOIN dw.dim_tiempo t ON v.id_tiempo = t.id_tiempo
        {join_extra}
        WHERE t.fecha BETWEEN :fi AND :ff
          AND NOT v.es_devolucion {suc_sql}
        GROUP BY {group_cols}
        ORDER BY {group_cols}
    """), params).fetchall()

    # Build series
    series_map = {}
    for r in rows:
        key = r.sucursal or "Global"
        if key not in series_map:
            series_map[key] = []
        series_map[key].append({
            "fecha": str(r.fecha),
            "valor_total": float(r.valor_total),
            "cantidad": float(r.cantidad),
        })

    # Calculate 7-day moving average
    series = []
    for suc_name, puntos in series_map.items():
        processed = []
        for i, p in enumerate(puntos):
            window = puntos[max(0, i - 6):i + 1]
            ma7 = round(sum(w["valor_total"] for w in window) / len(window), 2)
            processed.append(TendenciaPunto(
                fecha=p["fecha"],
                valor_total=p["valor_total"],
                cantidad=p["cantidad"],
                promedio_movil_7d=ma7,
            ))
        series.append(TendenciaSerie(
            sucursal=suc_name if suc_name != "Global" else None,
            puntos=processed,
        ))

    return TendenciasReporte(
        series=series,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
    )


# ── 6. GET /api/reportes/distribucion-categorias ─────
@router.get(
    "/distribucion-categorias",
    response_model=DistribucionCategorias,
    summary="Distribución de ventas por categoría",
)
def distribucion_categorias(
    fecha_inicio: Optional[str] = Query(None),
    fecha_fin: Optional[str] = Query(None),
    sucursal_id: Optional[int] = Query(None),
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fecha_max = _get_fecha_max(db)
    if not fecha_fin:
        fecha_fin = fecha_max
    if not fecha_inicio:
        fecha_inicio = f"{fecha_fin[:7]}-01"

    suc_sql, params = _build_suc_filter(user, sucursal_id)
    params["fi"] = fecha_inicio
    params["ff"] = fecha_fin

    # Total
    r_total = db.execute(text(f"""
        SELECT COALESCE(SUM(v.valor_total), 0) AS total
        FROM dw.fact_ventas v
        JOIN dw.dim_tiempo t ON v.id_tiempo = t.id_tiempo
        WHERE t.fecha BETWEEN :fi AND :ff
          AND NOT v.es_devolucion {suc_sql}
    """), params).fetchone()
    total_valor = float(r_total.total)

    rows = db.execute(text(f"""
        SELECT p.categoria,
               SUM(v.cantidad) AS cantidad,
               SUM(v.valor_total) AS valor_total,
               SUM(v.valor_total) - SUM(v.costo_total) AS margen,
               COUNT(DISTINCT v.id_producto) AS num_productos
        FROM dw.fact_ventas v
        JOIN dw.dim_tiempo t ON v.id_tiempo = t.id_tiempo
        JOIN dw.dim_producto p ON v.id_producto = p.id_producto
        WHERE t.fecha BETWEEN :fi AND :ff
          AND NOT v.es_devolucion {suc_sql}
        GROUP BY p.categoria
        ORDER BY valor_total DESC
    """), params).fetchall()

    items = [
        CategoriaDistribucion(
            categoria=r.categoria,
            cantidad=float(r.cantidad),
            valor_total=float(r.valor_total),
            margen=float(r.margen),
            participacion_pct=round(float(r.valor_total) / total_valor * 100, 2) if total_valor > 0 else 0,
            num_productos=r.num_productos,
        )
        for r in rows
    ]

    return DistribucionCategorias(
        items=items,
        total_valor=total_valor,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
    )
