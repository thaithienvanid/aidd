"""The guard's shell reader: a command line split into simple commands the way a shell cuts it (quotes, ANSI-C
strings, here-documents, `sh -c`, and wrappers), and the program and words each runs.
"""

from __future__ import annotations

import ntpath
import os
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path

_SEPARATOR_CHARS = set(";&|()")
WRAPPERS = {"sudo", "command", "nohup", "time", "exec", "builtin", "nice", "stdbuf", "timeout", "setsid", "ionice", "caffeinate", "chrt", "taskset"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
POWERSHELLS = {"pwsh", "powershell"}
# Wrapper options that take the next word as their value, when that value is not a number: `stdbuf -o L make`. No such
# list is ever complete, so `held_command` scans past a wrapper for a held program first (`_as_run`), and a word
# shaped like a number, a duration, a CPU list, or a mask (`5`, `10s`, `0-3`, `0x3`) is skipped as a value too.
_WRAPPER_VALUE_OPTIONS = {
    "env": frozenset({"-u", "--unset", "-C", "--chdir"}),
    "nice": frozenset({"-n"}),
    "sudo": frozenset({"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U"}),
    "stdbuf": frozenset({"-i", "-o", "-e"}),
    "timeout": frozenset({"-s", "-k", "--signal", "--kill-after"}),
}
_VALUE_WORD = re.compile(r"0x[0-9a-f]+|[0-9][0-9.,-]*[smhd]?", re.I)


def program_name(word: str) -> str:
    """A program word as the guard compares it: its basename on either path separator, lowercased, without a Windows
    launcher suffix, so `gh.exe`, `C:\\tools\\GH.EXE`, and `aidd.cmd` are `gh` and `aidd`."""
    name = ntpath.basename(word).lower()
    for suffix in (".exe", ".cmd", ".bat"):
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    return name


def powershell_plain(command: str) -> str:
    """A PowerShell command with its backtick escapes undone (`` mer`ge `` is `merge`): the text PowerShell runs."""
    return re.sub(r"`(.)", r"\1", re.sub(r"`\r?\n", " ", command), flags=re.S)


# A stand-in for escaped punctuation (`\;`, `\|`): shlex reads `\;` as a bare `;` separator, where a shell passes a
# literal `;` word (`tmux send-keys x \; run-shell y` is one command). A private-use character no command holds.
_ESCAPED = ""


def _mark_escaped_punctuation(command: str) -> str:
    """`command` with each unquoted backslash before shell punctuation replaced by _ESCAPED, so the punctuation after
    it stays part of a word; and a quoted string of punctuation alone (`';'`, `"&&"`), which shlex would hand back as a
    bare separator, marked the same way: a shell passes it as a word. ValueError when `command` already holds
    _ESCAPED: a word could then hide a real separator, so the command cannot be read (the caller fails closed)."""
    if _ESCAPED in command:
        raise ValueError("the command holds a character the shell check reserves")
    out, quote, i = [], "", 0
    while i < len(command):
        c = command[i]
        if not quote and c in "'\"":
            end = command.find(c, i + 1)
            body = command[i + 1 : end] if end > i else ""
            if body and set(body) <= set(";&|()<>"):
                out.append("".join(_ESCAPED + ch for ch in body))
                i = end + 1
                continue
        if quote:
            if c == quote:
                quote = ""
            elif c == "\\" and quote == '"' and i + 1 < len(command):
                out.append(command[i : i + 2])
                i += 2
                continue
        elif c in "'\"":
            quote = c
        elif c == "\\" and i + 1 < len(command):
            if command[i + 1] in ";&|()<>":
                out.append(_ESCAPED + command[i + 1])
            else:
                out.append(command[i : i + 2])
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def shell_tokens(command: str) -> list[str]:
    # A newline ends a command like `;` does; inside quotes it only changes text this check never executes.
    lex = shlex.shlex(_mark_escaped_punctuation(command).replace("\n", " ; "), posix=True, punctuation_chars=";&|()<>")
    lex.whitespace_split = True
    # An escaped punctuation character came back as a word of its own, or inside one: it is that word, `\;` (a backslash
    # marks it, so no check reads it as a separator).
    return [t.replace(_ESCAPED, "\\") for t in _join_escaped(list(lex))]


def _join_escaped(toks: list[str]) -> list[str]:
    """shlex splits `_ESCAPED;` into `_ESCAPED` and `;`: put each back together as one word."""
    out: list[str] = []
    for t in toks:
        if out and out[-1].endswith(_ESCAPED) and t and t[0] in ";&|()<>":
            out[-1] += t[0]
            if t[1:]:
                out.append(t[1:])
        else:
            out.append(t)
    return out


def _is_separator(tok: str) -> bool:
    return bool(tok) and set(tok) <= _SEPARATOR_CHARS


def _is_redirect(tok: str) -> bool:
    return bool(tok) and set(tok) <= set("<>&|") and (">" in tok or "<" in tok)


@dataclass
class SimpleCommand:
    """One simple command: its words, the files it redirects output to, and the files it reads as input. `depth` is how
    many subshell groups or command substitutions hold it: a `cd` inside one ends with it. A redirect after a group
    (`(echo y) > f`, `echo $(cat x) > f`) is a simple command with no words of its own."""

    argv: list[str] = field(default_factory=list)
    out: list[str] = field(default_factory=list)
    inp: list[str] = field(default_factory=list)
    depth: int = 0
    after: str = ""  # the separator before it: `|` when a pipe feeds it

    def __bool__(self) -> bool:
        return bool(self.argv or self.out or self.inp)


_PUNCTUATION_PIECE = re.compile(r";;&?|;&|[();]|[&|<>]+")


def _pieces(tok: str) -> list[str]:
    """A token of shell punctuation cut where a shell cuts it: `)>` is a group's end and a redirect, `);` two
    separators. A word is left whole."""
    if not tok or not set(tok) <= _SEPARATOR_CHARS | set("<>"):
        return [tok]
    return _PUNCTUATION_PIECE.findall(tok)


_ANSI_C = re.compile(r"\$'((?:\\.|[^'\\])*)'", re.S)
_ANSI_C_ESCAPES = {"a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v"}
_ANSI_C_CODE = re.compile(r"\\(?:x([0-9A-Fa-f]{1,2})|u([0-9A-Fa-f]{1,4})|U([0-9A-Fa-f]{1,8})|([0-7]{1,3})|(.))", re.S)
# `<<EOF`, `<<-EOF`, `<<'EOF'`, `<< "EOF"`, `<<\EOF`; never the here-string `<<<`.
_HEREDOC = re.compile(r"(?<!<)<<(?!<)(-?)[ \t]*(?:'([^'\n]*)'|\"([^\"\n]*)\"|\\?([A-Za-z0-9_.-]+))")
_SHELL_OPENER = re.compile(r"(?:^|[\s;&|(/\\])(?:sh|bash|zsh|dash|ksh|fish|pwsh|powershell)(?:\.exe)?\b[^\n]*?(?<!<)<<(?!<)", re.I)


def _ansi_c_char(m: re.Match) -> str:
    hexa, uni, uni8, octal, other = m.groups()
    if hexa or uni or uni8 or octal:
        code = int(hexa or uni or uni8, 16) if (hexa or uni or uni8) else int(octal, 8)
        return chr(code) if code < 0x110000 else ""
    return _ANSI_C_ESCAPES.get(other, other if other in "\\'\"?" else "\\" + other)


def _plain_ansi_c(command: str) -> str:
    """`command` with each bash ANSI-C string (`$'it\\'s'`) rewritten as the single-quoted word it stands for, which shlex reads."""
    return _ANSI_C.sub(lambda m: shlex.quote(_ANSI_C_CODE.sub(_ansi_c_char, m.group(1))), command)


def split_heredocs(command: str) -> tuple[str, list[str]]:
    """(`command` without its here-document bodies, the bodies a shell reads as commands). A body is text for the
    program it feeds (a commit message, a file), except when that program is a shell, which runs it."""
    lines = command.split("\n")
    kept: list[str] = []
    shell_bodies: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        kept.append(line)
        i += 1
        openers = list(_HEREDOC.finditer(line))
        for n, m in enumerate(openers):
            strip_tabs, word = m.group(1) == "-", next(g for g in m.groups()[1:] if g is not None)
            body: list[str] = []
            while i < len(lines) and (lines[i].lstrip("\t") if strip_tabs else lines[i]) != word:
                body.append(lines[i])
                i += 1
            i += 1  # the delimiter line
            if n == 0 and _SHELL_OPENER.search(line):
                shell_bodies.append("\n".join(body))
    return "\n".join(kept), shell_bodies


MAX_NESTING = 3  # levels of `sh -c` and `eval` the shell check follows; a deeper one is a command it cannot read


def simple_commands(command: str, depth: int = 0, broken: list[str] | None = None) -> list[SimpleCommand]:
    """Split a command line into simple commands, following `sh -c`, `bash -c`, and `eval` one level at a time.

    A command shlex cannot read (an ANSI-C string `$'it\\'s'`, a here-document with an apostrophe in it) is read again
    with those rewritten; one it still cannot read is added to `broken`, so the caller never takes "nothing parsed"
    for "nothing to deny"."""
    extra: list[SimpleCommand] = []
    try:
        toks = shell_tokens(command)
    except ValueError:
        stripped, bodies = split_heredocs(command)
        try:
            toks = shell_tokens(_plain_ansi_c(stripped))
        except ValueError:
            if broken is not None:
                broken.append(command)
            return []
        for body in bodies if depth < MAX_NESTING else []:
            for found in simple_commands(body, depth + 1, broken):
                found.depth += 1  # a shell that reads a here-document is a child shell
                extra.append(found)
    toks = [piece for tok in toks for piece in _pieces(tok)]
    out: list[SimpleCommand] = []
    group = 0  # open subshell groups and command substitutions; `depth` stays the nesting of `sh -c` and `eval`
    cases = 0  # open `case ... esac` blocks
    pattern = False  # inside a case, the next `)` ends a pattern, never a group
    cur = SimpleCommand()
    i = 0
    while i < len(toks):
        tok = toks[i]
        i += 1
        if pattern and tok in ("(", ")"):
            if tok == ")":
                pattern = False
                cur = SimpleCommand(depth=group)  # the pattern's words are not a command
        elif _is_redirect(tok):
            target = toks[i] if i < len(toks) else ""
            i += 1
            if target == "(":  # a process substitution, `>(cmd)`: the command inside is read as a group
                i -= 1
            # `2>&1` and `>&2` duplicate a descriptor; the digit after `>&` is not a file.
            elif not (tok.endswith("&") and target.isdigit()):
                (cur.inp if "<" in tok else cur.out).append(target)
        elif _is_separator(tok):
            if cur:
                out.append(cur)
            if cases and tok in (";;", ";&", ";;&"):
                pattern = True
            group = max(0, group + tok.count("(") - tok.count(")"))
            cur = SimpleCommand(depth=group, after=tok)
        else:
            if tok == "esac" and cases and not cur.argv:
                cases, pattern = cases - 1, False
            cur.argv.append(tok)
            if cur.argv[0] == "case" and len(cur.argv) == 3 and tok == "in":
                cases, pattern = cases + 1, True
    if cur:
        out.append(cur)
    expanded: list[SimpleCommand] = []
    for sc in out:
        expanded.append(sc)
        argv = program_argv(sc.argv)
        if not argv:
            continue
        name = program_name(argv[0])
        flag = next((a for a in argv[1:] if a.lower() in ("-c", "-command")), None) if name in POWERSHELLS else None
        inline, at = shell_operand(name, argv[1:]) if name in SHELLS else (False, None)
        if inline and at is not None:
            inner, shift = argv[1 + at], sc.depth + 1  # a child shell: its `cd` ends with it
        elif flag and argv.index(flag) + 1 < len(argv):
            inner, shift = " ".join(argv[argv.index(flag) + 1 :]), sc.depth + 1
        elif name == "eval":
            inner, shift = " ".join(argv[1:]), sc.depth  # eval runs in this shell
        else:
            continue
        if depth >= MAX_NESTING:
            if broken is not None:
                broken.append(f"nested more than {MAX_NESTING} levels of `sh -c` or `eval`")
            continue
        for found in simple_commands(inner, depth + 1, broken):
            found.depth += shift
            expanded.append(found)
    return expanded + extra


# Shell options that take the next word as their argument: `bash -o pipefail`, `bash --rcfile x.rc`.
_SHELL_ARG_OPTIONS = frozenset({"--rcfile", "--init-file"})


def shell_operand(name: str, args: list[str]) -> tuple[bool, int | None]:
    """How the POSIX shell `name` (one of _SHELLS) reads the words after its name: (inline, i). `inline` is true when a short-option cluster
    holds `c` (`-c`, `-lc`, `-cx`, `-euxc`). args[i] is then the command string, else the script file; i is None when
    no operand follows. It skips `--`, long options, and the argument of `-o`, `-O`, `+o`, `+O`, and of an `o` or `O`
    in a cluster (`-euo pipefail`). The splitter and `_as_run` both use it, so they never disagree on what runs."""
    if name not in SHELLS:
        return False, None
    inline, i = False, 0
    while i < len(args):
        word = args[i]
        if word == "--":
            return inline, i + 1 if i + 1 < len(args) else None
        if word.startswith("--"):
            i += 2 if word in _SHELL_ARG_OPTIONS else 1
        elif len(word) > 1 and word[0] in "-+":
            inline = inline or (word[0] == "-" and "c" in word[1:])
            i += 1 + word.count("o") + word.count("O")
        else:
            return inline, i
    return inline, None


def program_argv(argv: list[str]) -> list[str]:
    """The words after environment assignments and wrappers such as `sudo`, `env`, `command`, and `timeout 10`."""
    i = 0
    while i < len(argv):
        word = argv[i]
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", word):
            i += 1
        elif program_name(word) == "env":
            i += 1
            while i < len(argv) and (argv[i].startswith("-") or "=" in argv[i]):
                i += 2 if argv[i] in _WRAPPER_VALUE_OPTIONS["env"] else 1
        elif program_name(word) == "busybox" and i + 1 < len(argv) and program_name(argv[i + 1]) in SHELLS:
            i += 1  # `busybox sh -c ...` runs the shell
        elif program_name(word) in WRAPPERS:
            takes = _WRAPPER_VALUE_OPTIONS.get(program_name(word), frozenset())
            i += 1
            while i < len(argv) and (argv[i].startswith("-") or _VALUE_WORD.fullmatch(argv[i])):
                i += 2 if argv[i] in takes else 1
        else:
            break
    return argv[i:]


def positional_words(args: list[str], value_flags: set[str]) -> list[str]:
    """Positional words, skipping flags and the values of the flags that take one."""
    out, skip = [], False
    for a in args:
        if skip:
            skip = False
            continue
        if a.startswith("-"):
            skip = a in value_flags
            continue
        out.append(a)
    return out


def flag_value(args: list[str], *names: str) -> str | None:
    for i, a in enumerate(args):
        for n in names:
            if a == n and i + 1 < len(args):
                return args[i + 1]
            if a.startswith(n + "=") and n.startswith("--"):
                return a.split("=", 1)[1]
            if not n.startswith("--") and a.startswith(n) and len(a) > len(n):
                return a[len(n) :]
    return None


SEARCHERS = {"grep", "egrep", "fgrep", "rg", "ag", "ack", "cat", "head", "tail", "less", "more", "wc", "awk"}


# The modules `python -m` runs aidd's command line from.
_AIDD_MODULES = frozenset({"aidd", "aidd.cli", "aidd.__main__"})


def aidd_runs(argv: list[str]) -> list[list[str]]:
    """The words after each place a simple command runs aidd, through any wrapper: `uvx aidd`, `uv run aidd`, `pipx run
    aidd`, `python -m aidd` (or `-m aidd.cli`, `-maidd`), `xargs aidd`, `script -c 'aidd ...'`. A word naming the aidd
    program (its basename, or the module after `-m`) starts one. A search or an `echo` runs nothing."""
    if not argv or program_name(argv[0]) in SEARCHERS | {"echo", "printf"}:
        return []
    runs = []
    for i, word in enumerate(argv):
        if program_name(word) == "aidd":
            runs.append(argv[i + 1 :])
        elif word == "-m" and i + 1 < len(argv) and argv[i + 1] in _AIDD_MODULES:
            runs.append(argv[i + 2 :])
        elif word.startswith("-m") and word[2:] in _AIDD_MODULES:
            runs.append(argv[i + 1 :])
    return runs


def cd_target(here: Path, before: Path, args: list[str]) -> Path:
    """The folder bash's `cd` moves to: logical by default (`cd out/l/..` is out, with `..` taken as text), physical
    with -P, the folder before with `-`, and HOME with no folder."""
    physical = False
    while args and args[0].startswith("-") and len(args[0]) > 1 and args[0] != "--" and set(args[0][1:]) <= set("LPe@"):
        physical = physical or "P" in args[0]
        args = args[1:]
    args = args[1:] if args[:1] == ["--"] else args
    dest = args[0] if args else str(Path.home())
    if dest == "-":
        return before
    target = (here / dest) if not os.path.isabs(dest) else Path(dest)
    return Path(os.path.realpath(target)) if physical else Path(os.path.normpath(target))
