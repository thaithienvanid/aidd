"""What the guard reads before a git command writes a ref or the config: the decision records, where a person's decisions
are recorded, and the base branch's refspecs, under any name the shell or git resolves. A name the guard cannot read
(an expansion, a brace, a glob, a refspec set outside the command, a config include) counts as the decision records' ref,
failing closed. `tests/test_guard_ref_oracle.py` runs such commands with real git.
"""

from __future__ import annotations

import re

from aidd.guard import git_place, program_options, shell_parser
from aidd.guard.git_commands import sub_index
from aidd.guard.publish_commands import GH_VALUE_FLAGS
from aidd.kernel import git

# git commands that write a ref the command names. A name only the shell resolves, or refs read from stdin, may be the
# decision records' ref, where a person's decisions are recorded, so the guard never lets them through unread.
_REF_WRITERS = frozenset({"update-ref", "symbolic-ref"})
_REFSPEC_WRITERS = frozenset({"fetch", "push", "pull", "send-pack", "http-push"})
# A ref name the shell rewrites before git sees it: an expansion, a brace (`approval{s,}`), or a glob.
_SHELL_RESOLVED = re.compile(r"[$`{}\[\]*?]|^~")
# The namespaces a wildcard refspec may write into: everything else, `refs/*` among it, could reach aidd's own refs.
_GLOB_HOMES = ("refs/remotes/", "refs/heads/", "refs/tags/")
_REMOTE_REFSPEC_KEY = re.compile(r"^remote\..+\.(?:fetch|push)$", re.I)


