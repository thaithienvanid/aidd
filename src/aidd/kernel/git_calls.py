"""What kind of call a git argv is, from its words alone: a read of refs, a read that can run a filter, a call that may
write, and a call that can start a hook. `aidd.kernel.git` decides from these what to turn off and what `shared_reads` keeps.
Each answer errs toward the stricter kind: an unknown shape may write and may start a hook."""

from __future__ import annotations

# The reads that can run a filter, because they read a file of the work tree or the index, or apply its attributes to
# a blob: each blanks the filters its repository names.
FILTER_READS = frozenset({"status", "diff", "log", "show", "grep", "ls-files", "cat-file", "hash-object"})
# The reads of refs, commits, and trees only, which run no filter in any form, so they skip the filter probe's process.
REF_READS = frozenset({"ls-tree", "rev-parse", "symbolic-ref", "for-each-ref", "merge-base"})
# The commands that only read, and so may ignore the tree's attributes; the others (checkout, worktree add) need them.
READ_COMMANDS = FILTER_READS | REF_READS
# The subcommands that start no hook in any form, whatever their arguments. `remote` (`update` fetches, `prune` deletes
# refs) and `config` (a write changes what a later call reads) are not: only their exact read shapes are (`reads_only`).
HOOK_FREE = frozenset({"rev-list", "ls-remote"})
_CONFIG_SCOPES = frozenset({"--local", "--global", "--system"})
_CONFIG_READS = frozenset({"--get", "--get-all", "--get-regexp"})


def subcommand(args: list[str]) -> tuple[int, str]:
    """Where the subcommand is in `args`, and its name, past git's own options and the value each takes as the next word
    (`-c key=value`, `-C path`, `--git-dir path`, `--work-tree path`, `--namespace name`, `--config-env key=name`)."""
    i = 0
    while i < len(args):
        if args[i] in ("-c", "-C", "--git-dir", "--work-tree", "--namespace", "--config-env"):
            i += 2
        elif args[i].startswith("-"):
            i += 1
        else:
            return i, args[i]
    return len(args), ""


def kept_shape(args: list[str]) -> bool:
    """Whether `args` is one of the exact reads whose answer `shared_reads` keeps: a ref read, `symbolic-ref -q --short
    <ref>` or `-q HEAD`, `config [--local|--global|--system] --get <name>`, or a bare `git remote` (`-v` too). Any other
    shape, such as `symbolic-ref -qd <ref>` or `config <name> --get`, may write, so it is never kept."""
    at, name = subcommand(args)
    rest = args[at + 1 :]
    if name == "symbolic-ref":
        return (rest[:2] == ["-q", "--short"] and len(rest) == 3 and not rest[2].startswith("-")) or rest == ["-q", "HEAD"]
    if name == "config":
        words = rest[1:] if rest[:1] and rest[0] in _CONFIG_SCOPES else rest
        return len(words) == 2 and words[0] == "--get" and not words[1].startswith("-")
    if name == "remote":
        return rest in ([], ["-v"], ["--verbose"])
    return name in REF_READS


def may_write(args: list[str]) -> bool:
    """Whether a call may change the refs, the index, the work tree, or the config: it is no read of aidd's
    (`READ_COMMANDS`, except a `symbolic-ref` that sets or deletes) and no kept shape."""
    name = subcommand(args)[1]
    return bool(name) and not (kept_shape(args) or name in READ_COMMANDS - {"symbolic-ref"})


def reads_only(name: str, rest: list[str]) -> bool:
    """Whether `git remote` or `git config` with these arguments is one of the exact shapes that only read: a bare
    `remote`, `remote -v`, `remote get-url [--push|--all] <name>`, `config [--local|--global|--system] --list`, `--get`,
    `--get-all`, or `--get-regexp` with one name, or `config <name>` alone."""
    if name == "remote":
        return rest in ([], ["-v"], ["--verbose"]) or (
            len(rest) >= 2 and rest[0] == "get-url" and not rest[-1].startswith("-") and set(rest[1:-1]) <= {"--push", "--all"}
        )
    words = rest[1:] if rest[:1] and rest[0] in _CONFIG_SCOPES else rest
    if len(words) == 1:
        return words[0] in ("--list", "-l") or not words[0].startswith("-")
    return len(words) == 2 and words[0] in _CONFIG_READS and not words[1].startswith("-")


