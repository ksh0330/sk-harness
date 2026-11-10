---
name: hx-design
description: Compare algorithms, stack, architecture and data design for a material task decision or reconsider a failing approach using actual data, constraints and evaluation criteria.
---

# Technical decisions

`hx` means `{HX}`. Read `.hx/MODEL-POLICY.md` if not already loaded. Use High for ordinary design, Extra High only for difficult optimization, consequential architecture or unresolved conflicting approaches; use the supported runtime/user controls.

Define the real business objective, hard constraints, data quality and evaluation metric. Do not assume the first solution or a more complex solution is best. Consider only relevant families:

- Scheduling, assignment, routing or location: greedy baseline, dynamic programming, MILP/CP, local search; capacities, actual road/walking distance and travel time when relevant.
- Prediction or defect detection: statistical/rule baseline, tree/linear models; time/group splits and leakage checks. Neural methods need enough data, resources and benefit.
- Pipelines and reconciliation: keys, validation, idempotency, transactions and recovery.
- Services: end-to-end user flow, storage, concurrent changes, permissions, API contracts and errors.
- Semiconductor tasks: read `.hx/DOMAIN.md` only when needed, then verify task-specific process, equipment, yield or time-series assumptions from provided evidence.

Compare two or three viable approaches, including a simple baseline. Evaluate constraint coverage, measured quality, runtime, available packages, explainability and remaining time. Do not assume external APIs, internet, installations or platform changes are allowed. Use `hx doctor` without network probing by default.

For a consequential user choice, record `hx decide add "decision" --option "A: ..." --option "B: ..." --recommend A --why "data and constraints" --impact "tradeoff"`, show `hx brief`, and wait for the actual reply. Existing explicit choices need no repeat approval. If no material alternative exists, explain that fact instead of inventing one; record the user's authorized plan and any phase exception transparently.

Save the agreed implementation checklist and tests in `collab/PLAN.md`. For relevant risks, specify schema/invariants, empty or malformed inputs, duplicates, concurrency, recovery, API/UI integration and performance. Record routine reversible choices with `hx decide log`. Prefer tests that can detect a real failure over tests that mirror code.

If measured evidence contradicts the chosen approach, preserve the working baseline, explain the impact and ask before a material redesign. Never remove security, integrity or core tests to save tokens.
