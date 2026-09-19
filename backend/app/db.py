from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings


def to_psycopg_url(database_url: str) -> str:
    """Neon/most providers hand out postgresql:// URLs, which SQLAlchemy
    defaults to psycopg2. We install psycopg (v3), so rewrite the scheme."""
    return database_url.replace("postgresql://", "postgresql+psycopg://", 1)


engine = create_engine(to_psycopg_url(settings.database_url)) if settings.database_url else None
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
