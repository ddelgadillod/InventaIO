"""
InventAI/o — Consulta Router (Catálogos y Proveedores)
INV-008: Endpoints de solo lectura para información maestra.
Uses raw SQL via SQLAlchemy text() to avoid ORM cross-schema FK issues.
"""
import math
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from core.database import get_db
from core.productos import unidad_venta
from core.ubicaciones import BODEGA, VENTAS, cargar_ubicaciones, resolver_sucursal
from models.usuario import Usuario
from schemas.consulta import (
    CategoriaItem,
    CategoriaList,
    ProductoDetalle,
    ProductoItem,
    ProductoList,
    ProveedorDetalle,
    ProveedorItem,
    ProveedorList,
    SucursalItem,
    SucursalList,
    VentanaVentas,
    VentasProducto,
)

router = APIRouter(prefix="/api/consulta", tags=["Consulta"])

# INV-26: ventanas de ventas del mismo largo que el horizonte del pronóstico
HORIZONTE_DIAS_HABILES = 15

# Día hábil = fecha con alguna venta en la red, como SQL_HABILES de ml_service
SQL_ULTIMOS_HABILES = text("""
    SELECT t.fecha FROM dw.dim_tiempo t
    WHERE EXISTS (SELECT 1 FROM dw.fact_ventas v
                  WHERE v.id_tiempo = t.id_tiempo AND NOT v.es_devolucion AND v.cantidad > 0)
    ORDER BY t.fecha DESC
    LIMIT :n
""")
SQL_VENTAS_PRODUCTO = text("""
    SELECT fecha, unidades FROM dw.v_ventas_diarias_netas
    WHERE codigo_item = :codigo AND sucursal = :sucursal AND fecha BETWEEN :desde AND :hasta
""")


def armar_ventanas(habiles: list[date], ventas: dict[date, float], horizonte: int) -> list[VentanaVentas]:
    """Agrupa los días hábiles (orden cronológico) en ventanas completas de
    `horizonte` días que terminan en el último; un día sin venta cuenta 0."""
    completos = habiles[len(habiles) % horizonte:]
    bloques = [completos[i:i + horizonte] for i in range(0, len(completos), horizonte)]
    return [VentanaVentas(desde=b[0], hasta=b[-1], unidades=sum(ventas.get(d, 0.0) for d in b)) for b in bloques]


# Columnas de dw.dim_producto (alias p) con las que se arma un ProductoItem
COLUMNAS_PRODUCTO = """p.id_producto, p.codigo_item, p.nombre, p.familia, p.clase, p.categoria,
       p.es_perecedero, p.unidad_medida, p.precio_base, p.costo_base, p.margen_pct, p.iva_pct,
       p.se_vende_por_kilo"""


def producto_item(r) -> dict:
    """Campos de ProductoItem a partir de una fila con COLUMNAS_PRODUCTO."""
    return dict(
        id_producto=r.id_producto,
        codigo_item=r.codigo_item,
        nombre=r.nombre,
        familia=r.familia,
        clase=r.clase,
        categoria=r.categoria,
        es_perecedero=r.es_perecedero,
        unidad_medida=r.unidad_medida,
        unidad=unidad_venta(r.se_vende_por_kilo),
        precio_base=float(r.precio_base) if r.precio_base else None,
        costo_base=float(r.costo_base) if r.costo_base else None,
        margen_pct=float(r.margen_pct) if r.margen_pct else None,
        iva_pct=float(r.iva_pct),
    )


