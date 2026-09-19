"""Model tests (ROADMAP Fase 4): los 3 baselines de ADR-0006 deben producir
siempre probabilidades válidas y reproducibles, sobre datos sintéticos
controlados (no dependen de que haya datos reales cargados en Neon)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.prediction_models import elo, naive, poisson_dixon_coles
from app.models import Competition, Match, Result, Season, Team

BASE_TIME = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _seed_league(session, n_teams=6, n_rounds=4):
    competition = Competition(name="Liga de prueba")
    session.add(competition)
    session.flush()
    season = Season(competition_id=competition.id, year_label="2020")
    session.add(season)
    session.flush()

    teams = [Team(name=f"Equipo {i}") for i in range(n_teams)]
    session.add_all(teams)
    session.flush()

    day = 0
    for _round in range(n_rounds):
        for i in range(0, n_teams, 2):
            home, away = teams[i], teams[i + 1]
            kickoff = BASE_TIME + timedelta(days=day)
            day += 7
            match = Match(season_id=season.id, home_team_id=home.id, away_team_id=away.id, kickoff_at=kickoff, status="finished")
            session.add(match)
            session.flush()
            # resultado determinístico simple: el equipo de índice más bajo gana más seguido
            home_goals, away_goals = (2, 0) if i % 3 != 0 else (1, 1)
            session.add(Result(match_id=match.id, home_score=home_goals, away_score=away_goals, outcome="home" if home_goals > away_goals else "draw"))
    session.commit()
    return teams, BASE_TIME + timedelta(days=day + 10)


def _assert_valid_probability_triple(probs):
    assert all(0.0 <= p <= 1.0 for p in probs), probs
    assert abs(sum(probs) - 1.0) < 1e-6, probs


class TestNaive:
    def test_probabilities_valid_and_sum_to_one(self, db_session):
        _seed_league(db_session)
        as_of = BASE_TIME + timedelta(days=100)
        params = naive.fit(db_session, as_of)
        _assert_valid_probability_triple(naive.predict_proba(params))

    def test_reproducible(self, db_session):
        _seed_league(db_session)
        as_of = BASE_TIME + timedelta(days=100)
        assert naive.fit(db_session, as_of) == naive.fit(db_session, as_of)

    def test_empty_history_returns_uniform(self, db_session):
        as_of = BASE_TIME
        params = naive.fit(db_session, as_of)
        assert params["n_matches"] == 0
        _assert_valid_probability_triple(naive.predict_proba(params))


class TestElo:
    def test_probabilities_valid_and_sum_to_one(self, db_session):
        teams, as_of = _seed_league(db_session)
        params = elo.fit(db_session, as_of)
        for i in range(0, len(teams), 2):
            probs = elo.predict_proba(teams[i].id, teams[i + 1].id, params)
            _assert_valid_probability_triple(probs)

    def test_reproducible(self, db_session):
        teams, as_of = _seed_league(db_session)
        p1 = elo.fit(db_session, as_of)
        p2 = elo.fit(db_session, as_of)
        assert p1 == p2

    def test_unknown_team_uses_initial_rating(self, db_session):
        teams, as_of = _seed_league(db_session)
        params = elo.fit(db_session, as_of)
        import uuid

        probs = elo.predict_proba(uuid.uuid4(), teams[0].id, params)
        _assert_valid_probability_triple(probs)


class TestPoissonDixonColes:
    def test_probabilities_valid_and_sum_to_one(self, db_session):
        teams, as_of = _seed_league(db_session)
        params = poisson_dixon_coles.fit(db_session, as_of)
        for i in range(0, len(teams), 2):
            probs = poisson_dixon_coles.predict_proba(teams[i].id, teams[i + 1].id, params)
            _assert_valid_probability_triple(probs)

    def test_reproducible(self, db_session):
        teams, as_of = _seed_league(db_session)
        p1 = poisson_dixon_coles.fit(db_session, as_of)
        p2 = poisson_dixon_coles.fit(db_session, as_of)
        assert p1["attack"] == p2["attack"]
        assert p1["defense"] == p2["defense"]
        assert p1["home_advantage"] == pytest.approx(p2["home_advantage"])

    def test_unknown_team_returns_uniform_fallback(self, db_session):
        teams, as_of = _seed_league(db_session)
        params = poisson_dixon_coles.fit(db_session, as_of)
        import uuid

        probs = poisson_dixon_coles.predict_proba(uuid.uuid4(), teams[0].id, params)
        assert probs == (1 / 3, 1 / 3, 1 / 3)
