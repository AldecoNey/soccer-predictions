from datetime import datetime, timedelta, timezone

from app.features_lineup import rotation_index
from app.models import Competition, Match, MatchLineup, Player, Season, Team

BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _seed(session):
    competition = Competition(name="Liga de prueba")
    session.add(competition)
    session.flush()
    season = Season(competition_id=competition.id, year_label="2026")
    session.add(season)
    session.flush()

    home, away = Team(name="A"), Team(name="B")
    session.add_all([home, away])
    session.flush()

    players = [Player(name=f"P{i}") for i in range(22)]
    session.add_all(players)
    session.flush()

    match1 = Match(season_id=season.id, home_team_id=home.id, away_team_id=away.id, kickoff_at=BASE_TIME, status="finished")
    match2 = Match(season_id=season.id, home_team_id=home.id, away_team_id=away.id, kickoff_at=BASE_TIME + timedelta(days=7), status="finished")
    session.add_all([match1, match2])
    session.flush()
    return match1, match2, home, players


def _lineup(session, match_id, team_id, players):
    for p in players:
        session.add(MatchLineup(match_id=match_id, team_id=team_id, player_id=p.id))
    session.flush()


def test_identical_lineup_is_zero_rotation(db_session):
    match1, match2, home, players = _seed(db_session)
    xi = players[:11]
    _lineup(db_session, match1.id, home.id, xi)
    _lineup(db_session, match2.id, home.id, xi)
    db_session.commit()

    assert rotation_index(db_session, match2.id, home.id) == 0.0


def test_fully_different_lineup_is_one(db_session):
    match1, match2, home, players = _seed(db_session)
    _lineup(db_session, match1.id, home.id, players[:11])
    _lineup(db_session, match2.id, home.id, players[11:22])
    db_session.commit()

    assert rotation_index(db_session, match2.id, home.id) == 1.0


def test_partial_rotation(db_session):
    match1, match2, home, players = _seed(db_session)
    _lineup(db_session, match1.id, home.id, players[:11])
    # 8 iguales (players[3:11]) + 3 nuevos (players[11:14])
    _lineup(db_session, match2.id, home.id, players[3:11] + players[11:14])
    db_session.commit()

    assert rotation_index(db_session, match2.id, home.id) == 3 / 11


def test_none_when_no_previous_match_lineup(db_session):
    match1, match2, home, players = _seed(db_session)
    _lineup(db_session, match2.id, home.id, players[:11])  # match1 sin alineación cargada
    db_session.commit()

    assert rotation_index(db_session, match2.id, home.id) is None


def test_none_when_current_match_has_no_lineup(db_session):
    match1, match2, home, players = _seed(db_session)
    _lineup(db_session, match1.id, home.id, players[:11])
    db_session.commit()

    assert rotation_index(db_session, match2.id, home.id) is None
