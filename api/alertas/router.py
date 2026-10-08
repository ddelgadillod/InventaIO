"""
InventAI/o — Alertas Router
INV-007: Alertas automáticas basadas en reglas de inventario.
Generates alerts dynamically from fact_inventario + fact_ventas.
RBAC (INV-25, core/ubicaciones.py): gerente/admin_bodega ven todo;
admin_sucursal solo su sucursal (ni las alertas de la Bodega Central).
INV-25 (D4): la Bodega no vende, así que no tiene alertas de movimiento ni
de rotación; el stock negativo es inconsistencia_inventario, no stock_critico.
"""
import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from core.database import get_db
from core.productos import texto_cantidad, texto_dias, texto_numero
from core.ubicaciones import ALERTAS, SQL_TIPO_UBICACION, filtro_sucursal
from models.usuario import Usuario
from schemas.alertas import (
    URGENCIA_ORDER,
    AlertaContadores,
    AlertaItem,
    AlertaList,
    AlertaResumen,
    AlertaResumenSucursal,
)

router = APIRouter(prefix="/api/alertas", tags=["Alertas"])

# ── Thresholds ───────────────────────────────────────
UMBRAL_CRITICO = 3.0        # días cobertura
UMBRAL_BAJO = 7.0           # días cobertura
UMBRAL_SIN_MOVIMIENTO = 0   # 0 ventas en 30 días
UMBRAL_ROTACION_BAJA = 0.2  # < 20% del promedio de ventas

TIPOS = ("inconsistencia_inventario", "stock_critico", "stock_bajo", "sin_movimiento", "rotacion_baja")
ALERTAS_POR_PAGINA = 50     # INV-26 fix (K2): la página de Alertas pide de a 50


