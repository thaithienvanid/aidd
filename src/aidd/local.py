"""Local-first: approvals and merges on one machine, with no GitHub or GitLab.

A solo founder, or a team that keeps work local and pushes later, still gets the two human decisions. An approval
is a commit on the private ref `refs/aidd/approvals` (outside every branch and tag) whose message is the approval
line; the local gate reads it as it reads a platform's review or comment. `aidd ship` then merges a passing branch
into the base branch, keeping its history or squashing it.

The limit, said plainly: on one machine the agent runs as you. The hook denies `aidd approve` and `aidd ship` to
agents, and both refuse to run without a person at an interactive terminal who types back a one-time code the prompt
shows, which an agent cannot know before the prompt appears (as it knows the Spec id or a commit). Set up git
commit signing with a key that asks for your presence (a hardware key, or an SSH agent that prompts), and set
`gates.local_approvals = "signed"` in the base branch's config: then only approvals whose signature git verifies as
good ("G", and with SSH signing, a signer principal equal to the approval's author email) count. The requirement
comes from the base branch, not from this machine's git config, which an agent could clear. Without signing, a local
approval is as strong as the hook and the terminal check. A platform's review is stronger; push to one when the work
matters to other people.
"""

from __future__ import annotations

import datetime as dt
import os
import secrets
import sys

from . import gitutil

APPROVALS_REF = "refs/aidd/approvals"
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
MERGE_TRAILER = "Aidd-Merge-Approval"
# Variables an agent harness sets in the shells it starts: Claude Code (CLAUDECODE, CLAUDE_CODE_CHILD_SESSION), the
# generic AI_AGENT some harnesses export, and AIDD_AGENT for any other runner.
AGENT_ENV = ("CLAUDE_CODE_CHILD_SESSION", "CLAUDECODE", "AI_AGENT", "AIDD_AGENT")


class NotAPerson(RuntimeError):
    """Raised when an approval or a merge is attempted without a person at an interactive terminal."""


# The one-time code's characters: no 0/O or 1/I/L, so a person reads it back without a doubt.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6


def one_time_code() -> str:
    """A fresh random code for one confirmation, made when the prompt appears."""
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def require_person(what: str, ask=None) -> None:
    """A person types back a one-time code shown at an interactive terminal; an agent's tool shell has no terminal.

    The code is random and made when the prompt appears, so an agent that started a terminal running this command
    cannot have typed the answer ahead of time, as it could type the Spec id, the head commit, or the branch name.
    `ask` defaults to the built-in `input`, looked up at call time."""
    ask = ask or input
    if any(os.environ.get(v) for v in AGENT_ENV):
        raise NotAPerson(f"{what} is a person's decision; this shell was started by an agent. Run it in a terminal an agent did not start")
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise NotAPerson(f"{what} needs a person at an interactive terminal")
    code = one_time_code()
    try:
        answer = ask(f"{what}. Type {code} to approve: ").strip()
    except EOFError:  # Ctrl-D, or input that ended: nobody confirmed
        raise NotAPerson(f"{what} was not confirmed") from None
    if not secrets.compare_digest(answer.upper(), code):
        raise NotAPerson(f"{what} was not confirmed")


def signing(cwd: str = ".") -> bool:
    return bool(gitutil.config_value("user.signingkey", cwd))


def record(line: str, cwd: str = ".") -> tuple[str, bool]:
    """Append one approval to the approvals ref; signed when git signing is set up. Returns the commit and whether it is signed.

    The ref moves only from the parent read here (or from nothing), so two approvals recorded at once cannot drop one."""
    parent = gitutil.run(["rev-parse", "--verify", "--quiet", APPROVALS_REF], cwd, check=False).strip()
    signed = signing(cwd)
    args = ["commit-tree", EMPTY_TREE, "-m", line] + (["-p", parent] if parent else []) + (["-S"] if signed else [])
    sha = gitutil.run(args, cwd).strip()
    gitutil.run(["update-ref", APPROVALS_REF, sha, parent or "0" * len(sha)], cwd)
    return sha, signed


def verified(sig: str, signer: str, email: str, ssh: bool) -> bool:
    """A good signature from a key git trusts; with SSH signing, from the principal the author email names.

    "U" (a good signature from a key of unknown validity) does not count: anyone can make a key and sign with it."""
    return sig == "G" and (not ssh or signer.strip().lower() == email.strip().lower())


