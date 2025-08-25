# apps/agent_service/db.py
# ---------------------------------------------------------------------------
#  Conexión y gestión de sesiones con PostgreSQL (SQLAlchemy)
# ---------------------------------------------------------------------------

import os
from pathlib import Path
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# URL →  usa la variable de entorno DATABASE_URL si existe
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://scout:scout@db:5432/scouting",
)

# 1️⃣ motor y fábrica de sesiones
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# 2️⃣ context manager para usar con `with`
#@contextmanager
def get_session():

    return SessionLocal() 

