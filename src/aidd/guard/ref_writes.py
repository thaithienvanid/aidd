"""What the guard reads before a git command writes a ref or the config: the approvals ref, where a person's decisions
are recorded, and the base branch's refspecs, under any name the shell or git resolves. A name the guard cannot read
(an expansion, a brace, a glob, a refspec set outside the command, a config include) counts as the approvals ref,
failing closed. `tests/test_guard_ref_oracle.py` runs such commands with real git.
"""

from __future__ import annotations

import re

from aidd.guard import shell_parser
from aidd.guard.git_commands import sub_index
from aidd.kernel import git

# git commands that write a ref the command names. A name only the shell resolves, or refs read from stdin, may be the
# approvals ref, where a person's decisions are recorded, so the guard never lets them through unread.
_REF_WRITERS = frozenset({"update-ref", "symbolic-ref"})
_REFSPEC_WRITERS = frozenset({"fetch", "push", "pull", "send-pack", "http-push"})
# A ref name the shell rewrites before git sees it: an expansion, a brace (`approval{s,}`), or a glob.
_SHELL_RESOLVED = re.compile(r"[$`{}\[\]*?]|^~")
# The namespaces a wildcard refspec may write into: everything else, `refs/*` among it, could reach aidd's own refs.
_GLOB_HOMES = ("refs/remotes/", "refs/heads/", "refs/tags/")
_REMOTE_REFSPEC_KEY = re.compile(r"^remote\..+\.(?:fetch|push)$", re.I)


def risky_destination(dest: str) -> bool:
    """Whether a refspec's destination may write aidd's own refs: under `refs/aidd/` (only aidd writes there), or a
    short name git resolves there (`aidd/approvals` is `refs/aidd/approvals` once that ref exists), a wildcard outside
    the usual namespaces, or a name the shell rewrites."""
    d = re.sub(r"/{2,}", "/", dest.lstrip("+")).lower().lstrip("/")
    if re.match(r"(?:refs/)?aidd(?:/|$)", d):
        return True
    if "*" in d and not d.startswith(_GLOB_HOMES):
        return True
    return bool(re.search(r"[$`{}\[\]?]|^~", d))


def _refspec_destinations(words: list[str]) -> list[str]:
    """The destination of each refspec among `words` (`src:dst`), and of each `--refmap`."""
    out, refmap = [], False
    for w in words:
        if refmap:
            out.append(w.rsplit(":", 1)[-1])
            refmap = False
        elif w == "--refmap":
            refmap = True
        elif w.startswith("--refmap="):
            out.append(w.split("=", 1)[1].rsplit(":", 1)[-1])
        elif ":" in w and not w.startswith("-"):
            out.append(w.rsplit(":", 1)[1])
    return out


# A config include pulls in a file the guard never reads, which may set any refspec.
_INCLUDE_KEY = re.compile(r"^include(?:if\..+)?\.path$", re.I)


def _config_options(options: list[str]) -> list[tuple[str, str, bool]]:
    """Each (key, value, whether the value comes from the environment) that git's `-c` and `--config-env` options
    before its subcommand set for this run."""
    out = []
    for k, o in enumerate(options):
        if o in ("-c", "--config-env"):
            value = options[k + 1] if k + 1 < len(options) else ""
        elif o.startswith("--config-env="):
            value = o.split("=", 1)[1]
        elif o.startswith("-c") and o != "-c":
            value = o[2:]
        else:
            continue
        key, _, spec = value.partition("=")
        out.append((key.strip(), spec, o.startswith("--config-env")))
    return out


def _config_refspecs(options: list[str]) -> list[str]:
    """The refspecs `-c remote.<name>.fetch=...` or `.push=...` sets for this run; `$` for one the guard cannot read: a
    `--config-env` value, which comes from the environment, or a config include, which may set any."""
    out = []
    for key, spec, env in _config_options(options):
        if _INCLUDE_KEY.match(key):
            out.append("$")
        elif _REMOTE_REFSPEC_KEY.match(key):
            out.append("$" if env else spec)
    return out


