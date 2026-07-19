# macOS Handoff and Continuation Guide

## Project state

The project is in local live pretesting, after Milestones 0–5. The immediate
purpose is to finish the interrupted **mixed response-space question pretest**
and inspect its descriptive output before any expanded conversation execution.

Do not modify or delete existing scientific records, SQLite databases,
configurations, partial analyses, or exports during migration. Copy the project
directory and retain its relative paths.

## Runtime requirements

- Python **3.11 or newer** is required. The application intentionally uses
  `datetime.UTC` and exits early on unsupported versions.
- On the original Linux host, the supported interpreter was `/usr/bin/python`
  (Python 3.13). On macOS, use a Python 3.11+ virtual environment or an
  explicitly selected supported interpreter.
- From the repository root, set:

  ```bash
  export ERP_PYTHON="$(command -v python3)"
  export PYTHONPATH=.
  "$ERP_PYTHON" --version
  "$ERP_PYTHON" -m pip install -r requirements.txt
  ```

- Run all commands from the repository root.

## LM Studio requirements

Configure and load this exact local model in LM Studio:

- Model identifier: `dolphin3.0-llama3.1-8b`
- Artifact SHA-256:
  `a7f0539a32e5048aca2e03276e224a5de1bad1a907381608876b88eed7ce80ae`
- API endpoint: `http://127.0.0.1:1234/v1`

The adapter records LM Studio seed support as **best-effort**. A deterministic
PRNG condition means a reproducible entropy-source/derived-seed sequence; it
does not guarantee identical generated text.

Before execution, confirm the local server is reachable:

```bash
curl -s http://127.0.0.1:1234/v1/models
```

The output must include `dolphin3.0-llama3.1-8b`.

## Important paths

These paths are relative to the repository root unless noted otherwise:

- Completed smoke evidence: `database/live-smoke-20260718.db`
- Interrupted mixed-question pretest: `database/mixed-question-pretest-live.db`
- Reduced conversation validation: `database/conversation-reduced-live.db`
- Registered, not yet executed expanded conversation protocol:
  `database/self-directed-conversation-expanded-live.db`
- Mixed pretest protocol:
  `config/experiments/mixed-question-pretest.json`
- Expanded conversation protocol:
  `config/experiments/self-directed-conversation-expanded.json`
- Existing partial exports: `exports/mixed-question-pretest-*`
- Existing partial analysis log: `logs/mixed-question-pretest-analysis.json`
- Generated analysis artifacts: `reports/artifacts/`

## Mixed-question pretest: current evidence

Experiment revision reference:

```text
e1b8b19c-8b30-492d-94b4-b9b34b514be1:1:713094839e5b92494466e9ab9aa06b40e83076793c50db3cf69a69ff54f619ae
```

Run ID:

```text
5dfc2e63-ed42-4ec5-9151-33adc9827353
```

Current terminal state after restart reconciliation:

- 22 completed executions
- 2 terminal failures
- 32 unattempted planned slots

The run is currently `failed` deliberately, which makes it resumable. The two
terminal failures remain immutable evidence under the registered retry policy
(`max_attempts=1`); they must not be retried within this run.

### Terminal failure 1: provider error

- Trial slot / specification ID: `df463e0b-b1e6-4e4c-a9ab-b121f222fb3a`
- Condition: operating-system entropy
- Category: `provider`
- Error: HTTP 400 from LM Studio `/v1/chat/completions`
- Prompt: `What changes a person?`
- Recorded request used `max_tokens=512` and preserved prompt, entropy-policy,
  seed, and model provenance.

The persisted provider error did not include an HTTP response body, so its exact
LM Studio explanation is unavailable. Do not infer a cause from this record.

### Terminal failure 2: process interruption

- Trial slot / specification ID: `742d7b2a-2093-4c41-8f81-0b5f94590a13`
- Category: `interrupted`
- Error: process restart before terminal provider evidence was captured

It was reconciled through `run recover` into immutable failed execution evidence.

## Resume the existing mixed-question run

Set the identifiers once:

