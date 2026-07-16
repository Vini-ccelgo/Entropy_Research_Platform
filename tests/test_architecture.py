from pathlib import Path
from uuid import uuid4

from core.provenance import ModelSnapshot, RuntimeSnapshot, SoftwareSnapshot
from core.science import ExperimentRevision
from core.types import (
    EntropyApplicationPolicy, EntropyRequest, ExperimentPlan, Hypothesis,
    HypothesisStatus, ModelResponse, Observer, ObserverKind, PromptTemplate,
    TrialSpec, TrialStatus,
)
from database.sqlite_repository import SqliteRepository
from entropy.prng import PrngEntropySource
from entropy.policy import EntropyPolicyRegistry, EntropyPolicySpecification
from prompts.base import StrictPromptRenderer
from runner.orchestrator import TrialOrchestrator


class FakeModel:
    def capabilities(self) -> dict[str, object]:
        return {"seed": True}

    def provenance_snapshot(self, model_identifier: str) -> ModelSnapshot:
        return ModelSnapshot(provider="fake", model_identifier=model_identifier,
                             model_artifact_hash="a" * 64, provider_configuration_hash="b" * 64,
                             provider_capabilities=self.capabilities(), provider_configuration={"mode": "test"})

    def generate(self, request):
        return ModelResponse(text=f"seed={request.seed}", provider=request.provider,
                             model_identifier=request.model_identifier, latency_ms=1.0)


def test_registered_hypothesis_and_observer_are_persisted_with_trial(tmp_path: Path) -> None:
    repository = SqliteRepository(tmp_path / "experiment.db")
    policies=EntropyPolicyRegistry(); policy=policies.register(EntropyPolicySpecification())
    observer = Observer(display_name="Researcher", kind=ObserverKind.HUMAN)
    hypothesis = Hypothesis(title="Entropy affects seeded output", statement="A test claim.",
                            success_criteria="Compare pre-registered metrics.",
                            registered_by=observer.id, status=HypothesisStatus.REGISTERED)
    reference = repository.register(hypothesis)
    trial = TrialSpec(
        ordinal=1, prompt=PromptTemplate(id="control.prompt", version="1", category="control",
                                         goal="test", template="Reply to {subject}"),
        prompt_variables={"subject": "this"}, model_provider="fake", model_identifier="fake-1",
        entropy=EntropyRequest(purpose="model seed", bytes_required=32,
                               application_policy=EntropyApplicationPolicy.DERIVE_MODEL_SEED), entropy_policy=policy,
    )
    plan = ExperimentPlan(name="Control", hypothesis=reference, observers=(observer,), trials=(trial,))
    experiment = ExperimentRevision.from_plan(plan, created_by=observer.id)
    repository.register_experiment_revision(experiment)
    runtime = RuntimeSnapshot(operating_system="test", operating_system_version="1", architecture="test",
                              python_version="test", runtime_name="CPython", runtime_version="test")
    software = SoftwareSnapshot(application_version="test", dependency_manifest_hash="c" * 64)
    result = TrialOrchestrator(PrngEntropySource(7), StrictPromptRenderer(), FakeModel(), repository,
                               runtime, software, policies).execute(experiment, trial, uuid4(), uuid4(), 1, "test-attempt")
    assert result.status is TrialStatus.COMPLETED
    assert result.entropy is not None
    assert result.provenance.experiment_revision == experiment.reference()
    assert result.provenance.entropy_source.configuration["seed"] == 7
    assert result.provenance.prompt.template_hash
    assert {artifact.role.value for artifact in result.provenance.artifacts} >= {
        "entropy_raw_bytes", "provider_request", "provider_response", "model_artifact",
        "dependency_manifest", "experiment_definition",
    }
    relation = repository._connection.execute(
        "SELECT relation_type FROM scientific_relations WHERE source_type = 'experiment'"
    ).fetchone()
    assert relation[0] == "tests"
    repository.close()
