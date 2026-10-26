"""Local-first landing: the person check before an approval or a merge, and `aidd land`, which tests the merge of a
passing branch and lands exactly that tree. The person's decisions themselves are in workitems/decision_records.py."""

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
    if words[:2] == ["aidd", "land"]:
        return "land it"
    if words[:2] == ["aidd", "publish"]:
        return "publish"
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
    denies an agent's `aidd approve` and `aidd land`), and a signing key that asks for your presence are the controls,
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
    `aidd land` tests and then lands when the base moved, so the tested tree is exactly the landed tree, signed as the
    repository signs its commits. A conflict raises: nothing is merged, and the person merges or rebases the branch."""
    tree = merged_tree(base_tip, head, cwd)
    if tree is None:
        raise RuntimeError(
            f"{head[:12]} conflicts with the base tip {base_tip[:12]}, so nothing was tested or landed. Merge or rebase the base "
            "into the branch, and resolve the conflicts. Then run `aidd test`, get Merge approval on the new head, and `aidd land` again"
        )
    return _commit_tree(tree, ["-p", base_tip, "-p", head], message, cwd), tree


def merged_tree(base_tip: str, head: str, cwd: str = ".") -> str | None:
    """The tree of `head` merged into `base_tip`, built without a checkout; None on a conflict."""
    p = git._git(["merge-tree", "--write-tree", "--no-messages", base_tip, head], cwd)
    tree = p.stdout.decode("utf-8", errors="replace").split("\n", 1)[0].strip()
    if p.returncode == 1:
        return None
    if p.returncode != 0 or not tree:
        raise git.GitError(f"git merge-tree {base_tip[:12]} {head[:12]}: {p.stderr.decode('utf-8', errors='replace').strip()}")
    return tree


def _commit_tree(tree: str, parents: list[str], message: str, cwd: str) -> str:
    """A commit of `tree` on `parents`, signed when the repository sets `commit.gpgsign`, which `commit-tree` never reads
    itself. A signature git cannot make lands nothing and names the fix."""
    p = git._git(["config", "--bool", "commit.gpgsign"], cwd)
    if p.returncode not in (0, 1):
        raise RuntimeError(
            f"nothing moved: commit.gpgsign is not true or false ({p.stderr.decode('utf-8', errors='replace').strip()}); fix it in your git config"
        )
    signed = ["-S"] if p.stdout.decode().strip() == "true" else []
    try:
        return git.run(["commit-tree", tree, *parents, "-F", "-", *signed], cwd, input=message).strip()
    except git.GitError as exc:
        if not signed:
            raise
        raise RuntimeError(
            f"nothing moved: git could not sign the commit ({exc}). Set up your signing key (`user.signingkey`), or unset "
            "`commit.gpgsign`, then run the command again"
        ) from None


# On land's own git calls: no hook runs, since a hook in the working tree holds the branch's code, which would run with
# the person's credentials after the gate. Only the commit-msg hook runs, on purpose (commit_msg_hook).
NO_HOOKS = ["-c", f"core.hooksPath={os.devnull}"]


def run_in_worktree(commit: str, run, cwd: str = "."):
    """`run(path)` in a temporary detached worktree of `commit`, removed afterwards."""
    import shutil
    import tempfile

    tmp = tempfile.mkdtemp(prefix="aidd-land-")
    try:
        git.run([*NO_HOOKS, "worktree", "add", "--detach", "--force", tmp, commit], cwd)
        return run(tmp)
    finally:
        git.run([*NO_HOOKS, "worktree", "remove", "--force", tmp], cwd, check=False)
        shutil.rmtree(tmp, ignore_errors=True)


def land_locally(
    branch: str,
    base: str,
    *,
    squash: bool,
    message: str,
    head: str | None = None,
    cwd: str = ".",
    merged: tuple[str, str] | None = None,
    base_tip: str | None = None,
    notes: list[str] | None = None,
) -> str:
    """Merge `branch` into `base` locally: a merge commit that keeps the branch's history, or one squashed commit that
    keeps every agent's `Assisted-by` trailer, so provenance survives the squash. Returns the new base commit.

    `head` is the commit the gate verified: the merge takes that exact commit and refuses when the branch has moved
    since. With `merged` (the merge commit and tree `aidd land` tested because the base moved to `base_tip`), the base
    moves to exactly that tree: the tested merge commit itself, or, squashed, one commit with that tree on `base_tip`.

    The commit is built without a checkout, and every refusal comes before the base moves, so a conflict or a refusal
    leaves nothing half-landed. The repository's `commit-msg` hook checks or edits the message, as `git commit` runs it;
    no other commit hook runs, since there is no checkout to check (`notes` names the hook that ran). The base then moves where it is checked out: a worktree that holds it fast-forwards, so
    its files follow. Where none holds it, only the ref moves, and the root checkout switches to it, as a single checkout
    expects; a linked worktree keeps its own branch, since git lets only one worktree hold the base."""
    if git.run(["status", "--porcelain", "--untracked-files=no"], cwd).strip():
        raise RuntimeError("the working tree has uncommitted changes; commit or stash them first")
    tip = git.rev_parse(branch, cwd)
    if head and tip != head:
        raise RuntimeError(f"{branch} moved to {tip[:12]} after the gate verified {head[:12]}; run `aidd land` again")
    target = head or tip
    log = git.run(["log", "--format=%(trailers:key=Assisted-by)", f"{base}..{target}"], cwd)
    trailers = sorted({ln.strip() for ln in log.splitlines() if ln.strip()})
    now = git.rev_parse(base, cwd)
    text = message + ("\n\n" + "\n".join(trailers) if trailers else "") if squash else message
    tested = None
    if merged is not None:
        if not base_tip or now != base_tip:
            raise RuntimeError(f"{base} moved after its merge with {target[:12]} was tested; run `aidd land` again")
        tested, tree = merged
    else:
        if base_tip and now != base_tip:
            raise RuntimeError(f"{base} moved to {now[:12]} after the tests ran on {base_tip[:12]}; run `aidd land` again")
        base_tip = now
        found = merged_tree(base_tip, target, cwd)
        if found is None:
            raise _conflict(branch, base)
        tree = found
    checked = commit_msg_hook(text, base_tip, cwd, notes)
    if lost := sorted(_assisted_by(text, cwd) - _assisted_by(checked, cwd)):
        raise RuntimeError(
            f"the commit-msg hook removed {', '.join(lost)} from the message, so nothing was landed: the landed commit keeps every agent's trailer"
        )
    if tested is not None and not squash and checked == text:
        commit = tested  # the tested merge commit itself
    else:
        commit = _commit_tree(tree, ["-p", base_tip] if squash else ["-p", base_tip, "-p", target], checked, cwd)
    _move_base(base, commit, base_tip, cwd, notes)
    return commit


def _conflict(branch: str, base: str) -> RuntimeError:
    return RuntimeError(
        f"{branch} conflicts with {base}, so nothing was landed and {branch} stays checked out. To recover: on {branch}, "
        f"`git merge {base}` (or rebase onto {base}), resolve the conflicts and commit, run `aidd test`, get Merge "
        "approval on the new head, then `aidd land` again"
    )


HOOK_SECONDS = 300  # a hook may start a linter through a package runner


def commit_msg_hook(text: str, base_tip: str, cwd: str, notes: list[str] | None = None) -> str:
    """The message after the repository's `commit-msg` hook, which may check or edit it, as `git commit` runs it. A hook
    that fails refuses the land with its own words, before anything moves. With no hook, the message as it is.

    The hook runs in a worktree of the base tip, so the hook, what it reads from the tree, and a hook manager's config
    (pre-commit, lefthook, husky) are the base's, never the branch's, and with credentials removed, as the tests run.
    It runs only from the base's tree or the git directory; a hook anywhere else is skipped with a note."""
    if not git.config_value("core.hooksPath", cwd) and not os.path.isfile(
        git.run(["rev-parse", "--path-format=absolute", "--git-path", "hooks/commit-msg"], cwd).strip()
    ):
        return text  # no hook anywhere: no worktree to make
    return run_in_worktree(base_tip, lambda tmp: _run_commit_msg_hook(text, tmp, notes), cwd)


