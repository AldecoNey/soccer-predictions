"""Métricas de evaluación probabilística (ADR-0007). Log Loss es la métrica
principal; accuracy es secundaria e informativa, nunca criterio de
promoción por sí sola.

Todas las funciones toman `y_true` como índices de clase (0=home, 1=draw,
2=away) y `y_pred` como arrays de forma (n_samples, 3) que suman 1 por fila.
"""

import numpy as np

EPS = 1e-15


def log_loss(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    probs = np.clip(y_pred, EPS, 1 - EPS)
    true_class_probs = probs[np.arange(len(y_true)), y_true]
    return float(-np.mean(np.log(true_class_probs)))


def brier_score(y_true: np.ndarray, y_pred: np.ndarray, n_classes: int = 3) -> float:
    one_hot = np.eye(n_classes)[y_true]
    return float(np.mean(np.sum((y_pred - one_hot) ** 2, axis=1)))


def accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    predicted_class = np.argmax(y_pred, axis=1)
    return float(np.mean(predicted_class == y_true))


def expected_calibration_error(y_true: np.ndarray, y_pred: np.ndarray, n_bins: int = 10) -> float:
    """ECE clásico: para la clase predicha (máxima probabilidad), compara
    confianza promedio vs. accuracy real dentro de cada bin de confianza."""
    predicted_class = np.argmax(y_pred, axis=1)
    confidences = np.max(y_pred, axis=1)
    correct = (predicted_class == y_true).astype(float)

    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = len(y_true)
    for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
        in_bin = (confidences > lo) & (confidences <= hi)
        if not np.any(in_bin):
            continue
        bin_confidence = confidences[in_bin].mean()
        bin_accuracy = correct[in_bin].mean()
        ece += (in_bin.sum() / n) * abs(bin_confidence - bin_accuracy)
    return float(ece)


def compute_all_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    return {
        "log_loss": log_loss(y_true, y_pred),
        "brier_score": brier_score(y_true, y_pred),
        "accuracy": accuracy(y_true, y_pred),
        "ece": expected_calibration_error(y_true, y_pred),
        "n_samples": int(len(y_true)),
    }
