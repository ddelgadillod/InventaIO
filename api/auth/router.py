"""
InventAI/o — Auth Router
Endpoints: login, refresh, logout, me, password change.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone

from core.database import get_db
from core.security import (
    verify_password,
    hash_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from models.usuario import Usuario
from schemas.auth import (
    LoginRequest,
    RefreshRequest,
    PasswordChangeRequest,
    TokenResponse,
    UserProfile,
    MessageResponse,
)
from auth.dependencies import get_current_user

router = APIRouter(prefix="/api/auth", tags=["Auth"])


_blacklisted_tokens: set = set()


def is_blacklisted(token: str) -> bool:
    return token in _blacklisted_tokens


# ── POST /api/auth/login ────────────────────────────
@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Iniciar sesión",
    description="Autentica con email y contraseña. Retorna access_token + refresh_token.",
)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    # Buscar usuario por email
    user = db.query(Usuario).filter(Usuario.email == body.email).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
        )

    if not user.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta desactivada. Contacte al administrador.",
        )

    # Verificar contraseña
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
        )

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
    description="Recibe un refresh_token válido y retorna nuevos access_token + refresh_token.",
)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    # Verificar que no esté en blacklist
    if is_blacklisted(body.refresh_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalidado. Inicie sesión nuevamente.",
        )

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

    # Invalidar refresh token anterior
    _blacklisted_tokens.add(body.refresh_token)

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
    description="Invalida el refresh_token actual para impedir renovación.",
)
def logout(
    body: RefreshRequest,
    user: Usuario = Depends(get_current_user),
):
    _blacklisted_tokens.add(body.refresh_token)
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
    user.updated_at = datetime.now(timezone.utc)
    db.commit()

    return MessageResponse(message="Contraseña actualizada exitosamente")
