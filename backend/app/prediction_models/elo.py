"""Baseline 1 (ADR-0006): Elo + home advantage.

Conversión Elo -> 1-X-2: la tasa de empate se toma como constante global
(la frecuencia histórica observada, Baseline 0) y el resto de la masa de
probabilidad se reparte entre local/visitante proporcionalmente al
"expected score" de Elo. Es una simplificación deliberada y documentada
para un primer baseline interpretable — si Evaluation & Calibration
(Fase 5) muestra que la tasa de empate sí varía con la diferencia de
rating, se reemplaza por un modelo de empate no constante en una
iteración posterior, no ahora.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.prediction_models.data import get_historical_matches
from app.prediction_models.naive import fit as fit_naive

DEFAULT_INITIAL_RATING = 1500.0
DEFAULT_K_FACTOR = 20.0
DEFAULT_HOME_ADVANTAGE = 60.0


def fit(
    session: Session,
    as_of_timestamp: datetime,
    k_factor: float = DEFAULT_K_FACTOR,
    home_advantage: float = DEFAULT_HOME_ADVANTAGE,
    initial_rating: float = DEFAULT_INITIAL_RATING,
) -> dict:
    matches = get_historical_matches(session, as_of_timestamp)  # ya viene en orden cronológico
    ratings: dict[str, float] = {}

    def rating_of(team_id: uuid.UUID) -> float:
        return ratings.setdefault(str(team_id), initial_rating)

    for m in matches:
        r_home = rating_of(m.home_team_id)
        r_away = rating_of(m.away_team_id)
        expected_home = 1 / (1 + 10 ** (-(r_home + home_advantage - r_away) / 400))
        if m.home_goals > m.away_goals:
            actual_home = 1.0
        elif m.home_goals == m.away_goals:
            actual_home = 0.5
        else:
            actual_home = 0.0
        delta = k_factor * (actual_home - expected_home)
        ratings[str(m.home_team_id)] = r_home + delta
        ratings[str(m.away_team_id)] = r_away - delta

    naive = fit_naive(session, as_of_timestamp)
    return {
        "ratings": ratings,
        "home_advantage": home_advantage,
        "initial_rating": initial_rating,
        "k_factor": k_factor,
        "draw_rate": naive["p_draw"],
        "n_matches": len(matches),
    }


def predict_proba(home_team_id: uuid.UUID, away_team_id: uuid.UUID, params: dict) -> tuple[float, float, float]:
    r_home = params["ratings"].get(str(home_team_id), params["initial_rating"])
    r_away = params["ratings"].get(str(away_team_id), params["initial_rating"])
    expected_home = 1 / (1 + 10 ** (-(r_home + params["home_advantage"] - r_away) / 400))

    p_draw = params["draw_rate"]
    p_home = (1 - p_draw) * expected_home
    p_away = (1 - p_draw) * (1 - expected_home)
    return p_home, p_draw, p_away
