from pathlib import Path

from core.types import (
    EntropyApplicationPolicy, EntropyRequest, ExperimentPlan, Hypothesis,
    HypothesisStatus, ModelResponse, Observer, ObserverKind, PromptTemplate,
    TrialSpec, TrialStatus,
)
from database.sqlite_repository import SqliteRepository
from entropy.prng import PrngEntropySource
from prompts.base import StrictPromptRenderer
from runner.orchestrator import TrialOrchestrator


class FakeModel:
    def capabilities(self) -> dict[str, object]:
        return {"seed": True}

    def generate(self, request):
        return ModelResponse(text=f"seed={request.seed}", provider=request.provider,
                             model_identifier=request.model_identifier, latency_ms=1.0)


def test_registered_hypothesis_and_observer_are_persisted_with_trial(tmp_path: Path) -> None:
    repository = SqliteRepository(tmp_path / "experiment.db")
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
                               application_policy=EntropyApplicationPolicy.DERIVE_MODEL_SEED),
    )
    plan = ExperimentPlan(name="Control", hypothesis=reference, observers=(observer,), trials=(trial,))
    repository.create_experiment(plan)
    result = TrialOrchestrator(PrngEntropySource(7), StrictPromptRenderer(), FakeModel(), repository).execute(plan, trial)
    assert result.status is TrialStatus.COMPLETED
    stored = list(repository.trials_for_experiment(plan.id))
    assert stored[0].entropy is not None
    assert stored[0].entropy.value_hash == result.entropy.value_hash
    repository.close()
