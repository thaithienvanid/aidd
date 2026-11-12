"""Thin wrappers over git. A read of aidd's runs none of the code a tree carries, under the threat model below; a write may.

Every git process goes through `_git`, which bounds it with a timeout: a hung fetch or a pathological
repository ends the run with a GitError, never hangs it. No call runs a shell: each is an argv list. The git on PATH
stays as given, because a CI runner or a person may install git elsewhere.

The threat model: `.git/` is the person's own. `git clone` never copies a repository's config, hooks, or `info/`
folder, so what a clone holds there, the person wrote. A repository received with its `.git` folder (an archive, a
shared drive) is untrusted to git itself, and aidd cannot make that safe: re-clone it. What aidd adds is a cheap net
under its own reads, for what a tree can carry without `.git/`: its `.gitattributes`, `.gitmodules`, and files.

The net, on every call whatever `env` its caller passes. Some of it needs a recent git: the empty-tree `--attr-source`
needs 2.40 (the git of older Xcode Command Line Tools is 2.39), and `GIT_NO_LAZY_FETCH` needs a git with the May 2024 fix for CVE-2024-32465. The environment drops `HANDLER_ENV` (an external diff, a
pager, an editor, ssh and askpass programs) and sets `GIT_NO_LAZY_FETCH`, so a read never fetches. The command line sets
`SAFE_CONFIG` (no fsmonitor, no hooks, no attributes file, no signature check on a log, no `ext` protocol, no
alternate-refs command, submodules ignored when dirty) and `--no-pager`. A diff, log, or show gets
`--no-ext-diff --no-textconv`, and it and `status` get `--ignore-submodules=dirty`, which beats a `submodule.<name>.ignore`.
A `status` also gets `--no-optional-locks`, so it writes no index and starts no post-index-change hook.
A call that stays on this machine also sets `LOCAL_CONFIG` (no ssh, proxy, askpass, or credential program).

`core.hooksPath` stops the hook files only. Git 2.54 and later also run a hook that config names (`hook.<name>.command` and
`hook.<name>.event`), such as one a tracked file brings in through `include.path`. Git has no switch for all of them: its
documented one is `hook.<name>.enabled=false` for each name (2.55 adds `hook.<event>.enabled`, for one event). So a call that
can start a hook (a write, a push, a fetch, or a status) lists the repository's own hook names and turns each off
(`_blank_pairs`). An earlier git ignores the keys.

A filter is a program that attributes choose, in `.gitattributes` or in `.git/info/attributes`. A read ignores the tree's
attributes (`--attr-source` an empty tree, git 2.40 and newer). A read that can run a filter (`FILTER_READS`) also blanks
each filter its config names (`filter.<name>.clean`, `smudge`, `process`); a read of refs, commits, or trees only
(`REF_READS`) runs no filter, so it skips that probe. The blanks go in the environment as `GIT_CONFIG_KEY_n` and `GIT_CONFIG_VALUE_n` (`_with_config`), never
`-c`, which splits a key at its first `=`, and a filter name may hold one. A read then compares files as stored, without
an `eol` or `text` conversion. When the filters cannot be listed, aidd says so once, on stderr.

A call that must reach a remote (`ls-remote`, `fetch`, `push`) passes `remote=True`. It keeps the person's environment
variables (`REMOTE_ENV`) and their repository's own ssh, credential, askpass, proxy, and pack settings, because those
are the person's setup, by design. It still gets `SAFE_CONFIG` and `protocol.file.allow=user`. Any fetch or push enters no
submodule (`--no-recurse-submodules`, `--recurse-submodules=no`). The release check, `ls_remote`, reads no repository.

What this does not cover, because the command needs the very thing that is the person's or the remote's:
- `checkout`, `worktree add`, and `stash create` run the repository's clean and smudge filters (`filter.<name>.*`),
  which the tree's attributes choose. aidd's callers run them on a tree the tests already run in.
- `commit-tree` signs with the repository's `gpg.program` when `commit.gpgsign` is set (only the records ref uses it).
- A remote call runs the repository's own `core.sshCommand`, credential helper, `core.askPass`, `core.gitProxy`,
  `remote.<name>.uploadpack` and `receivepack`, and `vcs`, and honors `http.sslVerify`.
- A push to a remote on a local path runs that remote's own hooks and config, such as `pre-receive` and
  `core.alternateRefsCommand`, because git strips `-c` for a local `receive-pack`. The blank `core.alternateRefsCommand`
  covers the fetching side only.
- A filter in the person's global or system config, such as git-lfs, still runs.
"""

