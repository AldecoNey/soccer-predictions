"""Candidato 3 de ADR-0006: regresión logística multinomial. Puente entre
el rigor de Poisson/Dixon-Coles y la capacidad de incorporar variables
contextuales (Fase 6, ej. rotation_index) que un modelo puramente de goles
no captura."""

import base64
import pickle

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from app.prediction_models.contract import validate_probability_triple

FEATURE_NAMES = ["home_ppg", "home_goal_diff", "home_rest_days", "away_ppg", "away_goal_diff", "away_rest_days"]
FEATURE_NAMES_WITH_ROTATION = [*FEATURE_NAMES, "home_rotation_index", "away_rotation_index"]
# ADR-0022: a diferencia de rotation_index, head_to_head_features (app/features_h2h.py)
# no tiene el problema de oráculo, así que es un candidato real de producción,
# no solo diagnóstico. Deliberadamente solo 2 features (no matches_played/draw_rate,
# que son útiles para leer `raw`/debugging pero no como input del modelo) para
# mantener la comparación en el mismo espíritu que rotation_index (+2 features).
FEATURE_NAMES_WITH_H2H = [*FEATURE_NAMES, "h2h_home_win_rate", "h2h_avg_goal_diff"]

DEFAULT_REST_DAYS = 7.0  # equipo sin historial previo: se asume descanso "normal", no se inventa un valor extremo
# Sin encuentros previos entre los dos equipos, 0.0 implicaría "el local
# siempre pierde" — una afirmación falsa que no está respaldada por ningún
# dato. 1/3 es neutro: "no hay evidencia a favor de ningún resultado", el
# mismo tipo de supuesto no informativo que ya se usa en baseline_naive
# (ver app/prediction_models/naive.py) para el caso sin historial.
DEFAULT_H2H_HOME_WIN_RATE = 1.0 / 3.0
DEFAULT_H2H_AVG_GOAL_DIFF = 0.0  # neutro, consistente con cómo el resto del código default-ea numéricos desconocidos


def _safe(value, default=0.0):
    return default if value is None else value


def vectorize(features: dict, rotation: dict | None = None, h2h: dict | None = None) -> list[float]:
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
    if h2h is not None:
        vec += [
            _safe(h2h.get("home_win_rate"), DEFAULT_H2H_HOME_WIN_RATE),
            _safe(h2h.get("avg_goal_diff"), DEFAULT_H2H_AVG_GOAL_DIFF),
        ]
    return vec


def fit(x: np.ndarray, y: np.ndarray) -> dict:
    """Estandariza features antes de ajustar: sin esto, la regularización L2
    de LogisticRegression penaliza de forma desigual features con escalas muy
    distintas (ej. points_per_game ~0-3 vs. goal_difference ~±15), distorsionando
    el ajuste. El scaler se ajusta SOLO con datos de train (nunca con eval) y
    se reutiliza tal cual en predict_proba — evita leakage de la distribución
    del set de evaluación hacia el entrenamiento."""
    scaler = StandardScaler()
    x_scaled = scaler.fit_transform(x)
    model = LogisticRegression(max_iter=1000, C=1.0)
    model.fit(x_scaled, y)
    return {"scaler": scaler, "model": model}


def predict_proba(fitted: dict, x: list[float]) -> tuple[float, float, float]:
    x_scaled = fitted["scaler"].transform([x])
    probs = fitted["model"].predict_proba(x_scaled)[0]
    by_class = dict(zip(fitted["model"].classes_, probs, strict=True))
    return validate_probability_triple(by_class.get(0, 0.0), by_class.get(1, 0.0), by_class.get(2, 0.0))


def serialize_fitted(fitted: dict) -> str:
    """Encontrado en revisión (ADR-0018): registrábamos un ModelVersion para
    cada candidato logístico, pero el scaler/coeficientes ajustados se
    descartaban al terminar el proceso — un "modelo" que no se podía volver a
    cargar para inferencia no es honestamente un model_version reproducible.
    scaler + LogisticRegression son objetos chicos (unos KB); pickle+base64
    alcanza sin necesitar un artifact store dedicado todavía."""
    return base64.b64encode(pickle.dumps({"scaler": fitted["scaler"], "model": fitted["model"]})).decode("ascii")


def deserialize_fitted(blob: str) -> dict:
    return pickle.loads(base64.b64decode(blob))