# The variables that set git's config for one run, which a refspec (or a program git runs, such as core.fsmonitor)
# could hide in; any of them on a git line is unread. Only removing a source reads nothing new: GIT_CONFIG_GLOBAL or
# GIT_CONFIG_SYSTEM set to /dev/null, and GIT_CONFIG_NOSYSTEM.
_CONFIG_ENV = re.compile(r"^GIT_CONFIG[A-Z0-9_]*=")
_NO_CONFIG_ENV = re.compile(r"^(?:GIT_CONFIG_(?:GLOBAL|SYSTEM)=/dev/null|GIT_CONFIG_NOSYSTEM=[^$`]*)$")
# Commands that write with a remote's stored refspecs.
_STORED_REFSPEC_USERS = frozenset({"fetch", "pull", "push"})


def _stored_refspecs(root: str | None) -> list[str]:
    """Every remote's stored fetch and push refspec in the repository's config (`remote.<name>.fetch`, `.push`)."""
    if not root:
        return []
    out = git.run(["config", "--get-regexp", r"^remote\..*\.(fetch|push)$"], root, check=False)
    return [line.split(" ", 1)[1] for line in out.splitlines() if " " in line]


def _unread_ref_words(sub: str, rest: list[str]) -> bool:
    """Whether a ref writer's or a refspec taker's arguments hold a word the shell rewrites. A word with no colon in the
    text may get one from an expansion or a glob (`"HEAD${C}s"`, `HEAD?refs/...` matching a file named like a refspec),
    so any shell-resolved character counts. In a word with a colon, an expansion or a brace may add more refspecs; a
    glob there is judged in its destination (risky_destination)."""
    if sub not in (_REF_WRITERS | _REFSPEC_WRITERS):
        return False
    words = [w for w in rest if not w.startswith("-")]
    if sub in _REF_WRITERS:
        return any(_SHELL_RESOLVED.search(w) for w in words)
    return any(_SHELL_RESOLVED.search(w) if ":" not in w else re.search(r"[$`{}]", w) for w in words)


# Programs that change no file, so a line that runs them first still leaves git's config as the guard read it.
_READS_ONLY = frozenset({"echo", "printf", "cat", "ls", "pwd", "true", "false", "test", "[", "grep", "head", "tail", "wc", "which"})
# What moves git to another repository or another folder: the guard read the stored refspecs of this one only.
_ELSEWHERE_ENV = re.compile(r"^(?:GIT_DIR|GIT_WORK_TREE|GIT_COMMON_DIR|HOME|XDG_CONFIG_HOME)=")


def _changes_git_config(sc: shell_parser.SimpleCommand, argv: list[str]) -> bool:
    """Whether a simple command may change the config git reads, or the folder it runs in, failing closed: a redirect,
    any program outside a short read-only list (_READS_ONLY), `git config` beyond a read, and `git remote` beyond a list.
    `make` is never on the list: even `make -n` runs a recipe line marked `+` or holding `$(MAKE)`."""
    if sc.out or any(".git/" in w or w.endswith(".git") for w in sc.argv):
        return True
    if not argv:
        # A line's own assignment of HOME, XDG_CONFIG_HOME, a GIT_DIR, or a GIT_CONFIG variable reaches the git after it:
        # HOME is exported already, so the next git reads another global config.
        return any(_ELSEWHERE_ENV.match(w) or (_CONFIG_ENV.match(w) and not _NO_CONFIG_ENV.match(w)) for w in sc.argv)
    name = shell_parser.program_name(argv[0])
    if name != "git":
        return name not in _READS_ONLY
    if (i := sub_index(argv)) is None:
        return False
    sub, rest = argv[i], argv[i + 1 :]
    if sub == "config":
        return signing_config_denial(rest) is not None or _config_writes(rest)
    return sub == "remote" and rest[:1] not in ([], ["-v"], ["show"], ["get-url"])


