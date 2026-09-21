"""Tests del pipeline determinista de persistencia de hechos del Football
Intelligence Agent (ADR-0020). Corren contra Neon dentro de una transacción
que siempre se revierte (ver conftest.db_session) — `ingest_facts()` recibe
la sesión de test directamente en vez de abrir la suya propia, así todo lo
que persiste queda dentro de la misma transacción que el fixture revierte al
final.
"""

import uuid
from datetime import datetime, timedelta, timezone

from app.models import Competition, DataSource, Match, NewsSignal, Player, PlayerAvailability, Season, Team
from pipelines.ingest_intelligence_facts import ingest_facts

# Sufijo único por corrida de tests: la BD es la misma Neon con datos reales
# ya ingeridos (no hay entorno separado todavía), y el pipeline resuelve
# equipos/fuentes/jugadores por nombre EXACTO — reusar un nombre real
# (ej. "TyC Sports" si ya existiera) haría que una query por nombre
# devolviera más de una fila dentro de la transacción de test.
_RUN_SUFFIX = uuid.uuid4().hex[:8]
_TEST_SOURCE_NAME = f"Test Wire Service {_RUN_SUFFIX}"


def _make_competition_season(session):
    competition = Competition(name="Liga Profesional Argentina", country="Argentina")
    session.add(competition)
    session.flush()
    season = Season(competition_id=competition.id, year_label="2026")
    session.add(season)
    session.flush()
    return competition, season


def _make_match(session):
    # Nombres de equipo con sufijo único: la BD de test es la misma Neon con
    # datos reales ya ingeridos (no hay entorno separado todavía, ver
    # ADR-0017/roadmap Fase 7) — un nombre real como "San Lorenzo" ya existe
    # fuera de esta transacción, y el pipeline resuelve equipos por nombre
    # EXACTO, así que reusar un nombre real haría que la query por nombre
    # devuelva 2 filas (la real + la de este test) en vez de 1.
    suffix = uuid.uuid4().hex[:8]
    _, season = _make_competition_season(session)
    home = Team(name=f"Test Home FC {suffix}")
    away = Team(name=f"Test Away FC {suffix}")
    session.add_all([home, away])
    session.flush()
    match = Match(
        season_id=season.id,
        home_team_id=home.id,
        away_team_id=away.id,
        kickoff_at=datetime.now(timezone.utc) + timedelta(days=2),
    )
    session.add(match)
    session.flush()
    return match, home, away


def _player_availability_fact(match_id, team_name, player_name=None):
    if player_name is None:
        player_name = f"Jugador de Prueba {_RUN_SUFFIX}"
    return {
        "fact_type": "player_availability",
        "match_id": str(match_id),
        "team_name": team_name,
        "player_name": player_name,
        "status": "doubtful",
        "reason": "muscle_injury",
        "source_name": _TEST_SOURCE_NAME,
        "source_type": "established_outlet",
        "reliability_level": "B",
        "source_url": "https://example.com/nota",
        "event_time": "2026-09-19T10:00:00Z",
        "published_at": "2026-09-19T12:00:00Z",
        "raw_quote": "El jugador arrastra una molestia muscular y es duda.",
    }


def test_valid_fact_persists_with_observed_at_equal_available_at(db_session):
    match, home, _ = _make_match(db_session)
    now = datetime.now(timezone.utc)

    raw = {"facts": [_player_availability_fact(match.id, home.name)]}
    summary = ingest_facts(db_session, raw, now)

    assert summary.n_read == 1
    assert summary.n_persisted == 1
    assert summary.n_skipped == 0
    assert summary.n_new_players == 1
    assert summary.n_new_sources == 1

    row = db_session.query(PlayerAvailability).one()
    assert row.observed_at == now
    assert row.available_at == now
    assert row.ingested_at == now
    assert row.confidence == "B"
    assert row.status == "doubtful"


def test_unknown_match_id_is_skipped_and_reported_without_crashing_batch(db_session):
    _, home, _ = _make_match(db_session)
    now = datetime.now(timezone.utc)
    bogus_match_id = uuid.uuid4()

    valid_match, valid_home, _ = _make_match(db_session)
    raw = {
        "facts": [
            _player_availability_fact(bogus_match_id, home.name, player_name="Jugador Fantasma"),
            _player_availability_fact(valid_match.id, valid_home.name, player_name="Jugador Real"),
        ]
    }
    summary = ingest_facts(db_session, raw, now)

    assert summary.n_read == 2
    assert summary.n_persisted == 1
    assert summary.n_skipped == 1
    assert str(bogus_match_id) in summary.skip_reasons[0]

    persisted = db_session.query(PlayerAvailability).one()
    player = db_session.get(Player, persisted.player_id)
    assert player.name == "Jugador Real"


def test_unknown_team_name_is_skipped_and_reported(db_session):
    match, _, _ = _make_match(db_session)
    now = datetime.now(timezone.utc)

    raw = {"facts": [_player_availability_fact(match.id, "Equipo Que No Existe")]}
    summary = ingest_facts(db_session, raw, now)

    assert summary.n_persisted == 0
    assert summary.n_skipped == 1
    assert "Equipo Que No Existe" in summary.skip_reasons[0]
    assert db_session.query(PlayerAvailability).count() == 0


