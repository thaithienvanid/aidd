"""Local-first shipping: the person check before an approval or a merge, and `aidd ship`, which tests the merge of a
passing branch and lands exactly that tree. The approvals themselves are in workitems/approval_ledger.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from aidd.kernel import git

# Variables an agent harness sets in the shells it starts: Claude Code (CLAUDECODE, CLAUDE_CODE_CHILD_SESSION),
# Google Antigravity (ANTIGRAVITY_AGENT), the generic AI_AGENT some harnesses export, and AIDD_AGENT for any other runner.
AGENT_ENV = ("CLAUDE_CODE_CHILD_SESSION", "CLAUDECODE", "ANTIGRAVITY_AGENT", "AI_AGENT", "AIDD_AGENT")


class NotAPerson(RuntimeError):
    """Raised when an approval or a merge is attempted without a person at an interactive terminal."""


# The answers that confirm; anything else, an empty line included, is a no.
YES = frozenset({"y", "yes"})


def typed_words_for(command: str) -> str | None:
    """The words a person types at their coding agent's prompt for the same decision as `command`, which aidd's prompt
    hook records from their own words (cli/commands/typed_decisions.py); None when there are none."""
    words = command.split()
    if words[:3] == ["aidd", "approve", "spec"] and len(words) > 3 and "<" not in command:
        return "approve " + " ".join(Path(w).stem for w in words[3:] if not w.startswith("-"))
    if words[:3] == ["aidd", "approve", "merge"]:
        return "approve merge"
    if words[:3] == ["aidd", "approve", "all"]:
        return "approve all" + (" but major" if "--but-major" in words else "")
    if words[:2] == ["aidd", "ship"]:
        return "ship it"
    return None


def check_terminal(what: str, command: str = "") -> None:
    """Refuse before anything else when no person can be at this terminal: a shell an agent started, or no terminal.
    The refusal names the quickest way that works: the words to type at the agent's prompt (inside an agent's shell,
    such as Claude Code's `!`), then `command`, when given, for a terminal no agent started."""
    copy = f":\n  {command}" if command else "."
    if any(os.environ.get(v) for v in AGENT_ENV):
        typed = typed_words_for(command)
        first = f" Type `{typed}` at your coding agent's prompt instead (not as a `!` command): aidd records it from your own words." if typed else ""
        raise NotAPerson(f"{what} is a person's decision, and an agent started this shell.{first} Or run it in a terminal no agent started{copy}")
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise NotAPerson(f"{what} needs a person at an interactive terminal. Run it there{copy}")


def require_person(what: str, ask=None, command: str = "", question: str = "") -> None:
    """A person at an interactive terminal answers yes to `question` (default: `what?`); no, an empty line, or Ctrl-D
    stops. An agent's tool shell has no terminal, and a shell an agent started is refused before anyone is asked.

    A yes is what a person types and an agent that drives a terminal could type too: the agent check, the guard (which
    denies an agent's `aidd approve` and `aidd ship`), and a signing key that asks for your presence are the controls,
    not this answer. `ask` defaults to the built-in `input`, looked up at call time."""
    ask = ask or input
    check_terminal(what, command)
    try:
        answer = ask(f"{question or what + '?'} [y/N] ").strip().lower()
    except EOFError:  # Ctrl-D, or input that ended: nobody confirmed
        raise NotAPerson(f"{what} was not confirmed") from None
    if answer not in YES:
        raise NotAPerson(f"{what} was not confirmed")


