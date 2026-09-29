"""Thin wrappers over git. Every call reads objects; none runs code from the tree.

Every git process goes through `_git`, which bounds it with a timeout: a hung fetch or a pathological
repository ends the run with a GitError (which fails closed), never hangs it.
"""

from __future__ import annotations

import os
import subprocess

DEFAULT_TIMEOUT = 300
# A fetch that trickles below 1000 bytes/s for 60s is abandoned rather than holding the gate job open.
FETCH_ENV = {"GIT_HTTP_LOW_SPEED_LIMIT": "1000", "GIT_HTTP_LOW_SPEED_TIME": "60", "GIT_TERMINAL_PROMPT": "0"}


class GitError(RuntimeError):
    pass


def _shown(args: list[str]) -> str:
    return " ".join("<redacted>" if "extraheader" in a.lower() or "authorization" in a.lower() else a for a in args)


def _git(
    args: list[str], cwd: str = ".", *, env: dict[str, str] | None = None, timeout: float = DEFAULT_TIMEOUT, input: str | None = None
) -> subprocess.CompletedProcess[bytes]:
    try:
        if input is not None:
            return subprocess.run(["git", *args], cwd=cwd, capture_output=True, env=env, timeout=timeout, input=input.encode("utf-8"))
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, env=env, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise GitError(f"git {_shown(args)}: timed out after {timeout}s") from None
    except OSError as exc:
        raise GitError(f"git {_shown(args)}: {exc}") from None


def _text(b: bytes | str | None) -> str:
    return b if isinstance(b, str) else (b or b"").decode("utf-8", errors="replace")


def run(
    args: list[str], cwd: str = ".", check: bool = True, env: dict[str, str] | None = None, timeout: float = DEFAULT_TIMEOUT, input: str | None = None
) -> str:
    p = _git(args, cwd, env=env, timeout=timeout, input=input)
    if check and p.returncode != 0:
        raise GitError(f"git {_shown(args)}: {_text(p.stderr).strip() or _text(p.stdout).strip()}")
    return _text(p.stdout).replace("\r\n", "\n").replace("\r", "\n")  # universal newlines, as text mode reads them


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


def numstat(base: str, head: str, cwd: str = ".") -> list[dict]:
    out = run(["diff", "--numstat", "-z", "-M", base, head], cwd)
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


def commits(base: str, head: str, cwd: str = ".") -> list[dict]:
    out = run(["log", "--format=%H%x1f%ae%x1f%ce%x1f%P%x1f%B%x1e", f"{base}..{head}"], cwd)
    result = []
    for rec in out.split("\x1e"):
        rec = rec.strip("\n")
        if not rec:
            continue
        sha, ae, ce, parents, body = rec.split("\x1f", 4)
        result.append(
            {
                "sha": sha,
                "author": f"email:{ae}" if ae else None,
                "committer": f"email:{ce}" if ce else None,
                "message": body,
                "merge": len(parents.split()) > 1,
            }
        )
    return result


def hash_files(paths: list[str], cwd: str = ".") -> dict[str, str]:
    """Blob ids of working-tree files, identical to what git stores on commit."""
    if not paths:
        return {}
    out = run(["hash-object", "--", *paths], cwd)
    return dict(zip(paths, out.split(), strict=True))


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
