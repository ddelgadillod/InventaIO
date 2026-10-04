"""
InventAI/o — Regla de permisos por ubicación (INV-25)
Una sola regla para inventario, alertas y reportes: qué ubicación puede
filtrar cada rol según el tipo de dato. Ver docs/INV-25-requerimientos.md
(D1, D2, R1, R2).

| Rol                        | Stock                         | Alertas y ventas |
| gerente, admin_bodega      | todas                         | todas            |
| admin_sucursal             | la suya; la Bodega a pedido   | solo la suya     |
"""
from typing import Dict, Optional

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from models.usuario import Usuario

STOCK = "stock"
ALERTAS = "alertas"
VENTAS = "ventas"

BODEGA = "bodega_central"
ROLES_GLOBALES = ("gerente", "admin_bodega")

# SIN_SUCURSAL (sin_terminal) no es una ubicación filtrable (D7)
SQL_UBICACIONES = text("""
    SELECT id_sucursal, nombre, tipo FROM dw.dim_sucursal
    WHERE tipo <> 'sin_terminal'
    ORDER BY id_sucursal
""")

# Expresión SQL de tipo_ubicacion (D6) sobre dw.dim_sucursal con alias s
SQL_TIPO_UBICACION = "CASE WHEN s.tipo = 'bodega_central' THEN 'bodega_central' ELSE 'sucursal' END"


def cargar_ubicaciones(db: Session) -> Dict[int, dict]:
    """id_sucursal -> {"nombre", "tipo"}, sin SIN_SUCURSAL."""
    return {r.id_sucursal: {"nombre": r.nombre, "tipo": r.tipo} for r in db.execute(SQL_UBICACIONES).fetchall()}


def resolver_sucursal(ubicaciones: Dict[int, dict], user: Usuario, sucursal_id: Optional[int],
                      dato: str) -> Optional[int]:
    """El id_sucursal a filtrar (None = todas) para `user` y el tipo de `dato`.

    422 si sucursal_id no existe o es SIN_SUCURSAL (R2). gerente y admin_bodega
    ven todo (D1). admin_sucursal ve su sucursal; la Bodega solo en el stock
    (D2); otra ubicación pedida explícitamente da 403 (R1)."""
    if sucursal_id is not None and sucursal_id not in ubicaciones:
        validas = ", ".join(f"{i} ({u['nombre']})" for i, u in ubicaciones.items())
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"sucursal_id inválido: {sucursal_id}. Válidos: {validas}")
    if user.rol in ROLES_GLOBALES:
        return sucursal_id
    propia = ubicaciones.get(user.id_sucursal)
    if propia is None or propia["tipo"] == BODEGA:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El usuario no tiene una sucursal asignada")
    if sucursal_id is None or sucursal_id == user.id_sucursal:
        return user.id_sucursal
    if dato == STOCK and ubicaciones[sucursal_id]["tipo"] == BODEGA:
        return sucursal_id
    extra = "; la Bodega Central, solo en el stock" if ubicaciones[sucursal_id]["tipo"] == BODEGA else ""
    raise HTTPException(status.HTTP_403_FORBIDDEN, f"Solo puede consultar su sucursal ({propia['nombre']}){extra}")


def filtro_sucursal(db: Session, user: Usuario, sucursal_id: Optional[int], dato: str,
                    alias: str) -> tuple:
    """(condición SQL, parámetros) para filtrar `alias.id_sucursal` según la regla."""
    suc = resolver_sucursal(cargar_ubicaciones(db), user, sucursal_id, dato)
    if suc is None:
        return "", {}
    return f"AND {alias}.id_sucursal = :suc_permitida", {"suc_permitida": suc}
