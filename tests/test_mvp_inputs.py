import json
from pathlib import Path
from uuid import uuid4

import pytest

from core.mvp import build_and_register
from core.registries import EntropySourceSpecification, PromptRevision, PromptSetRevision
from database.sqlite_repository import SqliteRepository
from core.provenance import ModelSnapshot, RuntimeSnapshot, SoftwareSnapshot
from core.types import ModelResponse, TrialStatus
from entropy.policy import PersistentEntropyPolicyRegistry
from entropy.registry import EntropySourceRegistry
from prompts.base import StrictPromptRenderer
from runner.orchestrator import TrialOrchestrator


def test_registered_source_and_prompt_survive_restart(tmp_path: Path):
    db = tmp_path / "evidence.db"
    repo = SqliteRepository(db)
    from uuid import UUID
    actor = UUID("11111111-1111-4111-8111-111111111111")
    source = EntropySourceSpecification(created_by=actor, implementation_identity="entropy.prng.PrngEntropySource",
        implementation_version="1", source_type="deterministic_prng", configuration={"seed": 1},
        declared_capabilities={"max_bytes_per_request": 8, "replayable": True})
    source_ref = repo.register_entropy_source(source)
    prompt_ref = repo.register_prompt(PromptRevision(created_by=actor, category="neutral", purpose="test", content="hello {x}", variable_schema=("x",)))
    prompt_set_ref = repo.register_prompt_set(PromptSetRevision(created_by=actor, prompts=(prompt_ref,)))
    repo.close()
    reopened = SqliteRepository(db)
    assert reopened.resolve_entropy_source(source_ref).content_hash() == source_ref.content_hash
    assert reopened.resolve_prompt(prompt_ref).content_hash() == prompt_ref.content_hash
    assert reopened.resolve_prompt_set(prompt_set_ref).prompts == (prompt_ref,)


def test_secret_source_config_is_rejected(tmp_path: Path):
    from uuid import UUID
    with pytest.raises(ValueError):
        EntropySourceSpecification(created_by=UUID("11111111-1111-4111-8111-111111111111"),
            implementation_identity="x", implementation_version="1", source_type="qrng",
            configuration={"api_key": "actual-secret"})


def test_balanced_registered_mvp_plan(tmp_path: Path):
    source = Path("config/experiments/overnight.json")
    config = json.loads(source.read_text())
    config["experiment"]["trials_per_condition"] = 2
    path = tmp_path / "mvp.json"; path.write_text(json.dumps(config))
    repo = SqliteRepository(tmp_path / "mvp.db")
    ref, revision = build_and_register(path, repo)
    assert len(revision.plan.trials) == 4
    assert {trial.condition_id for trial in revision.plan.trials} == {"control", "os-entropy"}
    assert len({trial.slot_id for trial in revision.plan.trials}) == 4
    assert repo.resolve_scientific_record(ref).reference() == ref


class _SeedModel:
    def capabilities(self): return {"seed": True}
    def provenance_snapshot(self, identifier):
        return ModelSnapshot(provider="fake", model_identifier=identifier, model_artifact_hash="a" * 64,
            provider_configuration_hash="b" * 64, provider_capabilities=self.capabilities())
    def generate(self, request):
        return ModelResponse(text=f"seed={request.seed}", provider="fake", model_identifier=request.model_identifier, latency_ms=1)


def test_registered_condition_and_prompt_are_preserved_in_execution(tmp_path: Path):
    config = json.loads(Path("config/experiments/overnight.json").read_text())
    config["experiment"]["trials_per_condition"] = 1
    path = tmp_path / "mvp.json"; path.write_text(json.dumps(config))
    repo = SqliteRepository(tmp_path / "mvp.db")
    _, experiment = build_and_register(path, repo)
    trial = experiment.plan.trials[0]
    runtime = RuntimeSnapshot(operating_system="test", operating_system_version="1", architecture="x", python_version="x", runtime_name="x", runtime_version="x")
    software = SoftwareSnapshot(application_version="test", dependency_manifest_hash="c" * 64)
    execution = TrialOrchestrator(EntropySourceRegistry(repo), StrictPromptRenderer(), _SeedModel(), repo,
        runtime, software, PersistentEntropyPolicyRegistry(repo)).execute(experiment, trial, uuid4(), uuid4(), 1, "attempt")
    assert execution.status is TrialStatus.COMPLETED
    assert execution.condition_id == trial.condition_id
    assert execution.entropy_source_reference == trial.entropy_source
    assert execution.prompt_revision_reference == trial.prompt_revision
    assert execution.provenance.prompt.rendered_hash
