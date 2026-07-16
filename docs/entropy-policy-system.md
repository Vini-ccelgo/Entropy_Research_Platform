# Entropy Policy System

An immutable `EntropyPolicySpecification` is registered with a logical ID,
revision, content hash, author, timestamp, and audit entry. Trials pin its
exact reference; durable registry resolution verifies that reference before
sampling.

The only supported policy is `derive_model_seed` v1. It selects a declared byte
range, applies declared byte order, converts it to an unsigned integer seed,
and returns a typed `SeedPatch`. Policies receive only immutable sample/spec
inputs and cannot access persistence, providers, clocks, filesystems, networks,
or schedulers.

Preflight verifies the pinned specification, source maximum-byte capability,
requested range, model seed capability, and seed-only target. Each application
records policy/version/configuration hash, entropy hash, source capabilities,
byte range/order, transformation, output commitment, and applied request field.
It is embedded in the terminal `TrialExecution` finalized atomically with the
attempt state and control event.

Raw entropy is never persisted. Failures retain successfully captured partial
provenance and explicit unavailable reasons. LM Studio seed support remains
best-effort: a seed does not guarantee deterministic output across runtimes or
hardware.
