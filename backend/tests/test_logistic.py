"""Tests del candidato 3 (ADR-0006): regresión logística. Sobre todo,
verifica lo que el docstring de fit() PROMETE pero no tenía ningún test que
lo garantizara (encontrado en revisión, ADR-0015): el StandardScaler se
ajusta solo con train, nunca ve datos de eval."""

import numpy as np
from sklearn.preprocessing import StandardScaler

from app.prediction_models import logistic


def _base_features():
    return {
        "home": {"points_per_game": 1.5, "goal_difference": 3, "rest_days": 6},
        "away": {"points_per_game": 1.0, "goal_difference": -2, "rest_days": 4},
    }


def test_vectorize_with_h2h_appends_two_values():
    features = _base_features()
    h2h = {"matches_played": 4, "home_win_rate": 0.75, "draw_rate": 0.25, "avg_goal_diff": 1.5}

    vec = logistic.vectorize(features, h2h=h2h)

    assert len(vec) == len(logistic.FEATURE_NAMES_WITH_H2H) == len(logistic.FEATURE_NAMES) + 2
    assert vec[-2:] == [0.75, 1.5]


def test_vectorize_without_h2h_matches_base_feature_count():
    features = _base_features()
    vec = logistic.vectorize(features)
    assert len(vec) == len(logistic.FEATURE_NAMES)


def test_vectorize_h2h_neutral_defaults_when_no_prior_meetings():
    """Sin encuentros previos, head_to_head_features devuelve None — vectorize
    debe usar defaults neutros (1/3, no 0.0, para home_win_rate; 0.0 para
    avg_goal_diff), no crashear ni tratar "sin evidencia" como "siempre pierde"."""
    features = _base_features()
    h2h = {"matches_played": 0, "home_win_rate": None, "draw_rate": None, "avg_goal_diff": None}

    vec = logistic.vectorize(features, h2h=h2h)

    assert vec[-2] == logistic.DEFAULT_H2H_HOME_WIN_RATE == 1.0 / 3.0
    assert vec[-1] == logistic.DEFAULT_H2H_AVG_GOAL_DIFF == 0.0


def test_scaler_is_fit_only_on_training_data():
    x_train = np.array([[0.0, 1.0], [2.0, 3.0], [4.0, 5.0], [6.0, 7.0]])
    y_train = np.array([0, 1, 2, 0])
    # datos de "eval" con una distribución bien distinta — si el scaler los
    # viera de algún modo, su mean_/scale_ no coincidirían con los de un
    # StandardScaler ajustado exclusivamente sobre x_train.
    x_eval_like_if_leaked = np.array([[1000.0, 2000.0], [3000.0, 4000.0]])

    fitted = logistic.fit(x_train, y_train)

    reference_scaler = StandardScaler().fit(x_train)
    assert np.allclose(fitted["scaler"].mean_, reference_scaler.mean_)
    assert np.allclose(fitted["scaler"].scale_, reference_scaler.scale_)
    # ninguna de las dos cosas debería acercarse a la escala de "eval"
    assert fitted["scaler"].mean_.max() < 100
    del x_eval_like_if_leaked  # documenta la intención, no se usa para fittear nada


def test_predict_proba_valid_triple():
    x = np.array([[0.0, 1.0], [2.0, 3.0], [4.0, 5.0], [6.0, 7.0], [1.0, 2.0], [3.0, 4.0]])
    y = np.array([0, 1, 2, 0, 1, 2])
    fitted = logistic.fit(x, y)

    probs = logistic.predict_proba(fitted, [1.0, 1.5])
    assert all(0.0 <= p <= 1.0 for p in probs)
    assert sum(probs) == 1.0 or abs(sum(probs) - 1.0) < 1e-6


def test_serialize_deserialize_roundtrip_gives_identical_predictions():
    """ADR-0018: un ModelVersion de regresión logística debe ser realmente
    cargable para inferencia después, no solo metadata descriptiva."""
    x = np.array([[0.0, 1.0], [2.0, 3.0], [4.0, 5.0], [6.0, 7.0], [1.0, 2.0], [3.0, 4.0]])
    y = np.array([0, 1, 2, 0, 1, 2])
    fitted = logistic.fit(x, y)

    blob = logistic.serialize_fitted(fitted)
    restored = logistic.deserialize_fitted(blob)

    row = [1.0, 1.5]
    assert logistic.predict_proba(fitted, row) == logistic.predict_proba(restored, row)


def test_missing_class_in_training_fold_still_sums_to_one():
    """Si un fold de train nunca tuvo empates, model.classes_ no incluye la
    clase 1 — vectorize()/predict_proba() deben seguir devolviendo un
    triplete válido (0 para la clase ausente), no romper."""
    x = np.array([[0.0, 1.0], [2.0, 3.0], [4.0, 5.0], [1.0, 1.0]])
    y = np.array([0, 2, 0, 2])  # sin ningún 1 (draw)
    fitted = logistic.fit(x, y)

    probs = logistic.predict_proba(fitted, [1.0, 1.5])
    assert probs[1] == 0.0
    assert abs(sum(probs) - 1.0) < 1e-6
