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

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessage(FrozenModel):
    """An exact, role-bound message sent to a chat-completion provider."""
    role: ChatRole
    content: str = Field(min_length=1)
    content_hash: str | None = None

    def model_post_init(self, __context: Any) -> None:
        digest = sha256(json.dumps({"role": self.role.value, "content": self.content}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if self.content_hash is not None and self.content_hash != digest:
            raise ValueError("chat-message content hash does not match role and content")
        object.__setattr__(self, "content_hash", digest)


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
    messages: tuple[ChatMessage, ...] = ()
    temperature: float = Field(ge=0, le=2)
    top_p: float = Field(gt=0, le=1)
    top_k: int | None = Field(default=None, ge=1)
    repeat_penalty: float | None = Field(default=None, gt=0)
    max_tokens: int | None = Field(default=None, ge=1)
    seed: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _canonical_messages(self) -> "ModelRequest":
        messages = self.messages or (ChatMessage(role=ChatRole.USER, content=self.prompt.text),)
        if messages[0].role is ChatRole.ASSISTANT:
            raise ValueError("a chat request cannot begin with an assistant message")
        if any(message.role is ChatRole.SYSTEM for message in messages[1:]):
            raise ValueError("system messages may only be the fixed leading message")
        object.__setattr__(self, "messages", messages)
        return self


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
    # ``prompt`` is retained only to read pre-registration plans.  Registered
    # experiments use ``prompt_revision`` as their authoritative prompt input.
    prompt: PromptTemplate | None = None
    prompt_revision: "PromptRevisionReference | None" = None
    prompt_variables: dict[str, str] = Field(default_factory=dict)
    model_provider: str
    model_identifier: str
    entropy: EntropyRequest
    entropy_policy: "EntropyPolicyReference"
    entropy_source: "EntropySourceReference | None" = None
    condition_id: str | None = Field(default=None, min_length=1, max_length=120)
    slot_id: str | None = Field(default=None, min_length=1, max_length=160)
    conversation: "ConversationTurnPlan | None" = None
    temperature: float = Field(default=0.7, ge=0, le=2)
    top_p: float = Field(default=0.95, gt=0, le=1)
    top_k: int | None = Field(default=None, ge=1)
    repeat_penalty: float | None = Field(default=None, gt=0)
    max_tokens: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _registered_prompt_or_legacy_template(self) -> "TrialSpec":
        if self.prompt is None and self.prompt_revision is None:
            raise ValueError("a trial must pin a prompt revision")
        return self


class ExperimentCondition(FrozenModel):
    """A pinned entropy condition within one immutable experiment revision."""
    condition_id: str = Field(min_length=1, max_length=120)
    label: str = Field(min_length=1, max_length=240)
    blinded_label: str | None = Field(default=None, min_length=1, max_length=120)
    entropy_source: "EntropySourceReference"
    entropy_policy: "EntropyPolicyReference"
    planned_allocation_count: int = Field(ge=1)

    def content_hash(self) -> str:
        payload = self.model_dump(mode="json")
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class ConversationTurnPlan(FrozenModel):
    """Fixed, non-agentic plan for one turn of a declared trajectory."""
    trajectory_id: str = Field(min_length=1, max_length=160)
    turn_index: int = Field(ge=1, le=6)
    parent_slot_id: str | None = None
    instruction_prompt: "PromptRevisionReference"
    condition_id: str = Field(min_length=1, max_length=120)
    context_policy: str = "reject_if_exceeds_budget"
    context_window_budget: int = Field(ge=1)
    reconstruction_version: str = "conversation-v1"

    @model_validator(mode="after")
    def _parent_rule(self) -> "ConversationTurnPlan":
        if self.context_policy != "reject_if_exceeds_budget":
            raise ValueError("only reject_if_exceeds_budget is approved")
        if (self.turn_index == 1) != (self.parent_slot_id is None):
            raise ValueError("only the first conversation turn may omit a parent slot")
        return self

    def content_hash(self) -> str:
        return sha256(json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class ExperimentPlan(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=240)
    description: str = ""
    hypothesis: HypothesisReference
    observers: tuple[Observer, ...] = Field(min_length=1)
    trials: tuple[TrialSpec, ...] = Field(min_length=1)
    prompt_set: "PromptSetReference | None" = None
    conditions: tuple[ExperimentCondition, ...] = ()
    assignment_strategy: str | None = None
    assignment_seed: int | None = None
    assignment_hash: str | None = Field(default=None, min_length=64, max_length=64)
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

    @model_validator(mode="after")
    def _validate_conditioned_plan(self) -> "ExperimentPlan":
        # Legacy construction DTOs are accepted so old records remain readable.
        # A plan using registered conditions is held to the MVP invariants.
        if not self.conditions:
            return self
        ids = [condition.condition_id for condition in self.conditions]
        if len(ids) != len(set(ids)):
            raise ValueError("condition IDs must be unique within an experiment")
        if self.prompt_set is None or not self.assignment_strategy or not self.assignment_hash:
            raise ValueError("conditioned experiments require a prompt set and assignment provenance")
        deterministic = [c for c in self.conditions if c.condition_id.lower().startswith("control")]
        if len(deterministic) != 1:
            raise ValueError("MVP experiments require exactly one deterministic-control condition")
        if not any(c.condition_id.lower() != deterministic[0].condition_id.lower() for c in self.conditions):
            raise ValueError("MVP experiments require at least one physical-entropy condition")
        if sum(c.planned_allocation_count for c in self.conditions) != len(self.trials):
            raise ValueError("condition allocations must equal planned trial count")
        by_condition = {condition.condition_id: condition for condition in self.conditions}
        if any(t.condition_id not in by_condition or t.slot_id is None for t in self.trials):
            raise ValueError("every conditioned trial requires a known condition and immutable slot")
        if len({t.slot_id for t in self.trials}) != len(self.trials):
            raise ValueError("planned trial slots must be unique")
        for trial in self.trials:
            condition = by_condition[trial.condition_id]
            if trial.entropy_source != condition.entropy_source or trial.entropy_policy != condition.entropy_policy:
                raise ValueError("trials must pin the source and policy resolved through their condition")
            if trial.conversation and (trial.conversation.condition_id != trial.condition_id or trial.conversation.instruction_prompt != trial.prompt_revision):
                raise ValueError("conversation turn must pin its condition and instruction prompt")
        trajectories: dict[str, list[TrialSpec]] = {}
        for trial in self.trials:
            if trial.conversation:
                trajectories.setdefault(trial.conversation.trajectory_id, []).append(trial)
        for turns in trajectories.values():
            ordered = sorted(turns, key=lambda trial: trial.conversation.turn_index)
            if [trial.conversation.turn_index for trial in ordered] != list(range(1, len(ordered) + 1)):
                raise ValueError("conversation trajectory turn indexes must be contiguous from one")
            if len({trial.condition_id for trial in ordered}) != 1:
                raise ValueError("a conversation trajectory must retain one entropy condition")
        return self


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
from core.registries import EntropySourceReference, PromptRevisionReference, PromptSetReference
TrialSpec.model_rebuild()
ExperimentCondition.model_rebuild()
ConversationTurnPlan.model_rebuild()
ExperimentPlan.model_rebuild()
