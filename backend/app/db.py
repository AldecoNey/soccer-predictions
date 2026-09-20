import time
from typing import Callable, TypeVar

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

T = TypeVar("T")


def to_psycopg_url(database_url: str) -> str:
    """Neon/most providers hand out postgresql:// URLs, which SQLAlchemy
    defaults to psycopg2. We install psycopg (v3), so rewrite the scheme."""
    return database_url.replace("postgresql://", "postgresql+psycopg://", 1)


engine = (
    create_engine(
        to_psycopg_url(settings.database_url),
        pool_pre_ping=True,  # Neon puede cerrar conexiones inactivas/reescalar a cero;
        pool_recycle=280,  # sin esto, scripts largos (ej. pipelines/train_logistic.py
    )  # sobre miles de partidos) mueren con "server closed the connection unexpectedly".
    if settings.database_url
    else None
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def with_retries(session: Session, fn: Callable[[], T], max_attempts: int = 3, backoff_seconds: float = 1.0) -> T:
    """Reintenta fn() ante caídas transitorias de conexión — Neon (serverless)
    puede cerrar una conexión ya en uso sin previo aviso, algo que
    pool_pre_ping NO detecta (solo valida conexiones al sacarlas del pool,
    no una que ya está activa en medio de una transacción larga). Hace
    rollback antes de reintentar para dejar la sesión en estado limpio."""
    last_error: OperationalError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except OperationalError as exc:
            last_error = exc
            session.rollback()
            if attempt < max_attempts:
                time.sleep(backoff_seconds * attempt)
    raise last_error