def _get_fecha_inventario(db: Session) -> str:
    row = db.execute(text("""
        SELECT t.fecha
        FROM dw.fact_inventario fi
        JOIN dw.dim_tiempo t ON fi.id_tiempo = t.id_tiempo
        ORDER BY t.fecha DESC LIMIT 1
    """)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No hay datos de inventario")
    return str(row.fecha)

def _generar_alertas(db: Session, user: Usuario, fecha: str,
                     tipo_filtro: str | None = None,
                     urgencia_filtro: str | None = None,
                     sucursal_id: int | None = None) -> list:
    """Generate all alerts dynamically from inventory + sales data."""
    rbac_sql, rbac_params = filtro_sucursal(db, user, sucursal_id, ALERTAS, "fi")
    params = {"fecha": fecha, **rbac_params}

    alertas = []

    # ── 0. inconsistencia_inventario: stock negativo (INV-25, D4) ──
    if not tipo_filtro or tipo_filtro == "inconsistencia_inventario":
        rows = db.execute(text(f"""
            SELECT fi.id_producto, p.nombre, p.categoria, p.se_vende_por_kilo,
                   s.nombre AS sucursal, fi.id_sucursal,
                   {SQL_TIPO_UBICACION} AS tipo_ubicacion,
                   fi.stock_disponible, t.fecha
            FROM dw.fact_inventario fi
            JOIN dw.dim_tiempo t ON fi.id_tiempo = t.id_tiempo
            JOIN dw.dim_producto p ON fi.id_producto = p.id_producto
            JOIN dw.dim_sucursal s ON fi.id_sucursal = s.id_sucursal
            WHERE t.fecha = :fecha
              AND fi.stock_disponible < 0
              {rbac_sql}
            ORDER BY fi.stock_disponible ASC
        """), params).fetchall()

        for r in rows:
            alertas.append(AlertaItem(
                id_producto=r.id_producto,
                nombre_producto=r.nombre,
                categoria=r.categoria,
                sucursal=r.sucursal,
                id_sucursal=r.id_sucursal,
                tipo_ubicacion=r.tipo_ubicacion,
                tipo="inconsistencia_inventario",
                urgencia="critica",
                valor=float(r.stock_disponible),
                umbral=0.0,
                detalle=f"Stock negativo en la foto ({texto_cantidad(float(r.stock_disponible), r.se_vende_por_kilo)}): verificar el conteo",
                fecha=str(r.fecha),
            ))

    # ── 1. stock_critico: cobertura < 3 días ─────────
    if not tipo_filtro or tipo_filtro == "stock_critico":
        rows = db.execute(text(f"""
            SELECT fi.id_producto, p.nombre, p.categoria, p.se_vende_por_kilo,
                   s.nombre AS sucursal, fi.id_sucursal,
                   {SQL_TIPO_UBICACION} AS tipo_ubicacion,
                   fi.dias_cobertura, fi.stock_disponible, fi.punto_reorden,
                   t.fecha
            FROM dw.fact_inventario fi
            JOIN dw.dim_tiempo t ON fi.id_tiempo = t.id_tiempo
            JOIN dw.dim_producto p ON fi.id_producto = p.id_producto
            JOIN dw.dim_sucursal s ON fi.id_sucursal = s.id_sucursal
            WHERE t.fecha = :fecha
              AND fi.dias_cobertura < {UMBRAL_CRITICO}
              AND fi.stock_disponible >= 0
              {rbac_sql}
            ORDER BY fi.dias_cobertura ASC
        """), params).fetchall()

        for r in rows:
            alertas.append(AlertaItem(
                id_producto=r.id_producto,
                nombre_producto=r.nombre,
                categoria=r.categoria,
                sucursal=r.sucursal,
                id_sucursal=r.id_sucursal,
                tipo_ubicacion=r.tipo_ubicacion,
                tipo="stock_critico",
                urgencia="critica",
                valor=float(r.dias_cobertura),
                umbral=UMBRAL_CRITICO,
                detalle=f"Stock: {texto_cantidad(float(r.stock_disponible), r.se_vende_por_kilo)}, cobertura {texto_dias(float(r.dias_cobertura))} (umbral: {texto_dias(UMBRAL_CRITICO)})",
                fecha=str(r.fecha),
            ))

    # ── 2. stock_bajo: cobertura 3–7 días ────────────
    if not tipo_filtro or tipo_filtro == "stock_bajo":
        rows = db.execute(text(f"""
            SELECT fi.id_producto, p.nombre, p.categoria, p.se_vende_por_kilo,
                   s.nombre AS sucursal, fi.id_sucursal,
                   {SQL_TIPO_UBICACION} AS tipo_ubicacion,
                   fi.dias_cobertura, fi.stock_disponible, fi.punto_reorden,
                   t.fecha
            FROM dw.fact_inventario fi
            JOIN dw.dim_tiempo t ON fi.id_tiempo = t.id_tiempo
            JOIN dw.dim_producto p ON fi.id_producto = p.id_producto
            JOIN dw.dim_sucursal s ON fi.id_sucursal = s.id_sucursal
            WHERE t.fecha = :fecha
              AND fi.dias_cobertura >= {UMBRAL_CRITICO}
              AND fi.dias_cobertura < {UMBRAL_BAJO}
              {rbac_sql}
            ORDER BY fi.dias_cobertura ASC
        """), params).fetchall()

        for r in rows:
            alertas.append(AlertaItem(
                id_producto=r.id_producto,
                nombre_producto=r.nombre,
                categoria=r.categoria,
                sucursal=r.sucursal,
                id_sucursal=r.id_sucursal,
                tipo_ubicacion=r.tipo_ubicacion,
                tipo="stock_bajo",
                urgencia="alta",
                valor=float(r.dias_cobertura),
                umbral=UMBRAL_BAJO,
                detalle=f"Stock: {texto_cantidad(float(r.stock_disponible), r.se_vende_por_kilo)}, cobertura {texto_dias(float(r.dias_cobertura))} (umbral: {texto_dias(UMBRAL_BAJO)})",
                fecha=str(r.fecha),
            ))

    # ── 3. sin_movimiento: 0 ventas en 30 días ──────
    if not tipo_filtro or tipo_filtro == "sin_movimiento":
        rows = db.execute(text(f"""
            WITH ventas_30d AS (
                SELECT v.id_producto, v.id_sucursal, SUM(v.cantidad) AS total_qty
                FROM dw.fact_ventas v
                JOIN dw.dim_tiempo t ON v.id_tiempo = t.id_tiempo
                WHERE t.fecha > (CAST(:fecha AS DATE) - INTERVAL '30 days')
                  AND t.fecha <= CAST(:fecha AS DATE)
                  AND NOT v.es_devolucion
                GROUP BY v.id_producto, v.id_sucursal
            )
            SELECT fi.id_producto, p.nombre, p.categoria, p.se_vende_por_kilo,
                   s.nombre AS sucursal, fi.id_sucursal,
                   {SQL_TIPO_UBICACION} AS tipo_ubicacion,
                   fi.stock_disponible, COALESCE(v.total_qty, 0) AS ventas_30d,
                   t.fecha
            FROM dw.fact_inventario fi
            JOIN dw.dim_tiempo t ON fi.id_tiempo = t.id_tiempo
            JOIN dw.dim_producto p ON fi.id_producto = p.id_producto
            JOIN dw.dim_sucursal s ON fi.id_sucursal = s.id_sucursal
            LEFT JOIN ventas_30d v ON fi.id_producto = v.id_producto
                                  AND fi.id_sucursal = v.id_sucursal
            WHERE t.fecha = :fecha
              AND fi.stock_disponible > 0
              AND COALESCE(v.total_qty, 0) = 0
              AND s.tipo <> 'bodega_central'
              {rbac_sql}
            ORDER BY fi.stock_disponible DESC
        """), params).fetchall()

        for r in rows:
            alertas.append(AlertaItem(
                id_producto=r.id_producto,
                nombre_producto=r.nombre,
                categoria=r.categoria,
                sucursal=r.sucursal,
                id_sucursal=r.id_sucursal,
                tipo_ubicacion=r.tipo_ubicacion,
                tipo="sin_movimiento",
                urgencia="media",
                valor=0.0,
                umbral=1.0,
                detalle=f"0 ventas en 30 días con {texto_cantidad(float(r.stock_disponible), r.se_vende_por_kilo)} en stock",
                fecha=str(r.fecha),
            ))

    # ── 4. rotacion_baja: ventas < 20% promedio ──────
    if not tipo_filtro or tipo_filtro == "rotacion_baja":
        rows = db.execute(text(f"""
            WITH ventas_30d AS (
                SELECT v.id_producto, v.id_sucursal, SUM(v.cantidad) AS total_qty
                FROM dw.fact_ventas v
                JOIN dw.dim_tiempo t ON v.id_tiempo = t.id_tiempo
                WHERE t.fecha > (CAST(:fecha AS DATE) - INTERVAL '30 days')
                  AND t.fecha <= CAST(:fecha AS DATE)
                  AND NOT v.es_devolucion
                GROUP BY v.id_producto, v.id_sucursal
            ),
            promedio_global AS (
                SELECT v.id_producto, AVG(v.total_qty) AS avg_qty
                FROM ventas_30d v
                GROUP BY v.id_producto
            )
            SELECT fi.id_producto, p.nombre, p.categoria, p.se_vende_por_kilo,
                   s.nombre AS sucursal, fi.id_sucursal,
                   {SQL_TIPO_UBICACION} AS tipo_ubicacion,
                   v.total_qty, pg.avg_qty,
                   t.fecha
            FROM dw.fact_inventario fi
            JOIN dw.dim_tiempo t ON fi.id_tiempo = t.id_tiempo
            JOIN dw.dim_producto p ON fi.id_producto = p.id_producto
            JOIN dw.dim_sucursal s ON fi.id_sucursal = s.id_sucursal
            JOIN ventas_30d v ON fi.id_producto = v.id_producto
                             AND fi.id_sucursal = v.id_sucursal
            JOIN promedio_global pg ON fi.id_producto = pg.id_producto
            WHERE t.fecha = :fecha
              AND v.total_qty > 0
              AND pg.avg_qty > 0
              AND (v.total_qty / pg.avg_qty) < {UMBRAL_ROTACION_BAJA}
              AND s.tipo <> 'bodega_central'
              {rbac_sql}
            ORDER BY (v.total_qty / pg.avg_qty) ASC
        """), params).fetchall()

        for r in rows:
            ratio = float(r.total_qty) / float(r.avg_qty) if r.avg_qty else 0
            alertas.append(AlertaItem(
                id_producto=r.id_producto,
                nombre_producto=r.nombre,
                categoria=r.categoria,
                sucursal=r.sucursal,
                id_sucursal=r.id_sucursal,
                tipo_ubicacion=r.tipo_ubicacion,
                tipo="rotacion_baja",
                urgencia="media",
                valor=round(ratio * 100, 1),
                umbral=UMBRAL_ROTACION_BAJA * 100,
                detalle=(f"Ventas al {texto_numero(ratio * 100, 0)}% del promedio ({texto_cantidad(float(r.total_qty), r.se_vende_por_kilo)}"
                         f" frente a {texto_cantidad(float(r.avg_qty), r.se_vende_por_kilo)})"),
                fecha=str(r.fecha),
            ))

    # Filter by urgencia if requested
    if urgencia_filtro:
        alertas = [a for a in alertas if a.urgencia == urgencia_filtro]

    # Sort: critica first, then alta, then media
    alertas.sort(key=lambda a: (URGENCIA_ORDER.get(a.urgencia, 99), a.valor))

    return alertas


# ── GET /api/alertas ─────────────────────────────────
@router.get(
    "",
    response_model=AlertaList,
    response_model_exclude_unset=True,
    summary="Alertas activas por urgencia",
    description=(
        "Genera alertas dinámicas basadas en reglas de inventario. "
        "Tipos: inconsistencia_inventario (stock negativo), stock_critico, stock_bajo, sin_movimiento, "
        "rotacion_baja; la Bodega Central no tiene sin_movimiento ni rotacion_baja porque no vende. "
        "Urgencia: critica, alta, media. RBAC: admin_sucursal ve solo las de su sucursal. "
        "Con page o page_size devuelve solo esa página (más page, page_size y pages); sin ellos, todas."
    ),
)
def listar_alertas(
    tipo: str | None = Query(None, description="Filtrar: " + ", ".join(TIPOS)),
    urgencia: str | None = Query(None, description="Filtrar: critica, alta, media"),
    sucursal_id: int | None = Query(
        None, description="Filtrar por sucursal. admin_sucursal: solo la suya; otra da 403. Inexistente o SIN_SUCURSAL, 422"),
    page: int | None = Query(None, ge=1, description="Página (INV-26 fix). Sin page ni page_size: todas"),
    page_size: int | None = Query(
        None, ge=1, le=500, description=f"Alertas por página; {ALERTAS_POR_PAGINA} si solo se envía page"),
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fecha = _get_fecha_inventario(db)

    # Validate filters
    if tipo and tipo not in TIPOS:
        raise HTTPException(400, f"Tipo inválido. Válidos: {', '.join(TIPOS)}")

    urgencias_validas = {"critica", "alta", "media"}
    if urgencia and urgencia not in urgencias_validas:
        raise HTTPException(400, f"Urgencia inválida. Válidas: {', '.join(urgencias_validas)}")

    alertas = _generar_alertas(db, user, fecha, tipo, urgencia, sucursal_id)
    total = len(alertas)

    # INV-26 fix (K2): sin page ni page_size responde como en INV-25 (todas)
    if page is None and page_size is None:
        return AlertaList(items=alertas, total=total, fecha_inventario=fecha)
    page, page_size = page or 1, page_size or ALERTAS_POR_PAGINA
    inicio = (page - 1) * page_size
    return AlertaList(
        items=alertas[inicio:inicio + page_size],
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size),
        fecha_inventario=fecha,
    )


# ── GET /api/alertas/resumen ─────────────────────────
@router.get(
    "/resumen",
    response_model=AlertaResumen,
    summary="Contadores de alertas",
    description=(
        "Retorna contadores de alertas por urgencia, por sucursal, y por tipo. "
        "Con sucursal_id, solo esa ubicación."
    ),
)
def resumen_alertas(
    sucursal_id: int | None = Query(
        None, description="Filtrar por sucursal. admin_sucursal: solo la suya; otra da 403. Inexistente o SIN_SUCURSAL, 422"),
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fecha = _get_fecha_inventario(db)
    alertas = _generar_alertas(db, user, fecha, sucursal_id=sucursal_id)

    # Per-sucursal counters
    suc_map = {}
    por_tipo = {t: 0 for t in TIPOS}
    g_crit = g_alta = g_media = 0

    for a in alertas:
        key = (a.sucursal, a.id_sucursal, a.tipo_ubicacion)
        if key not in suc_map:
            suc_map[key] = {"critica": 0, "alta": 0, "media": 0}
        suc_map[key][a.urgencia] += 1
        por_tipo[a.tipo] += 1

        if a.urgencia == "critica":
            g_crit += 1
        elif a.urgencia == "alta":
            g_alta += 1
        else:
            g_media += 1

    items = []
    for (suc_nombre, suc_id, tipo_ubicacion), counts in sorted(suc_map.items(), key=lambda x: x[1]["critica"], reverse=True):
        total = counts["critica"] + counts["alta"] + counts["media"]
        items.append(AlertaResumenSucursal(
            sucursal=suc_nombre,
            id_sucursal=suc_id,
            tipo_ubicacion=tipo_ubicacion,
            contadores=AlertaContadores(
                critica=counts["critica"],
                alta=counts["alta"],
                media=counts["media"],
                total=total,
            ),
        ))

    g_total = g_crit + g_alta + g_media

    return AlertaResumen(
        items=items,
        global_=AlertaContadores(critica=g_crit, alta=g_alta, media=g_media, total=g_total),
        por_tipo=por_tipo,
        fecha_inventario=fecha,
    )
