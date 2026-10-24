"""What the person typed at the prompt, when it is a decision: aidd's prompt hook records it in its own process, before
the model reads the prompt, so the person's own words are the decision and no agent acts for them.

- `approve SPEC-1` (or several ids, or `/aidd approve SPEC-1`): the Spec approval of each, at the commit the branch is on.
- `approve` alone: every Spec approval that waits on this person.
- `approve merge`: the Merge approval of this branch's head.
- `land it` (or `/aidd land`): the person said to land this head on the local trunk, so `aidd land` lands it with
  nobody asked again.
- `publish` (`push it`, `open a PR`, or `/aidd publish`): the person said to take this head off this machine, so
  `aidd publish` pushes it and opens its PR/MR.
- `merge it` (or `/aidd merge`): on a pull or merge request, the person's Merge approval there, with auto-merge.
- `ship it` records nothing: it named all three of those once, and the note says which word to type.
- `approve all` (`automate`, or the slash form), with `but major` to keep major changes: a standing approval, so the
  agent records each approval it covers until the person types `stop approving`.
- `stop approving` (`/aidd stop`): the end of a standing approval.
- `decide PROP-1 go` (or `no-go`, with the reason after it) and `sign off PROP-1`: a proposal's go/no-go and its
  sign-off, written into the proposal for the person to commit.
- `explore branch <topic>` (`/aidd explore <topic>`): this worktree moves to an explore branch, where every edit is free.

What changed outside the agent's session since the person's last decision is part of this one: the line that says what
aidd recorded lists each change, which counts as theirs, and how to put it back (guard/outside_changes.py).

Any other prompt goes to the model as it is. The hook cannot tell a prompt the person typed from a message another
session sends this one, so the guard denies each way an agent hands a decision to another session: another agent's
prompt, keystrokes into a terminal, or an orchestrator's message (guard/approval_commands.py).
"""

from __future__ import annotations

import contextlib
import json
import re
from pathlib import Path

from aidd import guard, workitems
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


class Said(str):
    """The line the session reads about a typed decision, with what the person reads directly (`shown`), apart from the
    agent: in Claude Code the prompt hook's `systemMessage`, so the list of what changed never depends on the model."""

    shown: str = ""

    def __new__(cls, line: str, shown: str = "") -> Said:
        said = super().__new__(cls, line)
        said.shown = shown
        return said


def record(text: str, root: str, session_id: str = "") -> str | None:
    """Record the decision `text` holds (parse), as aidd's prompt hook: the line the session reads about it, or None when
    the prompt is not a decision or nothing waits for it. The line says plainly whether aidd recorded it: a decision
    that could not be recorded is never passed off as one, and never swallowed into an ordinary prompt. `session_id`
    is the session the person typed in: when its autopilot run waits on them, the line names how to start it again."""
    asked = parse(text)
    if asked is None:
        return None
    kind, rest = asked
    checked = None
    decided: tuple[bool, str] | None
    try:
        with arguments.prompt_hook():
            # What changed outside the agent's session since the last decision is part of this one: read before it is
            # recorded, and said with it (guard/outside_changes.py). Only a watched state aidd cannot read stops it.
            try:
                checked = guard.check_typed(root, text) if kind in guard.DECISION_KINDS else None
            except RuntimeError as exc:  # the watched state could not be read, where the project fails closed
                decided = (False, str(exc))
            else:
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
    if recorded and checked is not None:
        # What the always-on rules stood on before it, with its own record moved on and the person's words, which land,
        # approve, and publish compare with. Typed words take in only ordinary changes: one that weakens the guard stays
        # held for a dialog.
        guard.record_checked(checked, root)
    if recorded:
        note = checked.note if checked is not None and checked.note else ""
        counted = f" Tell the person this, word for word (Claude Code also shows it to them directly): {note}" if note else ""
        line = f"aidd: the person typed {typed!r}, and aidd recorded it from their own words: {said}{counted} {_what_next(kind, root, session_id)}"
        return Said(line, f"aidd recorded {typed!r}. {note}" if note else "")
    return (
        f"aidd: the person typed {typed!r}, but aidd could not record it: {said} Tell them so in one line, with the fix it "
        "names. Never act on it as their decision, and once the fix is in, they type it again."
    )


