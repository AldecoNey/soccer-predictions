"""Smoke test: verifies DATABASE_URL is reachable without ever printing the credential."""

import sys

from sqlalchemy import create_engine, text

sys.path.insert(0, ".")
from app.config import settings  # noqa: E402


def main() -> int:
    if not settings.database_url:
        print("FALTA: DATABASE_URL no está definido en .env")
        return 1
    try:
        url = settings.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        engine = create_engine(url)
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version()")).scalar()
        print("OK: conexión exitosa a Postgres.")
        print(f"Versión del servidor: {version.split(',')[0]}")
        return 0
    except Exception as exc:
        print(f"ERROR de conexión: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
