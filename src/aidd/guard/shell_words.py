"""How bash quotes each word of a command line, and what that lets the checks read exactly.

The reader (shell_parser) drops quotes, as shlex does, so on its own it cannot tell `'*'` from `*`. A word read from the
line's own text also keeps its quoting here: a Word holds one letter per character, `u` for unquoted, `s` for literal
(single quotes, a backslash escape, a value the guard put in), and `d` for inside double quotes, where `$` and a
backtick still expand. Any string made from a Word (a slice, a join, a replace) is a plain str again, which the checks
read as unquoted, failing closed. So no quoting crosses into another word, a child shell, or text a program builds.

From the quoting come two facts. `may_split`: the shell may turn the word into other words, or none, an option among
them (an unquoted glob, brace, tilde, or expansion). `literal`: the shell passes the word exactly as written. A quoted
expansion (`"$f"`) is one word whose value the guard does not know, and that value may start with `-`.

`unrolled` reads a `for` loop over literal words as its body once for each value, when nothing on the line can change
the loop's variable, so each write and each git command in it is judged on the value it gets.
"""

from __future__ import annotations

import re

_PUNCTUATION = ";&|()<>"
_WHITESPACE = " \t\r\n"
# The characters that make an unquoted word more words, other words, or none: a glob, a brace, a tilde, an expansion.
_SPECIAL = frozenset("*?[{~$`")
_SPLITS = re.compile(r"[*?\[{~$`]")  # the same, for a plain str whose quoting the guard does not know


class Word(str):
    """A word with how bash quotes each of its characters (the module docstring): `quoting` has one letter for each."""

    quoting: str

    def __new__(cls, text: str, quoting: str) -> Word:
        word = super().__new__(cls, text)
        word.quoting = quoting
        return word


def may_split(word: str) -> bool:
    """Whether the shell may turn `word` into other words, or none, an option among them (`-name *` with a file named
    `-delete`, `-b $MSG`): an unquoted glob, brace, tilde, or expansion. A word whose quoting the guard does not know
    counts with any of them, quoted or not."""
    if isinstance(word, Word):
        return any(q == "u" and c in _SPECIAL for c, q in zip(word, word.quoting, strict=True))
    return bool(_SPLITS.search(word))


def literal(word: str) -> bool:
    """Whether the shell passes `word` exactly as written: it splits into nothing and expands nothing, so a quoted
    `'*.py'` is literal, and `"$f"`, one word with a value the guard does not know, is not."""
    if isinstance(word, Word):
        return not any((q == "u" and c in _SPECIAL) or (q == "d" and c in "$`") for c, q in zip(word, word.quoting, strict=True))
    return not _SPLITS.search(word)


def literal_prefix(word: str) -> str:
    """The start of `word` the shell passes as written, up to its first expansion, glob, or brace."""
    if not isinstance(word, Word):
        return word[: m.start()] if (m := _SPLITS.search(word)) else word
    for k, (c, q) in enumerate(zip(word, word.quoting, strict=True)):
        if (q == "u" and c in _SPECIAL) or (q == "d" and c in "$`"):
            return word[:k]
    return str(word)


def quoted_tokens(text: str) -> list[tuple[str, str]] | None:
    """The words of `text` as shlex reads them in POSIX mode, splitting on whitespace with `;&|()<>` as punctuation,
    each with its quoting (the module docstring); None where shlex fails (an open quote, a trailing backslash). Inside
    double quotes, as shlex reads it, a backslash escapes only `"` and itself, and stays before any other character."""
    out: list[tuple[str, str]] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] in _WHITESPACE:
            i += 1
            continue
        if text[i] in _PUNCTUATION:
            j = i
            while j < n and text[j] in _PUNCTUATION:
                j += 1
            out.append((text[i:j], "u" * (j - i)))
            i = j
            continue
        word = _quoted_word(text, i)
        if word is None:
            return None
        chars, marks, i = word
        out.append(("".join(chars), "".join(marks)))
    return out


