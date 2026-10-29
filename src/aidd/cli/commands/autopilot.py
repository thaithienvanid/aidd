"""The autopilot commands: autopilot, and `aidd context` (experimental)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from aidd import config
from aidd.cli import arguments


def _autopilot_limits():
    """The run's limits as the base branch's config sets them: an agent writes the working tree's."""
    from aidd import autopilot, workitems

    root = Path(".")
    return autopilot.Limits.of(autopilot.base_config(root, workitems.Observer(root, None)))


def cmd_autopilot(args) -> int:
    """Autopilot: its lease and journal, kept in the git directory, and its next action."""
    from aidd import autopilot, tracking

    arguments.enter_repo(args)
    root = Path(".")
    if args.action in ("start", "next"):
        cfg = arguments.config_or_none_quiet()
        if cfg is not None and not config.component_on(cfg.raw, "autopilot"):
            off = "components.spec_steps" if not config.component_on(cfg.raw, "spec_steps") else "components.autopilot"
            raise ValueError(f"autopilot is off here: {off} is false in {config.CONFIG_PATH}. Set it to true to run it")
    if args.action == "start":
        held, what = autopilot.take_lease(root, work=args.work, session_id=args.session, timebox=args.timebox or _autopilot_limits().timebox)
        print(what)
        print(f"session: {held['session_id']}")
        return 0
    if args.action == "next":
        action = autopilot.next_action(root, work=args.work, session=args.session, goal=args.goal, harness=args.harness)
        print(json.dumps(action, indent=2) if args.json else autopilot.markdown(action), end="\n" if args.json else "")
        return 0
    if args.action == "note":
        if (args.cost is None) != (args.currency is None):
            raise ValueError("--cost and --currency go together, such as --cost 0.42 --currency USD")
        cost = {"amount": args.cost, "currency": args.currency} if args.cost is not None else None
        autopilot.check_spend(args.tokens, cost)
        merged = None
        code, _, words = autopilot.parse_note(args.text)
        if code == "learn.retro":
            merged = autopilot.merged_count(tracking.open_work(root)[1])
        entry = autopilot.note_step(
            root,
            args.text,
            session_id=args.session,
            spec=args.spec,
            head=args.head,
            tokens=args.tokens,
            cost=cost,
            merged=merged,
            goal=args.goal,
            codes=frozenset(autopilot.contract()),
        )
        cut = f"; its words were cut to their first {len(entry['text'])} characters" if len(words) > len(entry.get("text") or "") else ""
        print(f"noted {entry['code']} {entry['result']} for {entry.get('spec') or entry['work']}{cut}")
        return 0
    if args.action == "status":
        shown = autopilot.show_leases(root, session_id=args.session)
        print(json.dumps(shown, indent=2) if args.json else autopilot.lease_markdown(shown), end="\n" if args.json else "")
        return 0
    gone = autopilot.release_lease(root, session_id=args.session)
    print(f"stopped autopilot on {gone['work']} (session {gone['session_id']})" if gone else "autopilot holds no lease")
    return 0


# The variables a harness sets to this shell's session: Claude Code's own, and the one aidd's OpenCode plugin sets.
SESSION_ENV = ("CLAUDE_CODE_SESSION_ID", "AIDD_SESSION_ID")


def other_session(session: str) -> str | None:
    """This shell's own session id when the harness names it and `session` is another, else None: a session plays
    a role, or stops playing one, only for itself."""
    own = next((os.environ[k].strip() for k in SESSION_ENV if os.environ.get(k, "").strip()), "")
    return own if own and session != own else None


def cmd_context(args) -> int:
    """The minimal context pack for one step of a Spec (experimental)."""
    from aidd import autopilot

    if (args.play or args.stop_playing) and args.session and (own := other_session(args.session)):
        print(f"aidd context: this shell is session {own}, so it plays or stops a role only for itself: use --session {own}", file=sys.stderr)
        return 2
    if args.stop_playing:
        if not args.session:
            print("aidd context: --stop-playing needs --session <id>, the id the session hook named", file=sys.stderr)
            return 2
        try:
            stopped = autopilot.stop_playing(Path("."), args.session)
        except autopilot.LeaseError as exc:
            print(f"aidd context: {exc}", file=sys.stderr)
            return 2
        print(f"session {args.session} plays no role now" if stopped else f"session {args.session} played no role")
        return 0
    if not args.spec:
        print("aidd context: name the Spec, such as SPEC-1", file=sys.stderr)
        return 2
    raw = args.spec
    arguments.enter_repo(args, "spec")
    if "/" not in raw and "\\" not in raw and not Path(args.spec).is_file():
        args.spec = raw  # an id, such as SPEC-1
    try:
        pack = autopilot.build_context_pack(Path("."), args.spec, role=args.role, step=args.step, play=args.play)
    except ValueError as exc:
        print(f"aidd context: {exc}", file=sys.stderr)
        return 2
    if args.play and not args.session:
        print(
            "note: no --session, so the guard does not hold this session to the role's files. Add `--session <id>`: "
            "`${CLAUDE_SESSION_ID}` in Claude Code, `${AIDD_SESSION_ID}` in OpenCode, else the id aidd's session note names",
            file=sys.stderr,
        )
    if args.play and args.session:
        try:
            autopilot.declare_played(Path("."), args.session, args.role)
        except autopilot.LeaseError as exc:
            print(f"aidd context: {exc}", file=sys.stderr)
            return 2
    print(json.dumps(pack, indent=2) if args.json else autopilot.context_pack_markdown(pack), end="\n" if args.json else "")
    return 0
