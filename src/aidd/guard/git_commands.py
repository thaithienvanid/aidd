"""The git and autopilot commands the guard denies: a push that rewrites or deletes a protected branch, a command
that lands work on the base branch, a change to commit signing, and starting or stopping another session's autopilot.
"""

from __future__ import annotations

import itertools
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from aidd.guard import shell_parser
from aidd.kernel import git

_PROTECTED_BRANCHES = {"main", "master", "trunk"}


# The options of `aidd autopilot` that take a value, and the spellings argparse takes for `--session` (a unique prefix).
_AUTOPILOT_VALUE_FLAGS = {"--work", "--session", "--timebox", "--goal", "--ask", "--spec", "--tokens", "--cost", "--currency", "--merged"}
_SESSION_FLAGS = frozenset("--session"[:n] for n in range(3, len("--session") + 1))  # `--s` is unique for `stop`
_RAW_AUTOPILOT = re.compile(r"\bautopilot\b[^\n;&|]*\b(?:start|stop)\b[^\n;&|]*--se", re.I)
AUTOPILOT_SESSION = (
    "the command starts or stops autopilot for another session ({named}), not this one. A lease bound to another session, "
    "such as the person's own, makes `delegate: auto` deny that session's edits. Start and stop autopilot only for this "
    "session, with the id the harness gives it ({variable})"
)
# The word a command names its session with, in each harness that gives one; any other event is Claude Code's.
_SESSION_VARIABLES = {"opencode": "`${AIDD_SESSION_ID}` in OpenCode"}


def _session_values(args: list[str]) -> list[str]:
    """Every value `args` give `--session` (or a prefix argparse takes for it), as `--session X` or `--session=X`."""
    found = []
    for i, a in enumerate(args):
        name, eq, value = a.partition("=")
        if name in _SESSION_FLAGS:
            found.append(value if eq else (args[i + 1] if i + 1 < len(args) else ""))
    return found


def autopilot_session_denial(command: str, event: dict) -> str | None:
    """Why `command` may not run: it starts or stops autopilot (`aidd autopilot start|stop`) with a `--session` that is
    not the hook event's own `session_id`, which the harness writes. An agent that read the person's session id from
    the git directory could otherwise bind the lease to the person's session. None when it does not."""
    own = event.get("session_id")
    own = own if isinstance(own, str) and own else None
    broken: list[str] = []
    named: list[str] = []
    for sc in shell_parser.simple_commands(command, broken=broken):
        for rest in shell_parser.aidd_runs(shell_parser.program_argv(sc.argv)):
            pos = shell_parser.positional_words(rest, _AUTOPILOT_VALUE_FLAGS | _SESSION_FLAGS)
            if pos[:1] == ["autopilot"] and pos[1:2] in (["start"], ["stop"]):
                named += [v for v in _session_values(rest) if v != own]
    if broken and _RAW_AUTOPILOT.search(command):
        named.append("a session the check cannot read")
    if not named:
        return None
    variable = _SESSION_VARIABLES.get(str(event.get("harness")), "`${CLAUDE_SESSION_ID}` in Claude Code")
    return AUTOPILOT_SESSION.format(
        named=", ".join(f"`{n}`" for n in dict.fromkeys(named)) + ("" if own else "; the hook event names no session"), variable=variable
    )


def push_denial(args: list[str], root: str | None) -> str | None:
    """Why a `git push` rewrites or deletes a protected branch, or None. `root` resolves a push with no refspec (the
    current branch) and adds the repository's default branch to the protected set."""
    rest = args[args.index("push") + 1 :]
    protected = set(_PROTECTED_BRANCHES)
    current = ""
    if root:
        try:
            protected.add(git.default_base(root).removeprefix("origin/"))
        except git.GitError:
            pass
        current = git.run(["symbolic-ref", "-q", "--short", "HEAD"], root, check=False).strip()

    def short(flag: str, letter: str) -> bool:
        return flag.startswith("-") and not flag.startswith("--") and letter in flag[1:]

    forced = any(a in ("--force", "--force-if-includes") or a.startswith("--force-with-lease") or short(a, "f") or a.startswith("+") for a in rest)
    deleting = any(a == "--delete" or short(a, "d") for a in rest)
    if "--mirror" in rest or (forced and "--all" in rest) or ("--prune" in rest and "--all" in rest):
        return "a mirror, or a push of every branch that rewrites or deletes: it reaches the protected branches"
    refspecs = shell_parser.positional_words(rest, {"-o", "--push-option", "--repo", "--receive-pack", "--exec"})[1:]
    targets: set[str] = set()
    deleted: set[str] = set()
    for r in refspecs:
        src, colon, dst = r.lstrip("+").rpartition(":")
        name = (dst if colon else r.lstrip("+")).removeprefix("refs/heads/")
        if name == "HEAD":
            name = current
        (deleted if (colon and not src) or deleting else targets).add(name)
        if r.startswith("+"):
            forced = True
    if not refspecs and forced and current:
        targets.add(current)  # no refspec: git pushes the current branch
    keys = {_branch_key(p) for p in protected}
    if hit := sorted(d for d in deleted if _branch_key(d) in keys):
        return f"deleting the protected branch {', '.join(hit)}: history on the default branch is never removed by an agent. Leave the branch, or ask a person"
    if forced and any(_branch_key(t) in keys for t in targets):
        return "a force push to a protected branch: history on the default branch is never rewritten by an agent. Push a new commit instead, or ask a person"
    return None


