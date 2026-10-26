"""Commands another program runs for a shell line: the programs in RUNS_COMMANDS (`xargs`, `parallel`, `find -exec|-execdir|-ok|
-okdir`, `fd -x|-X`, and their kin). They fill in words from their input, or the paths they find, which the guard never
sees.

Two readings. `runs_only_readers` says when `xargs` or `find -exec|-execdir` runs only a literal reader, so a writer the
guard holds may run it (write_targets.OPAQUE denies the rest). `indirect_commands` gives each command they run as a
simple command, with INPUT for each word they fill in, so the git checks read a ref, a branch, or a subcommand that only
the input names as one they cannot read, and fail closed. `named_runs` is the backstop for a program no table names
(`ssh host gh ...`, `docker exec c git ...`): from each word that names git, gh, glab, aidd, or tmux, the rest of the
command is read as a command of its own.

The readers are programs no option makes write or run another program, because `xargs` hands them words from its input,
options too. `sort` and `file` have such an option (`-o`, `--compress-program`, `-T`; `-C`), so they pass only with a
literal `--` before the words that reach them, and never under `xargs -I`, where the input lands anywhere. `uniq` is not
a reader: its second operand is a file it writes.
"""

from __future__ import annotations

import itertools
import re
import shlex

from aidd.guard import shell_parser, shell_words, tmux_commands

READERS = frozenset({"wc", "grep", "head", "tail", "cat", "basename", "dirname", "ls", "stat"})
# A program that reads unless an option makes it write or run one: its option letters and long names that do.
GUARDED_READERS: dict[str, tuple[str, tuple[str, ...]]] = {
    "sort": ("oT", ("--output", "--compress-program", "--temporary-directory")),
    "file": ("C", ("--compile",)),
}
# The programs that run commands, by the way they take the command they run: find's `-exec` clauses, xargs's options, parallel's many
# shapes (its kin take the same: a command with `{}` placeholders, or none, when each input line is the command), and
# fd's `-x|--exec|-X|--exec-batch`, which take the rest of the line.
FIND_LIKE = frozenset({"find", "gfind", "bfs"})
XARGS_LIKE = frozenset({"xargs", "gxargs"})
PARALLEL_LIKE = frozenset({"parallel", "sem", "env_parallel", "rush", "xe"})
FD_LIKE = frozenset({"fd", "fdfind"})
RUNS_COMMANDS = FIND_LIKE | XARGS_LIKE | PARALLEL_LIKE | FD_LIKE
_FD_RUNS = frozenset({"-x", "--exec", "-X", "--exec-batch"})
# A word xargs, parallel, or find fills in: the guard reads it as a name only the shell resolves.
INPUT = "$INPUT"
# An expansion or a process substitution: text the shell turns into words the guard never sees.
_UNREAD = re.compile(r"[$`]|[<>]\(")
# A glob, a brace expansion (`{a,b}`, `{1..3}`; never `{}` alone), or a leading tilde, which the shell may expand into
# more words, an option among them, unless quoted: the guard reads words with their quotes gone, so it cannot tell.
# Harmless in a reader's words; elsewhere it counts.
_EXPANDS = re.compile(r"[*?\[]|\{[^{}]*(?:,|\.\.)[^{}]*\}|^~")
# find's tests whose value is a pattern, where a glob is what find is given (`-name '*.py'`).
FIND_PATTERNS = frozenset({"-name", "-iname", "-path", "-ipath", "-wholename", "-iwholename", "-regex", "-iregex", "-lname", "-ilname"})