def _quoted_word(text: str, i: int) -> tuple[list[str], list[str], int] | None:
    """The word that starts at text[i]: (its characters, their quoting, where it ends), or None where shlex fails."""
    chars: list[str] = []
    marks: list[str] = []
    n = len(text)
    while i < n and text[i] not in _WHITESPACE and text[i] not in _PUNCTUATION:
        c = text[i]
        if c == "\\":
            if i + 1 >= n:
                return None
            chars.append(text[i + 1])
            marks.append("s")
            i += 2
        elif c == "'":
            end = text.find("'", i + 1)
            if end < 0:
                return None
            chars += text[i + 1 : end]
            marks += "s" * (end - i - 1)
            i = end + 1
        elif c == '"':
            i += 1
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    kept = text[i + 1] in '\\"'
                    chars += [text[i + 1]] if kept else ["\\", text[i + 1]]
                    marks += ["s"] if kept else ["d", "d"]
                    i += 2
                    continue
                if text[i] == "\\":
                    return None
                chars.append(text[i])
                marks.append("d")
                i += 1
            if i >= n:
                return None
            i += 1
        else:
            chars.append(c)
            marks.append("u")
            i += 1
    return chars, marks, i


def marked(tokens: list[str], text: str) -> list[str]:
    """`tokens`, which shlex read from `text`, as Words with their quoting, when this module reads the same words from
    it; else `tokens` as they are, whose quoting the checks then do not know."""
    found = quoted_tokens(text)
    if found is None or [t for t, _ in found] != tokens:
        return tokens
    return [Word(t, q) for t, q in found]


# Loops the guard unrolls: at most this many values, and this many words once unrolled.
_MOST_VALUES = 16
_MOST_WORDS = 4096
# What may set a variable, or run code that does, in a way the unroll does not follow: builtins that assign by name,
# the shell's other loops and blocks (which the unroll would end at the wrong `done`), and arithmetic.
_CHANGES_VARIABLES = frozenset(
    {"read", "mapfile", "readarray", "getopts", "declare", "typeset", "local", "export", "readonly", "unset", "let", "eval"}
    | {"source", "set", "select", "trap", "alias", "shopt", "enable", "coproc", "function", "wait", "fc", "bind", "hash"}
    | {"for", "while", "until", "case", "esac", "[[", "]]", "do", "done"}
)
# A loop's variable in lower case, as a program's own environment variables and bash's specials never are (`PATH`,
# `GIT_DIR`, `IFS`, `RANDOM`), with no leading `_` (bash sets `$_` after each command), and none of the names zsh ties
# to one (`path` is PATH there).
_NAME = re.compile(r"[a-z][a-z0-9_]*")
_TIED = frozenset({"path", "cdpath", "fpath", "manpath", "mailpath", "module_path", "psvar", "fignore", "watch", "histchars", "argv"})
_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\[.*)?\+?=", re.S)
_STARTS = frozenset({";", "&&", "||", "&"})  # what may come before `for`, or after `done`: a plain list of commands
_COMMAND_STARTS = _STARTS | {"|", "|&", "do", "then", "else", "elif", "if", "{", "!", "command", "builtin", "exec", "time"}


def unrolled(tokens: list[str]) -> list[str]:
    """`tokens` with a `for NAME in WORDS; do BODY; done` loop written out as BODY once for each word, `"$NAME"` and
    `"${NAME}"` in it replaced by the word as literal text. Only for a loop over 1 to _MOST_VALUES literal words, on a
    line with no other loop, no group, no expansion but those, nothing in _CHANGES_VARIABLES, `printf` with no `-v`,
    and no assignment to NAME or to an array: then NAME holds each word in turn, and nothing else, while BODY runs.
    Any other line comes back as it is, and its `$NAME` counts as a value the guard does not know."""
    if tokens.count("for") != 1:
        return tokens
    at = tokens.index("for")
    loop = _loop(tokens, at)
    if loop is None:
        return tokens
    name, values, body, end = loop
    rest = tokens[:at] + body + tokens[end:]
    if not _plain_line(rest, name):
        return tokens
    out = tokens[:at] + [word for value in values for word in (_put_in(w, name, value) for w in body)] + tokens[end:]
    return out if len(out) <= _MOST_WORDS else tokens


