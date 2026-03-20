"""
InventAI/o — Auth dependencies for FastAPI
Provides get_current_user and require_role() for RBAC.
"""
from typing import List

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from core.database import get_db
from core.security import decode_token
from models.usuario import Usuario


bearer_scheme = HTTPBearer(auto_error=True)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Usuario:
    """
    Extract and validate JWT from Authorization header.
    Returns the authenticated Usuario or raises 401.
    """
    token = credentials.credentials
    payload = decode_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere un access token, no un refresh token",
        )

    user_id = int(payload.get("sub"))
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token sin identificador de usuario",
        )

    user = db.query(Usuario).filter(Usuario.id == user_id).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado",
        )

    if not user.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta desactivada",
        )

    return user


def require_role(allowed_roles: List[str]):
    """
    Factory that returns a dependency checking the user's role.

    Usage:
        @router.get("/admin-only", dependencies=[Depends(require_role(["gerente"]))])
        def admin_endpoint(): ...

    Or in the function signature:
        def endpoint(user: Usuario = Depends(require_role(["gerente", "admin_sucursal"]))):
    """
    def role_checker(user: Usuario = Depends(get_current_user)) -> Usuario:
        if user.rol not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Rol '{user.rol}' no tiene acceso. Se requiere: {', '.join(allowed_roles)}",
            )
        return user
    return role_checker
