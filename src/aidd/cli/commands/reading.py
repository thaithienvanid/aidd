"""The commands that read the repository's files and aidd's own data, and change nothing: `aidd validate` and `aidd explain`."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from aidd import config, knowledge, risk, workitems
from aidd.cli import arguments
from aidd.kernel import documents, findings, text

# The most characters of one validate message a terminal shows: far past any message aidd writes, so only a hostile value is cut.
MESSAGE_CHARS = 4000


def _config_errors(paths: list[str]) -> list[str]:
    """The errors of the config of each repository a path is in, nearest first: a file is checked by rules that a config that
    does not load cannot give, so `validate <path>` never passes past it."""
    seen: set[Path] = set()
    found: list[str] = []
    for p in paths:
        cfg = next((d / config.CONFIG_PATH for d in Path(p).resolve().parents if (d / config.CONFIG_PATH).is_file()), None)
        if cfg is not None and cfg not in seen:
            seen.add(cfg)
            found += [e for e in workitems.validate_file(cfg, label=os.path.relpath(cfg)) if workitems.is_error(e)]
    return found


def cmd_validate(args) -> int:
    if not args.paths:
        arguments.enter_repo(args)
        errors, warnings = workitems.check_repo(Path("."))
    else:
        found = list(dict.fromkeys([*_config_errors(args.paths), *(e for p in args.paths for e in workitems.validate_file(Path(p)))]))
        errors = [e for e in found if workitems.is_error(e)]
        warnings = [e for e in found if not workitems.is_error(e)]
    # A note says an expected state, such as a planned Spec's placeholders: it is shown, and it never fails the run.
    notes = [w for w in warnings if w.startswith(workitems.NOTE)]
    warnings = [w for w in warnings if not w.startswith(workitems.NOTE)]
    step = workitems.validate_next_step(errors)
    if args.json:
        warned, noted = [w.removeprefix(workitems.WARNING) for w in warnings], [n.removeprefix(workitems.NOTE) for n in notes]
        listed = {"passed": not errors, "errors": errors, "warnings": warned, "notes": noted}
        answer = listed | {"findings": workitems.validate_findings(errors, warned, noted, Path.cwd())} | ({"next": {"what": step}} if step else {})
        print(json.dumps({"schema_version": arguments.JSON_SCHEMA_VERSION} | answer, indent=2))
        return 1 if errors else 0
    # A message can quote a value from a file, which may hold an escape or a line break (`"\u001b"`, `"\n"`): each prints as one terminal line.
    for n in notes:
        print(documents.one_line(n, MESSAGE_CHARS))
    for w in warnings:
        print(documents.one_line(w if w.startswith(workitems.WARNING) else f"{workitems.WARNING}{w}", MESSAGE_CHARS))
    for e in errors:
        print(documents.one_line(f"error: {e}", MESSAGE_CHARS))
    counts = f"{len(errors)} error(s), {len(warnings)} warning(s)" + (f", {len(notes)} note(s)" if notes else "")
    print(counts + (f": {step}" if step else ""))
    return 1 if errors else 0


def _risk_facts(args) -> knowledge.RiskFacts:
    """The risk rules in force here: the repository's config when it loads, else the built-in rules alone, said on stderr, and the command exits 1."""
    try:
        rs = risk.rule_set(arguments.config_or_none_quiet(args))
    except (OSError, ValueError):
        rs = risk.rule_set(None)

    def level(action: str, area: str | None = None) -> dict:
        found, rule = risk.level_on_any_branch(rs, action, area=area)
        return {"level": found, "rule": rule.label() if rule else "", "source": rule.source if rule else ""}

    actions = {k: {"description": str(v.get("description") or "")} | level(k) for k, v in rs.actions.items()}
    areas = {k: {"description": str(v.get("description") or ""), "route": v.get("route", "minor")} | level("code.edit", k) for k, v in rs.areas.items()}
    profiles = {name: risk.routes_asking_for_spec_approval(name) for name in config.profiles()["profiles"]}
    return knowledge.RiskFacts(actions=actions, areas=areas, profiles=profiles)


def cmd_explain(args) -> int:
    """`aidd explain <word>`: what one of aidd's words means and why, from the data that owns it."""
    facts = _risk_facts(args)
    if args.list:
        listed = knowledge.explain_words(facts)
        if args.json:
            print(json.dumps({"schema_version": arguments.JSON_SCHEMA_VERSION, "words": listed}, indent=2))
        else:
            print("".join(f"{word_type.replace('_', ' ')}: {', '.join(names)}\n" for word_type, names in listed.items() if names), end="")
        return 0
    if not args.word:
        raise ValueError("name a word, such as `aidd explain pr.merge`, or list them with `aidd explain --list`")
    word = " ".join(args.word)
    found = knowledge.explain(word, facts)
    shown: dict = {"schema_version": arguments.JSON_SCHEMA_VERSION, "word": word, "matches": found}
    if not found:  # an unknown word is an error, as `risk --action` makes it: the closest word, then where the list is
        known = [n for names in knowledge.explain_words(facts).values() for n in names]
        guess = text.did_you_mean(word, known, 0.75)  # a weaker match is a different word, never a guess
        said = (
            f"{word!r} is not a word aidd knows. {guess + ' ' if guess else ''}`aidd explain --list` lists every word, "
            "and `aidd recall <word>` searches the glossary and the team's files."
        )
        if args.json:  # the matches stay, empty, and the error object joins them: one document on stdout
            print(json.dumps(shown | {"error": findings.finding("cli.unknown_word", said)}, indent=2))
        print(f"aidd explain: {said}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(shown, indent=2))
    for m in [] if args.json else found:
        print(f"{m['name']} ({m['type'].replace('_', ' ')}): {m['what']}")
        print(f"  why: {m['why']}" if m["why"] else "", end="\n" if m["why"] else "")
        print(f"  from: {m['source']}")
    return 0
