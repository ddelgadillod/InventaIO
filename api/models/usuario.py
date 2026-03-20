"""
InventAI/o — SQLAlchemy model for app.usuarios
Maps to the existing table created by init.sql.
"""
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, CheckConstraint
)
from sqlalchemy.sql import func
from core.database import Base


class Usuario(Base):
    __tablename__ = "usuarios"
    __table_args__ = (
        CheckConstraint(
            "rol IN ('gerente', 'admin_sucursal', 'admin_bodega')",
            name="ck_usuarios_rol"
        ),
        {"schema": "app"},
    )

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(150), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    nombre = Column(String(100), nullable=False)
    rol = Column(String(30), nullable=False)
    id_sucursal = Column(Integer, nullable=True)  # FK en DDL, no en ORM
    activo = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
