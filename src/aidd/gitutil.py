"""Thin wrappers over git. Every call reads objects; none runs code from the tree.

Every git process goes through `_git`, which bounds it with a timeout: a hung fetch or a pathological
repository ends the run with a GitError (which fails closed), never hangs it.

Inside `system_only()` (the guard and the session hooks), `_git` hardens each call, because a project's
settings can set PATH and the environment, and the repository's own config can name programs git runs:
- the program is the first of SYSTEM_GITS that answers `git --version`, never a git the session's PATH names;
- the environment is an allowlist (SYSTEM_ENV and a fixed PATH), so GIT_DIR, LD_PRELOAD, DYLD_*, and a project's
  `git-*` helpers never reach git. No GIT_* variable is needed: git finds a linked worktree from its `.git` file;
- through GIT_CONFIG_COUNT, GIT_CONFIG_KEY_<n>, and GIT_CONFIG_VALUE_<n> (the only GIT_* variables git sees, never
  split on `=`), it turns off core.fsmonitor, hooks, the ext transport, and credential helpers, and empties every
  filter, diff, and merge driver program that the repository's own config sets: `.git/config`, the worktree config,
  what they include, and any config file inside the repository.
The user's global and the system config stay in force (safe.directory, core.excludesFile, a Git LFS filter): only the
repository is the threat. Every other command keeps the git on PATH and the environment as given, because a CI runner
or a person may install git elsewhere or set GIT_* on purpose. No call runs a shell: each is an argv list. This
defends against the repository's committed content, not against a local writer of `.git/config`, HOME, or the git
programs, which the gate in CI, on a clean checkout, covers.
"""

from __future__ import annotations

import contextlib
import contextvars
import os
import re
import subprocess
import sys
import time
from collections.abc import Iterator, Sequence

DEFAULT_TIMEOUT = 300
# A fetch that trickles below 1000 bytes/s for 60s is abandoned rather than holding the gate job open.
FETCH_ENV = {"GIT_HTTP_LOW_SPEED_LIMIT": "1000", "GIT_HTTP_LOW_SPEED_TIME": "60", "GIT_TERMINAL_PROMPT": "0"}


class GitError(RuntimeError):
    pass


# The git programs `system_only()` trusts, in order: Homebrew, a local install, the system one, NixOS and Nix, and on
# Windows, Git for Windows. A candidate counts only when `<git> --version` succeeds (`_works`).
SYSTEM_GITS: tuple[str, ...] = (
    ("/opt/homebrew/bin/git", "/usr/local/bin/git", "/usr/bin/git", "/run/current-system/sw/bin/git", "/nix/var/nix/profiles/default/bin/git")
    if os.name != "nt"
    else (r"C:\Program Files\Git\cmd\git.exe", r"C:\Program Files\Git\bin\git.exe", r"C:\Program Files (x86)\Git\cmd\git.exe")
)
# The variables `system_only()` passes on from the session, with LC_* (see `_system_env`).
SYSTEM_ENV = ("HOME", "XDG_CONFIG_HOME", "LANG", "TMPDIR", "SYSTEMROOT", "WINDIR", "COMSPEC")
_SYSTEM_PATH = ("/usr/bin", "/bin", "/usr/sbin", "/sbin")
# Set on every call. The guard runs no hook and authenticates nowhere, so a reset credential helper costs it nothing,
# and fsmonitor off only costs speed.
_HARDENED = (("core.fsmonitor", "false"), ("core.hooksPath", os.devnull), ("protocol.ext.allow", "never"), ("credential.helper", ""))
# The config keys that name a program git runs while it reads a working tree or shows a diff.
_PROGRAM_KEY = re.compile(r"(?:filter|diff|merge)\.[^\n\0]+\.(?:clean|smudge|process|textconv|command|driver)")
# git's key grammar: a section of letters, digits, and `-`; an optional subsection of any byte but a newline or
# NUL; a variable that starts with a letter and holds letters, digits, and `-`.
_KEY = re.compile(r"[A-Za-z0-9-]+(?:\.[^\n\0]*)?\.[A-Za-z][A-Za-z0-9-]*")
_REPOSITORY_SCOPES = ("local", "worktree")
# The hook has 20 s. A `--version` check gets 4 s, and one retry of 10 s when it times out (a cold machine), within
# 14 s for every candidate together; the config read gets 4 s. That leaves 2 s for the guard's own git calls.
_VERSION_TIMEOUTS = (4.0, 10.0)
_VERSION_BUDGET = 14.0
_CONFIG_TIMEOUT = 4.0
_WORKS: dict[str, bool] = {}  # each candidate's `--version` answer, once a process
# Inside system_only: the overrides per git and folder (`_system_overrides`); None outside it.
_SYSTEM_ONLY: contextvars.ContextVar[dict[tuple[str, str], list[tuple[str, str]]] | None] = contextvars.ContextVar("aidd_system_git_only", default=None)


