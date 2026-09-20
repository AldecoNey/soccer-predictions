"""Data tests (ROADMAP Fase 2): verifican que el esquema real en Postgres
rechaza estados imposibles. Corren contra Neon dentro de una transacción que
siempre se revierte (ver conftest.db_session) — nunca dejan datos de prueba.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Competition, Match, Result, Season, Team


def _make_competition_season(session):
    competition = Competition(name="Liga Profesional Argentina", country="Argentina")
    session.add(competition)
    session.flush()
    season = Season(competition_id=competition.id, year_label="2026")
    session.add(season)
    session.flush()
    return competition, season


def _make_teams(session):
    home = Team(name="San Lorenzo")
    away = Team(name="Boca Juniors")
    session.add_all([home, away])
    session.flush()
    return home, away


def test_happy_path_creates_match_and_result(db_session):
    _, season = _make_competition_season(db_session)
    home, away = _make_teams(db_session)
    match = Match(
        season_id=season.id,
        home_team_id=home.id,
        away_team_id=away.id,
        kickoff_at=datetime.now(timezone.utc) - timedelta(days=3),
        # status="finished" explícito: un Result sobre un partido
        # "scheduled" (el default) sería un estado imposible que el schema
        # no bloquea a nivel BD (encontrado en revisión, ADR-0015) — el
        # happy path debe modelar un caso real, no uno inconsistente.
        status="finished",
    )
    db_session.add(match)
    db_session.flush()

    result = Result(match_id=match.id, home_score=2, away_score=1, outcome="home")
    db_session.add(result)
    db_session.flush()

    assert match.id is not None
    assert result.id is not None


def test_result_rejects_score_outcome_mismatch(db_session):
    """home_score=3, away_score=0, outcome='draw' — un estado imposible que
    antes ningún constraint bloqueaba (ADR-0015)."""
    _, season = _make_competition_season(db_session)
    home, away = _make_teams(db_session)
    match = Match(
        season_id=season.id, home_team_id=home.id, away_team_id=away.id, kickoff_at=datetime.now(timezone.utc), status="finished"
    )
    db_session.add(match)
    db_session.flush()

    db_session.add(Result(match_id=match.id, home_score=3, away_score=0, outcome="draw"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_match_rejects_same_team_home_and_away(db_session):
    _, season = _make_competition_season(db_session)
    home, _ = _make_teams(db_session)
    match = Match(
        season_id=season.id,
        home_team_id=home.id,
        away_team_id=home.id,
        kickoff_at=datetime.now(timezone.utc),
    )
    db_session.add(match)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_result_rejects_negative_score(db_session):
    _, season = _make_competition_season(db_session)
    home, away = _make_teams(db_session)
    match = Match(season_id=season.id, home_team_id=home.id, away_team_id=away.id, kickoff_at=datetime.now(timezone.utc))
    db_session.add(match)
    db_session.flush()

    db_session.add(Result(match_id=match.id, home_score=-1, away_score=0, outcome="away"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_result_rejects_invalid_outcome(db_session):
    _, season = _make_competition_season(db_session)
    home, away = _make_teams(db_session)
    match = Match(season_id=season.id, home_team_id=home.id, away_team_id=away.id, kickoff_at=datetime.now(timezone.utc))
    db_session.add(match)
    db_session.flush()

    db_session.add(Result(match_id=match.id, home_score=1, away_score=1, outcome="tie"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_result_is_unique_per_match(db_session):
    _, season = _make_competition_season(db_session)
    home, away = _make_teams(db_session)
    match = Match(season_id=season.id, home_team_id=home.id, away_team_id=away.id, kickoff_at=datetime.now(timezone.utc))
    db_session.add(match)
    db_session.flush()

    db_session.add(Result(match_id=match.id, home_score=1, away_score=0, outcome="home"))
    db_session.flush()
    db_session.add(Result(match_id=match.id, home_score=2, away_score=2, outcome="draw"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_season_year_label_unique_per_competition(db_session):
    competition, _ = _make_competition_season(db_session)
    db_session.add(Season(competition_id=competition.id, year_label="2026"))
    with pytest.raises(IntegrityError):
        db_session.flush()
