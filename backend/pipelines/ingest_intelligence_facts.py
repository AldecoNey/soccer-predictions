"""Fase 6 (ADR-0020): pipeline determinista que valida y persiste los hechos
producidos por el Football Intelligence Agent (`.claude/agents/football-intelligence.md`).

Ese agente entrega JSON, nunca escribe directo a la base de datos — este
script es la frontera determinista mencionada en su propia definición ("un
pipeline determinista de Data & Backend Platform Agent los valida y
persiste"). Coherente con el principio central del proyecto (CLAUDE.md): un
LLM nunca decide por sí mismo un valor anti-leakage-crítico.

Uso:
    python -m pipelines.ingest_intelligence_facts <ruta_al_json>

Decisión de diseño, no reinterpretable (ver instrucciones de la tarea): el
JSON de entrada NO trae `observed_at` ni `available_at` — este script los
estampa él mismo con un único `datetime.now(timezone.utc)` capturado una vez
al principio de la corrida, igual para `observed_at`/`ingested_at`/
`available_at` de todos los hechos de esta corrida (política por defecto
`available_at = observed_at`, documentada en docs/data/schema.md). Si el JSON
trajera esas claves igual se ignorarían: `app.schemas_intelligence` las
descarta por `extra="ignore"` — no hay ningún camino de código donde un valor
provisto por el agente llegue a esas columnas.

Fallos parciales: un hecho individual que no valida contra el schema, o cuyo
match_id/team_name no resuelve contra la base, se omite y se reporta — no
aborta el resto del batch. El código de salida de `main()` es distinto de 0
si hubo al menos un hecho omitido, para que no se confunda "corrida
completa" con "corrida con omisiones" en CI o en ejecución manual.

La lógica de negocio vive en `ingest_facts(session, raw, now)`, separada de
`main()` (que solo abre/cierra la sesión real y hace commit), para poder
testearla contra una transacción de test que se revierte siempre — ver
`tests/test_ingest_intelligence_facts.py`.
"""

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

sys.path.insert(0, ".")
from pydantic import TypeAdapter, ValidationError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import DataSource, Match, NewsSignal, Player, PlayerAvailability, Team  # noqa: E402
from app.schemas_intelligence import Fact, PlayerAvailabilityFact  # noqa: E402

_fact_adapter = TypeAdapter(Fact)


@dataclass
class IngestSummary:
    n_read: int = 0
    n_persisted: int = 0
    skip_reasons: list[str] = field(default_factory=list)
    n_new_players: int = 0
    n_new_sources: int = 0
    matches_with_insufficient_information: list[str] = field(default_factory=list)

    @property
    def n_skipped(self) -> int:
        return len(self.skip_reasons)


def _get_or_create_player(session: Session, cache: dict[str, Player], name: str) -> tuple[Player, bool]:
    """Match exacto por nombre. Un jugador investigado manualmente que
    todavía no apareció en ninguna alineación ingerida es un caso esperado
    (no un error) — se crea con api_football_id=None, pero se reporta."""
    if name in cache:
        return cache[name], False
    player = session.query(Player).filter_by(name=name).one_or_none()
    created = False
    if player is None:
        player = Player(name=name, api_football_id=None)
        session.add(player)
        session.flush()
        created = True
    cache[name] = player
    return player, created


def _get_or_create_source(
    session: Session, cache: dict[str, DataSource], name: str, source_type: str, reliability_level: str
) -> tuple[DataSource, bool]:
    """Match exacto por nombre. Una fuente legítima nunca vista antes es
    esperada per ADR-0020, no un error — se crea, pero se reporta."""
    if name in cache:
        return cache[name], False
    source = session.query(DataSource).filter_by(name=name).one_or_none()
    created = False
    if source is None:
        source = DataSource(name=name, source_type=source_type, reliability_level=reliability_level)
        session.add(source)
        session.flush()
        created = True
    cache[name] = source
    return source, created


