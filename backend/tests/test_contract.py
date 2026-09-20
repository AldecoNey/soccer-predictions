import pytest

from app.prediction_models.contract import validate_probability_triple


def test_valid_triple_passes_through():
    assert validate_probability_triple(0.5, 0.3, 0.2) == (0.5, 0.3, 0.2)


def test_tiny_negative_rounding_error_is_clamped():
    """Bug real encontrado en revisión: la versión anterior de este test no
    pasaba ningún valor negativo (0.5000000000001 no es negativo) — parecía
    probar el clamp sin ejercitarlo. -1e-12 sí es negativo de verdad, pero
    por debajo de TOLERANCE (1e-6): debe clampearse a 0, no rechazarse."""
    result = validate_probability_triple(0.5, 0.5, -1e-12)
    assert result == (0.5, 0.5, 0.0)
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
