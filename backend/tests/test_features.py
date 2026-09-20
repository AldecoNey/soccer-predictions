"""Model tests (ROADMAP Fase 3): el checklist anti-leakage de ADR-0007
convertido en tests automáticos. Si alguno de estos falla, no se puede
entrenar ni evaluar ningún modelo (ver .claude/agents/qa-data-integrity.md).
"""

from datetime import datetime, timedelta, timezone

from app.features import RESULT_KNOWN_BUFFER, build_features
from app.models import Competition, Match, Result, Season, Team


def _setup(session, n_past_matches=0, base_time=None):
    base_time = base_time or datetime(2026, 1, 1, tzinfo=timezone.utc)
    competition = Competition(name="Liga Profesional Argentina", country="Argentina")
    session.add(competition)
    session.flush()
    season = Season(competition_id=competition.id, year_label="2026")
    session.add(season)
    session.flush()

    home = Team(name="San Lorenzo")
    away = Team(name="Boca Juniors")
    opponent = Team(name="River Plate")
    session.add_all([home, away, opponent])
    session.flush()

    target_kickoff = base_time + timedelta(days=100)
    target_match = Match(
        season_id=season.id, home_team_id=home.id, away_team_id=away.id, kickoff_at=target_kickoff
    )
    session.add(target_match)
    session.flush()

    for i in range(n_past_matches):
        past_kickoff = base_time + timedelta(days=i * 7)
        past_match = Match(
            season_id=season.id,
            home_team_id=home.id,
            away_team_id=opponent.id,
            kickoff_at=past_kickoff,
            status="finished",
        )
        session.add(past_match)
        session.flush()
        session.add(Result(match_id=past_match.id, home_score=2, away_score=0, outcome="home"))
        session.flush()

    return target_match, home, away, opponent, base_time


def test_excludes_matches_after_as_of(db_session):
    target_match, home, _, opponent, base_time = _setup(db_session, n_past_matches=1)
    as_of = target_match.kickoff_at - timedelta(days=1)

    future_match = Match(
        season_id=target_match.season_id,
        home_team_id=home.id,
        away_team_id=opponent.id,
        kickoff_at=as_of + timedelta(hours=1),  # después de as_of
        status="finished",
    )
    db_session.add(future_match)
    db_session.flush()
    db_session.add(Result(match_id=future_match.id, home_score=99, away_score=0, outcome="home"))
    db_session.flush()

    features = build_features(db_session, target_match.id, as_of)
    assert features["home"]["matches_played"] == 1  # solo el partido pasado, no el "futuro"
    assert features["home"]["goals_for"] == 2  # no 101 (2 + 99 si hubiera leakeado)


def test_result_known_buffer_boundary(db_session):
    target_match, home, _, opponent, base_time = _setup(db_session, n_past_matches=0)
    as_of = base_time + timedelta(days=50)

    # Partido que terminó justo en el borde del buffer: debe CONTAR.
    on_boundary = Match(
        season_id=target_match.season_id,
        home_team_id=home.id,
        away_team_id=opponent.id,
        kickoff_at=as_of - RESULT_KNOWN_BUFFER,
        status="finished",
    )
    # Partido que terminó 1 minuto después del borde: NO debe contar todavía.
    past_boundary = Match(
        season_id=target_match.season_id,
        home_team_id=home.id,
        away_team_id=opponent.id,
        kickoff_at=as_of - RESULT_KNOWN_BUFFER + timedelta(minutes=1),
        status="finished",
    )
    db_session.add_all([on_boundary, past_boundary])
    db_session.flush()
    db_session.add(Result(match_id=on_boundary.id, home_score=1, away_score=0, outcome="home"))
    db_session.add(Result(match_id=past_boundary.id, home_score=5, away_score=0, outcome="home"))
    db_session.flush()

    features = build_features(db_session, target_match.id, as_of)
    assert features["home"]["matches_played"] == 1
    assert features["home"]["goals_for"] == 1  # el de 5 goles todavía no "existe" para as_of


def test_excludes_target_match_itself(db_session):
    target_match, home, away, _, base_time = _setup(db_session, n_past_matches=0)
    # as_of posterior al propio kickoff (caso patológico defensivo)
    as_of = target_match.kickoff_at + timedelta(hours=5)
    db_session.add(Result(match_id=target_match.id, home_score=3, away_score=1, outcome="home"))
    db_session.flush()

    features = build_features(db_session, target_match.id, as_of)
    assert features["home"]["matches_played"] == 0
    assert features["away"]["matches_played"] == 0


def test_reproducibility(db_session):
    target_match, _, _, _, base_time = _setup(db_session, n_past_matches=5)
    as_of = target_match.kickoff_at - timedelta(days=1)

    first = build_features(db_session, target_match.id, as_of)
    second = build_features(db_session, target_match.id, as_of)
    assert first == second


def test_window_limits_history_size(db_session):
    target_match, _, _, _, base_time = _setup(db_session, n_past_matches=8)
    as_of = target_match.kickoff_at - timedelta(days=1)

    features = build_features(db_session, target_match.id, as_of, window=3)
    assert features["home"]["matches_played"] == 3


def test_rest_days_is_gap_to_target_kickoff_not_to_snapshot(db_session):
    """rest_days debe medir el descanso HASTA el partido que se predice, no
    hasta el momento en que se genera el snapshot — bug real encontrado en
    revisión de Fase 6 (mismo partido, distinto horizonte, daba distinto
    "descanso" sin que hubiera ocurrido ningún partido nuevo)."""
    target_match, home, _, opponent, base_time = _setup(db_session, n_past_matches=0)
    # target_match.kickoff_at = base_time + 100 días (ver _setup)
    last_known_kickoff = base_time + timedelta(days=100 - 8)  # 8 días antes del kickoff objetivo

    match = Match(
        season_id=target_match.season_id,
        home_team_id=home.id,
        away_team_id=opponent.id,
        kickoff_at=last_known_kickoff,
        status="finished",
    )
    db_session.add(match)
    db_session.flush()
    db_session.add(Result(match_id=match.id, home_score=1, away_score=1, outcome="draw"))
    db_session.flush()

    as_of_t72 = target_match.kickoff_at - timedelta(hours=72)
    as_of_t2 = target_match.kickoff_at - timedelta(hours=2)

    features_t72 = build_features(db_session, target_match.id, as_of_t72)
    features_t2 = build_features(db_session, target_match.id, as_of_t2)

    assert features_t72["home"]["rest_days"] == 8
    assert features_t2["home"]["rest_days"] == 8  # mismo partido, mismo descanso real — no depende del horizonte
