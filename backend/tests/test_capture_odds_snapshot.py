"""Tests del pipeline de captura manual de cuotas 1X2 (ADR-0021). Corren
contra Neon dentro de una transacción que siempre se revierte (ver
conftest.db_session) — `capture_odds()` recibe la sesión de test
directamente en vez de abrir la suya propia, así todo lo que persiste queda
dentro de la misma transacción que el fixture revierte al final.

Sufijo único por corrida de tests, mismo motivo que
test_ingest_intelligence_facts.py: la BD es la misma Neon con datos reales
ya ingeridos (no hay entorno separado todavía). Regla derivada de esa misma
sesión de trabajo (hallazgo de auditoría QA, 2026-09-21): ningún assert acá
puede consultar `BookmakerSnapshot` sin acotar por el `match_id` que el
propio test creó — la tabla puede llegar a tener filas de producción reales
en cualquier momento, incluso si hoy todavía no las tiene.
"""

import uuid
from datetime import datetime, timedelta, timezone

from app.models import BookmakerSnapshot, Competition, Match, Season, Team
from pipelines.capture_odds_snapshot import capture_odds

_RUN_SUFFIX = uuid.uuid4().hex[:8]


_UNSET = object()


def _make_match(session, api_football_id=_UNSET):
    suffix = uuid.uuid4().hex[:8]
    competition = Competition(name=f"Test Competition {suffix}", country="Argentina")
    session.add(competition)
    session.flush()
    season = Season(competition_id=competition.id, year_label="2026")
    session.add(season)
    session.flush()
    home = Team(name=f"Test Home FC {suffix}")
    away = Team(name=f"Test Away FC {suffix}")
    session.add_all([home, away])
    session.flush()
    resolved_api_football_id = (
        int(uuid.uuid4().int % 1_000_000_000) if api_football_id is _UNSET else api_football_id
    )
    match = Match(
        season_id=season.id,
        home_team_id=home.id,
        away_team_id=away.id,
        kickoff_at=datetime.now(timezone.utc) + timedelta(days=3),
        api_football_id=resolved_api_football_id,
    )
    session.add(match)
    session.flush()
    return match, home, away


def _match_winner_bet(home="3.10", draw="2.88", away="2.40"):
    return {
        "id": 1,
        "name": "Match Winner",
        "values": [
            {"value": "Home", "odd": home},
            {"value": "Draw", "odd": draw},
            {"value": "Away", "odd": away},
        ],
    }


def _odds_response(fixture_id, bookmakers, update="2026-09-21T12:00:19+00:00"):
    return [
        {
            "league": {"id": 128},
            "fixture": {"id": fixture_id},
            "update": update,
            "bookmakers": bookmakers,
        }
    ]


def test_multi_bookmaker_response_persists_one_row_per_bookmaker(db_session):
    match, _, _ = _make_match(db_session)
    now = datetime.now(timezone.utc)

    response = _odds_response(
        match.api_football_id,
        bookmakers=[
            {
                "id": 7,
                "name": f"William Hill {_RUN_SUFFIX}",
                "bets": [_match_winner_bet("3.10", "2.88", "2.40")],
            },
            {
                "id": 8,
                "name": f"Bet365 {_RUN_SUFFIX}",
                "bets": [_match_winner_bet("3.00", "2.90", "2.50")],
            },
        ],
    )

    def fake_get_odds(fixture_id):
        assert fixture_id == match.api_football_id
        return response

    summary = capture_odds(db_session, [match], now, get_odds_fn=fake_get_odds)

    assert summary.n_matches_checked == 1
    assert summary.n_matches_with_odds == 1
    assert summary.n_snapshots_persisted == 2
    assert summary.bookmakers_per_match[str(match.id)] == 2

    rows = (
        db_session.query(BookmakerSnapshot)
        .filter_by(match_id=match.id)
        .order_by(BookmakerSnapshot.bookmaker_name)
        .all()
    )
    assert len(rows) == 2

    bet365 = next(r for r in rows if r.bookmaker_name == f"Bet365 {_RUN_SUFFIX}")
    assert bet365.odds_home == 3.00
    assert bet365.odds_draw == 2.90
    assert bet365.odds_away == 2.50
    assert bet365.captured_at == now
    assert bet365.provider_updated_at == datetime.fromisoformat("2026-09-21T12:00:19+00:00")

    william_hill = next(r for r in rows if r.bookmaker_name == f"William Hill {_RUN_SUFFIX}")
    assert william_hill.odds_home == 3.10
    assert william_hill.odds_draw == 2.88
    assert william_hill.odds_away == 2.40


