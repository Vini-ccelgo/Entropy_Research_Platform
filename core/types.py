"""Immutable domain records shared by the experiment platform.

These records deliberately contain no transport, database, or UI concerns.  They
are the stable vocabulary exchanged through the application's ports.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
import json
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)


class FrozenModel(BaseModel):
    """Strict, immutable base model for persisted domain values."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, ser_json_bytes="base64", val_json_bytes="base64"
    )


class TrialStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ObserverKind(StrEnum):
    HUMAN = "human"
    AUTOMATED = "automated"
    SYSTEM = "system"


class HypothesisStatus(StrEnum):
    DRAFT = "draft"
    REGISTERED = "registered"
    RETIRED = "retired"


class CriterionKind(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    EXCLUSION = "exclusion"
    STOPPING = "stopping"


class EntropyApplicationPolicy(StrEnum):
    """Supported, auditable ways an entropy sample may affect a trial."""

    DERIVE_MODEL_SEED = "derive_model_seed"


class Observer(FrozenModel):
    """An accountable human or automated agent that makes an observation."""

    id: UUID = Field(default_factory=uuid4)
    display_name: str = Field(min_length=1, max_length=160)
    kind: ObserverKind
    affiliation: str | None = None
    protocol_version: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class Prediction(FrozenModel):
    statement: str = Field(min_length=1)
    measurement: str = Field(min_length=1)


class EvaluationCriterion(FrozenModel):
    kind: CriterionKind
    statement: str = Field(min_length=1)


class AlternativeExplanation(FrozenModel):
    statement: str = Field(min_length=1)
    discrimination_plan: str = Field(min_length=1)


class HypothesisSpecification(FrozenModel):
    """Predictions, criteria, and alternatives for a hypothesis revision."""

    predictions: tuple[Prediction, ...] = ()
    criteria: tuple[EvaluationCriterion, ...] = ()
    alternatives: tuple[AlternativeExplanation, ...] = ()


class HypothesisReference(FrozenModel):
    """Pins an experiment to a precise hypothesis revision."""

    hypothesis_id: UUID
    revision: int = Field(ge=1)
    content_hash: str = Field(min_length=64, max_length=64)


class Hypothesis(FrozenModel):
    """A versioned, preregisterable claim tested by one or more experiments."""

    id: UUID = Field(default_factory=uuid4)
    revision: int = Field(default=1, ge=1)
    predecessor: HypothesisReference | None = None
    title: str = Field(min_length=1, max_length=240)
    statement: str = Field(min_length=1)
    null_statement: str | None = None
    success_criteria: str = Field(min_length=1)
    registered_by: UUID
    status: HypothesisStatus = HypothesisStatus.DRAFT
    created_at: datetime = Field(default_factory=utc_now)
    specification: HypothesisSpecification | None = None

    def content_hash(self) -> str:
        """Return a stable digest of the scientific claim, excluding identity."""
        payload = self.model_dump(
            mode="json", exclude={"id", "revision", "created_at", "status"}
        )
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class PromptTemplate(FrozenModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,127}$")
    version: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=100)
    goal: str = Field(min_length=1)
    template: str = Field(min_length=1)
    verification_type: str = Field(default="none")
    tags: tuple[str, ...] = ()


class RenderedPrompt(FrozenModel):
    template_id: str
    template_version: str
    text: str
    variables: dict[str, str] = Field(default_factory=dict)
    rendered_at: datetime = Field(default_factory=utc_now)


class EntropyRequest(FrozenModel):
    """Describes how an entropy sample will be consumed, before sampling."""

    purpose: str = Field(min_length=1)
    bytes_required: int = Field(default=32, ge=1, le=1_048_576)
    application_policy: EntropyApplicationPolicy


class EntropySample(FrozenModel):
    source: str
    raw_bytes: bytes = Field(default=b"", exclude=True, repr=False)
    value_hash: str
    collected_at: datetime = Field(default_factory=utc_now)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @field_validator("value_hash")
    @classmethod
    def require_sha256(cls, value: str) -> str:
        if len(value) != 64:
            raise ValueError("value_hash must be a SHA-256 hexadecimal digest")
        return value


class ModelRequest(FrozenModel):
    provider: str
    model_identifier: str
    prompt: RenderedPrompt
    temperature: float = Field(ge=0, le=2)
    top_p: float = Field(gt=0, le=1)
    top_k: int | None = Field(default=None, ge=1)
    repeat_penalty: float | None = Field(default=None, gt=0)
    max_tokens: int | None = Field(default=None, ge=1)
    seed: int | None = Field(default=None, ge=0)


class ModelResponse(FrozenModel):
    text: str
    provider: str
    model_identifier: str
    latency_ms: float = Field(ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    stop_reason: str | None = None
    backend_metadata: dict[str, Any] = Field(default_factory=dict)


class TrialSpec(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    ordinal: int = Field(ge=1)
    prompt: PromptTemplate
    prompt_variables: dict[str, str] = Field(default_factory=dict)
    model_provider: str
    model_identifier: str
    entropy: EntropyRequest
    entropy_policy: "EntropyPolicyReference"
    temperature: float = Field(default=0.7, ge=0, le=2)
    top_p: float = Field(default=0.95, gt=0, le=1)
    top_k: int | None = Field(default=None, ge=1)
    repeat_penalty: float | None = Field(default=None, gt=0)
    max_tokens: int | None = Field(default=None, ge=1)


class ExperimentPlan(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=240)
    description: str = ""
    hypothesis: HypothesisReference
    observers: tuple[Observer, ...] = Field(min_length=1)
    trials: tuple[TrialSpec, ...] = Field(min_length=1)
    schema_version: int = Field(default=1, ge=1)
    git_commit: str | None = None
    created_at: datetime = Field(default_factory=utc_now)

    def config_hash(self) -> str:
        """Return a hash of the canonical reproducibility plan."""
        canonical = json.dumps(
            self.model_dump(mode="json", exclude={"id", "created_at"}),
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(canonical.encode()).hexdigest()


class TrialResult(FrozenModel):
    trial_id: UUID
    experiment_id: UUID
    status: TrialStatus
    rendered_prompt: RenderedPrompt | None = None
    entropy: EntropySample | None = None
    request: ModelRequest | None = None
    response: ModelResponse | None = None
    error: str | None = None
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None


class Observation(FrozenModel):
    """A human or automated assessment, attributed to an Observer."""

    id: UUID = Field(default_factory=uuid4)
    trial_id: UUID
    observer_id: UUID
    rating: float | None = None
    interesting: bool | None = None
    tags: tuple[str, ...] = ()
    notes: str | None = None
    recorded_at: datetime = Field(default_factory=utc_now)

from entropy.policy import EntropyPolicyReference
TrialSpec.model_rebuild()