from __future__ import annotations

import functools
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from aidd.kernel import git_reads
from aidd.kernel.git_calls import EMPTY_ATTRIBUTES_COMMANDS, FILTER_READS, kept_shape, may_write, starts_hooks, subcommand

DEFAULT_TIMEOUT_SECONDS = 300
# A fetch that trickles below 1000 bytes/s for 60s is abandoned rather than holding a CI job open.
FETCH_ENV = {"GIT_HTTP_LOW_SPEED_LIMIT": "1000", "GIT_HTTP_LOW_SPEED_TIME": "60", "GIT_TERMINAL_PROMPT": "0"}
# Variables that make git run a program, dropped from every call's environment; REMOTE_ENV is the part a remote call keeps.
REMOTE_ENV = frozenset({"GIT_SSH", "GIT_SSH_COMMAND", "GIT_PROXY_COMMAND", "GIT_ASKPASS", "SSH_ASKPASS"})
HANDLER_ENV = REMOTE_ENV | {"GIT_EXTERNAL_DIFF", "GIT_PAGER", "GIT_EDITOR", "GIT_SEQUENCE_EDITOR", "GIT_EXEC_PATH"}
# Settings given to every call, as `-c`: the repository's own fsmonitor and hooks, an attributes file it points to, the
# signature check a log would make (it runs gpg.program), the `ext` protocol, the alternate-refs command (a program run to
# advertise an alternate's refs), and submodules ignored when dirty (a submodule's own filters would run).
SAFE_CONFIG = (
    "core.fsmonitor=false",
    "core.hooksPath=/dev/null",
    "core.attributesFile=/dev/null",
    "log.showSignature=false",
    "protocol.ext.allow=never",
    "core.alternateRefsCommand=",
    "diff.ignoreSubmodules=dirty",
)
# Also given to a call that stays on this machine: no ssh, proxy, askpass, or credential program (empty values).
LOCAL_CONFIG = ("core.sshCommand=", "core.gitProxy=", "core.askPass=", "credential.helper=")
# Windows' environment holds only text, so a config name with a byte that is not UTF-8 cannot pass through it unchanged.
WINDOWS = os.name == "nt"
# Given to a call that fetches a public https URL: no other protocol is allowed. Each is named, because a repository's own
# `protocol.<name>.allow=always` would beat `protocol.allow=never`.
HTTPS_ONLY = (
    "-c",
    "protocol.allow=never",
    "-c",
    "protocol.https.allow=always",
    *(word for name in ("http", "ssh", "git", "file", "ext") for word in ("-c", f"protocol.{name}.allow=never")),
)
# The settings that choose where git looks for a repository, its config, or its objects: not the person's to pass to a call
# that must read no repository.
LOCATION_ENV = frozenset(
    {"GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_CONFIG", "GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS"}
)
_PERSON_SCOPES = ("system", "global")
# The options a subcommand gets, whoever calls it: a diff never runs an external diff or a textconv, and neither it nor
# status enters a submodule's work tree (a submodule's own filters would run; the option beats a `submodule.<name>.ignore`);
# a fetch and a push enter no submodule.
DIFFING = frozenset({"diff", "log", "show"})
SUBCOMMAND_OPTIONS = {
    **dict.fromkeys(DIFFING, ["--no-ext-diff", "--no-textconv", "--ignore-submodules=dirty"]),
    "status": ["--ignore-submodules=dirty"],
    "fetch": ["--no-recurse-submodules"],
    "push": ["--recurse-submodules=no"],
}
# The settings a remote call adds: a `file://` remote the repository names is the user's to open, never forced open.
REMOTE_CONFIG = ("protocol.file.allow=user",)
EMPTY_TREE = {"sha1": "4b825dc642cb6eb9a060e54bf8d69288fbee4904", "sha256": "6ef19b41225c5369f1c104d45d8d85efa9b057b53b14b4b9b939dd74decc5321"}