# git subcommands that put new commits on the checked-out branch, or move it.
_LANDS = {"merge", "commit", "cherry-pick", "revert", "am", "rebase", "reset", "pull"}
_RESET_MOVES = {"--hard", "--soft", "--mixed", "--keep", "--merge"}
_GIT_VALUE_FLAGS = {"-C", "-c", "--config-env", "--git-dir", "--work-tree", "--namespace"}
# git's options and variables that choose the repository, the index, or the config a command acts on, besides `-C`.
# The guard never hands them to its own git: its hardening of a repository's config is per folder. A command that sets
# one acts on a branch the guard cannot read, which counts as every branch (ANY).
_WHERE_FLAGS = ("-C", "--git-dir", "--work-tree", "--namespace")
_WHERE_ENV = frozenset({"GIT_DIR", "GIT_WORK_TREE", "GIT_NAMESPACE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY"})
ANY = "*"  # a move whose branches the guard cannot list: every branch may be one
_UNREADABLE = re.compile(r"[$`]|^~")  # a folder only the shell resolves
# A word the shell may turn into other words: an expansion, a glob, a brace (`{main,x}`, never `@{u}`), or a tilde.
# A brace counts without its `}`, so a word never costs more than one pass, and an unclosed one fails closed.
_SHELL_WORD = re.compile(r"[$`*?\[]|\{[^{}]*(?:,|\.\.)|^~")
_BRACES = re.compile(r"\{[^{}]*(?:,|\.\.)")


def _may_be_option(word: str) -> bool:
    """Whether the shell may turn `word` into an option: an expansion, a brace (`{-f,main}`), or a glob after a dash
    (`-[f]`, with a file named `-f`). A glob that starts a word aside, so `git branch --list 'feat*'` lists."""
    return bool(_UNREADABLE.search(word) or _BRACES.search(word) or (word.startswith("-") and re.search(r"[*?\[]", word)))


def _unread_branch_words(rest: list[str]) -> list[int]:
    """The words of a `git branch` the shell may turn into an option (_may_be_option), and a glob that starts a word
    (`*`, with a file named `-f`), unless `--list` or `-l` lists: git then refuses `-d`, `-m`, and `-c`, and `-f` moves
    nothing."""
    listing = any(_lists(a) and not (k and _takes_value(rest[k - 1])) for k, a in enumerate(rest))
    return [k for k, a in enumerate(rest) if _may_be_option(a) or (not listing and a[:1] in "*?[")]


# `git branch`'s options that take the next word as their value, which may itself read like `-l`: `--sort -l`.
_BRANCH_VALUE_LONGS: tuple[str, ...] = ("--sort", "--format", "--contains", "--no-contains", "--merged", "--no-merged", "--points-at")
_BRANCH_VALUE_LONGS += ("--set-upstream-to",)


def _lists(word: str) -> bool:
    """Whether a `git branch` word is `-l` or `--list`, by any prefix git takes."""
    return word == "-l" or (len(word) > 2 and "=" not in word and "--list".startswith(word))


def _takes_value(word: str) -> bool:
    """Whether a `git branch` word is an option that takes the next word as its value: `-u`, also at a cluster's end
    (`-vu`), or `--sort` and its kin by a prefix."""
    return bool(re.fullmatch(r"-[A-Za-z]*u", word)) or (
        word.startswith("--") and len(word) > 2 and "=" not in word and any(o.startswith(word) for o in _BRANCH_VALUE_LONGS)
    )


def _long_name(word: str, longs: tuple[str, ...]) -> str:
    """`word` with a long option of `longs` it names by a prefix git takes (`--force-cr`) spelled in full, value kept; a
    word that is another option in full (`--force`) stays as it is."""
    name, eq, value = word.partition("=")
    found = [o for o in longs if o.startswith(name) and len(name) > len("--force")] if name.startswith("--") else []
    return f"{found[0]}{eq}{value}" if len(found) == 1 else word


def _branch_key(name: str) -> str:
    """A branch name as git finds its ref on a case-insensitive disk: `refs/heads/` and repeated slashes gone, any case."""
    name = re.sub(r"/+", "/", name).strip("/")
    return (name[len("refs/heads/") :] if name.casefold().startswith("refs/heads/") else name).casefold()


