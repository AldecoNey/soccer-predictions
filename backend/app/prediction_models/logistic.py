"""Candidato 3 de ADR-0006: regresión logística multinomial. Puente entre
el rigor de Poisson/Dixon-Coles y la capacidad de incorporar variables
contextuales (Fase 6, ej. rotation_index) que un modelo puramente de goles
no captura."""

import numpy as np
from sklearn.linear_model import LogisticRegression

FEATURE_NAMES = ["home_ppg", "home_goal_diff", "home_rest_days", "away_ppg", "away_goal_diff", "away_rest_days"]
FEATURE_NAMES_WITH_ROTATION = [*FEATURE_NAMES, "home_rotation_index", "away_rotation_index"]

DEFAULT_REST_DAYS = 7.0  # equipo sin historial previo: se asume descanso "normal", no se inventa un valor extremo


def _safe(value, default=0.0):
    return default if value is None else value


def vectorize(features: dict, rotation: dict | None = None) -> list[float]:
    home, away = features["home"], features["away"]
    vec = [
        _safe(home["points_per_game"]),
        home["goal_difference"],
        _safe(home["rest_days"], DEFAULT_REST_DAYS),
        _safe(away["points_per_game"]),
        away["goal_difference"],
        _safe(away["rest_days"], DEFAULT_REST_DAYS),
    ]
    if rotation is not None:
        vec += [_safe(rotation.get("home")), _safe(rotation.get("away"))]
    return vec


def fit(x: np.ndarray, y: np.ndarray) -> LogisticRegression:
    model = LogisticRegression(max_iter=1000, C=1.0)
    model.fit(x, y)
    return model


def predict_proba(model: LogisticRegression, x: list[float]) -> tuple[float, float, float]:
    probs = model.predict_proba([x])[0]
    by_class = dict(zip(model.classes_, probs, strict=True))
    return by_class.get(0, 0.0), by_class.get(1, 0.0), by_class.get(2, 0.0)
