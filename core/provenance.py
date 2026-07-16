"""Immutable execution provenance records for the reproducibility contract."""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from pydantic import Field

from core.science import ScientificRecordReference, ScientificRecordType
from core.types import (
    EntropySample, FrozenModel, ModelRequest, ModelResponse, RenderedPrompt,
    TrialStatus, utc_now,
)


def canonical_hash(value: Any) -> str:
    """Hash a JSON-compatible value with a stable canonical representation."""
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(payload.encode()).hexdigest()


class ArtifactAvailability(StrEnum):
    AVAILABLE = "available"
    OMITTED_BY_POLICY = "omitted_by_policy"
    UNAVAILABLE = "unavailable"


class ArtifactRole(StrEnum):
    ENTROPY_RAW_BYTES = "entropy_raw_bytes"
    PROVIDER_REQUEST = "provider_request"
    PROVIDER_RESPONSE = "provider_response"
    RESPONSE_TEXT = "response_text"
    MODEL_ARTIFACT = "model_artifact"
    DEPENDENCY_MANIFEST = "dependency_manifest"
    EXPERIMENT_DEFINITION = "experiment_definition"


class ArtifactManifestEntry(FrozenModel):
    """A digest-addressed artifact, or an explicit record of why it is absent."""

    role: ArtifactRole
    availability: ArtifactAvailability
    content_hash: str | None = Field(default=None, min_length=64, max_length=64)
    media_type: str | None = None
    locator: str | None = None
    omission_reason: str | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.availability is ArtifactAvailability.AVAILABLE and not self.content_hash:
            raise ValueError("available artifacts require a content hash")
        if self.availability is not ArtifactAvailability.AVAILABLE and not self.omission_reason:
            raise ValueError("unavailable artifacts require an omission reason")


class PromptSnapshot(FrozenModel):
    template_id: str
    template_version: str
    template_hash: str
    rendered_hash: str
    rendered_prompt: RenderedPrompt


class EntropySourceSnapshot(FrozenModel):
    source_type: str
    source_name: str
    configuration: dict[str, Any] = Field(default_factory=dict)
    configuration_hash: str
    conditioning_method: str = "source_native"
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


class ModelSnapshot(FrozenModel):
    provider: str
    model_identifier: str
    model_artifact_hash: str
    quantization: str | None = None
    tokenizer_hash: str | None = None
    chat_template_hash: str | None = None
    context_size: int | None = Field(default=None, ge=1)
    provider_capabilities: dict[str, Any] = Field(default_factory=dict)
    provider_configuration: dict[str, Any] = Field(default_factory=dict)
    provider_configuration_hash: str
    model_artifact_locator: str | None = None


class RuntimeSnapshot(FrozenModel):
    operating_system: str
    operating_system_version: str
    architecture: str
    python_version: str
    runtime_name: str
    runtime_version: str
    hardware: dict[str, str] = Field(default_factory=dict)
    configuration: dict[str, Any] = Field(default_factory=dict)


class SoftwareSnapshot(FrozenModel):
    application_version: str
    git_commit: str | None = None
    git_dirty: bool | None = None
    dependency_manifest_hash: str
    dependency_manifest_locator: str | None = None
    source_tree_hash: str | None = None


class ExecutionProvenance(FrozenModel):
    experiment_revision: ScientificRecordReference
    prompt: PromptSnapshot | None = None
    entropy_source: EntropySourceSnapshot | None = None
    model: ModelSnapshot | None = None
    runtime: RuntimeSnapshot | None = None
    software: SoftwareSnapshot | None = None
    artifacts: tuple[ArtifactManifestEntry, ...]
    unavailable_components: dict[str, str] = Field(default_factory=dict)
    captured_at: datetime = Field(default_factory=utc_now)

    def model_post_init(self, __context: Any) -> None:
        if self.experiment_revision.record_type is not ScientificRecordType.EXPERIMENT:
            raise ValueError("execution provenance must pin an experiment revision")


class TrialExecution(FrozenModel):
    """An immutable, terminal record of one attempted trial execution."""

    id: UUID = Field(default_factory=uuid4)
    experiment_run_id: UUID
    trial_attempt_id: UUID
    attempt_number: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1)
    trial_spec_id: UUID
    status: TrialStatus
    provenance: ExecutionProvenance
    entropy: EntropySample | None = None
    entropy_application: "EntropyApplication | None" = None
    request: ModelRequest | None = None
    response: ModelResponse | None = None
    error: str | None = None
    failure_category: str | None = None
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None

from entropy.policy import EntropyApplication
TrialExecution.model_rebuild()
