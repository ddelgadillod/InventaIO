"""
InventAI/o — Usuarios de prueba (INV-26 fix, K8). Solo para desarrollo.

Crea o restablece, por email, los cinco usuarios de prueba con la clave
admin123 y su ubicación, buscada por nombre en dw.dim_sucursal. Es idempotente:
correrlo otra vez deja lo mismo. Sirve también para devolver las claves a
admin123 después de probar el cambio de contraseña. Reemplaza a
reset_passwords.py (INV-004), que solo cambiaba claves de usuarios ya creados
por el ETL simulado; el ETL de la bodega real no crea usuarios.

    docker exec inventaio-api python -m scripts.seed_usuarios
"""
from typing import List, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.security import hash_password
from models.usuario import Usuario

CLAVE = "admin123"

# (email, nombre, rol, ubicación en dw.dim_sucursal)
USUARIOS = [
    ("gerente@inventaio.co", "Carlos Martínez", "gerente", None),
    ("admin.principal@inventaio.co", "Laura Gómez", "admin_sucursal", "PRINCIPAL"),
    ("admin.norte@inventaio.co", "Andrés Rivera", "admin_sucursal", "LA 21"),
    ("admin.sur@inventaio.co", "María Torres", "admin_sucursal", "GLORIETA"),
    ("bodega@inventaio.co", "Diego Sánchez", "admin_bodega", "BODEGA_CENTRAL"),
]


def sembrar(db: Session) -> List[Tuple[str, str]]:
    """Crea o restablece los usuarios; devuelve [(email, "creado" | "restablecido")]."""
    ids = {r.nombre: r.id_sucursal for r in db.execute(text("SELECT id_sucursal, nombre FROM dw.dim_sucursal"))}
    faltan = sorted({suc for *_, suc in USUARIOS if suc and suc not in ids})
    if faltan:
        raise SystemExit(f"La bodega no tiene las ubicaciones {faltan}: cargarla antes (docs/AMBIENTE-DESARROLLO.md)")

    resultado = []
    for email, nombre, rol, sucursal in USUARIOS:
        usuario = db.query(Usuario).filter(Usuario.email == email).first()
        resultado.append((email, "restablecido" if usuario else "creado"))
        if usuario is None:
            usuario = Usuario(email=email)
            db.add(usuario)
        usuario.nombre, usuario.rol, usuario.activo = nombre, rol, True
        usuario.id_sucursal = ids.get(sucursal)
        usuario.password_hash = hash_password(CLAVE)
    db.commit()
    return resultado


if __name__ == "__main__":
    from core.database import SessionLocal

    with SessionLocal() as sesion:
        for email, accion in sembrar(sesion):
            print(f"{accion:<13} {email}")
    print(f"Clave de todos: {CLAVE}")