class GitError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitCall:
    """How one git process runs. `env` replaces the environment (default: this process's); `remote` is a call that
    reaches a remote (see the module's text)."""

    env: dict[str, str] | None = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    input: str | None = None
    remote: bool = False


def _shown(args: list[str]) -> str:
    return " ".join("<redacted>" if "extraheader" in a.lower() or "authorization" in a.lower() else a for a in args)


def _environment(call: GitCall) -> dict[str, str]:
    # Every object reads as written: a replace ref (`git replace`), which only this machine holds, never stands one
    # object in for another, such as a Spec or the base branch's config.
    # No read fetches a missing object (a partial clone's lazy fetch would reach a remote).
    # git's messages stay in English (LC_ALL=C), because aidd reads some of them, such as "couldn't find remote ref" or
    # "not a git repository", to name the next step. Paths come with `-z`, so the locale changes only the messages.
    dropped = HANDLER_ENV - REMOTE_ENV if call.remote else HANDLER_ENV
    kept = {k: v for k, v in (os.environ if call.env is None else call.env).items() if k not in dropped}
    return {**kept, "GIT_NO_REPLACE_OBJECTS": "1", "GIT_NO_LAZY_FETCH": "1", "LC_ALL": "C"}


_version_seen: list[tuple[int, int]] = []  # only a real answer is kept, and an unknown git reads as new, so every guard applies


def _version() -> tuple[int, int]:
    if not _version_seen:
        try:
            out = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=10, check=False).stdout
        except (OSError, subprocess.TimeoutExpired):
            return 99, 0
        _version_seen.extend((int(m.group(1)), int(m.group(2))) for m in [re.search(r"(\d+)\.(\d+)", out)] if m)
    return _version_seen[0] if _version_seen else (99, 0)