# What the agent says after a recorded decision, before it acts (announce, then act): the person always knows what was
# recorded, what runs now, where it stops for them next, and how to stop it. Never ask them for the decision again.
ANNOUNCE = (
    "Before you start, tell the person in a few short lines: what aidd recorded; what you do now (the next steps `aidd "
    "list` gives, each Task with its scope); where you stop next for them (their `land it`); and how to stop you (they "
    "interrupt you, or say stop). Then start, and report one short line as each step finishes. Never ask them for this "
    "decision again."
)
HANDS_OFF = (
    "A standing approval holds. Tell the person in a few short lines what you work on now and in what order (`aidd "
    "list`), and that `/aidd stop`, or typing `stop approving`, ends it. Then work the open items one after another until they are done, one "
    "short line per step, stopping only where aidd says a person decides. Never ask them for this decision again."
)
LAND_NEXT = "Tell the person in one line what lands and where (`aidd land`, on the local trunk), then do it and report the result in one line."
MERGE_NEXT = (
    "Tell the person in one line that the pull or merge request merges on the platform once `aidd/gate` passes, and what "
    "it still waits on. Never merge it yourself."
)
PUBLISH_NEXT = (
    "Tell the person in one line what leaves this machine (the branch, the head, and where), then run `aidd publish` and "
    "report the result in one line: where it went, and the pull or merge request when it opened one."
)
# The retired `ship it`: a pointer to the three words it stood for, recorded as nothing.
SHIP_RETIRED = (
    "`ship it` named three steps, now each the person's own word: `land it` lands this branch on the local trunk, "
    "`publish` takes it off this machine (push, and its PR/MR), and `merge it` merges its PR/MR on the platform. Ask "
    "which they mean."
)
EXPLORE_NEXT = "Tell the person in one line that this worktree is on the explore branch now, then go on with what they ask."
STOPPED = "Finish the step in hand, say so in one line, then list the next steps (`aidd list`) and wait for the person."


# After a decision, when this session's autopilot run stopped to wait on the person: it goes on only when started again.
RESUME_NEXT = "This session's autopilot run waits on the person: once you have told them, start autopilot again with `{resume}`, and never build outside a run."


def _what_next(kind: str, root: str, session_id: str = "") -> str:
    """The line after a recorded decision: what the agent announces before it acts, and how this session's autopilot
    run goes on when it stopped to wait on the person."""
    said = _announced(kind, root)
    resume = _waiting_run(root, session_id) if kind not in ("stop", "explore") else None
    return f"{said} {RESUME_NEXT.format(resume=resume)}" if resume else said


def _waiting_run(root: str, session_id: str) -> str | None:
    """The command that starts `session_id`'s autopilot run again, when its last run event waits on a person
    (`waiting_on_person`); None otherwise, or when the events cannot be read. It is built here from the install's
    command and the run's work, checked as a lease's work is: the events file is in the git directory, where a program
    could write, so no text from it reaches the line as it is."""
    if not session_id:
        return None
    from aidd import autopilot

    try:
        path = autopilot.lease_store(root) / autopilot.RUN_EVENTS_FILE
        if path.is_symlink() or not path.is_file():
            return None
        lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError, autopilot.LeaseError):
        return None
    runs = [x.get("run") for x in lines if isinstance(x, dict)]
    mine = [r for r in runs if isinstance(r, dict) and r.get("session_id") == session_id]
    # A decision the run only announced (`result: waiting`) never ended it: the run goes on by itself.
    if not mine or mine[-1].get("event") != "waiting_on_person" or mine[-1].get("result") == "waiting":
        return None
    work = mine[-1].get("work")
    return f"{_autopilot_command(root)} {work}" if isinstance(work, str) and _WORK.fullmatch(work) else None