def test_fixture_with_no_odds_is_skipped_cleanly(db_session):
    match, _, _ = _make_match(db_session)
    now = datetime.now(timezone.utc)

    def fake_get_odds(fixture_id):
        return []  # API-Football todavía no cargó cuotas para este fixture

    summary = capture_odds(db_session, [match], now, get_odds_fn=fake_get_odds)

    assert summary.n_matches_checked == 1
    assert summary.n_matches_with_odds == 0
    assert summary.n_snapshots_persisted == 0
    assert str(match.id) not in summary.bookmakers_per_match
    assert db_session.query(BookmakerSnapshot).filter_by(match_id=match.id).count() == 0


def test_bookmaker_without_match_winner_bet_is_skipped_for_that_bookmaker(db_session):
    match, _, _ = _make_match(db_session)
    now = datetime.now(timezone.utc)

    response = _odds_response(
        match.api_football_id,
        bookmakers=[
            {
                "id": 7,
                "name": f"OnlyOverUnder {_RUN_SUFFIX}",
                "bets": [{"id": 5, "name": "Over/Under", "values": [{"value": "Over 2.5", "odd": "1.90"}]}],
            },
            {
                "id": 8,
                "name": f"HasMatchWinner {_RUN_SUFFIX}",
                "bets": [_match_winner_bet()],
            },
        ],
    )

    def fake_get_odds(fixture_id):
        return response

    summary = capture_odds(db_session, [match], now, get_odds_fn=fake_get_odds)

    assert summary.n_snapshots_persisted == 1
    assert summary.n_matches_with_odds == 1

    rows = db_session.query(BookmakerSnapshot).filter_by(match_id=match.id).all()
    assert len(rows) == 1
    assert rows[0].bookmaker_name == f"HasMatchWinner {_RUN_SUFFIX}"


def test_raw_response_round_trips_through_jsonb(db_session):
    match, _, _ = _make_match(db_session)
    now = datetime.now(timezone.utc)

    bookmaker = {
        "id": 7,
        "name": f"William Hill {_RUN_SUFFIX}",
        "bets": [
            _match_winner_bet(),
            {"id": 2, "name": "Home/Away", "values": [{"value": "Home", "odd": "1.20"}]},
        ],
    }
    response = _odds_response(match.api_football_id, bookmakers=[bookmaker])

    def fake_get_odds(fixture_id):
        return response

    capture_odds(db_session, [match], now, get_odds_fn=fake_get_odds)
    db_session.flush()

    row = db_session.query(BookmakerSnapshot).filter_by(match_id=match.id).one()
    assert row.raw_response == bookmaker
    assert row.raw_response["bets"][1]["name"] == "Home/Away"


def test_match_without_api_football_id_is_skipped_and_reported(db_session):
    match, _, _ = _make_match(db_session, api_football_id=None)
    now = datetime.now(timezone.utc)

    def fake_get_odds(fixture_id):
        raise AssertionError("no debería llamarse /odds sin api_football_id")

    summary = capture_odds(db_session, [match], now, get_odds_fn=fake_get_odds)

    assert summary.n_matches_checked == 1
    assert summary.n_matches_with_odds == 0
    assert summary.n_snapshots_persisted == 0
    assert any(str(match.id) in reason for reason in summary.skip_reasons)


def test_duplicate_bookmaker_across_batches_deduped_to_latest(db_session):
    """Si la respuesta trae más de un batch (el proveedor actualizó dos
    veces) y el mismo bookmaker aparece en ambos, no debe intentarse
    insertar dos filas con el mismo (match_id, bookmaker_name, captured_at)
    -- violaría el UniqueConstraint, porque captured_at es un único valor
    por corrida, no por batch."""
    match, _, _ = _make_match(db_session)
    now = datetime.now(timezone.utc)
    bookmaker_name = f"William Hill {_RUN_SUFFIX}"

    response = [
        {
            "league": {"id": 128},
            "fixture": {"id": match.api_football_id},
            "update": "2026-09-21T10:00:00+00:00",
            "bookmakers": [{"id": 7, "name": bookmaker_name, "bets": [_match_winner_bet("3.10", "2.88", "2.40")]}],
        },
        {
            "league": {"id": 128},
            "fixture": {"id": match.api_football_id},
            "update": "2026-09-21T12:00:19+00:00",
            "bookmakers": [{"id": 7, "name": bookmaker_name, "bets": [_match_winner_bet("3.05", "2.90", "2.45")]}],
        },
    ]

    def fake_get_odds(fixture_id):
        return response

    summary = capture_odds(db_session, [match], now, get_odds_fn=fake_get_odds)

    assert summary.n_snapshots_persisted == 1
    row = db_session.query(BookmakerSnapshot).filter_by(match_id=match.id).one()
    # se queda con la última ocurrencia (segundo batch)
    assert row.odds_home == 3.05
    assert row.provider_updated_at == datetime.fromisoformat("2026-09-21T12:00:19+00:00")