def test_invalid_schema_fact_is_skipped_and_reported(db_session):
    match, home, _ = _make_match(db_session)
    now = datetime.now(timezone.utc)

    bad_fact = _player_availability_fact(match.id, home.name)
    bad_fact["status"] = "not_a_real_status"  # enum inválido

    raw = {"facts": [bad_fact]}
    summary = ingest_facts(db_session, raw, now)

    assert summary.n_persisted == 0
    assert summary.n_skipped == 1
    assert "schema inválido" in summary.skip_reasons[0]


def test_missing_raw_quote_is_rejected():
    """raw_quote es el rastro de auditoría — nunca opcional. Se valida acá
    directo contra el schema (sin BD) porque es puramente un test de
    validación de forma."""
    from pydantic import TypeAdapter, ValidationError

    from app.schemas_intelligence import Fact

    fact = _player_availability_fact(uuid.uuid4(), "Cualquiera")
    del fact["raw_quote"]

    adapter = TypeAdapter(Fact)
    try:
        adapter.validate_python(fact)
        raise AssertionError("se esperaba ValidationError por raw_quote faltante")
    except ValidationError:
        pass


def test_new_player_and_data_source_created_and_logged(db_session):
    match, home, _ = _make_match(db_session)
    now = datetime.now(timezone.utc)

    raw = {"facts": [_player_availability_fact(match.id, home.name, player_name="Jugador Totalmente Nuevo")]}
    summary = ingest_facts(db_session, raw, now)

    assert summary.n_new_players == 1
    assert summary.n_new_sources == 1

    player = db_session.query(Player).filter_by(name="Jugador Totalmente Nuevo").one()
    assert player.api_football_id is None

    source = db_session.query(DataSource).filter_by(name=_TEST_SOURCE_NAME).one()
    assert source.reliability_level == "B"
    assert source.source_type == "established_outlet"


def test_existing_player_and_source_are_reused_not_duplicated(db_session):
    match, home, _ = _make_match(db_session)
    now = datetime.now(timezone.utc)

    existing_player = Player(name="Jugador Existente", api_football_id=None)
    existing_source = DataSource(name=_TEST_SOURCE_NAME, reliability_level="B", source_type="established_outlet")
    db_session.add_all([existing_player, existing_source])
    db_session.flush()

    raw = {"facts": [_player_availability_fact(match.id, home.name, player_name="Jugador Existente")]}
    summary = ingest_facts(db_session, raw, now)

    assert summary.n_new_players == 0
    assert summary.n_new_sources == 0
    assert db_session.query(Player).filter_by(name="Jugador Existente").count() == 1
    assert db_session.query(DataSource).filter_by(name=_TEST_SOURCE_NAME).count() == 1


def test_raw_fact_matches_original_input_exactly(db_session):
    match, home, _ = _make_match(db_session)
    now = datetime.now(timezone.utc)

    original_fact = _player_availability_fact(match.id, home.name)
    raw = {"facts": [original_fact]}
    ingest_facts(db_session, raw, now)

    # Fuerza una relectura real desde Postgres (todavía dentro de la misma
    # transacción sin commitear) en vez de comparar contra el objeto Python
    # que la identity map de SQLAlchemy ya tenía en memoria — así el test
    # verifica el round-trip real por JSONB, no una tautología.
    db_session.expire_all()
    row = db_session.query(PlayerAvailability).one()
    assert row.raw_fact == original_fact


def test_news_signal_without_match_or_team_persists(db_session):
    """news_signal permite match_id/team_name nulos (a diferencia de
    player_availability, donde team_name es obligatorio)."""
    now = datetime.now(timezone.utc)
    raw = {
        "facts": [
            {
                "fact_type": "news_signal",
                "match_id": None,
                "team_name": None,
                "signal_type": "coaching_change",
                "description": "Cambio de entrenador confirmado por el club.",
                "source_name": f"Test Club Site {_RUN_SUFFIX}",
                "source_type": "official_club",
                "reliability_level": "A",
                "source_url": None,
                "event_time": None,
                "published_at": None,
                "raw_quote": "El club confirma el cambio de entrenador.",
            }
        ]
    }
    summary = ingest_facts(db_session, raw, now)

    assert summary.n_persisted == 1
    row = db_session.query(NewsSignal).one()
    assert row.team_id is None
    assert row.match_id is None
    assert row.observed_at == now
    assert row.available_at == now


def test_matches_with_insufficient_information_passed_through_not_persisted(db_session):
    now = datetime.now(timezone.utc)
    bogus_id = str(uuid.uuid4())
    raw = {"facts": [], "matches_with_insufficient_information": [bogus_id]}

    summary = ingest_facts(db_session, raw, now)

    assert summary.matches_with_insufficient_information == [bogus_id]
    assert summary.n_persisted == 0
