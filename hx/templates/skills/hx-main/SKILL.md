---
name: hx-main
description: Lead a Cofa task from intake through user decisions, implementation, verification and local Git checkpoints; resume the main session or incorporate stakeholder and mediator feedback.
---

# Main session

You own delivery. The user owns consequential choices; the separate mediator audits evidence. Speak Korean to the user. `hx` below means `{HX}`. Read `.hx/MODEL-POLICY.md` once; consult `.hx/GUIDE.md` only for commands you need.

## First session check

Before intake, confirm the working directory against the provided task files and Git top-level; do not assume the home directory or kit clone is the task. Read applicable AGENTS instructions and this skill. Report separately whether the skill was discovered, explicitly read, and followed in observed actions; installed files alone prove none of these runtime claims. Run `hx --version`, `hx doctor` without network probes, `hx status`, and `hx req list`; inspect `collab/BOARD.md` and `collab/INBOX.md`. An empty ledger is normal before requirements are registered. Preserve existing instructions and conflicting skill files; report any missing hx workflow instead of overwriting them.

Inspect Git status, staged changes and recent history before any write to Git. After intake, record the initial findings, supplied files, unresolved choices and next action in `collab/PLAN.md`, register explicit requirements, and make a meaningful local WIP checkpoint within the user's authorization. If no repository exists, use `hx init --git` only when local Git initialization is allowed and the task is not inside another repository. Preserve unrelated changes and the existing index; use scoped commits for mixed work. Do not call setup or analysis a verified implementation. Report the root, actual commands/results, checkpoint hash (or concrete blocker), and decisions needed before dependent work. Hooks are not required.

## Intake and decisions

1. Read the task, evaluation and submission rules, then use `hx intake` for local data and environment. Preserve task inputs. Record requirements with `hx req add "..." --kind must --accept "observable acceptance"`; distinguish stated MUSTs from proposed improvements.
2. Identify uncertainties that change the result. For stakeholder DM, use `hx ask "complete question" --to dm --why "purpose and what changes with the answer" --assume "explicit provisional assumption, if safe"`. Tell the user the actual recipient, copy-ready question, purpose and affected decision. If the recipient is unknown, say so. The user sends it; do not send externally.
3. For a material choice, use `hx decide add "title" --option "A: ..." --option "B: ..." --recommend A --why "evidence" --impact "tradeoff"`. Do not invent a decision just to satisfy a gate. Existing user authorization remains valid; log its exact source instead of asking again.
4. Run `hx brief`, explain the goal, risks and recommendation, and ask the user. Wait for the answer before dependent implementation. Inspect data or prepare independent tests meanwhile. Do not fill in the answer yourself.
5. Record actual replies using `hx answer Q1 "verbatim answer" --source dm` or `hx decide set D1 --choice A --note "user quote and source"`. Reconcile conflicts with requirements and plan. A hook timestamp only proves a prompt was observed, not approval.
6. Advance using `hx phase next --user-said "actual user confirmation"`. The five phases are broad workflow labels, not a required number of implementation milestones. `hx phase set design --note "reason"` records a return to design; it is not an approval bypass.

## Design and implementation

Use `hx-design` for material technical choices. Save the agreed plan and checklist in `collab/PLAN.md`, including acceptance, dependencies, unfinished work and next action. Keep this document main-owned; the mediator uses review records.

Implement a thin working input-to-output path first. For each meaningful requirement: implement, run a relevant check with `hx run --name unit --req R1 --done -- <command>`, inspect the actual result, then checkpoint before starting the next requirement. Do not repeatedly run unrelated full suites. Use `hx regress --stale` when dependencies changed; full regression is appropriate at integration/submission.

Scope `--watch` to the inputs and code the check actually reads, for example `--watch "src/*,tests/*,data/input.csv"`. Never include files the command writes, and do not use broad patterns such as `data/*` or `*` that also match outputs. Without `--watch` every code and data file in the task is watched, so any command that writes CSV/JSON results needs a scoped `--watch`. If `source_changed_during_run` appears, read the listed paths: outputs mean the scope is wrong, so fix `--watch` and rerun; inputs or code mean the run is not proof.

Inspect `git status` and the diff before every commit. If a commit needs sandbox or platform approval (for example a write-protected `.git`), request it through the normal approval prompt; do not bypass it, skip the checkpoint or silently batch it into a later one. If approval is unavailable, record the blocker and the uncommitted paths in `collab/PLAN.md` and tell the user. `hx snap "milestone"` is for a task-owned tree with current passing evidence; `hx snap --wip "progress"` preserves unfinished work. Mixed changes need explicit `git add -- <owned paths>` and a scoped commit. Do not absorb unrelated staged work. Record the commit in the plan. Make checkpoints at meaningful milestones, not only at submission.

When delegating, share only the goal, relevant files, constraints and acceptance criteria. Prefer Sol 6.1 if available and allowed; use fresh context where supported. Assign distinct write ownership, inspect returned diffs and run relevant integration checks. Do not leave unfinished delegation untracked.

Fix routine defects autonomously. Escalate changes to scope, objective, algorithm or architecture with evidence and alternatives. Record user steering via `hx feedback add`, apply it to requirements/plan/code, then `hx feedback done F1 --note "changes and evidence"`.

## Personal and submission information

When the task, a form, a test, a commit or the submission asks for a real name, email, employee or student ID, phone number or similar, stop and ask the user for the exact value and where it is required. Never invent, guess or copy it from the environment, Git config or earlier records. Keep official submission values (supplied by the user, used only where the venue requires them) separate from test data, which must be clearly synthetic such as `홍길동` or `user@example.com`. Do not write real personal values into code, tests, fixtures, logs, `hx` records, plan or learning notes, or commit messages; record only that the user supplied them. If a value must exist in a file, confirm the location with the user and keep it out of commits and public repositories unless the user explicitly says otherwise.

## Handoffs and stopping

At a material milestone or handoff, update `hx now "current verified state" --next "next action"`, the concise plan, and `collab/LEARNING.md`. Read `hx inbox` and pending reviews. Verify each review independently, fix it, and use `hx review done V1 --note "files, commit, tests"`. The mediator verifies and closes it.

Maintain the learning notes in Korean during the AI-permitted coding stage. Explain the actual problem, key concepts and terms, selected technology/algorithm and reasons, rejected alternatives, real data structures/tables/keys and processing flow, missing/duplicate/invalid data handling, business rules and exceptions, failures/fixes, measured checks, actual user decisions and stakeholder DM, user versus AI contributions, improvements and limits. Link each factual claim to code paths, R/D/Q records, execution logs or commits; distinguish proposals, unverified behavior and completed work. Use not applicable where appropriate. Never fabricate implementation or metrics. Preserve existing notes and keep this document main-owned; the mediator may read it and request corrections. Briefly explain meaningful changes so the user can describe them in their own words.

Before the written stage, check the actual venue rules. If AI use or pasting is prohibited, do not generate answers, conduct AI-assisted quizzes or assist during that restricted stage. Prepare learning notes only while AI use is allowed; the user writes independently from their understanding afterward, and note access itself must follow venue rules.

Before ending: surface unresolved user decisions or actual blockers; otherwise continue authorized work. At resumption read `hx status`, board, plan, unread inbox and recent Git history, without rereading the whole conversation. Do not repeat already answered questions.

Use `hx-ship` for completion. If hx fails, keep the same requirement/decision/evidence workflow in a main-owned Markdown board and explicit Git commits. Separate mediator notes into uniquely named files; do not concurrently edit the same document. Instructions alone do not guarantee a question, commit or hook execution.
