"""The commands that read the repository's files and aidd's own data, and change nothing: `aidd validate` and `aidd explain`."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from aidd import knowledge, risk, workitems
from aidd.cli import arguments


def cmd_validate(args) -> int:
    if not args.paths:
        arguments.enter_repo(args)
        errors, warnings = workitems.check_repo(Path("."))
    else:
        found = [e for p in args.paths for e in workitems.validate_file(Path(p))]
        errors = [e for e in found if workitems.is_error(e)]
        warnings = [e for e in found if not workitems.is_error(e)]
    # A note says an expected state, such as a planned Spec's placeholders: it is shown, and it never fails the run.
    notes = [w for w in warnings if w.startswith(workitems.NOTE)]
    warnings = [w for w in warnings if not w.startswith(workitems.NOTE)]
    step = workitems.validate_next_step(errors)
    if args.json:
        warned, noted = [w.removeprefix(workitems.WARNING) for w in warnings], [n.removeprefix(workitems.NOTE) for n in notes]
        answer = {"passed": not errors, "errors": errors, "warnings": warned, "notes": noted, "next_step": step or None}
        print(json.dumps({"schema_version": arguments.JSON_SCHEMA_VERSION} | answer, indent=2))
        return 1 if errors else 0
    for n in notes:
        print(n)
    for w in warnings:
        print(w if w.startswith(workitems.WARNING) else f"{workitems.WARNING}{w}")
    for e in errors:
        print(f"error: {e}")
    counts = f"{len(errors)} error(s), {len(warnings)} warning(s)" + (f", {len(notes)} note(s)" if notes else "")
    print(counts + (f": {step}" if step else ""))
    return 1 if errors else 0


def _risk_facts() -> knowledge.RiskFacts:
    """The risk rules in force here: the repository's config when it loads, else the built-in rules alone."""
    try:
        rs = risk.rule_set(arguments.config_or_none_quiet())
    except (OSError, ValueError):
        rs = risk.rule_set(None)

    def level(action: str, area: str | None = None) -> dict:
        found, rule = risk.level_on_any_branch(rs, action, area=area)
        return {"level": found, "rule": rule.label() if rule else "", "source": rule.source if rule else ""}

    actions = {k: {"description": str(v.get("description") or "")} | level(k) for k, v in rs.actions.items()}
    areas = {k: {"description": str(v.get("description") or ""), "route": v.get("route", "minor")} | level("code.edit", k) for k, v in rs.areas.items()}
    return knowledge.RiskFacts(actions=actions, areas=areas)


def cmd_explain(args) -> int:
    """`aidd explain <word>`: what one of aidd's words means and why, from the data that owns it."""
    facts = _risk_facts()
    if args.list:
        listed = knowledge.explain_words(facts)
        if args.json:
            print(json.dumps({"schema_version": arguments.JSON_SCHEMA_VERSION, "words": listed}, indent=2))
        else:
            print("".join(f"{kind}: {', '.join(names)}\n" for kind, names in listed.items() if names), end="")
        return 0
    if not args.word:
        raise ValueError("name a word, such as `aidd explain pr.merge`, or list them with `aidd explain --list`")
    word = " ".join(args.word)
    found = knowledge.explain(word, facts)
    if args.json:
        print(json.dumps({"schema_version": arguments.JSON_SCHEMA_VERSION, "word": word, "matches": found}, indent=2))
    elif not found:
        print("I don't know that word; try `aidd explain --list`, which lists every word I know", file=sys.stderr)
    for m in [] if args.json else found:
        print(f"{m['name']} ({m['kind']}): {m['what']}")
        print(f"  why: {m['why']}" if m["why"] else "", end="\n" if m["why"] else "")
        print(f"  from: {m['source']}")
    return 0 if found else 1
