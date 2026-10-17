"""Documents aidd reads: YAML in a strict subset (kernel.strict_yaml), bounded in size and depth; `---` front matter;
Markdown sections; and the checks every document gets, such as control characters."""

from __future__ import annotations

import re

from aidd.kernel import strict_yaml

# Front matter: YAML between a `---` line at the very top and the next `---` line. The text between may be empty.
FRONT_MATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)(?:\r?\n)?^---[ \t]*(?:\r?\n|\Z)", re.S | re.M)


# The most a Spec, Epic, Initiative, Proposal, or linked object file may hold, front matter and body together. A person
# reads and approves all of it; a file far past this is not something anyone reads.
MAX_DOCUMENT_BYTES = 256 * 1024


MAX_YAML_DEPTH = strict_yaml.MAX_DEPTH


class DocumentError(ValueError):
    pass


def parse_yaml(text: str, what: str) -> dict:
    """A YAML document in aidd's strict subset as JSON-shaped data: a mapping at the top. Anything outside the subset
    is a DocumentError naming `what` and the line, never a crash. CRLF line endings read as LF, as git may write them."""
    try:
        return strict_yaml.load(text.replace("\r\n", "\n"))
    except strict_yaml.YamlError as exc:
        raise DocumentError(f"{what}: {exc}") from None


def _front_matter(text: str, what: str) -> tuple[dict, str]:
    if len(text) > MAX_DOCUMENT_BYTES // 4 and (size := len(text.encode("utf-8", errors="replace"))) > MAX_DOCUMENT_BYTES:
        raise DocumentError(f"{what}: {size} bytes; a document holds at most {MAX_DOCUMENT_BYTES}: split it, or link the detail")
    m = FRONT_MATTER.match(text.lstrip("﻿"))
    if not m:
        raise DocumentError(f"{what}: missing YAML front matter between `---` lines at the top of the file")
    return parse_yaml(m.group(1), what), text[m.end() :]


def split_front_matter(text: str, what: str = "document") -> tuple[dict, str]:
    """The front matter and the body. A document larger than MAX_DOCUMENT_BYTES, or front matter outside aidd's YAML
    subset, is a DocumentError."""
    return _front_matter(text, what)


_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def control_characters(text: str) -> str | None:
    """Where the first control character other than tab, newline, or carriage return is, for an error message."""
    m = _CONTROL.search(text)
    return f"control character {m.group(0)!r} at line {text.count(chr(10), 0, m.start()) + 1}" if m else None


def fmt_number(x: float) -> str:
    """A number as a person reads it: every digit, at most two decimals, no trailing zeros."""
    return f"{x:.2f}".rstrip("0").rstrip(".")


_HTML_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.S)


_HEADING = re.compile(r"^##[ \t]+(.+?)[ \t]*$", re.M)


def markdown_section(text: str, heading: str, *, fences: bool = True) -> str:
    """The body of a `## <heading>` section, with HTML comments and a Markdown table's skeleton removed (and code fence
    lines, unless `fences`): empty when the heading is absent or holds only the template's guidance, so a heading nobody
    filled in counts as missing."""
    matches = list(_HEADING.finditer(text))
    for i, m in enumerate(matches):
        if m.group(1).strip().lower() != heading.lower():
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        # A table nobody filled in is rules and empty cells, not prose.
        lines = [ln for ln in _HTML_COMMENT.sub("", text[m.end() : end]).splitlines() if ln.strip() and not re.fullmatch(r"\|[\s|:-]*\|", ln.strip())]
        return "\n".join(ln for ln in lines if fences or not ln.strip().startswith("```")).strip()
    return ""


def raw_section(text: str, title: str) -> str:
    """The body of one H2 section, up to the next H2."""
    m = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return m.group(1) if m else ""
