"""
InventAI/o — Security utilities
JWT token creation/verification and password hashing with bcrypt.
"""
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from passlib.context import CryptContext

from core.config import get_settings

settings = get_settings()

# ── Password hashing ────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Hash a plain-text password with bcrypt."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    return pwd_context.verify(plain, hashed)


# ── JWT tokens ──────────────────────────────────────
def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a short-lived access token."""
    to_encode = data.copy()
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(
    data: dict, expires_delta: timedelta | None = None, inicio: datetime | None = None
) -> str:
    """Create a long-lived refresh token.

    INV-41 (D8, ASVS 3.3.2): `auth_time` es la hora del login (`inicio`; sin ella, ahora) y pasa de cada refresh
    token al siguiente. El vencimiento nunca pasa de SESION_MAX_DIAS desde ahí: un token pasado de ese tope ya
    llega vencido, la renovación lo rechaza como a cualquier otro y hay que volver a iniciar sesión.
    """
    ahora = datetime.now(UTC)
    inicio = inicio or ahora
    to_encode = data.copy()
    expire = min(
        ahora + (expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)),
        inicio + timedelta(days=settings.SESION_MAX_DIAS),
    )
    # INV-41: el jti hace único cada token. Sin él, dos logins de la misma cuenta en el mismo segundo dan el mismo
    # token, y revocar uno (lista negra) revocaría el otro
    to_encode.update({
        "exp": expire, "type": "refresh", "jti": secrets.token_hex(16), "auth_time": int(inicio.timestamp()),
    })
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict | None:
    """Decode and validate a JWT token. Returns payload or None."""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except jwt.InvalidTokenError:
        return None
