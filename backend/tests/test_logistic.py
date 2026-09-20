"""Tests del candidato 3 (ADR-0006): regresión logística. Sobre todo,
verifica lo que el docstring de fit() PROMETE pero no tenía ningún test que
lo garantizara (encontrado en revisión, ADR-0015): el StandardScaler se
ajusta solo con train, nunca ve datos de eval."""

import numpy as np
from sklearn.preprocessing import StandardScaler

from app.prediction_models import logistic


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
