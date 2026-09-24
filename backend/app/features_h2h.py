"""head_to_head_features (Fase 6, ADR-0022): a diferencia de rotation_index
(app/features_lineup.py, ver ADR-0011), esta señal NO tiene el problema de
oráculo — solo usa partidos ENTRE estos dos equipos que ya terminaron antes
de `as_of_timestamp` (con el mismo corte RESULT_KNOWN_BUFFER que el resto de
app/features.py), algo legítimamente disponible antes del kickoff del
partido que se está prediciendo. Por eso es un candidato real a modelo
desplegable, no solo diagnóstico.

`MASTER_ARCHITECTURE_V1.md` la marca como "candidato a testear y descartar
en Fase 6, no como feature garantizada" — este módulo es exactamente ese
test.
"""

import uuid
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.features import RESULT_KNOWN_BUFFER
from app.models import Match, Result

DEFAULT_H2H_WINDOW = 5


def _past_meetings(
    session: Session,
    match_id: uuid.UUID,
    home_team_id: uuid.UUID,
    away_team_id: uuid.UUID,
    as_of_timestamp: datetime,
    window: int,
):
    """Partidos ya terminados entre estos dos equipos, en cualquier orden de
    localía histórico (un cruce cuenta como encuentro sin importar quién fue
    local esa vez), respetando el mismo corte que _team_past_results en
    app/features.py — no se reimplementa el filtro a mano, se reutiliza
    RESULT_KNOWN_BUFFER de ahí para no tener dos definiciones de "conocido"."""
    cutoff = as_of_timestamp - RESULT_KNOWN_BUFFER
    stmt = (
        select(Match, Result)
        .join(Result, Result.match_id == Match.id)
        .where(
            or_(
                (Match.home_team_id == home_team_id) & (Match.away_team_id == away_team_id),
                (Match.home_team_id == away_team_id) & (Match.away_team_id == home_team_id),
            ),
            Match.id != match_id,
            Match.kickoff_at <= cutoff,
            Match.status == "finished",
        )
        .order_by(Match.kickoff_at.desc())
        .limit(window)
    )
    return session.execute(stmt).all()


def head_to_head_features(
    session: Session,
    match_id: uuid.UUID,
    home_team_id: uuid.UUID,
    away_team_id: uuid.UUID,
    as_of_timestamp: datetime,
    window: int = DEFAULT_H2H_WINDOW,
) -> dict:
    """Historial head-to-head entre home_team_id y away_team_id, desde la
    perspectiva del equipo que es LOCAL en el partido actual (match_id) —
    independientemente de qué lado ocuparon en los encuentros históricos.

    Sin encuentros previos (matches_played == 0, caso común y esperado, no un
    error): devuelve tasas/promedios en None, igual filosofía que rest_days
    en app/features.py cuando no hay partido anterior. Los defaults numéricos
    "neutros" para consumo del modelo (1/3, 0.0) viven en
    app/prediction_models/logistic.py::vectorize, no acá — este módulo solo
    reporta lo que efectivamente se observó.
    """
    rows = _past_meetings(session, match_id, home_team_id, away_team_id, as_of_timestamp, window)
    played = len(rows)
    if played == 0:
        return {
            "matches_played": 0,
            "home_win_rate": None,
            "draw_rate": None,
            "avg_goal_diff": None,
        }

    home_wins = draws = 0
    goal_diff_sum = 0
    for match, result in rows:
        # gf/ga desde la perspectiva del equipo que HOY es local, sin importar
        # de qué lado jugó en ese encuentro histórico.
        current_home_played_as_home = match.home_team_id == home_team_id
        gf = result.home_score if current_home_played_as_home else result.away_score
        ga = result.away_score if current_home_played_as_home else result.home_score
        goal_diff_sum += gf - ga
        if gf > ga:
            home_wins += 1
        elif gf == ga:
            draws += 1

    return {
        "matches_played": played,
        "home_win_rate": home_wins / played,
        "draw_rate": draws / played,
        "avg_goal_diff": goal_diff_sum / played,
    }
