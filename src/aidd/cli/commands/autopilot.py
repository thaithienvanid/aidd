"""The autopilot commands: autopilot, and `aidd context` (experimental)."""

from __future__ import annotations

import json
from pathlib import Path

from aidd import config
from aidd.cli import arguments


def _autopilot_limits():
    from aidd import autopilot

    return autopilot.Limits.of(arguments.config_or_none_quiet())


def cmd_autopilot(args) -> int:
    """Autopilot: its lease and journal, kept in the git directory, and its next action."""
    from aidd import autopilot, tracking

    arguments.enter_repo(args)
    root = Path(".")
    if args.action in ("start", "next"):
        cfg = arguments.config_or_none_quiet()
        if cfg is not None and not config.component_on(cfg.raw, "autopilot"):
            off = "components.loop" if not config.component_on(cfg.raw, "loop") else "components.autopilot"
            raise ValueError(f"autopilot is off here: {off} is false in {config.CONFIG_PATH}. Set it to true to run it")
    if args.action == "start":
        held, what = autopilot.take_lease(root, work=args.work, session_id=args.session, timebox=args.timebox or _autopilot_limits().timebox)
        print(what)
        print(f"session: {held['session_id']}")
        return 0
    if args.action == "next":
        action = autopilot.next_action(root, work=args.work, session=args.session, goal=args.goal)
        print(json.dumps(action, indent=2) if args.json else autopilot.markdown(action), end="\n" if args.json else "")
        return 0
    if args.action == "note":
        if (args.cost is None) != (args.currency is None):
            raise ValueError("--cost and --currency go together, such as --cost 0.42 --currency USD")
        cost = {"amount": args.cost, "currency": args.currency} if args.cost is not None else None
        autopilot.check_spend(args.tokens, cost)
        merged = None
        if autopilot.parse_note(args.text)[0] == "learn.retro":
            merged = autopilot.merged_count(tracking.open_work(root)[1])
        entry = autopilot.note_step(root, args.text, session_id=args.session, spec=args.spec, tokens=args.tokens, cost=cost, merged=merged, goal=args.goal)
        print(f"noted {entry['code']} {entry['result']} for {entry.get('spec') or entry['work']}")
        return 0
    if args.action == "status":
        shown = autopilot.show_leases(root)
        print(json.dumps(shown, indent=2) if args.json else autopilot.lease_markdown(shown), end="\n" if args.json else "")
        return 0
    gone = autopilot.release_lease(root, session_id=args.session)
    print(f"stopped autopilot on {gone['work']} (session {gone['session_id']})" if gone else "autopilot holds no lease")
    return 0


def cmd_context(args) -> int:
    """The minimal context pack for one step of a Spec (experimental)."""
    from aidd import autopilot

    raw = args.spec
    arguments.enter_repo(args, "spec")
    if "/" not in raw and "\\" not in raw and not Path(args.spec).is_file():
        args.spec = raw  # an id, such as SPEC-1
    pack = autopilot.build_context_pack(Path("."), args.spec, role=args.role, step=args.step)
    print(json.dumps(pack, indent=2) if args.json else autopilot.context_pack_markdown(pack), end="\n" if args.json else "")
    return 0
