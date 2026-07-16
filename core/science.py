"""Revisioned scientific-record domain models for Milestone 0.

These records preserve the reasoning around experiments.  They intentionally do
not execute experiments, calculate analyses, or render a dashboard.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from uuid import UUID, uuid4

from pydantic import Field, HttpUrl, field_validator

from core.types import (
    ExperimentPlan, FrozenModel, HypothesisSpecification, ObserverKind, utc_now,
)


def _content_hash(value: FrozenModel, excluded: set[str]) -> str:
    payload = value.model_dump(mode="json", exclude=excluded)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode()).hexdigest()


class ScientificRecordType(StrEnum):
    RESEARCH_QUESTION = "research_question"
    HYPOTHESIS = "hypothesis"
    JOURNAL_ENTRY = "journal_entry"
    CLAIM = "claim"
    EXTERNAL_REFERENCE = "external_reference"
    EXPERIMENT = "experiment"
    TRIAL = "trial"
    ANALYSIS = "analysis"
    OBSERVATION = "observation"


class RelationType(StrEnum):
    MOTIVATES = "motivates"
    TESTS = "tests"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    REVISES = "revises"
    SUPERSEDES = "supersedes"
    DERIVED_FROM = "derived_from"
    USES = "uses"
    INTERPRETS = "interprets"


class AuditAction(StrEnum):
    REGISTERED = "registered"
    RELATION_RECORDED = "relation_recorded"
    BELIEF_ASSESSED = "belief_assessed"
    STATUS_CHANGED = "status_changed"


class JournalEntryType(StrEnum):
    IDEA = "idea"
    RATIONALE = "rationale"
    DECISION = "decision"
    PROTOCOL_CHANGE = "protocol_change"
    LITERATURE_NOTE = "literature_note"
    RESULT_INTERPRETATION = "result_interpretation"
    RETROSPECTIVE = "retrospective"


class ClaimKind(StrEnum):
    DESCRIPTIVE = "descriptive"
    INTERPRETIVE = "interpretive"
    METHODOLOGICAL = "methodological"


class ScientificRecordReference(FrozenModel):
    """Pins a link to a specific immutable record revision."""

    record_type: ScientificRecordType
    record_id: UUID
    revision: int = Field(ge=1)
    content_hash: str = Field(min_length=64, max_length=64)


class RevisionedScientificRecord(FrozenModel):
    """Immutable, attributable record revision with pinned predecessor lineage."""

    id: UUID = Field(default_factory=uuid4)
    revision: int = Field(default=1, ge=1)
    predecessor: ScientificRecordReference | None = None
    created_by: UUID
    created_at: datetime = Field(default_factory=utc_now)

    @property
    def record_type(self) -> ScientificRecordType:
        raise NotImplementedError

    def content_hash(self) -> str:
        return _content_hash(self, {"id", "revision", "created_at"})

    def reference(self) -> ScientificRecordReference:
        return ScientificRecordReference(
            record_type=self.record_type,
            record_id=self.id,
            revision=self.revision,
            content_hash=self.content_hash(),
        )


class ResearchQuestion(RevisionedScientificRecord):
    question: str = Field(min_length=1)
    rationale: str = Field(min_length=1)

    @property
    def record_type(self) -> ScientificRecordType:
        return ScientificRecordType.RESEARCH_QUESTION


class JournalEntry(RevisionedScientificRecord):
    entry_type: JournalEntryType
    title: str = Field(min_length=1, max_length=240)
    body: str = Field(min_length=1)

    @property
    def record_type(self) -> ScientificRecordType:
        return ScientificRecordType.JOURNAL_ENTRY


class Claim(RevisionedScientificRecord):
    kind: ClaimKind
    statement: str = Field(min_length=1)

    @property
    def record_type(self) -> ScientificRecordType:
        return ScientificRecordType.CLAIM


class ExternalReference(RevisionedScientificRecord):
    title: str = Field(min_length=1, max_length=500)
    locator: HttpUrl
    retrieved_at: datetime = Field(default_factory=utc_now)
    content_hash_at_retrieval: str | None = Field(default=None, min_length=64, max_length=64)

    @property
    def record_type(self) -> ScientificRecordType:
        return ScientificRecordType.EXTERNAL_REFERENCE


class ExperimentRevision(RevisionedScientificRecord):
    """The registered, immutable experiment definition that trials execute."""

    name: str = Field(min_length=1, max_length=240)
    description: str = ""
    plan: ExperimentPlan

    @property
    def record_type(self) -> ScientificRecordType:
        return ScientificRecordType.EXPERIMENT

    @classmethod
    def from_plan(cls, plan: ExperimentPlan, created_by: UUID) -> "ExperimentRevision":
        """Promote an in-memory construction plan to its first registered revision."""
        return cls(
            id=plan.id, name=plan.name, description=plan.description,
            plan=plan, created_by=created_by,
        )


class ScientificRelation(FrozenModel):
    """A typed, attributable, revision-pinned relationship between records."""

    id: UUID = Field(default_factory=uuid4)
    source: ScientificRecordReference
    relation_type: RelationType
    target: ScientificRecordReference
    rationale: str = Field(min_length=1)
    asserted_by: UUID
    asserted_at: datetime = Field(default_factory=utc_now)

    @field_validator("target")
    @classmethod
    def forbid_self_relation(cls, target: ScientificRecordReference, info):
        source = info.data.get("source")
        if source and source.record_type == target.record_type and source.record_id == target.record_id and source.revision == target.revision:
            raise ValueError("a record revision cannot relate to itself")
        return target


class BeliefAssessment(FrozenModel):
    """An attributed assessment; confidence is never mutable hypothesis state."""

    id: UUID = Field(default_factory=uuid4)
    hypothesis: ScientificRecordReference
    observer_id: UUID
    observer_kind: ObserverKind
    confidence: float = Field(ge=0, le=1)
    method: str = Field(min_length=1)
    basis: tuple[ScientificRecordReference, ...] = Field(min_length=1)
    assessed_at: datetime = Field(default_factory=utc_now)

    @field_validator("hypothesis")
    @classmethod
    def require_hypothesis(cls, reference: ScientificRecordReference) -> ScientificRecordReference:
        if reference.record_type is not ScientificRecordType.HYPOTHESIS:
            raise ValueError("belief assessments must reference a hypothesis revision")
        return reference


class AuditEvent(FrozenModel):
    """Append-only trace of a scientific-record mutation or registration."""

    id: UUID = Field(default_factory=uuid4)
    action: AuditAction
    subject: ScientificRecordReference | None = None
    actor_id: UUID
    occurred_at: datetime = Field(default_factory=utc_now)
    details: dict[str, str] = Field(default_factory=dict)
