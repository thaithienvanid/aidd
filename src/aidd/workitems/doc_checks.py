"""The documents a Spec links, checked: each exists, a frozen one is pinned, and a design or tech spec says what it must."""

from __future__ import annotations

import re
from pathlib import Path

from aidd.kernel.documents import markdown_section
from aidd.workitems import authoring, objects, repo_reads, spec_file, spec_warnings

# What a Spec may carry in its own body instead of a linked document of that kind: the full Spec, before its detail moved to linked documents.
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
INLINE_DOC_SECTIONS = {"tech-spec": ("Alternatives considered", "Pre-mortem"), "runbook": ("Rollout",)}


def _new_hint(kind: str, sid: str) -> str:
    if kind in authoring.REPO_DOCS:
        return f"`aidd new {kind}` (the repository's one {kind}), then link it"
    if kind in authoring.DOC_TEMPLATES:
        return f"`aidd new {kind} <topic> --spec {sid}`"
    if kind == "runbook":
        return f"`aidd new runbook <ID> --title ... --spec {sid}`"
    return "write it and add an item to the Spec's `docs` list"


_LAUNCH_READINESS = re.compile(r"^#{2,4}[ \t]+Launch readiness[ \t]*$(.*?)(?=^#{1,4}[ \t]|\Z)", re.M | re.S | re.I)
_UNCHECKED_BOX = re.compile(r"^[ \t]*[-*][ \t]+\[ \][ \t]", re.M)


def runbook_readiness_warnings(path: Path, root: Path, data: dict) -> list[str]:
    """A warning for each linked runbook whose launch-readiness boxes are still unchecked while the Spec is in review,
    which is when it waits for Merge approval. The status is the stored one, as a cache, and the gate never reads this."""
    from aidd.workitems import derived_status

    if derived_status.spec_status(data) != "in_review":
        return []
    out = []
    for d in data.get("docs") or []:
        if not isinstance(d, dict) or d.get("kind") != "runbook":
            continue
        for f in objects.files_matching(root, str(d.get("path"))):
            body = _HTML_COMMENT.sub("", (root / f).read_text(encoding="utf-8", errors="replace"))
            open_boxes = sum(len(_UNCHECKED_BOX.findall(m.group(1))) for m in _LAUNCH_READINESS.finditer(body))
            if open_boxes:
                out.append(
                    f"warning: {path}: the runbook {f} has {open_boxes} unchecked launch-readiness {'box' if open_boxes == 1 else 'boxes'} and the Spec is in review; "
                    "check each one, or say in the runbook why a box does not apply"
                )
    return out


