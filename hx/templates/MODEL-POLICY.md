# Model, reasoning and usage policy

Local preparation: GPT-6 Astra High for independent audit, verification and fixes. Cofa: GPT-6.1 Sol for main and mediator, and preferably child agents. Actual venue policy and the runtime model list are authoritative; never substitute a forbidden model.

Start substantive work at High. Recommend Low/Medium for lookup, file inventory, status, narrow document edits and repetition. Use High for requirements, planning, ordinary implementation/debugging, technical selection and test design. Use Extra High (`xhigh` where supported) for complex optimization, consequential architecture, conflicting approaches or persistent failures. Do not keep every task at High automatically.

Change reasoning only through an officially supported control exposed in the current runtime and within authorization. The CLI supports user selection through `/model` and invocation-scoped `-c model_reasoning_effort="high"`; supported levels depend on the model. If this session exposes no change tool, briefly recommend the level to the user. Do not edit global config, toggle experimental features or pretend that a written instruction changed the running model. Runtime capability is not venue permission.

Prefer a correct, complete result within time and usage limits over minimum tokens. Token-based contest scoring is unconfirmed. Reuse verified file findings, keep a concise shared state, delegate with minimal context, and rerun tests when changes or unresolved concerns justify them. Preserve security, integrity, core tests and user decisions.

The user starts main and mediator sessions independently. Their conversations, contexts and usage are not automatically shared. Hand off concise facts through shared Markdown, ledger records, actual files and Git. Record only observed per-session usage with its source; do not invent a combined total.

When actual usage is exposed (for example a completed `codex exec --json` turn's usage event), record model, effort, elapsed time, input/cached/output counts, quality result and the source event in the audit log. Missing counts are unknown, not zero. Local command time is not model time. A single run does not establish a causal performance difference; compare matched isolated tasks only when justified by remaining time and available usage. Never invent usage measurements or pricing.
