"""A software requirements specification (SRS), generated and never hand-kept: the outline of ISO/IEC/IEEE 29148 (assets/srs.md)
filled from an Initiative or an Epic, the Specs below it, and git.

A requirement is one Acceptance item of a Spec at or past Spec approval. It links the test command that covers it
(`covers` in the Spec's `tests.commands`) and the newest commit that names its Spec, which `tracing.trace` reads. An item
nothing covers is shown as a gap, so the document tells the truth about the tests. It is derived output, never evidence:
a runner's exit code on a commit is (`aidd test`). `product` in place of an id covers every Spec, which is the product's
whole trace from each Acceptance id to its tests.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from aidd import config
from aidd.kernel import documents, git
from aidd.kernel import text as kernel_text
from aidd.workitems import interfaces, spec_file, status, tracing, work_list
from aidd.workitems.backlog import WORK_TYPES

PRODUCT = "product"
IN_THE_SRS = ("approved", "in_progress", "in_review", "done")
_NONE = "none recorded"


def _cell(text: object, limit: int = 300) -> str:
    return kernel_text.md_cell(documents.one_line(text, limit))


def _real(*values: object) -> list[str]:
    """The values that say something: not empty, and not a template's TODO."""
    return [str(v) for v in values if v and "TODO" not in str(v)]


def _natural(oid: str) -> tuple[str, int]:
    prefix, _, number = oid.rpartition("-")
    return prefix, int(number) if number.isdigit() else 0


def acceptance_items(text: str) -> list[tuple[str, str]]:
    """(id, statement) for each Acceptance item in a Spec's body, once per id, in order."""
    items: dict[str, str] = {}
    for line in documents.markdown_section(text, "Acceptance").splitlines():
        if m := spec_file.ACCEPTANCE_ID.match(line):
            items.setdefault(m.group(1), line[m.end() :].strip(" |").lstrip(" :.)-–—*\t").replace(" | ", "; ").strip())
    return list(items.items())


def _scope(items: dict[str, tuple[str, dict]], target: str) -> list[str]:
    """The Spec ids below `target`, in order; `product` is every Spec. ValueError for any other id."""
    item_types = {i: str(d.get("type")) for i, (_, d) in items.items()}
    if target.lower() == PRODUCT:
        return sorted((i for i, k in item_types.items() if k == "spec"), key=_natural)
    if item_types.get(target) not in ("initiative", "epic"):
        raise ValueError(f"no Initiative or Epic has the id {target}; `aidd new srs <INIT-ID>` covers one, and `aidd new srs product` covers every Spec")
    children: dict[str, list[str]] = {}
    for i, (_, d) in items.items():
        if d.get("parent"):
            children.setdefault(str(d["parent"]), []).append(i)
    below: list[str] = []
    todo = [target]
    while todo:
        for child in children.get(todo.pop(0), []):
            if child not in below and child != target:
                below.append(child)
                todo.append(child)
    return sorted((i for i in below if item_types[i] == "spec"), key=_natural)


def _tests(data: dict, item: str) -> str:
    tests = data.get("tests")
    listed = tests.get("commands") if isinstance(tests, dict) else None
    commands = (
        [c for c in listed or [] if isinstance(c, dict) and isinstance(c.get("covers"), list) and item in c["covers"]] if isinstance(listed, list) else []
    )
    return (
        "; ".join(
            f"`{_cell(c.get('name'), 60)}`: `{_cell(' '.join(map(str, c['command'])) if isinstance(c.get('command'), list) else str(c.get('command') or ''), 120)}`"
            for c in commands
        )
        or "no test command covers it"
    )


def _commit(root: Path, cfg: config.Config | None, sid: str) -> str:
    try:
        found = tracing.trace(root, cfg, sid, commits=1)["commits"]
    except (ValueError, git.GitError):
        found = []
    return f"`{found[0]['sha'][:10]}` {found[0]['date'][:10]}" if found else "none yet"


def _group(items: dict[str, tuple[str, dict]], specs: list[str]) -> dict[str, list[str]]:
    """The Specs by the Epic they sit under ("" for none), Epics in order."""
    groups: dict[str, list[str]] = {}
    for sid in specs:
        parent = str(items[sid][1].get("parent") or "")
        groups.setdefault(parent if parent in items and items[parent][1].get("type") == "epic" else "", []).append(sid)
    return dict(sorted(groups.items(), key=lambda kv: (kv[0] == "", _natural(kv[0]))))


