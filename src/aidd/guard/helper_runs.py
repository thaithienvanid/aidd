"""The helper rule's shell half: a subagent that is not an aidd-team role only reads (role_areas.is_read_only_subagent),
so the guard lets it run only the programs below that read, each without its options that write a file or start a
program the command names. Every other command is denied, so a form no one listed fails closed. That is an allow-list,
as the OWASP input validation guidance advises, because a list of what to deny misses what it never named (CWE-184).

A helper names each program, never its path or a wrapper such as `env` or `timeout`, and sets no variable, so PATH,
BASH_ENV, and the rest stay the session's. A shell may run only a `-c` command line, whose commands the parser reads
and this check judges one by one. PowerShell is denied whole, because this list is the POSIX shell's. To add a read
program, add it to _READERS, or to _WRITING_OPTIONS with the options of it that write or run code, with a case in
tests/test_guard_helper_runs.py. indirect_runs owns the readers it shares with `xargs` and `find -exec`.

A role and the main session keep the documented limit, a program that writes by itself, because each of their writes
lands in a scope the gate checks. A helper has no scope, so nothing would check what its code wrote.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from aidd.guard import edit_check, indirect_runs, shell_parser, shell_words

# Programs that only read or print, with no option that writes a file or starts a program.
_READERS = indirect_runs.READERS | {
    *("tac", "du", "egrep", "fgrep", "jq", "diff", "cmp", "comm", "cut", "tr", "nl", "paste", "column", "od", "strings"),
    *("sha256sum", "shasum", "md5sum", "realpath", "readlink", "pwd", "echo", "which", "type", "uname"),
}
_PLAIN = _READERS | {"true", "false", "cd"}
# Read programs with options that write a file or start a program, as (letters, long names). A long name also denies
# its abbreviations, because getopt_long and argparse take any unique prefix, and a letter denies each short-option
# cluster that holds it.
Options = tuple[str, tuple[str, ...]]
_WRITING_OPTIONS: dict[str, Options] = {
    **indirect_runs.GUARDED_READERS,
    "rg": ("", ("--pre", "--hostname-bin")),
    "tree": ("oR", ()),  # `-R` runs tree again with `-o 00Tree.html` in each folder
    "printf": ("v", ()),  # `printf -v NAME` sets a variable
}
_GIT_READS = frozenset(
    {
        *("log", "show", "diff", "status", "blame", "grep", "ls-files", "ls-tree", "rev-parse", "rev-list", "cat-file"),
        *("shortlog", "describe", "diff-tree", "show-ref", "for-each-ref", "name-rev", "merge-base"),
    }
)
# git commands that read only in these forms: every word after the command is one of these. A bare `git stash` saves
# and clears the work, so stash also needs a word (_GIT_NEEDS_A_WORD).
_GIT_LISTS = {
    "branch": frozenset({"--show-current", "-a", "--all", "-r", "--remotes", "-v", "-vv", "--verbose", "--list"}),
    "remote": frozenset({"-v", "--verbose"}),
    "tag": frozenset({"-l", "--list"}),
    "stash": frozenset({"list"}),
    "worktree": frozenset({"list", "--porcelain"}),
}
_GIT_NEEDS_A_WORD = frozenset({"stash"})
_GIT_WRITING: Options = ("", ("--output", "--ext-diff"))
_GIT_GREP_WRITING: Options = ("O", ("--output", "--ext-diff", "--open-files-in-pager"))
_AIDD_READS = frozenset({"list", "context", "validate", "help", "gate"})
_AIDD_WRITING: Options = ("", ("--html", "--record", "--events"))
# The shell's words that set a variable, which would change what a later program reads.
_SETS = frozenset({"for", "select", "read", "mapfile", "readarray", "export", "declare", "typeset", "local", "readonly", "let", "unset", "getopts"})
# A shell runs a `-c` line with only these flags: exit on error, unset variables, the trace.
_SHELL_FLAGS = re.compile(r"-[ceux]+")
_SED_FLAGS = re.compile(r"-[nErsz]+")
_SED_LONG = frozenset({"--quiet", "--silent", "--regexp-extended", "--separate", "--null-data", "--sandbox"})
_SED_ADDRESS = r"(?:\d+|\$|/[^/\\\n]*/)"
_SED_PRINT = re.compile(rf"(?:{_SED_ADDRESS}(?:,{_SED_ADDRESS})?)?p")
_UNIQ_VALUES = frozenset({"-f", "-s", "-w", "--skip-fields", "--skip-chars", "--check-chars"})
# `test` and `[` evaluate an array subscript (`-v a[...]`) as arithmetic, which can run a command substitution.
_ARITHMETIC = re.compile(r"[\[`]|\$\(")
_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]*\])?\+?=.*", re.S)


def _writing_option(args: list[str], options: Options) -> str | None:
    """The first word of `args` that is one of the long `options` or an abbreviation of one, or a short-option cluster
    that holds one of its letters; or None. It reads every word, past a `--` too, since that may be an option's value."""
    letters, longs = options
    for word in args:
        if word.startswith("--"):
            name = word.split("=", 1)[0]
            if len(name) > 2 and any(d.startswith(name) for d in longs):
                return word
        elif word.startswith("-") and set(letters) & set(word[1:]):
            return word
    return None