def doc_findings(path: Path, text: str, data: dict) -> list[str]:
    """The linked documents, checked: every doc and local decision path exists (errors); a frozen doc names its Spec
    and holds no TODO, a test plan's Acceptance ids match the Spec's and its commands' `covers`, and the required-docs
    matrix (warnings). The paths are the repository's own only for a Spec in its Specs folder: a Spec elsewhere (an
    example, a fixture) gets the matrix alone."""
    root = spec_warnings.repo_root_of(path)
    if root is None:
        return []
    out: list[str] = []
    cfg = repo_reads.config_at(root)
    sid = str(data.get("id"))
    frozen = set(spec_file.frozen_docs(data))
    ids = spec_warnings.acceptance_ids(text)
    covered = {i for c in (data.get("tests") or {}).get("commands", []) for i in c.get("covers") or []}
    here = path.resolve().is_relative_to((root / (cfg.specs_dir if cfg else "specs")).resolve())
    for d in data.get("docs") or [] if here else []:
        files = objects.files_matching(root, d["path"])
        if not files:
            out.append(f"{path}: docs {d['path']!r} ({d['kind']}) does not exist; write it ({_new_hint(d['kind'], sid)}) or drop the entry")
            continue
        for f in files if d["path"] in frozen else []:
            body = (root / f).read_text(encoding="utf-8", errors="replace")
            if "TODO" in body:
                out.append(f"warning: {path}: frozen doc {f} still contains TODO placeholders; Spec approval would freeze them")
            if sid not in body:
                out.append(f"warning: {path}: frozen doc {f} does not name {sid}; start it with a back-link to the Spec")
        if d["kind"] == "test-plan":
            plan = list(
                dict.fromkeys(
                    spec_warnings.ACCEPTANCE_ID.findall(
                        markdown_section((root / files[0]).read_text(encoding="utf-8", errors="replace"), "Acceptance criteria")
                    )
                )
            )
            out += [f"warning: {path}: test plan {files[0]} lists {i}, which the Spec's '## Acceptance' does not have" for i in plan if i not in ids]
            out += [f"warning: {path}: Acceptance item {i} is missing from the test plan {files[0]}" for i in ids if i not in plan]
            out += [
                f"warning: {path}: test plan {files[0]} maps {i}, but no test command covers it; add it to a command's covers"
                for i in plan
                if i in ids and i not in covered
            ]
        if d["kind"] == "tech-spec":
            # The default home of testing: the tech spec's Test strategy maps the Spec's own ids, never new ones.
            mapped = list(
                dict.fromkeys(
                    spec_warnings.ACCEPTANCE_ID.findall(markdown_section((root / files[0]).read_text(encoding="utf-8", errors="replace"), "Test strategy"))
                )
            )
            out += [
                f"warning: {path}: the Test strategy in {files[0]} lists {i}, which the Spec's '## Acceptance' does not have" for i in mapped if i not in ids
            ]
            out += [
                f"warning: {path}: the Test strategy in {files[0]} maps {i}, but no test command covers it; add it to a command's covers"
                for i in mapped
                if i in ids and i not in covered
            ]
    for ref in data.get("adrs") or [] if here else []:
        if "://" not in ref and "/" in ref and not objects.files_matching(root, ref):
            out.append(f"{path}: adrs {ref!r} does not exist; link an ADR in the repository, or a URL")
    if (root / authoring.REPO_TOKENS).is_file():
        out += [
            f"warning: {path}: design.files hold their own tokens file {f}, but the repository's design system is {authoring.REPO_TOKENS}. "
            "Use its tokens, and propose a token change as a separate change, or the two drift apart"
            for f in authoring.own_tokens(root, data)
        ]
    out += runbook_readiness_warnings(path, root, data)
    linked = {d["kind"] for d in data.get("docs") or []} | ({"design-spec"} if (data.get("design") or {}).get("files") else set())
    for kind, level, why in authoring.required_docs(data, len(ids), cfg):
        inline = INLINE_DOC_SECTIONS.get(kind)
        if level != "warn" or kind in linked or (inline and all(markdown_section(text, h) for h in inline)):
            continue
        own = f", or write {' and '.join(repr('## ' + h) for h in inline)} in the Spec" if inline else ""
        out.append(f'warning: {path}: the Spec ({why}) links no {kind} doc; {_new_hint(kind, sid)}{own} (`docs.required.{kind}: "off"` turns this off)')
    return out


def design_specs(path: Path, data: dict) -> list[tuple[str, str]]:
    """The design specs a Spec links (its Markdown `design-spec` docs), as (path, text), those that exist."""
    root = spec_warnings.repo_root_of(path)
    if root is None:
        return []
    rels = [
        f for d in data.get("docs") or [] if isinstance(d, dict) and d.get("kind") == "design-spec" for f in objects.files_matching(root, str(d.get("path")))
    ]
    return [(rel, (root / rel).read_text(encoding="utf-8", errors="replace")) for rel in rels if rel.endswith(".md")]


def tech_specs(path: Path, data: dict) -> list[tuple[str, str]]:
    """The tech-spec docs a Spec links, as (path, text), those that exist."""
    root = spec_warnings.repo_root_of(path)
    if root is None:
        return []
    found = [
        f for d in data.get("docs") or [] if isinstance(d, dict) and d.get("kind") == "tech-spec" for f in objects.files_matching(root, str(d.get("path")))
    ]
    return [(f, (root / f).read_text(encoding="utf-8", errors="replace")) for f in found]


# Below this many words, a Design section has not said what it is there to say.
DESIGN_PROSE_WORDS = 40


def has_diagram(text: str) -> bool:
    """A Mermaid block or an image anywhere in the document."""
    return "```mermaid" in text or bool(re.search(r"!\[[^\]]*\]\(", text))
