"""Where a `batched` Intent's Specs stand on its branch `intent/<ID>`, read from git on each run and never stored.

The Specs of a `batched` Intent build on `spec/<ID>` branches cut from `intent/<ID>`, and one Merge approval lands that
branch on the default branch. `aidd status` reads the branch names once, with one `for-each-ref`, and the Specs merged
into each Intent's branch with one more, so its cost stays flat as the Specs grow. A Spec's file lives on its own branch
until it merges, so a slice counts as started when a branch carries its id, whatever this checkout holds."""

from __future__ import annotations

from aidd.kernel import git
from aidd.workitems import ids, status

# The branches that matter: local ones, and remote-tracking ones of the same names (to tell "not checked out" from "not cut").
PATTERNS = ["refs/heads/spec/", "refs/heads/intent/", "refs/remotes/*/spec/*", "refs/remotes/*/intent/*"]


def _names(top: str) -> tuple[set[str], set[str]]:
    """The local branch names under `spec/` and `intent/`, and the remote-tracking ones without their remote."""
    local, remote = set(), set()
    for ref in git.run(["for-each-ref", "--format=%(refname)", *PATTERNS], top, check=False).split():
        if ref.startswith("refs/heads/"):
            local.add(ref.removeprefix("refs/heads/"))
        else:
            remote.add(ref.split("/", 3)[3])
    return local, remote


def _landed(top: str, intent: str) -> bool | None:
    """Whether `intent` is merged into the default branch, or None when git cannot tell which branch that is."""
    try:
        base = git.default_base(top)
    except git.GitError:
        return None
    return intent in git.run(["for-each-ref", f"--merged={base}", "--format=%(refname:short)", "refs/heads/intent/"], top, check=False).split()


def _unnameable(top: str, name: str) -> bool:
    """Whether git refuses `name` as a branch, such as an id with `:`, `..`, or a `.lock` ending."""
    return not git.ok(["check-ref-format", "--branch", name], top)


def _intent_state(top: str, name: str, local: set[str], remote: set[str]) -> str:
    if name in local:
        landed = _landed(top, name)
        return "local" if landed is None else "merged" if landed else "unmerged"
    if name in remote:
        return "remote_only"
    return "invalid_name" if _unnameable(top, name) else "missing"


def _spec_state(top: str, name: str, merged: set[str], refs: tuple[set[str], set[str]], *, started_here: bool) -> str | None:
    """One Spec's place against its Intent's branch (`branch_state` in schemas/status.schema.json), or None when the slice has
    no Spec yet: no branch carries its id and this checkout holds no file for it."""
    local, remote = refs
    if name in local:
        return "merged" if name in merged else "unmerged"
    if name in remote:
        return "remote_only"
    if started_here:
        return "invalid_name" if _unnameable(top, name) else "missing"
    return None


def add_to(top: str, items: list[dict], started: set[str]) -> None:
    """Mark each `batched` Intent among `items`, and each of its slices that has a Spec, with its `branch_state`
    (schemas/status.schema.json). `started` holds the ids of the Specs this checkout has a file for. A
    Spec finished for good (`done`, with its branch gone) says nothing, because there is nothing left to do for it."""
    if not items:
        return
    local, remote = _names(top)
    for item in items:
        intent = f"intent/{item['id']}"
        state = item["branch_state"] = _intent_state(top, intent, local, remote)
        merged = set()
        if intent in local:
            merged = set(git.run(["for-each-ref", f"--merged=refs/heads/{intent}", "--format=%(refname:short)", "refs/heads/spec/"], top, check=False).split())
        for phase in item.get("phases") or []:
            for s in phase["specs"]:
                name = f"spec/{s['id']}"
                if not ids.is_id(s["id"]):
                    continue
                own = name in local or (not status.finished(s["status"]) and (name in remote or s["id"] in started))
                if not own:
                    continue
                place = _spec_state(top, name, merged, (local, remote), started_here=s["id"] in started)
                s["branch_state"] = place if state in ("local", "merged", "unmerged") or place is None else "intent_branch_missing"
        if state == "unmerged" and (step := item.get("next")) and step.get("code") == "intent.close":
            item["next"] = {**step, "what": f"{step['what']} (first land {intent}: its Merge approval is pending)"}
