"""Recall: search what the team already wrote, for `aidd recall` and the MCP `recall` tool.

It searches the records, the Specs and the documents in their folders, the ADRs, the glossary, the product brief, the
improvement log, and the commit subjects. Each match names its file and line, a record's id, or a commit's short sha,
with a one-line snippet. It reads through the index (aidd.kernel.index), a cache of the files rebuilt when they change,
so the files stay the truth. A match is never evidence and never a yes. No model, no embeddings, no network.

The children: sources (what it searches, each as a place of the index), matching (the words, the search, and the
answer), and limits (how many matches it shows, which the parser reads without loading the index).

This module is the package's door (aidd.kernel.doors): other packages use only the names below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "DEFAULT_MATCHES",
    "MAX_MATCHES",
    "search",
    "search_text",
]

if TYPE_CHECKING:
    from aidd.recall.limits import DEFAULT_MATCHES as DEFAULT_MATCHES
    from aidd.recall.limits import MAX_MATCHES as MAX_MATCHES
    from aidd.recall.matching import search as search
    from aidd.recall.matching import search_text as search_text
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "DEFAULT_MATCHES": "limits",
            "MAX_MATCHES": "limits",
            "search": "matching",
            "search_text": "matching",
        },
    )
