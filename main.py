"""Local control-plane CLI for reproducible overnight experiments."""
from __future__ import annotations

import argparse
import json
import sys
from hashlib import sha256
from pathlib import Path
from uuid import UUID


MINIMUM_PYTHON = (3, 11)


def require_supported_python(version_info=None) -> None:
    """Fail before importing domain modules that require Python 3.11+."""
    version = version_info or sys.version_info
    if tuple(version[:2]) < MINIMUM_PYTHON:
        detected = ".".join(str(part) for part in version[:3])
        raise SystemExit(
            f"Entropy Research Platform requires Python 3.11 or newer; detected {detected}."
        )


# This must remain above every application import: the domain intentionally uses
# ``datetime.UTC``, introduced in Python 3.11.
require_supported_python()

from core.config import load_experiment_plan
from core.experiment_service import ExperimentService
from core.mvp import build_and_register, resolve_experiment
from core.provenance_capture import capture_runtime_snapshot, capture_software_snapshot
from database.sqlite_repository import SqliteRepository
from entropy.policy import PersistentEntropyPolicyRegistry
from entropy.registry import EntropySourceRegistry
from models.lmstudio import LmStudioProvider
from prompts.base import StrictPromptRenderer
from runner.orchestrator import TrialOrchestrator
from runner.scheduler import InlineScheduler
from analysis.artifacts import LocalArtifactStore
from analysis.baseline import BaselineAnalyzer
from analysis.cohort import CohortBuilder
from analysis.domain import AnalysisSpecification
from analysis.service import AnalysisService


def _repo(path: Path) -> SqliteRepository:
    path.parent.mkdir(parents=True, exist_ok=True)
    return SqliteRepository(path)


def _config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_mvp_config(config: dict) -> None:
    for key in ("author_id", "hypothesis", "entropy_sources", "prompts", "experiment"):
        if key not in config:
            raise ValueError(f"configuration requires {key}")
    sources = config["entropy_sources"]
    if not sources or len({source["name"] for source in sources}) != len(sources):
        raise ValueError("entropy source names must be unique")
    conditions = config["experiment"].get("conditions", [])
    if len({c.get("id") for c in conditions}) != len(conditions):
        raise ValueError("condition IDs must be unique")
    source_by_name = {s["name"]: s for s in sources}
    if any(c.get("source") not in source_by_name for c in conditions):
        raise ValueError("every condition must reference a configured source")
    kinds = [source_by_name[c["source"]]["source_type"] for c in conditions]
    if kinds.count("deterministic_prng") != 1 or not any(k in {"os_entropy", "hardware_entropy", "qrng"} for k in kinds):
        raise ValueError("exactly one deterministic control and one physical-entropy condition are required")
    seen = set()
    for condition in conditions:
        source = source_by_name[condition["source"]]
        identity = (source["implementation_identity"], json.dumps(source.get("configuration", {}), sort_keys=True))
        if identity in seen:
            raise ValueError("equivalent source configurations cannot be separate conditions")
        seen.add(identity)
    kind = config["experiment"].get("allocation_kind", "replicated_single_prompt")
    if kind == "prompt_battery":
        if int(config["experiment"].get("replications_per_prompt", 0)) < 1:
            raise ValueError("prompt-battery replications_per_prompt must be positive")
    elif kind == "fixed_conversation":
        conversation = config["experiment"].get("conversation", {})
        turns = int(conversation.get("turns_per_trajectory", 0))
        if int(conversation.get("trajectories_per_condition", 0)) < 1 or not 2 <= turns <= 6:
            raise ValueError("conversation requires trajectories per condition and two to six turns")
        if conversation.get("context_policy") != "reject_if_exceeds_budget":
            raise ValueError("conversation supports only reject_if_exceeds_budget")
    elif int(config["experiment"].get("trials_per_condition", 0)) < 1:
        raise ValueError("trials_per_condition must be positive")


def _service(repo: SqliteRepository, config: dict) -> ExperimentService:
    model = LmStudioProvider(
        base_url=config.get("lmstudio", {}).get("base_url", "http://127.0.0.1:1234/v1"),
        timeout_s=float(config.get("experiment", {}).get("request_timeout_seconds", config.get("lmstudio", {}).get("timeout_s", 120))),
        model_artifact_hashes=config.get("model_artifact_hashes", {}),
    )
    software = capture_software_snapshot("local-mvp", Path("requirements.txt"))
    orchestrator = TrialOrchestrator(EntropySourceRegistry(repo), StrictPromptRenderer(), model, repo,
        capture_runtime_snapshot(), software, PersistentEntropyPolicyRegistry(repo))
    return ExperimentService(repo, repo, InlineScheduler(), orchestrator, UUID(config["author_id"]))


