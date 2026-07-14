"""Application service that executes a single reproducible trial."""

from __future__ import annotations

from datetime import UTC, datetime

from core.interfaces import EntropyPort, ExperimentRepositoryPort, ModelProviderPort, PromptRendererPort
from core.types import (
    EntropyApplicationPolicy, ExperimentPlan, ModelRequest, TrialResult,
    TrialSpec, TrialStatus,
)


class TrialOrchestrator:
    def __init__(self, entropy: EntropyPort, renderer: PromptRendererPort,
                 model: ModelProviderPort, repository: ExperimentRepositoryPort) -> None:
        self._entropy = entropy
        self._renderer = renderer
        self._model = model
        self._repository = repository

    def execute(self, plan: ExperimentPlan, trial: TrialSpec) -> TrialResult:
        """Execute and persist one trial; failures become durable result records."""
        started = datetime.now(UTC)
        try:
            entropy = self._entropy.sample(trial.entropy)
            rendered = self._renderer.render(trial.prompt, trial.prompt_variables)
            if trial.entropy.application_policy is not EntropyApplicationPolicy.DERIVE_MODEL_SEED:
                raise ValueError("unsupported entropy application policy")
            seed = int.from_bytes(entropy.raw_bytes[:8], "big")
            request = ModelRequest(
                provider=trial.model_provider, model_identifier=trial.model_identifier,
                prompt=rendered, temperature=trial.temperature, top_p=trial.top_p,
                top_k=trial.top_k, repeat_penalty=trial.repeat_penalty,
                max_tokens=trial.max_tokens, seed=seed,
            )
            response = self._model.generate(request)
            result = TrialResult(trial_id=trial.id, experiment_id=plan.id, status=TrialStatus.COMPLETED,
                                 rendered_prompt=rendered, entropy=entropy, request=request,
                                 response=response, started_at=started, finished_at=datetime.now(UTC))
        except Exception as exc:  # persisted error permits audit and safe continuation
            result = TrialResult(trial_id=trial.id, experiment_id=plan.id, status=TrialStatus.FAILED,
                                 error=f"{type(exc).__name__}: {exc}", started_at=started,
                                 finished_at=datetime.now(UTC))
        self._repository.record_trial(result)
        return result
