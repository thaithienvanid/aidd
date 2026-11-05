"""Shell text, read the way the command patterns need it: a command line split into simple commands, its words, and the
commands a simple command runs inside itself (`wrapped`), which include the command read by its program's base name.

A pattern matches one simple command as typed, so a wrapper hides what it runs: `sudo git push --force origin main`,
`bash -c '...'`, `(...)`, a loop body, `$(...)`, or a prefix such as `timeout 30` or `xargs`. `wrapped` lists the
commands inside, so `aidd risk --command` matches them too. That only adds matches, so it never lowers a level.

It reads the wrappers an agent uses by habit or by accident and stops there. It does not read `doas`, `su -c`, other
shells, here-strings, a pipe into `sh`, or process substitution. It advises a cooperative agent and is no guard against
one that hides a command on purpose: the harness's ask rules and branch protection are the hard stops (SECURITY.md).
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Sequence

SETTING = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*")  # a setting before the program, such as `FOO=1`
# Words a command may follow: a control keyword, or a prefix that runs the rest as it is. A prefix's options that take a
# value are listed, the others take none (`time -p`, `nice -5`, `exec -a name`).
_KEYWORDS = {"if", "then", "else", "elif", "do", "while", "until", "!"}
_PREFIXES = {
    "time": {"-o", "--output", "-f", "--format"},
    "command": set(),
    "exec": {"-a"},
    "nohup": set(),
    "builtin": set(),
    "nice": {"-n", "--adjustment"},
}
_SHELLS = {"bash", "sh", "zsh", "dash"}
_SHELL_VALUE = {"--rcfile", "--init-file"}
# The options that take a value, by tool: the next word, or the rest of a short one (`-uroot`), also in a run (`-nu root`).
_SUDO_VALUE = {
    "-u",
    "--user",
    "-g",
    "--group",
    "-h",
    "--host",
    "-p",
    "--prompt",
    "-C",
    "--close-from",
    "-D",
    "--chdir",
    "-R",
    "--chroot",
    "-T",
    "--command-timeout",
}
_ENV_VALUE = {"-u", "--unset", "-C", "--chdir"}
_TIMEOUT_VALUE = {"-s", "--signal", "-k", "--kill-after"}
_XARGS_VALUE = {"-a", "-d", "-E", "-I", "-L", "-l", "-n", "-P", "-s", "--arg-file", "--delimiter", "--max-args", "--max-lines", "--max-procs", "--max-chars"}
_DEPTH = 5


def split(line: str) -> list[str]:
    """The simple commands of a command line, split at `&&`, `||`, `;`, `|`, `|&`, a single `&`, and new lines outside
    quotes. A `&` inside `2>&1`, `&>`, or `>&` is a redirection, and a backslash before a new line joins the two lines."""
    parts, buf, quote, i = [], [], "", 0
    while i < len(line):
        c = line[i]
        nxt = line[i + 1] if i + 1 < len(line) else ""
        if quote == "'":
            buf.append(c)
            quote = "" if c == "'" else quote
        elif c == "\\" and nxt == "\n":
            i += 1  # a continuation: the shell joins the lines
        elif quote:
            buf.append(c)
            if c == quote:
                quote = ""
            elif c == "\\" and i + 1 < len(line):
                buf.append(nxt)
                i += 1
        elif c in "'\"":
            quote = c
            buf.append(c)
        elif c == "\\" and nxt:
            buf += [c, nxt]
            i += 1
        elif line.startswith(("&&", "||"), i):
            parts.append("".join(buf))
            buf = []
            i += 1
        elif c in ";|\n" or (c == "&" and (buf[-1] if buf else "") not in ("<", ">") and nxt != ">"):
            parts.append("".join(buf))
            buf = []
            i += 1 if c == "|" and nxt == "&" else 0
        else:
            buf.append(c)
        i += 1
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


class Word(str):
    """A word of a command with what quoting could not tell from its text: whether the shell expands it, with a `$` or a
    backtick that is neither in single quotes nor escaped. Such a word is not what it reads."""

    expands: bool

    def __new__(cls, text: str, expands: bool = False) -> Word:
        word = super().__new__(cls, text)
        word.expands = expands
        return word


def tokens(text: str) -> list[Word]:
    """The words of a simple command, as a POSIX shell splits them, with a setting before the program (`A=1 gh api`)
    dropped. A quote that never closes is no shell command, so the words are split at spaces then, which only reads more.
    A `$'...'` word, a variable, and a substitution expand."""
    words: list[Word] = []
    buf: list[str] = []
    quote, started, expands, i = "", False, False, 0
    while i < len(text):
        c = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if quote == "'":
            quote = "" if c == "'" else quote
            buf += [] if c == "'" else [c]
        elif c == "\\" and nxt and (not quote or nxt in '"\\$`\n'):
            buf += [] if nxt == "\n" else [nxt]
            started = True
            i += 1
        elif quote == '"' and c == '"':
            quote = ""
        elif not quote and c in " \t\n":
            if started:
                words.append(Word("".join(buf), expands))
            buf, started, expands = [], False, False
        elif not quote and c in "'\"":
            quote, started = c, True
        else:
            expands = expands or c in "$`"
            buf.append(c)
            started = True
        i += 1
    if quote:
        words = [Word(w, "$" in w or "`" in w) for w in text.split()]
    elif started:
        words.append(Word("".join(buf), expands))
    while words and SETTING.fullmatch(words[0]):
        words.pop(0)
    return words


def _join(words: Sequence[str]) -> str:
    """Words as one command that `tokens` reads back, an expanding word still expanding: it goes in double quotes, with
    a quote or a backslash escaped, whatever it holds, since a quote or a space would end it unquoted."""
    return " ".join('"' + re.sub(r'(["\\])', r"\\\1", w) + '"' if getattr(w, "expands", False) else shlex.quote(w) for w in words)


def _substitutions(text: str) -> list[str]:
    """What `$(...)` and backticks hold in `text`, outside single quotes. A pipe or `;` inside already split the part, so
    one with no closing bracket holds the rest."""
    out: list[str] = []
    quote, i = "", 0
    while i < len(text):
        c = text[i]
        if quote == "'":
            quote = "" if c == "'" else quote
        elif c == "\\":
            i += 1
        elif c == '"':
            quote = "" if quote else '"'
        elif c == "'" and not quote:
            quote = "'"
        elif text.startswith("$(", i):
            depth, j = 1, i + 2
            while j < len(text) and depth:
                depth += (text[j] == "(") - (text[j] == ")")
                j += 1
            out.append(text[i + 2 : j - 1 if depth == 0 else j])
            i = j - 1
        elif c == "`":
            end = text.find("`", i + 1)
            end = len(text) if end < 0 else end
            out.append(text[i + 1 : end])
            i = end
        i += 1
    return out


def _skip_options(rest: list[Word], takes_value: set[str], *, settings: bool = False) -> list[Word]:
    """`rest` without the options before the command. A short option may carry its value or sit in a run (`-nu root`),
    a long one takes its value after a space or `=`, `--` ends the options, and `settings` also drops `NAME=value`."""
    rest = list(rest)
    while rest and ((rest[0].startswith("-") and rest[0] != "-") or (settings and SETTING.fullmatch(rest[0]))):
        word = rest.pop(0)
        if word == "--":
            break
        if word.startswith("--"):
            if "=" not in word and word in takes_value and rest:
                rest.pop(0)
        else:
            for pos, char in enumerate(word[1:], 1):
                if "-" + char in takes_value:
                    if not word[pos + 1 :] and rest:
                        rest.pop(0)
                    break
    return rest


def _script(rest: list[Word]) -> str | None:
    """The script a shell runs for `-c`: the first word that is no option, after options before or after `-c` (`-lc`,
    `-c -e`, `-c --`), or None when `-c` is not among them."""
    i, has_c = 0, False
    while i < len(rest):
        word = rest[i]
        if word == "--":
            i += 1
            break
        if len(word) < 2 or word[0] not in "-+":
            break
        if word.startswith("--"):
            i += 2 if word in _SHELL_VALUE else 1
            continue
        has_c = has_c or (word[0] == "-" and "c" in word)
        i += 2 if word[-1] in "oO" else 1  # `-o name` and `-O name` take a word
    return str(rest[i]) if has_c and i < len(rest) else None


def _env_rest(rest: list[Word]) -> list[Word]:
    """What `env` runs: after its options and settings, and `-S`/`--split-string`, which hands over a string to split."""
    for i, word in enumerate(rest):
        if word in ("-S", "--split-string") and i + 1 < len(rest):
            return tokens(str(rest[i + 1])) + rest[i + 2 :]
        if word.startswith("--split-string="):
            return tokens(word.partition("=")[2]) + rest[i + 1 :]
        if word.startswith("-S") and not word.startswith("--"):
            return tokens(word[2:]) + rest[i + 1 :]
    return _skip_options(rest, _ENV_VALUE, settings=True)


def _inner(part: str) -> list[str]:
    """The commands one simple command runs directly: its text inside `(...)` or `{ ...; }`, or what it hands to the
    command after a keyword, a prefix, `env`, `sudo`, `timeout`, `xargs`, `eval`, or a shell's `-c`."""
    text = part.strip()
    bare = text.lstrip("({ ").rstrip(")} ") if text[:1] in ("(", "{") else text
    out = [bare] if bare and bare != text else []
    words = tokens(bare or text)
    if not words:
        return out
    program, rest = words[0].rsplit("/", 1)[-1], words[1:]
    if "/" in words[0].rstrip("/") and program:
        out.append(_join([program, *words[1:]]))  # a program by its path (`./bin/gh`, `~/bin/gh`) is read by its name
    if program in _KEYWORDS:
        pass
    elif program in _PREFIXES:
        rest = _skip_options(rest, _PREFIXES[program])
    elif program == "env":
        rest = _env_rest(rest)
    elif program == "sudo":
        rest = _skip_options(rest, _SUDO_VALUE)
    elif program == "timeout":
        rest = _skip_options(rest, _TIMEOUT_VALUE)[1:]  # the duration
    elif program == "xargs":
        rest = _skip_options(rest, _XARGS_VALUE)
    elif program == "eval":
        return out + split(" ".join(rest))
    elif program in _SHELLS:
        script = _script(rest)
        return out + (split(script) if script is not None else [])
    else:
        return out
    return out + ([_join(rest)] if rest else [])


