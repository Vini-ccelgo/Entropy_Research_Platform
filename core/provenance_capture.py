"""Deterministic helpers for constructing execution provenance snapshots."""

from __future__ import annotations

import platform
import sys
from pathlib import Path

from core.provenance import (
    ArtifactAvailability, ArtifactManifestEntry, ArtifactRole, PromptSnapshot,
    RuntimeSnapshot, SoftwareSnapshot, canonical_hash,
)
from core.types import ModelRequest, ModelResponse, PromptTemplate, RenderedPrompt


def capture_runtime_snapshot() -> RuntimeSnapshot:
    return RuntimeSnapshot(
        operating_system=platform.system(), operating_system_version=platform.version(),
        architecture=platform.machine(), python_version=sys.version,
        runtime_name=platform.python_implementation(), runtime_version=platform.python_version(),
        hardware={"processor": platform.processor() or "unavailable"},
    )


def capture_software_snapshot(application_version: str, dependency_manifest: Path,
                              git_commit: str | None = None, git_dirty: bool | None = None,
                              source_tree_hash: str | None = None) -> SoftwareSnapshot:
    return SoftwareSnapshot(
        application_version=application_version, git_commit=git_commit, git_dirty=git_dirty,
        dependency_manifest_hash=canonical_hash(dependency_manifest.read_text(encoding="utf-8")),
        dependency_manifest_locator=str(dependency_manifest),
        source_tree_hash=source_tree_hash,
    )


def snapshot_prompt(template: PromptTemplate, rendered: RenderedPrompt) -> PromptSnapshot:
    return PromptSnapshot(
        template_id=template.id, template_version=template.version,
        template_hash=canonical_hash(template.model_dump(mode="json")),
        rendered_hash=canonical_hash(rendered.model_dump(mode="json")), rendered_prompt=rendered,
    )


def execution_artifacts(request: ModelRequest | None, response: ModelResponse | None,
                         entropy_hash: str | None, model, software, experiment_hash: str) -> tuple[ArtifactManifestEntry, ...]:
    entries = [ArtifactManifestEntry(
        role=ArtifactRole.ENTROPY_RAW_BYTES,
        availability=ArtifactAvailability.OMITTED_BY_POLICY if entropy_hash else ArtifactAvailability.UNAVAILABLE,
        content_hash=entropy_hash,
        omission_reason=("Raw entropy retention is disabled by policy." if entropy_hash
                         else "Entropy sampling did not complete."),
    )]
    if request is not None:
        entries.append(ArtifactManifestEntry(
            role=ArtifactRole.PROVIDER_REQUEST, availability=ArtifactAvailability.AVAILABLE,
            content_hash=canonical_hash(request.model_dump(mode="json")), media_type="application/json",
            locator="embedded:trial_execution.request",
        ))
    else:
        entries.append(ArtifactManifestEntry(
            role=ArtifactRole.PROVIDER_REQUEST, availability=ArtifactAvailability.UNAVAILABLE,
            omission_reason="Model request was not constructed.",
        ))
    if response is not None:
        entries.extend((
            ArtifactManifestEntry(
                role=ArtifactRole.PROVIDER_RESPONSE, availability=ArtifactAvailability.AVAILABLE,
                content_hash=canonical_hash(response.model_dump(mode="json")), media_type="application/json",
                locator="embedded:trial_execution.response",
            ),
            ArtifactManifestEntry(
                role=ArtifactRole.RESPONSE_TEXT, availability=ArtifactAvailability.AVAILABLE,
                content_hash=canonical_hash(response.text), media_type="text/plain",
                locator="embedded:trial_execution.response.text",
            ),
        ))
    else:
        entries.extend((
            ArtifactManifestEntry(
                role=ArtifactRole.PROVIDER_RESPONSE, availability=ArtifactAvailability.UNAVAILABLE,
                omission_reason="Provider did not return a response.",
            ),
            ArtifactManifestEntry(
                role=ArtifactRole.RESPONSE_TEXT, availability=ArtifactAvailability.UNAVAILABLE,
                omission_reason="Provider did not return response text.",
            ),
        ))
    if model:
        entries.append(ArtifactManifestEntry(role=ArtifactRole.MODEL_ARTIFACT, availability=ArtifactAvailability.AVAILABLE if model.model_artifact_locator else ArtifactAvailability.UNAVAILABLE, content_hash=model.model_artifact_hash, locator=model.model_artifact_locator, omission_reason=None if model.model_artifact_locator else "Model artifact location was not supplied."))
    if software:
        entries.append(ArtifactManifestEntry(role=ArtifactRole.DEPENDENCY_MANIFEST, availability=ArtifactAvailability.AVAILABLE if software.dependency_manifest_locator else ArtifactAvailability.UNAVAILABLE, content_hash=software.dependency_manifest_hash, locator=software.dependency_manifest_locator, omission_reason=None if software.dependency_manifest_locator else "Dependency manifest location was not supplied."))
    entries.append(ArtifactManifestEntry(
        role=ArtifactRole.EXPERIMENT_DEFINITION, availability=ArtifactAvailability.AVAILABLE,
        content_hash=experiment_hash, media_type="application/json",
        locator="embedded:experiment_revision",
    ))
    return tuple(entries)