# A run's work as a lease names it: a Spec, Epic, or Initiative id, a label, or `all` (autopilot's own WORK pattern).
_WORK = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}")


def _autopilot_command(root: str) -> str:
    """How this repository's install names the autopilot command, as autopilot's own resume line names it: a flow file
    `aidd init --team` wrote, else the aidd-team plugin's."""
    from aidd import setup

    return "/aidd-autopilot" if any((Path(root) / f).is_file() for f in setup.flow_command_paths("autopilot")) else "/aidd-team:autopilot"


def _announced(kind: str, root: str) -> str:
    """What the agent announces before it acts on a recorded decision of `kind`."""
    if kind == "all":
        return HANDS_OFF
    if kind == "stop":
        return STOPPED
    if kind in ("land", "merge"):
        return LAND_NEXT
    if kind == "merge-it":
        return MERGE_NEXT
    if kind == "publish":
        return PUBLISH_NEXT
    if kind == "explore":
        return EXPLORE_NEXT
    try:
        standing = workitems.live_standing_for(workitems.config_at(Path(root)), root)
    except Exception:  # noqa: BLE001  # what cannot be read is no standing approval
        standing = None
    return HANDS_OFF if standing else ANNOUNCE


def _record_typed(kind: str, rest: list[str], root: str) -> tuple[bool, str] | None:
    """(whether aidd recorded it, what it said) for a typed decision, or None when nothing waits for it."""
    if kind == "spec":
        return _approve_specs(rest, root)
    if kind == "stop":
        code, out = _cli(["approve", "stop"], root)
        return code == 0, _as_sentence(out)
    if kind == "all":
        scope = "all" + ("-and-publish" if "and-publish" in rest else "") + ("-but-major" if "but-major" in rest else "")
        flags = [*(["--and-publish"] if "and-publish" in rest else []), *(["--but-major"] if "but-major" in rest else [])]
        code, out = _cli(["approve", "all", *flags, "--confirmed", scope, "--decided-via", "prompt"], root)
        return code == 0, _as_sentence(out)
    if kind in ("decide", "sign-off"):
        return _proposal_decided(kind, rest, root)
    if kind == "merge":
        head = git.rev_parse("HEAD", root)
        code, out = _cli(["approve", "merge", "--confirmed", head, "--decided-via", "prompt"], root)
        return code == 0, _as_sentence(out)
    if kind == "ship":
        return False, SHIP_RETIRED
    if kind == "explore":
        return _explore_said(rest[0], root)
    if kind == "publish":
        return _publish_said(root)
    if kind == "merge-it":
        return _merge_it(root)
    return _land_said(root)


def _as_sentence(out: str) -> str:
    """CLI output as one sentence for the session's note: its lines joined, without `error:` prefixes, ending in a stop."""
    text = " ".join(line.strip().removeprefix("error: ").removeprefix("not approved: ") for line in out.splitlines() if line.strip())
    return (text.rstrip(".") + ".") if text else "aidd said nothing."


def _proposal_decided(kind: str, rest: list[str], root: str) -> tuple[bool, str]:
    """A proposal's go/no-go, or its sign-off for the hash `aidd proposal sign-off --show` gives."""
    pid = rest[0]
    if kind == "decide":
        _, decision, reason = rest
        why = [f"--reason={reason}"] if reason else []
        code, out = _cli(["proposal", "decide", pid, decision, *why, f"--confirmed={decision}", "--decided-via=prompt"], root)
        return code == 0, _as_sentence(out.splitlines()[-1] if out else str(code))
    code, shown = _cli(["proposal", "sign-off", pid, "--show"], root)  # the id first, never "-…"
    try:
        preview = json.loads(shown) if code == 0 else {}
    except ValueError:
        preview = {}
    if problems := preview.get("problems") or ([] if preview.get("hash") else [shown.splitlines()[-1] if shown else "aidd could not read it"]):
        return False, _as_sentence(f"{pid} was not signed off: {problems[0]}")
    code, out = _cli(["proposal", "sign-off", pid, f"--confirmed={preview['hash']}", "--decided-via=prompt"], root)
    return code == 0, _as_sentence(out.splitlines()[-1] if out else str(code))


