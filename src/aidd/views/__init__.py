"""Human views: what a person reads to decide, as one self-contained HTML page each.

Sources stay text (the Spec, its tests and docs, the config, the evidence); a view is rendered from them by aidd,
deterministically, with no model. Two pages here: the Spec approval page (`aidd hash --html`) and the Merge approval
page (`aidd gate --html`), which holds the verification and what the verifier recorded for the head
(`<evidence>/preview/<head_sha>/artifacts.json`, which `aidd record artifacts` writes); an exploration's comparison page (`aidd explore`, in workitems/explorations.py) and
the client status (`aidd digest --client --html`, in tracking/status_rollup.py) are built from the same parts.

A view is never evidence and never approves: it holds no form, its only buttons copy text, and the gate never reads
it (no module the decision is computed in imports this one). Every string from the repository is escaped, because an
agent wrote most of them. The page loads nothing: a strict Content-Security-Policy allows inline styles, `data:`
images, and one hash-pinned inline script that only turns the copy buttons on. Mermaid diagrams show as their source.

The children: html_parts (escaped markup, the page, and the blocks pages share), markdown_html, verification,
spec_approval (the Spec approval page), merge_approval (the Merge approval page), decisions (the decisions page),
approval_summary, and exploration_page. The prototype viewer is not here: it is aidd-team's prototype tool
(plugins/aidd-team/tools/prototype/), which `aidd prototype` runs.

This module is the package's door (aidd.kernel.doors): other packages use only the names below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "Section",
    "badge",
    "comparison_page",
    "decision_page",
    "default_path",
    "diffs",
    "el",
    "join",
    "merge_summary",
    "merge_page",
    "page",
    "record_artifacts",
    "review_file",
    "since_last_approval",
    "spec_summary",
    "spec_page",
    "table",
    "write",
    "write_merge_page",
]

if TYPE_CHECKING:
    from aidd.views.approval_summary import merge_summary as merge_summary
    from aidd.views.approval_summary import since_last_approval as since_last_approval
    from aidd.views.approval_summary import spec_summary as spec_summary
    from aidd.views.decisions import decision_page as decision_page
    from aidd.views.exploration_page import comparison_page as comparison_page
    from aidd.views.html_parts import Section as Section
    from aidd.views.html_parts import badge as badge
    from aidd.views.html_parts import default_path as default_path
    from aidd.views.html_parts import el as el
    from aidd.views.html_parts import join as join
    from aidd.views.html_parts import page as page
    from aidd.views.html_parts import table as table
    from aidd.views.html_parts import write as write
    from aidd.views.merge_approval import diffs as diffs
    from aidd.views.merge_approval import merge_page as merge_page
    from aidd.views.merge_approval import review_file as review_file
    from aidd.views.merge_approval import write_merge_page as write_merge_page
    from aidd.views.spec_approval import spec_page as spec_page
    from aidd.views.verification import record_artifacts as record_artifacts
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "Section": "html_parts",
            "badge": "html_parts",
            "comparison_page": "exploration_page",
            "decision_page": "decisions",
            "default_path": "html_parts",
            "diffs": "merge_approval",
            "el": "html_parts",
            "join": "html_parts",
            "merge_summary": "approval_summary",
            "merge_page": "merge_approval",
            "page": "html_parts",
            "record_artifacts": "verification",
            "review_file": "merge_approval",
            "since_last_approval": "approval_summary",
            "spec_summary": "approval_summary",
            "spec_page": "spec_approval",
            "table": "html_parts",
            "write": "html_parts",
            "write_merge_page": "merge_approval",
        },
    )
