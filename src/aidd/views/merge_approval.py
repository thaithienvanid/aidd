"""The Merge approval page (`aidd gate --html`): the decision and its findings, the verification, the review, and the diff an Approver reads before a Merge approval."""

from __future__ import annotations

import hashlib
from pathlib import Path

from aidd import workitems
from aidd.views import approval_summary, html_parts, markdown_html, verification

_LEVELS = (("fail", "Failing"), ("pending", "Pending"), ("warn", "Warnings"))


def merge_page(
    ctx: dict,
    d,
    *,
    diffs: dict[str, str] | None = None,
    review: tuple[str | None, list[tuple[str, str]]] | None = None,
    evidence_dir: Path | None = None,
    since: str = "",
) -> str:
    """What an Approver reads before a Merge approval, behavior first: the decision and its findings with their fixes,
    Acceptance against the evidence, the verification evidence and what the verifier recorded, the reviewer's findings,
    the scope and the changed lines, and the diff, file by file. `d` is the gate's Decision; the page shows it and decides nothing."""
    r = d.record
    diffs = diffs or {}
    spec_path = r.get("spec") or ""
    data, body = verification.spec_parts((ctx.get("head_files") or {}).get(spec_path) if spec_path else None, spec_path)
    evidence = ctx.get("evidence") if isinstance(ctx.get("evidence"), dict) and not ctx["evidence"].get("invalid") else None
    tested = (ctx.get("merge_queue") or {}).get("sha") or ctx.get("head_sha")
    stale = ""
    if evidence and evidence.get("head_sha") != tested:
        stale = f"The evidence is for {str(evidence.get('head_sha'))[:12]}, not this head: it says nothing about this commit."
        evidence = None
    head = str(r.get("head_sha") or ctx.get("head_sha") or "")
    sections: list[html_parts.Section] = []

    level = d.decision if d.decision in ("pass", "fail", "pending") else "warn"
    decision_rows = [
        ("Decision", html_parts.join(html_parts.badge(level), "" if d.trusted else " (local, untrusted)")),
        ("Change", r.get("change")),
        ("Spec", html_parts.el("code", spec_path) if spec_path else ""),
        ("Head", html_parts.el("code", head)),
        ("Base", html_parts.el("code", r.get("base_sha") or ctx.get("base_sha") or "")),
        ("Profile", r.get("profile")),
        ("Route", f"{r.get('route')} (required: {r.get('required_route')})" if r.get("route") else ""),
        ("Spec approved by", ", ".join(r.get("spec_approved_by") or [])),
        ("Approved by", ", ".join(r.get("approved_by") or [])),
        ("Assisted by", ", ".join(r.get("assisted_by") or [])),
        ("Changed since the last approval", since),
    ]
    grouped: list = []
    for lvl, title in _LEVELS:
        found = [f for f in d.findings if f.level == lvl]
        if not found:
            continue
        grouped.append(html_parts.el("h3", html_parts.badge(lvl, title), f" {len(found)}"))
        grouped.append(
            html_parts.el(
                "ul",
                [
                    html_parts.el(
                        "li",
                        html_parts.el("code", f.rule),
                        ": ",
                        f.message,
                        html_parts.el("div", html_parts.el("strong", "Fix: "), html_parts.el("span", f.fix)) if f.fix else "",
                        html_parts.el("div", html_parts.el("code", f.code), class_="muted") if f.code else "",
                    )
                    for f in sorted(found, key=lambda f: (f.rule, f.code, f.message))
                ],
                class_="findings",
            )
        )
    if not d.findings:
        grouped.append(html_parts.el("p", html_parts.badge("pass", "every gate holds")))
    notes = html_parts.el("ul", [html_parts.el("li", n) for n in d.notes]) if d.notes else ""
    reasons = (
        html_parts.el(
            "details", html_parts.el("summary", "Why this route"), html_parts.el("ul", [html_parts.el("li", x) for x in r.get("route_reasons") or []])
        )
        if r.get("route_reasons")
        else ""
    )
    approve_help = html_parts.el(
        "p",
        "When every other rule holds, approve the head commit ",
        html_parts.el("code", head[:12]),
        " with a platform review. Under the solo profile, post the line below; without a platform, run ",
        html_parts.el("code", "aidd approve merge"),
        " at your own terminal. This page never approves: its buttons only copy text.",
    )
    sections.append(
        html_parts.Section(
            "decision",
            "Decision",
            html_parts.join(
                html_parts.facts(decision_rows),
                grouped,
                notes,
                reasons,
                approve_help,
                html_parts.copyable("approve-line", f"/aidd approve-merge {head}") if head else "",
            ),
        )
    )

    items = approval_summary.acceptance(body) if body else []
    cmds = ((data.get("tests") or {}).get("commands")) or []
    if items and items[0][0]:
        sections.append(
            html_parts.Section(
                "acceptance",
                "Acceptance against the evidence",
                html_parts.table(
                    ["Id", "Acceptance", "Proven by", "Red on base", "Green on head"],
                    verification.acceptance_rows(items, cmds, evidence or {}, evidence_dir, artifacts=False),
                    label="Each Acceptance item, the commands that cover it, and their results on this head",
                ),
            )
        )

    # What it does before what was said about it: the verifier's run of the built change (its previews included), then
    # the reviewer's report. A person accepts behavior against the Acceptance they approved, as a client accepts work.
    sections.append(html_parts.Section("verification", "Verification", verification.verification_section(evidence, data, body, evidence_dir, stale=stale)))

    who, found = review if review is not None else _review_from_comments(ctx.get("comments") or [])
    if found:
        by_sev: dict[str, list[str]] = {}
        for sev, text in found:
            by_sev.setdefault(sev, []).append(text)
        rev = [html_parts.el("p", f"Reported by {who}. A report, not evidence: weigh it, then decide.", class_="muted")]
        for sev in approval_summary.SEVERITIES:
            if sev in by_sev:
                lvl = "fail" if sev in ("Critical", "High") else "warn" if sev == "Medium" else "pending"
                rev.append(html_parts.el("h3", html_parts.badge(lvl, sev), f" {len(by_sev[sev])}"))
                rev.append(html_parts.el("ul", [html_parts.el("li", markdown_html.inline(t)) for t in by_sev[sev]], class_="findings"))
        sections.append(html_parts.Section("review", "Reviewer findings", html_parts.join(rev)))

    # What the team decided on its own, by a standard, a project rule, or aidd's default: the person may overrule any.
    made = workitems.team_decisions((ctx.get("head_files") or {}).get(spec_path) or "") if spec_path else []
    if made:
        sections.append(
            html_parts.Section(
                "team-decisions",
                "Decisions the team made",
                html_parts.join(
                    html_parts.el(
                        "p",
                        "Each was settled by a standard, a project rule, or aidd's default. Any of them is yours to change: a change order.",
                        class_="muted",
                    ),
                    html_parts.el("ul", [html_parts.el("li", markdown_html.inline(x)) for x in made]),
                ),
            )
        )

    limit = None
    if d.config is not None and r.get("route") not in (None, "standard", "emergency"):
        try:
            limit = d.config.gates["max_changed_lines"].get(r.get("route"))
        except (AttributeError, KeyError, TypeError):
            limit = None
    scope = list(r.get("scope") or [])
    allowed = scope + list((data.get("tests") or {}).get("files") or []) + workitems.design_paths(data) + ([spec_path] if spec_path else [])
    allowed += workitems.threat_models(data, d.config.docs_dir if d.config is not None else "docs")
    files = ctx.get("files") or []
    file_rows = []
    for f in sorted(files, key=lambda f: str(f.get("path"))):
        p = str(f.get("path"))
        where = "in scope" if _any(allowed, p) else "outside the scope"
        moved = f" (from {f['previous_path']})" if f.get("previous_path") else ""
        file_rows.append(
            [
                html_parts.el("a", html_parts.el("code", p + moved), href=f"#{_anchor(p)}") if p in diffs else html_parts.el("code", p + moved),
                f"+{f.get('additions', 0)}",
                f"-{f.get('deletions', 0)}",
                html_parts.badge("pass" if where == "in scope" else "fail", where),
            ]
        )
    lines = r.get("changed_lines", sum(int(f.get("additions") or 0) + int(f.get("deletions") or 0) for f in files))
    sections.append(
        html_parts.Section(
            "scope",
            "Scope and changed lines",
            html_parts.join(
                html_parts.facts(
                    [
                        ("Scope", html_parts.code_list(scope)),
                        ("Changed", f"{r.get('changed_files', len(files))} file(s), {lines} line(s) counted against the changed-line limit"),
                        ("Changed-line limit", f"{limit} lines for the {r.get('route')} route" if limit is not None else "none for this route"),
                    ]
                ),
                html_parts.table(["File", "Added", "Removed", "Scope"], file_rows, label="The diffstat: every changed file") if file_rows else "",
            ),
        )
    )

    if diffs:
        budget_left = html_parts.MAX_DIFF_CHARS
        blocks = []
        for p in sorted(diffs):
            text = diffs[p]
            if budget_left <= 0:
                blocks.append(html_parts.el("p", f"{p}: not shown, the page's diff limit is reached; see it with git", class_="muted"))
                continue
            budget_left -= len(text)
            blocks.append(html_parts.el("details", html_parts.el("summary", html_parts.el("code", p)), html_parts.diff_block(text), id=_anchor(p)))
        sections.append(html_parts.Section("diff", "The diff, file by file", html_parts.join(blocks)))

    title = f"Merge approval: {data.get('id') or r.get('change') or head[:12]}" + (f": {data.get('title')}" if data.get("title") else "")
    return html_parts.page(
        title, sections, lead=f"head {head[:12]}, {len(files)} file(s) changed", badge=html_parts.badge(level, f"gate: {d.decision.upper()}")
    )


