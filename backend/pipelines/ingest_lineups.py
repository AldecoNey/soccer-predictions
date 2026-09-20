"""Fase 6: ingesta de alineaciones titulares (1 request por partido —
requiere el plan Pro para completarlo en un tiempo razonable, ver ADR-0003).

Idempotente: salta partidos que ya tienen match_lineups cargadas. Solo
procesa partidos con status='finished' (no tiene sentido pedir alineación
de un partido que todavía no se jugó).
"""

import sys
import time

sys.path.insert(0, ".")
from app.db import SessionLocal  # noqa: E402
from app.external.api_football import ApiFootballError, get_lineups  # noqa: E402
from app.models import Match, MatchLineup, Player  # noqa: E402

REQUEST_DELAY_SECONDS = 0.15  # cortesía con el rate limit por minuto, no solo el diario


def _get_or_create_player(session, cache: dict, player_id: int, name: str) -> Player:
    if player_id in cache:
        return cache[player_id]
    player = session.query(Player).filter_by(api_football_id=player_id).one_or_none()
    if player is None:
        player = Player(name=name, api_football_id=player_id)
        session.add(player)
        session.flush()
    cache[player_id] = player
    return player


def main() -> int:
    session = SessionLocal()
    player_cache: dict[int, Player] = {}
    try:
        pending = (
            session.query(Match)
            .filter(Match.status == "finished", Match.api_football_id.isnot(None))
            .order_by(Match.kickoff_at.asc())
            .all()
        )
        already_done = {row[0] for row in session.query(MatchLineup.match_id).distinct().all()}
        pending = [m for m in pending if m.id not in already_done]

        print(f"{len(pending)} partidos finalizados sin alineación cargada todavía.")
        no_lineup_available = 0
        for i, match in enumerate(pending, start=1):
            try:
                lineups = get_lineups(match.api_football_id)
            except ApiFootballError as exc:
                print(f"  [{i}/{len(pending)}] error en fixture {match.api_football_id}: {exc}")
                time.sleep(REQUEST_DELAY_SECONDS)
                continue

            if not lineups:
                no_lineup_available += 1
                time.sleep(REQUEST_DELAY_SECONDS)
                continue

            for team_lineup in lineups:
                api_team_id = team_lineup["team"]["id"]
                team_id = match.home_team_id if _team_matches(session, match.home_team_id, api_team_id) else match.away_team_id
                for entry in team_lineup.get("startXI", []):
                    p = entry["player"]
                    player = _get_or_create_player(session, player_cache, p["id"], p["name"])
                    session.add(MatchLineup(match_id=match.id, team_id=team_id, player_id=player.id, position=p.get("pos")))
            session.commit()

            if i % 50 == 0:
                print(f"  [{i}/{len(pending)}] procesados...")
            time.sleep(REQUEST_DELAY_SECONDS)

        print(f"OK: {len(pending) - no_lineup_available} partidos con alineación cargada, {no_lineup_available} sin alineación disponible en el proveedor.")
        return 0
    finally:
        session.close()


_team_external_id_cache: dict = {}


def _team_matches(session, team_id, api_team_id) -> bool:
    if team_id not in _team_external_id_cache:
        from app.models import Team

        team = session.get(Team, team_id)
        _team_external_id_cache[team_id] = team.api_football_id
    return _team_external_id_cache[team_id] == api_team_id


if __name__ == "__main__":
    raise SystemExit(main())
