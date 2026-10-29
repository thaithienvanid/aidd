"""What autopilot tells a person, word for word: the message of a stop they end, and an action in a few lines."""

from __future__ import annotations

# The decisions a message lists in full; the rest are counted and left to `aidd list --waiting-on-me`.
LISTED = 10


# The decisions a person takes by typing words at the prompt, which aidd records before the agent reads them
# (`approve SPEC-1`, `land it`, `publish`): the run goes on from that, so the person decides once.
TYPED = frozenset({"spec.spec_approval", "spec.merge_approval", "spec.publish", "goal.release"})
# Of those, the ones that land the work: in a run on that one item, nothing is left to go on to.
LANDS = frozenset({"spec.merge_approval", "goal.release"})
NEW_SESSION = (
    "This session works. After a long run, start a new session (or `/clear`) first: the run begins again from the files and the journal, so nothing is lost."
)


def message(action: dict, where: str | None = None) -> str:
    """What the autopilot command shows a person when the run ends on `action`, word for word: why it stopped, each
    decision and how to take it, and how it goes on. `where`: the file of the item a blocked ask set aside."""
    reason, resume = action.get("reason"), action["resume"]
    if action["action"] == "ask" and action.get("blocked") and action.get("spec"):
        note = f" in {where}" if where else ""
        head = f"Autopilot set {action['spec']} aside: {action['why']}. Read its latest handoff note{note}, fix the cause, then run `{resume}`; the run tries it again."
    elif action["action"] == "ask":
        head = "Autopilot stopped at a decision only a person can make."
    elif reason == "plan_ready":
        head = "Autopilot stopped: the plan is ready for you. `aidd list` shows the planned work (`aidd list --html` as a page)."
    else:
        head = f"Autopilot stopped: {action['why']}."
    lines = [head]
    waiting = action.get("decisions") or []
    if waiting:
        lines += ["", f"Waiting on a person ({len(waiting)}):"]
        for d in waiting[:LISTED]:
            lines.append(f"- {d['what']}" + (f" ({d['who']})" if d.get("who") else ""))
            if d.get("how"):
                lines.append(f"  {d['how']}")
        if len(waiting) > LISTED:
            lines.append(f"- and {len(waiting) - LISTED} more: `aidd list --waiting-on-me`")
    if action.get("behind"):
        n = action["behind"]
        lines += ["", f"{n} more {'waits' if n == 1 else 'wait'} on other work and {'starts' if n == 1 else 'start'} when it finishes."]
    way = _way_on(action, waiting)
    return "\n".join([*lines, "", way, NEW_SESSION] if way else [*lines, "", NEW_SESSION])


def _way_on(action: dict, waiting: list[dict]) -> str | None:
    """The line that says how the run goes on: a decision typed at the prompt goes on by itself once aidd records it,
    so the person decides once; anything else goes on when the person runs `resume`."""
    resume, code = action["resume"], action.get("code")
    if action.get("blocked"):
        return None  # the head line says it
    if action.get("reason") == "plan_ready":
        return f"To go on, run `{resume}`. Starting it again is how you agree to the plan."
    if action["action"] == "ask" and code in TYPED:
        if code in LANDS and action.get("work") == action.get("spec") and len(waiting) <= 1:
            return f"Type it at the prompt. Once aidd records it, {action['spec']} lands, and this run has nothing left to go on to."
        return f"Type each decision at the prompt: the run goes on once aidd records it, as `{resume}` does."
    return f"{'When you have decided, run' if waiting else 'To go on, run'} `{resume}`."


def markdown(action: dict) -> str:
    """One action in a few lines, for the autopilot command's start line or a person reading along."""
    kind = action["action"]
    lines = [f"next: {kind}"]
    if kind == "run":
        lines.append(f"  {action['command']} {action.get('args') or ''}".rstrip())
        if action.get("codes"):
            lines.append(f"  side by side: {', '.join(action['codes'])}, each noted on its own")
        for a in action.get("also") or []:
            lines.append(f"  also: {a['command']} {a.get('args') or ''}".rstrip() + (f" (side by side: {', '.join(a['codes'])})" if a.get("codes") else ""))
    elif kind == "ask":
        lines += [f"  who: {action.get('who')}", f"  what: {action.get('what')}", f"  page: `{action.get('page')}`"]
    else:
        lines.append(f"  reason: {action.get('reason')}")
    lines.append(f"  why: {action['why']}")
    for p in action.get("paused") or []:
        lines.append(f"  set aside: {p['spec']} ({p['why']})")
    for d in action.get("decisions") or [] if kind == "run" else []:
        lines.append(f"  waits on a person: {d['what']}")
    if action.get("message"):
        lines += ["", action["message"]]
    return "\n".join(lines) + "\n"
