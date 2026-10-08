"""
InventAI/o — Reportes Router
INV-006: Reportes de ventas, KPIs y análisis.
Queries against fact_ventas + fact_inventario.
RBAC (INV-25, core/ubicaciones.py): gerente/admin_bodega ven todo y filtran
por cualquier ubicación; admin_sucursal solo su sucursal.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from core.database import get_db
from core.semaforo import SEMAFORO_EN_RIESGO
from core.ubicaciones import VENTAS, filtro_sucursal
from models.usuario import Usuario
from schemas.reportes import (
    CategoriaDistribucion,
    ComparativaPeriodo,
    DistribucionCategorias,
    KPIs,
    TendenciaPunto,
    TendenciaSerie,
    TendenciasReporte,
    TopProducto,
    TopProductosList,
    VentaPeriodo,
    VentasComparativa,
    VentasReporte,
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


def _get_rango_datos(db: Session) -> tuple:
    """Primera y última fecha con ventas (INV-26 fix, K7): los atajos de la
    vista de reportes no fijan fechas en el código."""
    # Recorre las fechas de dim_tiempo, no los 2 millones de ventas
    row = db.execute(text("""
        SELECT MIN(t.fecha) AS desde, MAX(t.fecha) AS hasta FROM dw.dim_tiempo t
        WHERE EXISTS (SELECT 1 FROM dw.fact_ventas v WHERE v.id_tiempo = t.id_tiempo)
    """)).fetchone()
    return str(row.desde), str(row.hasta)


def _build_suc_filter(db: Session, user: Usuario, sucursal_id: int | None, alias: str = "v") -> tuple:
    """RBAC + filtro opcional sucursal_id (INV-25): 403 fuera de lo permitido, 422 si no existe."""
    return filtro_sucursal(db, user, sucursal_id, VENTAS, alias)


def _expr_agrupacion(agrupacion: str) -> tuple:
    """(expresión SQL del período sobre dim_tiempo t, agrupación normalizada)."""
    if agrupacion == "semana":
        return "TO_CHAR(t.fecha, 'IYYY') || '-W' || TO_CHAR(t.fecha, 'IW')", "semana"
    if agrupacion == "mes":
        return "TO_CHAR(t.fecha, 'YYYY-MM')", "mes"
    return "TO_CHAR(t.fecha, 'YYYY-MM-DD')", "dia"


def _filtro_categoria(categoria: str | None, params: dict) -> str:
    """Condición SQL por categoría del producto (alias p), o vacía."""
    if not categoria:
        return ""
    params["cat"] = categoria
    return " AND p.categoria = :cat"


DESC_SUCURSAL = ("Filtrar por sucursal. admin_sucursal: solo la suya; otra da 403. "
                 "Inexistente o SIN_SUCURSAL, 422")


# ── 1. GET /api/reportes/kpis ────────────────────────
@router.get(
    "/kpis",
    response_model=KPIs,
    summary="KPIs principales",
    description=("ventas_hoy, ventas_mes, productos_en_riesgo (semáforo bajo + crítico; el stock "
                 "negativo cuenta como inconsistencia, no en riesgo), stock_valorizado."),
)
def kpis(
    sucursal_id: int | None = Query(None, description=DESC_SUCURSAL),
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fecha = _get_fecha_max(db)
    suc_sql, params = _build_suc_filter(db, user, sucursal_id)
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

    # Productos en riesgo: tramos bajo y crítico del semáforo (INV-26 fix, K9;
    # antes, cobertura < 7 días, que también contaba stock negativo)
    suc_sql_fi, params_fi = _build_suc_filter(db, user, sucursal_id, "fi")
    params_fi["fecha"] = fecha
    r5 = db.execute(text(f"""
        SELECT COUNT(*) AS en_riesgo
        FROM dw.fact_inventario fi
        JOIN dw.dim_tiempo t ON fi.id_tiempo = t.id_tiempo
        WHERE t.fecha = :fecha AND ({SEMAFORO_EN_RIESGO}) {suc_sql_fi}
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
    description=(
        "Filtros: fecha_inicio, fecha_fin, sucursal, categoría. Agrupación: dia, semana, mes. "
        "datos_desde y datos_hasta: la primera y la última fecha con ventas."
    ),
)
def ventas(
    fecha_inicio: str | None = Query(None, description="YYYY-MM-DD"),
    fecha_fin: str | None = Query(None, description="YYYY-MM-DD"),
    sucursal_id: int | None = Query(None, description=DESC_SUCURSAL),
    categoria: str | None = Query(None),
    agrupacion: str = Query("dia", description="dia, semana, mes"),
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fecha_max = _get_fecha_max(db)
    if not fecha_fin:
        fecha_fin = fecha_max
    if not fecha_inicio:
        fecha_inicio = f"{fecha_fin[:7]}-01"  # primer día del mes

    suc_sql, params = _build_suc_filter(db, user, sucursal_id)
    params["fi"] = fecha_inicio
    params["ff"] = fecha_fin
    extra = _filtro_categoria(categoria, params)
    group_expr, agrupacion = _expr_agrupacion(agrupacion)

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

    datos_desde, datos_hasta = _get_rango_datos(db)
    return VentasReporte(
        items=items,
        total_cantidad=sum(i.cantidad for i in items),
        total_valor=sum(i.valor_total for i in items),
        total_margen=sum(i.margen for i in items),
        agrupacion=agrupacion,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        datos_desde=datos_desde,
        datos_hasta=datos_hasta,
    )


# ── 3. GET /api/reportes/ventas/comparativa ──────────
@router.get(
    "/ventas/comparativa",
    response_model=VentasComparativa,
    summary="Comparativa periodo actual vs anterior",
    description=(
        "Compara ventas del rango dado vs el mismo rango desplazado hacia atrás (periodo_anterior trae "
        "sus fechas). Filtros: sucursal y categoría (INV-26 fix)."
    ),
)
def ventas_comparativa(
    fecha_inicio: str | None = Query(None),
    fecha_fin: str | None = Query(None),
    sucursal_id: int | None = Query(None, description=DESC_SUCURSAL),
    categoria: str | None = Query(None),
    agrupacion: str = Query("dia"),
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fecha_max = _get_fecha_max(db)
    if not fecha_fin:
        fecha_fin = fecha_max
    if not fecha_inicio:
        fecha_inicio = f"{fecha_fin[:7]}-01"

    # Período anterior: el mismo largo, justo antes del actual
    inicio, fin = date.fromisoformat(fecha_inicio), date.fromisoformat(fecha_fin)
    fin_ant = inicio - timedelta(days=1)
    inicio_ant = fin_ant - (fin - inicio)

    suc_sql, params = _build_suc_filter(db, user, sucursal_id)
    params.update(fi=fecha_inicio, ff=fecha_fin, fi_ant=inicio_ant, ff_ant=fin_ant)
    extra = _filtro_categoria(categoria, params)
    desde = """FROM dw.fact_ventas v
        JOIN dw.dim_tiempo t ON v.id_tiempo = t.id_tiempo
        JOIN dw.dim_producto p ON v.id_producto = p.id_producto"""

    r_actual = db.execute(text(f"""
        SELECT SUM(v.valor_total) AS valor, SUM(v.cantidad) AS cantidad
        {desde}
        WHERE t.fecha BETWEEN :fi AND :ff
          AND NOT v.es_devolucion {suc_sql} {extra}
    """), params).fetchone()
    r_ant = db.execute(text(f"""
        SELECT SUM(v.valor_total) AS valor, SUM(v.cantidad) AS cantidad
        {desde}
        WHERE t.fecha BETWEEN :fi_ant AND :ff_ant
          AND NOT v.es_devolucion {suc_sql} {extra}
    """), params).fetchone()

    val_act = float(r_actual.valor or 0)
    val_ant = float(r_ant.valor or 0)
    var_pct = round((val_act - val_ant) / val_ant * 100, 1) if val_ant > 0 else 0.0

    # Detail for current period
    group_expr, agrupacion = _expr_agrupacion(agrupacion)
    rows = db.execute(text(f"""
        SELECT {group_expr} AS periodo,
               SUM(v.cantidad) AS cantidad,
               SUM(v.valor_total) AS valor_total,
               SUM(v.costo_total) AS costo_total,
               COUNT(*) AS transacciones
        {desde}
        WHERE t.fecha BETWEEN :fi AND :ff
          AND NOT v.es_devolucion {suc_sql} {extra}
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
            periodo_anterior=f"{inicio_ant} / {fin_ant}",
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
    fecha_inicio: str | None = Query(None),
    fecha_fin: str | None = Query(None),
    sucursal_id: int | None = Query(None, description=DESC_SUCURSAL),
    categoria: str | None = Query(None),
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fecha_max = _get_fecha_max(db)
    if not fecha_fin:
        fecha_fin = fecha_max
    if not fecha_inicio:
        fecha_inicio = f"{fecha_fin[:7]}-01"

    suc_sql, params = _build_suc_filter(db, user, sucursal_id)
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
    description=(
        "Ventas por día con promedio móvil 7 días, o por semana o mes (sin promedio). Por sucursal o global; "
        "filtro opcional por categoría. Sin fecha_inicio, la serie empieza `dias` días antes de fecha_fin "
        "(30 por defecto)."
    ),
)
def tendencias(
    fecha_inicio: str | None = Query(None),
    fecha_fin: str | None = Query(None),
    dias: int = Query(30, ge=1, le=366, description="Días hacia atrás cuando no hay fecha_inicio (INV-25)"),
    sucursal_id: int | None = Query(None, description=DESC_SUCURSAL),
    por_sucursal: bool = Query(False, description="Desglosar por sucursal"),
    categoria: str | None = Query(None, description="Filtrar por categoría (INV-26 fix)"),
    agrupacion: str = Query("dia", description="dia, semana, mes (INV-26 fix)"),
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fecha_max = _get_fecha_max(db)
    if not fecha_fin:
        fecha_fin = fecha_max
    if not fecha_inicio:
        # Default: últimos `dias` días (30)
        fecha_inicio = str(db.execute(text(
            "SELECT CAST(:ff AS DATE) - make_interval(days => :dias)"
        ), {"ff": fecha_fin, "dias": dias}).scalar())[:10]

    suc_sql, params = _build_suc_filter(db, user, sucursal_id)
    params["fi"] = fecha_inicio
    params["ff"] = fecha_fin
    extra = _filtro_categoria(categoria, params)
    periodo, agrupacion = _expr_agrupacion(agrupacion)

    if por_sucursal:
        group_cols = f"s.nombre, {periodo}"
        select_extra = "s.nombre AS sucursal,"
        join_extra = "JOIN dw.dim_sucursal s ON v.id_sucursal = s.id_sucursal"
    else:
        group_cols = periodo
        select_extra = "NULL AS sucursal,"
        join_extra = ""

    rows = db.execute(text(f"""
        SELECT {select_extra}
               {periodo} AS fecha,
               SUM(v.valor_total) AS valor_total,
               SUM(v.cantidad) AS cantidad
        FROM dw.fact_ventas v
        JOIN dw.dim_tiempo t ON v.id_tiempo = t.id_tiempo
        JOIN dw.dim_producto p ON v.id_producto = p.id_producto
        {join_extra}
        WHERE t.fecha BETWEEN :fi AND :ff
          AND NOT v.es_devolucion {suc_sql} {extra}
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

    # Calculate 7-day moving average (solo por día: en semanas o meses no aplica)
    series = []
    for suc_name, puntos in series_map.items():
        processed = []
        for i, p in enumerate(puntos):
            window = puntos[max(0, i - 6):i + 1]
            ma7 = round(sum(w["valor_total"] for w in window) / len(window), 2) if agrupacion == "dia" else None
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
    fecha_inicio: str | None = Query(None),
    fecha_fin: str | None = Query(None),
    sucursal_id: int | None = Query(None, description=DESC_SUCURSAL),
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fecha_max = _get_fecha_max(db)
    if not fecha_fin:
        fecha_fin = fecha_max
    if not fecha_inicio:
        fecha_inicio = f"{fecha_fin[:7]}-01"

    suc_sql, params = _build_suc_filter(db, user, sucursal_id)
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
