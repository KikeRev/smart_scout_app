# apps/agent_service/db.py
# ---------------------------------------------------------------------------
#  Conexión y gestión de sesiones con PostgreSQL (SQLAlchemy)
# ---------------------------------------------------------------------------

import os
from pathlib import Path
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

# URL →  usa la variable de entorno DATABASE_URL si existe
# Leer URL desde entorno y normalizar para SQLAlchemy
_raw_db_url = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://scout:scout@db:5432/scouting",
)

# Normalizar de forma robusta usando make_url
try:
    _url = make_url(_raw_db_url)
    # Mapear alias incorrecto "postgres" al dialecto correcto
    if _url.drivername == "postgres":
        _url = _url.set(drivername="postgresql+psycopg2")
    # Solo cambiar postgresql:// a postgresql+psycopg2:// si no tiene driver
    elif _url.drivername == "postgresql" and "+" not in _url.drivername:
        _url = _url.set(drivername="postgresql+psycopg2")
    # Si ya tiene postgresql+psycopg2, dejarlo como está
    DATABASE_URL = str(_url)
except Exception:
    # Fallback a reemplazo por texto
    if _raw_db_url.startswith("postgres://"):
        _raw_db_url = _raw_db_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif _raw_db_url.startswith("postgresql://") and "+" not in _raw_db_url:
        _raw_db_url = _raw_db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    DATABASE_URL = _raw_db_url

# 1️⃣ motor y fábrica de sesiones
engine = create_engine(
    DATABASE_URL, 
    pool_pre_ping=True, 
    future=True,
    pool_recycle=300,  # Recrear conexiones cada 5 minutos
    pool_reset_on_return='commit'  # Reset conexiones al devolverlas
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# 2️⃣ context manager para usar con `with`
#@contextmanager
def get_session():

    return SessionLocal() 

