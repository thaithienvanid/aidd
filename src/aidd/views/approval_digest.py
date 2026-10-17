"""Short, phone-sized digests for the two human approvals.

`spec_digest` is what an Approver reads before posting `/aidd approve-spec` (`aidd hash --line --summary`);
`merge_digest` is what they read before a Merge approval (the gate's job summary). Both are for people and never
count as evidence: the gate decides on the hash, the exit codes, and the SHAs.
"""

from __future__ import annotations

import re

from aidd import gate, workitems
from aidd.kernel import documents, git
from aidd.kernel.text import md_cell

MAX_LINES = 25
WIDTH = 78
_ACCEPTANCE_ITEM = re.compile(
    r"^[ \t]*(?:[-*|#]+[ \t]*)?\**(?:(?:Scenario Outline|Scenario|Example|Rule)[ \t]*:[ \t]*)?\**(A[1-9][0-9]{0,3})\b[ \t:.)|-]*(.*)$", re.M
)
# A ranked review report (REVIEW.md): a line that opens with the severity.
_FINDING = re.compile(r"^[ \t]*(?:[-*]|\d+\.)?[ \t]*(?:\*\*|\[|`)?(Critical|High)\b(?:\*\*|\]|`)?[ \t]*[:\-—|)]+[ \t]*(.+)$", re.M | re.I)
# Every severity a review report ranks by (REVIEW.md), worst first; the Merge approval page shows them all.
SEVERITIES = ("Critical", "High", "Medium", "Low", "Nit")
_RANKED = re.compile(_FINDING.pattern.replace("(Critical|High)", "(" + "|".join(SEVERITIES) + ")"), re.M | re.I)


def _cut(text: str, width: int = WIDTH) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[: width - 1].rstrip() + "…"


def acceptance(body: str) -> list[tuple[str, str]]:
    """The Acceptance items as (id, text); items without ids come back as ("", line), the first few lines only."""
    text = documents.markdown_section(body, "Acceptance", fences=False)
    items: dict[str, str] = {}
    for m in _ACCEPTANCE_ITEM.finditer(text):
        items.setdefault(m.group(1), m.group(2).strip(" |*"))
    if items:
        return list(items.items())
    return [("", ln.strip()) for ln in text.splitlines() if not ln.strip().startswith("|")][:4]


def spec_digest(text: str, path: str, approval_line: str, *, max_lines: int = MAX_LINES, files: dict[str, str] | None = None) -> str:
    """The Spec in at most `max_lines` lines, ending with the approval line: what the Approver approves by hash.
    `files` holds the frozen docs' text by path, so each is listed with its size: the Approver approves those too."""
    data, body = documents.split_front_matter(text, path)
    risk = data.get("risk") or {}
    tests = data.get("tests") or {}
    head = [f"{data.get('id')}: {_cut(data.get('title', ''), WIDTH - len(str(data.get('id'))) - 2)}"]
    head.append(f"{data.get('type')}, route {data.get('route')}, confidence {data.get('confidence')}")
    for name in ("Intent", "Problem", "Context"):
        found = documents.markdown_section(body, name, fences=False)
        if found:
            head.append(f"{name}: " + _cut(found, WIDTH - len(name) - 2))
            break
    tail = []
    scope = [s for task in data.get("tasks") or [] for s in task.get("scope") or []]
    tail.append("Scope: " + _cut(", ".join(scope) or "none declared", WIDTH - 7))
    dims = f" [{', '.join(risk.get('dimensions') or []) or 'no dimensions'}]" + ("" if risk.get("reversible", True) else " IRREVERSIBLE")
    tail.append(f"Risk: {_cut(risk.get('summary', ''), WIDTH - 6 - len(dims))}{dims}")
    tail.append("Rollback: " + _cut(data.get("rollback", ""), WIDTH - 10))
    if data.get("residual_risk"):
        tail.append("Residual risk: " + _cut(data["residual_risk"], WIDTH - 15))
    docs = workitems.frozen_docs(data)
    frozen = [p for p in workitems.frozen_paths(data) if p not in docs]
    tail.append("Frozen: " + _cut(", ".join(frozen) or "no test files", WIDTH - 8))
    for d in docs[:3]:
        tail.append("Doc: " + _cut(_doc_size(d, files or {}), WIDTH - 5))
    if len(docs) > 3:
        tail.append(f"Doc: … {len(docs) - 3} more in the Spec's `docs`")
    cmds = tests.get("commands") or []
    if cmds:
        parts = [c["name"] + (" (red first)" if c.get("new_behavior") else "") + (f" covers {'/'.join(c['covers'])}" if c.get("covers") else "") for c in cmds]
        tail.append("Tests: " + _cut("; ".join(parts), WIDTH - 7))
    tail += ["", approval_line]
    items = acceptance(body)
    room = max_lines - len(head) - len(tail) - 1
    lines = [f"  {i} {_cut(t, WIDTH - 3 - len(i))}".rstrip() if i else f"  {_cut(t, WIDTH - 2)}" for i, t in items]
    if len(lines) > room:
        lines = lines[: max(room - 1, 0)] + [f"  … {len(items) - max(room - 1, 0)} more in the Spec"]
    out = head + [f"Acceptance ({len(items) if items and items[0][0] else 'no ids'}):"] + lines + tail
    return "\n".join(out[:max_lines])


