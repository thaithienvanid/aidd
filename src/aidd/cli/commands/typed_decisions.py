"""What the person typed at the prompt, when it is a decision: aidd's prompt hook records it in its own process, before
the model reads the prompt, so the person's own words are the decision and no agent acts for them.

- `approve SPEC-1` (or several ids, or `/aidd approve SPEC-1`): the Spec approval of each, for its current hash.
- `approve` alone: every Spec approval that waits on this person.
- `approve merge`: the Merge approval of this branch's head.
- `ship it` (or `/aidd ship`): the person said to ship this head, so `aidd ship` lands it with nobody asked again.
- `approve all` (`automate`, `/aidd approve all`), with `but major` to keep major changes: never recorded here (a
  standing approval covers every change after it), but answered with the dialog that starts one, the MCP tool `approve_all`.
- `stop approving` (`/aidd approve stop`): the end of a standing approval.

Any other prompt goes to the model as it is. The hook cannot tell a prompt the person typed from a message another
session sends this one; aidd-mods in Claude Code can, and records only from the person's keyboard (docs/INSTALL.md).
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

from aidd import workitems
from aidd.cli import arguments
from aidd.kernel import git

# What a prompt decides: one parser, shared with the guard (workitems/typed_words.py).
parse = workitems.parse_typed


def _cli(argv: list[str], root: str) -> tuple[int, str]:
    """`aidd <argv>` in this process, in `root`: its exit code and everything it printed, as the MCP server runs it."""
    import io

    from aidd.cli import app

    out = io.StringIO()
    with contextlib.chdir(root), contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            code = app.main(argv)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) and exc.code else 2
    return code, out.getvalue().strip()


def record(text: str, root: str) -> str | None:
    """Record the decision `text` holds (parse), as aidd's prompt hook: the line the session reads about it, or None when
    the prompt is not a decision or nothing waits for it. The line says plainly whether aidd recorded it: a decision
    that could not be recorded is never passed off as one, and never swallowed into an ordinary prompt."""
    asked = parse(text)
    if asked is None:
        return None
    kind, rest = asked
    if kind == "all":
        return _not_from_a_prompt(text, bool(rest))
    try:
        with arguments.prompt_hook():
            decided = _record_typed(kind, rest, root)
    except Exception as exc:  # noqa: BLE001  # say so: the person typed a decision, and it must not vanish
        decided = (
            False,
            f"aidd failed while recording it ({type(exc).__name__}). Ask them to type it once more; if it fails again, run `aidd doctor` and show them what it says.",
        )
    if decided is None:
        return None
    recorded, said = decided
    typed = text.strip()
    if recorded:
        return f"aidd: the person typed {typed!r}, and aidd recorded it from their own words: {said} Go on with the work; never ask them again for it."
    return (
        f"aidd: the person typed {typed!r}, but aidd could not record it: {said} Tell them so in one line, with the fix it "
        "names. Never act on it as their decision, and once the fix is in, they type it again."
    )


def _record_typed(kind: str, rest: list[str], root: str) -> tuple[bool, str] | None:
    """(whether aidd recorded it, what it said) for a typed decision, or None when nothing waits for it."""
    if kind == "spec":
        return _approve_specs(rest, root)
    if kind == "stop":
        code, out = _cli(["approve", "stop"], root)
        return code == 0, _as_sentence(out)
    if kind == "merge":
        head = git.rev_parse("HEAD", root)
        code, out = _cli(["approve", "merge", "--confirmed", head, "--confirmed-in", "prompt"], root)
        return code == 0, _as_sentence(out)
    return _ship_said(root)


def _as_sentence(out: str) -> str:
    """CLI output as one sentence for the session's note: its lines joined, without `error:` prefixes, ending in a stop."""
    text = " ".join(line.strip().removeprefix("error: ").removeprefix("not approved: ") for line in out.splitlines() if line.strip())
    return (text.rstrip(".") + ".") if text else "aidd said nothing."