def merged_commit(base_tip: str, head: str, *, message: str, cwd: str = ".") -> tuple[str, str]:
    """The merge of `head` into `base_tip` as a commit git has not placed on any branch: (its id, its tree). It is what
    `aidd ship` tests and then lands when the base moved, so the tested tree is exactly the shipped tree. A conflict
    raises: nothing is merged, and the person merges or rebases the branch themselves."""
    p = git._git(["merge-tree", "--write-tree", "--no-messages", base_tip, head], cwd)
    tree = p.stdout.decode("utf-8", errors="replace").split("\n", 1)[0].strip()
    if p.returncode == 1:
        raise RuntimeError(
            f"{head[:12]} conflicts with the base tip {base_tip[:12]}, so nothing was tested or shipped. Merge or rebase the base "
            "into the branch, and resolve the conflicts. Then run `aidd test`, get Merge approval on the new head, and `aidd ship` again"
        )
    if p.returncode != 0 or not tree:
        raise git.GitError(f"git merge-tree {base_tip[:12]} {head[:12]}: {p.stderr.decode('utf-8', errors='replace').strip()}")
    sha = git.run(["commit-tree", tree, "-p", base_tip, "-p", head, "-m", message], cwd).strip()
    return sha, tree


def run_in_worktree(commit: str, run, cwd: str = "."):
    """`run(path)` in a temporary detached worktree of `commit`, removed afterwards."""
    import shutil
    import tempfile

    tmp = tempfile.mkdtemp(prefix="aidd-ship-")
    try:
        git.run(["worktree", "add", "--detach", "--force", tmp, commit], cwd)
        return run(tmp)
    finally:
        git.run(["worktree", "remove", "--force", tmp], cwd, check=False)
        shutil.rmtree(tmp, ignore_errors=True)


def ship_locally(
    branch: str,
    base: str,
    *,
    squash: bool,
    message: str,
    head: str | None = None,
    cwd: str = ".",
    merged: tuple[str, str] | None = None,
    base_tip: str | None = None,
) -> str:
    """Merge `branch` into `base` locally: a merge commit that keeps the branch's history, or one squashed commit that
    keeps every agent's `Assisted-by` trailer, so provenance survives the squash. Returns the new base commit.

    `head` is the commit the gate verified: the merge takes that exact commit and refuses when the branch has moved
    since. A conflict leaves nothing half-merged: the merge is undone and the branch checked out again. With `merged`
    (the merge commit and tree `aidd ship` tested because the base moved to `base_tip`), the base moves to exactly that
    tree: the tested merge commit itself, or, squashed, one commit with that tree on `base_tip`."""
    if git.run(["status", "--porcelain", "--untracked-files=no"], cwd).strip():
        raise RuntimeError("the working tree has uncommitted changes; commit or stash them first")
    tip = git.rev_parse(branch, cwd)
    if head and tip != head:
        raise RuntimeError(f"{branch} moved to {tip[:12]} after the gate verified {head[:12]}; run `aidd ship` again")
    target = head or tip
    log = git.run(["log", "--format=%(trailers:key=Assisted-by)", f"{base}..{target}"], cwd)
    trailers = sorted({ln.strip() for ln in log.splitlines() if ln.strip()})
    if merged is not None:
        if not base_tip or git.rev_parse(base, cwd) != base_tip:
            raise RuntimeError(f"{base} moved after its merge with {target[:12]} was tested; run `aidd ship` again")
        commit, tree = merged
        if squash:
            body = message + ("\n\n" + "\n".join(trailers) if trailers else "")
            commit = git.run(["commit-tree", tree, "-p", base_tip, "-m", body], cwd).strip()
        git.run(["update-ref", f"refs/heads/{base}", commit, base_tip], cwd)
        git.run(["switch", base], cwd)
        return git.rev_parse("HEAD", cwd)
    git.run(["switch", base], cwd)
    try:
        if squash:
            git.run(["merge", "--squash", target], cwd)
            body = message + ("\n\n" + "\n".join(trailers) if trailers else "")
            git.run(["commit", "-m", body], cwd)
        else:
            git.run(["merge", "--no-ff", target, "-m", message], cwd)
    except git.GitError as exc:
        # `merge --abort` needs MERGE_HEAD, which a squash never writes; `reset --merge` undoes either kind.
        git.run(["merge", "--abort"], cwd, check=False)
        git.run(["reset", "--merge"], cwd, check=False)
        git.run(["switch", branch], cwd, check=False)
        raise RuntimeError(
            f"merging {branch} into {base} failed, so nothing was shipped and {branch} is checked out again. To recover: "
            f"on {branch}, `git merge {base}` (or rebase onto {base}), resolve the conflicts and commit, run `aidd test`, "
            f"get Merge approval on the new head, then `aidd ship` again. git said: {exc}"
        ) from exc
    return git.rev_parse("HEAD", cwd)