def _doc_size(pattern: str, files: dict[str, str]) -> str:
    """A frozen doc with its line count, or the files and lines a glob matches, or that it is missing."""
    from aidd.kernel import globs

    found = [text for p, text in sorted(files.items()) if globs.match_any([pattern], p)]
    if not found:
        return f"{pattern} (missing)"
    lines = sum(len(text.splitlines()) for text in found)
    return f"{pattern} ({lines} lines)" if len(found) == 1 else f"{pattern} ({len(found)} files, {lines} lines)"


def red_on_base(evidence: dict | None) -> str:
    """yes: every red run failed as a test should on base; no: one passed there; not run: no red result."""
    reds = [r for r in (evidence or {}).get("results") or [] if r.get("red_green") == "red"]
    if not reds:
        return "not run"
    if any(r.get("status") == "passed" for r in reds):
        return "no"
    return "yes" if all(gate.red_ok(r) for r in reds) else "inconclusive (a red run errored or timed out)"


def _review_findings(comments: list[dict], limit: int = 5) -> tuple[str | None, list[str]]:
    """Critical and High lines from the newest comment that holds a ranked review report, and who posted it."""
    for c in reversed(comments):
        found = [f"{m.group(1).capitalize()}: {_cut(m.group(2), WIDTH - 10)}" for m in _FINDING.finditer(documents._HTML_COMMENT.sub("", c.get("body") or ""))]
        if found:
            return c.get("user"), found[:limit] + ([f"… {len(found) - limit} more"] if len(found) > limit else [])
    return None, []


def ranked_findings(text: str) -> list[tuple[str, str]]:
    """Every ranked line of a review report as (severity, text), in the report's order."""
    return [(m.group(1).capitalize(), m.group(2).strip()) for m in _RANKED.finditer(documents._HTML_COMMENT.sub("", text or ""))]


def since_last_approval(ctx: dict, cwd: str | None) -> str:
    head = ctx["head_sha"]
    approved = sorted((r for r in ctx.get("reviews") or [] if r.get("state") == "approved" and r.get("commit_sha")), key=lambda r: r.get("submitted_at") or "")
    if not approved:
        return "no earlier approval"
    last = approved[-1]
    if last["commit_sha"] == head:
        return f"nothing: {last['user']} approved this head"
    if cwd is None:
        return f"the last approval ({last['user']}) was on {last['commit_sha'][:12]}"
    try:
        files = git.numstat(last["commit_sha"], head, cwd)
    except git.GitError:
        return f"the last approval ({last['user']}) was on {last['commit_sha'][:12]}, which is no longer in this history (a force-push)"
    paths = [f["path"] for f in files]
    lines = sum(f.get("additions", 0) + f.get("deletions", 0) for f in files)
    shown = ", ".join(f"`{p}`" for p in paths[:5]) + (f", and {len(paths) - 5} more" if len(paths) > 5 else "")
    return f"{len(paths)} file(s), {lines} line(s) since {last['user']} approved {last['commit_sha'][:12]}: {shown or 'no file changes'}"


