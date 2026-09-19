import pytest
from sqlalchemy.orm import Session

from app.db import engine


@pytest.fixture
def db_session():
    if engine is None:
        pytest.skip("DATABASE_URL no configurado — se omiten tests de integración de BD")
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()  # nunca deja datos de test en la BD real
        connection.close()
