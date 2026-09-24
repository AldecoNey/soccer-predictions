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
        # sobre miles de partidos) mueren con "server closed the connection unexpectedly".
        connect_args={
            # Sin esto, cuando el proxy de Neon tira la conexión sin mandar
            # FIN/RST (visto en vivo: pipelines/train_logistic.py colgado 22+
            # min con CPU en 0, sin ninguna excepción — with_retries() nunca
            # se activa porque no hay OperationalError que atrapar, el socket
            # simplemente nunca vuelve de un read()). Los keepalives de TCP
            # hacen que el SO detecte la conexión muerta y la cierre con error
            # en vez de bloquear para siempre.
            #
            # Nota honesta (ADR-0022, 2026-09-24): esto NO eliminó el problema
            # — volvió a colgarse (8-24 min, mismo síntoma) durante el
            # experimento de H2H, en Windows. Los valores de acá se ajustaron
            # más agresivos (detección en ~25s en vez de ~60s) como mejora de
            # mejor esfuerzo, no como solución confirmada — es posible que
            # libpq/Windows no propague estos parámetros al socket real de la
            # misma forma que en Linux, o que el problema esté en un punto de
            # la red que ni el keepalive alcanza a ver. Mientras no bloquee
            # trabajo (hay un workaround de cache en pipelines/train_logistic_h2h.py
            # para este caso puntual), queda como riesgo operacional conocido
            # a revisar en serio si Fase 7 (pipeline en vivo) lo vuelve crítico.
            "keepalives": 1,
            "keepalives_idle": 10,
            "keepalives_interval": 5,
            "keepalives_count": 3,
            # Se intentó agregar "options": "-c statement_timeout=30000" acá
            # como defensa adicional — Neon lo rechaza en su endpoint pooled
            # ("unsupported startup parameter in options: statement_timeout...
            # use unpooled connection", verificado en vivo, rompía TODOS los
            # tests). Revertido. Si se quiere un statement_timeout real, hay
            # que setearlo por sesión después de conectar (evento `connect` de
            # SQLAlchemy + `SET statement_timeout`), no vía connect_args — no
            # se implementó esa versión, queda pendiente si el problema de
            # cuelgues sigue apareciendo.
        },
    )
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
