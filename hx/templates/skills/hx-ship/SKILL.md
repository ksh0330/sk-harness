---
name: hx-ship
description: Verify a completed implementation or a near-deadline deliverable against original requirements, real execution, test evidence, Git and Cofa submission rules.
---

# Final verification

`hx` means `{HX}`. Use `.hx/MODEL-POLICY.md`; do not reduce core verification to save tokens. Avoid new optional features at this stage.

1. Follow the README from a clean start. Verify exact output names, formats and locations. For a UI, check input, processing, persistence/reload and error paths. If interactive observation is unavailable, mark it unverified and give the user a concrete check; do not report it as passed.
2. Match every original requirement and acceptance condition with actual outputs and meaningful tests. Audit the tests themselves: wrong expectations, no assertions, zero/all-skipped tests and stale inputs can yield misleading success.
3. Run `hx gate --final` once after final code changes. Inspect any failure and rerun affected checks after fixing it. High-severity review items need mediator closure. Pending material decisions need real user answers. Gate PASS covers registered evidence, not omitted requirements or all product behavior.
4. Inspect `git diff` and status. Commit only owned changes. Checkpoint tested code with `hx snap "validated milestone"` only if the whole task tree is yours; otherwise use explicit Git paths. Re-render the board after the commit so its HEAD is current. Verify the live Git state, since a tracked board cannot contain its own future commit hash.
5. Use `hx ship --no-run` after the verified final gate to avoid an identical repeat. Review `collab/REPORT.md` against the source evidence and write a concise Korean README describing startup, tests, assumptions and remaining limits.
6. Confirm current Cofa submission instructions and size from supplied authoritative material. Git ignore rules do not exclude files from an uploaded folder. Do not remove inputs, publish, push or submit externally without the applicable authorization. Keep organizer-provided tests and private evaluation expectations out of solver prompts.
7. Reconcile the Korean `collab/LEARNING.md` with the final code, actual decisions/DM and checks. Explain choices, alternatives, data handling, exceptions, user/AI contributions and limits while AI use is allowed. If the written stage bans AI or pasting, stop AI assistance at that transition; the user writes independently and follows any restrictions on reading notes.

Report implemented behavior, executed checks and results, commit, remaining work and unverified Cofa behavior. A real user-participation rehearsal is distinct from an automated simulation. Never state that instructions guarantee user questions, automatic commits or hook execution.
