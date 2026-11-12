"""What a template leaves for a person to fill in, in one place, and the check that none is left in a document.

A placeholder has one of these shapes. `aidd validate` warns on each in a linked document, frozen or living, and in the
repository's own documents. `tests/test_placeholders.py` reads every template in the skill's assets and fails when one
holds a placeholder-like text that no shape matches, so a new template is covered with no new code here.
"""

from __future__ import annotations

import re
from pathlib import Path

from aidd.workitems import authoring, objects, status

# A comment is guidance for the writer, whether it is HTML in the body or `#` in the front matter, and it can run to the
# end of the text when it never closes.
HTML_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.S)
_INLINE_CODE = re.compile(r"`[^`\n]*`")

# The word a template puts where text is missing.
WORD = status.PLACEHOLDER
# The shapes of a date or an id with its value left out. A code span such as `YYYY-MM-DD` names the format, so only these
# shapes skip a code span.
FORMATS = (
    r"YYYY-MM(?:-DD)?",  # a date
    r"\b[A-Z]{1,20}(?:-[A-Z]{1,20}){0,4}-\?+",  # an id with its number left out: SPEC-?, INTENT-?, EC-??; bounded, so a long run backtracks little
    r"\bA\?(?![\w?])",  # an Acceptance id left out
)
_WORD = re.compile(re.escape(WORD))
_FORMAT = re.compile("|".join(FORMATS))


def _without_front_comments(text: str) -> str:
    """`text` with the `#` comments of its front matter removed; the body is as it was."""
    m = re.match(r"---\n(?:.*\n)*?---\n", text)
    if not m:
        return text
    head = re.sub(r"(?m)^[ \t]*#.*\n?|(?<![ \t])[ \t]+#.*$", "", m.group(0))
    return head + text[m.end() :]


def visible(text: str) -> str:
    """`text` as a reader sees it: with the guidance comments of the front matter and the body removed."""
    return HTML_COMMENT.sub("", _without_front_comments(text))


def found(text: str, *, markdown: bool = True) -> list[str]:
    """The placeholders left in `text`, each once, in the order they first appear. Comments are guidance, so a placeholder in
    one does not count. Only Markdown has the date and id shapes; any other file is checked for the word alone, as it is."""
    if not markdown:
        return [WORD] if WORD in text else []
    body = visible(text)
    shaped = _FORMAT.findall(_INLINE_CODE.sub("", body))
    return list(dict.fromkeys([*_WORD.findall(body), *shaped]))


def _shown(left: list[str]) -> str:
    """The first three placeholders, for a finding to quote."""
    return ", ".join(left[:3]) + (", ..." if len(left) > 3 else "")


def finding(path: Path | str, doc: str, left: list[str], *, frozen: bool) -> str:
    """The warning for a linked document `doc` of the Spec at `path` that still holds the placeholders `left`."""
    shown = _shown(left)
    why = "Spec approval would freeze them" if frozen else "replace each before Spec approval"
    return f"warning: {path}: {'frozen' if frozen else 'living'} doc {doc} still holds placeholders ({shown}); {why}"


def repo_doc_warnings(root: Path, docs_dir: str) -> list[str]:
    """A warning for each of the repository's own documents (`aidd new <type>`: the glossary, the data map, the product
    brief, and the rest) that still holds a placeholder. A document that is not there says nothing."""
    out: list[str] = []
    for files in authoring.repo_docs().values():
        for rel, tpl in files:
            rel = rel.replace("{docs}", docs_dir)
            text = objects.read_document(root, rel)[0] if tpl.endswith(".md") else None
            if text is not None and (left := found(text)):
                out.append(f"warning: {rel}: still holds placeholders ({_shown(left)}); replace each, or delete the line")
    return out
