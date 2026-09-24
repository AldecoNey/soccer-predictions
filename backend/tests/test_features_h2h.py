"""Tests de head_to_head_features (ADR-0022, Fase 6): a diferencia de
rotation_index (ADR-0011), esta señal no tiene problema de oráculo — solo
usa encuentros pasados entre los dos equipos, así que el checklist
anti-leakage de ADR-0007 aplica igual que a build_features().
"""

from datetime import datetime, timedelta, timezone

from app.features import RESULT_KNOWN_BUFFER
from app.features_h2h import head_to_head_features
from app.models import Competition, Match, Result, Season, Team


def _setup(session, base_time=None):
    base_time = base_time or datetime(2026, 1, 1, tzinfo=timezone.utc)
    competition = Competition(name="Liga Profesional Argentina", country="Argentina")
    session.add(competition)
    session.flush()
    season = Season(competition_id=competition.id, year_label="2026")
    session.add(season)
    session.flush()

    home = Team(name="San Lorenzo")
    away = Team(name="Boca Juniors")
    other = Team(name="River Plate")
    session.add_all([home, away, other])
    session.flush()

    target_kickoff = base_time + timedelta(days=100)
    target_match = Match(
        season_id=season.id, home_team_id=home.id, away_team_id=away.id, kickoff_at=target_kickoff
    )
    session.add(target_match)
    session.flush()

    return target_match, home, away, other, season, base_time


def test_no_prior_meetings_returns_neutral_defaults(db_session):
    target_match, home, away, _, _, base_time = _setup(db_session)
    as_of = target_match.kickoff_at - timedelta(days=1)

    features = head_to_head_features(db_session, target_match.id, home.id, away.id, as_of)

    assert features["matches_played"] == 0
    assert features["home_win_rate"] is None
    assert features["draw_rate"] is None
    assert features["avg_goal_diff"] is None


def test_known_prior_meeting_computes_rates_from_current_home_perspective(db_session):
    target_match, home, away, _, season, base_time = _setup(db_session)
    as_of = target_match.kickoff_at - timedelta(days=1)

    # Encuentro 1: home (hoy local) jugó de VISITANTE la vez pasada y ganó 3-1.
    meeting_1 = Match(
        season_id=season.id,
        home_team_id=away.id,
        away_team_id=home.id,
        kickoff_at=base_time,
        status="finished",
    )
    # Encuentro 2: home jugó de LOCAL y empataron 1-1.
    meeting_2 = Match(
        season_id=season.id,
        home_team_id=home.id,
        away_team_id=away.id,
        kickoff_at=base_time + timedelta(days=30),
        status="finished",
    )
    db_session.add_all([meeting_1, meeting_2])
    db_session.flush()
    db_session.add(Result(match_id=meeting_1.id, home_score=1, away_score=3, outcome="away"))  # home (visitante) ganó 3-1
    db_session.add(Result(match_id=meeting_2.id, home_score=1, away_score=1, outcome="draw"))
    db_session.flush()

    features = head_to_head_features(db_session, target_match.id, home.id, away.id, as_of)

    assert features["matches_played"] == 2
    assert features["home_win_rate"] == 0.5  # 1 de 2
    assert features["draw_rate"] == 0.5  # 1 de 2
    # goal_diff desde la perspectiva de home: (+2 en el encuentro 1) + (0 en el encuentro 2) = 2, promedio 1.0
    assert features["avg_goal_diff"] == 1.0


def test_excludes_target_match_itself(db_session):
    target_match, home, away, _, _, base_time = _setup(db_session)
    as_of = target_match.kickoff_at + timedelta(hours=5)
    db_session.add(Result(match_id=target_match.id, home_score=3, away_score=1, outcome="home"))
    db_session.flush()

    features = head_to_head_features(db_session, target_match.id, home.id, away.id, as_of)
    assert features["matches_played"] == 0


def test_result_known_buffer_boundary(db_session):
    target_match, home, away, _, season, base_time = _setup(db_session)
    as_of = base_time + timedelta(days=50)

    # Encuentro cuyo kickoff_at cae justo en el borde del buffer: debe CONTAR.
    on_boundary = Match(
        season_id=season.id,
        home_team_id=home.id,
        away_team_id=away.id,
        kickoff_at=as_of - RESULT_KNOWN_BUFFER,
        status="finished",
    )
    # Encuentro cuyo kickoff_at cae 1 minuto después del borde: NO debe contar todavía.
    past_boundary = Match(
        season_id=season.id,
        home_team_id=home.id,
        away_team_id=away.id,
        kickoff_at=as_of - RESULT_KNOWN_BUFFER + timedelta(minutes=1),
        status="finished",
    )
    db_session.add_all([on_boundary, past_boundary])
    db_session.flush()
    db_session.add(Result(match_id=on_boundary.id, home_score=1, away_score=0, outcome="home"))
    db_session.add(Result(match_id=past_boundary.id, home_score=5, away_score=0, outcome="home"))
    db_session.flush()

    features = head_to_head_features(db_session, target_match.id, home.id, away.id, as_of)
    assert features["matches_played"] == 1
    assert features["avg_goal_diff"] == 1.0  # el de 5 goles todavía no "existe" para as_of


def test_meeting_counts_regardless_of_historical_side(db_session):
    """Un cruce cuenta sin importar de qué lado jugó cada equipo esa vez —
    ver docstring de _past_meetings."""
    target_match, home, away, _, season, base_time = _setup(db_session)
    as_of = target_match.kickoff_at - timedelta(days=1)

    meeting = Match(
        season_id=season.id,
        home_team_id=away.id,  # away (hoy visitante) fue local esa vez
        away_team_id=home.id,
        kickoff_at=base_time,
        status="finished",
    )
    db_session.add(meeting)
    db_session.flush()
    db_session.add(Result(match_id=meeting.id, home_score=2, away_score=2, outcome="draw"))
    db_session.flush()

    features = head_to_head_features(db_session, target_match.id, home.id, away.id, as_of)
    assert features["matches_played"] == 1