@dataclass
class _Move:
    """One move of a local or remote branch: what does it (`git merge`), the branch, and, for a commit on it, the
    command's words, where it runs, and whether it is the first command of the line."""

    what: str
    branch: str
    rest: list[str] = field(default_factory=list)
    where: tuple[str, tuple[str, ...]] = ("", ())
    first: bool = False


def _where(sc_argv: list[str], argv: list[str], sub: int, cwd: Path | None) -> tuple[str, tuple[str, ...]]:
    """(the folder git runs in, the options and variables that choose another repository): `-C` folds into the folder;
    `--git-dir`, `--work-tree`, `--namespace`, _WHERE_ENV, and the `GIT_CONFIG*` variables stay as options, which the
    guard never runs.
    The folder is "" when only the shell can resolve it. `argv` is the git command, `sub` its subcommand's index."""
    opts: list[str] = []
    for word in sc_argv[: len(sc_argv) - len(argv)]:
        name, eq, _ = word.partition("=")
        if eq and _moves_repository(name):
            opts.append(word)
        elif word.startswith(("-C", "--chdir")):
            opts.append("env --chdir")  # `env -C dir git ...` runs git elsewhere: a folder the guard does not follow
    head = argv[1:sub]
    i = 0
    while i < len(head) and head[i].startswith("-"):
        flag, eq, value = head[i].partition("=")
        if flag in _WHERE_FLAGS:
            if not eq:
                value = head[i + 1] if i + 1 < len(head) else ""
                i += 1
            opts.append(f"{flag}={value}" if flag != "-C" else f"-C{value}")
        elif flag in _GIT_VALUE_FLAGS and not eq:
            i += 1
        i += 1
    cwd_s = str(cwd) if cwd is not None else ""
    for o in opts:  # git applies each -C in turn, before the others
        if o.startswith("-C") and cwd_s:
            cwd_s = "" if _UNREADABLE.search(o[2:]) else os.path.normpath(os.path.join(cwd_s, o[2:]))
    return cwd_s, tuple(o for o in opts if not o.startswith("-C"))


def _moves_repository(name: str) -> bool:
    """Whether an environment variable chooses the repository, the index, or the config git acts on."""
    return name in _WHERE_ENV or name.startswith("GIT_CONFIG")


def _exports_repository(argv: list[str]) -> bool:
    """Whether `export`, `declare -x`, or `set -a` may set a variable that moves git elsewhere for later commands."""
    if shell_parser.program_name(argv[0]) == "set":
        return any(a.startswith("-") and "a" in a[1:] for a in argv[1:])
    return any(_moves_repository(a.partition("=")[0]) for a in argv[1:] if not a.startswith("-"))


def _readable(where: tuple[str, tuple[str, ...]]) -> bool:
    """Whether the guard can read the repository a command acts on: a folder it knows, chosen by no other option."""
    cwd, opts = where
    return bool(cwd) and not opts and Path(cwd).is_dir()


def _head(where: tuple[str, tuple[str, ...]]) -> str:
    """The branch checked out where a command acts, "" when detached, ANY when the guard cannot read it."""
    return git.run(["symbolic-ref", "-q", "--short", "HEAD"], where[0], check=False).strip() if _readable(where) else ANY


def _exists(where: tuple[str, tuple[str, ...]], branch: str) -> bool:
    """Whether a local branch exists where a command acts; True when the guard cannot read it (fail closed)."""
    return not _readable(where) or git.ok(["rev-parse", "-q", "--verify", f"refs/heads/{branch}"], where[0])


def sub_index(argv: list[str]) -> int | None:
    """Where git's subcommand is in `argv` (`git -C x commit`: 3), past its options and their values; None for none."""
    i = 1
    while i < len(argv) and argv[i].startswith("-"):
        i += 2 if argv[i] in _GIT_VALUE_FLAGS else 1
    return i if i < len(argv) else None


def _refspec_targets(refspecs: list[str], current: str) -> set[str]:
    """The branches refspecs write: each one's destination (`src:dst`, or the name alone), `HEAD` as the current branch,
    and ANY for a pattern. A destination spelled exactly under `refs/remotes/` or `refs/tags/` is no branch, a pattern
    there included; any other spelling, an upper-case one among them, still counts."""
    out = set()
    for r in refspecs:
        _, colon, dst = r.lstrip("+").rpartition(":")
        if colon and dst.startswith(("refs/remotes/", "refs/tags/")) and "/../" not in dst:
            continue
        name = (dst if colon else r.lstrip("+")).removeprefix("refs/heads/")
        out.add(ANY if "*" in name else current if name == "HEAD" else name)
    return out


# Config that decides where a plain `git push` writes; a change to it counts as a move of any branch.
_PUSH_TARGET_KEY = re.compile(r"^(?:branch\..+\.(?:merge|remote|pushremote)|remote\..+\.(?:push|url|pushurl)|push\.default|remote\.pushdefault)$", re.I)


