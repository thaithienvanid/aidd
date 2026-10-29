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

from aidd.guard import program_options, shell_words

_SEPARATOR_CHARS = set(";&|()")
WRAPPERS = {"sudo", "command", "nohup", "time", "exec", "builtin", "nice", "stdbuf", "timeout", "setsid", "ionice", "caffeinate", "chrt", "taskset", "arch"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
POWERSHELLS = {"pwsh", "powershell"}
# Wrapper options that take the next word as their value, when that value is not a number: `stdbuf -o L make`. No such
# list is ever complete, so `held_command` scans past a wrapper for a held program first (`_as_run`), and a word
# shaped like a number, a duration, a CPU list, or a mask (`5`, `10s`, `0-3`, `0x3`) is skipped as a value too.
_WRAPPER_VALUE_OPTIONS = {
    "arch": frozenset({"-arch", "-d", "-e"}),  # macOS: `arch -arm64 cmd`, `arch -arch x86_64 -e K=V cmd`
    "env": frozenset({"-u", "--unset", "-C", "--chdir"}),
    "nice": frozenset({"-n"}),
    "sudo": frozenset({"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U"}),
    "stdbuf": frozenset({"-i", "-o", "-e"}),
    "timeout": frozenset({"-s", "-k", "--signal", "--kill-after"}),
}
_VALUE_WORD = re.compile(r"0x[0-9a-f]+|[0-9][0-9.,-]*[smhd]?", re.I)
# The shell's reserved words that may start a simple command, before the program it runs (`if true; then gh ...`,
# `{ gh ...; }`, `! gh ...`): skipped the way a wrapper is. `coproc NAME {` and `function NAME` skip their name too.
RESERVED = frozenset({"if", "then", "elif", "else", "do", "while", "until", "!", "{", "}", "fi", "done", "esac", "coproc", "function"})
# Multi-call programs that run the applet their next word names (`busybox xargs`, `toybox sh`).
_MULTI_CALL = frozenset({"busybox", "toybox"})


def program_name(word: str) -> str:
    """A program word as the guard compares it: its basename on either path separator, lowercased, without a Windows
    launcher suffix, so `gh.exe`, `C:\\tools\\GH.EXE`, and `aidd.cmd` are `gh` and `aidd`."""
    name = ntpath.basename(word).lower()
    for suffix in (".exe", ".cmd", ".bat"):
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    return name


def powershell_plain(command: str) -> str:
    """The text PowerShell runs: backtick escapes undone (`` mer`ge `` is `merge`), and typographic quotes read as `"` and `'`."""
    command = command.translate({0x201C: 34, 0x201D: 34, 0x201E: 34, 0x2018: 39, 0x2019: 39, 0x201A: 39, 0x201B: 39})
    return re.sub(r"`(.)", r"\1", re.sub(r"`\r?\n", " ", command), flags=re.S)


# A stand-in for escaped punctuation (`\;`, `\|`): shlex reads `\;` as a bare `;` separator, where a shell passes a
# literal `;` word (`tmux send-keys x \; run-shell y` is one command). A private-use character no command holds.
_ESCAPED = ""


def _mark_escaped_punctuation(command: str) -> str:
    """`command` with each unquoted backslash before shell punctuation replaced by _ESCAPED, so the punctuation after
    it stays part of a word; and a quoted string of punctuation alone (`';'`, `"&&"`), which shlex would hand back as a
    bare separator, marked the same way: a shell passes it as a word. And as bash reads it: a backslash before a
    newline, outside single quotes, joins the lines (`mer\\<newline>ge` is `merge`), and a `#` that starts a word starts
    a comment to the end of its line (`a#b` is one word). ValueError when `command` already holds _ESCAPED: a word
    could then hide a real separator, so the command cannot be read (the caller fails closed)."""
    if _ESCAPED in command:
        raise ValueError("the command holds a character the shell check reserves")
    out, quote, i, starts = [], "", 0, True  # `starts`: the next character starts a word
    while i < len(command):
        c, nxt = command[i], command[i + 1 : i + 2]
        if not quote and c in "'\"":
            end = command.find(c, i + 1)
            body = command[i + 1 : end] if end > i else ""
            if body and set(body) <= set(";&|()<>"):
                out.append("".join(_ESCAPED + ch for ch in body))
                i, starts = end + 1, False
                continue
        if quote:
            if c == quote[-1]:
                quote = ""
            elif c == "\\" and quote != "'" and nxt:
                out.append("" if (quote, nxt) == ('"', "\n") else c + nxt)
                i += 2
                continue
        elif c == "$" and nxt == "'":
            quote, c, i = "$'", "$'", i + 1  # an ANSI-C string, where a backslash escapes a quote
        elif c in "'\"":
            quote = c
        elif c == "\\" and nxt:
            out.append("" if nxt == "\n" else _ESCAPED + nxt if nxt in ";&|()<>" else c + nxt)
            starts, i = starts and nxt == "\n", i + 2
            continue
        elif c == "#" and starts:
            end = command.find("\n", i)
            i = len(command) if end < 0 else end
            continue
        starts = not quote and c in " \t\n;&|()<>"
        out.append(c)
        i += 1
    return "".join(out)


def shell_tokens(command: str, quoting: bool = False) -> list[str]:
    """The words and punctuation of `command` as bash cuts them, quotes removed; with `quoting`, each word read from
    the text as it stands keeps its quoting (shell_words.Word)."""
    # A newline ends a command like `;` does; inside quotes it only changes text this check never executes.
    text = _mark_escaped_punctuation(command).replace("\n", " ; ")
    lex = shlex.shlex(text, posix=True, punctuation_chars=";&|()<>")
    lex.whitespace_split = True
    lex.commenters = ""  # read above: shlex would end a comment at no line here, and start one inside a word
    toks = shell_words.marked(list(lex), text) if quoting else list(lex)
    # An escaped punctuation character came back as a word of its own, or inside one: it is that word, `\;` (a backslash
    # marks it, so no check reads it as a separator).
    return [t.replace(_ESCAPED, "\\") if _ESCAPED in t else t for t in _join_escaped(toks)]


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
    strings: list[str] = field(default_factory=list)  # here-strings (`<<<`): a shell with no script runs them
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
    stripped, bodies = _heredoc_parts(command)
    return stripped, [body for body, _, shell in bodies if shell]


def _heredoc_parts(command: str) -> tuple[str, list[tuple[str, bool, bool]]]:
    """(`command` without its here-document bodies, each body with whether its delimiter is quoted, so the shell
    expands nothing in it, and whether a shell reads it)."""
    lines = command.split("\n")
    kept: list[str] = []
    bodies: list[tuple[str, bool, bool]] = []
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
            if i == len(lines):  # no delimiter, as in a line whose bodies are gone already: the lines stay commands
                kept += body
                break
            i += 1  # the delimiter line
            quoted = m.group(4) is None or "\\" in m.group(0)
            bodies.append(("\n".join(body), quoted, n == 0 and bool(_SHELL_OPENER.search(line))))
    return "\n".join(kept), bodies


def _substitutions(text: str, body: bool = False) -> list[str] | None:
    """The command of each substitution the tokens keep inside one word: in backticks, anywhere outside single quotes,
    and `$(...)` inside double quotes, or anywhere in a here-document's `body`, where a quote is only text. None when
    one has no end, so the command cannot be read."""
    found, quote, i, starts = [], "", 0, True
    text = text.replace("\\\n", "")
    while i < len(text):
        c, nxt = text[i], text[i + 1 : i + 2]
        if quote in ("'", "$'"):
            i += 2 if c == "\\" and quote == "$'" else 1
            quote = "" if c == "'" else quote
            continue
        if c == "\\":
            i, starts = i + 2, False
            continue
        if c == "`" or (c == "$" and nxt == "(" and (quote or body)):
            end = _substitution_end(text, i + (c == "$"))
            if end is None:
                return None
            found.append(text[i + 1 : end].replace("\\`", "`") if c == "`" else text[i + 2 : end])
            i, starts = end + 1, False
            continue
        if not body and not quote and c == "#" and starts:
            end = text.find("\n", i)
            i = len(text) if end < 0 else end
            continue
        if not body and c == '"':
            quote = "" if quote else '"'
        elif not body and not quote and c == "'":
            quote = "$'" if text[i - 1 : i] == "$" else "'"
        starts = not quote and c in " \t\n;&|()<>"
        i += 1
    return found


def _substitution_end(text: str, i: int) -> int | None:
    """Where the substitution that opens at text[i] (a backtick, or the `(` of `$(`) ends; None when it never does."""
    if text[i] == "`":
        k = i + 1
        while k < len(text) and text[k] != "`":
            k += 2 if text[k] == "\\" else 1
        return k if k < len(text) else None
    depth, quote, k = 0, "", i
    while k < len(text):
        c = text[k]
        if c == "\\" and quote != "'":
            k += 2
            continue
        if quote:
            quote = "" if c == quote else quote
        elif c in "'\"`":
            quote = c
        elif c in "()":
            depth += 1 if c == "(" else -1
            if depth == 0:
                return k
        k += 1
    return None


def _substituted(command: str, depth: int, broken: list[str] | None) -> list[SimpleCommand]:
    """The commands the substitutions in `command` run (_substitutions), each in a child shell whose folder the guard
    does not know: an unread `cd` comes first, so a write or a git command there is judged where it may be anywhere."""
    stripped, bodies = _heredoc_parts(command)
    texts = [_substitutions(stripped)]
    texts += [_substitutions(b, body=True) for b, quoted, _ in bodies if not quoted] + [_substitutions(b) for b, _, shell in bodies if shell]
    if any(t is None for t in texts) and broken is not None:
        broken.append("a command substitution with no end")
    found: list[SimpleCommand] = []
    for text in (t for ts in texts for t in ts or []):
        if depth >= MAX_NESTING:
            if broken is not None:
                broken.append(f"nested more than {MAX_NESTING} levels of command substitutions")
            break
        found.append(SimpleCommand(["cd", "$(...)"], depth=1))
        for sc in simple_commands(text, depth + 1, broken):
            sc.depth += 1
            found.append(sc)
    return found


MAX_NESTING = 3  # levels of `sh -c` and `eval` the shell check follows; a deeper one is a command it cannot read


def simple_commands(command: str, depth: int = 0, broken: list[str] | None = None, *, quoting: bool = False) -> list[SimpleCommand]:
    """Split a command line into simple commands, following `sh -c`, `bash -c`, and `eval` one level at a time.

    A command shlex cannot read (an ANSI-C string `$'it\\'s'`, a here-document with an apostrophe in it) is read again
    with those rewritten; one it still cannot read is added to `broken`, so the caller never takes "nothing parsed"
    for "nothing to deny". With `quoting`, the words of the line's own text keep their quoting, and a loop over literal
    words is written out (shell_words); never those of a here-document, a substitution, or a child shell."""
    read = _read_tokens(command, depth, broken, quoting)
    if read is None:
        return []
    toks, extra = read
    toks = [piece for tok in toks for piece in _pieces(tok)]
    toks = shell_words.unrolled(toks) if quoting and depth == 0 else toks
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
                _redirect(cur, tok, target)
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
    return _nested(out, depth, broken) + extra + _substituted(command, depth, broken)


def _read_tokens(command: str, depth: int, broken: list[str] | None, quoting: bool) -> tuple[list[str], list[SimpleCommand]] | None:
    """(`command`'s tokens, the commands of the here-documents a shell reads when shlex needs them rewritten), or None
    when it cannot be read (simple_commands). Quoting is kept only for a line with no here-document, read as it stands."""
    try:
        return shell_tokens(command, quoting and depth == 0 and not _HEREDOC.search(command)), []
    except ValueError:
        pass
    stripped, bodies = split_heredocs(command)
    try:
        toks = shell_tokens(_plain_ansi_c(stripped))
    except ValueError:
        if broken is not None:
            broken.append(command)
        return None
    extra: list[SimpleCommand] = []
    for body in bodies if depth < MAX_NESTING else []:
        for found in simple_commands(body, depth + 1, broken):
            found.depth += 1  # a shell that reads a here-document is a child shell
            extra.append(found)
    return toks, extra


def _redirect(cur: SimpleCommand, tok: str, target: str) -> None:
    """Add a redirect's target to what `cur` reads or writes: `<>` does both, and a here-string (`<<<`) is text too."""
    if "<" in tok:
        cur.inp.append(target)
    if ">" in tok:
        cur.out.append(target)
    if tok == "<<<":
        cur.strings.append(target)


OPAQUE_ENV = "$ENV_OPAQUE"  # a program in place of env's when the guard cannot read env's options


def _env_split(words: list[str]) -> str | None:
    """The command line `env -S STRING` runs (`--split-string`, a prefix of it, or `S` in a cluster), as shell text
    with STRING in its place: env splits it into words. A STRING with a backslash, which env reads as its own escape,
    and options the guard cannot read, stand for a program the guard cannot read."""
    for k, word in enumerate(words):
        if program_name(word) != "env":
            continue
        end, split, exact = program_options.env_options(words, k + 1)
        if not exact:
            return " ".join([shlex.join(words[: k + 1]), OPAQUE_ENV])
        if split is not None:
            return " ".join([shlex.join(words[: k + 1]), "$ENV_S" if "\\" in split else split, shlex.join(words[end:])])
    return None


def _trap_words(args: list[str]) -> list[str]:
    """`trap`'s action and signals, as bash reads them: its options (`-p`, `-l`, `-P`) end at `--` or at the first word
    that is no option, and that word is the action, whatever it starts with (`'-x; cmd'`)."""
    k = 0
    while k < len(args) and args[k].startswith("-") and args[k] != "-":
        if args[k] == "--":
            k += 1
            break
        if not re.fullmatch(r"-[lpP]+", args[k]):
            break  # no option bash knows: bash reads it as the action
        k += 1
    return args[k:]


OPAQUE_PIPE = "$PIPED_OPAQUE"  # a program in place of text a pipe carries that the guard cannot read exactly


def _shown(feeder: SimpleCommand) -> bool:
    return bool(feeder.strings) or program_name((program_argv(feeder.argv) or [""])[0]) in ("echo", "printf")


# A script operand that is a stream, and the ones that are this shell's stdin, which a here-string or a pipe may fill.
STREAM = re.compile(r"-|/dev/stdin|/dev/fd/\d+|/proc/[^/]+/fd/\d+")
_STDIN = frozenset({"-", "/dev/stdin", "/dev/fd/0", "/proc/self/fd/0"})


def here_script(sc: SimpleCommand) -> str | None:
    """The text a shell, or `source`, runs from its here-string, or None. A shell with no script, or one that names its
    stdin (`bash /dev/stdin`, `bash -`), or `source /dev/stdin` reads it, only while it is the last stdin redirect: a
    later `< file` replaces it. stream_fed and _nested both ask this, so they never disagree."""
    argv = program_argv(sc.argv) or [""]
    name = program_name(argv[0])
    if not sc.strings or sc.inp[-1:] != sc.strings[-1:]:
        return None
    inline, at = shell_operand(name, argv[1:]) if name in SHELLS else (True, None)
    shell = name in SHELLS and not inline and (at is None or argv[1 + at] in _STDIN)
    return sc.strings[-1] if shell or (name in ("source", ".") and argv[1:2] != ["-"] and argv[1:2] and argv[1] in _STDIN) else None


def stream_fed(sc: SimpleCommand) -> bool:
    """Whether a shell or `source` runs code from a stream the line never shows: `. <(...)` and `bash <(...)`, which
    reach here with no file, or a stream operand (`/dev/fd/3`, `/dev/stdin`) no here-string or pipe fills. A pipe's
    text is piped_text's; a file, as `bash x.sh` or `bash < x.sh`, is a script, which no reader here sees."""
    argv = program_argv(sc.argv) or [""]
    name = program_name(argv[0])
    if here_script(sc) is not None:
        return False
    if name in ("source", "."):
        return len(argv) == 1 or bool(STREAM.fullmatch(argv[1]))
    inline, at = shell_operand(name, argv[1:]) if name in SHELLS else (True, None)
    if inline:
        return False
    if at is None or argv[1 + at] in _STDIN:
        return sc.after != "|" and not sc.inp
    return bool(STREAM.fullmatch(argv[1 + at]))


def piped_text(out: list[SimpleCommand], shell: int) -> str | None:
    """The text a pipe feeds the shell `out[shell]`, as it reads it: what `echo` or `printf` before it writes (echo its
    words on one line; printf its format filled with its arguments, again for each group of them). OPAQUE_PIPE for
    text the line shows but the guard cannot follow: any backslash in echo's words (bash's echo keeps it, and the shell
    then reads `mai\\n` as `main`), a printf escape other than `\\n` or a `%b`, which may spell any word, or a program
    between it and the shell. None for a pipe that carries none, such as a download."""
    j = shell - 1
    while j > 0 and out[j].after == "|":
        j -= 1
    argv = program_argv(out[shell - 1].argv)
    if not argv or program_name(argv[0]) not in ("echo", "printf") or out[shell - 1].out:
        return OPAQUE_PIPE if any(_shown(sc) for sc in out[j:shell]) else None
    if program_name(argv[0]) == "echo":
        text = " ".join(w for w in argv[1:] if not re.fullmatch(r"-[neE]+", w))
        return OPAQUE_PIPE if "\\" in text else text  # echo reads a backslash per shell and per -e or -E: no one reading
    fmt, args = (argv[1:2] or [""])[0], argv[2:]
    if re.search(r"\\(?!n)|%(?!s)", fmt) or fmt.startswith("-") or any("\\" in a for a in args):
        return OPAQUE_PIPE  # an escape, a `%%`, a directive with a width or another letter, or an option: any word
    specs = len(re.findall(r"%[a-z]", fmt)) or 1
    groups = [args[j : j + specs] for j in range(0, len(args), specs)] or [[]]
    pieces = re.split(r"%[a-z]", fmt)
    lines = ["".join(p + (group[n] if n < len(group) else "") for n, p in enumerate(pieces)) for group in groups]
    return "".join(lines).replace("\\n", "\n")


def _nested(out: list[SimpleCommand], depth: int, broken: list[str] | None) -> list[SimpleCommand]:
    """`out`, each simple command followed by the commands a shell, `eval`, `trap`, `script -c`, `watch`, `flock`, or
    `env -S` has it run, read one level at a time: a shell with no script runs its here-strings, and the text `echo` or
    `printf` pipes into it."""
    expanded: list[SimpleCommand] = []
    for k, sc in enumerate(out):
        expanded.append(sc)
        argv = program_argv(sc.argv) or [""]
        name = program_name(argv[0])
        flag = next((a for a in argv[1:] if a.lower() in ("-c", "-command")), None) if name in POWERSHELLS else None
        inline, at = shell_operand(name, argv[1:]) if name in SHELLS else (False, None)
        runs = _runs_text(name, argv[1:])
        trapped = _trap_words(argv[1:]) if name == "trap" else []
        if (split := _env_split(sc.argv)) is not None:
            inner, shift = split, sc.depth  # env runs the words it splits in this process
        elif inline and at is not None:
            inner, shift = argv[1 + at], sc.depth + 1  # a child shell: its `cd` ends with it
        elif flag and argv.index(flag) + 1 < len(argv):
            inner, shift = " ".join(argv[argv.index(flag) + 1 :]), sc.depth + 1
        elif (here := here_script(sc)) is not None:
            inner, shift = here, sc.depth + 1
        elif name in SHELLS and (at is None or argv[1 + at] in _STDIN) and not inline and sc.after == "|" and k and (fed := piped_text(out, k)) is not None:
            inner, shift = fed, sc.depth + 1
        elif name == "eval":
            inner, shift = " ".join(argv[1:]), sc.depth  # eval runs in this shell
        elif len(trapped) > 1 and trapped[0] != "-":
            inner, shift = trapped[0], sc.depth  # the shell runs it later, on a signal or at exit
        elif runs is not None:
            inner, shift = runs, sc.depth + 1
        else:
            continue
        if depth >= MAX_NESTING:
            if broken is not None:
                broken.append(f"nested more than {MAX_NESTING} levels of `sh -c` or `eval`")
            continue
        for found in simple_commands(inner, depth + 1, broken):
            found.depth += shift
            expanded.append(found)
    return expanded


# The options of `watch` and `flock` that take the next word as their value, and those of `script`.
_LAUNCH_VALUES = {"watch": frozenset({"-n", "--interval", "-q", "--equexit"}), "flock": frozenset({"-w", "--timeout", "-E", "--conflict-exit-code"})}
_SCRIPT_VALUES = {"-E", "--echo", "-I", "--log-in", "-O", "--log-out", "-B", "--log-io", "-T", "--log-timing", "-m", "--logging-format", "-o", "-t"}


def _script_command(args: list[str]) -> str | None:
    """The text util-linux's `script -c CMD` (`--command`) runs, even after the file, or None; `_runs_text` adds BSD's."""
    for k, a in enumerate(args):
        if a.startswith("--command="):
            return a.split("=", 1)[1]
        if a == "--command" or (a.startswith("-") and not a.startswith("--") and "c" in a[1:]):
            value = a[a.index("c", 1) + 1 :] if a != "--command" else ""
            return value or (args[k + 1] if k + 1 < len(args) else "")
    return None


def _runs_text(name: str, args: list[str]) -> str | None:
    """The shell text `script`, `watch`, or `flock` runs, or None: `script -c CMD` (or BSD's `script FILE CMD...`), `watch [opts] CMD...`
    (which hands its words to `sh -c`), and `flock [opts] LOCK -c CMD` or `flock LOCK CMD...`."""
    if name == "script":
        i = 0
        while i < len(args) and args[i].startswith("-") and args[i] != "--":
            i += 2 if args[i] in _SCRIPT_VALUES else 1
        i += args[i : i + 1] == ["--"]
        found = [r for r in (_script_command(args), shlex.join(args[i + 1 :]) if args[i + 1 :] else None) if r is not None]
        return "\n".join(found) or None
    if name not in _LAUNCH_VALUES:
        return None
    i = 0
    while i < len(args) and args[i].startswith("-") and args[i] != "--":
        i += 2 if args[i] in _LAUNCH_VALUES[name] else 1
    i += args[i : i + 1] == ["--"]
    if name == "flock":
        i += 1  # the lock file or descriptor
        if args[i : i + 1] in (["-c"], ["--command"]):
            return args[i + 1] if i + 1 < len(args) else ""
        return shlex.join(args[i:]) if args[i:] else None
    if not args[i:]:
        return None
    return shlex.join(args[i:]) if {"-x", "--exec"} & set(args[:i]) else " ".join(args[i:])


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


# An environment assignment before a command, as bash reads it: `NAME=value`, `NAME+=value` (it appends), and
# `NAME[sub]=value`. Every check reads one by its name through assignment(), so no spelling slips past one of them.
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def assignment(word: str) -> tuple[str, str] | None:
    """(name, value) of an environment assignment word, or None for any other word. A subscript is balanced, as bash
    reads it (`A[a[0]]=1`), and the value starts right after the first `=` or `+=` that follows it (`X[0]=a]=b` is
    `a]=b`). Failing closed: the guard reads words with their quotes gone, so a quoted bracket can unbalance a
    subscript (`A['[']=1`); a word that starts `NAME[` and holds `]=` or `]+=` anywhere is an assignment, with all that
    follows the first one as its value. The word after it is then checked as the program."""
    m = _NAME.match(word)
    if not m:
        return None
    i = m.end()
    if word[i : i + 1] == "[":
        depth, end = 0, None
        for j in range(i, len(word)):
            depth += {"[": 1, "]": -1}.get(word[j], 0)
            if depth == 0:
                end = j + 1
                break
        if end is None or not (word.startswith("=", end) or word.startswith("+=", end)):
            loose = re.search(r"\]\+?=", word[i:])
            return (m.group(0), word[i + loose.end() :]) if loose else None
        i = end
    if word.startswith("+=", i):
        return m.group(0), word[i + 2 :]
    return (m.group(0), word[i + 1 :]) if word.startswith("=", i) else None


def program_argv(argv: list[str]) -> list[str]:
    """The words after reserved words (`then`, `do`, `{`, `!`), environment assignments, and wrappers such as `sudo`,
    `env`, `command`, `timeout 10`, and `busybox`."""
    i = reserved_lead(argv)
    while i < len(argv):
        word = argv[i]
        if assignment(word):
            i += 1
        elif program_name(word) == "env":
            i, _, exact = program_options.env_options(argv, i + 1)
            if not exact:
                return [OPAQUE_ENV, *argv[i:]]  # a program the guard cannot read: env's options hide it
        elif program_name(word) in _MULTI_CALL and i + 1 < len(argv) and not argv[i + 1].startswith("-"):
            i += 1  # `busybox xargs ...` runs the applet
        elif program_name(word) in WRAPPERS:
            takes = _WRAPPER_VALUE_OPTIONS.get(program_name(word), frozenset())
            i += 1
            while i < len(argv) and (argv[i].startswith("-") or _VALUE_WORD.fullmatch(argv[i])):
                i += 2 if argv[i] in takes else 1
        else:
            break
    return argv[i:]


def reserved_lead(argv: list[str]) -> int:
    """How many of `argv`'s first words are the shell's reserved words, not the command (RESERVED). `coproc NAME {` and
    `function NAME` name what they define, so the name counts too."""
    i = 0
    while i < len(argv) and argv[i] in RESERVED:
        named = argv[i] == "function" or (argv[i] == "coproc" and argv[i + 2 : i + 3] == ["{"])
        i += 2 if named else 1
    return min(i, len(argv))


SEARCHERS = {"grep", "egrep", "fgrep", "rg", "ag", "ack", "cat", "head", "tail", "less", "more", "wc", "awk"}
_AIDD_MODULES = frozenset({"aidd", "aidd.cli", "aidd.__main__"})  # the modules `python -m` runs aidd's command line from


def aidd_runs(argv: list[str]) -> list[list[str]]:
    """The words after each place a simple command runs aidd, through any wrapper: `uvx aidd`, `uv run aidd`, `pipx run
    aidd`, `python -m aidd` (or `-m aidd.cli`, `-maidd`), `xargs aidd`, `script -c 'aidd ...'`. A word naming the aidd
    program (its basename, or the module after `-m`) starts one. A search or an `echo` runs nothing, nor does a plain
    find (shell_words.plain_find): its words name files (`find /opt/aidd`), and what its actions run is read on its own."""
    if not argv or program_name(argv[0]) in SEARCHERS | {"echo", "printf"} or shell_words.plain_find(program_name(argv[0]), argv[1:]):
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
