"""
InventAI/o — Alertas Router
INV-007: Alertas automáticas basadas en reglas de inventario.
Generates alerts dynamically from fact_inventario + fact_ventas.
RBAC: admin_sucursal/admin_bodega see only their sucursal.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from core.database import get_db
from auth.dependencies import get_current_user
from models.usuario import Usuario
from schemas.alertas import (
    URGENCIA_ORDER,
    AlertaItem, AlertaList,
    AlertaContadores, AlertaResumenSucursal, AlertaResumen,
)

router = APIRouter(prefix="/api/alertas", tags=["Alertas"])

# ── Thresholds ───────────────────────────────────────
UMBRAL_CRITICO = 3.0        # días cobertura
UMBRAL_BAJO = 7.0           # días cobertura
UMBRAL_SIN_MOVIMIENTO = 0   # 0 ventas en 30 días
UMBRAL_ROTACION_BAJA = 0.2  # < 20% del promedio de ventas


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


def _sucursal_filter(user: Usuario) -> tuple:
    if user.rol == "gerente":
        return "", {}
    return "AND fi.id_sucursal = :user_sucursal", {"user_sucursal": user.id_sucursal}


def _generar_alertas(db: Session, user: Usuario, fecha: str,
                     tipo_filtro: Optional[str] = None,
                     urgencia_filtro: Optional[str] = None,
                     sucursal_id: Optional[int] = None) -> list:
    """Generate all alerts dynamically from inventory + sales data."""
    rbac_sql, rbac_params = _sucursal_filter(user)
    params = {"fecha": fecha, **rbac_params}

    # Extra sucursal filter for gerente
    suc_extra = ""
    if sucursal_id and user.rol == "gerente":
        suc_extra = "AND fi.id_sucursal = :suc_filter"
        params["suc_filter"] = sucursal_id

    alertas = []

    # ── 1. stock_critico: cobertura < 3 días ─────────
    if not tipo_filtro or tipo_filtro == "stock_critico":
        rows = db.execute(text(f"""
            SELECT fi.id_producto, p.nombre, p.categoria,
                   s.nombre AS sucursal, fi.id_sucursal,
                   fi.dias_cobertura, fi.stock_disponible, fi.punto_reorden,
                   t.fecha
            FROM dw.fact_inventario fi
            JOIN dw.dim_tiempo t ON fi.id_tiempo = t.id_tiempo
            JOIN dw.dim_producto p ON fi.id_producto = p.id_producto
            JOIN dw.dim_sucursal s ON fi.id_sucursal = s.id_sucursal
            WHERE t.fecha = :fecha
              AND fi.dias_cobertura < {UMBRAL_CRITICO}
              {rbac_sql} {suc_extra}
            ORDER BY fi.dias_cobertura ASC
        """), params).fetchall()

        for r in rows:
            alertas.append(AlertaItem(
                id_producto=r.id_producto,
                nombre_producto=r.nombre,
                categoria=r.categoria,
                sucursal=r.sucursal,
                id_sucursal=r.id_sucursal,
                tipo="stock_critico",
                urgencia="critica",
                valor=float(r.dias_cobertura),
                umbral=UMBRAL_CRITICO,
                detalle=f"Stock: {float(r.stock_disponible):.0f} uds, cobertura {float(r.dias_cobertura):.1f}d (umbral: {UMBRAL_CRITICO}d)",
                fecha=str(r.fecha),
            ))

    # ── 2. stock_bajo: cobertura 3–7 días ────────────
    if not tipo_filtro or tipo_filtro == "stock_bajo":
        rows = db.execute(text(f"""
            SELECT fi.id_producto, p.nombre, p.categoria,
                   s.nombre AS sucursal, fi.id_sucursal,
                   fi.dias_cobertura, fi.stock_disponible, fi.punto_reorden,
                   t.fecha
            FROM dw.fact_inventario fi
            JOIN dw.dim_tiempo t ON fi.id_tiempo = t.id_tiempo
            JOIN dw.dim_producto p ON fi.id_producto = p.id_producto
            JOIN dw.dim_sucursal s ON fi.id_sucursal = s.id_sucursal
            WHERE t.fecha = :fecha
              AND fi.dias_cobertura >= {UMBRAL_CRITICO}
              AND fi.dias_cobertura < {UMBRAL_BAJO}
              {rbac_sql} {suc_extra}
            ORDER BY fi.dias_cobertura ASC
        """), params).fetchall()

        for r in rows:
            alertas.append(AlertaItem(
                id_producto=r.id_producto,
                nombre_producto=r.nombre,
                categoria=r.categoria,
                sucursal=r.sucursal,
                id_sucursal=r.id_sucursal,
                tipo="stock_bajo",
                urgencia="alta",
                valor=float(r.dias_cobertura),
                umbral=UMBRAL_BAJO,
                detalle=f"Stock: {float(r.stock_disponible):.0f} uds, cobertura {float(r.dias_cobertura):.1f}d (umbral: {UMBRAL_BAJO}d)",
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
            SELECT fi.id_producto, p.nombre, p.categoria,
                   s.nombre AS sucursal, fi.id_sucursal,
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
              {rbac_sql} {suc_extra}
            ORDER BY fi.stock_disponible DESC
        """), params).fetchall()

        for r in rows:
            alertas.append(AlertaItem(
                id_producto=r.id_producto,
                nombre_producto=r.nombre,
                categoria=r.categoria,
                sucursal=r.sucursal,
                id_sucursal=r.id_sucursal,
                tipo="sin_movimiento",
                urgencia="media",
                valor=0.0,
                umbral=1.0,
                detalle=f"0 ventas en 30 días con {float(r.stock_disponible):.0f} uds en stock",
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
            SELECT fi.id_producto, p.nombre, p.categoria,
                   s.nombre AS sucursal, fi.id_sucursal,
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
              {rbac_sql} {suc_extra}
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
                tipo="rotacion_baja",
                urgencia="media",
                valor=round(ratio * 100, 1),
                umbral=UMBRAL_ROTACION_BAJA * 100,
                detalle=f"Ventas al {ratio*100:.0f}% del promedio ({float(r.total_qty):.0f} vs avg {float(r.avg_qty):.0f})",
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
    summary="Alertas activas por urgencia",
    description=(
        "Genera alertas dinámicas basadas en reglas de inventario. "
        "Tipos: stock_critico, stock_bajo, sin_movimiento, rotacion_baja. "
        "Urgencia: critica, alta, media. RBAC aplicado."
    ),
)
def listar_alertas(
    tipo: Optional[str] = Query(None, description="Filtrar: stock_critico, stock_bajo, sin_movimiento, rotacion_baja"),
    urgencia: Optional[str] = Query(None, description="Filtrar: critica, alta, media"),
    sucursal_id: Optional[int] = Query(None, description="Filtrar por sucursal (gerente)"),
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fecha = _get_fecha_inventario(db)

    # Validate filters
    tipos_validos = {"stock_critico", "stock_bajo", "sin_movimiento", "rotacion_baja"}
    if tipo and tipo not in tipos_validos:
        raise HTTPException(400, f"Tipo inválido. Válidos: {', '.join(tipos_validos)}")

    urgencias_validas = {"critica", "alta", "media"}
    if urgencia and urgencia not in urgencias_validas:
        raise HTTPException(400, f"Urgencia inválida. Válidas: {', '.join(urgencias_validas)}")

    alertas = _generar_alertas(db, user, fecha, tipo, urgencia, sucursal_id)

    return AlertaList(
        items=alertas,
        total=len(alertas),
        fecha_inventario=fecha,
    )


# ── GET /api/alertas/resumen ─────────────────────────
@router.get(
    "/resumen",
    response_model=AlertaResumen,
    summary="Contadores de alertas",
    description="Retorna contadores de alertas por urgencia, por sucursal, y por tipo.",
)
def resumen_alertas(
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fecha = _get_fecha_inventario(db)
    alertas = _generar_alertas(db, user, fecha)

    # Per-sucursal counters
    suc_map = {}
    por_tipo = {"stock_critico": 0, "stock_bajo": 0, "sin_movimiento": 0, "rotacion_baja": 0}
    g_crit = g_alta = g_media = 0

    for a in alertas:
        key = (a.sucursal, a.id_sucursal)
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
    for (suc_nombre, suc_id), counts in sorted(suc_map.items(), key=lambda x: x[1]["critica"], reverse=True):
        total = counts["critica"] + counts["alta"] + counts["media"]
        items.append(AlertaResumenSucursal(
            sucursal=suc_nombre,
            id_sucursal=suc_id,
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
