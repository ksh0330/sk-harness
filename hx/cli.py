"""Command line for the hx kit. Exit codes: 0 ok, 1 a check failed, 2 usage or input error."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__, check, collab, doctor, hooks, intake, ledger, profile, project, smoke, snap, util
from .tableio import TableError, load_table

# Commands that only read: they do not refresh the shared board (a mediator must be able to look without writing).
READ_ONLY = {"doctor", "profile", "check", "status", "audit", "smoke", "hook", "inbox-peek"}


def _parser():
    parser = argparse.ArgumentParser(prog="hx", description="Collaboration kit for a time-boxed task: requirements, user "
                                     "decisions, evidence, checkpoints, shared board. Standard library only.")
    parser.add_argument("--root", help="task folder (default: nearest folder with .hx, else the current folder)")
    parser.add_argument("--version", action="version", version=f"hx {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="prepare this folder (.hx state, AGENTS.md, Codex skills, shared board)")
    p.add_argument("--deadline", help="deadline as HH:MM Korean time, e.g. 16:00")
    p.add_argument("--git", action="store_true", help="git init + baseline commit if this is not a repository (local only)")
    p.add_argument("--hooks", action="store_true", help="also write .codex/hooks.json (approve once with /hooks in Codex)")
    p.add_argument("--no-agents", action="store_true", help="do not create AGENTS.md or .agents/skills")

    p = sub.add_parser("doctor", help="what can this machine run right now")
    p.add_argument("--net", action="store_true", help="also test TCP reachability of common hosts")
    sub.add_parser("intake", help="inventory of the task folder: documents as text, data summary, code, environment")

    p = sub.add_parser("profile", help="schema, types, missing, duplicates, outliers, cross-file references")
    p.add_argument("files", nargs="+", help="csv/tsv/json/jsonl/xlsx/sqlite; file.xlsx#Sheet or file.db#table")
    p.add_argument("--max-rows", type=int, default=200000, help="rows to read per file (0 = all)")
    p.add_argument("--encoding")
    p.add_argument("--delimiter")
    p.add_argument("--header-row", type=int, help="1-based row that holds the column names")
    p.add_argument("--no-save", action="store_true", help="print only; do not write .hx/profile")

    p = sub.add_parser("check", help="run integrity rules (rules.json) or draft them from data")
    p.add_argument("target", nargs="+", help="rules.json, or data files together with --draft")
    p.add_argument("--draft", action="store_true", help="infer starter rules from the given data files")
    p.add_argument("-o", "--output", help="where to write the draft (default: rules.json)")
    p.add_argument("--force", action="store_true", help="overwrite an existing draft file")

    p = sub.add_parser("req", help="requirement ledger")
    req = p.add_subparsers(dest="action", required=True)
    a = req.add_parser("add")
    a.add_argument("text", nargs="?")
    a.add_argument("--kind", default="must", choices=["must", "should", "could"])
    a.add_argument("--accept", default="", help="observable acceptance condition")
    a.add_argument("--file", help="bulk add: lines 'MUST: text => acceptance' / 'Q: question => assumption'")
    s = req.add_parser("set")
    s.add_argument("id")
    s.add_argument("--status", choices=ledger.STATUSES)
    s.add_argument("--kind", choices=["must", "should", "could"])
    s.add_argument("--note")
    s.add_argument("--text")
    s.add_argument("--accept")
    s.add_argument("--decision", help="the user decision (D<n>) that allows dropping or downgrading a MUST")
    req.add_parser("list")

    p = sub.add_parser("ask", help="record a question for the user, or one the user must send to the task stakeholder (--to dm)")
    p.add_argument("text")
    p.add_argument("--assume", default="", help="what you will assume if no answer comes")
    p.add_argument("--to", default="user", choices=["user", "dm"])
    p.add_argument("--why", default="", help="why the answer matters")
    p = sub.add_parser("answer", help="record the answer to a question, verbatim")
    p.add_argument("id")
    p.add_argument("text")
    p.add_argument("--source", choices=["user", "dm"], help="who answered (default: whoever the question was for)")

    p = sub.add_parser("decide", help="decisions: put a choice to the user, record their answer, or log a small one of your own")
    dec = p.add_subparsers(dest="action", required=True)
    a = dec.add_parser("add", help="a choice the user must make")
    a.add_argument("title")
    a.add_argument("--option", action="append", default=[], help="repeat: 'A: what it is, cost, risk'")
    a.add_argument("--recommend", default="")
    a.add_argument("--why", default="")
    a.add_argument("--impact", default="")
    s = dec.add_parser("set", help="record the user's choice")
    s.add_argument("id")
    s.add_argument("--choice", required=True)
    s.add_argument("--note", default="", help="the user's own words")
    g = dec.add_parser("log", help="a small reversible choice made by the agent")
    g.add_argument("title")
    g.add_argument("--choice", required=True)
    g.add_argument("--why", default="")
    sub.add_parser("brief", help="what the user must read and answer now (understanding, questions, pending decisions)")

    p = sub.add_parser("feedback", help="direction-changing feedback from the user")
    fb = p.add_subparsers(dest="action", required=True)
    a = fb.add_parser("add")
    a.add_argument("text")
    d = fb.add_parser("done")
    d.add_argument("id")
    d.add_argument("--note", required=True)
    sub.add_parser("inbox", help="show the part of collab/INBOX.md not read yet and mark it read")

    p = sub.add_parser("phase", help="show the phase, close it (next) or move to another one (set)")
    p.add_argument("action", nargs="?", choices=["next", "set"])
    p.add_argument("target", nargs="?", choices=collab.PHASES)
    p.add_argument("--note", default="")
    p.add_argument("--user-said", default="", help="the user's confirmation, quoted")
    p.add_argument("--force", default="", help="skip unmet conditions; give the user's explicit instruction")
    p = sub.add_parser("now", help="say what is being worked on (shown on the board)")
    p.add_argument("doing")
    p.add_argument("--next", default=None)

    p = sub.add_parser("run", help="run a command as evidence:  hx run --name unit --req R1 -- python -m unittest")
    p.add_argument("--name", required=True, help="check name; re-running the same name replaces the saved command")
    p.add_argument("--req", help="comma-separated requirement ids this run proves")
    p.add_argument("--sh", help="command as one shell string instead of `-- cmd args`")
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--expect", help="regex that must appear in the output")
    p.add_argument("--metric", action="append", default=[], help="NAME=REGEX with one capture group holding a number")
    p.add_argument("--watch", help="comma-separated globs; the proof goes stale only when matching files change")
    p.add_argument("--tail", type=int, default=30, help="output lines to echo (the full log is always saved)")
    p.add_argument("--done", action="store_true", help="when the run passes, mark the linked requirements done")

    p = sub.add_parser("regress", help="re-run saved checks")
    p.add_argument("--only", help="comma-separated check names")
    p.add_argument("--stale", action="store_true", help="only checks that are not currently PASS")
    p.add_argument("--no-record", action="store_true", help="run and report without writing evidence (for a reviewer)")
    p = sub.add_parser("forget", help="remove a saved check")
    p.add_argument("name")
    p = sub.add_parser("gate", help="mechanical completion check (exit 0 only when nothing blocks)")
    p.add_argument("--final", action="store_true", help="re-run all checks first")
    sub.add_parser("status", help="time left, requirements and proof state, decisions, reviews")
    p = sub.add_parser("ship", help="final check, lints and the submission report collab/REPORT.md")
    p.add_argument("--no-run", action="store_true", help="do not re-run the checks first")

    p = sub.add_parser("smoke", help="start server, probe endpoints, stop server (spec.json)")
    p.add_argument("spec")

    p = sub.add_parser("snap", help="checkpoint: verified state gets tag hx-ok-N; --wip commits without a tag")
    p.add_argument("label", nargs="?", default="")
    p.add_argument("--wip", action="store_true", help="commit work in progress without an ok-tag")
    p = sub.add_parser("back", help="return to the last checkpoint; the abandoned state is kept on a branch")
    p.add_argument("--to", help="checkpoint tag (default: latest hx-ok-N)")
    p.add_argument("--yes", action="store_true", help="actually do it (default is a dry run)")

    sub.add_parser("audit", help="for a reviewer: where the ledger and reality (git, evidence, files) disagree; changes nothing")
    p = sub.add_parser("review", help="review items from the mediator session")
    rv = p.add_subparsers(dest="action", required=True)
    a = rv.add_parser("add")
    a.add_argument("text")
    a.add_argument("--severity", default="med", choices=collab.SEVERITIES)
    a.add_argument("--evidence", default="")
    a.add_argument("--ask", default="", help="what the main session should do")
    for name, text in (("done", "main session: handled, say how"), ("close", "mediator: verified"), ("reopen", "mediator: not fixed")):
        r = rv.add_parser(name, help=text)
        r.add_argument("id")
        r.add_argument("--note", default="")
    rv.add_parser("prompt", help="a prompt to paste into the main session")

    p = sub.add_parser("hook", help="Codex hook entry point (reads the hook JSON on stdin)")
    p.add_argument("event", choices=sorted(hooks.HANDLERS))
    sub.add_parser("allow", help="after the user approved a command the hook blocked: let it through once")

    p = sub.add_parser("new", help="scaffold")
    p.add_argument("what", choices=["app"])
    p.add_argument("--dir", default="app")
    p.add_argument("--port", type=int, default=8765)
    return parser


def _profile(args, root):
    tables, names = [], set()
    for spec in args.files:
        table = load_table(spec, max_rows=args.max_rows or None, encoding=args.encoding,
                           delimiter=args.delimiter, header_row=args.header_row)
        base, n = table.name, 2
        while table.name in names:
            table.name, n = f"{base}_{n}", n + 1
        names.add(table.name)
        tables.append(table)
    profiles = [profile.profile_table(table) for table in tables]
    related = profile.relations(tables, profiles) if len(tables) > 1 else []
    parts = [profile.render(item) for item in profiles]
    if related:
        parts.append(profile.render_relations(related))
    text = "\n\n".join(parts)
    print(text)
    tally = {"high": 0, "med": 0, "info": 0}
    for item in profiles:
        for level, _, _ in item["findings"]:
            tally[level] += 1
    tally["high"] += sum(1 for item in related if item.get("orphans"))
    saved = ""
    if not args.no_save:
        folder = util.state_dir(root, "profile")
        for item in profiles:
            util.write_json(folder / f"{item['name']}.json", item)
        util.write_text(folder / "last.md", text + "\n")
        if related:
            util.write_json(folder / "_relations.json", related)
        saved = f"  saved={util.rel(folder, root)}/"
    print(f"\nPROFILE: tables={len(tables)} high={tally['high']} med={tally['med']} info={tally['info']}{saved}")
    return 0


def _check(args, root):
    if args.draft:
        tables = [load_table(spec) for spec in args.target]
        profiles = [profile.profile_table(table) for table in tables]
        related = profile.relations(tables, profiles) if len(tables) > 1 else []
        output = Path(args.output or "rules.json")
        if output.exists() and not args.force:
            raise ValueError(f"{output} exists; use --force or -o another.json")
        spec = check.draft(tables, profiles, related)
        util.write_json(output, spec)
        print(f"DRAFT: {len(spec['rules'])} rule(s) written to {output}. They describe the data as it is; "
              f"edit them to the business rules, then run: hx check {output}")
        return 0
    if len(args.target) != 1:
        raise ValueError("give exactly one rules.json (or use --draft with data files)")
    path = Path(args.target[0])
    results, failed = check.run_rules(check.read_rules(path), path.resolve().parent)
    print(check.render(results))
    return 1 if failed else 0


def _req(args, root):
    if args.action == "add":
        if args.file:
            added = ledger.add_from_file(root, args.file)
            for item in added:
                print(f"added {item['id']} [{item['kind']}] {item['text']}")
            print(f"REQ: {len(added)} item(s) added")
        elif args.text:
            item = ledger.add_req(root, args.kind, args.text, args.accept)
            print(f"added {item['id']} [{item['kind']}] {item['text']}"
                  + ("" if item["accept"] else "  (no --accept: how will it be observed?)"))
        else:
            raise ValueError("give the requirement text or --file")
    elif args.action == "set":
        item = ledger.set_req(root, args.id, args.status, args.note, args.text, args.accept, args.kind, args.decision)
        print(f"{item['id']} [{item['kind']}] status={item['status']}")
        if args.status == "done":
            proof, linked = ledger.compute(root)["proof"][item["id"]]
            if proof != "PASS":
                print(f"  note: proof is {proof} ({', '.join(linked) or 'no linked check'}); the gate will block "
                      f"until `hx run --req {item['id']}` passes on the current source")
    else:
        text, _ = ledger.render_status(root)
        print(text)
    return 0


def _decide(args, root):
    if args.action == "add":
        item = ledger.add_decision(root, args.title, args.option, args.recommend, args.why, args.impact)
        print(f"added {item['id']} (pending, the user decides): {item['text']}\n"
              f"  now run `hx brief`, show it to the user and stop. Do not implement anything that depends on {item['id']} yet.")
    elif args.action == "set":
        item = ledger.decide(root, args.id, args.choice, args.note)
        print(f"{item['id']} decided by the user: {item['choice']}" + ("" if item["confirmed"] else
              "  (no hook saw the user's message; make sure these really are the user's words)"))
    else:
        item = ledger.log_decision(root, args.title, args.choice, args.why)
        print(f"logged {item['id']} (decided by the agent): {item['text']} -> {item['choice']}")
    return 0


def _phase(args, root):
    if args.action == "next":
        current, target = collab.phase_next(root, args.note, args.user_said, args.force)
        print(f"PHASE: {current} -> {target}")
        collab.write_board(root)
        if collab.git_facts(root).get("repo"):
            head, staged = snap.commit_all(root, f"[hx-phase] {current} done -> {target}" + (f": {args.note}" if args.note else ""))
            print(f"  checkpoint {head} ({len(staged)} file(s))" if head else "  nothing new to commit")
        else:
            print("  not a git repository: nothing was preserved (hx init --git)")
    elif args.action == "set":
        if not args.target:
            raise ValueError("hx phase set <phase> --note \"why\"")
        print(f"PHASE: now {collab.phase_set(root, args.target, args.note)}")
    else:
        print(f"PHASE: {collab.phase(root)} ({' -> '.join(collab.PHASES)})")
        for reason in collab.phase_blockers(root, "?"):
            print(f"  to close it: {reason}")
    return 0


def _review(args, root):
    if args.action == "add":
        item = collab.review_add(root, args.text, args.severity, args.evidence, args.ask)
        print(f"added {item['id']} [{item['severity']}] open. Hand it to the main session: `hx review prompt`")
    elif args.action == "prompt":
        print(collab.review_prompt(root))
    else:
        status = {"done": "handled", "close": "closed", "reopen": "open"}[args.action]
        item = collab.review_set(root, args.id, status, args.note)
        print(f"{item['id']} -> {item['status']}")
    return 0


def _dispatch(args, command, root):
    name = args.command
    if name == "init":
        print(project.init(root, args.deadline, args.git, not args.no_agents, args.hooks))
    elif name == "doctor":
        return 1 if doctor.run(args.net) else 0
    elif name == "intake":
        print(intake.intake(root))
    elif name == "profile":
        return _profile(args, root)
    elif name == "check":
        return _check(args, root)
    elif name == "req":
        return _req(args, root)
    elif name == "ask":
        item = ledger.add_question(root, args.text, args.assume, args.to, args.why)
        print(f"added {item['id']} ({'for the stakeholder, via the user' if args.to == 'dm' else 'for the user'}) assume={item['assume'] or '-'}")
    elif name == "answer":
        item = ledger.answer(root, args.id, args.text, args.source)
        print(f"{item['id']} answered by {'the stakeholder (DM)' if item['source'] == 'dm' else 'the user'}; "
              f"now update the requirements/plan it affects")
    elif name == "decide":
        return _decide(args, root)
    elif name == "brief":
        text, pending, questions = ledger.brief(root)
        collab.mark_brief(root)
        print(text)
        print(f"BRIEF: {pending} decision(s) and {questions} question(s) for the user. Show the text above, then end your turn and wait.")
    elif name == "feedback":
        if args.action == "add":
            item = ledger.add_feedback(root, args.text)
            print(f"added {item['id']}: assess what it changes (requirements, decisions, plan, code), apply it, then `hx feedback done {item['id']} --note ...`")
        else:
            print(f"{ledger.close_feedback(root, args.id, args.note)['id']} done")
    elif name == "inbox":
        text = collab.inbox_read(root)
        print(text if text else "INBOX: nothing new")
        if text:
            print("\nINBOX: marked as read. Record what it changes: hx answer / hx decide set / hx feedback add / hx review done")
    elif name == "phase":
        return _phase(args, root)
    elif name == "now":
        collab.set_now(root, args.doing, args.next)
        print("noted")
    elif name == "run":
        if bool(command) == bool(args.sh):
            raise ValueError("give the command either after `--` or with --sh \"...\" (exactly one)")
        metrics = {}
        for spec in args.metric:
            key, _, pattern = spec.partition("=")
            if not key or not pattern:
                raise ValueError(f"--metric expects NAME=REGEX, got {spec!r}")
            metrics[key] = pattern
        reqs = [part.strip() for part in args.req.split(",") if part.strip()] if args.req is not None else None
        watch = [part.strip() for part in args.watch.split(",") if part.strip()] if args.watch is not None else None
        record = ledger.run_check(root, args.name, args.sh or command, reqs, args.timeout, args.expect,
                                  metrics or None, args.tail, watch=watch)
        if args.done and record["ok"] and "weak" not in record["flags"]:
            for req_id in record["reqs"]:
                ledger.set_req(root, req_id, status="done")
            print(f"marked done: {', '.join(record['reqs']) or '(no --req given)'}")
        return 0 if record["ok"] else (record["exit"] or 1)
    elif name == "regress":
        only = [part.strip() for part in args.only.split(",")] if args.only else None
        return 1 if ledger.regress(root, only, stale=args.stale, record=not args.no_record) else 0
    elif name == "forget":
        ledger.forget(root, args.name)
        print(f"forgot check {args.name}")
    elif name == "gate":
        return 0 if ledger.gate(root, args.final) else 1
    elif name == "status":
        text, _ = ledger.render_status(root)
        facts = collab.git_facts(root)
        text += f"\nphase: {collab.phase(root)}\n"
        if facts.get("repo"):
            last = facts["last"]
            text += (f"git: branch {facts['branch']}, {len(facts['dirty'])} uncommitted file(s), last checkpoint "
                     + (f"{last['hash']} {last['subject']}" if last else "none yet (hx snap)") + "\n")
        print(text)
    elif name == "ship":
        return 0 if intake.ship(root, rerun=not args.no_run) else 1
    elif name == "smoke":
        return 0 if smoke.run(args.spec) else 1
    elif name == "snap":
        collab.write_board(root)
        print(snap.snap(root, args.label, args.wip))
    elif name == "back":
        print(snap.back(root, args.to, args.yes))
        return 0 if args.yes else 2
    elif name == "audit":
        collab.audit(root)
    elif name == "review":
        return _review(args, root)
    elif name == "allow":
        print(f"allowed once: {hooks.allow(root)}")
    elif name == "new":
        print(project.new_app(root, args.dir, args.port))
    return 0


def main(argv=None):
    util.setup_console()
    argv = list(sys.argv[1:] if argv is None else argv)
    command = None
    if "--" in argv:
        cut = argv.index("--")
        argv, command = argv[:cut], argv[cut + 1:]
    args = _parser().parse_args(argv)
    if args.command == "hook":
        return hooks.main(args.event)
    if command is not None and args.command != "run":
        print("hx: error: `--` is only used by `hx run`", file=sys.stderr)
        return 2
    # `init` always targets the given/current folder; other commands find the initialised ancestor.
    root = Path(args.root or ".").resolve() if args.command == "init" else util.find_root(args.root)
    try:
        code = _dispatch(args, command, root)
        quiet = args.command in READ_ONLY or (args.command == "regress" and args.no_record) \
            or (args.command == "review" and args.action == "prompt")
        if not quiet:
            collab.write_board(root)
        return code
    except (TableError, ValueError, snap.SnapError, OSError, json.JSONDecodeError) as exc:
        print(f"hx: error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("hx: interrupted", file=sys.stderr)
        return 130