def _checked_out(branch: str, cwd: str) -> str | None:
    """The worktree that has `branch` checked out, or None."""
    path = None
    for line in git.run(["worktree", "list", "--porcelain"], cwd, check=False).splitlines():
        if line.startswith("worktree "):
            path = line.removeprefix("worktree ")
        elif line == f"branch refs/heads/{branch}":
            return path
    return None


def move_branch(branch: str, new: str, old: str, cwd: str = ".") -> None:
    """Move the local `branch` from `old` to `new`, a commit that holds it (`aidd integrate`'s merge). Where a worktree
    has the branch checked out, it fast-forwards there, so that worktree's files follow; a worktree with uncommitted
    changes refuses. Elsewhere only the ref moves, and only from `old`."""
    where = _checked_out(branch, cwd)
    if where is None:
        git.run(["update-ref", f"refs/heads/{branch}", new, old], cwd)
        return
    if git.run(["status", "--porcelain", "--untracked-files=no"], where, check=False).strip():
        raise RuntimeError(f"{branch} is checked out at {where} with uncommitted changes; commit or remove them there first")
    if git.rev_parse("HEAD", where) != old:
        raise RuntimeError(f"{branch} moved at {where}; run it again")
    git.run(["merge", "--ff-only", "-q", new], where)


def _upstream(branch: str, cwd: str) -> tuple[str, str] | None:
    """(the remote, the upstream's short name such as origin/goal/x) of a local branch, or None when it has none."""
    upstream = git.run(["rev-parse", "--abbrev-ref", "--symbolic-full-name", f"{branch}@{{upstream}}"], cwd, check=False).strip()
    remote = git.run(["config", "--get", f"branch.{branch}.remote"], cwd, check=False).strip()
    return (remote, upstream) if upstream and remote and remote != "." else None


def fetch_upstream(branch: str, cwd: str = ".") -> str | None:
    """Fetch the upstream of a local branch, when it has one, and return its remote-tracking ref; None when it has no
    upstream, or the fetch failed (offline: the local branch is all there is to go on)."""
    found = _upstream(branch, cwd)
    if found is None:
        return None
    remote, upstream = found
    p = git._git(["fetch", "--quiet", remote, f"refs/heads/{upstream.removeprefix(remote + '/')}:refs/remotes/{upstream}"], cwd)
    return f"refs/remotes/{upstream}" if p.returncode == 0 else None


def publish_branch(branch: str, cwd: str = ".") -> str | None:
    """Push a new local branch to `origin` and make it the upstream, when there is an `origin`: what happened, in
    words; None when there is none."""
    if "origin" not in git.run(["remote"], cwd, check=False).split():
        return None
    p = git._git(["push", "--quiet", "--set-upstream", "origin", f"refs/heads/{branch}:refs/heads/{branch}"], cwd)
    return (
        f"pushed {branch} to origin" if p.returncode == 0 else f"note: {branch} was not pushed to origin ({p.stderr.decode('utf-8', errors='replace').strip()})"
    )


def push_branch(branch: str, cwd: str = ".") -> str | None:
    """Push `branch` to its upstream, when it has one: what happened, in words; None when it has no upstream."""
    found = _upstream(branch, cwd)
    if found is None:
        return None
    remote, upstream = found
    p = git._git(["push", "--quiet", remote, f"refs/heads/{branch}:refs/heads/{upstream.removeprefix(remote + '/')}"], cwd)
    if p.returncode != 0:
        why = p.stderr.decode("utf-8", errors="replace").strip()
        return (
            f"note: {branch} was not pushed to {upstream} ({why}). If it moved there too, a person brings the two together; "
            "`aidd integrate` pushes it again on its next run"
        )
    return f"pushed {branch} to {upstream}"