def _push_default(where: tuple[str, tuple[str, ...]], current: str) -> set[str]:
    """What a push with no refspec writes: the current branch, and the branch its config names as upstream (which
    `push.default` may push to); ANY when a remote's `push` refspecs decide, or the guard cannot read the config."""
    if not current:
        return set()
    if current == ANY or not _readable(where):
        return {ANY}
    if git.run(["config", "--get-regexp", r"^remote\..*\.push$"], where[0], check=False).strip():
        return {ANY}
    upstream = git.run(["config", "--get", f"branch.{current}.merge"], where[0], check=False).strip().removeprefix("refs/heads/")
    return {current, upstream} - {""}


def _branch_option(rest: list[str], letters: str, longs: tuple[str, ...], unread: bool = True) -> bool:
    """Whether a `git branch` holds one of the short options `letters`, alone or in a cluster (`-qf`; a `-u` in one
    takes the rest as its value), or a long option of `longs` by any prefix git takes (`--forc`), before a `--`; or,
    with `unread`, a word only the shell or the input fills in, which may be any of them."""
    unread_at = set(_unread_branch_words(rest)) if unread else set()
    for k, a in enumerate(rest):
        if a == "--":
            return False
        if k in unread_at:
            return True
        name = a.split("=", 1)[0]
        if a.startswith("--") and len(name) > 2 and any(long.startswith(name) for long in longs):
            return True
        if a.startswith("-") and not a.startswith("--") and set(a[1:].split("u", 1)[0]) & set(letters):
            return True
    return False


_BRANCH_ROLES = (None, "-f", "-m", "-M", "-d")  # what a word only the shell or the input fills in may be


def _branch_targets(rest: list[str], current: str) -> list[str]:
    """The branches a `git branch` moves, reading each word only the shell or the input fills in as a name and as each
    option that moves one (_BRANCH_ROLES). Such a word may also split into an option and a name (`B="-f main"; git
    branch $B feat`), so it adds ANY too; more such words than two read as ANY alone."""
    unread = _unread_branch_words(rest)
    if len(unread) > 2:
        return [ANY]
    found: list[str] = [ANY] if unread else []
    for roles in itertools.product(_BRANCH_ROLES, repeat=len(unread)):
        words = list(rest)
        for k, role in zip(unread, roles, strict=True):
            words[k] = role or words[k]
        found += _branch_reading(words, current)
    return list(dict.fromkeys(found))


def _branch_reading(rest: list[str], current: str) -> list[str]:
    """The branches one reading of a `git branch` moves: each one `-d` deletes or `-f` resets, and for `-m` (rename)
    or `-c` (copy), the branch it renames (the current one, when it names only the new name) and the new name. A new
    name only the shell names counts only with a force (`-M`, `-C`, `-f`): without one, git refuses to overwrite a
    branch, so it only creates one, as a plain `git branch <name>` does."""
    pos = shell_parser.positional_words(rest, {"-u"})
    if _branch_option(rest, "dD", ("--delete",), unread=False):
        return pos
    forced = _branch_option(rest, "fMC", ("--force",), unread=False)
    if not _branch_option(rest, "mMcC", ("--move", "--copy"), unread=False):
        return pos if forced else []
    moves = _branch_option(rest, "mM", ("--move",), unread=False)
    found = [pos[0] if len(pos) >= 2 else current] if moves else []
    if pos and (forced or not _SHELL_WORD.search(pos[-1])):
        found.append(pos[-1])
    return [b for b in found if b]


def _targets(sub: str, rest: list[str], pos: list[str], where: tuple[str, tuple[str, ...]], current: str) -> list[str]:
    """The branches one git command other than checkout and switch moves (branch_moves): ANY for those it cannot list."""
    found: list[str] = []
    if sub in _LANDS:
        if sub == "reset" and not (set(rest) & _RESET_MOVES) and (not pos or "--" in rest or (_readable(where) and (Path(where[0]) / pos[0]).exists())):
            return []  # unstaging paths moves no branch
        if sub == "rebase" and len(pos) >= 2:
            found.append(pos[1])  # `git rebase <upstream> <branch>` checks the branch out and rebases it
        elif current:
            found.append(current)
    elif sub in ("push", "fetch"):
        refspecs = shell_parser.positional_words(rest, {"-o", "--push-option", "--repo", "--receive-pack", "--exec", "--upload-pack", "--depth"})[1:]
        if sub == "push":
            found += sorted(_refspec_targets(refspecs, current) or _push_default(where, current))
            if {"--all", "--mirror", "--stdin"} & set(rest):
                found.append(ANY)
        else:  # a fetch writes a local branch only through a refspec that names one
            found += sorted(t for t in _refspec_targets([r for r in refspecs if ":" in r], current) if t)
            if "--stdin" in rest:
                found.append(ANY)
    elif sub == "branch" and _branch_option(rest, "fdDmMcC", ("--force", "--delete", "--move", "--copy")):
        found += _branch_targets(rest, current)
    elif (sub == "branch" and any(a in ("-u", "--set-upstream-to") or a.startswith("--set-upstream-to=") for a in rest)) or (
        sub == "config" and any(_PUSH_TARGET_KEY.match(a) for a in pos)
    ):
        found.append(ANY)  # where a later plain `git push` goes: any branch
    elif sub == "update-ref":
        found += [_branch_key(w) for w in pos if re.sub(r"/+", "/", w).casefold().startswith("refs/heads/")]
        if "--stdin" in rest:
            found.append(ANY)
    elif sub in ("filter-branch", "filter-repo"):
        found += _rewritten(sub, rest, current)
    elif sub == "worktree" and pos[:1] == ["add"]:
        resets = shell_parser.flag_value(rest, "-B", clusters=True)
        if resets and (_UNREADABLE.search(resets) or _exists(where, resets)):
            found.append(resets)
    return found


