"""The words, the search, and the answer of `aidd recall` (schemas/recall.schema.json, without its version field).

A word is a run of letters and digits in what was given, so no quote, star, underscore, or operator reaches the
full-text query as syntax, and `a_b` is the two words `a` and `b` in both the full-text and the plain search: a crafted query can't fail or match everything. A line matches when it holds every word.
"""

from __future__ import annotations

import re
from pathlib import Path

from aidd import config, workitems
from aidd.kernel import documents, index
from aidd.recall import sources
from aidd.recall.limits import DEFAULT_MATCHES, MAX_MATCHES

MAX_WORDS = 16
MAX_WORD_CHARS = 100
SNIPPET_CHARS = 160
# What every answer says first: what recall is, and what it never is.
NOTE = "A cache of the team's files: never a source of truth, never evidence, and never a yes. Read the file before you rely on a match."
_WORD = re.compile(r"[^\W_]+")


def words_of(given: list[str]) -> list[str]:
    """The words to search for in what was given, each once, in order."""
    words = list(dict.fromkeys(w for text in given for w in _WORD.findall(text)))
    if not words:
        raise ValueError("give a word to search for, such as `aidd recall retry budget`")
    if len(words) > MAX_WORDS:
        raise ValueError(f"give at most {MAX_WORDS} words: fewer words find more lines")
    if any(len(w) > MAX_WORD_CHARS for w in words):
        raise ValueError(f"a word is longer than {MAX_WORD_CHARS} characters: give a shorter part of it")
    return words


def snippet(text: str, words: list[str], width: int = SNIPPET_CHARS) -> str:
    """The line as one safe terminal line of at most `width` characters, from just before the first word it holds."""
    line = " ".join(documents.one_line(text, len(text) + 1).split())
    low = line.lower()
    first = min((i for w in words if (i := low.find(w.lower())) >= 0), default=0)
    start = max(0, first - width // 4) if len(line) > width else 0
    return documents.one_line(("…" if start else "") + line[start:], width)


def _match(found: index.Found, words: list[str]) -> dict:
    source, p = found.place.rsplit(":", 1)[1], found.passage
    out: dict = {"source": source}
    if source == "record":
        out["id"] = p.ref
    elif source == "commit":
        out["sha"] = p.ref
    else:
        out |= {"path": p.ref, "line": p.line}
    if p.at:
        out["at"] = p.at
    out["snippet"] = snippet(p.text, words)
    return out


def search(root: Path, cfg: config.Config | None, given: list[str], *, limit: int = DEFAULT_MATCHES) -> dict:
    """The lines of the team's writing that hold every word given, newest first where a line has a date, then by
    source, path, and line; at most `limit` of them."""
    if not 1 <= limit <= MAX_MATCHES:
        raise ValueError(f"--limit is the most matches to show, from 1 to {MAX_MATCHES}")
    words = words_of(given)
    top = root.resolve()
    places, skipped = sources.places(top, cfg)
    found, more, method = index.search_passages(workitems.index_path(top), places, words, limit=limit, gone=sources.gone)
    return {"words": words, "method": method, "note": NOTE, "matches": [_match(f, words) for f in found], "more": more, "skipped": skipped}


def search_text(answer: dict) -> str:
    """The answer as a person reads it: the note first, then one line per match."""
    words, matches = " ".join(answer["words"]), answer["matches"]
    lines = [f"aidd recall: {len(matches)} match(es) for {documents.one_line(words)}. {NOTE}"]
    if answer["method"] == "substring":
        lines.append("It searched as plain text, because full-text search was not available here: each word matches anywhere in a line.")
    for m in matches:
        if m["source"] == "record":
            where = f"record {documents.one_line(m['id'], 80)}  {m.get('at', '')}"
        elif m["source"] == "commit":
            where = f"commit {m['sha']}  {m['at'][:10]}"
        else:
            where = f"{documents.one_line(m['path'], 200)}:{m['line']}"
        lines.append(f"  {where}  {m['snippet']}")
    if not matches:
        lines.append("Nothing matched every word. Try fewer words, or other ones.")
    if answer["more"]:
        lines.append(f"More lines matched: give more words, or a higher --limit (at most {MAX_MATCHES}).")
    if skipped := answer["skipped"]:
        first = skipped[0]
        lines.append(f"Skipped {len(skipped)} file(s), such as {documents.one_line(first['path'], 200)}: {first['reason']}.")
    return "\n".join(lines) + "\n"
