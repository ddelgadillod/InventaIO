"""
InventAI/o — Auth Router
Endpoints: login, refresh, logout, me, password change.
"""
import logging
from datetime import UTC, datetime
from functools import lru_cache

import redis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from auth.limite_login import LimiteLogin, get_limite_login
from auth.lista_negra import ListaNegra, get_lista_negra
from core.database import get_db
from core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from models.usuario import Usuario
from schemas.auth import (
    LoginRequest,
    MessageResponse,
    PasswordChangeRequest,
    RefreshRequest,
    TokenResponse,
    UserProfile,
)

router = APIRouter(prefix="/api/auth", tags=["Auth"])
log = logging.getLogger(__name__)

# INV-41 (D4): el mismo 401 para un correo inexistente, una clave incorrecta y una cuenta desactivada
CREDENCIALES_INVALIDAS = "Credenciales inválidas"


@lru_cache
def _hash_ficticio() -> str:
    """Un hash del mismo costo que los reales: con un correo inexistente, el login tarda lo mismo (INV-41, H2)."""
    return hash_password("inventaio-hash-ficticio-para-igualar-el-tiempo")


_hash_ficticio()   # al importar: ni el primer login con un correo inexistente tarda distinto


# ── POST /api/auth/login ────────────────────────────
@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Iniciar sesión",
    description=(
        "Autentica con email y contraseña. Retorna access_token + refresh_token. Un correo inexistente, una "
        "clave incorrecta y una cuenta desactivada dan el mismo 401 (INV-41). Tras varios intentos fallidos "
        "responde 429 con Retry-After (INV-66)."
    ),
)
def login(
    body: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
    limite: LimiteLogin = Depends(get_limite_login),
):
    # INV-66 (CA 5): antes de la base y de bcrypt, para que un ataque no cueste CPU
    ip = request.client.host if request.client else "desconocida"
    limite.verificar(body.email, ip)

    # INV-41 (H1, H2 y T4): la clave se verifica siempre, también sin usuario (contra un hash del mismo costo), y
    # la cuenta desactivada se revisa después. Las tres fallas dan el mismo 401 y cuentan para el límite
    user = db.query(Usuario).filter(Usuario.email == body.email).first()
    clave_correcta = verify_password(body.password, user.password_hash if user else _hash_ficticio())

    if user is None or not clave_correcta or not user.activo:
        limite.registrar_fallo(body.email, ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=CREDENCIALES_INVALIDAS,
        )

    limite.registrar_exito(body.email, ip)

    # Generar tokens
    token_data = {"sub": str(user.id), "email": user.email, "rol": user.rol}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


# ── POST /api/auth/refresh ─────────────────────────
@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Renovar tokens",
    description=(
        "Recibe un refresh_token válido y retorna nuevos access_token + refresh_token. Cada refresh token sirve "
        "una sola vez: el usado queda revocado en Redis hasta su vencimiento (INV-41)."
    ),
)
def refresh(
    body: RefreshRequest,
    db: Session = Depends(get_db),
    lista: ListaNegra = Depends(get_lista_negra),
):
    payload = decode_token(body.refresh_token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido o expirado",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere un refresh token",
        )

    user_id = payload.get("sub")
    user = db.query(Usuario).filter(Usuario.id == user_id).first()

    if user is None or not user.activo:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado o desactivado",
        )

    # INV-41 (T2 y D2): marcar el token como usado es la revisión. SET NX es atómico: de dos renovaciones con el
    # mismo token gana una. Sin Redis, falla cerrada: la persona vuelve a iniciar sesión
    try:
        revocado_ahora = lista.revocar(body.refresh_token, payload["exp"])
    except redis.RedisError as e:
        log.warning("Redis no responde (%s): la renovación de sesión se rechaza", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No se pudo renovar la sesión. Inicie sesión nuevamente.",
        ) from None
    if not revocado_ahora:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalidado. Inicie sesión nuevamente.",
        )

    # Generar nuevos tokens
    token_data = {"sub": str(user.id), "email": user.email, "rol": user.rol}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


# ── POST /api/auth/logout ──────────────────────────
@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Cerrar sesión",
    description=(
        "Revoca el refresh_token de la sesión para impedir su renovación. Un token inválido o de otro usuario se "
        "ignora. Responde 503 si no se pudo registrar el cierre (INV-41)."
    ),
)
def logout(
    body: RefreshRequest,
    user: Usuario = Depends(get_current_user),
    lista: ListaNegra = Depends(get_lista_negra),
):
    # INV-41 (T3): solo un refresh token vigente de quien cierra la sesión. Lo demás ya no sirve o no es suyo
    payload = decode_token(body.refresh_token)
    if payload and payload.get("type") == "refresh" and payload.get("sub") == str(user.id):
        try:
            lista.revocar(body.refresh_token, payload["exp"])
        except redis.RedisError as e:
            log.error("Redis no responde (%s): no se registró el cierre de sesión del usuario %s", e, user.id)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No se pudo cerrar la sesión en el servidor. Intente de nuevo.",
            ) from None
    return MessageResponse(message="Sesión cerrada exitosamente")


# ── GET /api/auth/me ────────────────────────────────
@router.get(
    "/me",
    response_model=UserProfile,
    summary="Perfil del usuario autenticado",
    description="Retorna los datos del usuario autenticado, incluyendo nombre de sucursal.",
)
def me(
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Obtener nombre de sucursal si tiene asignada
    sucursal_nombre = None
    if user.id_sucursal:
        row = db.execute(
            text("SELECT nombre FROM dw.dim_sucursal WHERE id_sucursal = :id"),
            {"id": user.id_sucursal}
        ).fetchone()
        if row:
            sucursal_nombre = row[0]

    return UserProfile(
        id=user.id,
        email=user.email,
        nombre=user.nombre,
        rol=user.rol,
        id_sucursal=user.id_sucursal,
        sucursal_nombre=sucursal_nombre,
        activo=user.activo,
        created_at=user.created_at,
    )


# ── PATCH /api/auth/password ────────────────────────
@router.patch(
    "/password",
    response_model=MessageResponse,
    summary="Cambiar contraseña",
    description="Cambia la contraseña del usuario autenticado. Requiere la contraseña actual.",
)
def change_password(
    body: PasswordChangeRequest,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Verificar contraseña actual
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña actual es incorrecta",
        )

    # Validar que la nueva sea diferente
    if body.current_password == body.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La nueva contraseña debe ser diferente a la actual",
        )

    # Actualizar
    user.password_hash = hash_password(body.new_password)
    user.updated_at = datetime.now(UTC)
    db.commit()

    return MessageResponse(message="Contraseña actualizada exitosamente")