# filter-branch's options that take a value, and those that take none.
_FILTER_VALUES = {"--setup", "--subdirectory-filter", "--env-filter", "--tree-filter", "--index-filter", "--parent-filter", "--msg-filter"}
_FILTER_VALUES |= {"--commit-filter", "--tag-name-filter", "-d", "--original", "--state-branch"}
_FILTER_FLAGS = frozenset({"-f", "--force", "--prune-empty", "--"})


def _rewritten(sub: str, rest: list[str], current: str) -> list[str]:
    """The branches `git filter-branch` or `git filter-repo` rewrites: each name in the revisions they are given (the
    current branch when filter-branch names none), or ANY for a rev-list option (`--all`, `--branches`), or a
    filter-repo without `--refs`, which rewrites every ref."""
    if sub == "filter-repo":
        refs = list(itertools.takewhile(lambda w: not w.startswith("-"), rest[rest.index("--refs") + 1 :])) if "--refs" in rest else []
        return [n for r in refs for n in _rev_names(r)] or [ANY]
    if any(w.startswith("-") and w.split("=", 1)[0] not in _FILTER_VALUES | _FILTER_FLAGS for w in rest):
        return [ANY]
    names = [n for w in shell_parser.positional_words(rest, _FILTER_VALUES) for n in _rev_names(w)]
    return [current if n == "HEAD" else n for n in names] or ([current] if current else [])


def _rev_names(rev: str) -> list[str]:
    """The branch names a revision or a range names (`main~3..feat`: main and feat), without `^`, `~`, or `@{...}`."""
    return [n for part in re.split(r"\.{2,3}", rev) if (n := re.sub(r"[~^@].*$", "", part.lstrip("^")))]


def branch_moves(simple: list[shell_parser.SimpleCommand], root: str) -> list[_Move]:
    """Each branch the commands move, by any git command the guard reads: a commit or merge on the checked-out branch,
    a push, a fetch into a local branch, `branch -f/-D/-m`, `update-ref`, a reset of a branch with `checkout -B` or
    `worktree add -B`, and `rebase <upstream> <branch>`. It follows `cd`, `git -C`, `--git-dir`, `--work-tree`, and
    `git checkout`/`git switch` through the commands in order, so `cd ../wt && git merge x` is a merge on wt's branch."""
    dirs: list[tuple[Path | None, Path | None]] = [(Path(root), Path(root))]
    heads: dict[tuple[str, tuple[str, ...]], str] = {}
    moves: list[_Move] = []
    exported = False  # an earlier `export GIT_DIR=...` (or `set -a`): every later git acts where the guard cannot read
    for n, sc in enumerate(simple):
        dirs = (dirs + [dirs[-1]] * sc.depth)[: sc.depth + 1]
        argv = shell_parser.program_argv(sc.argv)
        if argv and shell_parser.program_name(argv[0]) in ("pushd", "popd"):
            dirs[-1] = (None, dirs[-1][0])  # a directory stack the guard does not keep
            continue
        if argv and shell_parser.program_name(argv[0]) in ("export", "declare", "typeset", "set") and _exports_repository(argv):
            exported = True
            continue
        if argv and shell_parser.program_name(argv[0]) == "cd":
            here, before = dirs[-1]
            shell_only = any(_UNREADABLE.search(a) for a in argv[1:])  # `cd "$DIR"`, `cd ~x`: only the shell resolves it
            dirs[-1] = (shell_parser.cd_target(here, before, argv[1:]) if here is not None and before is not None and not shell_only else None, here)
            continue
        if not argv or shell_parser.program_name(argv[0]) != "git":
            continue
        i = sub_index(argv)
        if i is None:
            continue
        sub, rest = argv[i], argv[i + 1 :]
        where = _where(sc.argv, argv, i, dirs[-1][0])
        if exported:
            where = (where[0], (*where[1], "exported"))
        if where not in heads:
            heads[where] = _head(where)
        current = heads[where]
        pos = shell_parser.positional_words(rest, {"-m", "-F", "-b", "-B", "-c", "-C", "--orphan", "-X", "-s", "--strategy", "--onto"})
        found: list[str] = []
        if sub in ("checkout", "switch"):
            rest = [_long_name(w, ("--create", "--force-create", "--orphan")) for w in rest]
            new = shell_parser.flag_value(rest, "-b", "-B", "-c", "-C", "--orphan", "--create", "--force-create", clusters=True)
            resets = shell_parser.flag_value(rest, "-B", "-C", "--force-create", clusters=True)
            if resets and (_UNREADABLE.search(resets) or _exists(where, resets)):
                found.append(resets)  # resets an existing branch to another commit
            if new:
                heads[where] = new
            elif "--detach" in rest or "-d" in rest:
                heads[where] = ""
            elif "--" not in rest and len(pos) == 1:
                heads[where] = pos[0]
        elif sub == "symbolic-ref" and len(pos) == 2 and pos[0] == "HEAD":
            heads[where] = pos[1].removeprefix("refs/heads/")
        else:
            found += _targets(sub, rest, pos, where, current)
        # A branch only the shell, or the input of xargs or find (indirect_runs), names may be any branch.
        moves += [_Move(sub, ANY if _SHELL_WORD.search(b) else b, rest, where, n == 0) for b in dict.fromkeys(found)]
    return moves