def _run_probe(argv: list[str], timeout: float) -> bool | None:
    """Whether a probe exits 0; None when it ran out of `timeout`."""
    try:
        return subprocess.run(argv, capture_output=True, stdin=subprocess.DEVNULL, env=_system_env(argv[0], None), timeout=timeout).returncode == 0
    except subprocess.TimeoutExpired:
        return None
    except (OSError, subprocess.SubprocessError):
        return False


def _works(path: str, deadline: float) -> bool:
    """Whether `path` is a git that runs: an executable file that answers `--version`, retried once when the first try
    times out (_VERSION_TIMEOUTS), and never past `deadline`. On macOS, /usr/bin/git counts only when `xcode-select -p`
    succeeds: without the Command Line Tools, that shim fails every call and opens an install dialog each time. A
    candidate that ran out of time is not cached, so a later call may try it again."""
    if path in _WORKS:
        return _WORKS[path]
    ok: bool | None = os.path.isfile(path) and os.access(path, os.X_OK)
    if ok and sys.platform == "darwin" and path == "/usr/bin/git":
        ok = _run_probe(["/usr/bin/xcode-select", "-p"], max(0.0, min(_VERSION_TIMEOUTS[0], deadline - time.monotonic())))
    if ok:
        for limit in _VERSION_TIMEOUTS:
            left = deadline - time.monotonic()
            if left <= 0:
                return False
            ok = _run_probe([path, "--version"], min(limit, left))
            if ok is not None:
                break
    if ok is None:
        return False
    _WORKS[path] = ok
    return ok


def system_git() -> str | None:
    """The first of SYSTEM_GITS that runs (`_works`), all checked within _VERSION_BUDGET; None when there is none."""
    deadline = time.monotonic() + _VERSION_BUDGET
    return next((p for p in SYSTEM_GITS if _works(p, deadline)), None)


@contextlib.contextmanager
def system_only() -> Iterator[None]:
    """Run every git call inside with a system git, an allowlisted environment, and config programs off (see the
    module docstring)."""
    token = _SYSTEM_ONLY.set({})
    try:
        yield
    finally:
        _SYSTEM_ONLY.reset(token)


def _system_env(git: str, env: dict[str, str] | None, overrides: Sequence[tuple[str, str]] = ()) -> dict[str, str]:
    """The environment of a git `system_only` runs: SYSTEM_ENV and LC_* from `env` (else the session's), a fixed PATH
    with `git`'s own folder, and then `overrides` as GIT_CONFIG_COUNT, GIT_CONFIG_KEY_<n>, and GIT_CONFIG_VALUE_<n>."""
    kept = {k: v for k, v in (os.environ if env is None else env).items() if k.upper() in SYSTEM_ENV or k.upper().startswith("LC_")}
    base = list(_SYSTEM_PATH) if os.name != "nt" else [os.path.join(kept[k], "System32") for k in kept if k.upper() == "SYSTEMROOT"]
    kept["PATH"] = os.pathsep.join([*base, os.path.dirname(git)])
    if overrides:
        kept["GIT_CONFIG_COUNT"] = str(len(overrides))
        for i, (k, v) in enumerate(overrides):
            kept[f"GIT_CONFIG_KEY_{i}"], kept[f"GIT_CONFIG_VALUE_{i}"] = k, v
    return kept


def _valid_key(key: str) -> bool:
    """Whether `key` follows git's key grammar (_KEY)."""
    return _KEY.fullmatch(key) is not None


