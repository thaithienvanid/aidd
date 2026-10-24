"""A proposal's go/no-go and sign-off: a person's decisions, written into the proposal's front matter for them to commit.
Asked at their terminal (`aidd proposal decide|sign-off`), or confirmed in a dialog: the MCP tools `decide_proposal`
and `sign_off_proposal`, or aidd-mods' `/aidd decide` and `/aidd sign-off`, each of which reads `--show` first and
records with `--confirmed` exactly what the person saw. An agent never records one: the guard denies it the command."""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

from aidd import config, platforms, workitems
from aidd.cli import arguments
from aidd.cli.commands.confirmations import DECIDED_WHERE, confirmation_problem
from aidd.cli.commands.decide import card, plain


def proposal_decision(args, data: dict) -> int:
    """`aidd proposal decide <proposal> go|no-go` and `aidd proposal sign-off <proposal>`: show what the person
    decides, then record it once they confirm, at their terminal or, with `--confirmed`, in a dialog."""
    path = Path(args.file)
    text = path.read_text(encoding="utf-8")
    shown, key, value = _preview(args, data, text)
    if args.show:
        print(json.dumps(shown, indent=2))
        return 0
    if shown["problems"]:
        raise ValueError(shown["problems"][0])
    rows = [("For", plain(data.get("addressee"), 120)), ("By", plain(shown["by"], 80))]
    if key == "go_no_go":
        rows += [("Decision", shown["decision"]), ("Reason", plain(shown["reason"] or "none given", 240))]
    else:
        rows += [("Means", "it may be sent, as it reads now, with its price, commitments, assumptions, and exclusions")]
    if shown["replaces"]:
        rows.append(("Replaces", plain(shown["replaces"], 240)))
    print(card(f"Proposal {plain(shown['id'], 40)}", shown["title"], rows))
    if (code := _confirmed(args, shown)) is not None:
        return code
    new = workitems.record_decision(text, key, value)
    if errors := workitems.load_object(new, str(path))[2]:
        raise ValueError(f"nothing recorded: the proposal would not load: {errors[0]}")
    path.write_text(new, encoding="utf-8")
    print(f'Recorded {key} in {path.as_posix()}. Commit it: git commit {path.as_posix()} -m "{shown["id"]}: {key.replace("_", " ")}"')
    return 0


def _preview(args, data: dict, text: str) -> tuple[dict, str, dict]:
    """What the person decides (the `--show` JSON, with `problems` when it cannot be recorded), the front-matter key
    it records, and the value it writes there."""
    pid = str(data.get("id"))
    problems: list[str] = []
    who = args.by or _operator_identity(problems)
    cfg = arguments.config_or_none_quiet()
    if who and config.is_agent(who, set(cfg.get("identities", "bots", default=[]) or []) if cfg else set()):
        problems.append(f"{who} is an agent account; a person decides a proposal")
    today = dt.date.today().isoformat()
    h = workitems.proposal_hash(text)
    if args.action == "decide":
        key = "go_no_go"
        if args.decision is None:
            problems.append(f"name the decision: aidd proposal decide {pid} go (or no-go)")
        value = {"decision": (args.decision or "").replace("-", "_"), "by": who, "decided_on": today} | ({"reason": args.reason} if args.reason else {})
    else:
        key = "sign_off"
        if args.decision or args.reason:
            problems.append("sign-off takes no decision and no --reason: it records who signed off which text")
        if (data.get("go_no_go") or {}).get("decision") != "go":
            problems.append(f"{pid} has no go yet: a person decides first, `aidd proposal decide {pid} go`")
        value = {"by": who, "decided_on": today, "hash": h}
    previous = data.get(key)
    shown = {
        "id": plain(pid, 40),
        "path": arguments.repo_relative(Path(args.file).resolve()),
        "title": plain(data.get("title")),
        "addressee": plain(data.get("addressee"), 120),
        "action": args.action,
        "decision": args.decision,
        "reason": plain(args.reason, 240) if args.reason else None,
        "by": who,
        "hash": h,
        "replaces": ", ".join(f"{k} {v}" for k, v in previous.items()) if isinstance(previous, dict) else None,
        "problems": problems,
    }
    return shown, key, value


def _confirmed(args, shown: dict) -> int | None:
    """None once the person said yes: at a terminal no agent started, or in a dialog (`--confirmed`) for exactly the
    decision they saw, or for a sign-off exactly the text's hash. Else the exit code that stops it."""
    pid = shown["id"]
    if args.confirmed is None:
        command = f"aidd proposal {args.action} {pid}" + (f" {args.decision}" if args.decision else "")
        what = f"The go/no-go of {pid}" if args.action == "decide" else f"The sign-off of {pid}"
        question = f"Record {args.decision} on {pid} as {shown['by']}?" if args.action == "decide" else f"Sign off {pid} as {shown['by']}, so it may be sent?"
        platforms.require_person(what, command=command, question=question)
        return None
    if args.by:
        print("error: --by names who decides at a terminal; a dialog's answer is this machine's person. Nothing was recorded", file=sys.stderr)
        return 2
    expected = args.decision if args.action == "decide" else shown["hash"]
    if args.confirmed != expected:
        print(
            f"error: you confirmed {args.confirmed!r}, but this records {expected!r}"
            + (": the proposal changed since you saw it" if args.action == "sign-off" else "")
            + ". Nothing was recorded; look at it again",
            file=sys.stderr,
        )
        return 1
    if problem := confirmation_problem(args.decided_via):
        print(f"error: not recorded: {problem}", file=sys.stderr)
        return 2 if not DECIDED_WHERE.fullmatch(args.decided_via) else 1
    return None


def _operator_identity(problems: list[str]) -> str:
    """Who decides here: `@<GitHub login>` from local git or gh configuration, else `email:<git user.email>`; with
    neither, "" and the problem."""
    if login := config.operator_login(Path(".")):
        return f"@{login}"
    if email := config.operator_email(Path(".")):
        return f"email:{email}"
    problems.append("aidd cannot tell who you are: set git config user.email, or name yourself with --by @you")
    return ""
