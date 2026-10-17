"""The Spec approval page (`aidd hash --html`): what an Approver reads before posting the approval line."""

from __future__ import annotations

from aidd import workitems
from aidd.kernel import documents
from aidd.views import approval_digest, html_parts, markdown_html, verification


def spec_page(
    text: str,
    path: str,
    line: str,
    *,
    files: dict[str, str] | None = None,
    spec_hash: str = "",
    commit: str = "",
    route: dict | None = None,
    since: dict | None = None,
) -> str:
    """What an Approver reads before posting the approval line: the intent, Acceptance against the tests that cover it,
    the route and why, the risk and rollback, each frozen file and doc, the diagrams, what changed since the last
    approval (`since`: commit, stat, diff), and the line itself to copy."""
    files = files or {}
    data, body = documents.split_front_matter(text, path)
    risk = data.get("risk") or {}
    tests = data.get("tests") or {}
    cmds = tests.get("commands") or []
    sid = str(data.get("id", ""))
    sections: list[html_parts.Section] = []

    approve = [
        html_parts.el("p", "Read this page, then approve by posting this line as a comment on the pull request:"),
        html_parts.copyable("approval-line", line),
        html_parts.el(
            "p",
            "Without a platform, run this at your own terminal instead, and answer yes (or type `approve <ID>` in Claude Code with the aidd-mods plugin):",
            class_="muted",
        ),
        html_parts.copyable("approve-local", f"aidd approve spec {path}"),
        html_parts.el(
            "p",
            "This page never approves: its buttons only copy text. The hash covers the Spec, its test files, its design files, and its frozen docs; "
            "changing any of them voids the approval.",
            class_="muted",
        ),
    ]
    sections.append(
        html_parts.Section(
            "approve",
            "What you approve",
            html_parts.join(
                html_parts.facts(
                    [("Spec", html_parts.el("code", path)), ("Hash", html_parts.el("code", spec_hash)), ("Commit", html_parts.el("code", commit))]
                ),
                approve,
            ),
        )
    )

    intent, intent_name = "", "Intent"
    for name in ("Intent", "Problem", "Context"):
        found = _section_raw(body, name)
        if found:
            intent, intent_name = found, name
            break
    sections.append(
        html_parts.Section(
            "intent",
            intent_name,
            markdown_html.md(intent) if intent else html_parts.el("p", "The Spec has no Intent, Problem, or Context section.", class_="muted"),
        )
    )

    items = approval_digest.acceptance(body)
    if items and items[0][0]:
        acc = html_parts.table(
            ["Id", "Acceptance", "Proven by"],
            verification.acceptance_rows(items, cmds, None, None),
            label="Each Acceptance item and the test commands that list it in covers",
        )
    else:
        acc = html_parts.join(
            html_parts.el("p", "The Acceptance items carry no ids (A1, A2, …), so no command can say which it proves.", class_="muted"),
            markdown_html.md(_section_raw(body, "Acceptance")),
        )
    cmd_rows = [
        [
            html_parts.el("code", c.get("name")),
            html_parts.el("code", verification.command_line(c.get("command"))),
            "yes: must fail on base first" if c.get("new_behavior") else "no",
            html_parts.code_list(list(c.get("covers") or [])),
        ]
        for c in cmds
    ]
    acc = html_parts.join(
        acc,
        html_parts.el("h3", "Test commands"),
        html_parts.table(["Name", "Runs", "New behavior", "Covers"], cmd_rows, label="The Spec's test commands")
        if cmd_rows
        else html_parts.el("p", "none", class_="muted"),
    )
    sections.append(html_parts.Section("acceptance", "Acceptance and tests", acc))

    route_rows = [
        ("Declared route", html_parts.el("strong", data.get("route", ""))),
        ("Type", data.get("type")),
        ("Confidence", data.get("confidence")),
        ("Dimensions", ", ".join(risk.get("dimensions") or []) or "none declared"),
    ]
    route_body: list = [html_parts.facts(route_rows)]
    if route:
        route_body.append(html_parts.el("p", f"From the Spec's scope, the rules compute at least {route.get('route')} ({route.get('lane')} lane), because:"))
        route_body.append(
            html_parts.el(
                "ul",
                [html_parts.el("li", r) for r in route.get("reasons") or ["no risk rule, protected path, or declared risk raised it: the minimum is minor"]],
            )
        )
        route_body.append(html_parts.el("p", "The gate computes the route again from the real diff, and can only raise it.", class_="muted"))
    sections.append(html_parts.Section("route", "Route", html_parts.join(route_body)))

    task_rows = [
        [html_parts.el("code", t.get("id")), t.get("title", ""), html_parts.code_list(list(t.get("scope") or [])), ", ".join(t.get("depends_on") or []) or "-"]
        for t in data.get("tasks") or []
    ]
    sections.append(
        html_parts.Section(
            "risk",
            "Risk, rollback, and scope",
            html_parts.join(
                html_parts.facts(
                    [
                        ("Risk", risk.get("summary", "")),
                        ("Reversible", "yes" if risk.get("reversible", True) else "NO: irreversible"),
                        ("Rollback", data.get("rollback", "")),
                        ("Residual risk", data.get("residual_risk", "")),
                        ("Hypothesis", (data.get("hypothesis") or {}).get("statement", "") if isinstance(data.get("hypothesis"), dict) else ""),
                    ]
                ),
                html_parts.el("h3", "Tasks and scope"),
                html_parts.table(["Task", "Title", "Scope", "Depends on"], task_rows, label="What each Task may change")
                if task_rows
                else html_parts.el("p", "none", class_="muted"),
            ),
        )
    )

    docs = workitems.frozen_docs(data)
    frozen = workitems.frozen_paths(data)
    frozen_rows = []
    for pattern in frozen:
        matched = sorted(p for p in files if _matches(pattern, p))
        kind = "doc" if pattern in docs else "design" if pattern in (data.get("design") or {}).get("files", []) else "test"
        lines = sum(len(files[p].splitlines()) for p in matched)
        frozen_rows.append(
            [html_parts.el("code", pattern), kind, f"{len(matched)} file(s), {lines} line(s)" if matched else html_parts.badge("warn", "missing")]
        )
    frozen_body: list = [
        html_parts.table(["Pattern", "Kind", "At this commit"], frozen_rows, label="What the hash freezes besides the Spec")
        if frozen_rows
        else html_parts.el("p", "Nothing but the Spec.", class_="muted")
    ]
    for pattern in docs:
        for p in sorted(p for p in files if _matches(pattern, p)):
            frozen_body.append(html_parts.el("details", html_parts.el("summary", p), markdown_html.md(files[p], top=4)))
    sections.append(html_parts.Section("frozen", "Frozen files and docs", html_parts.join(frozen_body)))

    diagrams = [(path, src) for src in markdown_html.mermaid_blocks(body)] + [
        (p, src) for pattern in docs for p in sorted(files) if _matches(pattern, p) for src in markdown_html.mermaid_blocks(files[p])
    ]
    if diagrams:
        sections.append(
            html_parts.Section(
                "diagrams",
                "Diagrams",
                html_parts.join([html_parts.join(html_parts.el("h3", html_parts.el("code", where)), html_parts.diagram(src)) for where, src in diagrams]),
            )
        )

    if since:
        sections.append(
            html_parts.Section(
                "since",
                "Changed since the last approval",
                html_parts.join(
                    html_parts.el(
                        "p",
                        "An earlier approval of this Spec named commit ",
                        html_parts.el("code", str(since.get("commit", ""))[:12]),
                        "; since then the frozen files changed:",
                    ),
                    html_parts.el("pre", since.get("stat") or "(no change in the frozen files)"),
                    html_parts.el("details", html_parts.el("summary", "The diff"), html_parts.diff_block(since.get("diff") or "")) if since.get("diff") else "",
                ),
            )
        )

    sections.append(
        html_parts.Section(
            "spec",
            "The whole Spec",
            html_parts.el("details", html_parts.el("summary", f"{path}, as written"), markdown_html.md(workitems.strip_handoffs(body), top=3)),
        )
    )
    lead = f"{data.get('type', '')}, route {data.get('route', '')}, confidence {data.get('confidence', '')}, owner {data.get('owner_team', '')}"
    return html_parts.page(f"{sid}: {data.get('title', '')}", sections, lead=lead, badge=html_parts.badge("pending", "Spec approval"))


def _matches(pattern: str, path: str) -> bool:
    from aidd.kernel import globs

    return globs.match_any([pattern], path)


def _section_raw(body: str, heading: str) -> str:
    """A `## heading` section's Markdown, fences kept, HTML comments dropped."""
    return documents.markdown_section(body, heading, fences=True)
