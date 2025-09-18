# apps/agent_service/db.py
# ---------------------------------------------------------------------------
#  PostgreSQL connection and session management (SQLAlchemy)
# ---------------------------------------------------------------------------

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# URL → uses DATABASE_URL environment variable if it exists
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://scout:scout@db:5432/scouting",
)

# 1️⃣ engine and session factory
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# 2️⃣ context manager for use with `with`
#@contextmanager
def get_session():
    return SessionLocal() 