def _probe(args: list[str], folder: str) -> subprocess.CompletedProcess[str] | None:
    """A short read of the repository's own settings, with handlers off; None when git cannot run. A byte that is not
    UTF-8, such as a cp1252 path in a global `filter.lfs.*` value, decodes as a lone surrogate (`surrogateescape`), so
    it never stops a read, and on POSIX it goes back into the environment as the same byte."""
    argv = ["git", *(word for setting in SAFE_CONFIG for word in ("-c", setting)), *args]
    try:
        return subprocess.run(
            argv,
            cwd=folder,
            capture_output=True,
            encoding="utf-8",
            errors="surrogateescape",
            timeout=10,
            check=False,
            stdin=subprocess.DEVNULL,
            env=_environment(_LOCAL),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


@functools.lru_cache(maxsize=256)
def _empty_tree(folder: str) -> str | None:
    """The id of the empty tree in the repository at `folder`, for `--attr-source`; None when this git is older than 2.40."""
    if _version() < (2, 40):
        return None
    done = _probe(["rev-parse", "--show-object-format"], folder)
    return EMPTY_TREE.get(done.stdout.strip() if done else "", EMPTY_TREE["sha1"])  # a probe that failed still guards


_SAID: set[str] = set()


def _say_once(line: str) -> None:
    if line not in _SAID:
        _SAID.add(line)
        print(line, file=sys.stderr)


def _blank_pairs(folder: str, tree: str | None) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """(key, value) pairs that turn off what the repository's own config names, whichever file chooses it: each filter, so
    none runs on a read (`.gitattributes`, or `.git/info/attributes`), and each config-based hook, so none runs on a
    call that can start one. Git 2.54 and later run `hook.<name>.command` for `hook.<name>.event`, and `core.hooksPath` does
    not stop them; `hook.<name>.enabled=false` does, and an earlier git ignores the keys. The person's own scopes (system,
    global) are theirs. Read afresh for each call, as the config can change under a long-lived aidd, except inside
    `shared_reads`, which reads it once until a write. A name may hold an `=` or a space."""
    done = _probe(["config", "--includes", "--show-scope", "-z", "--get-regexp", r"^(filter|hook)\."], folder)
    if done is not None and done.returncode == 128 and "not a git repository" in done.stderr:
        return [], []  # no repository, so no config of one to run anything from
    if done is None or done.returncode not in (0, 1):
        _say_once(
            f"aidd: aidd could not list the filters and hooks in {folder}'s git config, so a filter that .git/info/attributes names may run when aidd reads it, and a config hook may run when aidd writes"
            + ("" if tree else ", and this git (older than 2.40) cannot ignore the tree's attributes. Update git to 2.40 or later")
            + ". To see why, run `git config --list` inside that folder."
        )
        return [], []
    names: dict[str, set[str]] = {"filter": set(), "hook": set()}
    tokens = done.stdout.split("\0")
    for scope, entry in zip(tokens[0::2], tokens[1::2], strict=False):
        key = entry.partition("\n")[0]
        kind = key.partition(".")[0]
        if scope not in _PERSON_SCOPES and key.count(".") >= 2 and kind in names:
            names[kind].add(key[len(kind) + 1 : key.rindex(".")])
    odd = {name for found in names.values() for name in found if any("\udc80" <= c <= "\udcff" for c in name)}  # a byte surrogateescape kept
    if odd:
        # No path joins the command: the folder is the repository's, so its name is the repository's text (kernel.command_names).
        find = "`git config --show-origin --get-regexp '^(filter|hook)\\.'`, run inside that folder,"
        if WINDOWS:
            # Windows' environment holds only text, so aidd can't pass the name back to git to turn the filter or hook off.
            # One aidd can't turn off could run on its calls, so it stops rather than go on (fail closed).
            raise GitError(
                f"a filter or hook name in {folder}'s git config holds a byte that is not UTF-8, and on Windows aidd can't turn "
                f"it off, so it runs nothing there. Rename it, then run aidd again: {find} finds it."
            )
        # On POSIX the byte goes back into the environment unchanged, so aidd turns it off as usual.
        _say_once(
            f"aidd: a filter or hook name in {folder}'s git config holds a byte that is not UTF-8; aidd turns it off on its "
            f"reads all the same, and on the calls that can start a hook. To rename it, {find} finds it."
        )
    filters = [
        (f"filter.{name}.{var}", "false" if var == "required" else "") for name in sorted(names["filter"]) for var in ("clean", "smudge", "process", "required")
    ]
    return filters, [(f"hook.{name}.enabled", "false") for name in sorted(names["hook"])]


def _with_config(env: dict[str, str], pairs: list[tuple[str, str]]) -> dict[str, str]:
    """`env` with `pairs` added as GIT_CONFIG_COUNT / GIT_CONFIG_KEY_n / GIT_CONFIG_VALUE_n, after any the person set, so a key
    and its value are never split at an `=`."""
    try:
        start = int(env.get("GIT_CONFIG_COUNT", "0"))
    except ValueError:
        start = 0
    out = dict(env)
    for i, (key, value) in enumerate(pairs, start):
        out[f"GIT_CONFIG_KEY_{i}"], out[f"GIT_CONFIG_VALUE_{i}"] = key, value
    out["GIT_CONFIG_COUNT"] = str(start + len(pairs))
    return out


def _command(args: list[str], cwd: str, remote: bool) -> list[str]:
    """The argv for `args` with git's handlers off (see the module's text)."""
    options = ["--no-pager"]
    for setting in SAFE_CONFIG + (REMOTE_CONFIG if remote else LOCAL_CONFIG):
        options += ["-c", setting]
    at, name = subcommand(args)
    if name == "status":
        options.append("--no-optional-locks")  # a status that refreshes the index writes it, and that starts post-index-change
    rest = list(args)
    rest[at + 1 : at + 1] = SUBCOMMAND_OPTIONS.get(name, [])
    if not remote and name in EMPTY_ATTRIBUTES_COMMANDS and (tree := _empty_tree(os.path.realpath(cwd))):
        options.append(f"--attr-source={tree}")
    return ["git", *options, *rest]


def _config_pairs(args: list[str], cwd: str, remote: bool) -> list[tuple[str, str]]:
    """The settings that go in the environment: a read that can run a filter blanks the filters its repository names, and a
    call that can start a hook turns off the config hooks it names."""
    filters, hooks = not remote and subcommand(args)[1] in FILTER_READS, starts_hooks(args)
    if not (filters or hooks):
        return []
    folder = os.path.realpath(cwd)
    shared = git_reads.current()
    if shared is None:
        found = _blank_pairs(folder, _empty_tree(folder))
    else:
        key = ("blanks", folder, git_reads.environment_key())
        if key not in shared:
            shared[key] = _blank_pairs(folder, _empty_tree(folder))
        found = shared[key]
    return (found[0] if filters else []) + (found[1] if hooks else [])


_LOCAL = GitCall()


def _git(args: list[str], cwd: str = ".", call: GitCall = _LOCAL) -> subprocess.CompletedProcess[bytes]:
    shared, key = git_reads.current(), None
    writes = shared is not None and may_write(args)
    if shared is not None and not writes and call.env is None and call.input is None and not call.remote and kept_shape(args):
        key = ("read", tuple(args), os.path.realpath(cwd), git_reads.environment_key())
        if key in shared:
            return shared[key]
    argv, env = _command(args, cwd, call.remote), _environment(call)
    if pairs := _config_pairs(args, cwd, call.remote):
        env = _with_config(env, pairs)
    try:
        if call.input is not None:
            done = subprocess.run(argv, cwd=cwd, capture_output=True, env=env, timeout=call.timeout_seconds, input=call.input.encode("utf-8"))
        else:
            done = subprocess.run(argv, cwd=cwd, capture_output=True, env=env, timeout=call.timeout_seconds, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise GitError(f"git {_shown(args)}: timed out after {call.timeout_seconds}s") from None
    except OSError as exc:
        raise GitError(f"git {_shown(args)}: {exc}") from None
    finally:
        if writes and shared is not None:
            shared.clear()  # a write may change the refs or the config that what was kept came from
    if shared is not None and key is not None:
        shared[key] = done
    return done


def neutral_env(folder: Path) -> dict[str, str]:
    """The environment for a git call that must read no repository: git stops looking for one at `folder`'s parent, so a
    repository around aidd's cache folder is never read, and the variables that point git at one (`LOCATION_ENV`) are gone."""
    return {
        **{k: v for k, v in os.environ.items() if k not in LOCATION_ENV and not k.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))},
        **FETCH_ENV,
        "GIT_CEILING_DIRECTORIES": str(folder.parent),
    }