def wrapped(part: str, depth: int = _DEPTH) -> list[str]:
    """Every command a simple command runs inside itself, however deep, each as a simple command, without `part`: for
    `time sudo -nu root bash -c 'a && b'` it is `sudo -nu root bash -c ...`, `bash -c ...`, `a`, and `b`. It reads
    `$(...)` and backticks too, outside single quotes."""
    if depth < 1:
        return []
    found: list[str] = []
    for sub in _substitutions(part):
        for command in split(sub):
            found += [command, *wrapped(command, depth - 1)]
    for command in _inner(part):
        found += [command, *wrapped(command, depth - 1)]
    return list(dict.fromkeys(c for c in found if c.strip() and c != part))


# A redirection operator, read only where it stands unquoted, with a file descriptor or `&` written just before it.
_OPERATOR = re.compile(r"<<<|<<-?|<>|<&|<|>>|>&|>\||>")


def shell_words(command: str) -> list[tuple[str, bool]]:
    """The words of a simple command as the shell reads them, each with whether it is a redirection operator: `<`, `>`,
    `>>`, `>|`, `<>`, `<&`, `>&`, `<<`, or `<<<`, unquoted, with a file descriptor or `&` just before it (`2>`, `&>`). A
    quoted or escaped `>` is a word. A quote that never closes holds the rest of the command."""
    out: list[tuple[str, bool]] = []
    buf: list[str] = []
    quote, started, plain, i = "", False, True, 0  # `plain`: nothing quoted or escaped in the word so far
    while i < len(command):
        c, nxt = command[i], command[i + 1 : i + 2]
        if quote and c == quote:
            quote = ""
        elif quote == '"' and c == "\\" and nxt and nxt in '"\\$`':
            buf.append(nxt)
            i += 1
        elif quote:
            buf.append(c)
        elif c == "\\" and nxt:
            buf.append(nxt)
            started, plain, i = True, False, i + 1
        elif c in "'\"":
            quote, started, plain = c, True, False
        elif c in " \t\n":
            out += [("".join(buf), False)] if started else []
            buf, started, plain = [], False, True
        elif c in "<>":
            word = "".join(buf)
            fd = word if started and plain and (word.isdigit() or word == "&") else ""
            out += [(word, False)] if started and not fd else []
            op = _OPERATOR.match(command, i).group()  # type: ignore[union-attr]
            out.append((fd + op, True))
            buf, started, plain, i = [], False, True, i + len(op) - 1
        else:
            buf.append(c)
            started = True
        i += 1
    return out + ([("".join(buf), False)] if started else [])


def without_redirections(call: str) -> str:
    """The simple command without its redirections, such as `2>&1`, `>/dev/null`, or `<file`, and their targets."""
    kept, words = [], shell_words(call)
    while words:
        word, operator = words.pop(0)
        if operator:
            if words and not words[0][1]:
                words.pop(0)  # the redirection's target, never a word of the command
            continue
        kept.append(word)
    return shlex.join(kept)
