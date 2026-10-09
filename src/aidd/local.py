"""Local-first: approvals and merges on one machine, with no GitHub or GitLab.

A solo founder, or a team that keeps work local and pushes later, still gets the two human decisions. An approval
is a commit on the private ref `refs/aidd/approvals` (outside every branch and tag) whose message is the approval
line; the local gate reads it as it reads a platform's review or comment. `aidd ship` then merges a passing branch
into the base branch, keeping its history or squashing it.

The limit, said plainly: on one machine the agent runs as you. The hook denies `aidd approve` and `aidd ship` to
agents, and both refuse to run without a person at an interactive terminal who types back a one-time code the prompt
shows, which an agent cannot know before the prompt appears (as it knows the Spec id or a commit). Set up git
commit signing with an SSH key that asks for your presence (a hardware key, or an SSH agent that prompts), list each
Approver's key in the base branch's allowed signers file (`gates.local_signers`, `.aidd/allowed_signers` by default),
and set `gates.local_approvals = "signed"` in the base branch\'s config: then only approvals whose SSH signature
ssh-keygen verifies against that file, from the principal the approval's author email names, count. Both the
requirement and the keys come from the base branch, and the check pins its own gpg settings, so neither this
machine's git config nor its `gpg.ssh.allowedSignersFile`, which an agent could edit, decides it; with no signers
file on the base branch, no approval counts. What stays on this machine is the private key and the programs that run
(git, ssh-keygen): an agent that can use your key, or replace those programs, still defeats it. Without signing, a
local approval is as strong as the hook and the terminal check. A platform's review is stronger; push to one when
the work matters to other people.
"""

from __future__ import annotations

import datetime as dt
import os
import secrets
import sys

from . import gitutil

APPROVALS_REF = "refs/aidd/approvals"
# The allowed signers file (`gates.local_signers`), read from the base branch: whose signatures count as approvals.
DEFAULT_SIGNERS = ".aidd/allowed_signers"
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
MERGE_TRAILER = "Aidd-Merge-Approval"
# The branch a Merge approval was given on, so another branch's approval is never read as this one's; and a cool-off the
# person skipped on record (`--skip-cooloff`).
BRANCH_TRAILER = "Aidd-Branch"
COOLOFF_TRAILER = "Aidd-Cooloff"
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


def check_terminal(what: str, command: str = "") -> None:
    """Refuse before anything else when no person can be at this terminal: a shell an agent started, or no terminal.
    The refusal ends with `command`, when given, for the person to copy."""
    copy = f":\n  {command}" if command else "."
    if any(os.environ.get(v) for v in AGENT_ENV):
        raise NotAPerson(f"{what} is a person's decision, and an agent started this shell. A person runs it in a terminal no agent started{copy}")
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise NotAPerson(f"{what} needs a person at an interactive terminal. Run it there{copy}")


def require_person(what: str, ask=None, command: str = "") -> None:
    """A person types back a one-time code shown at an interactive terminal; an agent's tool shell has no terminal.

    The code is random and made when the prompt appears, so an agent that started a terminal running this command
    cannot have typed the answer ahead of time, as it could type the Spec id, the head commit, or the branch name.
    `ask` defaults to the built-in `input`, looked up at call time."""
    ask = ask or input
    check_terminal(what, command)
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


def signers_path(cfg) -> str:
    """Where the base branch keeps the people whose signatures count (`gates.local_signers`)."""
    return str((cfg.gates.get("local_signers") if cfg is not None else None) or DEFAULT_SIGNERS)


def base_signers(cfg, base_ref: str | None, cwd: str = ".") -> str | None:
    """The allowed signers file as the base branch's tip holds it, or None when it has none. Never the working tree's
    copy, and never this machine's `gpg.ssh.allowedSignersFile`: an agent on this machine can edit both."""
    if not base_ref:
        return None
    return gitutil.show(base_ref, signers_path(cfg), cwd)


# The configuration every signature check pins, whatever this machine's git config says: SSH signatures, checked by
# ssh-keygen against the base branch's signers. An agent can point gpg.ssh.program at a script that always says good.
_PINNED = ("gpg.format=ssh", "gpg.ssh.program=ssh-keygen")