def _loop(tokens: list[str], at: int) -> tuple[str, list[str], list[str], int] | None:
    """(the loop's variable, its values, its body with the separator that ends it, where the words after `done` start)
    for the `for` at tokens[at], or None for a loop the guard does not unroll."""
    name = tokens[at + 1] if at + 1 < len(tokens) else ""
    if (at and tokens[at - 1] not in _STARTS) or tokens[at + 2 : at + 3] != ["in"] or not _NAME.fullmatch(name) or name in _TIED:
        return None
    k = at + 3
    while k < len(tokens) and tokens[k] not in _PUNCTUATION_WORDS:
        k += 1
    values = tokens[at + 3 : k]
    while k < len(tokens) and tokens[k] == ";":
        k += 1
    if not 1 <= len(values) <= _MOST_VALUES or not all(isinstance(v, Word) and literal(v) for v in values) or tokens[k : k + 1] != ["do"]:
        return None
    done = next((j for j in range(k + 2, len(tokens)) if tokens[j] == "done" and tokens[j - 1] in (";", "&")), None)
    if done is None or (done + 1 < len(tokens) and tokens[done + 1] not in _STARTS):
        return None
    return tokens[at + 1], values, tokens[k + 1 : done], done + 1


_PUNCTUATION_WORDS = frozenset({";", "&", "&&", "|", "||", "(", ")", "<", ">", ">>", "<<", "<<<", "<&", ">&", "<>", ">|", "&>", "|&"})


def rebinds(words: list[str]) -> bool:
    """Whether a line's `words` hold what may set a variable by name, or run code that does: a builtin or a loop in
    _CHANGES_VARIABLES, `printf -v`, a group, or `.` where a command starts. Then a value the line sets plainly may
    change before it is used."""
    if any(w in _CHANGES_VARIABLES or (set(w) & set("()") and set(w) <= set(_PUNCTUATION)) for w in words):
        return True
    if any(w == "." and (k == 0 or words[k - 1] in _COMMAND_STARTS) for k, w in enumerate(words)):
        return True  # `.` runs a file where a command starts; elsewhere it is a folder
    return "printf" in words and any(w.startswith("-v") for w in words)


def _plain_line(words: list[str], name: str) -> bool:
    """Whether nothing in `words` (the line without the loop's header) can change `name`, or the code that runs."""
    if rebinds(words):
        return False
    for w in words:
        m = _ASSIGNMENT.match(w)
        if m and (w.startswith(f"{name}=") or w.startswith(f"{name}+=") or "[" in m.group(0)):
            return False
        if ("$" in w or "`" in w) and not _only_refs(w, name):
            return False
    return True


def _refs(name: str) -> re.Pattern:
    return re.compile(r"\$(?:\{" + re.escape(name) + r"\}|" + re.escape(name) + r"(?![A-Za-z0-9_]))")


def _only_refs(word: str, name: str) -> bool:
    """Whether each `$` and backtick in `word` that the shell reads is part of `"$name"` or `"${name}"`, wholly inside
    double quotes; a literal one (quoted, escaped) is text."""
    if not isinstance(word, Word):
        return False
    spans = [range(m.start(), m.end()) for m in _refs(name).finditer(word) if set(word.quoting[m.start() : m.end()]) == {"d"}]
    return all(q == "s" or any(k in r for r in spans) for k, (c, q) in enumerate(zip(word, word.quoting, strict=True)) if c in "$`")


def _put_in(word: str, name: str, value: str) -> str:
    """`word` with each double-quoted `$name` or `${name}` replaced by `value`, as literal text."""
    if not isinstance(word, Word) or "$" not in word:
        return word
    text, quoting, k = "", "", 0
    for m in _refs(name).finditer(word):
        if set(word.quoting[m.start() : m.end()]) != {"d"}:
            continue
        text += word[k : m.start()] + value
        quoting += word.quoting[k : m.start()] + "s" * len(value)
        k = m.end()
    return Word(text + word[k:], quoting + word.quoting[k:])
