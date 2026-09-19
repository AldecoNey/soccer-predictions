"""Smoke test: lista las tablas creadas en Neon sin exponer la credencial."""

import sys

from sqlalchemy import inspect

sys.path.insert(0, ".")
from app.db import engine  # noqa: E402


def main() -> int:
    if engine is None:
        print("FALTA: DATABASE_URL no está definido en .env")
        return 1
    tables = sorted(inspect(engine).get_table_names())
    print("Tablas encontradas:", tables)
    expected = {"competitions", "seasons", "teams", "matches", "results", "alembic_version"}
    missing = expected - set(tables)
    if missing:
        print(f"FALTAN tablas: {missing}")
        return 1
    print("OK: todas las tablas esperadas están presentes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
