"""
InventAI/o — Usuarios de prueba (INV-26 fix, K8) y de la nube (INV-66, CA 6).

Crea o restablece, por email, los cinco usuarios con su ubicación, buscada por
nombre en dw.dim_sucursal. Reemplaza a reset_passwords.py (INV-004), que solo
cambiaba claves de usuarios ya creados por el ETL simulado; el ETL de la bodega
real no crea usuarios.

Desarrollo: todos con la clave admin123. Es idempotente: correrlo otra vez deja
lo mismo y devuelve las claves a admin123 después de probar el cambio de
contraseña. Fuera de ENTORNO=desarrollo se niega a correr.

    docker exec inventaio-api python -m scripts.seed_usuarios

Nube (--nube): una clave aleatoria por usuario, que se muestra una sola vez y no
se guarda (H2 de docs/INV-66-requerimientos.md). Correrlo otra vez cambia todas
las claves: sirve para rotarlas.

    docker compose -f docker-compose.prod.yml exec api python -m scripts.seed_usuarios --nube
"""
import argparse
import secrets

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.security import hash_password
from models.usuario import Usuario

CLAVE = "admin123"
BYTES_CLAVE_NUBE = 18   # token_urlsafe: 24 caracteres

# (email, nombre, rol, ubicación en dw.dim_sucursal)
USUARIOS = [
    ("gerente@inventaio.co", "Carlos Martínez", "gerente", None),
    ("admin.principal@inventaio.co", "Laura Gómez", "admin_sucursal", "PRINCIPAL"),
    ("admin.norte@inventaio.co", "Andrés Rivera", "admin_sucursal", "LA 21"),
    ("admin.sur@inventaio.co", "María Torres", "admin_sucursal", "GLORIETA"),
    ("bodega@inventaio.co", "Diego Sánchez", "admin_bodega", "BODEGA_CENTRAL"),
]


def claves_nube() -> dict[str, str]:
    """Una clave aleatoria por email, distinta de admin123."""
    return {email: secrets.token_urlsafe(BYTES_CLAVE_NUBE) for email, *_ in USUARIOS}


def elegir_claves(nube: bool, entorno: str) -> dict[str, str] | None:
    """None es admin123 para todos, que solo se acepta en desarrollo."""
    if nube:
        return claves_nube()
    if entorno != "desarrollo":
        raise SystemExit(f"ENTORNO={entorno}: la clave {CLAVE} es solo para desarrollo. Usar --nube")
    return None


def sembrar(db: Session, claves: dict[str, str] | None = None) -> list[tuple[str, str]]:
    """Crea o restablece los usuarios; devuelve [(email, "creado" | "restablecido")].
    Sin `claves`, todos quedan con CLAVE."""
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
        usuario.password_hash = hash_password(claves[email] if claves else CLAVE)
    db.commit()
    return resultado


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crea o restablece los cinco usuarios")
    parser.add_argument("--nube", action="store_true", help="claves aleatorias, mostradas una sola vez (INV-66)")
    args = parser.parse_args()

    from core.config import get_settings
    from core.database import SessionLocal

    claves = elegir_claves(args.nube, get_settings().ENTORNO)
    with SessionLocal() as sesion:
        for email, accion in sembrar(sesion, claves):
            print(f"{accion:<13} {email:<30} {claves[email]}" if claves else f"{accion:<13} {email}")
    if claves:
        print("Las claves se muestran solo esta vez: guárdalas fuera del repositorio.")
    else:
        print(f"Clave de todos: {CLAVE}")