def risky_destination(dest: str) -> bool:
    """Whether a refspec's destination may write aidd's own refs: under `refs/aidd/` (only aidd writes there), under
    `refs/replace/` (where a ref stands one object in for another, an approval among them), a short name git resolves
    there (`aidd/decisions` is `refs/aidd/decisions` once that ref exists), a wildcard outside the usual namespaces, or
    a name the shell rewrites."""
    d = re.sub(r"/{2,}", "/", dest.lstrip("+")).lower().lstrip("/")
    # A ref of the main worktree, or of another one, named from here: `main-worktree/refs/aidd/...` writes the shared one.
    d = re.sub(r"^(?:main-worktree|worktrees/[^/]+)/(?=refs/)", "", d)
    if re.match(r"(?:refs/)?(?:aidd|replace)(?:/|$)", d):
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
    config), refs fed on stdin (`--stdin`, `fast-import`), a mirror remote, `filter-branch` over every ref, and a
    subcommand only the shell names (`git "$S"`, or xargs input: indirect_runs). Each could write the decision records' ref
    under a name no reading of the text shows. And a `git config` that switches off
    signing or sets a risky refspec or include (`signing_config_denial`), found past every git option."""
    from aidd import workitems

    injected = any(_CONFIG_ENV.match(w) and not _NO_CONFIG_ENV.match(w) for sc in simple for w in sc.argv)
    changed_config = False
    for n, sc in enumerate(simple):
        argv = shell_parser.program_argv(sc.argv)
        if argv and shell_parser.program_name(argv[0]) in ("cd", "pushd", "popd"):
            changed_config = True  # git runs in another folder from here on, with that repository's config
            continue
        if not argv or shell_parser.program_name(argv[0]) != "git" or (i := sub_index(argv)) is None:
            changed_config = changed_config or _changes_git_config(sc, argv)
            continue
        sub, rest = argv[i], argv[i + 1 :]
        if _SHELL_RESOLVED.search(sub):
            return (
                f"`git {sub}`: only the shell, or the input of xargs or find, names this git subcommand, which could write "
                f"{workitems.DECISIONS_REF}, where a person's decisions are recorded. Run git with its subcommand named plainly"
            )
        if sub == "config" and (why := signing_config_denial(rest)):
            return why
        stdin = sub == "fast-import" or ("--stdin" in rest and sub in (_REF_WRITERS | _REFSPEC_WRITERS))
        unread = injected or _unread_ref_words(sub, rest)
        specs = _config_refspecs(argv[1:i]) + (_refspec_destinations(rest) if sub in _REFSPEC_WRITERS else [])
        if _uses_stored_refspecs(sub, rest):
            # The refspecs read here are not the ones git uses when an earlier command on the line changed the config or
            # the folder, or when this one runs in another repository, unless `git -C <absolute folder>` names it.
            there = git_place.absolute_c(simple, n, argv, i)
            specs += _stored_refspecs(there or root)
            unread = unread or changed_config or (there is None and _elsewhere(sc, argv, i))
        unread = unread or any(risky_destination(s.rsplit(":", 1)[-1]) for s in specs)
        # The ref `update-ref` or `symbolic-ref` writes, named plainly: under refs/aidd/ only aidd writes, as a refspec's.
        # `symbolic-ref <name> <target>` also points a name at its target, which a later write through the name moves.
        named = program_options.positional_words(rest, {"-m"})[: 2 if sub == "symbolic-ref" else 1] if sub in _REF_WRITERS else []
        unread = unread or any(risky_destination(w) for w in named)
        unread = unread or (sub == "remote" and rest[:1] == ["add"] and any(w.startswith("--mirror") for w in rest))
        every = sub == "filter-branch" and any(w in ("--all", "--glob") or w.startswith(("--glob=", "--branches", "--tags")) for w in rest)
        every = every or (sub == "filter-repo" and "--refs" not in rest)
        if why := _replace_denial(sub, rest) or _reflog_denial(sub, rest, argv[1:i]):
            return why
        changed_config = changed_config or _changes_git_config(sc, argv)
        if stdin or unread or every:
            return _unread_write_why(sub, stdin, every)
    return None


def _unread_write_why(sub: str, stdin: bool, every: bool) -> str:
    """The denial for a git command whose ref writes the guard cannot read: from stdin, every ref, or an unread name."""
    from aidd import workitems

    what = (
        "reads the refs it writes from stdin"
        if stdin
        else "rewrites every ref"
        if every
        else "writes a ref the guard cannot read (a name the shell rewrites, a wildcard, one under refs/aidd/ or refs/replace/, or a refspec set outside the command)"
    )
    return (
        f"`git {sub}` {what}, which could be {workitems.DECISIONS_REF}, where a person's decisions are recorded. Name each ref plainly, "
        "and keep each remote's refspecs under refs/remotes/<name>/. For another repository, run `git -C <its absolute folder>`, "
        "never after a `cd`"
    )


# `git config` options that take a value, and the ones that only read.
_CONFIG_VALUE_FLAGS = {"-f", "--file", "--blob", "--type", "--default", "--comment", "--value"}
_CONFIG_READS = {"--get", "--get-all", "--get-regexp", "--get-urlmatch", "--get-color", "--get-colorbool", "--list", "-l"}
# Every long option `git config` takes, which it also takes by any prefix that names one alone (`--rename-sec`).
_CONFIG_LONGS = (
    "--global", "--system", "--local", "--worktree", "--file", "--blob", "--get", "--get-all", "--get-regexp",
    "--get-urlmatch", "--replace-all", "--add", "--unset", "--unset-all", "--rename-section", "--remove-section", "--list",
    "--fixed-value", "--edit", "--get-color", "--get-colorbool", "--type", "--no-type", "--bool", "--int", "--bool-or-int",
    "--bool-or-str", "--path", "--expiry-date", "--null", "--name-only", "--show-origin", "--show-scope", "--includes",
    "--no-includes", "--default", "--comment", "--value", "--all", "--regexp", "--url", "--no-value", "--no-comment",
)  # fmt: skip


def _config_long(word: str) -> str | None:
    """A `git config` long option as git reads it: the one it names in full or by a prefix of one alone, or None when
    it names none or more than one, which the guard does not guess at."""
    name = word.split("=", 1)[0]
    if name in _CONFIG_LONGS:
        return name
    found = [o for o in _CONFIG_LONGS if o.startswith(name)]
    return found[0] if len(found) == 1 else None


def _signing_key(key: str) -> bool:
    """A config key (or section) that decides which key signs or which signatures git counts as good."""
    k = key.lower()
    return k in ("gpg", "user", "user.signingkey") or k.startswith("gpg.") or k in ("commit.gpgsign", "tag.gpgsign", "push.gpgsign")


# A config key that names a program git runs, or one it hands its output to, also when a person runs git: hooks, the
# file monitor, the pager and editors, ssh, credential helpers, diff and merge drivers, filters, aliases, config hooks,
# a submodule's update command, the transports a URL may name (`ext::` runs one), and URL rewrites into them.
_PROGRAM_KEY = re.compile(
    r"(?:core\.(?:hookspath|fsmonitor|sshcommand|pager|editor|askpass|gitproxy)|sequence\.editor|diff\.external"
    r"|interactive\.difffilter|uploadpack\.packobjectshook|web\.browser|credential\.(?:.+\.)?helper|pager\..+|alias\..+"
    r"|(?:diff|merge|filter|difftool|mergetool|browser|man)\..+\.(?:textconv|command|driver|clean|smudge|process|cmd|path)"
    r"|remote\..+\.(?:uploadpack|receivepack)|sendemail\..+|core\.alternaterefscommand|hook\..+|submodule\..+\.update"
    r"|protocol\.(?:.+\.)?allow|url\..+\.(?:insteadof|pushinsteadof)|trailer\..+\.(?:command|cmd)|imap\.tunnel"
    r"|gpg\.(?:.+\.)?program)",
    re.I,
)
# The sections that hold one: a section renamed into one brings its keys along.
_PROGRAM_SECTIONS = frozenset(
    {"core", "sequence", "diff", "merge", "filter", "difftool", "mergetool", "browser", "man", "credential", "pager", "alias"}
    | {"interactive", "uploadpack", "web", "sendemail", "remote", "hook", "submodule", "protocol", "url"}
    | {"trailer", "imap"}
)


def _program_key(key: str, renames: bool) -> bool:
    """Whether a config key names a program git runs (_PROGRAM_KEY), or, for a section rename, either name is in one of
    their sections. Removing the core section counts too, since it holds core.hooksPath."""
    k = key.lower()
    return bool(_PROGRAM_KEY.fullmatch(k)) or k == "core" or (renames and k.split(".", 1)[0] in _PROGRAM_SECTIONS)


def _config_keys(rest: list[str]) -> tuple[list[str], list[str]] | None:
    """The keys a `git config` command (its words after `config`) changes, and the values it sets; None when it only
    reads (`get`, `list`, `--get`, or a bare `git config <key>`)."""
    flags, pos, skip = [], [], False
    for k, a in enumerate(rest):
        if skip:
            skip = False
            continue
        if a == "--":
            pos += rest[k + 1 :]
            break
        if a.startswith("--"):
            if (name := _config_long(a)) is None:
                return ["gpg", "include.path"], []  # an option the guard cannot read may be any write
            flags.append(name)
            skip = name in _CONFIG_VALUE_FLAGS and "=" not in a
        elif a.startswith("-"):
            flags.append(a.split("=", 1)[0])
            skip = a in _CONFIG_VALUE_FLAGS
        else:
            pos.append(a)
    if (pos[:1] in (["get"], ["list"])) or _CONFIG_READS & set(flags):
        return None
    if {"-e", "--edit"} & set(flags) or pos[:1] == ["edit"]:
        return ["gpg", "include.path"], []  # the whole file: signing, includes, and every refspec
    if pos[:1] == ["rename-section"]:
        return pos[1:3], []  # both names: a section renamed into a signing or include key, or out of one
    if "--rename-section" in flags:
        return pos[:2], []
    if pos[:1] in (["set"], ["unset"], ["remove-section"]):
        return pos[1:2], pos[2:]
    if {"--unset", "--unset-all", "--remove-section", "--add", "--replace-all"} & set(flags) or len(pos) >= 2:
        return pos[:1], pos[1:]
    return None


def _config_writes(rest: list[str]) -> bool:
    """Whether a `git config` command writes the config."""
    return _config_keys(rest) is not None


def _replace_denial(sub: str, rest: list[str]) -> str | None:
    """Why a git command writes a replace ref (refs/replace/), or None: `git replace` beyond a list (no words, `-l`,
    `--list`, `--format`), or `update-ref` or `symbolic-ref` naming one."""
    from aidd import workitems

    lists = not rest or rest[0] in ("-l", "--list") or all(w.startswith("--format") for w in rest)
    named = sub in _REF_WRITERS and any(re.sub(r"/{2,}", "/", w).lower().lstrip("/").startswith("refs/replace/") for w in rest)
    if (sub == "replace" and not lists) or named:
        return (
            f"`git {sub}` writes a replace ref (refs/replace/), which makes git read one object as another, so a forged record "
            f"could stand in for a person's approval in {workitems.DECISIONS_REF}. Leave the objects as they are"
        )
    return None


_REFLOG_EXPIRY = re.compile(r"(?:gc\.(?:[^=]*\.)?reflogexpire|core\.logallrefupdates)", re.I)


def _reflog_denial(sub: str, rest: list[str], options: list[str]) -> str | None:
    """Why a git command drops entries from a branch's reflog, or None: `git reflog expire` or `delete`, or a run whose
    `-c` sets a reflog expiry (`gc.reflogExpire`, per ref too). The reflog keeps a Spec frozen after a squash."""
    words = program_options.positional_words(rest, set())
    drops = sub == "reflog" and words[:1] in (["expire"], ["delete"])
    drops = drops or any(_REFLOG_EXPIRY.search(w) for w in options)  # `-c <key>=`, and `--config-env=<key>=` too
    if drops:
        return (
            f"`git {sub}` drops entries from the reflog, git's record of where each branch has been, which keeps a Spec "
            "frozen after a squash while its approval stands. Leave the reflog to git's own expiry"
        )
    return None


# The `gh` and `glab` verbs under `alias`, `extension`, and `config` that only read, or run what a person installed.
_SETTINGS_READS = {"alias": {"list"}, "extension": {"list", "browse", "search", "exec"}, "config": {"get", "list"}}
_SETTINGS_GROUPS = {"alias": "alias", "extension": "extension", "extensions": "extension", "ext": "extension", "config": "config"}


# The options gh and glab take before their command that the guard reads; any other may take a value that shifts the
# words it reads (`gh --host h config set ...`).
_ROOT_OPTIONS = frozenset({"-R", "--repo", "-h", "--help", "--version"})
# The only assignments a line that runs gh or glab may hold: exact pairs agents need, which name no program.
_CLI_ENVIRONMENT = re.compile(
    r"(?:GH_PAGER|PAGER|GLAB_PAGER)=cat|(?:NO_COLOR|GH_PROMPT_DISABLED)=1|GH_REPO=[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+|GH_HOST=[A-Za-z0-9.-]+(?::[0-9]+)?"
)
_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\[.*\])?\+?=", re.S)
# Programs and loops that set a variable, or run code the guard does not read in this shell.
_SETS_VARIABLES = frozenset({"export", "declare", "typeset", "local", "readonly", "read", "mapfile", "readarray", "getopts", "let", "eval", "source", "."})
_SETS_VARIABLES |= {"for", "select", "while", "until", "coproc", "unset"}


def cli_environment_denial(simple: list[shell_parser.SimpleCommand]) -> str | None:
    """Why a line that runs `gh` or `glab` sets a variable, or None. gh and glab, and the git they run, read programs from
    many variables (an editor, a pager, a browser, `GIT_SSH_COMMAND`, `GIT_CONFIG_*`), which may run a command the guard
    cannot read. So one rule, failing closed: on such a line, every assignment, in a prefix or alone, and every program
    that sets one (`export`, `declare`, `read`, `printf -v`, `set -a`, a nameref, a loop) or runs code here (`eval`,
    `source`) is denied, except the exact pairs in _CLI_ENVIRONMENT. `simple` is the line read without its loops
    written out (shell_words.unrolled), so a loop is seen."""
    for sc in simple:
        argv = shell_parser.program_argv(sc.argv)
        lead = sc.argv[: len(sc.argv) - len(argv)]
        name = shell_parser.program_name(argv[0]) if argv else ""
        settable = (
            name in _SETS_VARIABLES
            or any(w in _SETS_VARIABLES for w in lead)
            or (name == "set" and any(a.startswith(("-", "+")) and "a" in a for a in argv[1:]))
        )
        settable = settable or (name == "printf" and any(a.startswith("-v") for a in argv[1:]))
        assigned = [w for w in lead if _ASSIGNMENT.match(w) and not _CLI_ENVIRONMENT.fullmatch(w)]
        if settable or assigned or any(re.search(r"\$\{[^}]*=", w) for w in sc.argv):
            what = f"`{assigned[0]}`" if assigned else f"`{name or sc.argv[0]}`"
            return f"{what} on a line that runs gh or glab: set environment variables in a separate command, or use gh's own flags (--repo, --hostname)"
    return None


def cli_settings_denial(name: str, args: list[str]) -> str | None:
    """Why a `gh` or `glab` command changes an alias, an extension, or the config, or None. An alias or an extension
    is a command the guard cannot read when it runs later (`gh alias set m 'pr merge'`, then `gh m 3`), and the config
    names the editor, the pager, and the browser gh runs, also when a person runs it. All are a person's settings, as
    git's aliases are, so only the verbs that read pass, read as an allowlist, and failing closed: an option before the
    command that the guard does not read, or a group word anywhere without a reading verb after it."""
    k = 0
    while k < len(args) and args[k].startswith("-"):
        if args[k].split("=", 1)[0] not in _ROOT_OPTIONS:
            return f"`{name} {args[k]}` comes before the command, where the guard reads only `-R`, `--repo`, and `--help`. Put the option after the command"
        k += 2 if args[k] in ("-R", "--repo") else 1
    words = program_options.positional_words(args, GH_VALUE_FLAGS)
    for at, word in enumerate(words[:-1]):
        group = _SETTINGS_GROUPS.get(word)
        if group is not None and words[at + 1] not in _SETTINGS_READS[group]:
            return (
                f"`{name} {word} {words[at + 1]}` changes a {name} {group} setting, which could run a command the guard cannot "
                f"read, also when a person runs {name}. Aliases, extensions, and the config are a person's settings: run the "
                f"{name} command you need by its own name, and ask the person to change the setting"
            )
    return None


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
    renames = "rename-section" in rest or any(a.startswith("--") and _config_long(a) == "--rename-section" for a in rest)
    if program := next((k for k in keys if _program_key(k, renames)), None):
        return (
            f"the command sets {program}, which names a program git runs, also when a person runs git, where it could act "
            "as them: a hook, a pager, an editor, a driver, a filter, a helper, or an alias. These are a person's settings, "
            "so leave them as they are, and run the program you need yourself"
        )
    if any(_REFLOG_EXPIRY.match(k) or k.lower() == "core.logallrefupdates" for k in keys):
        return (
            "the command changes how long git keeps the reflog, or whether it keeps one (gc.reflogExpire, "
            "core.logAllRefUpdates), and the reflog keeps a Spec frozen after a squash while its approval stands. Leave it as it is"
        )
    if any(_INCLUDE_KEY.match(k) or k.lower() == "include" or k.lower().startswith("includeif.") for k in keys):
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