def _options(name: str, args: list[str], sc: shell_parser.SimpleCommand) -> str | None:
    word = _writing_option(args, _WRITING_OPTIONS[name])
    return f"`{name} {word}` writes a file or starts a program" if word else None


def _runs_readers(name: str, args: list[str], sc: shell_parser.SimpleCommand) -> str | None:
    """xargs and `find -exec` that run only readers (indirect_runs judges their globs), or find with no action that runs
    a program or writes and no word the shell may split into one."""
    if indirect_runs.runs_only_readers(sc):
        return None
    if name in indirect_runs.FIND_LIKE and not (indirect_runs.FIND_ALL_RUNS | indirect_runs.FIND_UNSAFE) & set(args):
        return _split(name, args)
    return f"`{name}` runs a program or writes, beyond one of the readers written plainly"


def _split(name: str, args: list[str]) -> str | None:
    """A word of a guarded program's that the shell may turn into an option, such as a file named `-o` for `*`."""
    split = next((w for w in args if shell_words.may_split(w)), None)
    return f"`{name}` gets {split}, which the shell may turn into an option, such as a file named -o; quote it" if split else None


def _uniq(name: str, args: list[str], sc: shell_parser.SimpleCommand) -> str | None:
    """uniq writes its second operand, so it reads at most one; `-` is stdin, and every word after `--` is an operand."""
    operands: list[str] = []
    i = 0
    while i < len(args):
        word = args[i]
        i += 1
        if word == "--":
            operands += args[i:]
            break
        if word in _UNIQ_VALUES:
            i += 1
        elif word == "-" or not word.startswith("-"):
            operands.append(word)
    return "`uniq` with a second file writes it" if len(operands) > 1 else None


def _sed(name: str, args: list[str], sc: shell_parser.SimpleCommand) -> str | None:
    """sed may only print lines, by number, `$`, or a plain pattern (`sed -n 1,20p`): its other commands write files
    (`w`) or run them (`e`)."""
    scripts: list[str] = []
    files: list[str] = []
    i = 0
    while i < len(args):
        word = args[i]
        i += 1
        if re.fullmatch(r"-[nErsz]*e", word):
            scripts.append(args[i] if i < len(args) else "")
            i += 1
        elif word.startswith("--expression="):
            scripts.append(word.split("=", 1)[1])
        elif word == "--":
            files += args[i:]
            break
        elif word.startswith("-") and word != "-":
            if not (_SED_FLAGS.fullmatch(word) or word in _SED_LONG):
                return f"`sed {word}` may write files; a helper prints lines with sed -n 1,20p"
        else:
            files.append(word)
    if not scripts and files:
        scripts.append(files.pop(0))
    printing = all(_SED_PRINT.fullmatch(piece.strip()) for script in scripts for piece in script.split(";") if piece.strip())
    return None if printing else "`sed` runs a script that is not a line print; a helper prints lines with sed -n 1,20p"


def _git(name: str, args: list[str], sc: shell_parser.SimpleCommand) -> str | None:
    if args == ["--version"]:
        return None
    i = 0
    while i < len(args) and args[i].startswith("-"):
        if args[i] not in ("-C", "--no-pager", "-P", "--no-optional-locks"):
            return f"`git {args[i]}` changes how git runs"
        i += 2 if args[i] == "-C" else 1
    sub, rest = (args[i], args[i + 1 :]) if i < len(args) else ("", [])
    if sub in _GIT_LISTS:
        return (
            None
            if set(rest) <= _GIT_LISTS[sub] and (rest or sub not in _GIT_NEEDS_A_WORD)
            else f"`git {sub}` with these words changes the repository; it reads only as {sub} {' '.join(sorted(_GIT_LISTS[sub]))}"
        )
    reflog = sub == "reflog" and (not rest or rest[0] == "show" or rest[0].startswith("-"))
    if sub not in _GIT_READS and not reflog:
        return f"`git {sub}` is not one of git's reads: {', '.join(sorted(_GIT_READS | set(_GIT_LISTS) | {'reflog'}))}"
    word = _writing_option(rest, _GIT_GREP_WRITING if sub == "grep" else _GIT_WRITING)
    return f"`git {sub} {word}` writes a file or starts a program" if word else None