_BRANCH_READS = frozenset({"-a", "--all", "-r", "--remotes", "-v", "-vv", "--verbose", "-l", "--list", "--show-current"})


# The calls that can't create or move a ref other than the checked-out branch's own tip, or change an upstream: reads, and
# the writes that only move the current branch. Every other subcommand, an alias included, counts as moving refs.
_STILL_REFS = frozenset(
    {
        "add",
        "blame",
        "cat-file",
        "check-attr",
        "check-ignore",
        "cherry-pick",
        "commit",
        "describe",
        "diff",
        "for-each-ref",
        "grep",
        "hash-object",
        "log",
        "ls-files",
        "ls-remote",
        "ls-tree",
        "merge",
        "merge-base",
        "mv",
        "name-rev",
        "restore",
        "rev-list",
        "rev-parse",
        "revert",
        "rm",
        "shortlog",
        "show",
        "show-ref",
        "stash",
        "status",
        "version",
    }
)
_NEW_BRANCH_FLAGS = ("-b", "-B", "-c", "-C", "--orphan", "--force-create", "--create")


def sets_config(args: list[str]) -> bool:
    """Whether a call sets git's config for itself, with `-c` or `--config-env` before its subcommand: it can then rename
    a branch's upstream, a remote's refs, or a command, so the names it reads are not the ones the repository holds."""
    at, _ = subcommand(args)
    return "-c" in args[:at] or any(a.startswith("--config-env") for a in args[:at])


_NO_TAGS_WORDS = frozenset({"--no-tags", "-q", "--quiet", "-v", "--prune", "--ff-only", "--rebase", "--no-rebase"})


def _fetches_no_tags(name: str, rest: list[str]) -> bool:
    """Whether a `fetch` or `pull` brings no tag and makes no ref of its own name: `--no-tags` and, besides it, only the
    options in `_NO_TAGS_WORDS` and at most one remote name (a `pull` also its branch). Anything else, such as `-t`, a
    `--tags` before or after it (git takes the last), an abbreviated `--ta`, `tag <name>`, a refspec, or an unknown option,
    counts as bringing tags."""
    words = [w for w in rest if w not in _NO_TAGS_WORDS]
    return "--no-tags" in rest and not any(w.startswith("-") or ":" in w or w == "tag" for w in words) and len(words) <= (2 if name == "pull" else 1)


def moves_refs(args: list[str]) -> bool:
    """Whether a call might create or move a ref, or change an upstream or a remote, so a name read after it may not be the
    name it was before. It fails closed: a `-c` option before the subcommand, an alias, or any subcommand outside a short
    list of known shapes counts as moving. A `fetch` or `pull` follows the tags of what it brings, so `origin/main` can name a
    tag it just made: both move refs, unless they pass `--no-tags` and nothing but the few words `_fetches_no_tags` lists."""
    at, name = subcommand(args)
    if sets_config(args):
        return True
    rest = args[at + 1 :]
    if name == "tag":
        return bool(rest) and rest[0] not in ("-l", "--list")
    if name == "branch":
        return not set(rest) <= _BRANCH_READS
    if name == "config":
        return not reads_only(name, rest) and any(w.lower().startswith(("branch.", "remote.", "alias.")) for w in rest)
    if name == "remote":
        return not reads_only(name, rest)
    if name in ("fetch", "pull"):
        return not _fetches_no_tags(name, rest)
    if name in ("checkout", "switch"):
        return any(w.startswith(_NEW_BRANCH_FLAGS) for w in rest)
    if name == "symbolic-ref":
        return not kept_shape(args)
    return name not in _STILL_REFS


def starts_hooks(args: list[str]) -> bool:
    """Whether a call can start a hook: a write, a `status` or a `diff`, which refresh the index when a file's stat changed
    and its content did not, or a `remote` or `config` that is not one of the exact read shapes."""
    at, name = subcommand(args)
    if name in ("status", "diff"):
        return True
    if name in ("remote", "config"):
        return not reads_only(name, args[at + 1 :])
    return name not in HOOK_FREE and may_write(args)