def _repository_dirs(cwd: str) -> list[str]:
    """The working tree that holds `cwd` and its git folder, found by `.git` without running git; [] outside one."""
    d = os.path.realpath(cwd)
    while True:
        dot = os.path.join(d, ".git")
        if os.path.isdir(dot):
            return [d]
        if os.path.isfile(dot):
            try:
                with open(dot, encoding="utf-8") as f:
                    line = f.readline().strip()
            except OSError:
                return [d]
            gitdir = line.removeprefix("gitdir:").strip() if line.startswith("gitdir:") else ""
            return [d, os.path.realpath(os.path.join(d, gitdir))] if gitdir else [d]
        parent = os.path.dirname(d)
        if parent == d:
            return []
        d = parent


def _inside(path: str, dirs: list[str]) -> bool:
    return any(path == d or path.startswith(d.rstrip(os.sep) + os.sep) for d in dirs)


def _system_overrides(git: str, cwd: str, cache: dict[tuple[str, str], list[tuple[str, str]]]) -> list[tuple[str, str]]:
    """What `system_only` sets for a git in `cwd`: _HARDENED, and an empty value for each program key (_PROGRAM_KEY)
    that the repository's own config sets. That is a key of local or worktree scope (an include counts as the file that
    includes it), or one from a config file inside the working tree or its git folder (a HOME the project moved
    there). Reading config runs nothing. A repository key outside git's grammar, or a read that fails or takes longer
    than _CONFIG_TIMEOUT, raises GitError, so the guard denies instead of guessing."""
    cache_key = (git, os.path.realpath(cwd))
    if cache_key in cache:
        return cache[cache_key]
    argv = [git, "config", "--list", "--show-scope", "--show-origin", "--includes", "--null"]
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, stdin=subprocess.DEVNULL, env=_system_env(git, None, _HARDENED), timeout=_CONFIG_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise GitError(f"git config --list: timed out after {_CONFIG_TIMEOUT}s") from None
    except OSError as exc:
        raise GitError(f"git config --list: {exc}") from None
    tokens = _text(p.stdout).split("\0") if p.returncode == 0 else []
    if tokens and tokens[-1] == "":
        tokens.pop()
    if len(tokens) % 3:
        raise GitError("git config --list: its output does not split into scope, origin, and entry")
    dirs = _repository_dirs(cwd)
    programs: list[str] = []
    for scope, origin, entry in zip(tokens[::3], tokens[1::3], tokens[2::3], strict=True):
        key = entry.partition("\n")[0]
        source = origin.removeprefix("file:") if origin.startswith("file:") else None
        if source is not None and not os.path.isabs(source):
            source = os.path.join(dirs[0] if dirs else cwd, source)
        if scope not in _REPOSITORY_SCOPES and not (source and _inside(os.path.realpath(source), dirs)):
            continue
        if not _valid_key(key):
            raise GitError(f"git config: the repository's config holds a key that does not parse: {key!r}")
        if _PROGRAM_KEY.fullmatch(key):
            programs.append(key)
    cache[cache_key] = [*_HARDENED, *((k, "") for k in dict.fromkeys(programs))]
    return cache[cache_key]


def _shown(args: list[str]) -> str:
    return " ".join("<redacted>" if "extraheader" in a.lower() or "authorization" in a.lower() else a for a in args)