def _requirements(root: Path, cfg: config.Config | None, items: dict[str, tuple[str, dict]], specs: list[str]) -> tuple[str, int, int, int, list[str]]:
    """The 3.2 tables, then the counts: requirements, with a test, with a commit; and the ids no test covers."""
    out: list[str] = []
    total = tested = landed = 0
    gaps: list[str] = []
    for epic, members in _group(items, specs).items():
        rows = []
        for sid in members:
            path, data = items[sid]
            commit = _commit(root, cfg, sid)
            for item, statement in acceptance_items((root / path).read_text(encoding="utf-8", errors="replace")):
                test = _tests(data, item)
                total, tested, landed = total + 1, tested + (not test.startswith("no ")), landed + (commit != "none yet")
                gaps += [f"{sid}/{item}"] if test.startswith("no ") else []
                rows.append(f"| {sid}/{item} | {_cell(statement)} | {status.spec_status(data)} | {test} | {commit} |")
        if rows:
            title = f"{epic}: {_cell(items[epic][1].get('title'), 100)}" if epic else "Specs under no Epic"
            out.append(f"#### {title}\n\n| Requirement | Statement | Spec status | Test | Commit |\n| --- | --- | --- | --- | --- |\n" + "\n".join(rows))
    return "\n\n".join(out) or f"{_NONE}: no Spec in scope is at or past Spec approval.", total, tested, landed, gaps


def _frame(root: Path, items: dict[str, tuple[str, dict]], target: str, scope: list[str], ready: list[str]) -> dict[str, str]:
    """Sections 1, 2, 3.1, and Appendix A: what the work items say about the target and its Specs."""
    top = items.get(target, ("", {}))[1]
    epics = [e for e in _group(items, scope) if e]
    perspective = f"{_NONE}: no Epic groups these Specs."
    if epics:
        rows = (f"| {e} | {_cell(items[e][1].get('title'), 100)} | {len([s for s in ready if items[s][1].get('parent') == e])} |" for e in epics)
        perspective = "| Epic | Title | Specs in this document |\n| --- | --- | --- |\n" + "\n".join(rows)
    people = sorted(set(_real(*(items[s][1].get("approved_by") for s in ready))))
    teams = sorted(set(_real(*(items[i][1].get("owner_team") for i in [target, *scope] if i in items))))
    held = documents.markdown_section((root / items[target][0]).read_text(encoding="utf-8", errors="replace"), "Out of scope") if target in items else ""
    bound = "\n".join(documents.one_line(line, 300) for line in held.splitlines()[:30])
    wires = {n for s in ready for k in ("provides", "consumes") for n in interfaces.names(items[s][1], k)}

    def by(key: str, name: str) -> str:
        return ", ".join(s for s in ready if name in interfaces.names(items[s][1], key)) or "no Spec here"

    return dict(
        title=_cell(top.get("title")) if top else "the product",
        purpose=_cell((_real(top.get("goal")) or [str(top.get("title"))])[0], 400) if top else "The product's approved Specs, taken together.",
        scope=f"{len(ready)} of {len(scope)} Specs are at or past Spec approval."
        + (f"\n\nOut of scope, from {target}:\n\n{bound}" if bound and "TODO" not in bound else ""),
        perspective=perspective,
        stakeholders=f"Teams: {', '.join(teams) or _NONE}. Approved by: {', '.join(people) or _NONE}.",
        references="- ISO/IEC/IEEE 29148:2018, Systems and software engineering: Life cycle processes: Requirements engineering\n"
        + "\n".join(f"- {s}: {items[s][0]}" for s in [target, *scope] if s in items),
        interfaces="\n".join(f"- {n}: provided by {by('provides', n)}; consumed by {by('consumes', n)}" for n in sorted(wires))
        or f"{_NONE}: no Spec here provides or consumes a named interface.",
        excluded="\n".join(f"- {s}: {_cell(items[s][1].get('title'), 100)} ({status.spec_status(items[s][1])})" for s in scope if s not in ready) or "none",
    )


def render(root: Path, cfg: config.Config | None, target: str, template: str, *, today: dt.date | None = None) -> str:
    """The SRS of `target` (an Initiative or Epic id, or `product`) from the template text. ValueError for any other id."""
    found, _ = work_list.read_work(root, cfg)
    items = {str(d["id"]): (p, d) for p, d in found if d.get("type") in WORK_TYPES and d.get("id")}
    target = target if target in items else target.upper() if target.upper() in items else target
    scope = _scope(items, target)
    ready = [s for s in scope if status.spec_status(items[s][1]) in IN_THE_SRS]
    body, total, tested, landed, gaps = _requirements(root, cfg, items, ready)
    verification = (
        f"{total} requirements from {len(ready)} Specs. {tested} have a test command that covers them, and {landed} link a commit. "
        + (f"No test command covers {', '.join(gaps[:10])}{' and more' if len(gaps) > 10 else ''}. " if gaps else "")
        + "This document is not evidence: `aidd test --spec <ID>` runs a Spec's tests, and the runner's exit code on a commit is the proof."
    )
    values = _frame(root, items, target, scope, ready) | dict(
        today=(today or dt.date.today()).isoformat(), head=_head(root) or "no commit", target=target, requirements=body, verification=verification
    )
    return kernel_text.fill_template(template, **values).rstrip() + "\n"


def _head(root: Path) -> str:
    """The short id of the repository's HEAD commit; empty with no commit."""
    try:
        return git.rev_parse("HEAD", str(root))[:10]
    except git.GitError:
        return ""
