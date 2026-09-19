"""Modelos SQLAlchemy para las tablas núcleo necesarias en Fase 2.

Solo cubre competitions/seasons/teams/matches/results (ver docs/roadmap/ROADMAP.md
Fase 2). El resto del esquema de docs/data/schema.md (player_availability,
news_signals, model_versions, predictions, etc.) se agrega en las fases que
realmente las necesitan, no de antemano.
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
    matchday: Mapped[int | None] = mapped_column()
    status: Mapped[str] = mapped_column(String, nullable=False, default="scheduled")
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
    )