# xargs's options (GNU findutils and BSD): without a value, with one (attached or the next word), and with an optional
# value that only an attached one gives. Any other option, such as GNU's --process-slot-var, which sets a variable in
# the program's environment, leaves the line unread.
_XARGS_FLAGS = frozenset("0oprtx")
_XARGS_VALUE = frozenset("adEIJLnPRSs")
_XARGS_OPTIONAL = frozenset("eil")
_XARGS_LONG_FLAGS = frozenset({"--null", "--no-run-if-empty", "--verbose", "--exit", "--open-tty", "--interactive", "--show-limits"})
_XARGS_LONG_VALUE = frozenset({"--arg-file", "--delimiter", "--max-args", "--max-procs", "--max-chars"})
_XARGS_LONG_OPTIONAL = frozenset({"--eof", "--replace", "--max-lines"})

# find's actions that write or ask, and the starting-point options a name that starts with `-` can come in by.
FIND_UNSAFE = frozenset({"-delete", "-fprint", "-fprint0", "-fprintf", "-fls", "-ok", "-okdir", "-f", "-files0-from"})
_FIND_RUNS = frozenset({"-exec", "-execdir"})
FIND_ALL_RUNS = _FIND_RUNS | {"-ok", "-okdir"}
_NESTING = 3  # xargs that runs xargs, and so on; deeper, the innermost is read as git with an unread subcommand
_STARTS = 12  # the words _every_command tries as the start of the command, which bounds the work on a long line
_MOST = 48  # the commands one level gives before the rest is read as unreadable git
_PARALLEL_INPUTS = re.compile(r":{3,4}\+?")  # parallel's `:::`, `::::`, `:::+`, and `::::+`, which start its inputs
_PLACEHOLDER = re.compile(r"\{[^{}]*\}")  # parallel's `{}`, `{.}`, `{/}`, `{#}`, `{1}`
# The programs `named_runs` starts a command at, and the programs whose words are only text (a search, an echo).
_NAMED = frozenset({"git", "gh", "glab", "aidd", "tmux", "orca"})
_TEXT_ONLY = READERS | shell_parser.SEARCHERS | {"echo", "printf"}
_NAMED_MOST = 8


def runs_a_command(sc: shell_parser.SimpleCommand) -> bool:
    """Whether `sc` has another program run a command: xargs and parallel and their kin always (xargs alone runs echo), find
    with an `-exec|-execdir|-ok|-okdir` clause, and fd with `-x|-X`."""
    argv = shell_parser.program_argv(sc.argv)
    name, args = (shell_parser.program_name(argv[0]), set(argv[1:])) if argv else ("", set())
    return name in XARGS_LIKE | PARALLEL_LIKE or (name in FIND_LIKE and bool(FIND_ALL_RUNS & args)) or (name in FD_LIKE and _fd_runs(argv[1:]))


def _fd_runs(args: list[str]) -> bool:
    return any(a in _FD_RUNS or a.startswith(("--exec=", "--exec-batch=")) for a in args)


def runs_only_readers(sc: shell_parser.SimpleCommand) -> bool:
    """Whether `sc` is `xargs` or `find` with `-exec|-execdir`, written plainly (no wrapper, assignment, output redirect,
    or expansion), and every program it runs is a reader with words that keep it one."""
    words = sc.argv
    if not words or sc.out or any(_UNREAD.search(w) for w in words):
        return False
    first = words[0]
    if "/" in first and not first.startswith("/"):
        return False  # `./xargs` is a program of the repository's, not xargs
    name = shell_parser.program_name(first)
    if name in XARGS_LIKE:
        found = _xargs_program(words[1:])
        if found is None or found[0] >= len(words) - 1:
            return False  # xargs alone runs echo: not a reader
        at, replaces = found
        program = words[1 + at]
        if any(_EXPANDS.search(w) for w in words[: 2 + at]):
            return False  # a glob or a brace there may give xargs other options, or another program
        if any(not r or r in program for r in replaces):
            return False  # the input would become the program's name
        return _reader(program, words[2 + at :], from_input=True, replaced=bool(replaces))
    if name in FIND_LIKE:
        args = words[1:]
        clauses = find_clauses(args)
        if not clauses or FIND_UNSAFE & set(args) or any(end is None for _, _, end in clauses):
            return False  # find refuses a clause with no end, so the guard reads none
        inside = {j for _, start, end in clauses if end for j in range(start, end)}
        if any(_EXPANDS.search(w) and j not in inside and (j == 0 or args[j - 1] not in FIND_PATTERNS) for j, w in enumerate(args)):
            return False  # a starting point or a test the shell may expand into an action, such as a file named -delete
        if find_glob_injects(args):
            return False
        return all(_reader(args[start], args[start + 1 : end], from_input=False, replaced=False) for _, start, end in clauses if end)
    return False