def ls_remote(url: str, patterns: list[str], folder: Path, timeout_seconds: float) -> str:
    """`git ls-remote` of a public https `url`, run in `folder` (an empty folder of aidd's own, never the person's
    repository, whose config could steer it) as a local call: no ssh, askpass, or credential program. Only https is allowed."""
    args = ["ls-remote", url, *patterns]
    return run([*HTTPS_ONLY, *args], str(folder), env=neutral_env(folder), timeout_seconds=timeout_seconds)


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
    remote: bool = False,
) -> str:
    """git's output as text, with universal newlines as text mode reads them; `raw` (and any `-z` command, whose NUL
    separated names may hold a carriage return) keeps it exactly as git wrote it."""
    p = _git(args, cwd, GitCall(env, timeout_seconds, input, remote))
    if check and p.returncode != 0:
        raise GitError(f"git {_shown(args)}: {_text(p.stderr).strip() or _text(p.stdout).strip()}")
    out = _text(p.stdout)
    if raw or "-z" in args:
        return out
    return out.replace("\r\n", "\n").replace("\r", "\n")


def attempt(args: list[str], cwd: str = ".", env: dict[str, str] | None = None, *, remote: bool = False) -> tuple[int, str]:
    """git's exit code and its error output as text, for a call whose failure the caller reads, such as a fetch."""
    p = _git(args, cwd, GitCall(env, remote=remote))
    return p.returncode, _text(p.stderr).strip()


def rev_parse(ref: str, cwd: str = ".") -> str:
    return run(["rev-parse", "--verify", f"{ref}^{{commit}}"], cwd).strip()