def _pinned_env() -> dict[str, str]:
    """This process's environment without configuration passed through it (`GIT_CONFIG_PARAMETERS`, `GIT_CONFIG_COUNT`
    and its keys), which could reach past the `-c` options the check sets."""
    return {
        k: v
        for k, v in os.environ.items()
        if not (k.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")) or k in ("GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT"))
    }


def _records(cwd: str, signers: str | None) -> list[list[str]]:
    fields = ["%H", "%ae", "%aI", "%G?", "%GS"]
    if signers is None:
        return gitutil.log_fields([APPROVALS_REF], fields, cwd)
    import tempfile

    fd, path = tempfile.mkstemp(prefix="aidd-signers-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(signers)
        options = [x for kv in (*_PINNED, f"gpg.ssh.allowedSignersFile={path}") for x in ("-c", kv)]
        return gitutil.log_fields([APPROVALS_REF], fields, cwd, options=options, env=_pinned_env())
    finally:
        os.unlink(path)


# What an approval's message may never hold: the separators an older reader split records on, and NUL.
_SEPARATORS = ("\x00", "\x1e", "\x1f")


def load(
    cwd: str = ".", require_signed: bool = False, *, signers: str | None = None, signers_file: str = DEFAULT_SIGNERS
) -> tuple[list[dict], list[dict], list[str]]:
    """The recorded approvals as the gate reads them: (reviews, comments, notes about what did not count).

    Every approval carries `verified`: whether its signature verifies. `signers` is the allowed signers file the base
    branch holds (`base_signers`, at `signers_file`): when given, only an SSH signature from a key it lists for the
    approval's author email verifies, checked with ssh-keygen whatever this machine's gpg.* config says. Without it, git
    checks as this machine is configured, which an agent on it can change; so under `require_signed` (the base branch's
    `gates.local_approvals = "signed"`) no approval verifies until the base branch holds the file.

    `require_signed` comes from the base branch's config, which an agent on this machine cannot change the way it can
    clear `user.signingkey`. When it is set, unverified approvals stay in the context with `verified: false` and the
    gate drops them (`merge_approval.unsigned`, `spec_approval.unsigned`), so the rule is checkable from the context
    alone. When only this machine has git signing set up, they are dropped here.

    Each approval's fields are read NUL-separated and its message by its length, so a message cannot forge another
    approval, its author, or its signature; a message holding NUL or an ASCII record or unit separator never counts."""
    if not gitutil.ok(["rev-parse", "--verify", "--quiet", APPROVALS_REF], cwd):
        return [], [], []
    records = _records(cwd, signers)
    raw = gitutil.raw_commits([r[0] for r in records], cwd)
    need_signature = require_signed or signing(cwd)
    pinned = signers is not None
    ssh = pinned or gitutil.config_value("gpg.format", cwd).lower() == "ssh"
    reviews: list[dict] = []
    comments: list[dict] = []
    notes: list[str] = []
    if require_signed and not pinned:
        notes.append(
            f'gates.local_approvals = "signed", but the base branch has no {signers_file}, so no local approval counts. Add one '
            f"`<email> <public key>` line per Approver to {signers_file} (git's allowed signers format), and merge it to the base branch"
        )
    for sha, email, when, sig, signer in records:
        obj = raw.get(sha)
        if obj is None:
            notes.append(f"skipped approval {sha[:12]} on {APPROVALS_REF}: git could not read it")
            continue
        body = gitutil.commit_message(obj)
        if any(c in body for c in _SEPARATORS):
            notes.append(f"approval {sha[:12]} does not count: its message holds a control separator, which no approval carries")
            continue
        # With pinned signers, only an SSH signature: an OpenPGP or X.509 one is checked against this machine's keyring.
        good = verified(sig, signer, email, ssh) and (not pinned or gitutil.signature_kind(obj) == "ssh")
        if require_signed and not pinned:
            good = False  # the note above says why
        elif need_signature and not good:
            notes.append(f"approval {sha[:12]} is not signed with a trusted key of its author, so it does not count")
        if need_signature and not good:
            if not require_signed:
                continue
        user = f"email:{email}"
        lines = body.splitlines()
        branch = next((ln.split(": ", 1)[1].strip() for ln in lines if ln.startswith(f"{BRANCH_TRAILER}: ")), None)
        skipped = f"{COOLOFF_TRAILER}: skipped" in lines
        for line in lines:
            if line.startswith(f"{MERGE_TRAILER}: "):
                review = {"user": user, "state": "approved", "commit_sha": line.split(": ", 1)[1].strip(), "submitted_at": when, "verified": good}
                if skipped:
                    review["cooloff_skipped"] = True
                if branch:
                    review["branch"] = branch  # for the adapter only (localctx drops it): never part of a context
                reviews.append(review)
            elif line.startswith("/aidd "):
                comments.append({"user": user, "body": line, "created_at": when, "verified": good})
    if not need_signature and (reviews or comments):
        notes.append(
            "local approvals are not signed. Set up git commit signing with an SSH key that asks for your presence. List the key in "
            f'{signers_file} on the base branch. Then set gates.local_approvals = "signed" in the base branch\'s config: only signed approvals count after that'
        )
    return reviews, comments, notes


def approve_spec_line(spec_id: str, spec_hash: str, commit: str) -> str:
    return f"/aidd approve-spec {spec_id} {spec_hash} {commit}"


def approve_merge_line(head: str, *, branch: str | None = None, skip_cooloff: bool = False) -> str:
    """The approval record's message: the head, then the branch it was given on and a skipped cool-off, when there are."""
    extra = (f"\n{BRANCH_TRAILER}: {branch}" if branch and branch != "HEAD" else "") + (f"\n{COOLOFF_TRAILER}: skipped" if skip_cooloff else "")
    return f"{MERGE_TRAILER}: {head}{extra}\n\nApproved at {dt.datetime.now(dt.UTC).isoformat(timespec='seconds')}."


def merged_commit(base_tip: str, head: str, *, message: str, cwd: str = ".") -> tuple[str, str]:
    """The merge of `head` into `base_tip` as a commit git has not placed on any branch: (its id, its tree). It is what
    `aidd ship` tests and then lands when the base moved, so the tested tree is exactly the shipped tree. A conflict
    raises: nothing is merged, and the person merges or rebases the branch themselves."""
    p = gitutil._git(["merge-tree", "--write-tree", "--no-messages", base_tip, head], cwd)
    tree = p.stdout.decode("utf-8", errors="replace").split("\n", 1)[0].strip()
    if p.returncode == 1:
        raise RuntimeError(
            f"{head[:12]} conflicts with the base tip {base_tip[:12]}, so nothing was tested or shipped. Merge or rebase the base "
            "into the branch, and resolve the conflicts. Then run `aidd test`, get Merge approval on the new head, and `aidd ship` again"
        )
    if p.returncode != 0 or not tree:
        raise gitutil.GitError(f"git merge-tree {base_tip[:12]} {head[:12]}: {p.stderr.decode('utf-8', errors='replace').strip()}")
    sha = gitutil.run(["commit-tree", tree, "-p", base_tip, "-p", head, "-m", message], cwd).strip()
    return sha, tree


def run_in_worktree(commit: str, run, cwd: str = "."):
    """`run(path)` in a temporary detached worktree of `commit`, removed afterwards."""
    import shutil
    import tempfile

    tmp = tempfile.mkdtemp(prefix="aidd-ship-")
    try:
        gitutil.run(["worktree", "add", "--detach", "--force", tmp, commit], cwd)
        return run(tmp)
    finally:
        gitutil.run(["worktree", "remove", "--force", tmp], cwd, check=False)
        shutil.rmtree(tmp, ignore_errors=True)


def ship(
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
    if gitutil.run(["status", "--porcelain", "--untracked-files=no"], cwd).strip():
        raise RuntimeError("the working tree has uncommitted changes; commit or stash them first")
    tip = gitutil.rev_parse(branch, cwd)
    if head and tip != head:
        raise RuntimeError(f"{branch} moved to {tip[:12]} after the gate verified {head[:12]}; run `aidd ship` again")
    target = head or tip
    log = gitutil.run(["log", "--format=%(trailers:key=Assisted-by)", f"{base}..{target}"], cwd)
    trailers = sorted({ln.strip() for ln in log.splitlines() if ln.strip()})
    if merged is not None:
        if not base_tip or gitutil.rev_parse(base, cwd) != base_tip:
            raise RuntimeError(f"{base} moved after its merge with {target[:12]} was tested; run `aidd ship` again")
        commit, tree = merged
        if squash:
            body = message + ("\n\n" + "\n".join(trailers) if trailers else "")
            commit = gitutil.run(["commit-tree", tree, "-p", base_tip, "-m", body], cwd).strip()
        gitutil.run(["update-ref", f"refs/heads/{base}", commit, base_tip], cwd)
        gitutil.run(["switch", base], cwd)
        return gitutil.rev_parse("HEAD", cwd)
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
