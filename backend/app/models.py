"""Modelos SQLAlchemy para las tablas núcleo necesarias en Fases 2-3, más las
que se fueron agregando a medida que las fases posteriores las necesitaron
(match_lineups/model_versions/evaluation_metrics, Fase 4-6; data_sources/
player_availability/news_signals, Fase 6 — activación del Football
Intelligence Agent; bookmaker_snapshots, Fase 6 — ADR-0021, benchmark de
cuotas). El resto del esquema de docs/data/schema.md (predictions, etc.) se
agrega en las fases que realmente las necesitan, no de antemano.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Competition(Base):
    __tablename__ = "competitions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    country: Mapped[str | None] = mapped_column(String)
    api_football_id: Mapped[int | None] = mapped_column(unique=True)
    external_ids: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    seasons: Mapped[list["Season"]] = relationship(back_populates="competition")


class Season(Base):
    __tablename__ = "seasons"

    id: Mapped[uuid.UUID] = _uuid_pk()
    competition_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("competitions.id"), nullable=False)
    year_label: Mapped[str] = mapped_column(String, nullable=False)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    competition: Mapped[Competition] = relationship(back_populates="seasons")
    matches: Mapped[list["Match"]] = relationship(back_populates="season")

    __table_args__ = (UniqueConstraint("competition_id", "year_label"),)


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    short_name: Mapped[str | None] = mapped_column(String)
    country: Mapped[str | None] = mapped_column(String)
    api_football_id: Mapped[int | None] = mapped_column(unique=True)
    external_ids: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


MATCH_STATUSES = ("scheduled", "postponed", "finished", "cancelled")


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[uuid.UUID] = _uuid_pk()
    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seasons.id"), nullable=False)
    home_team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    away_team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    kickoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    venue: Mapped[str | None] = mapped_column(String)
    # ej. "2nd Phase - 1" (Liga Profesional usa fases, no solo fechas numéricas).
    # Nota (ADR-0013): el downgrade de la migración 94407e13dc47 (String -> Integer)
    # no es realmente reversible una vez que existan valores no numéricos como
    # este — documentado acá para no asumir que un downgrade siempre es seguro.
    matchday: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False, default="scheduled")
    api_football_id: Mapped[int | None] = mapped_column(unique=True)
    external_ids: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    season: Mapped[Season] = relationship(back_populates="matches")
    result: Mapped["Result"] = relationship(back_populates="match", uselist=False)

    __table_args__ = (
        CheckConstraint(f"status IN {MATCH_STATUSES}", name="ck_matches_status"),
        CheckConstraint("home_team_id != away_team_id", name="ck_matches_distinct_teams"),
        Index("ix_matches_kickoff_at", "kickoff_at"),
    )


MATCH_OUTCOMES = ("home", "draw", "away")


class Result(Base):
    __tablename__ = "results"

    id: Mapped[uuid.UUID] = _uuid_pk()
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id"), nullable=False, unique=True)
    home_score: Mapped[int] = mapped_column(nullable=False)
    away_score: Mapped[int] = mapped_column(nullable=False)
    outcome: Mapped[str] = mapped_column(String, nullable=False)
    finalized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    match: Mapped[Match] = relationship(back_populates="result")

    __table_args__ = (
        CheckConstraint(f"outcome IN {MATCH_OUTCOMES}", name="ck_results_outcome"),
        CheckConstraint("home_score >= 0 AND away_score >= 0", name="ck_results_nonnegative_scores"),
        # Encontrado en revisión (ADR-0015): nada impedía antes un estado
        # imposible como home_score=3, away_score=0, outcome='draw'. El
        # código de ingesta siempre calculó outcome correctamente (ver
        # pipelines/ingest_historical_fixtures.py::_outcome), pero la BD por
        # sí sola no lo garantizaba — un bug en cualquier otro código que
        # escriba acá habría pasado silencioso.
        CheckConstraint(
            "(home_score > away_score AND outcome = 'home') OR "
            "(away_score > home_score AND outcome = 'away') OR "
            "(home_score = away_score AND outcome = 'draw')",
            name="ck_results_outcome_matches_score",
        ),
    )


HORIZONS = ("T-72", "T-24", "T-2")


class FeatureSnapshot(Base):
    """Valores de features congelados para una predicción específica (ADR-0007).

    Igual que `predictions` (ADR-0008): nunca se hace UPDATE sobre una fila
    existente. Si el cálculo de features cambia, se genera una fila nueva con
    otro `dataset_version`/`generated_at` — la anterior se conserva intacta.
    """

    __tablename__ = "feature_snapshots"

    id: Mapped[uuid.UUID] = _uuid_pk()
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id"), nullable=False)
    horizon: Mapped[str] = mapped_column(String, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    features: Mapped[dict] = mapped_column(JSONB, nullable=False)
    dataset_version: Mapped[str] = mapped_column(String, nullable=False, default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (CheckConstraint(f"horizon IN {HORIZONS}", name="ck_feature_snapshots_horizon"),)


ALGORITHM_FAMILIES = ("naive", "elo", "poisson_dixon_coles", "logistic", "gbm", "ensemble")
MODEL_STATUSES = ("candidate", "production", "retired")


class ModelVersion(Base):
    """Ver ADR-0006 (orden de complejidad) y ADR-0005/ADR-0013: Evaluation &
    Calibration Agent produce la recomendación de promoción, pero es el
    Orquestador quien ejecuta el cambio de `status` — Modeling nunca se
    autopromueve, y Evaluation nunca se autoejecuta."""

    __tablename__ = "model_versions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    version_tag: Mapped[str] = mapped_column(String, nullable=False)
    algorithm_family: Mapped[str] = mapped_column(String, nullable=False)
    training_dataset_version: Mapped[str] = mapped_column(String, nullable=False)
    hyperparameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String, nullable=False, default="candidate")
    # Trazabilidad barata de agregar ya (ADR-0013): permite responder "con qué
    # código exacto se entrenó esto" y "de qué versión viene" sin necesitar
    # todavía un pipeline de entrenamiento automatizado ni artifacts serializados.
    git_sha: Mapped[str | None] = mapped_column(String)
    # True si hubo cambios sin commitear al momento de entrenar (ADR-0014):
    # git_sha solo no basta para reproducibilidad si el working tree estaba sucio.
    git_dirty: Mapped[bool | None] = mapped_column()
    parent_model_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("model_versions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        CheckConstraint(f"algorithm_family IN {ALGORITHM_FAMILIES}", name="ck_model_versions_algorithm_family"),
        CheckConstraint(f"status IN {MODEL_STATUSES}", name="ck_model_versions_status"),
        UniqueConstraint("name", "version_tag"),
    )


class EvaluationMetric(Base):
    """Resultado de una corrida de evaluación (ADR-0007): versionada, nunca
    sobreescrita — cada corrida de `pipelines/evaluate_baselines.py` inserta
    filas nuevas, nunca actualiza una `evaluation_run_at` anterior.

    `segment` es texto libre en vez de columnas separadas por horizon/local-
    visitante/competición (ej. "fold=2023;split=home") porque el desglose
    "por horizonte" (docs/data/schema.md) todavía no es informativo: ninguno
    de los baselines de Fase 4 consume features sensibles a T-72/T-24/T-2
    (eso empieza en Fase 6). Agregar una columna `horizon` que siempre
    valdría lo mismo sería una columna sin uso real — se agrega cuando deje
    de serlo, no antes (mismo criterio que docs/data/schema.md aplica a
    tablas completas)."""

    __tablename__ = "evaluation_metrics"

    id: Mapped[uuid.UUID] = _uuid_pk()
    model_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("model_versions.id"), nullable=False)
    evaluation_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    segment: Mapped[str] = mapped_column(String, nullable=False)
    log_loss: Mapped[float] = mapped_column(nullable=False)
    brier_score: Mapped[float] = mapped_column(nullable=False)
    ece: Mapped[float | None] = mapped_column()
    accuracy: Mapped[float] = mapped_column(nullable=False)
    n_samples: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Player(Base):
    """Nota (Fase 6, ADR-0003): la fuente de datos NO tiene lesiones
    históricas para 2022-2024 (verificado con una llamada real, no asumido
    de la documentación). Sí tiene alineaciones titulares. Por eso esta
    tabla y `match_lineups` cubrieron, hasta que se activó el Football
    Intelligence Agent, el rol que `PlayerAvailability` (más abajo en este
    archivo) tiene ahora para status de lesión/suspensión — esa tabla existe
    desde entonces pero todavía sin datos: el agente que la puebla se activa
    en una tarea separada, esto es solo el esquema."""

    __tablename__ = "players"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    api_football_id: Mapped[int | None] = mapped_column(unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class MatchLineup(Base):
    """Un jugador que fue titular (startXI) en un partido, para un equipo.
    Permite calcular `rotation_index` (Sección 9 del brief) comparando la
    alineación de un partido contra la anterior del mismo equipo."""

    __tablename__ = "match_lineups"

    id: Mapped[uuid.UUID] = _uuid_pk()
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id"), nullable=False)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id"), nullable=False)
    position: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("match_id", "team_id", "player_id"),)


class DataSource(Base):
    """Fuente de información cualitativa consumida por el Football
    Intelligence Agent (jerarquía Nivel A-E, ver ADR-0020 para la lista
    concreta de niveles y fuentes reales). `reliability_level` queda como
    texto libre (no enum cerrado) porque la jerarquía puede ganar/perder
    fuentes sin requerir una migración cada vez — el valor esperado hoy es
    "A"-"E" según ADR-0020."""

    __tablename__ = "data_sources"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    reliability_level: Mapped[str] = mapped_column(String, nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(String)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PlayerAvailability(Base):
    """Hecho estructurado de disponibilidad de un jugador (lesión,
    suspensión, duda, rotación), producido por el Football Intelligence
    Agent y persistido acá — nunca escrito directamente por ese agente
    (ver `.claude/agents/football-intelligence.md`, "Qué NO debe hacer").

    Cinco timestamps separados, nunca colapsados en uno (Regla P0 de
    anti-leakage del mismo documento): `event_time`/`published_at` son
    metadato informativo; `available_at` es el único corte real usado por
    el feature builder (`available_at <= as_of_timestamp`), y por defecto
    es igual a `observed_at`, nunca a `published_at`. El constraint
    `ck_player_availability_available_at_after_observed_at` bloquea a
    nivel BD la violación más peligrosa: que `available_at` quede antes
    de `observed_at` (leakage retroactivo)."""

    __tablename__ = "player_availability"

    id: Mapped[uuid.UUID] = _uuid_pk()
    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id"), nullable=False)
    # Requerido (a diferencia de match_lineups, donde se infiere de la
    # alineación): players no tiene team_id propio (ver nota en Player),
    # así que acá hay que declararlo explícitamente.
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    match_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("matches.id"))
    status: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str | None] = mapped_column(String)
    confidence: Mapped[str] = mapped_column(String, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String)
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_fact: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        CheckConstraint(
            "available_at >= observed_at",
            name="ck_player_availability_available_at_after_observed_at",
        ),
    )


class NewsSignal(Base):
    """Señal contextual más amplia (cambio de DT, noticia táctica, sanción
    administrativa) no atada a la disponibilidad de un jugador puntual —
    mismo patrón de 5 timestamps y misma regla P0 de anti-leakage que
    `PlayerAvailability`, ver ese modelo para el detalle."""

    __tablename__ = "news_signals"

    id: Mapped[uuid.UUID] = _uuid_pk()
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"))
    match_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("matches.id"))
    signal_type: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String)
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_fact: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        CheckConstraint(
            "available_at >= observed_at",
            name="ck_news_signals_available_at_after_observed_at",
        ),
    )


class BookmakerSnapshot(Base):
    """Cuota 1X2 ("Match Winner") de un bookmaker para un partido, capturada
    vía el endpoint `/odds` de API-Football (ADR-0021) — solo benchmark
    externo, nunca feature del modelo de producción sin un ADR nuevo
    (CLAUDE.md regla 4 / ADR-0003 / ADR-0009).

    A diferencia de `player_availability`/`news_signals`, acá no hay una
    pareja `observed_at`/`available_at` que proteger con un CheckConstraint
    anti-leakage: `captured_at` es simplemente cuándo corrió nuestro script
    (un único valor compartido por corrida, mismo patrón que
    `ingest_intelligence_facts.py`), y `provider_updated_at` es metadato
    informativo del proveedor (`update` en la respuesta cruda) — no se usa
    como corte de disponibilidad en ningún feature builder.

    Populada bajo demanda por `pipelines/capture_odds_snapshot.py` — sin
    cadencia automatizada todavía (deliberado, ver ADR-0021: automatizar la
    captura es trabajo de Fase 7)."""

    __tablename__ = "bookmaker_snapshots"

    id: Mapped[uuid.UUID] = _uuid_pk()
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id"), nullable=False)
    bookmaker_name: Mapped[str] = mapped_column(String, nullable=False)
    odds_home: Mapped[float] = mapped_column(nullable=False)
    odds_draw: Mapped[float] = mapped_column(nullable=False)
    odds_away: Mapped[float] = mapped_column(nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_response: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("match_id", "bookmaker_name", "captured_at"),)