def _run_commit_msg_hook(text: str, tmp: str, notes: list[str] | None) -> str:
    import tempfile

    from aidd.kernel import processes

    hook = git.run(["rev-parse", "--path-format=absolute", "--git-path", "hooks/commit-msg"], tmp).strip()
    if not os.path.lexists(hook):
        return text
    gitdir = Path(git.run(["rev-parse", "--path-format=absolute", "--git-common-dir"], tmp).strip()).resolve()
    trusted = [Path(tmp).resolve(), gitdir]
    if not any(Path(hook).resolve().is_relative_to(d) and Path(os.path.abspath(hook)).resolve(strict=False).is_relative_to(d) for d in trusted):
        if notes is not None:
            notes.append(
                f"did not run the commit-msg hook {hook}: it is outside the base's tree and the git directory. A check you rely on belongs in `aidd test` or CI"
            )
        return text
    if not os.access(hook, os.X_OK):
        return text
    env = processes.scrub_credentials(dict(os.environ))
    for name in ("SSH_AUTH_SOCK", "GPG_AGENT_INFO"):
        env.pop(name, None)
    fd, path = tempfile.mkstemp(prefix="aidd-land-msg-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        code, out, err = processes.run_bounded(["git", "hook", "run", "commit-msg", "--", path], timeout_seconds=HOOK_SECONDS, cwd=tmp, env=env)
        if code is None:
            raise RuntimeError(f"the commit-msg hook ({hook}) did not finish in {HOOK_SECONDS} s, so nothing was landed")
        if code != 0:
            raise RuntimeError(
                f"the repository's commit-msg hook ({hook}) refused the land's message, so nothing was landed. Fix what it "
                f"names, or give the message with `aidd land --message`, then `aidd land` again. It said: {(out + err).strip() or 'nothing'}"
            )
        checked = Path(path).read_text(encoding="utf-8")
    finally:
        os.unlink(path)
    if notes is not None:
        notes.append("ran the commit-msg hook as the base holds it, on the landed commit's message; no other hook runs on a land")
    return checked


def _assisted_by(message: str, cwd: str) -> set[str]:
    """The `Assisted-by` trailers git's trailer parser finds in `message`."""
    lines = git.run(["interpret-trailers", "--parse"], cwd, input=message).splitlines()
    return {ln.strip() for ln in lines if ln.lower().startswith("assisted-by:")}


def _move_base(base: str, commit: str, base_tip: str, cwd: str, notes: list[str] | None = None) -> None:
    """Move `base` from `base_tip` to `commit` where it is checked out (move_branch), and switch the root checkout to
    it when no worktree holds it. A worktree that holds it with uncommitted changes refuses, and the base stays."""
    held = checked_out(base, cwd) is not None
    try:
        move_branch(base, commit, base_tip, cwd, again="`aidd land`")
    except (RuntimeError, git.GitError) as exc:
        raise RuntimeError(f"nothing was landed: {exc}") from exc
    if not held and _is_root_checkout(cwd):
        p = git._git([*NO_HOOKS, "switch", base], cwd)
        if p.returncode != 0 and notes is not None:
            said = p.stderr.decode("utf-8", errors="replace").strip()
            notes.append(f"{base} moved to {commit[:12]}, but this checkout stayed on its branch ({said}): clear what git names, then `git switch {base}`")


def _is_root_checkout(cwd: str) -> bool:
    """Whether `cwd` is in the repository's root checkout, not a linked worktree."""
    dirs = git.run(["rev-parse", "--path-format=absolute", "--git-dir", "--git-common-dir"], cwd, check=False).split()
    return len(dirs) == 2 and dirs[0] == dirs[1]


def checked_out(branch: str, cwd: str) -> str | None:
    """The worktree that has `branch` checked out, or None."""
    return next((w["path"] for w in git.worktrees(cwd) if w.get("branch") == branch), None)


def move_branch(branch: str, new: str, old: str, cwd: str = ".", *, again: str = "it") -> None:
    """Move the local `branch` from `old` to `new`, a commit that holds it (`aidd integrate`'s merge). Where a worktree
    has the branch checked out, it fast-forwards there, so that worktree's files follow; a worktree with uncommitted
    changes refuses. Elsewhere only the ref moves, and only from `old`. Before anything runs in that worktree, it must
    be one of this repository's, on `branch`; after, the branch must be at `new`. `again` is the command to run again."""
    where = checked_out(branch, cwd)
    if where is None:
        git.run([*NO_HOOKS, "update-ref", f"refs/heads/{branch}", new, old], cwd)
        return
    if not Path(where).is_dir():
        raise RuntimeError(f"{branch} is checked out in {where}, which is gone: run `git worktree prune`, then {again} again")
    ours = git.run(["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd).strip()
    if git.run(["rev-parse", "--path-format=absolute", "--git-common-dir"], where, check=False).strip() != ours:
        raise RuntimeError(
            f"{where} is not a worktree of this repository, though git lists it as holding {branch}: run `git worktree prune`, then {again} again"
        )
    if git.run(["symbolic-ref", "-q", "HEAD"], where, check=False).strip() != f"refs/heads/{branch}":
        raise RuntimeError(f"{where} no longer has {branch} checked out; run {again} again")
    if git.run(["status", "--porcelain", "--untracked-files=no"], where, check=False).strip():
        raise RuntimeError(f"{branch} is checked out at {where} with uncommitted changes; commit or remove them there first")
    if git.rev_parse("HEAD", where) != old:
        raise RuntimeError(f"{branch} moved at {where}; run {again} again")
    git.run([*NO_HOOKS, "merge", "--ff-only", "-q", new], where)
    if git.rev_parse(f"refs/heads/{branch}", cwd) != new:
        now = git.run(["symbolic-ref", "-q", "--short", "HEAD"], where, check=False).strip() or "a detached HEAD"
        raise RuntimeError(
            f"{branch} did not move to {new[:12]} at {where}, which now has {now} checked out: another change reached it at the same "
            f"time, so check {now} there (`git -C {where} log -1`), then run {again} again"
        )


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
