# Local Overnight Experiment MVP

## Scientific inputs

An `EntropySourceSpecification`, `PromptRevision`, and `PromptSetRevision` are immutable registered inputs. Each has a stable logical ID, revision, canonical content hash, author, timestamp, and one atomic registration audit entry. A reference resolves only when all three values match, so resolution works after a process restart.

`EntropySourceSpecification` records a redacted declared capability. Attempt evidence separately records the capability snapshot actually returned by the resolved adapter. Sensitive configuration names require `$env:NAME` references; raw credential values are rejected. Raw entropy bytes are never persisted.

`ExperimentCondition` is an immutable value in an `ExperimentRevision`. It pins the source and policy references, includes a researcher-facing and optional blinded label, allocation count, and condition hash. The MVP requires one deterministic PRNG control plus at least one OS/hardware/QRNG condition. Equivalent implementation/configuration pairs are rejected as distinct conditions.

Plans use a deterministic, separately seeded assignment shuffle. The assignment seed, strategy, hash, and unique slot identifiers are stored in the revision; entropy streams never select their own condition or slot.

## Execution

The CLI's `experiment register` command registers source records, prompts, a prompt set, a seed-derivation policy, hypothesis, and experiment revision. Registration validates all pinned references. `preflight` resolves each input independently, compares declared and observed source capability, validates the seed patch, and checks LM Studio reachability/model availability.

`run start` is sequential through the inline local scheduler. `run resume` skips slots with a successful terminal attempt, retaining immutable failed attempts and their retry lineage. `run pause` and `run cancel` are cooperative boundaries between trials.

Every attempt records the condition ID, source reference, prompt revision reference, rendered-prompt hash/snapshot, source snapshot, policy application, model/runtime/software snapshots, request/response or structured terminal failure. LM Studio seed use is explicitly **best effort**, not guaranteed determinism.

## Analysis and review

`analyze baseline` creates a new immutable analysis run and digest-verified JSON and Markdown artifacts. It reports descriptive counts, response/token/latency distributions, duplicate responses, lexical frequencies, and source/policy condition counts. It does not make causal or hypothesis-support claims.

The workspace is localhost-only, read-only, and consumes persisted SQLite read models. It cannot access schedulers, providers, or entropy adapters.

## Blind review

`export blind` writes condition hashes and blinded labels. `export reveal-map` is separate and should remain withheld until the planned review point. Neither changes scientific records.