# ── GET /api/consulta/productos ─────────────────────
@router.get(
    "/productos",
    response_model=ProductoList,
    summary="Listar productos",
    description=(
        "Retorna productos paginados con filtros opcionales por categoría, familia, perecedero y búsqueda "
        "por nombre, familia o código (INV-26, V11)."
    ),
)
def listar_productos(
    page: int = Query(1, ge=1, description="Página"),
    page_size: int = Query(20, ge=1, le=100, description="Items por página"),
    categoria: str | None = Query(None, description="Filtrar por categoría"),
    familia: str | None = Query(None, description="Filtrar por familia"),
    perecedero: bool | None = Query(None, description="Filtrar por perecedero"),
    busqueda: str | None = Query(None, description="Buscar en nombre, familia o código (codigo_item, por ejemplo P1632)"),
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Build WHERE clauses
    conditions = []
    params = {}

    if categoria:
        conditions.append("p.categoria = :categoria")
        params["categoria"] = categoria
    if familia:
        conditions.append("p.familia = :familia")
        params["familia"] = familia
    if perecedero is not None:
        conditions.append("p.es_perecedero = :perecedero")
        params["perecedero"] = perecedero
    if busqueda:
        conditions.append("(p.nombre ILIKE :busqueda OR p.familia ILIKE :busqueda OR p.codigo_item ILIKE :busqueda)")
        params["busqueda"] = f"%{busqueda}%"

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    # Count
    count_sql = f"SELECT COUNT(*) FROM dw.dim_producto p {where}"
    total = db.execute(text(count_sql), params).scalar()

    # Paginated query
    offset = (page - 1) * page_size
    params["limit"] = page_size
    params["offset"] = offset

    query_sql = f"""
        SELECT {COLUMNAS_PRODUCTO}
        FROM dw.dim_producto p
        {where}
        ORDER BY p.categoria, p.nombre
        LIMIT :limit OFFSET :offset
    """
    rows = db.execute(text(query_sql), params).fetchall()

    items = [ProductoItem(**producto_item(r)) for r in rows]

    return ProductoList(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total > 0 else 0,
    )


# ── GET /api/consulta/productos/:id ─────────────────
@router.get(
    "/productos/{id_producto}",
    response_model=ProductoDetalle,
    summary="Detalle de producto",
    description="Retorna un producto por ID, incluyendo los proveedores que lo abastecen (dw.producto_proveedor).",
)
def detalle_producto(
    id_producto: int,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.execute(
        text(f"SELECT {COLUMNAS_PRODUCTO} FROM dw.dim_producto p WHERE p.id_producto = :id"),
        {"id": id_producto},
    ).fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Producto {id_producto} no encontrado",
        )

    # INV-25 (D5): la relación real de la bodega, no la categoría
    proveedores = db.execute(
        text("""
            SELECT d.razon_social
            FROM dw.producto_proveedor pp
            JOIN dw.dim_proveedor d ON d.id_proveedor = pp.id_proveedor
            WHERE pp.id_producto = :id
            ORDER BY d.calificacion DESC
        """),
        {"id": id_producto},
    ).fetchall()

    return ProductoDetalle(**producto_item(row), proveedores=[p.razon_social for p in proveedores])


# ── GET /api/consulta/productos/:id/ventas ──────────
@router.get(
    "/productos/{id_producto}/ventas",
    response_model=VentasProducto,
    summary="Ventas de un producto en ventanas de 15 días hábiles",
    description=(
        "INV-26: ventas de un producto en una sucursal física, en ventanas de 15 días hábiles (días con alguna "
        "venta en la red, como el modelo) que terminan en el último día hábil, para compararlas con POST "
        "/api/ml/predict. Fuente: dw.v_ventas_diarias_netas (sin devoluciones). Un día sin venta cuenta 0. "
        "Permisos de INV-25: gerente y admin_bodega deben enviar sucursal_id; admin_sucursal, la suya. "
        "Errores: 403 otra sucursal o la Bodega (admin_sucursal); 404 producto inexistente; 422 sin sucursal_id, "
        "sucursal inexistente, SIN_SUCURSAL, la Bodega Central (no vende) o ventanas fuera de 1-24."
    ),
)
def ventas_producto(
    id_producto: int,
    sucursal_id: int | None = Query(
        None, description="Sucursal física. Obligatoria para gerente y admin_bodega; admin_sucursal usa la suya."),
    ventanas: int = Query(8, ge=1, le=24, description="Número de ventanas, de la más reciente hacia atrás"),
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ubicaciones = cargar_ubicaciones(db)
    suc = resolver_sucursal(ubicaciones, user, sucursal_id, VENTAS)
    if suc is None:
        fisicas = ", ".join(f"{i} ({u['nombre']})" for i, u in ubicaciones.items() if u["tipo"] != BODEGA)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"sucursal_id es obligatorio. Válidos: {fisicas}")
    if ubicaciones[suc]["tipo"] == BODEGA:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "La Bodega Central no vende: las ventas son por sucursal física")

    producto = db.execute(
        text("SELECT id_producto, codigo_item, nombre, categoria, se_vende_por_kilo "
             "FROM dw.dim_producto WHERE id_producto = :id"),
        {"id": id_producto},
    ).fetchone()
    if not producto:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Producto {id_producto} no encontrado")

    habiles = [r.fecha for r in db.execute(SQL_ULTIMOS_HABILES, {"n": ventanas * HORIZONTE_DIAS_HABILES})][::-1]
    if not habiles:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "La bodega no tiene ventas cargadas")
    nombre_sucursal = ubicaciones[suc]["nombre"]
    ventas = {
        r.fecha: float(r.unidades)
        for r in db.execute(SQL_VENTAS_PRODUCTO, {"codigo": producto.codigo_item, "sucursal": nombre_sucursal,
                                                  "desde": habiles[0], "hasta": habiles[-1]})
    }

    return VentasProducto(
        id_producto=producto.id_producto,
        codigo_item=producto.codigo_item,
        nombre_producto=producto.nombre,
        categoria=producto.categoria,
        unidad=unidad_venta(producto.se_vende_por_kilo),
        id_sucursal=suc,
        sucursal=nombre_sucursal,
        horizonte_dias_habiles=HORIZONTE_DIAS_HABILES,
        fecha_fin=habiles[-1],
        ventanas=armar_ventanas(habiles, ventas, HORIZONTE_DIAS_HABILES),
    )


