"""Data tests para el esquema del Football Intelligence Agent
(data_sources/player_availability/news_signals): verifican que el
constraint anti-leakage `available_at >= observed_at` está realmente
aplicado a nivel BD, no solo documentado — mismo patrón que
test_schema_constraints.py para Result.outcome (ADR-0015). Corren contra
Neon dentro de una transacción que siempre se revierte (ver
conftest.db_session).
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Competition, DataSource, Match, NewsSignal, PlayerAvailability, Player, Season, Team


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


def _make_source(session):
    source = DataSource(
        name="Boca Juniors - sitio oficial",
        reliability_level="A",
        source_type="official_club",
    )
    session.add(source)
    session.flush()
    return source


def test_data_source_happy_path_and_unique_name(db_session):
    source = _make_source(db_session)
    assert source.id is not None

    dup = DataSource(name=source.name, reliability_level="B", source_type="aggregator")
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_player_availability_happy_path(db_session):
    home, _ = _make_teams(db_session)
    source = _make_source(db_session)
    player = Player(name="Jugador de Prueba")
    db_session.add(player)
    db_session.flush()

    now = datetime.now(timezone.utc)
    availability = PlayerAvailability(
        player_id=player.id,
        team_id=home.id,
        status="doubtful",
        reason="muscle_injury",
        confidence="A",
        source_id=source.id,
        observed_at=now,
        available_at=now,
        raw_fact={"player": player.name, "status": "doubtful"},
    )
    db_session.add(availability)
    db_session.flush()

    assert availability.id is not None


def test_player_availability_rejects_available_at_before_observed_at(db_session):
    """Regla P0 de anti-leakage (.claude/agents/football-intelligence.md):
    available_at nunca puede ser anterior a observed_at — un artículo
    publicado antes de que lo encontráramos no puede retroactivamente
    "estar disponible" antes de que lo hayamos observado."""
    home, _ = _make_teams(db_session)
    source = _make_source(db_session)
    player = Player(name="Jugador de Prueba 2")
    db_session.add(player)
    db_session.flush()

    now = datetime.now(timezone.utc)
    availability = PlayerAvailability(
        player_id=player.id,
        team_id=home.id,
        status="unavailable",
        confidence="A",
        source_id=source.id,
        observed_at=now,
        available_at=now - timedelta(hours=4),  # anterior a observed_at: inválido
        raw_fact={"player": player.name, "status": "unavailable"},
    )
    db_session.add(availability)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_news_signal_happy_path(db_session):
    _, season = _make_competition_season(db_session)
    home, away = _make_teams(db_session)
    source = _make_source(db_session)
    match = Match(
        season_id=season.id,
        home_team_id=home.id,
        away_team_id=away.id,
        kickoff_at=datetime.now(timezone.utc) + timedelta(days=2),
    )
    db_session.add(match)
    db_session.flush()

    now = datetime.now(timezone.utc)
    signal = NewsSignal(
        team_id=home.id,
        match_id=match.id,
        signal_type="coaching_change",
        description="Cambio de entrenador confirmado por el club.",
        source_id=source.id,
        observed_at=now,
        available_at=now,
        raw_fact={"headline": "Cambio de DT"},
    )
    db_session.add(signal)
    db_session.flush()

    assert signal.id is not None


def test_news_signal_rejects_available_at_before_observed_at(db_session):
    source = _make_source(db_session)
    now = datetime.now(timezone.utc)
    signal = NewsSignal(
        signal_type="other",
        description="Señal con timestamps inválidos.",
        source_id=source.id,
        observed_at=now,
        available_at=now - timedelta(minutes=1),
        raw_fact={"headline": "invalido"},
    )
    db_session.add(signal)
    with pytest.raises(IntegrityError):
        db_session.flush()