def _any(patterns: list[str], path: str) -> bool:
    from aidd.kernel import globs

    return bool(patterns) and globs.match_any(patterns, path)


def _anchor(path: str) -> str:
    return "file-" + hashlib.sha256(path.encode("utf-8")).hexdigest()[:12]


def _review_from_comments(comments: list[dict]) -> tuple[str | None, list[tuple[str, str]]]:
    """The newest comment that holds a ranked review report, all its severities."""
    for c in reversed(comments):
        found = approval_summary.ranked_findings(c.get("body") or "")
        if found:
            return c.get("user"), found
    return None, []


def review_file(path: Path) -> tuple[str | None, list[tuple[str, str]]] | None:
    """A review report saved as a file (`.aidd/evidence/review.md`), or None when there is none or it ranks nothing."""
    if not path.is_file():
        return None
    found = approval_summary.ranked_findings(path.read_text(encoding="utf-8", errors="replace"))
    return (path.name, found) if found else None


def diffs(ctx: dict, cwd: str) -> dict[str, str]:
    """Each changed file's diff between the context's base and head, read from git in `cwd`; empty when git cannot."""
    from aidd.kernel import git

    base, head = ctx.get("base_sha"), ctx.get("head_sha")
    out: dict[str, str] = {}
    if not base or not head:
        return out
    for f in ctx.get("files") or []:
        p = str(f.get("path") or "")
        if p:
            text = git.run(["diff", "--no-color", "--no-ext-diff", str(base), str(head), "--", p], cwd, check=False)
            if text:
                out[p] = text
    return out


def write_merge_page(ctx: dict, d, path: str, *, cwd: str, evidence_dir: Path | None = None, number: int | None = None) -> None:
    """The Merge approval page from a CI adapter; a failure prints a warning and never touches the decision."""
    try:
        target = Path(path) if path else html_parts.default_path("merge", str(ctx.get("head_sha") or "change")[:12])
        if number is not None:
            target = target.with_name(f"{target.stem}-{number}{target.suffix}")
        review = review_file(evidence_dir / "review.md") if evidence_dir else None
        page_text = merge_page(ctx, d, diffs=diffs(ctx, cwd), review=review, evidence_dir=evidence_dir, since=approval_summary.since_last_approval(ctx, cwd))
        html_parts.write(target, page_text)
        print(f"wrote {target}")
    except Exception as exc:  # a view for people: it must never turn a decision into an error
        print(f"warning: the Merge approval page was not written: {type(exc).__name__}: {exc}")
