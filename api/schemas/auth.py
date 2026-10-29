"""
InventAI/o — Pydantic schemas for Auth module
Request/response models for login, tokens, profile, password change.
"""
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

# ── Requests ────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)

    model_config = {"json_schema_extra": {"example": {
        "email": "gerente@inventaio.co",
        "password": "admin123"
    }}}


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)

    model_config = {"json_schema_extra": {"example": {
        "current_password": "admin123",
        "new_password": "nuevaPassword456"
    }}}


# ── Responses ───────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserProfile(BaseModel):
    id: int
    email: str
    nombre: str
    rol: str
    id_sucursal: int | None = None
    sucursal_nombre: str | None = None
    activo: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    message: str
