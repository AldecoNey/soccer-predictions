"""Model tests (ROADMAP Fase 4): los 3 baselines de ADR-0006 deben producir
siempre probabilidades válidas y reproducibles, sobre datos sintéticos
controlados (no dependen de que haya datos reales cargados en Neon)."""

from datetime import datetime, timedelta, timezone

import pytest

import uuid

from app.prediction_models import elo, naive, poisson_dixon_coles
from app.prediction_models.poisson_dixon_coles import _tau
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

        probs = poisson_dixon_coles.predict_proba(uuid.uuid4(), teams[0].id, params)
        assert probs == (1 / 3, 1 / 3, 1 / 3)


class TestDixonColesTauValidity:
    """Tests adversariales (ADR-0014/0015): tau(x,y) puede volverse negativo
    para combinaciones de lambda/rho matemáticamente posibles dentro de
    nuestros propios bounds (rho en [-0.3, 0.3]) — no alcanza con que el
    dataset sintético "normal" nunca lleve al optimizador ahí por casualidad."""

    def test_tau_can_go_negative_for_valid_bounds(self):
        """Demuestra el bug documentado: lambda_home=lambda_away=2, rho=0.3
        (dentro de nuestros bounds) da tau(0,0) negativo. Si esta aserción
        alguna vez empieza a fallar porque _tau cambió de fórmula, hay que
        revisar que el resto de esta clase siga siendo relevante."""
        assert _tau(0, 0, lambda_x=2.0, lambda_y=2.0, rho=0.3) == pytest.approx(-0.2)

    def test_tau_negative_at_other_low_score_cells_too(self):
        # rho muy negativo también puede tirar tau(0,1)/tau(1,0) por debajo de 0
        assert _tau(0, 1, lambda_x=10.0, lambda_y=1.0, rho=-0.3) < 0
        assert _tau(1, 0, lambda_x=1.0, lambda_y=10.0, rho=-0.3) < 0

    def test_predict_proba_stays_valid_despite_negative_tau_cells(self):
        """El escenario adversarial completo: parámetros que fuerzan tau<0 en
        la grilla, pero predict_proba() debe devolver igual un triplete válido
        (clampeado), nunca una probabilidad negativa cruda."""
        team_a, team_b = str(uuid.uuid4()), str(uuid.uuid4())
        params = {
            "team_ids": [team_a, team_b],
            # attack=[ln(2), ln(2)], defense=[0,0], home_advantage=0
            # -> lambda_home = lambda_away = 2 para cualquier par de equipos
            "attack": [0.6931471805599453, 0.6931471805599453],
            "defense": [0.0, 0.0],
            "home_advantage": 0.0,
            "rho": 0.3,  # el peor caso documentado, dentro de nuestros bounds reales
        }
        probs = poisson_dixon_coles.predict_proba(team_a, team_b, params)
        assert all(0.0 <= p <= 1.0 for p in probs)
        assert sum(probs) == pytest.approx(1.0, abs=1e-6)

    def test_non_convergence_is_reported_honestly(self, db_session):
        """fit() con un dataset degenerado (0 partidos conocidos) no debe
        fingir que convergió — converged=False es la señal real que
        pipelines/train_baselines.py usa para rechazar el candidato en vez
        de registrarlo igual."""
        params = poisson_dixon_coles.fit(db_session, BASE_TIME)  # antes de que exista cualquier partido
        assert params["converged"] is False
        assert params["n_matches"] == 0
