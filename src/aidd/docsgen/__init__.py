"""Generate the Markdown that restates aidd's schemas, team, and command line, so the docs and their sources never drift.

A generated block sits between `<!-- aidd:gen NAME -->` and `<!-- aidd:end -->`. `aidd gen-docs --check` fails when
any block, domain pack, or agent file is stale. The children: generate (one block, or every file), schema_tables,
cli_reference, team_reference, error_catalog (docs/ERRORS.md), diagrams, pack_render, counts, blocks, and pack_budget
(`aidd eval packs`).

This module is the package's door (aidd.kernel.doors): other packages use only the names below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = ["CliFacts", "gen_docs", "pack_descriptions", "pack_sizes_and_problems", "render", "standard_text"]

if TYPE_CHECKING:
    from aidd.docsgen.cli_reference import CliFacts as CliFacts
    from aidd.docsgen.generate import gen_docs as gen_docs
    from aidd.docsgen.generate import render as render
    from aidd.docsgen.pack_budget import pack_descriptions as pack_descriptions
    from aidd.docsgen.pack_budget import pack_sizes_and_problems as pack_sizes_and_problems
    from aidd.docsgen.team_reference import standard_text as standard_text
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "CliFacts": "cli_reference",
            "gen_docs": "generate",
            "pack_descriptions": "pack_budget",
            "pack_sizes_and_problems": "pack_budget",
            "render": "generate",
            "standard_text": "team_reference",
        },
    )
