"""Tests de app/evaluation.py (métricas) con ejemplos calculados a mano,
y de pipelines/evaluate_baselines.py (aislamiento temporal de los folds —
criterio explícito de la Fase 5: "verificación de que la validación es
estrictamente temporal")."""

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app.evaluation import accuracy, brier_score, expected_calibration_error, log_loss
from app.models import Competition, Match, Result, Season, Team
from pipelines.evaluate_baselines import get_folds, get_season_matches

BASE_TIME = datetime(2020, 1, 1, tzinfo=timezone.utc)


def test_log_loss_perfect_predictions_near_zero():
    y_true = np.array([0, 1, 2])
    y_pred = np.array([[0.999, 0.0005, 0.0005], [0.0005, 0.999, 0.0005], [0.0005, 0.0005, 0.999]])
    assert log_loss(y_true, y_pred) < 0.01


def test_log_loss_uniform_guess_equals_ln3():
    y_true = np.array([0, 1, 2, 0])
    y_pred = np.full((4, 3), 1 / 3)
    assert log_loss(y_true, y_pred) == pytest.approx(np.log(3), abs=1e-6)


def test_brier_score_perfect_is_zero():
    y_true = np.array([0])
    y_pred = np.array([[1.0, 0.0, 0.0]])
    assert brier_score(y_true, y_pred) == pytest.approx(0.0)


def test_brier_score_worst_case():
    y_true = np.array([0])
    y_pred = np.array([[0.0, 0.0, 1.0]])
    # (0-1)^2 + (0-0)^2 + (1-0)^2 = 2.0
    assert brier_score(y_true, y_pred) == pytest.approx(2.0)


def test_accuracy_counts_argmax_matches():
    y_true = np.array([0, 1, 2, 0])
    y_pred = np.array([[0.6, 0.3, 0.1], [0.3, 0.6, 0.1], [0.1, 0.3, 0.6], [0.1, 0.6, 0.3]])
    assert accuracy(y_true, y_pred) == 0.75


def test_ece_zero_when_confidence_matches_accuracy_exactly():
    # 10 predicciones con confianza 0.7, de las cuales exactamente 7 son correctas
    y_pred = np.tile([0.7, 0.2, 0.1], (10, 1))
    y_true = np.array([0] * 7 + [1] * 3)
    assert expected_calibration_error(y_true, y_pred, n_bins=10) == pytest.approx(0.0, abs=1e-9)


def test_ece_positive_when_overconfident():
    # confianza 0.9 pero solo 50% de aciertos -> mal calibrado
    y_pred = np.tile([0.9, 0.05, 0.05], (10, 1))
    y_true = np.array([0] * 5 + [1] * 5)
    ece = expected_calibration_error(y_true, y_pred, n_bins=10)
    assert ece == pytest.approx(0.4, abs=1e-9)


def _seed_two_seasons(session):
    competition = Competition(name="Liga de prueba")
    session.add(competition)
    session.flush()
    season_a = Season(competition_id=competition.id, year_label="2022", start_date=BASE_TIME, end_date=BASE_TIME + timedelta(days=90))
    season_b = Season(
        competition_id=competition.id,
        year_label="2023",
        start_date=BASE_TIME + timedelta(days=200),
        end_date=BASE_TIME + timedelta(days=290),
    )
    session.add_all([season_a, season_b])
    session.flush()

    home, away = Team(name="A"), Team(name="B")
    session.add_all([home, away])
    session.flush()

    match_a = Match(season_id=season_a.id, home_team_id=home.id, away_team_id=away.id, kickoff_at=BASE_TIME + timedelta(days=10), status="finished")
    match_b = Match(season_id=season_b.id, home_team_id=home.id, away_team_id=away.id, kickoff_at=BASE_TIME + timedelta(days=210), status="finished")
    session.add_all([match_a, match_b])
    session.flush()
    session.add(Result(match_id=match_a.id, home_score=1, away_score=0, outcome="home"))
    session.add(Result(match_id=match_b.id, home_score=2, away_score=2, outcome="draw"))
    session.commit()
    return competition, season_a, season_b


def test_get_folds_builds_expanding_windows(db_session):
    competition, season_a, season_b = _seed_two_seasons(db_session)
    folds = get_folds(db_session, competition.id)
    assert len(folds) == 1
    assert folds[0]["train_years"] == ["2022"]
    assert folds[0]["eval_season"].year_label == "2023"


def test_get_season_matches_isolated_by_season(db_session):
    _, season_a, season_b = _seed_two_seasons(db_session)
    matches_a = get_season_matches(db_session, season_a)
    matches_b = get_season_matches(db_session, season_b)
    assert len(matches_a) == 1
    assert len(matches_b) == 1
    assert matches_a[0].kickoff_at < season_b.start_date  # fold de 2022 nunca ve datos de 2023
