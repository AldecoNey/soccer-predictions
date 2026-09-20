"""build_features(match_id, as_of_timestamp): el único punto de entrada
autorizado para calcular features de un partido (ADR-0007, ADR-0006).

Regla no negociable: ningún dato con timestamp posterior a `as_of_timestamp`
puede influir en el resultado. En particular, un partido histórico solo
cuenta como "conocido" RESULT_KNOWN_BUFFER después de su kickoff (el
resultado real no existe instantáneamente al pitazo inicial) — nunca se usa
`Result.finalized_at` para este corte porque esa columna registra cuándo nosotros
cargamos el dato, no cuándo el resultado existió en el mundo real.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Match, Result

RESULT_KNOWN_BUFFER = timedelta(hours=3)
DEFAULT_FORM_WINDOW = 5


def _team_past_results(session: Session, team_id: uuid.UUID, match_id: uuid.UUID, as_of_timestamp: datetime, window: int):
    cutoff = as_of_timestamp - RESULT_KNOWN_BUFFER
    stmt = (
        select(Match, Result)
        .join(Result, Result.match_id == Match.id)
        .where(
            or_(Match.home_team_id == team_id, Match.away_team_id == team_id),
            Match.id != match_id,
            Match.kickoff_at <= cutoff,
            Match.status == "finished",
        )
        .order_by(Match.kickoff_at.desc())
        .limit(window)
    )
    return session.execute(stmt).all()


def _team_form(
    session: Session,
    team_id: uuid.UUID,
    match_id: uuid.UUID,
    as_of_timestamp: datetime,
    window: int,
    target_kickoff_at: datetime,
) -> dict:
    rows = _team_past_results(session, team_id, match_id, as_of_timestamp, window)
    wins = draws = losses = goals_for = goals_against = 0
    last_kickoff = None
    for match, result in rows:
        is_home = match.home_team_id == team_id
        gf = result.home_score if is_home else result.away_score
        ga = result.away_score if is_home else result.home_score
        goals_for += gf
        goals_against += ga
        if gf > ga:
            wins += 1
        elif gf == ga:
            draws += 1
        else:
            losses += 1
        if last_kickoff is None or match.kickoff_at > last_kickoff:
            last_kickoff = match.kickoff_at

    played = len(rows)
    points = wins * 3 + draws
    return {
        "matches_played": played,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "goal_difference": goals_for - goals_against,
        "points_per_game": (points / played) if played else None,
        # Descanso HASTA el partido que se está prediciendo, no hasta el
        # snapshot que lo calcula — son cosas distintas. `target_kickoff_at`
        # es el kickoff del propio partido (ya conocido de antemano, ver
        # fixtures — no es leakage usarlo) y es un valor FIJO
        # independientemente del horizonte (T-72/T-24/T-2) del snapshot. Antes
        # se restaba as_of_timestamp acá, lo que hacía que el mismo partido
        # tuviera un "descanso" distinto según a cuántas horas del kickoff se
        # generara el snapshot — no tenía sentido futbolístico (encontrado en
        # revisión de Fase 6).
        "rest_days": (target_kickoff_at - last_kickoff).days if last_kickoff else None,
    }


def build_features(
    session: Session,
    match_id: uuid.UUID,
    as_of_timestamp: datetime,
    window: int = DEFAULT_FORM_WINDOW,
) -> dict:
    """Calcula el vector de features de un partido usando solo información
    con timestamp <= as_of_timestamp (respetando RESULT_KNOWN_BUFFER)."""
    match = session.get(Match, match_id)
    if match is None:
        raise ValueError(f"match {match_id} no existe")

    return {
        "match_id": str(match_id),
        "as_of": as_of_timestamp.isoformat(),
        "window": window,
        "home": _team_form(session, match.home_team_id, match_id, as_of_timestamp, window, match.kickoff_at),
        "away": _team_form(session, match.away_team_id, match_id, as_of_timestamp, window, match.kickoff_at),
    }