def merge_digest(ctx: dict, *, cwd: str | None = None) -> str:
    """The Merge approval digest for the gate summary, in Markdown: Acceptance against the evidence (through each
    command's `covers`), red on base, the review report's Critical and High findings, the residual risk, and what
    changed since the last approval. `cwd` is a repository holding both commits, for that last line."""
    body = (ctx.get("change") or {}).get("body") or ""
    cr, _ = workitems.parse_change_block(body)
    cr_spec = (cr or {}).get("spec")
    text = (ctx.get("head_files") or {}).get(cr_spec) if cr_spec else None
    evidence = ctx.get("evidence") if isinstance(ctx.get("evidence"), dict) and not ctx["evidence"].get("invalid") else None
    tested = (ctx.get("merge_group") or {}).get("sha") or ctx.get("head_sha")
    if evidence and evidence.get("head_sha") != tested:
        evidence = None  # stale: results for another commit say nothing about this one
    out = ["", "#### Merge approval digest", ""]
    data: dict = {}
    spec_body = ""
    if text:
        try:
            data, spec_body = documents.split_front_matter(text, str(cr_spec))
        except documents.DocumentError:
            data = {}
    green = {r["name"]: r for r in (evidence or {}).get("results") or [] if r.get("red_green") == "green"}
    red = {r["name"]: r for r in (evidence or {}).get("results") or [] if r.get("red_green") == "red"}
    cmds = ((data.get("tests") or {}).get("commands")) or []
    items = acceptance(spec_body) if spec_body else []
    if items and items[0][0]:
        out += ["| Acceptance | Proven by | Head | Red on base |", "| --- | --- | --- | --- |"]
        for i, t in items[:8]:
            by = [c["name"] for c in cmds if i in (c.get("covers") or [])]
            head_state = ", ".join(green[n]["status"] if n in green else "no result" for n in by) or "-"
            red_state = ", ".join(("yes" if gate.red_ok(red[n]) else red[n]["status"]) if n in red else "-" for n in by) or "-"
            out.append(f"| {i} {md_cell(_cut(t, 50))} | {', '.join(f'`{n}`' for n in by) or '**nothing covers it**'} | {head_state} | {red_state} |")
        out.append("")
    red_line = red_on_base(evidence)
    out.append(f"- **Red on base:** {red_line}")
    spec_only = bool(data) and _spec_only(ctx, str(cr_spec), data)
    if spec_only and red_line == "yes":
        out.append("- **Spec-only change:** the new tests fail on base, as they should before implementation; approve the Spec knowing they bite.")
    who, findings = _review_findings(ctx.get("comments") or [])
    if findings:
        out.append(f"- **Review findings, Critical and High** (reported by {who}; a report, not evidence):")
        out += [f"  - {md_cell(f)}" for f in findings]
    residual = data.get("residual_risk") or ((cr or {}).get("residual_risk") if cr else None)
    if residual:
        out.append(f"- **Residual risk:** {md_cell(_cut(residual, 200))}")
    out.append(f"- **Changed since the last approval:** {since_last_approval(ctx, cwd)}")
    return "\n".join(out) + "\n"


def _spec_only(ctx: dict, spec_path: str, data: dict) -> bool:
    """True when the diff holds only the Spec and the files its approval freezes: the Spec-first pull request."""
    from aidd.kernel import globs

    frozen = [spec_path, *workitems.frozen_paths(data)]
    paths = [f["path"] for f in ctx.get("files") or []]
    return bool(paths) and all(globs.match_any(frozen, p) for p in paths)