def find_glob_injects(args: list[str]) -> bool:
    """Whether a find pattern's value (`-name *`) may reach find as more words than one, an action among them: it holds
    a glob, a brace, a tilde, or an expansion (shell_words.may_split). With files `*` and `-delete` in the folder,
    `-name *` is `-name '*' -delete`, and an earlier command on the line can make them, so the files on disk never
    decide. A quoted pattern (`-name '*.py'`) is one word, and find gets it as it is; a word whose quoting the guard
    does not know counts, failing closed."""
    return any(args[j - 1] in FIND_PATTERNS and shell_words.may_split(w) for j, w in enumerate(args[1:], start=1))


def opaque_program(argv: list[str]) -> bool:
    """Whether the program a simple command runs is a name only the shell, or the input of xargs or find, resolves: an
    expansion (`$X`, `$(...)`, INPUT), a glob, or a brace in its name, or a shell whose options or script the input
    fills in (`xargs sh` with the input `-c '...'`)."""
    if not argv:
        return False
    name = shell_parser.program_name(argv[0])
    if name not in ("[", "[[") and re.search(r"[$`*?\[]|\{[^{}]*(?:,|\.\.)", name):
        return True
    if name in shell_parser.SHELLS:
        _, at = shell_parser.shell_operand(name, argv[1:])
        return any(INPUT in w for w in argv[1 : (at + 2 if at is not None else len(argv))])
    return False


def stream_program(simple: shell_parser.SimpleCommand) -> str | None:
    """The program of a simple command that runs code from a stream the line never shows (shell_parser.stream_fed),
    or None."""
    argv = shell_parser.program_argv(simple.argv)
    return argv[0] if argv and shell_parser.stream_fed(simple) else None


def first_stream_program(command: str) -> str | None:
    """The first program in `command` that runs code from a stream the line never shows (stream_program), or None."""
    return next((p for sc in shell_parser.simple_commands(command) if (p := stream_program(sc))), None)


def first_opaque_program(command: str) -> str | None:
    """The first program word in `command` that is a name only the shell or the input resolves (opaque_program), in
    each simple command and in what xargs, find, or their kin run for it; None for none. A here-document's text is a command only where a
    shell reads it (`bash <<EOF`), never where it is a commit message or a file."""
    stripped, bodies = shell_parser.split_heredocs(command)
    for text in (stripped, *bodies):
        for sc in shell_parser.simple_commands(text):
            for found in (sc, *indirect_commands(sc)):
                argv = shell_parser.program_argv(found.argv)
                if opaque_program(argv):
                    return argv[0]
    return None


def named_runs(sc: shell_parser.SimpleCommand) -> list[shell_parser.SimpleCommand]:
    """The backstop for a program no table names that runs a command: in a command whose program is not a search, a reader, or an echo,
    each word that names git, gh, glab, aidd, tmux, or orca starts a command of its own, read as the agent's (`ssh host gh
    pr merge 3`, `watch -n1 gh ...`). tmux refuses a command line that names a command it lacks, so a word `tmux`
    followed by none it knows (`brew install tmux git`) runs nothing."""

    argv = shell_parser.program_argv(sc.argv)
    if not argv or shell_parser.program_name(argv[0]) in _TEXT_ONLY:
        return []
    found: list[shell_parser.SimpleCommand] = []
    for k in range(1, len(argv)):
        name = shell_parser.program_name(argv[k])
        if name not in _NAMED or (name == "tmux" and "?" in tmux_commands.commands(argv[k + 1 :])[0]):
            continue
        # Plain words: the program may hand them to a shell that reads them again (`ssh host gh ...`), quotes gone.
        found.append(shell_parser.SimpleCommand([str(w) for w in argv[k:]], depth=sc.depth + 1))
        if len(found) >= _NAMED_MOST:
            break
    return found


