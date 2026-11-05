"""Thin wrappers over git. Every call reads objects; none runs code from the tree.

Every git process goes through `_git`, which bounds it with a timeout: a hung fetch or a pathological
repository ends the run with a GitError, never hangs it. No call runs a shell: each is an argv list. The git on PATH
and the environment stay as given, because a CI runner or a person may install git elsewhere or set GIT_* on purpose.
"""

from __future__ import annotations

import os
import re
import subprocess

DEFAULT_TIMEOUT_SECONDS = 300
# A fetch that trickles below 1000 bytes/s for 60s is abandoned rather than holding a CI job open.
FETCH_ENV = {"GIT_HTTP_LOW_SPEED_LIMIT": "1000", "GIT_HTTP_LOW_SPEED_TIME": "60", "GIT_TERMINAL_PROMPT": "0"}


class GitError(RuntimeError):
    pass


def _shown(args: list[str]) -> str:
    return " ".join("<redacted>" if "extraheader" in a.lower() or "authorization" in a.lower() else a for a in args)


def _git(
    args: list[str], cwd: str = ".", *, env: dict[str, str] | None = None, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS, input: str | None = None
) -> subprocess.CompletedProcess[bytes]:
    # Every object reads as written: a replace ref (`git replace`), which only this machine holds, never stands one
    # object in for another, such as a Spec or the base branch's config.
    env = {**(os.environ if env is None else env), "GIT_NO_REPLACE_OBJECTS": "1"}
    argv = ["git", *args]
    try:
        if input is not None:
            return subprocess.run(argv, cwd=cwd, capture_output=True, env=env, timeout=timeout_seconds, input=input.encode("utf-8"))
        return subprocess.run(argv, cwd=cwd, capture_output=True, env=env, timeout=timeout_seconds, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise GitError(f"git {_shown(args)}: timed out after {timeout_seconds}s") from None
    except OSError as exc:
        raise GitError(f"git {_shown(args)}: {exc}") from None


def _text(b: bytes | str | None) -> str:
    return b if isinstance(b, str) else (b or b"").decode("utf-8", errors="replace")


def run(
    args: list[str],
    cwd: str = ".",
    check: bool = True,
    env: dict[str, str] | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    input: str | None = None,
    *,
    raw: bool = False,
) -> str:
    """git's output as text, with universal newlines as text mode reads them; `raw` (and any `-z` command, whose NUL
    separated names may hold a carriage return) keeps it exactly as git wrote it."""
    p = _git(args, cwd, env=env, timeout_seconds=timeout_seconds, input=input)
    if check and p.returncode != 0:
        raise GitError(f"git {_shown(args)}: {_text(p.stderr).strip() or _text(p.stdout).strip()}")
    out = _text(p.stdout)
    if raw or "-z" in args:
        return out
    return out.replace("\r\n", "\n").replace("\r", "\n")


def attempt(args: list[str], cwd: str = ".", env: dict[str, str] | None = None) -> tuple[int, str]:
    """git's exit code and its error output as text, for a call whose failure the caller reads, such as a fetch."""
    p = _git(args, cwd, env=env)
    return p.returncode, _text(p.stderr).strip()


def rev_parse(ref: str, cwd: str = ".") -> str:
    return run(["rev-parse", "--verify", f"{ref}^{{commit}}"], cwd).strip()


def ok(args: list[str], cwd: str = ".") -> bool:
    """Whether a git command succeeds; for yes/no questions such as merge-base --is-ancestor."""
    return _git(args, cwd).returncode == 0


def merge_base(a: str, b: str, cwd: str = ".") -> str:
    return run(["merge-base", a, b], cwd).strip()


def show_bytes(ref: str, path: str, cwd: str = ".") -> bytes | None:
    p = _git(["show", f"{ref}:{path}"], cwd)
    return p.stdout if p.returncode == 0 else None


def show(ref: str, path: str, cwd: str = ".") -> str | None:
    b = show_bytes(ref, path, cwd)
    return None if b is None else _text(b)


def ls_tree(ref: str, cwd: str = ".", *, paths: list[str] | None = None) -> dict[str, str]:
    """Each file of `ref`'s tree by its path from the top, and its blob's id; under `paths` only, when given."""
    out = run(["ls-tree", "-r", "-z", "--full-tree", ref, *(["--", *paths] if paths else [])], cwd)
    tree: dict[str, str] = {}
    for entry in out.split("\0"):
        if not entry:
            continue
        meta, path = entry.split("\t", 1)
        _mode, obj_type, oid = meta.split()
        if obj_type == "blob":
            tree[path] = oid
    return tree


def numstat(base: str, head: str | None, cwd: str = ".") -> list[dict]:
    """Each file a diff changes, with its added and deleted lines; `head` None compares `base` with the working tree."""
    out = run(["diff", "--numstat", "-z", "-M", base, *([] if head is None else [head])], cwd)
    tokens = out.split("\0")
    files: list[dict] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if not t:
            i += 1
            continue
        add, dele, path = t.split("\t", 2)
        if path == "":
            old, new = tokens[i + 1], tokens[i + 2]
            i += 3
        else:
            old, new = None, path
            i += 1
        files.append(
            {
                "path": new,
                "previous_path": old,
                "additions": 0 if add == "-" else int(add),
                "deletions": 0 if dele == "-" else int(dele),
                "binary": add == "-" and dele == "-",
            }
        )
    return files


_SHA = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")


def log_fields(
    args: list[str], fields: list[str], cwd: str = ".", *, check: bool = True, options: list[str] | None = None, env: dict[str, str] | None = None
) -> list[list[str]]:
    """`git log <args>` as one list of `fields` (placeholders such as %H, %ae, %aI, %G?) per commit, newest first.

    Only fixed fields, never a message: each is NUL-separated (-z), and none can hold a NUL, so no commit can add a
    record or a field of its own. The first field must be %H; output that does not split into whole records starting
    with a commit id raises GitError (which fails closed), since a misaligned record could name the wrong commit. A
    message comes from `messages`, which reads each by its length. `options` go before `log` (`-c key=value`)."""
    if not fields or fields[0] != "%H":
        raise ValueError("log_fields needs %H as its first field")
    out = run([*(options or []), "log", "-z", f"--format={'%x00'.join(fields)}", *args], cwd, check=check, env=env, raw=True)
    tokens = out.split("\0")
    if tokens and tokens[-1] == "":
        tokens.pop()
    n = len(fields)
    if len(tokens) % n:
        raise GitError(f"git log {' '.join(args)}: its output does not split into records of {n} fields")
    records = [tokens[i : i + n] for i in range(0, len(tokens), n)]
    if any(not _SHA.fullmatch(rec[0]) for rec in records):
        raise GitError(f"git log {' '.join(args)}: a record does not start with a commit id")
    return records


def raw_commits(shas: list[str], cwd: str = ".") -> dict[str, bytes]:
    """Each commit object's raw bytes (its headers, a blank line, and its message), read length-prefixed through
    `git cat-file --batch`, so nothing a message holds can split one commit into two. A missing object is left out."""
    return raw_objects(shas, cwd, "commit")


def raw_objects(shas: list[str], cwd: str = ".", obj_type: str = "blob") -> dict[str, bytes]:
    """Each object of type `obj_type` by its raw bytes, read length-prefixed through `git cat-file --batch`. A missing
    object, or one of another type, is left out."""
    if not shas:
        return {}
    p = _git(["cat-file", "--batch"], cwd, input="".join(f"{s}\n" for s in shas))
    if p.returncode != 0:
        raise GitError(f"git cat-file --batch: {_text(p.stderr).strip()}")
    data, pos, found = p.stdout, 0, {}
    for sha in shas:
        nl = data.find(b"\n", pos)
        if nl < 0:
            break
        header = data[pos:nl].split()
        pos = nl + 1
        if len(header) != 3:
            continue  # "<sha> missing"
        size = int(header[2])
        if header[1] == obj_type.encode("ascii"):
            found[sha] = data[pos : pos + size]
        pos += size + 1
    return found


def commit_message(raw: bytes) -> str:
    """A raw commit object's message (what %B prints), decoded as its `encoding` header says (UTF-8 when it has none),
    with universal newlines."""
    head, sep, body = raw.partition(b"\n\n")
    if not sep:
        return ""
    encoding = "utf-8"
    for line in head.split(b"\n"):
        if line.startswith(b"encoding "):
            encoding = line[9:].decode("ascii", errors="replace").strip() or "utf-8"
    try:
        text = body.decode(encoding, errors="replace")
    except LookupError:
        text = body.decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def messages(shas: list[str], cwd: str = ".") -> dict[str, str]:
    """Each commit's message, read by its length (see `raw_commits`)."""
    return {sha: commit_message(raw) for sha, raw in raw_commits(shas, cwd).items()}


def commits(base: str, head: str, cwd: str = ".") -> list[dict]:
    """The commits in `base..head`, newest first: id, author, committer, message, and whether each is a merge."""
    records = log_fields([f"{base}..{head}"], ["%H", "%ae", "%ce", "%P"], cwd)
    bodies = messages([r[0] for r in records], cwd)
    return [
        {
            "sha": sha,
            "author": f"email:{ae}" if ae else None,
            "committer": f"email:{ce}" if ce else None,
            "message": bodies.get(sha, "").rstrip("\n"),
            "merge": len(parents.split()) > 1,
        }
        for sha, ae, ce, parents in records
    ]


def common_dir(cwd: str = ".") -> str:
    """The clone's common git folder, absolute: `.git` of the main checkout, which every worktree of the clone shares."""
    return run(["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd).strip()


def toplevel(cwd: str = ".", check: bool = False) -> str:
    """The repository's top-level directory; "" when `cwd` is not in one (unless `check`, which raises)."""
    return run(["rev-parse", "--show-toplevel"], cwd, check=check).strip()


def dirty(cwd: str = ".", *, untracked: bool = False, check: bool = True) -> list[str]:
    """Paths with uncommitted changes, exactly as named (-z: no quoting; a rename's or copy's source entry is skipped)."""
    tokens = run(["status", "--porcelain", "-z", f"--untracked-files={'all' if untracked else 'no'}"], cwd, check=check).split("\0")
    out, i = [], 0
    while i < len(tokens):
        entry = tokens[i]
        i += 1
        if len(entry) < 4:
            continue
        out.append(entry[3:])
        if entry[0] in "RC":
            i += 1
    return out


def default_base(cwd: str = ".") -> str:
    """The base branch to compare against when --base is not given: the trunk. That is the remote's default branch,
    unless this machine's branch of the same name holds all of it and more: work landed here and not yet published
    (the local trunk), which the next change builds on."""
    head = run(["symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"], cwd, check=False).strip()
    for ref in ([head] if head else []) + ["origin/main", "origin/master", "main", "master"]:
        if run(["rev-parse", "-q", "--verify", f"{ref}^{{commit}}"], cwd, check=False).strip():
            return _local_trunk(ref, cwd) or ref
    raise GitError("cannot find a base branch (tried origin/HEAD, origin/main, origin/master, main, master); pass --base <ref>")


def _local_trunk(ref: str, cwd: str) -> str | None:
    """The local branch `ref` names (`origin/main` -> `main`) when it is strictly ahead of `ref`: it holds every commit
    of `ref`, and more. None when `ref` is local already, when there is no such branch, or when it is behind or apart."""
    remote, _, name = ref.partition("/")
    if not name or remote not in run(["remote"], cwd, check=False).split():
        return None
    local = run(["rev-parse", "-q", "--verify", f"refs/heads/{name}^{{commit}}"], cwd, check=False).strip()
    tip = run(["rev-parse", "-q", "--verify", f"{ref}^{{commit}}"], cwd, check=False).strip()
    if not local or local == tip:
        return None
    return name if _git(["merge-base", "--is-ancestor", tip, local], cwd).returncode == 0 else None


def changed_since(root: str, base: str, *pathspec: str) -> list[str]:
    """Paths (under `pathspec`) that differ from `base`: committed on the branch, staged, unstaged, or untracked."""
    tail = ["--", *pathspec] if pathspec else []
    changed = run(["diff", "--name-only", "-z", base, *tail], root, check=False).split("\0")
    changed += run(["ls-files", "--others", "--exclude-standard", "-z", *tail], root, check=False).split("\0")
    return sorted({p for p in changed if p})


def branch_base(root: str) -> str:
    """The merge-base of HEAD and the default branch, or HEAD when there is none."""
    try:
        return merge_base(rev_parse(default_base(root), root), rev_parse("HEAD", root), root)
    except (GitError, ValueError, LookupError):
        return "HEAD"
