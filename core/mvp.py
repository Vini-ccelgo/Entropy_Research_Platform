"""Local-MVP application assembly and deterministic experiment construction."""
from __future__ import annotations

import json
import random
from pathlib import Path
from uuid import UUID

from core.registries import (
    EntropySourceSpecification, PromptRevision, PromptSetRevision,
)
from core.science import ExperimentRevision
from core.types import (
    ConversationTurnPlan,
    EntropyApplicationPolicy, EntropyRequest, ExperimentCondition, ExperimentPlan,
    Hypothesis, HypothesisReference, Observer, ObserverKind, TrialSpec,
)
from entropy.policy import EntropyPolicySpecification, PersistentEntropyPolicyRegistry


def reference_text(reference) -> str:
    return f"{reference.record_id}:{reference.revision}:{reference.content_hash}"


def parse_experiment_reference(value: str):
    from core.science import ScientificRecordReference, ScientificRecordType
    record_id, revision, content_hash = value.split(":", 2)
    return ScientificRecordReference(record_type=ScientificRecordType.EXPERIMENT,
        record_id=UUID(record_id), revision=int(revision), content_hash=content_hash)


def _assignment_hash(assignments: list[tuple[str, str]]) -> str:
    from core.registries import canonical_hash
    return canonical_hash(assignments)