def base_branch_denial(simple: list[shell_parser.SimpleCommand], root: str) -> str | None:
    """Why a command lands an agent's work on the base branch, or moves it, or None (branch_moves). Not where agents
    publish to a platform's trunk (`publish: agents`), since the platform protects its own branch. Everywhere else the
    local base branch is the person's: the gate, the derived status, and the approvers read it while it is ahead."""
    from aidd import gate

    if gate.trunk_on_platform(root) and gate.agents_publish(root):
        return None
    protected = set(_PROTECTED_BRANCHES)
    try:
        protected.add(git.default_base(root).removeprefix("origin/"))
    except git.GitError:
        pass
    keys = {_branch_key(p) for p in protected}
    for m in branch_moves(simple, root):
        if _branch_key(m.branch) in keys or m.branch == ANY:
            branch = m.branch if m.branch != ANY else sorted(protected)[0]
            return (
                f"`git {m.what}` lands work on the base branch {branch}, or moves it, which is the person's step. Work "
                f"reaches {branch} only through `aidd land` (the person types `land it`, then you run it), or through its "
                "pull or merge request once the person types `publish`"
            )
    return None


GOAL_PREFIX = "goal/"
_GOAL_MOVES = (
    "a goal branch moves only through aidd: `aidd integrate` lands a Spec's branch once its approval holds and the gate "
    "passes against the goal, and `aidd sync` brings the default branch in. A commit of plan files alone (the "
    "Initiative, the Epics, and the Spec stubs directly in the Specs folder), as its own command, is the one direct "
    "commit allowed"
)


def _plan_only(m: _Move, root: str) -> bool:
    """Whether a `git commit`, the first command of its line and no amend, holds plan files alone: every path it would
    commit is a Markdown file directly in the Specs folder. With `-a`, named paths, or a pathspec file, the changed
    tracked files count too. A command before it could stage more, so a plan commit runs alone."""
    from aidd import workitems
    from aidd.guard import repo_config
    from aidd.kernel import globs

    if not m.first or not _readable(m.where) or any(a == "--amend" or a.startswith("--pathspec-from-file") for a in m.rest):
        return False
    cwd = m.where[0]
    cfg = repo_config.load_config(root)
    plan = workitems.plan_paths(cfg.specs_dir if cfg else "specs")
    staged = [p for p in git.run(["diff", "--cached", "--name-only", "-z"], cwd, check=False).split("\0") if p]
    every = any(a in ("-a", "--all") or (a.startswith("-") and not a.startswith("--") and "a" in a[1:] and a[1:].isalpha()) for a in m.rest)
    named = shell_parser.positional_words(m.rest, {"-m", "-F", "-C", "-c", "--author", "--date", "-t", "--template", "--fixup", "--squash"})
    if every or named:
        staged += [p for p in git.run(["diff", "--name-only", "-z"], cwd, check=False).split("\0") if p]
    return bool(staged) and all(globs.match_any(plan, p) for p in staged)


