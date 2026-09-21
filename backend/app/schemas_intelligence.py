"""Contrato JSON producido por el Football Intelligence Agent (ADR-0020,
`.claude/agents/football-intelligence.md`). Estos modelos validan la forma
del JSON *antes* de que `pipelines/ingest_intelligence_facts.py` lo toque —
son la frontera determinista entre "extracción vía LLM" y "persistencia con
reglas fijas" que ese agente describe en su propia definición ("No escribe
directamente en la base de datos").

Deliberadamente NO incluyen `observed_at` ni `available_at`: esos dos
timestamps son anti-leakage-críticos (Regla P0 del agente) y el pipeline de
persistencia los estampa él mismo con `datetime.now(timezone.utc)` al momento
de la corrida — nunca un valor que venga del JSON. Si el JSON de entrada
trajera esas claves igual se ignorarían: no forman parte de este schema, así
que Pydantic ni las parsea.
"""

from datetime import datetime
from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

PlayerAvailabilityStatus = Literal["unavailable", "doubtful", "available", "rotation_risk"]
PlayerAvailabilityReason = Literal["muscle_injury", "suspension", "rotation", "personal", "unknown"] | None
NewsSignalType = Literal["coaching_change", "tactical_news", "suspension_admin", "other"]
SourceType = Literal[
    "official_club",
    "official_federation",
    "credentialed_journalist",
    "established_outlet",
    "aggregator",
    "social_media",
    "unverified",
]
ReliabilityLevel = Literal["A", "B", "C", "D", "E"]


class _FactBase(BaseModel):
    """Campos de trazabilidad de fuente comunes a ambos tipos de hecho.
    `raw_quote` es obligatorio y no puede ser vacío — es el rastro de
    auditoría de todo el hecho, no un campo opcional de conveniencia.

    **`raw_quote` debe ser estrictamente textual, nunca mezclado con
    razonamiento del agente** (hallazgo de auditoría QA, primera corrida
    2026-09-21: 2/14 hechos traían una cita real seguida de una nota propia
    del agente tipo "— nota: no clasifica limpiamente en..."; el dato
    subyacente era correcto pero contaminaba el campo pensado para ser
    100% verbatim). Ese tipo de razonamiento sobre ambigüedad de categoría
    va en `extraction_note`, un campo separado para exactamente eso."""

    model_config = ConfigDict(extra="ignore")  # ignora observed_at/available_at si vinieran, y cualquier otra clave inesperada

    source_name: str = Field(min_length=1)
    source_type: SourceType
    reliability_level: ReliabilityLevel
    source_url: str | None = None
    event_time: datetime | None = None
    published_at: datetime | None = None
    raw_quote: str = Field(min_length=1)
    extraction_note: str | None = None


class PlayerAvailabilityFact(_FactBase):
    fact_type: Literal["player_availability"]
    match_id: UUID
    team_name: str = Field(min_length=1)
    player_name: str = Field(min_length=1)
    status: PlayerAvailabilityStatus
    reason: PlayerAvailabilityReason = None


class NewsSignalFact(_FactBase):
    fact_type: Literal["news_signal"]
    match_id: UUID | None = None
    team_name: str | None = None
    signal_type: NewsSignalType
    description: str = Field(min_length=1)


Fact = Annotated[Union[PlayerAvailabilityFact, NewsSignalFact], Field(discriminator="fact_type")]


class UnresolvedContradiction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    description: str
    sources: list[str] = Field(default_factory=list)


class IntelligenceFactsEnvelope(BaseModel):
    """Modelo raíz del JSON completo que produce el agente."""

    model_config = ConfigDict(extra="ignore")

    facts: list[Fact] = Field(default_factory=list)
    unresolved_contradictions: list[UnresolvedContradiction] = Field(default_factory=list)
    matches_with_insufficient_information: list[str] = Field(default_factory=list)