def _approve_specs(ids: list[str], root: str) -> tuple[bool, str] | None:
    """Each Spec's approval at the commit `aidd approve spec --show` gives; with no ids, what waits on this person. True
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
            h = json.loads(shown)["commit"] if code == 0 else None
        except (ValueError, KeyError, TypeError):
            h = None
        if h is None:
            said.append(f"{spec_id} was not approved: {_as_sentence(shown.splitlines()[-1] if shown else 'aidd could not read it')}")
            continue
        code, out = _cli(["approve", "spec", spec_id, "--ref", ref, "--confirmed", h, "--decided-via", "prompt"], root)
        if code == 0 and out:
            recorded = True
            said.append(_as_sentence(out.splitlines()[0]))
        else:
            said.append(f"{spec_id} was not approved: {_as_sentence(out.splitlines()[-1] if out else str(code))}")
    return recorded, " ".join(said)


def _land_said(root: str) -> tuple[bool, str]:
    """The person said to land this head on the local trunk: recorded in the decision records, so the agent's `aidd land`
    lands it (and a later head of the same branch, while the Spec stays as approved: land_said). Where this branch is
    on its platform, it merges there instead: `merge it`."""
    from aidd import gate
    from aidd.cli.commands import confirmations, decide

    with contextlib.chdir(root):
        if gate.platform_of(".") == "preflight":
            return False, "this branch is on its platform, where its pull or merge request merges: type `merge it` there."
        login, problem = confirmations.standing_identity()
        if problem := problem or decide.local_identity_problem():
            return False, _as_sentence(problem)
        head = git.rev_parse("HEAD")
        branch = git.run(["symbolic-ref", "-q", "--short", "HEAD"], check=False).strip()
        # The decision itself, on this machine's decision records: a later head of the same work lands under it, each Merge
        # approval citing it (land_decision).
        workitems.record_local_approval(workitems.with_login(workitems.land_said_line(head, branch), login))
    return True, (
        f"land {head[:12]}: run `aidd land` on this branch once the gate passes. A fix the gate or the reviewer asks for "
        "lands too, with nobody asked again, while the Spec and its tests stay as approved."
    )


def _explore_said(topic: str, root: str) -> tuple[bool, str]:
    """The person asked for an explore branch: aidd switches this worktree to `explore/<topic>` for them, a new branch
    from here or the one that exists, and uncommitted work comes along. Only a person starts one (the guard holds an
    agent's switch), so their words are the confirmation, recorded on this machine's decision records: the guard frees
    edits only on an explore branch such a record names (workitems.explore_started)."""
    from aidd.cli.commands import confirmations, decide

    branch = f"{workitems.EXPLORE_PREFIX}{topic}"
    if not git.ok(["check-ref-format", "--branch", branch], root):
        return False, f"{branch} is not a branch name git accepts: type `{workitems.EXPLORE_WORD} branch <topic>` with letters, digits, `.`, `_`, or `-`."
    with contextlib.chdir(root):
        login, problem = confirmations.standing_identity()
        if problem := problem or decide.local_identity_problem():
            return False, _as_sentence(problem)
    exists = git.ok(["rev-parse", "-q", "--verify", f"refs/heads/{branch}"], root)
    switched = git.run(["switch", *([] if exists else ["-c"]), branch], root, check=False)
    if git.run(["symbolic-ref", "-q", "--short", "HEAD"], root, check=False).strip() != branch:
        return False, f"git could not switch to {branch}: {switched.strip() or 'it said nothing'}. Commit or stash what blocks it, then type it again."
    with contextlib.chdir(root):
        workitems.record_local_approval(workitems.with_login(workitems.explore_said_line(branch), login))
    return True, workitems.explore_note(branch) + "."


def _publish_said(root: str) -> tuple[bool, str]:
    """The person said to take this head off this machine: recorded in the decision records, so the agent's `aidd publish`
    pushes exactly this head (and opens its PR/MR where a platform runs the gate)."""
    from aidd.cli.commands import confirmations, decide

    with contextlib.chdir(root):
        login, problem = confirmations.standing_identity()
        if problem := problem or decide.local_identity_problem():
            return False, _as_sentence(problem)
        head = git.rev_parse("HEAD")
        branch = git.run(["symbolic-ref", "-q", "--short", "HEAD"], check=False).strip()
        if not branch:
            return False, "HEAD is detached: switch to the branch to publish, then type `publish` again."
        # `origin`, or the only remote, as for `approve all and publish`: never the push remote the config names, which
        # an agent could have pointed at a place of its own before the person typed.
        remotes = git.run(["remote"], check=False).split()
        remote = "origin" if "origin" in remotes else remotes[0] if len(remotes) == 1 else ""
        if not remote:
            return False, (
                "publishing needs one remote to publish to (`origin`, or the only remote): add it (`git remote add origin "
                "<url>`), then type `publish` again. To publish to another remote, run `aidd publish --remote <name>` "
                "at your own terminal."
            )
        urls = workitems.remote_urls(".", remote)
        workitems.record_local_approval(workitems.with_login(workitems.publish_said_line(head, branch, remote, urls), login))
    return True, (
        f"publish {branch} at {head[:12]} to {remote} ({', '.join(urls) or 'no URL'}): run `aidd publish`. A fix pushed to the same branch and remote "
        "follows it; anything else needs a new `publish`."
    )


def _merge_it(root: str) -> tuple[bool, str]:
    """`merge it`: the person's Merge approval on this branch's pull or merge request, with its auto-merge. Before the
    branch is on a platform there is nothing to merge there."""
    from aidd import gate
    from aidd.cli.commands import confirmations, decide

    with contextlib.chdir(root):
        if gate.platform_of(".") != "preflight":
            return False, (
                "this branch is not on a platform yet, so there is no pull or merge request to merge. Type `land it` to "
                "land it on the local trunk, or `publish` to push it and open one."
            )
        login, problem = confirmations.standing_identity()
        if problem := problem or decide.local_identity_problem():
            return False, _as_sentence(problem)
        head = git.rev_parse("HEAD")
        branch = git.run(["symbolic-ref", "-q", "--short", "HEAD"], check=False).strip()
        # The decision itself, as for `land it`: a fix the gate or the reviewer asks for merges under it (land_decision).
        workitems.record_local_approval(workitems.with_login(workitems.land_said_line(head, branch, words="merge it"), login))
    return _merge_on_platform(root)


def _merge_on_platform(root: str) -> tuple[bool, str]:
    """`merge it` where a platform's gate decides: the person's Merge approval, posted on the pull request as them, with
    the pull request's auto-merge, so it merges by itself once `aidd/gate` passes. An agent never merges there."""
    head = git.rev_parse("HEAD", root)
    code, out = _cli(["approve", "merge", "--confirmed", head, "--decided-via", "prompt", "--auto-merge"], root)
    if code != 0:
        return False, _as_sentence(out)
    return True, (
        f"{_as_sentence(out)} Never run `aidd land` here: the pull request merges on the platform. After a fix the gate or "
        'the reviewer asks for, push it and run `aidd approve merge`: their "merge it" covers the new head while the Spec '
        "and its tests stay as approved."
    )
