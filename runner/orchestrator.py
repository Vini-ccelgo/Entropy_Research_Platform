"""One-attempt execution with complete, non-fabricated failure evidence."""
from __future__ import annotations
from datetime import UTC, datetime
import httpx
from core.interfaces import EntropyPort, ModelProviderPort, PromptRendererPort
from core.provenance import ExecutionProvenance, TrialExecution
from core.provenance_capture import execution_artifacts, snapshot_prompt
from core.science import ExperimentRevision
from core.types import EntropyApplicationPolicy, ModelRequest, TrialSpec, TrialStatus

class TrialOrchestrator:
    def __init__(self, entropy: EntropyPort, renderer: PromptRendererPort, model: ModelProviderPort,
                 repository, runtime, software, policies) -> None:
        self._entropy,self._renderer,self._model=entropy,renderer,model
        self._runtime,self._software,self._policies=runtime,software,policies

    def execute(self, experiment: ExperimentRevision, trial: TrialSpec, experiment_run_id, trial_attempt_id,
                attempt_number: int, idempotency_key: str) -> TrialExecution:
        started=datetime.now(UTC); rendered=None; entropy=None; request=None; response=None
        prompt=None; source=None; model=None; unavailable={}
        try:
            try: prompt=snapshot_prompt(trial.prompt, self._renderer.render(trial.prompt, trial.prompt_variables)); rendered=prompt.rendered_prompt
            except Exception as exc: unavailable["prompt"]=f"{type(exc).__name__}: {exc}"; raise
            try: source=self._entropy.provenance_snapshot()
            except Exception as exc: unavailable["entropy_source"]=f"{type(exc).__name__}: {exc}"; raise
            try: model=self._model.provenance_snapshot(trial.model_identifier)
            except Exception as exc: unavailable["model"]=f"{type(exc).__name__}: {exc}"; raise
            spec,policy=self._policies.resolve(trial.entropy_policy)
            capabilities=self._entropy.capabilities()
            if capabilities.get("max_bytes_per_request",0) < spec.byte_start + spec.byte_length: raise ValueError("entropy source capability cannot supply policy byte range")
            if trial.entropy.bytes_required < spec.byte_start + spec.byte_length: raise ValueError("entropy request cannot supply policy byte range")
            if not self._model.capabilities().get("seed"): raise ValueError("model provider does not support seed patch")
            entropy=self._entropy.sample(trial.entropy)
            patch,application=policy.apply(entropy,spec); application=application.model_copy(update={"source_capabilities":capabilities})
            request=ModelRequest(provider=trial.model_provider,model_identifier=trial.model_identifier,prompt=rendered,temperature=trial.temperature,top_p=trial.top_p,top_k=trial.top_k,repeat_penalty=trial.repeat_penalty,max_tokens=trial.max_tokens,seed=patch.seed)
            response=self._model.generate(request); status=TrialStatus.COMPLETED; error=None; category=None
        except Exception as exc:
            status=TrialStatus.FAILED; error=f"{type(exc).__name__}: {exc}"; category=self._category(exc)
            if entropy is None and "entropy_source" not in unavailable: unavailable["entropy_sample"]=error
        provenance=ExecutionProvenance(experiment_revision=experiment.reference(),prompt=prompt,entropy_source=source,model=model,runtime=self._runtime,software=self._software,artifacts=execution_artifacts(request,response,entropy.value_hash if entropy else None,model,self._software,experiment.reference().content_hash),unavailable_components=unavailable)
        return TrialExecution(experiment_run_id=experiment_run_id,trial_attempt_id=trial_attempt_id,attempt_number=attempt_number,idempotency_key=idempotency_key,trial_spec_id=trial.id,status=status,provenance=provenance,entropy=entropy,entropy_application=locals().get("application"),request=request,response=response,error=error,failure_category=category,started_at=started,finished_at=datetime.now(UTC))
    @staticmethod
    def _category(exc:Exception)->str:
        if isinstance(exc,(httpx.TimeoutException,httpx.NetworkError)): return "transient"
        if isinstance(exc,httpx.HTTPError): return "provider"
        if isinstance(exc,ValueError): return "configuration"
        return "unknown"
