"""What a secret's value looks like: the patterns that find a key, a token, or a private key in a line of text.

The token shapes follow gitleaks' common rules. They find a known format, never every secret: a check built on them
catches a slip, and a person still keeps secrets out of what they write. `LOOSE_PATTERNS` adds a password in a URL and
a credential assignment, which suits a short text such as a record and would be noisy over a repository's files.
"""

from __future__ import annotations

import re
import unicodedata

MAX_SECRET_LINE = 4096
# A line's matches come back in this order.
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
    ("a JSON web token", re.compile(r"\beyJ[0-9A-Za-z_-]{10,}\.eyJ[0-9A-Za-z_-]{10,}\.[0-9A-Za-z_-]{10,}")),
    ("a private key", re.compile(r"-----BEGIN (?:[A-Z0-9]{1,20} ){0,3}PRIVATE KEY-----")),
    ("a *_SECRET assignment", re.compile(r"\b[A-Za-z][A-Za-z0-9_]{0,60}_SECRET(?:_KEY)?[ \t]{0,4}[=:][ \t]{0,4}[\"']?(?![$<{%])[^\s\"'$]{8,200}")),
)
# After the patterns above, in this order.
LOOSE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("a password in a URL", re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]{1,20}://[^\s:/@]{1,200}:(?![$<{%])[^\s@/]{3,200}@")),
    (
        "a credential assignment",
        re.compile(
            r"(?i)\b[a-z0-9_]{0,40}(?:password|passwd|pwd|passphrase|api[_-]?key|access[_-]?key|secret|token|auth|credentials?)[ \t]{0,4}[=:][ \t]{0,4}"
            r"[\"']?(?![$<{%*])[^\s\"']{8,200}"
        ),
    ),
    ("a bearer token", re.compile(r"(?i)\bbearer[ \t]+(?![$<{%])[A-Za-z0-9._~+/-]{16,}=*")),
    ("a password on a command line", re.compile(r"\b(?:mysql|mysqldump|mariadb)\b[^\n]{0,200}?[ \t]-p(?![ \t$<{%])\S{3,}")),
)


def _comparable(text: str) -> str:
    """`text` as the patterns read it: NFKC-normalized, so a fullwidth `ｇｈｐ＿` reads as `ghp_`, and without Unicode's
    format characters (category Cf), so a zero-width space inside a token no longer splits it."""
    return "".join(c for c in unicodedata.normalize("NFKC", text) if unicodedata.category(c) != "Cf")


def secret_types(line: str, *, loose: bool = False) -> list[str]:
    """The types of secret `line` looks like it holds, in pattern order; [] for none. `loose` adds LOOSE_PATTERNS and
    reads the whole text, for a short text such as a record; a repository's line is read to MAX_SECRET_LINE. Either is
    read as `_comparable` gives it."""
    text = _comparable(line if loose else line[:MAX_SECRET_LINE])
    patterns = SECRET_PATTERNS + (LOOSE_PATTERNS if loose else ())
    return [secret_type for secret_type, rx in patterns if rx.search(text)]