def current_branch(cwd: str = ".") -> str:
    """The branch checked out, by its name under `refs/heads`, or "" for a detached HEAD. `symbolic-ref --short` would print
    `heads/main` for it when a tag is named `main`, and then no rule would know the branch."""
    return run(["symbolic-ref", "-q", "HEAD"], cwd, check=False).strip().removeprefix("refs/heads/")


def tracks_own_name(branch: str, upstream: str, cwd: str = ".") -> bool:
    """Whether `branch` tracks the branch of its own name on a configured remote: `branch.<branch>.merge` is
    `refs/heads/<branch>`, `branch.<branch>.remote` names a remote (never `.`, this repository), and `upstream`, the full
    name of its upstream, is exactly `refs/remotes/<remote>/<branch>` (a fetch refspec can map it elsewhere)."""
    remote = run(["config", "--get", f"branch.{branch}.remote"], cwd, check=False).strip()
    merge = run(["config", "--get", f"branch.{branch}.merge"], cwd, check=False).strip()
    known = remote not in ("", ".") and remote in run(["remote"], cwd, check=False).split()
    return known and merge == f"refs/heads/{branch}" and upstream == f"refs/remotes/{remote}/{branch}"


def full_ref_name(ref: str, cwd: str = ".") -> str | None:
    """The one full name git reads `ref` as (`refs/heads/main`, `refs/tags/main`), the way a merge resolves it. None when
    it names no ref, when git says two refs share the name (a tag `main` and the branch `main`), or when it starts with `-`."""
    if not ref or ref.startswith("-"):
        return None
    p = _git(["rev-parse", "--symbolic-full-name", ref], cwd)
    full = _text(p.stdout).strip()
    return full if p.returncode == 0 and full and "ambiguous" not in _text(p.stderr) else None


def ok(args: list[str], cwd: str = ".") -> bool:
    """Whether a git command succeeds; for yes/no questions such as merge-base --is-ancestor."""
    return _git(args, cwd).returncode == 0


def merge_base(left: str, right: str, cwd: str = ".") -> str:
    return run(["merge-base", left, right], cwd).strip()


def show_bytes(ref: str, path: str, cwd: str = ".") -> bytes | None:
    p = _git(["show", "--end-of-options", f"{ref}:{path}"], cwd)
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
    out = run(["diff", "--numstat", "-z", "-M", "--end-of-options", base, *([] if head is None else [head])], cwd)
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
    """`git log <args>` as one list of `fields` (placeholders such as %H, %ae, %aI) per commit, newest first.

    Only fixed fields, never a message: each is NUL-separated (-z), and none can hold a NUL, so no commit can add a
    record or a field of its own. The first field must be %H; output that does not split into whole records starting
    with a commit id raises GitError (which fails closed), since a misaligned record could name the wrong commit. A
    signature field (`%G?`, `%GS`) is refused, because git runs the repository's `gpg.program` to fill it, and aidd verifies
    no signature. A message comes from `messages`, which reads each by its length. `options` go before `log` (`-c key=value`)."""
    if not fields or fields[0] != "%H":
        raise ValueError("log_fields needs %H as its first field")
    if any(re.search(r"%[-+ ]?(?:G|\(signature)", field.replace("%%", "")) for field in fields):
        raise ValueError("log_fields reads no signature field: git would run the repository's gpg.program, and aidd verifies no signature")
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
    p = _git(["cat-file", "--batch"], cwd, GitCall(input="".join(f"{s}\n" for s in shas)))
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
    except (LookupError, UnicodeError):  # an unknown codec, or one such as idna that cannot replace
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


def aidd_dir(cwd: str = ".") -> Path:
    """aidd's folder in the clone's common git folder, `.git/aidd`, which every worktree shares: the records and the
    index live in it, and leave the machine only through `aidd records push`."""
    return Path(common_dir(cwd)) / "aidd"


def no_repository_problem(command: str | None = None) -> str:
    """What a command that works on a git repository says in a folder that no repository holds: why, and the next step."""
    what = f"`aidd {command}`" if command else "this command"
    return f"this folder is in no git repository, and {what} works on one: run it inside the repository, or run `git init` here first"


def is_no_repository(exc: BaseException) -> bool:
    """Whether a git error is git saying the folder is in no repository."""
    return isinstance(exc, GitError) and "not a git repository" in str(exc)