def ingest_facts(session: Session, raw: dict, now: datetime) -> IngestSummary:
    """Valida y persiste (session.add, sin commit — eso es responsabilidad
    del llamador) los hechos de `raw` contra `session`. `now` se pasa
    explícitamente (en vez de llamarse a sí misma) para que todos los hechos
    de una misma corrida compartan exactamente el mismo `observed_at` y para
    que los tests puedan fijar un valor determinístico."""
    raw_facts = raw.get("facts", [])
    summary = IngestSummary(
        n_read=len(raw_facts),
        matches_with_insufficient_information=list(raw.get("matches_with_insufficient_information", [])),
    )

    player_cache: dict[str, Player] = {}
    source_cache: dict[str, DataSource] = {}

    for i, raw_fact in enumerate(raw_facts):
        try:
            fact = _fact_adapter.validate_python(raw_fact)
        except ValidationError as exc:
            first_error = exc.errors()[0] if exc.errors() else {"msg": str(exc)}
            summary.skip_reasons.append(f"fact[{i}]: schema inválido ({first_error.get('loc')}: {first_error.get('msg')})")
            continue

        match = None
        if fact.match_id is not None:
            match = session.get(Match, fact.match_id)
            if match is None:
                summary.skip_reasons.append(f"fact[{i}] ({fact.fact_type}): match_id {fact.match_id} no existe en matches, se omite")
                continue

        team = None
        if fact.team_name is not None:
            team = session.query(Team).filter_by(name=fact.team_name).one_or_none()
            if team is None:
                summary.skip_reasons.append(
                    f"fact[{i}] ({fact.fact_type}): team_name '{fact.team_name}' no coincide con ningún equipo, se omite"
                )
                continue

        source, source_created = _get_or_create_source(
            session, source_cache, fact.source_name, fact.source_type, fact.reliability_level
        )
        if source_created:
            summary.n_new_sources += 1
            print(f"  [INFO] DataSource nueva creada: '{fact.source_name}' ({fact.source_type}, nivel {fact.reliability_level})")

        if isinstance(fact, PlayerAvailabilityFact):
            # team es obligatorio para este tipo de hecho (team_name no-vacío
            # validado por el schema) y ya se resolvió arriba o se omitió.
            player, player_created = _get_or_create_player(session, player_cache, fact.player_name)
            if player_created:
                summary.n_new_players += 1
                print(f"  [INFO] Player nuevo creado: '{fact.player_name}' (api_football_id=None)")

            row = PlayerAvailability(
                player_id=player.id,
                team_id=team.id,
                match_id=match.id if match else None,
                status=fact.status,
                reason=fact.reason,
                confidence=fact.reliability_level,
                source_id=source.id,
                source_url=fact.source_url,
                event_time=fact.event_time,
                published_at=fact.published_at,
                observed_at=now,
                ingested_at=now,
                available_at=now,
                raw_fact=raw_fact,
            )
        else:
            row = NewsSignal(
                team_id=team.id if team else None,
                match_id=match.id if match else None,
                signal_type=fact.signal_type,
                description=fact.description,
                source_id=source.id,
                source_url=fact.source_url,
                event_time=fact.event_time,
                published_at=fact.published_at,
                observed_at=now,
                ingested_at=now,
                available_at=now,
                raw_fact=raw_fact,
            )

        session.add(row)
        session.flush()
        summary.n_persisted += 1

    return summary


def _print_summary(summary: IngestSummary) -> None:
    print(f"\n{summary.n_read} hechos leídos, {summary.n_persisted} persistidos, {summary.n_skipped} omitidos.")
    print(f"{summary.n_new_players} Player nuevos creados, {summary.n_new_sources} DataSource nuevas creadas.")
    if summary.skip_reasons:
        print("Omitidos:")
        for reason in summary.skip_reasons:
            print(f"  - {reason}")
    if summary.matches_with_insufficient_information:
        print(
            f"\nPartidos marcados por el agente como información insuficiente "
            f"({len(summary.matches_with_insufficient_information)}), no persistido en ninguna tabla:"
        )
        for match_id in summary.matches_with_insufficient_information:
            print(f"  - {match_id}")


def main() -> int:
    if len(sys.argv) != 2:
        print("uso: python -m pipelines.ingest_intelligence_facts <ruta_al_json>")
        return 2

    path = sys.argv[1]
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    # Un solo "ahora" para toda la corrida: todos los hechos de este archivo
    # fueron "observados" por esta misma pasada de investigación, no uno por
    # uno en momentos distintos.
    now = datetime.now(timezone.utc)

    session = SessionLocal()
    try:
        summary = ingest_facts(session, raw, now)
        session.commit()
    finally:
        session.close()

    _print_summary(summary)
    return 1 if summary.n_skipped > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