def _git(
    args: list[str], cwd: str = ".", *, env: dict[str, str] | None = None, timeout: float = DEFAULT_TIMEOUT, input: str | None = None
) -> subprocess.CompletedProcess[bytes]:
    argv = ["git", *args]
    cache = _SYSTEM_ONLY.get()
    if cache is not None:
        found = system_git()
        if found is None:
            raise GitError(f"git {_shown(args)}: no git that runs at {', '.join(SYSTEM_GITS)} (a git on PATH is not used here)")
        argv, env = [found, *args], _system_env(found, env, _system_overrides(found, cwd, cache))
    try:
        if input is not None:
            return subprocess.run(argv, cwd=cwd, capture_output=True, env=env, timeout=timeout, input=input.encode("utf-8"))
        return subprocess.run(argv, cwd=cwd, capture_output=True, env=env, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise GitError(f"git {_shown(args)}: timed out after {timeout}s") from None
    except OSError as exc:
        raise GitError(f"git {_shown(args)}: {exc}") from None


def _text(b: bytes | str | None) -> str:
    return b if isinstance(b, str) else (b or b"").decode("utf-8", errors="replace")


def run(
    args: list[str],
    cwd: str = ".",
    check: bool = True,
    env: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    input: str | None = None,
    *,
    raw: bool = False,
) -> str:
    """git's output as text, with universal newlines as text mode reads them; `raw` (and any `-z` command, whose NUL
    separated names may hold a carriage return) keeps it exactly as git wrote it."""
    p = _git(args, cwd, env=env, timeout=timeout, input=input)
    if check and p.returncode != 0:
        raise GitError(f"git {_shown(args)}: {_text(p.stderr).strip() or _text(p.stdout).strip()}")
    out = _text(p.stdout)
    if raw or "-z" in args:
        return out
    return out.replace("\r\n", "\n").replace("\r", "\n")


def fetch(cwd: str, refspecs: list[str], *, env: dict[str, str] | None = None, remote: str = "origin", timeout: float = DEFAULT_TIMEOUT) -> None:
    """`git fetch` from `remote`, abandoned when the transfer stalls. `env` adds to the process environment."""
    run(["fetch", "--no-tags", "--quiet", remote, *refspecs], cwd, env={**os.environ, **FETCH_ENV, **(env or {})}, timeout=timeout)


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


def ls_tree(ref: str, cwd: str = ".") -> dict[str, str]:
    out = run(["ls-tree", "-r", "-z", "--full-tree", ref], cwd)
    tree: dict[str, str] = {}
    for entry in out.split("\0"):
        if not entry:
            continue
        meta, path = entry.split("\t", 1)
        _mode, kind, oid = meta.split()
        if kind == "blob":
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
        if header[1] == b"commit":
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


def signature_kind(raw: bytes) -> str | None:
    """The kind of a raw commit's signature ("ssh", "openpgp", or "x509"), from its gpgsig header; None when unsigned."""
    for line in raw.partition(b"\n\n")[0].split(b"\n"):
        if line.startswith((b"gpgsig ", b"gpgsig-sha256 ")):
            armor = line.split(b" ", 1)[1]
            if armor.startswith(b"-----BEGIN SSH SIGNATURE"):
                return "ssh"
            return "openpgp" if armor.startswith(b"-----BEGIN PGP SIGNATURE") else "x509"
    return None


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


def hash_files(paths: list[str], cwd: str = ".") -> dict[str, str]:
    """Blob ids of working-tree files, identical to what git stores on commit.

    A symbolic link is stored as a blob of its target's name, never of the file it points to, so it is hashed that way
    here. The other paths go to git on stdin (`--stdin-paths`, which applies the same filters as a commit), so no list
    is too long for one command line; a name holding a newline, which stdin cannot carry, goes alone as an argument."""
    out: dict[str, str] = {}
    plain, odd = [], []
    for p in dict.fromkeys(paths):
        full = os.path.join(cwd, p)
        if os.path.islink(full):
            out[p] = _blob_id(os.fsencode(os.readlink(full)), cwd)
        elif "\n" in p or "\r" in p:
            odd.append(p)
        else:
            plain.append(p)
    if plain:
        ids = run(["hash-object", "--stdin-paths"], cwd, input="".join(f"{p}\n" for p in plain)).split()
        out.update(zip(plain, ids, strict=True))
    for p in odd:
        out[p] = run(["hash-object", "--", p], cwd).strip()
    return {p: out[p] for p in paths}


def _blob_id(data: bytes, cwd: str = ".") -> str:
    """The id git gives a blob of `data`, in the repository's object format (sha1 or sha256)."""
    import hashlib

    fmt = run(["rev-parse", "--show-object-format"], cwd, check=False).strip() or "sha1"
    return hashlib.new(fmt, b"blob %d\0" % len(data) + data).hexdigest()


def config_value(key: str, cwd: str = ".") -> str:
    return run(["config", "--get", key], cwd, check=False).strip()


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
