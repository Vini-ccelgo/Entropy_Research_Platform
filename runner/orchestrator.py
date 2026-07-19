"""One-attempt execution; all pre-provider work is inside the failure boundary."""
from __future__ import annotations

from datetime import UTC, datetime

import httpx

from core.provenance import ConversationTurnEvidence, ExecutionProvenance, TrialExecution, canonical_hash
from core.provenance_capture import execution_artifacts, snapshot_prompt
from core.science import ExperimentRevision
from core.types import ChatMessage, ChatRole, ModelRequest, PromptTemplate, TrialSpec, TrialStatus


class TrialOrchestrator:
    def __init__(self, entropy, renderer, model, repository, runtime, software, policies) -> None:
        # ``entropy`` is either one legacy adapter or an EntropySourceRegistry.
        self._entropy, self._renderer, self._model = entropy, renderer, model
        self._repository, self._runtime, self._software, self._policies = repository, runtime, software, policies

    def _resolved_inputs(self, trial: TrialSpec):
        source_spec = None
        if trial.entropy_source is not None:
            source_spec, source = self._entropy.resolve(trial.entropy_source)
        else:
            source = self._entropy
        prompt_record = None
        if trial.prompt_revision is not None:
            prompt_record = self._repository.resolve_prompt(trial.prompt_revision)
            template = PromptTemplate(
                id=str(prompt_record.id), version=str(prompt_record.revision), category=prompt_record.category,
                goal=prompt_record.purpose, template=prompt_record.content, tags=prompt_record.tags,
            )
        elif trial.prompt is not None:
            template = trial.prompt
        else:  # Model validation prevents this; retains a useful failure if deserializing old records.
            raise ValueError("trial lacks a prompt revision")
        return source_spec, source, template, prompt_record

    def execute(self, experiment: ExperimentRevision, trial: TrialSpec, experiment_run_id, trial_attempt_id,
                attempt_number: int, idempotency_key: str) -> TrialExecution:
        started = datetime.now(UTC)
        rendered = entropy_sample = request = response = application = conversation = None
        prompt_snapshot = source_snapshot = model_snapshot = None
        unavailable: dict[str, str] = {}
        source = None
        try:
            source_spec, source, template, prompt_record = self._resolved_inputs(trial)
            try:
                rendered_value = self._renderer.render(template, trial.prompt_variables)
                prompt_snapshot = snapshot_prompt(template, rendered_value,
                    category=prompt_record.category if prompt_record else template.category,
                    purpose=prompt_record.purpose if prompt_record else template.goal,
                    metadata=prompt_record.metadata if prompt_record else {})
                rendered = prompt_snapshot.rendered_prompt
            except Exception as exc:
                unavailable["prompt"] = f"{type(exc).__name__}: {exc}"
                raise
            try:
                source_snapshot = source.provenance_snapshot()
            except Exception as exc:
                unavailable["entropy_source"] = f"{type(exc).__name__}: {exc}"
                raise
            try:
                model_snapshot = self._model.provenance_snapshot(trial.model_identifier)
            except Exception as exc:
                unavailable["model"] = f"{type(exc).__name__}: {exc}"
                raise
            messages = self._conversation_messages(experiment, trial, experiment_run_id, rendered)
            conversation = messages[1]
            spec, policy = self._policies.resolve(trial.entropy_policy)
            capabilities = source.capabilities()
            required = spec.byte_start + spec.byte_length
            if capabilities.get("max_bytes_per_request", 0) < required:
                raise ValueError("entropy source capability cannot supply policy byte range")
            if trial.entropy.bytes_required < required:
                raise ValueError("entropy request cannot supply policy byte range")
            if not bool(self._model.capabilities().get("seed")):
                raise ValueError("model provider does not support seed patch")
            entropy_sample = source.sample(trial.entropy)
            patch, application = policy.apply(entropy_sample, spec)
            application = application.model_copy(update={"source_capabilities": capabilities})
            request = ModelRequest(provider=trial.model_provider, model_identifier=trial.model_identifier,
                prompt=rendered, temperature=trial.temperature, top_p=trial.top_p, top_k=trial.top_k,
                repeat_penalty=trial.repeat_penalty, max_tokens=trial.max_tokens, seed=patch.seed,
                messages=messages[0])
            response = self._model.generate(request)
            status, error, category = TrialStatus.COMPLETED, None, None
        except Exception as exc:
            status, error, category = TrialStatus.FAILED, f"{type(exc).__name__}: {exc}", self._category(exc)
            conversation = getattr(exc, "conversation_evidence", conversation)
            if entropy_sample is None and "entropy_source" not in unavailable:
                unavailable["entropy_sample"] = error
        provenance = ExecutionProvenance(
            experiment_revision=experiment.reference(), prompt=prompt_snapshot, entropy_source=source_snapshot,
            model=model_snapshot, runtime=self._runtime, software=self._software,
            artifacts=execution_artifacts(request, response, entropy_sample.value_hash if entropy_sample else None,
                model_snapshot, self._software, experiment.reference().content_hash),
            unavailable_components=unavailable,
        )
        return TrialExecution(
            experiment_run_id=experiment_run_id, trial_attempt_id=trial_attempt_id,
            attempt_number=attempt_number, idempotency_key=idempotency_key, trial_spec_id=trial.id,
            condition_id=trial.condition_id, entropy_source_reference=trial.entropy_source,
            prompt_revision_reference=trial.prompt_revision, status=status, provenance=provenance,
            conversation=conversation,
            entropy=entropy_sample, entropy_application=application, request=request, response=response,
            error=error, failure_category=category, started_at=started, finished_at=datetime.now(UTC),
        )

    @staticmethod
    def _category(exc: Exception) -> str:
        if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
            return "transient"
        if isinstance(exc, httpx.HTTPError):
            return "provider"
        if isinstance(exc, (ValueError, KeyError)):
            return "configuration"
        return "unknown"

    def _conversation_messages(self, experiment: ExperimentRevision, trial: TrialSpec, run_id, rendered):
        """Reconstruct a complete request from persisted parent evidence only."""
        plan = trial.conversation
        if plan is None:
            return ((), None)
        if plan.turn_index == 1:
            messages = (ChatMessage(role=ChatRole.USER, content=rendered.text),)
            parent_execution = None
        else:
            by_slot = {candidate.slot_id: candidate for candidate in experiment.plan.trials}
            parent_trial = by_slot.get(plan.parent_slot_id)
            if parent_trial is None or parent_trial.conversation is None:
                raise ValueError("conversation parent slot is not part of this experiment")
            if parent_trial.conversation.trajectory_id != plan.trajectory_id or parent_trial.condition_id != trial.condition_id:
                raise ValueError("conversation parent belongs to a different trajectory or condition")
            parent_execution = self._repository.successful_execution_for_trial_spec(run_id, parent_trial.id)
            if parent_execution is None or parent_execution.response is None or parent_execution.conversation is None:
                raise ValueError("conversation parent has no successful persisted execution")
            messages = parent_execution.conversation.messages + (
                ChatMessage(role=ChatRole.ASSISTANT, content=parent_execution.response.text),
                ChatMessage(role=ChatRole.USER, content=rendered.text),
            )
        transcript_hash = canonical_hash([message.model_dump(mode="json") for message in messages])
        # Conservative, deterministic estimate.  The configured budget reserves
        # generation capacity so an over-budget request is rejected before I/O.
        estimated = sum((len(message.content) + 3) // 4 + 4 for message in messages)
        if estimated + (trial.max_tokens or 0) > plan.context_window_budget:
            evidence = ConversationTurnEvidence(
                trajectory_id=plan.trajectory_id, turn_index=plan.turn_index, parent_slot_id=plan.parent_slot_id,
                parent_execution_id=parent_execution.id if parent_execution else None, messages=messages,
                pre_context_transcript_hash=transcript_hash, final_request_messages_hash=transcript_hash,
                context_policy=plan.context_policy, context_window_budget=plan.context_window_budget,
                estimated_context_tokens=estimated, reconstruction_version=plan.reconstruction_version,
            )
            # Attach evidence to the exception so the terminal failure remains auditable.
            error = ValueError("conversation context exceeds declared budget")
            error.conversation_evidence = evidence
            raise error
        return (messages, ConversationTurnEvidence(
            trajectory_id=plan.trajectory_id, turn_index=plan.turn_index, parent_slot_id=plan.parent_slot_id,
            parent_execution_id=parent_execution.id if parent_execution else None, messages=messages,
            pre_context_transcript_hash=transcript_hash, final_request_messages_hash=transcript_hash,
            context_policy=plan.context_policy, context_window_budget=plan.context_window_budget,
            estimated_context_tokens=estimated, reconstruction_version=plan.reconstruction_version,
        ))
