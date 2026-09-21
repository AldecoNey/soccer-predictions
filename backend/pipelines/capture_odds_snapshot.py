"""Fase 6 (ADR-0021): captura manual/bajo demanda de cuotas 1X2 ("Match
Winner") vía el endpoint `/odds` de API-Football, para partidos programados
(`status='scheduled'`) cuyo `kickoff_at` cae dentro de una ventana próxima.

Solo benchmark externo (CLAUDE.md regla 4 / ADR-0003 / ADR-0009) — estas
cuotas nunca se usan como feature del modelo de producción sin un ADR nuevo
aprobado por el usuario.

Deliberadamente NO programado vía GitHub Actions (ver ADR-0021): automatizar
la cadencia es trabajo de Fase 7 ("Automatización T-72/T-24/T-2"). Este
script se corre a mano.

Uso:
    python -m pipelines.capture_odds_snapshot [--days-ahead N]

Si el proveedor todavía no tiene cuotas cargadas para un fixture (plausible
para partidos a varios días del kickoff, ver ADR-0021), ese partido se
cuenta como "sin cuotas" y se sigue con el resto — nunca es un error.

La lógica de negocio vive en `capture_odds(session, matches, now,
get_odds_fn)`, separada de `main()` (que abre/cierra la sesión real, resuelve
los partidos candidatos y hace commit), para poder testearla sin llamadas de
red reales — ver `tests/test_capture_odds_snapshot.py`.
"""

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

sys.path.insert(0, ".")
from sqlalchemy.orm import Session  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.external.api_football import get_odds  # noqa: E402
from app.models import BookmakerSnapshot, Match  # noqa: E402

MATCH_WINNER_BET_NAME = "Match Winner"


@dataclass
class OddsCaptureSummary:
    n_matches_checked: int = 0
    n_matches_with_odds: int = 0
    n_snapshots_persisted: int = 0
    # match_id (str) -> cantidad de bookmakers distintos con Match Winner
    # encontrados para ese partido en esta corrida. Informativo.
    bookmakers_per_match: dict[str, int] = field(default_factory=dict)
    skip_reasons: list[str] = field(default_factory=list)

    @property
    def n_matches_without_odds(self) -> int:
        return self.n_matches_checked - self.n_matches_with_odds


def _parse_provider_updated_at(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def capture_odds(
    session: Session,
    matches: list[Match],
    now: datetime,
    get_odds_fn: Callable[[int], list[dict]] = get_odds,
) -> OddsCaptureSummary:
    """Persiste (session.add, sin commit — responsabilidad del llamador) un
    `BookmakerSnapshot` por bookmaker con mercado "Match Winner" encontrado,
    para cada partido de `matches`. `now` se pasa explícitamente para que
    todos los snapshots de una misma corrida compartan `captured_at` y para
    que los tests puedan fijar un valor determinístico."""
    summary = OddsCaptureSummary(n_matches_checked=len(matches))

    for match in matches:
        if match.api_football_id is None:
            summary.skip_reasons.append(f"match {match.id}: sin api_football_id, no se puede consultar /odds, se omite")
            continue

        response = get_odds_fn(match.api_football_id)
        if not response:
            # Sin cuotas cargadas todavía para este fixture — esperado para
            # partidos varios días en el futuro (ver ADR-0021), no un error.
            continue

        # Dedupe por bookmaker dentro de esta corrida: la respuesta puede
        # traer más de un elemento top-level (un "batch" por cada tanda de
        # actualización del proveedor). captured_at es un único valor
        # compartido por TODA la corrida (no por batch), así que si el mismo
        # bookmaker aparece en más de un batch nos quedamos con la última
        # ocurrencia (orden de la respuesta = orden cronológico del
        # proveedor) en vez de insertar una fila por batch — insertar ambas
        # violaría UniqueConstraint(match_id, bookmaker_name, captured_at).
        per_bookmaker: dict[str, dict] = {}

        for batch in response:
            provider_updated_at = _parse_provider_updated_at(batch.get("update"))
            for bookmaker in batch.get("bookmakers", []):
                bookmaker_name = bookmaker.get("name")
                match_winner_bet = next(
                    (bet for bet in bookmaker.get("bets", []) if bet.get("name") == MATCH_WINNER_BET_NAME),
                    None,
                )
                if match_winner_bet is None:
                    continue  # este bookmaker no cotiza Match Winner para este fixture

                values = {v.get("value"): v.get("odd") for v in match_winner_bet.get("values", [])}
                if not all(key in values for key in ("Home", "Draw", "Away")):
                    summary.skip_reasons.append(
                        f"match {match.id}, bookmaker '{bookmaker_name}': Match Winner sin las 3 opciones completas, se omite"
                    )
                    continue

                per_bookmaker[bookmaker_name] = {
                    "odds_home": float(values["Home"]),
                    "odds_draw": float(values["Draw"]),
                    "odds_away": float(values["Away"]),
                    "provider_updated_at": provider_updated_at,
                    "raw_response": bookmaker,
                }

        if not per_bookmaker:
            continue  # tenía respuesta, pero ningún bookmaker con Match Winner

        for bookmaker_name, data in per_bookmaker.items():
            row = BookmakerSnapshot(
                match_id=match.id,
                bookmaker_name=bookmaker_name,
                captured_at=now,
                **data,
            )
            session.add(row)
            session.flush()
            summary.n_snapshots_persisted += 1

        summary.n_matches_with_odds += 1
        summary.bookmakers_per_match[str(match.id)] = len(per_bookmaker)

    return summary


def _print_summary(summary: OddsCaptureSummary) -> None:
    print(
        f"\n{summary.n_matches_checked} partidos revisados, "
        f"{summary.n_matches_with_odds} con cuotas encontradas, "
        f"{summary.n_matches_without_odds} sin cuotas todavía, "
        f"{summary.n_snapshots_persisted} snapshots persistidos."
    )
    if summary.bookmakers_per_match:
        print("Bookmakers por partido:")
        for match_id, n_bookmakers in summary.bookmakers_per_match.items():
            print(f"  - {match_id}: {n_bookmakers} bookmaker(s)")
    if summary.skip_reasons:
        print("Omitidos:")
        for reason in summary.skip_reasons:
            print(f"  - {reason}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Captura manual de cuotas 1X2 (ADR-0021)")
    parser.add_argument(
        "--days-ahead",
        type=int,
        default=7,
        help="Ventana de kickoff_at a futuro a considerar, en días (default 7)",
    )
    args = parser.parse_args()

    # Un solo "ahora" para toda la corrida, igual que ingest_intelligence_facts.py.
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(days=args.days_ahead)

    session = SessionLocal()
    try:
        matches = (
            session.query(Match)
            .filter(Match.status == "scheduled")
            .filter(Match.kickoff_at >= now)
            .filter(Match.kickoff_at <= window_end)
            .order_by(Match.kickoff_at)
            .all()
        )
        summary = capture_odds(session, matches, now, get_odds)
        session.commit()
    finally:
        session.close()

    _print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
