"""What a secret's value looks like: the patterns that find a key, a token, or a private key in a line of text.

The token shapes follow gitleaks' common rules. They find a known format, never every secret: a check built on them
catches a slip, and a person still keeps secrets out of what they write. `LOOSE_PATTERNS` adds a password in a URL and
a credential assignment, which suits a short text such as a record and would be noisy over a repository's files.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable

MAX_SECRET_LINE = 4096
REDACTED = "<redacted>"
# A line's matches come back in this order. Each part a later part must follow is bounded, so a crafted run, such as
# `eyJ-eyJ-...`, costs a bounded scan from each place a match could start, never the rest of the run.
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("an AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("a Stripe live key", re.compile(r"\b(?:sk|rk)_live_[0-9A-Za-z]{16,99}\b")),
    ("a GitHub token", re.compile(r"\b(?:gh[pousr]_[0-9A-Za-z]{36}|github_pat_[0-9A-Za-z_]{22,255})\b")),
    ("a GitLab token", re.compile(r"\bglpat-[0-9A-Za-z_-]{20,}\b")),
    ("a Slack token", re.compile(r"\bxox[abposr]-[0-9A-Za-z-]{10,250}\b")),
    ("a Slack webhook", re.compile(r"hooks\.slack\.com/(?:services|workflows)/[A-Za-z0-9+/]{20,}")),
    ("an OpenAI or Anthropic key", re.compile(r"\bsk-(?:ant-|proj-|svcacct-|admin-)?[0-9A-Za-z_-]{20,}")),
    ("a Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("an npm token", re.compile(r"\bnpm_[0-9A-Za-z]{36}\b")),
    ("a JSON web token", re.compile(r"\beyJ[0-9A-Za-z_-]{10,1024}\.eyJ[0-9A-Za-z_-]{10,}\.[0-9A-Za-z_-]{10,}")),
    ("a private key", re.compile(r"-----BEGIN (?:[A-Z0-9]{1,20} ){0,3}PRIVATE KEY-----")),
    ("a *_SECRET assignment", re.compile(r"\b[A-Za-z][A-Za-z0-9_]{0,60}_SECRET(?:_KEY)?[ \t]{0,4}[=:][ \t]{0,4}[\"']?(?![$<{%])(?P<secret>[^\s\"'$]{8,200})")),
)
# After the patterns above, in this order. A pattern with a `secret` group hides only that part (the value after a key, a URL's
# password), so a scrubbed line still says what it was about.
LOOSE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # The look-ahead finds the `@` once from the colon, however long the password, and the capped group never runs it again on a
    # retry; the scrub reads on past the cap to the `@` (`_VALUE_CHARS`).
    ("a password in a URL", re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]{1,20}://[^\s:/@]{1,200}:(?![$<{%])(?=[^\s@/]{3,}@)(?P<secret>[^\s@/]{3,200})")),
    (
        "a credential assignment",
        re.compile(
            r"(?i)\b[a-z0-9_]{0,40}(?:password|passwd|pwd|passphrase|api[_-]?key|access[_-]?key|secret|token|auth|credentials?)[ \t]{0,4}[=:][ \t]{0,4}"
            r"[\"']?(?![$<{%*])(?P<secret>[^\s\"']{8,200})"
        ),
    ),
    ("a bearer token", re.compile(r"(?i)\bbearer[ \t]+(?![$<{%])(?P<secret>[A-Za-z0-9._~+/-]{16,}=*)")),
    ("a password on a command line", re.compile(r"\b(?:mysql|mysqldump|mariadb)\b[^\n]{0,200}?[ \t]-p(?![ \t$<{%])(?P<secret>\S{3,})")),
)


# What a match of each strict pattern must contain, so a text without it holds none and the pattern is not searched in it. A pattern
# with no row is always searched. `tests/test_secret_file_scan.py` holds a row for every pattern and finds no match without its text.
_NEEDS: dict[str, tuple[str, ...]] = {
    "an AWS access key id": ("AKIA", "ASIA"),
    "a Stripe live key": ("_live_",),
    "a GitHub token": ("ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_"),
    "a GitLab token": ("glpat-",),
    "a Slack token": ("xox",),
    "a Slack webhook": ("hooks.slack.com/",),
    "an OpenAI or Anthropic key": ("sk-",),
    "a Google API key": ("AIza",),
    "an npm token": ("npm_",),
    "a JSON web token": ("eyJ",),
    "a private key": ("PRIVATE KEY-----",),
    "a *_SECRET assignment": ("_SECRET",),
}


def comparable(text: str) -> str:
    """`text` as the patterns read it: NFKC-normalized, so a fullwidth `ｇｈｐ＿` reads as `ghp_`, and without Unicode's
    format characters (category Cf), so a zero-width space inside a token no longer splits it. ASCII is its own reading
    (NFKC leaves it alone and it has no Cf character), so it is not walked."""
    if text.isascii():
        return text
    return "".join(c for c in unicodedata.normalize("NFKC", text) if unicodedata.category(c) != "Cf")


def secret_types(line: str, *, loose: bool = False) -> list[str]:
    """The types of secret `line` looks like it holds, in pattern order; [] for none. `loose` adds LOOSE_PATTERNS and
    reads the whole text, for a short text such as a record; a repository's line is read to MAX_SECRET_LINE. Either is
    read as `comparable` gives it."""
    text = comparable(line if loose else line[:MAX_SECRET_LINE])
    patterns = SECRET_PATTERNS + (LOOSE_PATTERNS if loose else ())
    return [secret_type for secret_type, rx in patterns if rx.search(text)]


def file_secret_types(text: str) -> list[str]:
    """The types of secret any line of `text` looks like it holds, in the order the lines first show them, as `secret_types`
    finds them one line at a time. Each line is read as `secret_types` reads it (to MAX_SECRET_LINE, as `comparable` gives it),
    then the lines are searched once, joined by a line break: no pattern's match includes a line break or reaches past a line's
    end differently from the joined text's, so a text in which the patterns find nothing holds nothing on any line. A pattern is
    searched only in a text that holds what its match must (`_NEEDS`). Only a text in which they find something is read line by line."""
    lines = [comparable(line[:MAX_SECRET_LINE]) for line in text.splitlines()]
    joined = "\n".join(lines)
    if not any(rx.search(joined) for name, rx in SECRET_PATTERNS if (needs := _NEEDS.get(name)) is None or any(lit in joined for lit in needs)):
        return []
    shapes: list[str] = []
    for line in lines:
        shapes += [name for name, rx in SECRET_PATTERNS if name not in shapes and rx.search(line)]
    return shapes


# A private key's whole block, from its header to its footer or the end of the text.
_PRIVATE_KEY_BLOCK = re.compile(r"-----BEGIN (?:[A-Z0-9]{1,20} ){0,3}PRIVATE KEY-----.*?(?:-----END (?:[A-Z0-9]{1,20} ){0,3}PRIVATE KEY-----|\Z)", re.S)


# The characters that go on a secret's value after its pattern's capped match, by pattern. A pattern's cap bounds the detection of
# hostile text; the value a person wrote has no such cap, so the redaction reads on while the next character still belongs to it.
_VALUE_CHARS: dict[str, Callable[[str], bool]] = {
    "a *_SECRET assignment": lambda c: not c.isspace() and c not in "\"'$",
    "a credential assignment": lambda c: not c.isspace() and c not in "\"'",
    "a bearer token": lambda c: c.isascii() and (c.isalnum() or c in "._~+/=-"),
    "a password on a command line": lambda c: not c.isspace(),
    "a password in a URL": lambda c: not c.isspace() and c not in "@/",
}


def _spans(text: str, name: str, rx: re.Pattern[str]) -> list[tuple[int, int]]:
    """The places in `text` that `rx` finds a secret in: the `secret` group where there is one, read on to the end of the value, else
    the whole match. A match that starts inside what an earlier match already read on over is not read on again: its value is
    the same run, which ends where that read stopped (every `_VALUE_CHARS` predicate holds for the whole of its pattern's `secret`
    group), so each character is read once and a run of `password=password=...` costs time in its length, not its square."""
    out = []
    reach = 0  # where the reads so far stopped: the furthest end of a span
    for found in rx.finditer(text):
        if "secret" not in rx.groupindex or found.start("secret") < 0:
            out.append(found.span())
            reach = max(reach, found.end())
            continue
        start, end = found.span("secret")
        if start >= reach:
            belongs = _VALUE_CHARS[name]
            while end < len(text) and belongs(text[end]):
                end += 1
        out.append((start, end))
        reach = max(reach, end)
    return out


def _hidden(text: str) -> str:
    """`text` with each secret the patterns find in it replaced by REDACTED, whole, whatever the cap of the pattern that found it."""
    text = _PRIVATE_KEY_BLOCK.sub(REDACTED, text)
    for name, rx in SECRET_PATTERNS + LOOSE_PATTERNS:
        out, pos = [], 0
        for start, end in _spans(text, name, rx):
            if start >= pos:
                out += [text[pos:start], REDACTED]
                pos = end
            elif end > pos:  # inside what an earlier match already read on over
                pos = end
        text = "".join([*out, text[pos:]])
    return text


def scrubbed(text: str) -> str:
    """`text` with every secret `secret_types(..., loose=True)` finds in it hidden, so that function finds none in the result.
    The text is kept as it was where it holds none. A secret written to hide from the patterns (a fullwidth letter, a
    zero-width space inside a token) is hidden from `comparable`'s reading of the text, which then replaces the original."""
    out = _hidden(text)
    return out if not secret_types(out, loose=True) else _hidden(comparable(text))
