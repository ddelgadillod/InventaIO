"""
InventAI/o — Catálogo de la bodega para las recomendaciones (INV-23)
Productos (nombre y categoría), categorías y sucursales de dw, y la
normalización de los filtros: sin mayúsculas, acentos ni espacios de más (R3).
"""
import unicodedata
from typing import Dict, List, Optional, Tuple

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.database import get_db

# SIN_SUCURSAL (tipo sin_terminal) no es una ubicación que reciba o despache
TIPOS_SUCURSAL = ("principal", "estandar", "bodega_central")


def normalizar(valor: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", valor).encode("ascii", "ignore").decode()
    return " ".join(sin_acentos.lower().split())


def buscar(valor: str, opciones) -> Optional[str]:
    """El nombre canónico de `opciones` que coincide con `valor` normalizado."""
    clave = normalizar(valor)
    return next((o for o in opciones if normalizar(o) == clave), None)


class CatalogoBodega:
    def __init__(self, db: Session):
        self._db = db

    def sucursales(self) -> Dict[int, str]:
        """id_sucursal -> nombre, sin SIN_SUCURSAL."""
        rows = self._db.execute(text(
            "SELECT id_sucursal, nombre FROM dw.dim_sucursal WHERE tipo = ANY(:tipos) ORDER BY id_sucursal"
        ), {"tipos": list(TIPOS_SUCURSAL)}).fetchall()
        return {r.id_sucursal: r.nombre for r in rows}

    def categorias(self) -> List[str]:
        rows = self._db.execute(text("SELECT DISTINCT categoria FROM dw.dim_producto ORDER BY categoria")).fetchall()
        return [r.categoria for r in rows]

    def productos(self) -> Dict[str, Tuple[str, str]]:
        """codigo_item -> (nombre, categoria)."""
        rows = self._db.execute(text("SELECT codigo_item, nombre, categoria FROM dw.dim_producto")).fetchall()
        return {r.codigo_item: (r.nombre, r.categoria) for r in rows}


def get_catalogo(db: Session = Depends(get_db)) -> CatalogoBodega:
    return CatalogoBodega(db)
