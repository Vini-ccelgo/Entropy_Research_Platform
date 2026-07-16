# Reproducibility Contract

Milestone 1 defines the minimum evidence required to interpret and audit one
trial execution. It does not add scheduling, retries, dashboard views,
analysis, or additional entropy policies.

## Authoritative experiment identity

`ExperimentPlan` is an in-memory construction DTO only. It becomes an
immutable, registered `ExperimentRevision` before execution. Each revision has
an identity, content hash, predecessor lineage, author, audit event, and an
automatic `tests` relation to its pinned hypothesis revision.

Every `TrialExecution` points to an exact `ExperimentRevision` reference rather
than a mutable plan or an unqualified UUID.

## Execution snapshots

An execution stores these immutable snapshots:

| Snapshot | Answers |
|---|---|
| Prompt | Exact template ID/version/content hash, rendered text, variables, and rendered hash. |
| Entropy source | Adapter implementation, source name, full declared configuration, configuration hash, conditioning method, and provider metadata. |
| Entropy sample | Sample source, sample hash, collection time, purpose, and entropy application policy. |
| Model | Provider/model identity, mandatory model-artifact SHA-256, optional tokenizer/chat-template/quantization/context identity, capabilities, and normalized provider configuration plus hash. |
| Runtime | OS, architecture, Python, runtime identity/version, and declared hardware/runtime configuration. |
| Software | Application version, Git commit/dirty state when supplied, dependency-manifest hash and locator, and optional source-tree hash. |
| Artifact manifest | Digest, location, media type, role, and explicit availability/omission state for execution artifacts. |

The LM Studio adapter refuses to execute unless the caller has configured the
SHA-256 of the selected model artifact. This avoids recording an apparently
complete but unidentified model run.

## Artifact policy

The raw entropy sample is intentionally omitted from durable storage by the
current policy. Its SHA-256 is retained and the omission is made explicit in
the manifest. Normalized request, response, response text, and experiment
definition are embedded records with content hashes. Model artifacts and
dependency manifests are marked available only when a locator is supplied;
otherwise they are recorded as unavailable with a reason.

## Capture boundary

`TrialOrchestrator` requires caller-supplied runtime and software snapshots.
This makes missing provenance a composition-time decision rather than an
invisible default. `core.provenance_capture` provides local capture helpers,
but deployment composition is responsible for supplying an application version,
Git state, source-tree hash, and artifact locations appropriate to the research
environment.

## Known limits

This contract captures declared and observed execution conditions. It cannot by
itself guarantee bitwise repeatability from an inference provider: backend
runtime behavior, kernel nondeterminism, or unavailable model artifacts may
still prevent replay. Those limits are made inspectable rather than hidden.