def indirect_commands(sc: shell_parser.SimpleCommand, depth: int = 0) -> list[shell_parser.SimpleCommand]:
    """Each command `sc` has xargs, parallel, find, fd, or their kin run, one level down, with INPUT for every word they fill in. Under `find
    -execdir`, git runs in a folder the guard does not know, so it reads `git -C INPUT`. For xargs with options the
    guard does not read, and for parallel and its kin, every command the line could run is read (_every_command)."""
    argv = shell_parser.program_argv(sc.argv)
    if not argv:
        return []
    name, args = shell_parser.program_name(argv[0]), argv[1:]
    runs: list[list[str]] = []
    if name in XARGS_LIKE:
        found = _xargs_program(args)
        if found is None:
            runs = _every_command(args)
        elif found[0] < len(args):
            at, replaces = found
            words = args[at:]
            runs = [[_filled(w, replaces) for w in words] if replaces else [*words, INPUT]]
    elif name in PARALLEL_LIKE:
        runs = _every_command(args)
    elif name in FIND_LIKE:
        for kind, start, end in find_clauses(args):
            words = [w.replace("{}", INPUT) for w in args[start : end if end is not None else len(args)]]
            if kind in ("-execdir", "-okdir") and words and shell_parser.program_name(words[0]) == "git":
                words[1:1] = ["-C", INPUT]
            runs.append(words)
    elif name in FD_LIKE:
        runs = _fd_commands(args)
    out: list[shell_parser.SimpleCommand] = []
    for words in runs:
        if not words:
            continue
        if depth >= _NESTING or len(out) >= _MOST:
            # Deeper, or more, than the guard reads: git with a subcommand it cannot read, which the git checks deny.
            return [*out, shell_parser.SimpleCommand(["git", INPUT], depth=sc.depth + 1)]
        for inner in shell_parser.simple_commands(shlex.join(words)):
            inner.depth += sc.depth + 1  # a program of its own: a `cd` inside it ends with it
            out += [inner, *indirect_commands(inner, depth + 1)]
    return out


def _fd_commands(args: list[str]) -> list[list[str]]:
    """The commands fd's `-x|--exec|-X|--exec-batch` run: the words after it, up to a `;`, with each placeholder (`{}`,
    `{/}`, `{//}`, `{.}`, `{/.}`) as INPUT, and the path at the end when it names none."""
    found: list[list[str]] = []
    for k, a in enumerate(args):
        if a not in _FD_RUNS and not a.startswith(("--exec=", "--exec-batch=")):
            continue
        rest = ([a.split("=", 1)[1]] if "=" in a else []) + args[k + 1 :]
        words = list(itertools.takewhile(lambda w: w not in (";", "\\;"), rest))
        filled = [_PLACEHOLDER.sub(INPUT, w) for w in words]
        found.append(filled if any(INPUT in w for w in filled) else [*filled, INPUT])
    return found


def _every_command(args: list[str]) -> list[list[str]]:
    """For xargs with an option the guard does not read, and for parallel and its kin, whose options and command take
    more shapes than one: the command that starts at each word that is not an option (the first _STARTS of them), up
    to parallel's `:::`, with each `{...}` placeholder and the input after it as INPUT. One of them is the command that
    runs. A placeholder starts one only where nothing but options and their values come before it. With no command at
    all, each input is the command: INPUT."""
    command = list(itertools.takewhile(lambda w: not _PARALLEL_INPUTS.fullmatch(w), args))
    starts = [k for k, w in enumerate(command) if not w.startswith("-") and (not _PLACEHOLDER.fullmatch(w) or _after_options(command[:k]))]
    found = [[_PLACEHOLDER.sub(INPUT, w) for w in command[k:]] + [INPUT] for k in starts[:_STARTS]]
    return found if any(not w.startswith("-") for w in command) else [[INPUT]]


