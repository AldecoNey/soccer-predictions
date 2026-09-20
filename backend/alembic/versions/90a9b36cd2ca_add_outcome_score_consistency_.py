"""add outcome-score consistency constraint to results

Revision ID: 90a9b36cd2ca
Revises: c35bf0966afa
Create Date: 2026-09-20 18:21:50.630826

"""
from typing import Sequence, Union

from alembic import op


revision: str = '90a9b36cd2ca'
down_revision: Union[str, None] = 'c35bf0966afa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Autogenerate no detecta CheckConstraint nuevos (limitación conocida de
    # Alembic) — la corrida original generó este archivo vacío y se aplicó
    # sin revisar el contenido, lo que dejó el constraint sin crear en Neon
    # pese a que "alembic upgrade head" reportó éxito (encontrado por un test
    # que debía fallar y no fallaba — ADR-0015). Escrito a mano.
    op.create_check_constraint(
        "ck_results_outcome_matches_score",
        "results",
        "(home_score > away_score AND outcome = 'home') OR "
        "(away_score > home_score AND outcome = 'away') OR "
        "(home_score = away_score AND outcome = 'draw')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_results_outcome_matches_score", "results", type_="check")