def _elsewhere(sc: shell_parser.SimpleCommand, argv: list[str], i: int) -> bool:
    """Whether a git command runs in a repository other than the one the guard read: `-C`, `--git-dir`, `--work-tree`,
    a variable that moves it (`GIT_DIR`, or `HOME` and `XDG_CONFIG_HOME`, which choose its global config), or any option
    of a wrapper before it, which may change its folder (`env -C`, `sudo -D`)."""
    opts = argv[1:i]
    moved = any(o in ("-C", "--git-dir", "--work-tree") or o.startswith(("--git-dir=", "--work-tree=")) for o in opts)
    prefix = sc.argv[: len(sc.argv) - len(argv)]
    return moved or any(_ELSEWHERE_ENV.match(w) or w.startswith("-") for w in prefix)


def _uses_stored_refspecs(sub: str, rest: list[str]) -> bool:
    """Whether a command takes refspecs from the config: every fetch, pull, and push (a ref a fetch names, or one a
    push sends, also updates the remote-tracking ref the stored fetch refspec maps it to; a push with no refspec uses
    the stored push refspec), and `git remote update`."""
    if sub == "remote":
        return rest[:1] == ["update"]
    return sub in _STORED_REFSPEC_USERS


def unread_ref_write_denial(simple: list[shell_parser.SimpleCommand], root: str | None = None) -> str | None:
    """Why a git command writes a ref the guard cannot read, or None: `update-ref` or `symbolic-ref` naming a ref only
    the shell resolves (`$R`, `${R}s`, a backtick), a refspec whose destination is one or reaches refs/aidd/ (given on
    the command line, set for the run with `-c`, `--config-env`, or a `GIT_CONFIG_*` variable, or stored in a remote's
    config), refs fed on stdin (`--stdin`, `fast-import`), a mirror remote, and `filter-branch` over every ref. Each
    could write the approvals ref under a name no reading of the text shows. And a `git config` that switches off
    signing or sets a risky refspec or include (`signing_config_denial`), found past every git option."""
    from aidd import workitems

    injected = any(_CONFIG_ENV.match(w) and not _NO_CONFIG_ENV.match(w) for sc in simple for w in sc.argv)
    changed_config = False
    for sc in simple:
        argv = shell_parser.program_argv(sc.argv)
        if argv and shell_parser.program_name(argv[0]) in ("cd", "pushd", "popd"):
            changed_config = True  # git runs in another folder from here on, with that repository's config
            continue
        if not argv or shell_parser.program_name(argv[0]) != "git" or (i := sub_index(argv)) is None:
            changed_config = changed_config or _changes_git_config(sc, argv)
            continue
        sub, rest = argv[i], argv[i + 1 :]
        if sub == "config" and (why := signing_config_denial(rest)):
            return why
        stdin = sub == "fast-import" or ("--stdin" in rest and sub in (_REF_WRITERS | _REFSPEC_WRITERS))
        unread = injected or _unread_ref_words(sub, rest)
        specs = _config_refspecs(argv[1:i]) + (_refspec_destinations(rest) if sub in _REFSPEC_WRITERS else [])
        if _uses_stored_refspecs(sub, rest):
            specs += _stored_refspecs(root)
            # The refspecs read here are not the ones git uses when an earlier command on the line changed the config or
            # the folder, or when this one runs in another repository.
            unread = unread or changed_config or _elsewhere(sc, argv, i)
        unread = unread or any(risky_destination(s.rsplit(":", 1)[-1]) for s in specs)
        unread = unread or (sub == "remote" and rest[:1] == ["add"] and any(w.startswith("--mirror") for w in rest))
        every = sub == "filter-branch" and any(w in ("--all", "--glob") or w.startswith(("--glob=", "--branches", "--tags")) for w in rest)
        changed_config = changed_config or _changes_git_config(sc, argv)
        if stdin or unread or every:
            what = (
                "reads the refs it writes from stdin"
                if stdin
                else "rewrites every ref"
                if every
                else "writes a ref the guard cannot read (a name the shell rewrites, a wildcard, one under refs/aidd/, or a refspec set outside the command)"
            )
            return (
                f"`git {sub}` {what}, which could be {workitems.APPROVALS_REF}, where a person's decisions are recorded. Name each ref plainly, "
                "and keep each remote's refspecs under refs/remotes/<name>/"
            )
    return None