def repository_top(cwd: str = ".") -> str | None:
    """The repository's top-level directory, or None when git says `cwd` is in no repository. Any other failure, such as
    a repository git refuses for its owner (`safe.directory`), raises with git's own words, which name the cause."""
    p = _git(["rev-parse", "--show-toplevel"], cwd, GitCall())
    if p.returncode == 0:
        return _text(p.stdout).strip()
    err = _text(p.stderr).strip()
    if "not a git repository" in err:
        return None
    raise GitError(f"git rev-parse --show-toplevel: {err}")


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


def _trunk(cwd: str) -> tuple[str, str, str] | None:
    """The trunk the repository tells, as (the short ref to compare against, the branch's own name, its tip), else None: origin's default
    branch, `origin/main`, `origin/master`, `main`, `master`, then this repository's own `init.defaultBranch` (local scope only: a global one is a
    default for new repositories, never this one's trunk). The one reading behind `default_base` and `default_branches`, so they never differ."""
    head = run(["symbolic-ref", "-q", "refs/remotes/origin/HEAD"], cwd, check=False).strip()
    named = run(["config", "--local", "--get", "init.defaultBranch"], cwd, check=False).strip()
    guessed = ["refs/remotes/origin/main", "refs/remotes/origin/master", "refs/heads/main", "refs/heads/master"]
    for ref in ([head] if head.startswith("refs/remotes/") else []) + guessed + ([f"refs/remotes/origin/{named}", f"refs/heads/{named}"] if named else []):
        if tip := run(["rev-parse", "-q", "--verify", f"{ref}^{{commit}}"], cwd, check=False).strip():
            short = ref.removeprefix("refs/remotes/").removeprefix("refs/heads/")
            return short, short.split("/", 1)[1] if ref.startswith("refs/remotes/") else short, tip
    return None


def default_base(cwd: str = ".") -> str:
    """The base branch to compare against when --base is not given: the trunk (`_trunk`), unless this machine's branch of the same name
    holds all of it and more: work landed here and not yet published (the local trunk), which the next change builds on."""
    if (found := _trunk(cwd)) is None:
        raise GitError(
            "cannot find a base branch (tried origin/HEAD, origin/main, origin/master, main, master, and this repository's init.defaultBranch); "
            "pass --base <ref>, or name the trunk with `git remote set-head origin --auto` or `git config init.defaultBranch <branch>`"
        )
    return _local_trunk(found[0], found[2], cwd) or found[0]


def default_branches(cwd: str = ".") -> tuple[list[str], bool]:
    """The branch names a push to the default branch reaches, and whether the repository tells which one it is: it tells by `_trunk`, else,
    with nothing committed yet, by the branch checked out. Else it cannot tell, and every branch that could be the default counts, so each reading is
    the stricter one: the branch checked out, `init.defaultBranch` from any scope, `main`, `master`, then each local branch and each of origin's."""
    if found := _trunk(cwd):
        return [found[1]], True
    current = current_branch(cwd)
    refs = run(["for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes/origin"], cwd, check=False).split()
    if not any(r.startswith("refs/heads/") for r in refs):
        return [current or "main"], True
    names = [current, run(["config", "--get", "init.defaultBranch"], cwd, check=False).strip(), "main", "master"]
    names += [r.removeprefix("refs/heads/") for r in refs if r.startswith("refs/heads/")]
    names += [r.removeprefix("refs/remotes/origin/") for r in refs if r.startswith("refs/remotes/origin/") and r != "refs/remotes/origin/HEAD"]
    return list(dict.fromkeys(n for n in names if n)), False


def _local_trunk(ref: str, tip: str, cwd: str) -> str | None:
    """The local branch `ref` names (`origin/main` -> `main`) when it is strictly ahead of `ref`, whose commit is `tip`:
    it holds every commit of `ref`, and more. None when `ref` is local already, when there is no such branch, or when it
    is behind or apart."""
    remote, _, name = ref.partition("/")
    if not name or remote not in run(["remote"], cwd, check=False).split():
        return None
    local = run(["rev-parse", "-q", "--verify", f"refs/heads/{name}^{{commit}}"], cwd, check=False).strip()
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
