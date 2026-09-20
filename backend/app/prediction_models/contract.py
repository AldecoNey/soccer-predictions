"""Contrato mínimo que todo predict_proba() debe cumplir (ADR-0014): no
confiar en que cada modelo lo garantice por su cuenta — se valida en un
solo lugar."""

import math

TOLERANCE = 1e-6


def validate_probability_triple(p_home: float, p_draw: float, p_away: float) -> tuple[float, float, float]:
    probs = (p_home, p_draw, p_away)
    if not all(math.isfinite(p) for p in probs):
        raise ValueError(f"Probabilidades no finitas: {probs}")
    if any(p < -TOLERANCE for p in probs):
        raise ValueError(f"Probabilidad negativa: {probs}")
    total = sum(probs)
    if abs(total - 1.0) > 1e-3:
        raise ValueError(f"Probabilidades no suman 1 (suma={total}): {probs}")
    # tolera negativos numéricos ínfimos (ej. -1e-12 por redondeo de punto
    # flotante) clampeando a 0 después de validar, nunca antes
    return tuple(max(p, 0.0) for p in probs)
