"""Views: what a person reads, as one self-contained HTML page.

Sources stay text; a view is rendered from them by aidd, deterministically, with no model. The exploration's
comparison page (`aidd explore`) and the work-item page (`aidd status --html`) are built from the shared parts here.

A view is never evidence and never approves: it holds no form, and its only buttons copy text. Every string from the
repository is escaped, because an agent wrote most of them. The page loads nothing: a strict Content-Security-Policy
names its one style block by hash, allows `data:` images, and runs no script but the status page's own, pinned by hash.
Mermaid diagrams show as their source.

The children: html_parts (escaped markup, the page, and the blocks pages share), markdown_html, exploration_page, work_item_page,
and design_tokens (the design system's CSS and DESIGN.md's front matter, from design/tokens.json and components.css).
The prototype viewer is not here: it is aidd-team's prototype tool (plugins/aidd-team/tools/prototype/), which
`aidd prototype` runs.

This module is the package's door (aidd.kernel.doors): other packages use only the names below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "Section",
    "comparison_page",
    "default_path",
    "el",
    "join",
    "page",
    "status_page",
    "system_css",
    "table",
    "with_design_front_matter",
    "write",
]

if TYPE_CHECKING:
    from aidd.views.design_tokens import system_css as system_css
    from aidd.views.design_tokens import with_design_front_matter as with_design_front_matter
    from aidd.views.exploration_page import comparison_page as comparison_page
    from aidd.views.html_parts import Section as Section
    from aidd.views.html_parts import default_path as default_path
    from aidd.views.html_parts import el as el
    from aidd.views.html_parts import join as join
    from aidd.views.html_parts import page as page
    from aidd.views.html_parts import table as table
    from aidd.views.html_parts import write as write
    from aidd.views.work_item_page import status_page as status_page
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "Section": "html_parts",
            "comparison_page": "exploration_page",
            "default_path": "html_parts",
            "el": "html_parts",
            "join": "html_parts",
            "page": "html_parts",
            "status_page": "work_item_page",
            "system_css": "design_tokens",
            "table": "html_parts",
            "with_design_front_matter": "design_tokens",
            "write": "html_parts",
        },
    )