def _preflight(repo: SqliteRepository, config: dict, reference: str) -> None:
    experiment = resolve_experiment(repo, reference)
    if not experiment.plan.conditions:
        raise ValueError("preflight requires a registered condition-based experiment")
    registry = EntropySourceRegistry(repo)
    policies = PersistentEntropyPolicyRegistry(repo)
    model = LmStudioProvider(config.get("lmstudio", {}).get("base_url", "http://127.0.0.1:1234/v1"),
        timeout_s=float(config.get("experiment", {}).get("request_timeout_seconds", config.get("lmstudio", {}).get("timeout_s", 120))),
        model_artifact_hashes=config.get("model_artifact_hashes", {}))
    for condition in experiment.plan.conditions:
        spec, source = registry.resolve(condition.entropy_source)
        policy, _ = policies.resolve(condition.entropy_policy)
        needed = policy.byte_start + policy.byte_length
        if source.capabilities().get("max_bytes_per_request", 0) < needed:
            raise ValueError(f"condition {condition.condition_id}: source cannot supply policy bytes")
        declared = spec.declared_capabilities.get("max_bytes_per_request")
        observed = source.capabilities().get("max_bytes_per_request")
        if isinstance(declared, int) and isinstance(observed, int) and observed < declared:
            raise ValueError(f"condition {condition.condition_id}: resolved source capability is below its registered declaration")
        if not bool(model.capabilities().get("seed")):
            raise ValueError("configured provider cannot accept a seed request patch")
        if spec.content_hash() != condition.entropy_source.content_hash:
            raise ValueError("source reference hash mismatch")
    max_conversation_turn = max((trial.conversation.turn_index for trial in experiment.plan.trials if trial.conversation), default=0)
    for trial in experiment.plan.trials:
        if trial.conversation and trial.conversation.turn_index == max_conversation_turn:
            # Conservative planning estimate: each prior response may consume its
            # full configured completion budget; exact tokenizer accounting is a
            # provider concern recorded at execution when available.
            instruction = repo.resolve_prompt(trial.prompt_revision).content
            estimate = trial.conversation.turn_index * (trial.max_tokens or 0) + ((len(instruction) + 3) // 4 + 4) * trial.conversation.turn_index
            if estimate + (trial.max_tokens or 0) > trial.conversation.context_window_budget:
                raise ValueError("declared conversation context budget cannot accommodate maximum-length conversation turns")
    # Network check comes last: all scientific references are already validated.
    model.preflight(experiment.plan.trials[0].model_identifier)
    print("preflight passed: registered sources, policies, prompts, model capability, and LM Studio availability")
    if model.capabilities().get("seed") == "best-effort":
        print("warning: LM Studio accepts seed requests as best-effort; a deterministic entropy control does not guarantee identical model outputs.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Entropy Research Platform local control plane")
    parser.add_argument("--database", type=Path, default=Path("database/experiment.db"))
    parser.add_argument("--config", type=Path, default=Path("config/experiments/overnight.json"))
    top = parser.add_subparsers(dest="area", required=True)
    experiment = top.add_parser("experiment")
    exp_cmd = experiment.add_subparsers(dest="action", required=True)
    validate = exp_cmd.add_parser("validate"); validate.add_argument("path", type=Path)
    register = exp_cmd.add_parser("register"); register.add_argument("path", type=Path)
    preflight = exp_cmd.add_parser("preflight"); preflight.add_argument("reference")
    run = top.add_parser("run"); run_cmd = run.add_subparsers(dest="action", required=True)
    start = run_cmd.add_parser("start"); start.add_argument("reference"); start.add_argument("--idempotency-key", required=True)
    for name in ("status", "pause", "resume", "cancel", "recover"):
        command = run_cmd.add_parser(name); command.add_argument("run_id")
        if name == "resume": command.add_argument("--experiment", required=True)
    analyze = top.add_parser("analyze"); analyze_cmd = analyze.add_subparsers(dest="action", required=True)
    baseline = analyze_cmd.add_parser("baseline"); baseline.add_argument("run_id")
    export = top.add_parser("export"); export_cmd = export.add_subparsers(dest="action", required=True)
    blind = export_cmd.add_parser("blind"); blind.add_argument("reference"); blind.add_argument("output", type=Path)
    reveal = export_cmd.add_parser("reveal-map"); reveal.add_argument("reference"); reveal.add_argument("output", type=Path)
    readable = export_cmd.add_parser("readable-results"); readable.add_argument("run_id"); readable.add_argument("output", type=Path); readable.add_argument("--blinded", action="store_true")
    workspace = top.add_parser("workspace"); ws = workspace.add_subparsers(dest="action", required=True); serve = ws.add_parser("serve"); serve.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.area == "experiment" and args.action == "validate":
        data = _config(args.path); _validate_mvp_config(data); print("valid local-MVP configuration") ; return
    repo = _repo(args.database)
    try:
        config = _config(args.config if args.area != "experiment" or args.action != "register" else args.path)
        if args.area == "experiment":
            if args.action == "register":
                _validate_mvp_config(config); ref, _ = build_and_register(args.path, repo); print(f"registered experiment: {ref.record_id}:{ref.revision}:{ref.content_hash}")
            elif args.action == "preflight": _preflight(repo, config, args.reference)
            return
        if args.area == "run":
            service = _service(repo, config)
            if args.action == "start":
                experiment_revision = resolve_experiment(repo, args.reference)
                result = service.start(experiment_revision, args.idempotency_key)
            elif args.action == "status": result = repo.get_run(UUID(args.run_id))
            elif args.action == "pause": result = service.pause(UUID(args.run_id))
            elif args.action == "cancel": result = service.cancel(UUID(args.run_id))
            elif args.action == "recover": result = service.reconcile_interrupted(UUID(args.run_id))
            else: result = service.resume(resolve_experiment(repo, args.experiment), UUID(args.run_id))
            print(result.model_dump_json(indent=2)); return
        if args.area == "analyze":
            executions = repo.executions_for_run(UUID(args.run_id))
            cohort = CohortBuilder().build(executions, filters={"experiment_run_id": args.run_id})
            spec = AnalysisSpecification(analyzer_id="baseline_descriptive", analyzer_version="1",
                parameters={"scope": "local-mvp descriptive baseline"}, created_by=UUID(config["author_id"]))
            service = AnalysisService(repo, {"baseline_descriptive": BaselineAnalyzer()}, "local-mvp", "local-runtime",
                LocalArtifactStore(Path("reports/artifacts")))
            result = service.run(spec, cohort)
            print(result.model_dump_json(indent=2)); return
        if args.area == "export":
            if args.action == "readable-results":
                executions = repo.executions_for_run(UUID(args.run_id))
                experiment = repo.resolve_scientific_record(executions[0].provenance.experiment_revision) if executions else None
                trial_slots = {str(trial.id): trial.slot_id for trial in experiment.plan.trials} if experiment else {}
                payload = []
                for number, execution in enumerate(executions, 1):
                    condition = execution.condition_id
                    if args.blinded:
                        experiment = repo.resolve_scientific_record(execution.provenance.experiment_revision)
                        condition = next((item.blinded_label or item.condition_id for item in experiment.plan.conditions if item.condition_id == condition), condition)
                    slot_id = trial_slots.get(str(execution.trial_spec_id))
                    row = {"execution_order": number, "execution_id": str(execution.id), "condition": condition,
                        "slot_id": slot_id,
                        "prompt": execution.provenance.prompt.rendered_prompt.text if execution.provenance.prompt else None,
                        "question_group": execution.provenance.prompt.metadata.get("question_group") if execution.provenance.prompt else None,
                        "replication": slot_id.rsplit("-r", 1)[1] if slot_id and "-r" in slot_id else None,
                        "output": execution.response.text if execution.response else None,
                        "response_hash": sha256(execution.response.text.encode()).hexdigest() if execution.response else None,
                        "latency_ms": execution.response.latency_ms if execution.response else None,
                        "prompt_tokens": execution.response.prompt_tokens if execution.response else None,
                        "completion_tokens": execution.response.completion_tokens if execution.response else None,
                        "stop_reason": execution.response.stop_reason if execution.response else None}
                    if not args.blinded:
                        row.update({"entropy_value_hash": execution.entropy.value_hash if execution.entropy else None,
                            "derived_seed": execution.request.seed if execution.request else None})
                    if execution.conversation:
                        row.update({"trajectory_id": execution.conversation.trajectory_id, "turn_number": execution.conversation.turn_index,
                            "trajectory_replication": execution.conversation.trajectory_id.rsplit("-", 1)[-1],
                            "transcript": [message.model_dump(mode="json") for message in execution.conversation.messages]})
                    payload.append(row)
                json_bytes = json.dumps(payload, indent=2, sort_keys=True).encode()
                markdown = "\n\n".join(f"## Execution {row['execution_order']}\n\n```json\n{json.dumps(row, indent=2, sort_keys=True)}\n```" for row in payload).encode()
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_bytes(json_bytes)
                markdown_path = args.output.with_suffix(".md")
                markdown_path.write_bytes(markdown)
                print(json.dumps({"json": str(args.output), "json_sha256": sha256(json_bytes).hexdigest(), "markdown": str(markdown_path), "markdown_sha256": sha256(markdown).hexdigest()})); return
            experiment_revision = resolve_experiment(repo, args.reference)
            if args.action == "blind":
                payload = {"experiment_revision": args.reference, "conditions": [
                    {"blinded_label": c.blinded_label or "blinded-condition", "condition_hash": c.content_hash()
                    } for c in experiment_revision.plan.conditions],
                    "disclosure": "Blinded labels only; retain the reveal map separately until the planned analysis is complete."}
            else:
                payload = {"experiment_revision": args.reference, "reveal_map": {
                    c.blinded_label or c.condition_id: c.label for c in experiment_revision.plan.conditions}}
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            print(args.output); return
        from dashboard.server import serve as serve_workspace
        serve_workspace(args.database, port=args.port)
    finally:
        if args.area != "workspace": repo.close()


if __name__ == "__main__":
    main()
