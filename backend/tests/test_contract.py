import pytest

from app.prediction_models.contract import validate_probability_triple


def test_valid_triple_passes_through():
    assert validate_probability_triple(0.5, 0.3, 0.2) == (0.5, 0.3, 0.2)


def test_tiny_negative_rounding_error_is_clamped():
    # -1e-12 es ruido de punto flotante, no un error real
    result = validate_probability_triple(0.5000000000001, 0.3, 0.1999999999999)
    assert all(p >= 0.0 for p in result)


def test_rejects_real_negative_probability():
    with pytest.raises(ValueError, match="negativa"):
        validate_probability_triple(1.2, -0.2, 0.0)


def test_rejects_non_finite():
    with pytest.raises(ValueError, match="no finitas"):
        validate_probability_triple(float("nan"), 0.5, 0.5)


def test_rejects_sum_not_one():
    with pytest.raises(ValueError, match="no suman 1"):
        validate_probability_triple(0.5, 0.5, 0.5)