def _aidd(name: str, args: list[str], sc: shell_parser.SimpleCommand) -> str | None:
    sub = args[0] if args else ""
    forecast = any(w == "--paths" or w.startswith("--paths=") for w in args)
    if sub not in _AIDD_READS or (sub == "gate" and not forecast):
        return f"`aidd {sub}` is not one of aidd's reads (list, context, validate, help, gate --paths)"
    word = _writing_option(args[1:], _AIDD_WRITING)
    return f"`aidd {sub} {word}` writes a file" if word else None


def _shell(name: str, args: list[str], sc: shell_parser.SimpleCommand) -> str | None:
    inline, at = shell_parser.shell_operand(name, args)
    if inline and at is not None and all(_SHELL_FLAGS.fullmatch(w) for w in args[:at]):
        return None
    return f"`{name}` runs code that is not a `-c` command line"


def _test(name: str, args: list[str], sc: shell_parser.SimpleCommand) -> str | None:
    unread = next((w for w in args if w == "-v" or _ARITHMETIC.search(w)), None)
    return f"`{name} {unread}` may evaluate arithmetic, which can run a command" if unread else None


def _command(name: str, args: list[str], sc: shell_parser.SimpleCommand) -> str | None:
    return None if args[:1] in (["-v"], ["-V"]) else "`command` runs a program; a helper asks with command -v"


Check = Callable[[str, list[str], shell_parser.SimpleCommand], "str | None"]
# Read programs a check holds to their reads, and the shell's words a check holds to theirs.
_PROGRAM_CHECKS: dict[str, Check] = {
    **dict.fromkeys(_WRITING_OPTIONS, _options),
    **dict.fromkeys(indirect_runs.FIND_LIKE | indirect_runs.XARGS_LIKE, _runs_readers),
    "uniq": _uniq,
    "sed": _sed,
    "git": _git,
    "aidd": _aidd,
}
_CHECKS: dict[str, Check] = {
    **_PROGRAM_CHECKS,
    **dict.fromkeys(shell_parser.SHELLS - {"fish"}, _shell),
    "test": _test,
    "[": _test,
    "command": _command,
}
READ_PROGRAMS = sorted(_READERS | set(_PROGRAM_CHECKS))

HELPER_RUNS = (
    edit_check.HELPER_DENY
    + ". Hand a test run or a script back the same way. A helper runs only these reads, without their options that write"
    + " a file or start a program the command names: "
    + ", ".join(READ_PROGRAMS)
    + ", and `sh -c` running them"
)
POWERSHELL = "a helper runs no PowerShell, since its read programs are the POSIX shell's; use Bash to read"


def denial(whats: list[str]) -> str:
    """The one denial for every command on a line that a helper may not run: each reason, then the rule and its list once."""
    return "; ".join(dict.fromkeys(whats)) + ": " + HELPER_RUNS


def unread_code(sc: shell_parser.SimpleCommand) -> str | None:
    """Why a helper may not run this simple command, in words for the denial, or None when it only reads."""
    argv = sc.argv[shell_parser.reserved_lead(sc.argv) :]
    if not argv:
        return None
    word, args = argv[0], argv[1:]
    if _ASSIGNMENT.fullmatch(word):
        return f"`{word.split('=', 1)[0]}=` sets a variable"
    if "/" in word or "\\" in word:
        return f"{word} names a program by its path"
    name = shell_parser.program_name(word)
    if name in _PLAIN:
        return None
    if name in _PROGRAM_CHECKS and _PROGRAM_CHECKS[name] is not _runs_readers and (split := _split(name, args)):
        return split
    if (check := _CHECKS.get(name)) is not None:
        return check(name, args, sc)
    if name in _SETS:
        return f"`{name}` sets a variable, so run each command on its own"
    return f"`{name}` is not a read program"
