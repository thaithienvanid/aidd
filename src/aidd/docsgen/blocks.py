"""What every generated block shares: the markers around it, and the Markdown table most blocks hold."""

from __future__ import annotations

import re

BLOCK = re.compile(r"(<!-- aidd:gen (\S+) -->\n)(.*?)(<!-- aidd:end -->)", re.S)
# A value inside a sentence, on one line: `<!-- aidd:gen count:roles -->14<!-- aidd:end -->`.
INLINE = re.compile(r"(<!-- aidd:gen ((?:count|mcp|list):\S+) -->)([^\n<]*)(<!-- aidd:end -->)")


def markdown_table(head: str, rows) -> str:
    """A Markdown table: `head` is its header cells ("A | B"), each row a list of cell strings."""
    sep = "| " + " | ".join("---" for _ in head.split(" | ")) + " |"
    return "\n".join([f"| {head} |", sep, *(f"| {' | '.join(map(str, r))} |" for r in rows)])