def load(cwd: str = ".", require_signed: bool = False) -> tuple[list[dict], list[dict], list[str]]:
    """The recorded approvals as the gate reads them: (reviews, comments, notes about what did not count).

    Every approval carries `verified`: whether its signature verifies (a good signature from a trusted key of its author).
    `require_signed` comes from the base branch's config (`gates.local_approvals = "signed"`), which an agent on this
    machine cannot change the way it can clear `user.signingkey`. When it is set, unverified approvals stay in the
    context with `verified: false` and the verifier drops them (`merge_approval.unsigned`, `spec_approval.unsigned`), so
    the rule is checkable from the context alone. When only this machine has git signing set up, they are dropped here."""
    if not gitutil.ok(["rev-parse", "--verify", "--quiet", APPROVALS_REF], cwd):
        return [], [], []
    out = gitutil.run(["log", "--format=%H%x1f%ae%x1f%aI%x1f%G?%x1f%GS%x1f%B%x1e", APPROVALS_REF], cwd)
    need_signature = require_signed or signing(cwd)
    ssh = gitutil.config_value("gpg.format", cwd).lower() == "ssh"
    reviews, comments, notes = [], [], []
    for entry in out.split("\x1e"):
        if not entry.strip():
            continue
        fields = entry.strip("\n").split("\x1f", 5)
        if len(fields) != 6:
            notes.append(f"skipped a malformed entry on {APPROVALS_REF}")
            continue
        sha, email, when, sig, signer, body = fields
        good = verified(sig, signer, email, ssh)
        if need_signature and not good:
            notes.append(f"approval {sha[:12]} is not signed with a trusted key of its author, so it does not count")
            if not require_signed:
                continue
        user = f"email:{email}"
        for line in body.splitlines():
            if line.startswith(f"{MERGE_TRAILER}: "):
                reviews.append({"user": user, "state": "approved", "commit_sha": line.split(": ", 1)[1].strip(), "submitted_at": when, "verified": good})
            elif line.startswith("/aidd "):
                comments.append({"user": user, "body": line, "created_at": when, "verified": good})
    if not need_signature and (reviews or comments):
        notes.append(
            "local approvals are not signed: set up git commit signing with a key that asks for your presence, and set "
            'gates.local_approvals = "signed" in the base branch\'s config, and only signed ones will count'
        )
    return reviews, comments, notes


def approve_spec_line(spec_id: str, spec_hash: str, commit: str) -> str:
    return f"/aidd approve-spec {spec_id} {spec_hash} {commit}"


def approve_merge_line(head: str) -> str:
    return f"{MERGE_TRAILER}: {head}\n\nApproved at {dt.datetime.now(dt.UTC).isoformat(timespec='seconds')}."


def ship(branch: str, base: str, *, squash: bool, message: str, head: str | None = None, cwd: str = ".") -> str:
    """Merge `branch` into `base` locally: a merge commit that keeps the branch's history, or one squashed commit that
    keeps every agent's `Assisted-by` trailer, so provenance survives the squash. Returns the new base commit.

    `head` is the commit the gate verified: the merge takes that exact commit and refuses when the branch has moved
    since. A conflict leaves nothing half-merged: the merge is undone and the branch checked out again."""
    if gitutil.run(["status", "--porcelain", "--untracked-files=no"], cwd).strip():
        raise RuntimeError("the working tree has uncommitted changes; commit or stash them first")
    tip = gitutil.rev_parse(branch, cwd)
    if head and tip != head:
        raise RuntimeError(f"{branch} moved to {tip[:12]} after the gate verified {head[:12]}; run `aidd ship` again")
    target = head or tip
    log = gitutil.run(["log", "--format=%(trailers:key=Assisted-by)", f"{base}..{target}"], cwd)
    trailers = sorted({ln.strip() for ln in log.splitlines() if ln.strip()})
    gitutil.run(["switch", base], cwd)
    try:
        if squash:
            gitutil.run(["merge", "--squash", target], cwd)
            body = message + ("\n\n" + "\n".join(trailers) if trailers else "")
            gitutil.run(["commit", "-m", body], cwd)
        else:
            gitutil.run(["merge", "--no-ff", target, "-m", message], cwd)
    except gitutil.GitError as exc:
        # `merge --abort` needs MERGE_HEAD, which a squash never writes; `reset --merge` undoes either kind.
        gitutil.run(["merge", "--abort"], cwd, check=False)
        gitutil.run(["reset", "--merge"], cwd, check=False)
        gitutil.run(["switch", branch], cwd, check=False)
        raise RuntimeError(
            f"merging {branch} into {base} failed, so nothing was shipped and {branch} is checked out again. To recover: "
            f"on {branch}, `git merge {base}` (or rebase onto {base}), resolve the conflicts and commit, run `aidd test`, "
            f"get Merge approval on the new head, then `aidd ship` again. git said: {exc}"
        ) from exc
    return gitutil.rev_parse("HEAD", cwd)
