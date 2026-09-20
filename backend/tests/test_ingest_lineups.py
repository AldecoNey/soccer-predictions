"""Regresión: resolve_team_id nunca debe asumir "si no es local, es
visitante" sin verificarlo (bug real encontrado en revisión de Fase 6,
corregido en pipelines/ingest_lineups.py)."""

import uuid

from pipelines.ingest_lineups import resolve_team_id

HOME_ID, AWAY_ID = uuid.uuid4(), uuid.uuid4()
HOME_API_ID, AWAY_API_ID = 100, 200


def test_resolves_home_team():
    assert resolve_team_id(HOME_ID, HOME_API_ID, AWAY_ID, AWAY_API_ID, HOME_API_ID) == HOME_ID


def test_resolves_away_team():
    assert resolve_team_id(HOME_ID, HOME_API_ID, AWAY_ID, AWAY_API_ID, AWAY_API_ID) == AWAY_ID


def test_returns_none_when_neither_matches():
    """Antes del fix, esto habría devuelto AWAY_ID silenciosamente — el bug real."""
    assert resolve_team_id(HOME_ID, HOME_API_ID, AWAY_ID, AWAY_API_ID, 999) is None