def _after_options(words: list[str]) -> bool:
    """Whether every word is an option or the value right after one, so the word after them may be the program."""
    return all(w.startswith("-") or (j and words[j - 1].startswith("-")) for j, w in enumerate(words))


def _filled(word: str, replaces: list[str]) -> str:
    for r in replaces:
        word = word.replace(r, INPUT) if r else INPUT
    return word


def _xargs_program(args: list[str]) -> tuple[int, list[str]] | None:
    """(where the program xargs runs is in `args`, the replace strings -I, -i, -J, or --replace set), or None when an
    option is one the guard does not read. The index is len(args) when xargs names no program."""
    i, replaces = 0, []
    while i < len(args) and args[i].startswith("-") and args[i] != "-":
        word = args[i]
        i += 1
        if word == "--":
            break
        if word.startswith("--"):
            key, has_value, value = word.partition("=")
            if key in _XARGS_LONG_FLAGS and not has_value:
                continue
            if key in _XARGS_LONG_OPTIONAL:
                replaces += [value or "{}"] if key == "--replace" else []
                continue
            if key not in _XARGS_LONG_VALUE:
                return None
            i += 0 if has_value else 1
            continue
        for at, letter in enumerate(word[1:], start=1):
            rest = word[at + 1 :]
            if letter in _XARGS_FLAGS:
                continue
            if letter in _XARGS_OPTIONAL:
                replaces += [rest or "{}"] if letter == "i" else []
                break
            if letter not in _XARGS_VALUE:
                return None
            if not rest:
                if i >= len(args):
                    return None
                rest, i = args[i], i + 1
            replaces += [rest] if letter in ("I", "J") else []
            break
    return min(i, len(args)), replaces


def find_clauses(args: list[str]) -> list[tuple[str, int, int | None]]:
    """Each `-exec`, `-execdir`, `-ok`, or `-okdir` clause in find's `args`: (its action, where its program is, where
    its end is, or None when it has none). find ends a clause at `;` (which the reader keeps as `\\;`) or at a `+` right
    after `{}`; a word bash passes as `\\;` ends none, so find's clause can only run longer than the one read here."""
    out: list[tuple[str, int, int | None]] = []
    i = 0
    while i < len(args):
        if args[i] not in FIND_ALL_RUNS:
            i += 1
            continue
        start = i + 1
        end = next((j for j in range(start, len(args)) if args[j] in (";", "\\;") or (args[j] == "+" and args[j - 1] == "{}")), None)
        out.append((args[i], start, end if end != start else None))
        i = (end if end is not None else len(args)) + 1
    return out


def _reader(program: str, words: list[str], *, from_input: bool, replaced: bool) -> bool:
    """Whether `program` with `words` (and the words find or xargs adds) only reads. The name must be exactly a listed
    one: no path, no other case, nothing find or xargs fills in."""
    if program in READERS:
        return True
    if program not in GUARDED_READERS or replaced or "--" not in words:
        return False  # without `--`, the words find or xargs adds could be options
    letters, longs = GUARDED_READERS[program]
    before = words[: words.index("--")]
    if not from_input and "{}" in before:
        return False
    for w in before:
        if _EXPANDS.search(w):
            return False  # `sort * --` with a file named -ofoo is `sort -ofoo`
        if w.startswith("--"):
            key = w.split("=", 1)[0]
            if len(key) > 2 and any(long.startswith(key) for long in longs):
                return False
        elif w.startswith("-") and any(c in letters for c in w[1:]):
            return False
    return True