# ── GET /api/consulta/sucursales ────────────────────
@router.get(
    "/sucursales",
    response_model=SucursalList,
    summary="Listar sucursales",
    description=(
        "Retorna las ubicaciones con su información geográfica y tipo (principal, estandar o "
        "bodega_central). SIN_SUCURSAL no se lista: no tiene inventario y no se puede filtrar por ella."
    ),
)
def listar_sucursales(
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text("""
            SELECT id_sucursal, codigo_tienda, nombre, ciudad, departamento,
                   tipo, cluster, factor_volumen
            FROM dw.dim_sucursal
            WHERE tipo <> 'sin_terminal'
            ORDER BY id_sucursal
        """)
    ).fetchall()

    items = [
        SucursalItem(
            id_sucursal=r.id_sucursal,
            codigo_tienda=r.codigo_tienda,
            nombre=r.nombre,
            ciudad=r.ciudad,
            departamento=r.departamento,
            tipo=r.tipo,
            cluster=r.cluster,
            factor_volumen=float(r.factor_volumen) if r.factor_volumen is not None else None,
        )
        for r in rows
    ]

    return SucursalList(items=items, total=len(items))


# ── GET /api/consulta/proveedores ───────────────────
@router.get(
    "/proveedores",
    response_model=ProveedorList,
    summary="Listar proveedores",
    description="Retorna todos los proveedores con lead times y calificación.",
)
def listar_proveedores(
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text("""
            SELECT id_proveedor, codigo, razon_social, nit, ciudad,
                   telefono, email, lead_time_dias, categorias, calificacion
            FROM dw.dim_proveedor
            ORDER BY calificacion DESC
        """)
    ).fetchall()

    items = [
        ProveedorItem(
            id_proveedor=r.id_proveedor,
            codigo=r.codigo,
            razon_social=r.razon_social,
            nit=r.nit,
            ciudad=r.ciudad,
            telefono=r.telefono,
            email=r.email,
            lead_time_dias=r.lead_time_dias,
            categorias=list(r.categorias) if r.categorias else [],
            calificacion=float(r.calificacion) if r.calificacion else None,
        )
        for r in rows
    ]

    return ProveedorList(items=items, total=len(items))


# ── GET /api/consulta/proveedores/:id ───────────────
@router.get(
    "/proveedores/{id_proveedor}",
    response_model=ProveedorDetalle,
    summary="Detalle de proveedor",
    description="Retorna un proveedor por ID, incluyendo los productos que abastece (dw.producto_proveedor).",
)
def detalle_proveedor(
    id_proveedor: int,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.execute(
        text("""
            SELECT id_proveedor, codigo, razon_social, nit, ciudad,
                   telefono, email, lead_time_dias, categorias, calificacion
            FROM dw.dim_proveedor
            WHERE id_proveedor = :id
        """),
        {"id": id_proveedor},
    ).fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proveedor {id_proveedor} no encontrado",
        )

    categorias = list(row.categorias) if row.categorias else []

    # INV-25 (D5): los productos que abastece según dw.producto_proveedor
    productos_rows = db.execute(
        text(f"""
            SELECT {COLUMNAS_PRODUCTO}
            FROM dw.producto_proveedor pp
            JOIN dw.dim_producto p ON p.id_producto = pp.id_producto
            WHERE pp.id_proveedor = :id
            ORDER BY p.categoria, p.nombre
        """),
        {"id": id_proveedor},
    ).fetchall()

    productos = [ProductoItem(**producto_item(p)) for p in productos_rows]

    return ProveedorDetalle(
        id_proveedor=row.id_proveedor,
        codigo=row.codigo,
        razon_social=row.razon_social,
        nit=row.nit,
        ciudad=row.ciudad,
        telefono=row.telefono,
        email=row.email,
        lead_time_dias=row.lead_time_dias,
        categorias=categorias,
        calificacion=float(row.calificacion) if row.calificacion else None,
        productos=productos,
        total_productos=len(productos),
    )


# ── GET /api/consulta/categorias ────────────────────
@router.get(
    "/categorias",
    response_model=CategoriaList,
    summary="Listar categorías",
    description="Retorna categorías con conteo de productos y distribución perecedero/no perecedero.",
)
def listar_categorias(
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text("""
            SELECT categoria,
                   COUNT(*) as total_productos,
                   SUM(CASE WHEN es_perecedero THEN 1 ELSE 0 END) as perecederos,
                   SUM(CASE WHEN NOT es_perecedero THEN 1 ELSE 0 END) as no_perecederos
            FROM dw.dim_producto
            GROUP BY categoria
            ORDER BY total_productos DESC
        """)
    ).fetchall()

    items = [
        CategoriaItem(
            categoria=r.categoria,
            total_productos=r.total_productos,
            perecederos=r.perecederos,
            no_perecederos=r.no_perecederos,
        )
        for r in rows
    ]

    return CategoriaList(items=items, total=len(items))