def goal_branch_denial(simple: list[shell_parser.SimpleCommand], root: str) -> str | None:
    """Why a command moves a goal branch (`goal/<name>`) by hand, or None. On every platform: a goal branch is the team's
    integration branch, which only `aidd integrate` and `aidd sync` move, so each Spec in it has its approval and its gate
    run behind it (branch_moves). A move the guard cannot list counts when the repository has a goal branch."""
    goals: list[str] | None = None
    for m in branch_moves(simple, root):
        branch = m.branch
        if branch == ANY:
            if goals is None:
                goals = git.run(["for-each-ref", "--format=%(refname:short)", f"refs/heads/{GOAL_PREFIX}"], root, check=False).split()
            if not goals:
                continue
            branch = goals[0]
        if not _branch_key(branch).startswith(GOAL_PREFIX):
            continue
        if m.what == "commit" and _plan_only(m, root):
            continue
        return f"`git {m.what}` moves the goal branch {branch} by hand: {_GOAL_MOVES}" + (
            ". `aidd integrate` pushes the goal branch when it has a remote" if m.what == "push" else ""
        )
    return None


EXPLORE_PREFIX = "explore/"
_EXPLORE_DENY = (
    "the guard holds no edit on an explore branch, so only a person starts one or switches to one: they type `explore "
    "branch <topic>` at the prompt, and aidd switches this worktree to {branch} (or they run `git switch -c {branch}` "
    "in their own terminal). Meanwhile, work inside the scope you have"
)


# A word that names an explore branch: as itself, as a ref (`refs/heads/explore/x`), through a remote (`origin/explore/x`),
# or inside a refspec, an option's value, or an alias's text (`HEAD:explore/x`, `--track=origin/explore/x`, `'switch explore/x'`).
_EXPLORE_WORD = re.compile(r"(?:^(?:-[A-Za-z]+)?|[\s/:=])" + re.escape(EXPLORE_PREFIX), re.I)  # `-bexplore/x`, `EXPLORE/x` too
# The git commands that only read a branch, or send it somewhere, and never check one out; `branch` and `checkout`
# are read below. Any other subcommand, an alias included, counts when one of its words names an explore branch.
_NEVER_CHECKS_OUT = frozenset(
    {"log", "show", "diff", "status", "rev-parse", "rev-list", "for-each-ref", "merge-base", "ls-tree", "ls-files", "cat-file", "blame", "grep"}
    | {"describe", "name-rev", "shortlog", "cherry", "range-diff", "format-patch", "fetch", "push", "archive", "bundle", "show-ref"}
)
# The ones that move HEAD, where a branch only the shell or git resolves may be an explore branch.
_MOVES_HEAD = frozenset({"checkout", "switch", "worktree", "symbolic-ref", "rebase", "stash"})
# git's own commands that never move HEAD by a branch name. A subcommand outside every list here is read as an alias,
# which may stand for any of them: a name only the shell or git resolves counts there too.
_TAKES_NO_BRANCH = frozenset(
    {"add", "commit", "merge", "cherry-pick", "revert", "reset", "restore", "rm", "mv", "pull", "clone", "init", "tag", "config"}
    | {"am", "apply", "clean", "gc", "bisect", "notes", "remote", "submodule", "sparse-checkout", "update-index", "hash-object"}
    | {"update-ref", "mktree", "commit-tree", "read-tree", "write-tree", "verify-commit", "verify-tag", "fsck", "prune", "repack"}
    | {"maintenance", "help", "version", "var", "check-ignore", "check-attr", "mailinfo", "send-email", "request-pull", "whatchanged"}
)


def _renames(rest: list[str]) -> bool:
    """Whether a `git branch` may rename or copy the checked-out branch: `-m`, `-M`, `-c`, `-C`, bundled with other short
    flags (`-fm`) too, `--move` and `--copy` by any prefix git takes (`--mov`), or a word only the input names."""
    return _branch_option(rest, "mMcC", ("--move", "--copy"))


def _explore_target(sub: str, rest: list[str]) -> str | None:
    """The word with which one git command could put a worktree on an explore branch, or None. Failing closed: every
    word of a command that may check a branch out counts, a remote's or a ref's prefix included. Reading files from one
    (`checkout <branch> -- <path>`), creating, listing, or deleting one with `branch`, and the commands that never check
    one out do not count. Only `checkout` reads the words after `--` as paths: `git switch -- explore/x` switches."""
    if sub in _NEVER_CHECKS_OUT:
        return None
    if sub == "branch" and not _renames(rest):
        return None
    if sub == "checkout" and "--" in rest and rest[rest.index("--") + 1 :]:
        return None  # restores files; HEAD stays where it is
    words = rest[: rest.index("--")] if "--" in rest and sub == "checkout" else [w for w in rest if w != "--"]
    if found := next((w for w in words if _EXPLORE_WORD.search(w)), None):
        return found
    if sub in _MOVES_HEAD or sub == "branch" or sub not in _TAKES_NO_BRANCH:
        # A name only the shell resolves (`$BRANCH`, `$(...)`, a glob or a brace), or only git (`-` and `@{-1}`, the
        # branch before). Only a stash's message (`stash push -m`) is no name: `checkout -m` and `switch -m` merge, and
        # take no value.
        names = [w for k, w in enumerate(words) if sub != "stash" or words[k - 1 : k] not in (["-m"], ["--message"])]
        return next((w for w in names if _SHELL_WORD.search(w) or w == "-" or "@{" in w), None)
    return None