```bash
export DB=database/mixed-question-pretest-live.db
export CFG=config/experiments/mixed-question-pretest.json
export RUN_ID=5dfc2e63-ed42-4ec5-9151-33adc9827353
export EXPERIMENT_REF=e1b8b19c-8b30-492d-94b4-b9b34b514be1:1:713094839e5b92494466e9ab9aa06b40e83076793c50db3cf69a69ff54f619ae
```

Resume exactly this existing run:

```bash
"$ERP_PYTHON" main.py --database "$DB" --config "$CFG" \
  run resume "$RUN_ID" --experiment "$EXPERIMENT_REF" \
  | tee logs/mixed-question-pretest-resumed.json
```

The resume operation schedules only the 32 unattempted slots. Successful slots
are not duplicated. The expected final attempt totals are:

- 54 `succeeded`
- 2 `failed`
- no `running`, `planned`, or `scheduled` attempts

The run’s final operational state should remain `failed`, accurately reflecting
the two immutable terminal failures.

## Verification commands

Run status:

```bash
"$ERP_PYTHON" main.py --database "$DB" --config "$CFG" run status "$RUN_ID"
```

Attempt totals:

```bash
sqlite3 "$DB" "
SELECT state, COUNT(*)
FROM trial_attempts
WHERE experiment_run_id = '$RUN_ID'
GROUP BY state;
"
```

No duplicate successful slot may exist:

```bash
sqlite3 "$DB" "
SELECT trial_spec_id, COUNT(*) AS successful_attempts
FROM trial_attempts
WHERE experiment_run_id = '$RUN_ID' AND state = 'succeeded'
GROUP BY trial_spec_id
HAVING COUNT(*) > 1;
"
```

The duplicate query must return no rows.

## Final analysis and exports

Do not overwrite partial outputs. Use the `final` names below:

```bash
"$ERP_PYTHON" main.py --database "$DB" --config "$CFG" \
  analyze baseline "$RUN_ID" \
  | tee logs/mixed-question-pretest-final-analysis.json

"$ERP_PYTHON" main.py --database "$DB" --config "$CFG" \
  export readable-results "$RUN_ID" \
  exports/mixed-question-pretest-final-revealed.json

"$ERP_PYTHON" main.py --database "$DB" --config "$CFG" \
  export readable-results "$RUN_ID" \
  exports/mixed-question-pretest-final-blinded.json --blinded

"$ERP_PYTHON" main.py --database "$DB" --config "$CFG" \
  export blind "$EXPERIMENT_REF" \
  exports/mixed-question-pretest-final-blind-map.json

"$ERP_PYTHON" main.py --database "$DB" --config "$CFG" \
  export reveal-map "$EXPERIMENT_REF" \
  exports/mixed-question-pretest-final-reveal-map.json
```

Each readable-results command prints SHA-256 hashes for its JSON and Markdown
output. Preserve those manifests with the exported files.

## Expanded conversation protocol

The expanded conversation protocol is registered separately but must **not** be
executed until the final mixed-question export has received researcher review.

- Configuration: `config/experiments/self-directed-conversation-expanded.json`
- Database: `database/self-directed-conversation-expanded-live.db`
- Design: 4 trajectories per condition, 6 turns each, 48 executions total
- Fixed messages: `Choose any subject and begin.` followed by `Continue.`
- Context policy: `reject_if_exceeds_budget`; complete history is retained and
  never silently truncated or summarized.
- Generation settings: `temperature=0.9`, `top_p=0.95`, `max_tokens=512`,
  timeout 300 seconds.

When approved, preflight it again on the macOS host before execution.

## Known limitations

- The framework’s current LM Studio seed support is best-effort, not proof of
  deterministic generation.
- Raw entropy bytes are intentionally excluded from durable evidence; only the
  entropy value hash and policy application are retained.
- The recorded provider 400 failure does not contain an HTTP response body.
- The inline local scheduler is sequential. After an unclean shutdown, use
  `run recover <run-id>` only when no runner process remains, then resume.
- The mixed run includes two terminal failures and therefore will finish in
  operational state `failed` even after all remaining slots are processed.
- Analysis remains descriptive; it does not make causal claims, inferential
  claims, semantic classifications, or automatic scientific conclusions.
