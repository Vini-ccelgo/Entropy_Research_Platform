# Fixed-Continuation Conversation Pilot

The conversation pilot is a fixed, non-agentic protocol. Each trajectory begins
with one registered user instruction and each later turn uses the same registered
continuation instruction. The only dynamic content is a prior model response,
preserved exclusively as an `assistant` chat message in the ordered provider
request.

Every `ConversationTurnPlan` pins its trajectory, condition, turn index, parent
slot, instruction revision, context policy, and budget. A child cannot execute
until its parent has a successful persisted execution in the same run. Resume
reconstructs the request from that evidence rather than process memory.

`ConversationTurnEvidence` persists the complete ordered messages actually sent,
parent execution ID, transcript/request hashes, context estimate, and policy.
Only `reject_if_exceeds_budget` is implemented. It rejects an over-budget turn
before provider invocation; it never truncates or summarizes history.

The six-turn pilot uses a declared 8192-token context budget, conservatively
preflighted against six 256-token outputs. Exact tokenizer accounting remains
provider-dependent. LM Studio seed use remains best-effort: the deterministic
condition describes the PRNG source and seed derivation, not deterministic text.