def _not_from_a_prompt(text: str, but_major: bool) -> str:
    """A standing approval covers every change after it, so a prompt this hook cannot trace to the keyboard never starts
    one: aidd-mods records it from the person's keys, the MCP tool `approve_all` asks them in a dialog, and `aidd approve
    all` asks at their own terminal. The note names both ways, since this hook cannot tell which tools the session has."""
    but = " --but-major" if but_major else ""
    return (
        f"aidd: the person typed {text.strip()!r}. A standing approval starts only from their keyboard or their own dialog, and this "
        "hook cannot tell where a prompt came from. If `aidd list` does not show it on yet: when this session has the aidd MCP tool "
        f"`approve_all`, call it{' with but_major: true' if but_major else ''}, and it asks them in a dialog. Otherwise tell them to run "
        f"`aidd approve all{but}` in their own terminal, which asks them there."
    )


def _approve_specs(ids: list[str], root: str) -> tuple[bool, str] | None:
    """Each Spec's approval at the hash `aidd approve spec --show` gives; with no ids, what waits on this person. True
    when at least one was recorded; None when nothing waits."""
    refs: dict[str, str] = {}
    if not ids:
        from aidd import tracking

        waiting = tracking.plan(Path(root), filters=tracking.Filters(all=True, waiting_on_me=True))
        for s in waiting:
            if s.get("code") == "spec.spec_approval" and s.get("id"):
                refs[str(s["id"])] = str(s.get("branch") or "HEAD")
        if not refs:
            return None
    else:
        refs = {i: "HEAD" for i in ids}
    said, recorded = [], False
    for spec_id, ref in refs.items():
        code, shown = _cli(["approve", "spec", spec_id, "--ref", ref, "--show"], root)
        try:
            h = json.loads(shown)["hash"] if code == 0 else None
        except (ValueError, KeyError, TypeError):
            h = None
        if h is None:
            said.append(f"{spec_id} was not approved: {_as_sentence(shown.splitlines()[-1] if shown else 'aidd could not read it')}")
            continue
        code, out = _cli(["approve", "spec", spec_id, "--ref", ref, "--confirmed", h, "--confirmed-in", "prompt"], root)
        if code == 0 and out:
            recorded = True
            said.append(_as_sentence(out.splitlines()[0]))
        else:
            said.append(f"{spec_id} was not approved: {_as_sentence(out.splitlines()[-1] if out else str(code))}")
    return recorded, " ".join(said)


def _ship_said(root: str) -> tuple[bool, str]:
    """The person said to ship this head: recorded on the approvals ref, so the agent's `aidd ship` lands it (and a
    later head of the same branch, while the Spec stays as approved: ship_said)."""
    from aidd import gate
    from aidd.cli.commands import confirmations, decide

    with contextlib.chdir(root):
        on_platform = gate.platform_of(".") == "preflight"
        login, problem = confirmations.standing_identity()
        if problem := problem or decide.local_identity_problem():
            return False, _as_sentence(problem)
        head = git.rev_parse("HEAD")
        branch = git.run(["symbolic-ref", "-q", "--short", "HEAD"], check=False).strip()
        # The decision itself, on this machine's approvals ref: a later head of the same work ships under it, each
        # Merge approval citing it (ship_decision), on a platform too.
        workitems.record_local_approval(workitems.with_login(workitems.ship_said_line(head, branch), login))
        if on_platform:
            return _ship_on_platform(root)
    return True, (
        f"ship {head[:12]}: run `aidd ship` on this branch once the gate passes. A fix the gate or the reviewer asks for "
        "ships too, with nobody asked again, while the Spec and its tests stay as approved."
    )


def _ship_on_platform(root: str) -> tuple[bool, str]:
    """ "ship it" where a platform's gate decides: the person's Merge approval, posted on the pull request as them, with
    the pull request's auto-merge, so it merges by itself once `aidd/gate` passes. An agent never merges there."""
    head = git.rev_parse("HEAD", root)
    code, out = _cli(["approve", "merge", "--confirmed", head, "--confirmed-in", "prompt", "--auto-merge"], root)
    if code != 0:
        return False, _as_sentence(out)
    return True, (
        f"{_as_sentence(out)} Never run `aidd ship` here: the pull request merges on the platform. After a fix the gate or "
        'the reviewer asks for, push it and run `aidd approve merge`: their "ship it" covers the new head while the Spec '
        "and its tests stay as approved."
    )
