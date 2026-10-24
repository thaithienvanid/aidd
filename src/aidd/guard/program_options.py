"""How getopt reads a program's options: a letter in a cluster, a long option by any prefix, and the values some take."""

from __future__ import annotations

from aidd.guard import shell_words


def has_option(args: list[str], letter: str, long: str, values: tuple[str, tuple[str, ...]] = ("", ())) -> bool:
    """Whether `args` hold the option `letter`, alone or in a cluster (`-sf`), or `long` by any prefix, read in order as
    getopt reads them: a value an option takes (`values`: its short letters and its long names) is no option, and `--`
    ends them. A prefix of two long options counts too, since the program then refuses the command."""
    short_values, long_values = values
    skip = False
    for a in args:
        name = a.split("=", 1)[0]
        if skip or a == "--":
            if a == "--" and not skip:
                return False
            skip = False
        elif a.startswith("--") and len(name) > 2:
            if long.startswith(name):
                return True
            skip = "=" not in a and any(v.startswith(name) for v in long_values)
        elif a.startswith("-") and len(a) > 1:
            for k, c in enumerate(a[1:], 1):
                if c == letter:
                    return True
                if c in short_values:
                    skip = k == len(a) - 1  # its value is the cluster's rest, or the next word
                    break
    return False


# env's long options, which it takes by any prefix that names one alone, and those of them that take a value.
_ENV_LONGS: tuple[str, ...] = ("--ignore-environment", "--null", "--unset", "--chdir", "--split-string", "--argv0", "--block-signal")
_ENV_LONGS += ("--default-signal", "--ignore-signal", "--list-signal-handling", "--debug", "--help", "--version")
_ENV_LONG_VALUES = frozenset({"--unset", "--chdir", "--split-string", "--argv0"})


def env_options(argv: list[str], start: int) -> tuple[int, str | None, bool]:
    """Read env's options from `argv[start]`, the word after `env`, as env does: (where its command starts, the STRING of
    `-S STRING` or None, whether every option read exactly). A short cluster (`-iu NAME`) ends at a letter that takes a
    value, which is the cluster's rest or the next word; a long option may be any prefix of one alone."""
    split, i = None, start
    while i < len(argv) and (argv[i].startswith("-") or "=" in argv[i]):
        word = argv[i]
        if word == "--":
            return i + 1, split, True
        if not word.startswith("-"):  # NAME=VALUE
            i += 1
            continue
        if word.startswith("--"):
            name, eq, value = word.partition("=")
            found = [o for o in _ENV_LONGS if o.startswith(name)] if len(name) > 2 else []
            if len(found) != 1:
                return i, split, False
            if found[0] in _ENV_LONG_VALUES and not eq:
                if i + 1 >= len(argv):
                    return i, split, False
                value, i = argv[i + 1], i + 1
            split = value if found[0] == "--split-string" else split
            i += 1
            continue
        for at, letter in enumerate(word[1:], 1):
            if letter in "i0v":
                continue
            if letter not in "uCSa":
                return i, split, False
            value = word[at + 1 :]
            if not value:
                if i + 1 >= len(argv):
                    return i, split, False
                value, i = argv[i + 1], i + 1
            split = value if letter == "S" else split
            break
        i += 1
    return i, split, True


# `git restore`'s long options: the switches (each with its `--no-` form), and those that take a value.
_RESTORE_SWITCHES = ("staged", "worktree", "patch", "quiet", "progress", "merge", "ours", "theirs", "overlay")
_RESTORE_SWITCHES_TOO = ("recurse-submodules", "ignore-unmerged", "ignore-skip-worktree-bits", "pathspec-file-nul")
_RESTORE_VALUES = ("source", "conflict", "unified", "inter-hunk-context", "pathspec-from-file")
_RESTORE_LONGS = tuple([*_RESTORE_SWITCHES, *_RESTORE_SWITCHES_TOO, *(f"no-{s}" for s in (*_RESTORE_SWITCHES, *_RESTORE_SWITCHES_TOO)), *_RESTORE_VALUES])


def restore_writes_index_only(words: list[str]) -> bool:
    """Whether a `git restore` surely writes the index alone: read in order as git reads it, the last of `--staged`
    (`-S`) and `--no-staged`, and of `--worktree` (`-W`) and `--no-worktree`, wins, and a long option counts by any
    prefix git takes of it alone. Staged and not worktree is index only. A word before `--` the guard cannot read for
    sure (an unknown or ambiguous option, an unquoted glob, or an expansion, quoted too, whose value may start with
    `-`) makes it a worktree write. `words` start at git's subcommand."""
    if words[:1] != ["restore"]:
        return False
    rest = words[1:]
    rest = rest[: rest.index("--")] if "--" in rest else rest
    toggles = {"staged": False, "worktree": False}
    skip = False
    for a in rest:
        if skip or not a.startswith("-"):
            skip = False
            if not shell_words.literal(a):
                return False  # a value or a path the shell expands may be an option
            continue
        if not shell_words.literal(a):
            return False
        if a.startswith("--"):
            key, eq, _ = a[2:].partition("=")
            names = [n for n in _RESTORE_LONGS if n == key] or [n for n in _RESTORE_LONGS if n.startswith(key)]
            if len(names) != 1:
                return False
            name = names[0]
            skip = name in _RESTORE_VALUES and not eq
            for toggle in toggles:
                toggles[toggle] = True if name == toggle else False if name == f"no-{toggle}" else toggles[toggle]
            continue
        for k, letter in enumerate(a[1:], start=1):
            if letter in "sU":
                skip = k == len(a) - 1  # its value is the rest of the word, or the next word
                break
            if letter not in "SWpqm":
                return False
            toggles["staged"] = toggles["staged"] or letter == "S"
            toggles["worktree"] = toggles["worktree"] or letter == "W"
    return toggles["staged"] and not toggles["worktree"]
