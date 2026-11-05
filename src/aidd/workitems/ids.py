"""What a work item's id may be: the one pattern `common.schema.json` gives, read from it, so nothing copies it.

An id is the only text of a work item that goes into words a person copies, and only when it matches: front matter is
another person's text, so an id outside the pattern is named by its path, or by nothing.
"""

from __future__ import annotations

import functools
import re

from aidd.kernel import resources


@functools.cache
def id_pattern() -> re.Pattern[str]:
    """The schema's `$defs.id.pattern`, compiled."""
    return re.compile(resources.load_json("common.schema.json")["$defs"]["id"]["pattern"])


def is_id(text: object) -> bool:
    """Whether `text` is a work item's id by the schema's pattern."""
    return isinstance(text, str) and id_pattern().fullmatch(text) is not None


_DIGITS = re.compile(r"(\d+)")


def _digits_key(digits: str) -> tuple[int, str]:
    """A run of digits as a key that sorts in numeric order without int(): by its length, then its digits, once leading
    zeros are gone. int() refuses a run past 4,300 digits, and an id comes from another person's file."""
    significant = digits.lstrip("0") or "0"
    return (len(significant), significant)


def id_order(text: str) -> tuple:
    """A key that sorts ids by their numbers, so SPEC-2 comes before SPEC-10 and SPEC-2-T2 before SPEC-2-T10. The key
    alternates text and number keys, starting with text, so any two keys compare part by part, each part with its kind."""
    return tuple(_digits_key(part) if i % 2 else part for i, part in enumerate(_DIGITS.split(text)))
