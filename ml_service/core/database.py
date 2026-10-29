"""
InventAI/o — ML Service: conexión a la bodega (SQLAlchemy)
INV-20 (fix). Solo lectura; mismo patrón que api/core/database.py.
"""
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def crear_engine(database_url: str) -> Engine:
    # pool_pre_ping: si Postgres se reinicia, la conexión rota se descarta en
    # vez de fallar la primera petición. connect_timeout acota /api/health.
    return create_engine(database_url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