# git's own commands the lists above name; any other subcommand is an alias, which git expands before it runs.
_KNOWN_COMMANDS = _NEVER_CHECKS_OUT | _MOVES_HEAD | _TAKES_NO_BRANCH | {"branch"}
# What a shell alias (`!...`) runs that may move HEAD, or read a name the guard cannot see.
_SHELL_ALIAS_MOVES = re.compile(r"\b(?:checkout|switch|worktree|symbolic-ref|rebase|stash)\b")


def one_off_alias(options: list[str]) -> bool:
    """Whether git's options before its subcommand define an alias for this run only (`-c alias.x=...`, `-calias...`,
    `--config-env alias.x=VAR`), which nothing reads before git expands it."""
    for k, o in enumerate(options):
        if o in ("-c", "--config-env"):
            value = options[k + 1] if k + 1 < len(options) else ""
        elif o.startswith("--config-env="):
            value = o.split("=", 1)[1]
        elif o.startswith("-c"):
            value = o[2:]
        else:
            continue
        if value.strip().lower().startswith("alias."):
            return True
    return False


def _alias_denial(words: list[str], argv: list[str], i: int, root: str) -> str | None:
    """Why a git command's alias could hide a checkout of an explore branch, or None. Failing closed: a one-off alias,
    an environment value that names one (a shell alias may read it), and an alias whose expansion could check one out."""
    if one_off_alias(argv[1:i]):
        return (
            "`git -c alias.<name>=...` defines a command for this run that the guard cannot read before git runs it. Run the git command it stands for instead"
        )
    env = [w.split("=", 1)[1] for w in words[: len(words) - len(argv)] if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", w)]
    if any(_EXPLORE_WORD.search(v) or v.startswith(EXPLORE_PREFIX) for v in env):
        return "an environment value names an explore branch, which a git alias or hook could check out: " + _EXPLORE_DENY.format(branch="explore/<topic>")
    sub = argv[i]
    if sub in _KNOWN_COMMANDS or sub.startswith("-"):
        return None
    expansion = git.run(["config", "--get", f"alias.{sub}"], root, check=False).strip()
    if not expansion:
        return None
    if expansion.startswith("!"):
        body = expansion[1:]
        if _EXPLORE_WORD.search(body) or _UNREADABLE.search(body) or _SHELL_ALIAS_MOVES.search(body):
            return f"`git {sub}` is a shell alias that could move HEAD to a branch the guard cannot read. Run the commands it stands for instead"
        return None
    parts = expansion.split()
    if parts and (word := _explore_target(parts[0], parts[1:] + argv[i + 1 :])):
        return f"`git {sub}` stands for `git {parts[0]}`, which names {word}, and could put a worktree on an explore branch: " + _EXPLORE_DENY.format(
            branch="explore/<topic>"
        )
    return None


def explore_branch_denial(simple: list[shell_parser.SimpleCommand], root: str) -> str | None:
    """Why a command could put a worktree on an explore branch, or None. The guard frees every edit there, so an agent
    that could switch to one would free its own edits; the gate still fails what comes from one (rule `explore`). Not
    where the config switches the Spec steps off: every edit is free there already."""
    from aidd import config
    from aidd.guard import repo_config

    cfg = repo_config.load_config(root)
    if cfg is not None and not config.component_on(cfg.raw, "spec_steps"):
        return None
    for sc in simple:
        argv = shell_parser.program_argv(sc.argv)
        name = shell_parser.program_name(argv[0]) if argv else ""
        if name in ("gh", "glab"):
            words = shell_parser.positional_words(argv[1:], {"-R", "--repo", "-b", "--branch"})
            local = shell_parser.flag_value(argv[1:], "-b", "--branch")
            if words[:2] in (["pr", "checkout"], ["mr", "checkout"]) and (not local or _EXPLORE_WORD.search(local) or _UNREADABLE.search(local)):
                return (
                    f"`{name} {' '.join(words[:2])}` checks out a branch the guard cannot accept: an explore branch frees every edit, so "
                    "only a person starts one. Name the local branch plainly: `--branch review/<number>`"
                )
            continue
        if name != "git" or (i := sub_index(argv)) is None:
            continue
        if why := _alias_denial(sc.argv, argv, i, root):
            return why
        if word := _explore_target(argv[i], argv[i + 1 :]):
            m = _EXPLORE_WORD.search(word)
            if m is None:
                return f"`git {argv[i]}` names the branch {word}, which only the shell or git resolves and may be an explore branch: name it plainly"
            branch = word[m.end() - len(EXPLORE_PREFIX) :]
            return f"`git {argv[i]}` could put a worktree on the explore branch {branch}: " + _EXPLORE_DENY.format(branch=branch)
    return None
