"""
InventAI/o — Consulta Router (Catálogos y Proveedores)
INV-008: Endpoints de solo lectura para información maestra.
Uses raw SQL via SQLAlchemy text() to avoid ORM cross-schema FK issues.
"""
import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import text

from core.database import get_db
from auth.dependencies import get_current_user
from models.usuario import Usuario
from schemas.consulta import (
    ProductoItem, ProductoList, ProductoDetalle,
    SucursalItem, SucursalList,
    ProveedorItem, ProveedorList, ProveedorDetalle,
    CategoriaItem, CategoriaList,
)

router = APIRouter(prefix="/api/consulta", tags=["Consulta"])


# ── GET /api/consulta/productos ─────────────────────
@router.get(
    "/productos",
    response_model=ProductoList,
    summary="Listar productos",
    description="Retorna productos paginados con filtros opcionales por categoría, familia, perecedero y búsqueda por nombre.",
)
def listar_productos(
    page: int = Query(1, ge=1, description="Página"),
    page_size: int = Query(20, ge=1, le=100, description="Items por página"),
    categoria: Optional[str] = Query(None, description="Filtrar por categoría"),
    familia: Optional[str] = Query(None, description="Filtrar por familia"),
    perecedero: Optional[bool] = Query(None, description="Filtrar por perecedero"),
    busqueda: Optional[str] = Query(None, description="Buscar en nombre o familia"),
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
        conditions.append("(p.nombre ILIKE :busqueda OR p.familia ILIKE :busqueda)")
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
        SELECT id_producto, codigo_item, nombre, familia, clase, categoria,
               es_perecedero, unidad_medida, precio_base, costo_base,
               margen_pct, iva_pct
        FROM dw.dim_producto p
        {where}
        ORDER BY categoria, nombre
        LIMIT :limit OFFSET :offset
    """
    rows = db.execute(text(query_sql), params).fetchall()

    items = [
        ProductoItem(
            id_producto=r.id_producto,
            codigo_item=r.codigo_item,
            nombre=r.nombre,
            familia=r.familia,
            clase=r.clase,
            categoria=r.categoria,
            es_perecedero=r.es_perecedero,
            unidad_medida=r.unidad_medida,
            precio_base=float(r.precio_base) if r.precio_base else None,
            costo_base=float(r.costo_base) if r.costo_base else None,
            margen_pct=float(r.margen_pct) if r.margen_pct else None,
            iva_pct=float(r.iva_pct),
        )
        for r in rows
    ]

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
    description="Retorna un producto por ID, incluyendo los proveedores que lo abastecen.",
)
def detalle_producto(
    id_producto: int,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.execute(
        text("""
            SELECT id_producto, codigo_item, nombre, familia, clase, categoria,
                   es_perecedero, unidad_medida, precio_base, costo_base,
                   margen_pct, iva_pct
            FROM dw.dim_producto
            WHERE id_producto = :id
        """),
        {"id": id_producto},
    ).fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Producto {id_producto} no encontrado",
        )

    # Find providers that supply this product's category
    proveedores = db.execute(
        text("""
            SELECT razon_social
            FROM dw.dim_proveedor
            WHERE :categoria = ANY(categorias)
            ORDER BY calificacion DESC
        """),
        {"categoria": row.categoria},
    ).fetchall()

    return ProductoDetalle(
        id_producto=row.id_producto,
        codigo_item=row.codigo_item,
        nombre=row.nombre,
        familia=row.familia,
        clase=row.clase,
        categoria=row.categoria,
        es_perecedero=row.es_perecedero,
        unidad_medida=row.unidad_medida,
        precio_base=float(row.precio_base) if row.precio_base else None,
        costo_base=float(row.costo_base) if row.costo_base else None,
        margen_pct=float(row.margen_pct) if row.margen_pct else None,
        iva_pct=float(row.iva_pct),
        proveedores=[p.razon_social for p in proveedores],
    )


# ── GET /api/consulta/sucursales ────────────────────
@router.get(
    "/sucursales",
    response_model=SucursalList,
    summary="Listar sucursales",
    description="Retorna todas las sucursales con su información geográfica y tipo.",
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
            factor_volumen=float(r.factor_volumen),
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
    description="Retorna un proveedor por ID, incluyendo los productos que abastece.",
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

    # Get products in those categories
    productos = []
    if categorias:
        placeholders = ", ".join(f":cat{i}" for i in range(len(categorias)))
        cat_params = {f"cat{i}": c for i, c in enumerate(categorias)}

        productos_rows = db.execute(
            text(f"""
                SELECT id_producto, codigo_item, nombre, familia, clase, categoria,
                       es_perecedero, unidad_medida, precio_base, costo_base,
                       margen_pct, iva_pct
                FROM dw.dim_producto
                WHERE categoria IN ({placeholders})
                ORDER BY categoria, nombre
            """),
            cat_params,
        ).fetchall()

        productos = [
            ProductoItem(
                id_producto=p.id_producto,
                codigo_item=p.codigo_item,
                nombre=p.nombre,
                familia=p.familia,
                clase=p.clase,
                categoria=p.categoria,
                es_perecedero=p.es_perecedero,
                unidad_medida=p.unidad_medida,
                precio_base=float(p.precio_base) if p.precio_base else None,
                costo_base=float(p.costo_base) if p.costo_base else None,
                margen_pct=float(p.margen_pct) if p.margen_pct else None,
                iva_pct=float(p.iva_pct),
            )
            for p in productos_rows
        ]

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
