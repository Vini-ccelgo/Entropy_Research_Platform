"""Immutable registered inputs used by experiment revisions.

These are deliberately narrow records, rather than a generic configuration
system: a source condition and a prompt are both scientific inputs whose exact
identity must remain resolvable after the process that registered them exits.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from core.types import FrozenModel, utc_now


def canonical_hash(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


_SENSITIVE = re.compile(r"(secret|password|token|api[_-]?key|credential)", re.I)


def redact_configuration(value: Any, key: str = "") -> Any:
    """Reject persisted secrets; credential values may only be environment references."""
    if isinstance(value, dict):
        return {str(k): redact_configuration(v, str(k)) for k, v in value.items()}
    if _SENSITIVE.search(key):
        if not (isinstance(value, str) and value.startswith("$env:")):
            raise ValueError(f"sensitive configuration {key!r} must be a $env: reference")
    return value


class EntropySourceType(StrEnum):
    DETERMINISTIC_PRNG = "deterministic_prng"
    OS_ENTROPY = "os_entropy"
    HARDWARE_ENTROPY = "hardware_entropy"
    QRNG = "qrng"


class EntropySourceSpecification(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    revision: int = Field(default=1, ge=1)
    predecessor: "EntropySourceReference | None" = None
    implementation_identity: str = Field(min_length=1)
    implementation_version: str = Field(min_length=1)
    source_type: EntropySourceType
    configuration: dict[str, Any] = Field(default_factory=dict)
    declared_capabilities: dict[str, int | bool | str] = Field(default_factory=dict)
    created_by: UUID
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("configuration")
    @classmethod
    def _redact(cls, value: dict[str, Any]) -> dict[str, Any]:
        return redact_configuration(value)

    def content_hash(self) -> str:
        return canonical_hash(self.model_dump(mode="json", exclude={"id", "revision", "created_at"}))


class EntropySourceReference(FrozenModel):
    source_id: UUID
    revision: int = Field(ge=1)
    content_hash: str = Field(min_length=64, max_length=64)


class PromptRevision(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    revision: int = Field(default=1, ge=1)
    predecessor: "PromptRevisionReference | None" = None
    category: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    content: str = Field(min_length=1)
    role: str = "user"
    system_prompt: str | None = None
    variable_schema: tuple[str, ...] = ()
    rendering_rules: str = "python-format-v1; missing variables are invalid"
    metadata: dict[str, str] = Field(default_factory=dict)
    tags: tuple[str, ...] = ()
    created_by: UUID
    created_at: datetime = Field(default_factory=utc_now)

    def content_hash(self) -> str:
        return canonical_hash(self.model_dump(mode="json", exclude={"id", "revision", "created_at"}))


class PromptRevisionReference(FrozenModel):
    prompt_id: UUID
    revision: int = Field(ge=1)
    content_hash: str = Field(min_length=64, max_length=64)


class PromptSetRevision(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    revision: int = Field(default=1, ge=1)
    predecessor: "PromptSetReference | None" = None
    prompts: tuple[PromptRevisionReference, ...] = Field(min_length=1)
    allocation_metadata: dict[str, str] = Field(default_factory=dict)
    created_by: UUID
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _unique_ordered(self) -> "PromptSetRevision":
        if len({(p.prompt_id, p.revision) for p in self.prompts}) != len(self.prompts):
            raise ValueError("a prompt set cannot contain a prompt revision more than once")
        return self

    def content_hash(self) -> str:
        return canonical_hash(self.model_dump(mode="json", exclude={"id", "revision", "created_at"}))


class PromptSetReference(FrozenModel):
    prompt_set_id: UUID
    revision: int = Field(ge=1)
    content_hash: str = Field(min_length=64, max_length=64)


class RegisteredInputRepositoryPort:
    """Narrow durable port; implementations must atomically append audit evidence."""
    def register_entropy_source(self, spec: EntropySourceSpecification) -> EntropySourceReference: raise NotImplementedError
    def resolve_entropy_source(self, ref: EntropySourceReference) -> EntropySourceSpecification: raise NotImplementedError
    def register_prompt(self, prompt: PromptRevision) -> PromptRevisionReference: raise NotImplementedError
    def resolve_prompt(self, ref: PromptRevisionReference) -> PromptRevision: raise NotImplementedError
    def register_prompt_set(self, prompt_set: PromptSetRevision) -> PromptSetReference: raise NotImplementedError
    def resolve_prompt_set(self, ref: PromptSetReference) -> PromptSetRevision: raise NotImplementedError


EntropySourceSpecification.model_rebuild()
PromptRevision.model_rebuild()
PromptSetRevision.model_rebuild()