def build_and_register(config_path: Path, repository):
    """Register all local inputs then construct one immutable, balanced revision."""
    config = json.loads(config_path.read_text(encoding="utf-8"))
    actor = UUID(config["author_id"])
    observer = Observer(id=actor, display_name=config.get("author_name", "local researcher"), kind=ObserverKind.HUMAN)
    hypothesis_data = dict(config["hypothesis"])
    hypothesis = Hypothesis(registered_by=actor, **hypothesis_data)
    hypothesis_ref = repository.register(hypothesis)

    policy = EntropyPolicySpecification(created_by=actor, **config.get("entropy_policy", {}))
    policy_ref = repository.register_entropy_policy(policy)
    source_refs = {}
    source_specs = {}
    for entry in config["entropy_sources"]:
        name = entry["name"]
        data = {k: v for k, v in entry.items() if k != "name"}
        spec = EntropySourceSpecification(created_by=actor, **data)
        source_refs[name] = repository.register_entropy_source(spec)
        source_specs[name] = spec
    prompts = []
    prompt_refs_by_name = {}
    for entry in config["prompts"]:
        name = entry.get("name")
        prompt = repository.register_prompt(PromptRevision(created_by=actor, **{k: v for k, v in entry.items() if k != "name"}))
        prompts.append(prompt)
        if name:
            prompt_refs_by_name[name] = prompt
    prompt_set_ref = repository.register_prompt_set(PromptSetRevision(prompts=tuple(prompts), created_by=actor))

    experiment = config["experiment"]
    conditions_data = experiment["conditions"]
    controls = [c for c in conditions_data if source_specs[c["source"]].source_type == "deterministic_prng"]
    physical = [c for c in conditions_data if source_specs[c["source"]].source_type in {"os_entropy", "hardware_entropy", "qrng"}]
    if len(controls) != 1 or not physical:
        raise ValueError("MVP requires exactly one deterministic PRNG control and a physical-entropy condition")
    allocation_kind = experiment.get("allocation_kind", "replicated_single_prompt")
    rng = random.Random(int(experiment["assignment_seed"]))
    assignments: list[dict] = []
    if allocation_kind == "prompt_battery":
        replications = int(experiment["replications_per_prompt"])
        for condition in conditions_data:
            for prompt_index, prompt_ref in enumerate(prompts):
                for replication in range(1, replications + 1):
                    assignments.append({"condition_id": condition["id"], "slot_id": f"{condition['id']}-p{prompt_index + 1}-r{replication}", "prompt": prompt_ref})
        rng.shuffle(assignments)
    elif allocation_kind == "fixed_conversation":
        conversation = experiment["conversation"]
        initial = prompt_refs_by_name[conversation["initial_prompt"]]
        continuation = prompt_refs_by_name[conversation["continuation_prompt"]]
        trajectories = int(conversation["trajectories_per_condition"])
        turns = int(conversation["turns_per_trajectory"])
        # Group by turn so every parent is scheduled before its child; ordering
        # inside each turn remains deterministic and condition-interleaved.
        for turn in range(1, turns + 1):
            layer = []
            for condition in conditions_data:
                for trajectory in range(1, trajectories + 1):
                    trajectory_id = f"{condition['id']}-trajectory-{trajectory}"
                    slot_id = f"{trajectory_id}-turn-{turn}"
                    parent = None if turn == 1 else f"{trajectory_id}-turn-{turn - 1}"
                    instruction = initial if turn == 1 else continuation
                    layer.append({"condition_id": condition["id"], "slot_id": slot_id, "prompt": instruction,
                        "conversation": {"trajectory_id": trajectory_id, "turn_index": turn, "parent_slot_id": parent,
                            "instruction_prompt": instruction, "condition_id": condition["id"],
                            "context_policy": conversation["context_policy"], "context_window_budget": int(conversation["context_window_budget"])}})
            rng.shuffle(layer)
            assignments.extend(layer)
    else:
        per_condition = int(experiment["trials_per_condition"])
        assignments = [{"condition_id": c["id"], "slot_id": f"{c['id']}-{i:05d}", "prompt": prompts[i % len(prompts)]}
                       for c in conditions_data for i in range(per_condition)]
        rng.shuffle(assignments)
    per_condition = len(assignments) // len(conditions_data)
    if any(sum(item["condition_id"] == condition["id"] for item in assignments) != per_condition for condition in conditions_data):
        raise ValueError("allocation must be balanced across conditions")
    assignment_hash = _assignment_hash([(item["condition_id"], item["slot_id"], str(item["prompt"].prompt_id)) for item in assignments])
    conditions = tuple(ExperimentCondition(
        condition_id=c["id"], label=c["label"], blinded_label=c.get("blinded_label"),
        entropy_source=source_refs[c["source"]], entropy_policy=policy_ref,
        planned_allocation_count=per_condition,
    ) for c in conditions_data)
    trials = []
    for ordinal, item in enumerate(assignments, 1):
        condition_id, slot_id, prompt_ref = item["condition_id"], item["slot_id"], item["prompt"]
        source_name = next(c["source"] for c in conditions_data if c["id"] == condition_id)
        trials.append(TrialSpec(
            ordinal=ordinal, slot_id=slot_id, condition_id=condition_id, prompt_revision=prompt_ref,
            prompt_variables=dict(experiment.get("prompt_variables", {})),
            model_provider=experiment["model_provider"], model_identifier=experiment["model_identifier"],
            entropy=EntropyRequest(purpose="derive model seed", bytes_required=8,
                application_policy=EntropyApplicationPolicy.DERIVE_MODEL_SEED), entropy_policy=policy_ref,
            entropy_source=source_refs[source_name], temperature=float(experiment.get("temperature", 0.7)),
            top_p=float(experiment.get("top_p", 0.95)), max_tokens=experiment.get("max_tokens"),
            conversation=ConversationTurnPlan(**item["conversation"]) if "conversation" in item else None,
        ))
    plan = ExperimentPlan(name=experiment["name"], description=experiment.get("description", ""),
        hypothesis=HypothesisReference(hypothesis_id=hypothesis_ref.hypothesis_id, revision=hypothesis_ref.revision,
            content_hash=hypothesis_ref.content_hash), observers=(observer,), trials=tuple(trials),
        prompt_set=prompt_set_ref, conditions=conditions, assignment_strategy="deterministic-shuffle-v1",
        assignment_seed=int(experiment["assignment_seed"]), assignment_hash=assignment_hash,
        git_commit=experiment.get("git_commit"))
    revision = ExperimentRevision.from_plan(plan, actor)
    return repository.register_experiment_revision(revision), revision


def resolve_experiment(repository, value: str) -> ExperimentRevision:
    return repository.resolve_scientific_record(parse_experiment_reference(value))
