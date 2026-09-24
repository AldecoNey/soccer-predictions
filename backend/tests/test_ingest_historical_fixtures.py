"""Tests de resolve_90min_score (ADR-0019). Hallazgo real, 2026-09-24: en
partidos AET (alargue), `goals.home/away` de API-Football incluye el gol de
alargue, NO es el resultado a 90' — verificado contra 4 partidos reales de
Liga Profesional Argentina 2025/2026 (ej. fixture 1486749: fulltime 0-0,
goals 0-1 tras un gol en el alargue). `score.fulltime` es la fuente correcta.
"""

from pipelines.ingest_historical_fixtures import resolve_90min_score


def _fixture(goals_home, goals_away, fulltime_home=None, fulltime_away=None, extratime_home=None, extratime_away=None):
    return {
        "goals": {"home": goals_home, "away": goals_away},
        "score": {
            "fulltime": {"home": fulltime_home, "away": fulltime_away},
            "extratime": {"home": extratime_home, "away": extratime_away},
        },
    }


def test_ft_match_uses_fulltime_score():
    fx = _fixture(goals_home=2, goals_away=1, fulltime_home=2, fulltime_away=1)
    assert resolve_90min_score(fx) == (2, 1)


def test_aet_match_uses_fulltime_not_goals_with_extratime_baked_in():
    """Caso real: fixture 1486749 (Deportivo Riestra vs Barracas Central,
    2025-11-24). fulltime=0-0, goals=0-1 (incluye el gol de alargue) —
    resolve_90min_score debe devolver el resultado a 90', no el de goals."""
    fx = _fixture(goals_home=0, goals_away=1, fulltime_home=0, fulltime_away=0, extratime_home=0, extratime_away=1)
    assert resolve_90min_score(fx) == (0, 0)


def test_pen_match_without_extratime_matches_fulltime_and_goals():
    """Caso real: fixture 1374527 (Boca vs Lanús). Esta competencia va de
    90' directo a penales sin alargue — fulltime y goals coinciden acá, no
    porque goals sea la fuente correcta sino porque no hubo alargue que
    los desalineara."""
    fx = _fixture(goals_home=0, goals_away=0, fulltime_home=0, fulltime_away=0)
    assert resolve_90min_score(fx) == (0, 0)


def test_missing_fulltime_falls_back_to_goals():
    fx = {"goals": {"home": 3, "away": 2}, "score": {}}
    assert resolve_90min_score(fx) == (3, 2)


def test_missing_score_key_entirely_falls_back_to_goals():
    fx = {"goals": {"home": 1, "away": 1}}
    assert resolve_90min_score(fx) == (1, 1)
