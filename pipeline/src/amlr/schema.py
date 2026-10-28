"""Harmonized record / decision / extraction schema.

Paper records with PRISMA-specific fields.
Pydantic v2 is used so JSONL round-trips are strict and typed.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PrismaPhase(str, Enum):
    identified = "identified"
    duplicate = "duplicate"
    screened_in = "screened_in"
    screened_out = "screened_out"
    fulltext_sought = "fulltext_sought"
    fulltext_not_retrieved = "fulltext_not_retrieved"
    assessed = "assessed"
    excluded_eligibility = "excluded_eligibility"
    included = "included"


class Stage(str, Enum):
    title_abstract = "title_abstract"
    full_text = "full_text"


class Decision(BaseModel):
    """One screening or eligibility vote from one reviewer (human or LLM)."""

    model_config = ConfigDict(extra="forbid")

    reviewer: str
    stage: Stage
    include: bool
    reason: str | None = None
    at: date
    model: str | None = None
    prompt_sha256: str | None = None
    confidence: float | None = None
    rationale: str | None = None


class Record(BaseModel):
    """A corpus record."""

    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    publisher: str | None = None
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    arxiv_id: str | None = None
    source_ids: dict[str, str] = Field(default_factory=dict)
    source_query: str | None = None
    access_route: str | None = None
    license: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    local_pdf_path: str | None = None
    checksum: str | None = None
    byte_count: int | None = None
    acquisition_status: str = "pending"
    failure_reason: str | None = None

    phase: PrismaPhase = PrismaPhase.identified
    decisions: list[Decision] = Field(default_factory=list)

    extraction: dict[str, Any] = Field(default_factory=dict)


class Extraction(BaseModel):
    """Structured data items extracted from an included study's full text."""

    model_config = ConfigDict(extra="forbid")

    record_id: str
    platform: str | None = None
    agents: int | None = None
    control_architecture: str | None = None
    interaction_modality: str | None = None
    environment: str | None = None
    phases_observed: list[str] = Field(default_factory=list)
    model_class: str | None = None
    code_available: bool | None = None
    data_available: bool | None = None
    notes: str | None = None
