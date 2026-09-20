"""Baseline 0 (ADR-0006): frecuencia histórica de 1-X-2, sin distinguir
equipos. Piso de referencia — cualquier modelo real debe superarlo."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.prediction_models.contract import validate_probability_triple
from app.prediction_models.data import get_historical_matches


def fit(session: Session, as_of_timestamp: datetime) -> dict:
    matches = get_historical_matches(session, as_of_timestamp)
    n = len(matches)
    if n == 0:
        return {"p_home": 1 / 3, "p_draw": 1 / 3, "p_away": 1 / 3, "n_matches": 0}

    home_wins = sum(1 for m in matches if m.home_goals > m.away_goals)
    draws = sum(1 for m in matches if m.home_goals == m.away_goals)
    away_wins = n - home_wins - draws

    return {
        "p_home": home_wins / n,
        "p_draw": draws / n,
        "p_away": away_wins / n,
        "n_matches": n,
    }


def predict_proba(params: dict) -> tuple[float, float, float]:
    """La predicción es la misma para cualquier partido — es la definición del baseline."""
    return validate_probability_triple(params["p_home"], params["p_draw"], params["p_away"])
