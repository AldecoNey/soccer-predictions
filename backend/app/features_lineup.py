"""rotation_index (Fase 6, Sección 9 del brief): fracción del once titular
que cambió respecto al partido anterior del mismo equipo.

A diferencia de build_features() en app/features.py, esta señal NO es
segura para T-72/T-24: usa la alineación REAL del propio partido que se
está evaluando, que en la realidad recién se conoce cerca del kickoff
(T-2, según la Sección 6 del brief — "si alineaciones confirmadas... más
cerca del inicio"). Por eso vive separada del pipeline anti-leakage
prospectivo de Fase 3: es una señal de investigación/backtesting por ahora
(Fase 6), y su integración a un pipeline en vivo real (Fase 7) tendría que
limitarse explícitamente al horizonte T-2.

No requiere as_of_timestamp: opera sobre partidos ya jugados, comparando
la alineación real de `match_id` contra la alineación real del partido
inmediatamente anterior del mismo equipo (por kickoff_at)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Match, MatchLineup


def _lineup_player_ids(session: Session, match_id: uuid.UUID, team_id: uuid.UUID) -> set[uuid.UUID]:
    stmt = select(MatchLineup.player_id).where(MatchLineup.match_id == match_id, MatchLineup.team_id == team_id)
    return {row[0] for row in session.execute(stmt).all()}


def _previous_match_id(session: Session, team_id: uuid.UUID, before_kickoff, current_match_id: uuid.UUID) -> uuid.UUID | None:
    stmt = (
        select(Match.id)
        .where(
            (Match.home_team_id == team_id) | (Match.away_team_id == team_id),
            Match.id != current_match_id,
            Match.kickoff_at < before_kickoff,
            Match.status == "finished",
        )
        .order_by(Match.kickoff_at.desc())
        .limit(1)
    )
    row = session.execute(stmt).first()
    return row[0] if row else None


def rotation_index(session: Session, match_id: uuid.UUID, team_id: uuid.UUID) -> float | None:
    """0.0 = mismo once que el partido anterior, 1.0 = los 11 cambiaron.
    None si no hay alineación del propio partido o del anterior (debut de
    temporada, o el proveedor no tenía datos para ese partido)."""
    match = session.get(Match, match_id)
    current_xi = _lineup_player_ids(session, match_id, team_id)
    if not current_xi:
        return None

    previous_id = _previous_match_id(session, team_id, match.kickoff_at, match_id)
    if previous_id is None:
        return None
    previous_xi = _lineup_player_ids(session, previous_id, team_id)
    if not previous_xi:
        return None

    changed = len(current_xi - previous_xi)
    return changed / len(current_xi)
