"""Acceso a datos históricos compartido por los baselines (ADR-0006).

Reutiliza el mismo criterio anti-leakage que app/features.py: un partido
solo es "conocido" RESULT_KNOWN_BUFFER horas después de su kickoff.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.features import RESULT_KNOWN_BUFFER
from app.models import Match, Result, Season, Team


@dataclass(frozen=True)
class HistoricalMatch:
    id: uuid.UUID
    home_team_id: uuid.UUID
    away_team_id: uuid.UUID
    home_team_name: str
    away_team_name: str
    kickoff_at: datetime
    home_goals: int
    away_goals: int


def get_historical_matches(
    session: Session, as_of_timestamp: datetime, competition_id: uuid.UUID | None = None
) -> list[HistoricalMatch]:
    """Todos los partidos finalizados y ya "conocidos" a as_of_timestamp,
    en orden cronológico (requerido por Elo, que actualiza secuencialmente).

    `competition_id=None` (default, comportamiento sin cambios) trae partidos
    de TODAS las competiciones cargadas — hoy solo hay una (Liga Profesional
    Argentina), así que no cambia nada en la práctica. El parámetro existe
    para cuando se agregue una segunda competición (Copa Argentina, etc.):
    sin él, el Elo/Poisson-DC de Primera mezclaría partidos de otra
    competición en silencio — mismo tipo de bug real que ya se encontró y
    corrigió en `pipelines/evaluate_baselines.py::get_folds` (ADR-0007)."""
    cutoff = as_of_timestamp - RESULT_KNOWN_BUFFER
    HomeTeam = aliased(Team)
    AwayTeam = aliased(Team)
    stmt = (
        select(Match, Result, HomeTeam.name, AwayTeam.name)
        .join(Result, Result.match_id == Match.id)
        .join(HomeTeam, HomeTeam.id == Match.home_team_id)
        .join(AwayTeam, AwayTeam.id == Match.away_team_id)
        .where(Match.kickoff_at <= cutoff, Match.status == "finished")
        .order_by(Match.kickoff_at.asc())
    )
    if competition_id is not None:
        stmt = stmt.join(Season, Season.id == Match.season_id).where(Season.competition_id == competition_id)
    rows = session.execute(stmt).all()
    return [
        HistoricalMatch(
            id=match.id,
            home_team_id=match.home_team_id,
            away_team_id=match.away_team_id,
            home_team_name=home_name,
            away_team_name=away_name,
            kickoff_at=match.kickoff_at,
            home_goals=result.home_score,
            away_goals=result.away_score,
        )
        for match, result, home_name, away_name in rows
    ]