# `git config` options that take a value, and the ones that only read.
_CONFIG_VALUE_FLAGS = {"-f", "--file", "--blob", "--type", "--default", "--comment", "--value"}
_CONFIG_READS = {"--get", "--get-all", "--get-regexp", "--get-urlmatch", "--get-color", "--get-colorbool", "--list", "-l"}


def _signing_key(key: str) -> bool:
    """A config key (or section) that decides which key signs or which signatures git counts as good."""
    k = key.lower()
    return k in ("gpg", "user", "user.signingkey") or k.startswith("gpg.")


def _config_keys(rest: list[str]) -> tuple[list[str], list[str]] | None:
    """The keys a `git config` command (its words after `config`) changes, and the values it sets; None when it only
    reads (`get`, `list`, `--get`, or a bare `git config <key>`)."""
    flags, pos, skip = [], [], False
    for a in rest:
        if skip:
            skip = False
            continue
        if a.startswith("-"):
            flags.append(a.split("=", 1)[0])
            skip = a in _CONFIG_VALUE_FLAGS
        else:
            pos.append(a)
    if (pos[:1] in (["get"], ["list"])) or _CONFIG_READS & set(flags):
        return None
    if {"-e", "--edit"} & set(flags) or pos[:1] == ["edit"]:
        return ["gpg", "include.path"], []  # the whole file: signing, includes, and every refspec
    if pos[:1] in (["set"], ["unset"], ["rename-section"], ["remove-section"]):
        return pos[1:2], pos[2:]
    if {"--unset", "--unset-all", "--remove-section", "--rename-section", "--add", "--replace-all"} & set(flags) or len(pos) >= 2:
        return pos[:1], pos[1:]
    return None


def _config_writes(rest: list[str]) -> bool:
    """Whether a `git config` command writes the config."""
    return _config_keys(rest) is not None


def signing_config_denial(rest: list[str]) -> str | None:
    """Why a `git config` command (its words after `config`) changes commit signing, a config include, or a remote's
    refspec into aidd's refs; None when it only reads or changes another key. An agent that points `gpg.ssh.program`
    at a script, or `gpg.ssh.allowedSignersFile` at its own list, would make this machine call any signature good. An
    include pulls in a file the guard never reads, which may set any refspec."""
    found = _config_keys(rest)
    if found is None:
        return None
    keys, values = found
    if any(_signing_key(k) for k in keys):
        return (
            "the command changes commit signing in git's config (gpg.*, user.signingkey). Which key signs, and which signatures "
            "count as good, are a person's settings: an agent never changes them"
        )
    if any(_INCLUDE_KEY.match(k) for k in keys):
        return (
            "the command sets a config include (include.path, includeIf), which pulls in a file the guard never reads and "
            "may set where git writes refs. Set the keys you need in the config itself"
        )
    if any(_REMOTE_REFSPEC_KEY.match(k) for k in keys) and any(risky_destination(v.rsplit(":", 1)[-1]) for v in values):
        return (
            "the command sets a remote's refspec that writes under refs/aidd/, where a person's decisions are recorded, or a "
            "wildcard outside refs/heads/, refs/remotes/, and refs/tags/. Map a remote into refs/remotes/<name>/ instead"
        )
    return None
