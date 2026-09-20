"""Fase 2 (+ extensión Fase 6, ADR-0003): ingesta de fixtures de Liga
Profesional Argentina. Originalmente limitada a 2022-2024 (free tier);
tras el upgrade a Pro (ADR-0003, 2026-09-19) también cubre 2025-2026.

Idempotente: se puede correr varias veces sin duplicar filas (upsert por
api_football_id). No usa `results` como input de `matches`/features — solo
las puebla a partir del resultado ya finalizado del proveedor. Partidos
de 2026 (temporada en curso) que todavía no se jugaron simplemente quedan
con status='scheduled' y sin result, hasta la próxima corrida.
"""

import sys
from datetime import datetime

sys.path.insert(0, ".")
sys.stdout.reconfigure(line_buffering=True)  # progreso visible en tiempo real, no solo al terminar
from app.db import SessionLocal  # noqa: E402
from app.external.api_football import LIGA_PROFESIONAL_ARGENTINA_ID, get_fixtures, get_league_seasons  # noqa: E402
from app.models import Competition, Match, Result, Season, Team  # noqa: E402

FINISHED_STATUSES = {"FT", "AET", "PEN"}
SEASONS_TO_INGEST = (2022, 2023, 2024, 2025, 2026)  # requiere plan Pro para 2025/2026 (ver ADR-0003)


def _outcome(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "home"
    if away_goals > home_goals:
        return "away"
    return "draw"


def _get_or_create_competition(session) -> Competition:
    competition = session.query(Competition).filter_by(api_football_id=LIGA_PROFESIONAL_ARGENTINA_ID).one_or_none()
    if competition is None:
        competition = Competition(
            name="Liga Profesional Argentina",
            country="Argentina",
            api_football_id=LIGA_PROFESIONAL_ARGENTINA_ID,
            external_ids={"api_football": LIGA_PROFESIONAL_ARGENTINA_ID},
        )
        session.add(competition)
        session.flush()
    return competition


def _get_or_create_season(session, competition: Competition, year: int, seasons_meta: list[dict]) -> Season:
    year_label = str(year)
    season = session.query(Season).filter_by(competition_id=competition.id, year_label=year_label).one_or_none()
    if season is not None:
        return season
    meta = next((s for s in seasons_meta if s["year"] == year), None)
    season = Season(
        competition_id=competition.id,
        year_label=year_label,
        start_date=datetime.fromisoformat(meta["start"]) if meta else None,
        end_date=datetime.fromisoformat(meta["end"]) if meta else None,
    )
    session.add(season)
    session.flush()
    return season


def _get_or_create_team(session, cache: dict, team_id: int, name: str) -> Team:
    if team_id in cache:
        return cache[team_id]
    team = session.query(Team).filter_by(api_football_id=team_id).one_or_none()
    if team is None:
        team = Team(name=name, api_football_id=team_id, external_ids={"api_football": team_id})
        session.add(team)
        session.flush()
    cache[team_id] = team
    return team


def ingest_season(session, season_year: int, seasons_meta: list[dict]) -> dict:
    competition = _get_or_create_competition(session)
    season = _get_or_create_season(session, competition, season_year, seasons_meta)
    team_cache: dict[int, Team] = {}

    stats = {"matches_created": 0, "matches_updated": 0, "results_created": 0}
    fixtures = get_fixtures(season_year)
    for fx in fixtures:
        home = _get_or_create_team(session, team_cache, fx["teams"]["home"]["id"], fx["teams"]["home"]["name"])
        away = _get_or_create_team(session, team_cache, fx["teams"]["away"]["id"], fx["teams"]["away"]["name"])

        fixture_id = fx["fixture"]["id"]
        match = session.query(Match).filter_by(api_football_id=fixture_id).one_or_none()
        status_short = fx["fixture"]["status"]["short"]
        match_status = "finished" if status_short in FINISHED_STATUSES else "scheduled"
        if status_short in {"PST", "SUSP"}:
            match_status = "postponed"
        elif status_short in {"CANC", "ABD", "WO"}:
            match_status = "cancelled"

        if match is None:
            match = Match(
                season_id=season.id,
                home_team_id=home.id,
                away_team_id=away.id,
                kickoff_at=datetime.fromisoformat(fx["fixture"]["date"]),
                venue=(fx["fixture"]["venue"] or {}).get("name"),
                matchday=fx["league"].get("round"),
                status=match_status,
                api_football_id=fixture_id,
                external_ids={"api_football": fixture_id},
            )
            session.add(match)
            session.flush()
            stats["matches_created"] += 1
        else:
            # Reescribe también kickoff_at/venue: los fixtures se reprograman
            # con cierta frecuencia (lluvia, TV, seguridad). Antes de este fix,
            # una reprogramación posterior a la primera ingesta quedaba
            # silenciosamente desactualizada — corrompiendo el cálculo de
            # horizontes T-72/T-24/T-2 y el corte anti-leakage, que dependen
            # de kickoff_at (encontrado en revisión de Fase 6, no en producción).
            match.kickoff_at = datetime.fromisoformat(fx["fixture"]["date"])
            match.venue = (fx["fixture"]["venue"] or {}).get("name")
            match.matchday = fx["league"].get("round")
            match.status = match_status
            stats["matches_updated"] += 1

        if match_status == "finished" and fx["goals"]["home"] is not None:
            existing_result = session.query(Result).filter_by(match_id=match.id).one_or_none()
            if existing_result is None:
                home_goals, away_goals = fx["goals"]["home"], fx["goals"]["away"]
                session.add(
                    Result(
                        match_id=match.id,
                        home_score=home_goals,
                        away_score=away_goals,
                        outcome=_outcome(home_goals, away_goals),
                    )
                )
                stats["results_created"] += 1

    session.commit()
    return stats


def main() -> int:
    session = SessionLocal()
    try:
        seasons_meta = get_league_seasons()
        totals = {"matches_created": 0, "matches_updated": 0, "results_created": 0}
        for year in SEASONS_TO_INGEST:
            print(f"Ingiriendo temporada {year}...")
            stats = ingest_season(session, year, seasons_meta)
            print(f"  {stats}")
            for k in totals:
                totals[k] += stats[k]
        print(f"Total: {totals}")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
