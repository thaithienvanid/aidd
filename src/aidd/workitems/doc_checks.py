"""The documents a Spec links, checked: each exists, a frozen one is pinned, and a design or tech spec says what it must."""

from __future__ import annotations

import re
from pathlib import Path

from aidd import config
from aidd.kernel import command_names, globs
from aidd.kernel.documents import markdown_section
from aidd.workitems import authoring, living_docs, objects, placeholders, repo_reads, spec_file, spec_warnings, status

# What a Spec may carry in its own body instead of a linked document of that type: the full Spec, before its detail moved to linked documents.
# A comment, or one that never closes, which hides the rest: one scan, however many `<!--` a crafted text holds.
_HTML_COMMENT = placeholders.HTML_COMMENT
INLINE_DOC_SECTIONS = {"tech-spec": ("Alternatives considered", "Pre-mortem"), "runbook": ("Rollout",)}
# An id in a table's Acceptance id column, alone (`A4`) or named for its Spec (`SPEC-7/A4`), as a living doc shared by
# several Specs writes it.
CITED_ID = re.compile(r"(?:\b([A-Za-z][\w.-]*-\d+)/)?\b(A[1-9][0-9]{0,3})\b")


def _new_hint(doc_type: str, sid: str, living: bool = False, docs_dir: str = "docs") -> str:
    spec = command_names.quoted(sid) or "<ID>"  # a Spec's id is the file's text until it passes the id pattern
    if doc_type in authoring.REPO_DOCS:
        return f"`aidd new {doc_type}` (the repository's one {doc_type}), then link it"
    if doc_type in authoring.DOC_TEMPLATES:
        if living:
            return f"`aidd new {doc_type} <component> --living --spec {spec}`, which writes {docs_dir}/{spec_file.TEST_PLANS}/<component>.md"
        return f"`aidd new {doc_type} <topic> --spec {spec}`"
    if doc_type == "runbook":
        return f"`aidd new runbook <ID> --title ... --spec {spec}`"
    return "write it and add an item to the Spec's `docs` list"


_LAUNCH_READINESS = re.compile(r"^#{2,4}[ \t]+Launch readiness[ \t]*$(.*?)(?=^#{1,4}[ \t]|\Z)", re.M | re.S | re.I)
_UNCHECKED_BOX = re.compile(r"^[ \t]*[-*][ \t]+\[ \][ \t]", re.M)


def launch_readiness_warnings(path: Path, text: str, data: dict) -> list[str]:
    """A warning for the Spec's own launch-readiness boxes (under its `## Rollout`) that are still unchecked while the
    Spec is in review, which is when the agent asks for Merge approval."""
    if status.spec_status(data) != "in_review":
        return []
    body = _HTML_COMMENT.sub("", text)
    open_boxes = sum(len(_UNCHECKED_BOX.findall(m.group(1))) for m in _LAUNCH_READINESS.finditer(body))
    if not open_boxes:
        return []
    return [
        f"warning: {path}: the Spec has {open_boxes} unchecked launch-readiness {'box' if open_boxes == 1 else 'boxes'} in its Rollout and is in review; "
        "check each one, or say in the Spec why a box does not apply"
    ]


def _written(data: dict) -> list[dict]:
    """The Spec's `docs` entries that name a document a role writes: every one but a `design-files` entry, which lists mockups and
    flows. Those hold no placeholder or back-link to find, and no file has to be there before the design is drawn."""
    return [d for d in data.get("docs") or [] if d.get("type") != objects.DESIGN_FILES]


def _linked_types(docs: list[dict]) -> set[str]:
    """The types the Spec links, where design files stand in for a design spec."""
    types = {d["type"] for d in docs}
    return types | {"design-spec"} if objects.DESIGN_FILES in types else types


def doc_findings(path: Path, text: str, data: dict) -> list[str]:
    """The linked documents, checked: every doc and local decision path exists (errors); a doc holds no placeholder, a frozen doc names its Spec, a test plan's
    Acceptance ids match the Spec's and its commands' `covers`, and the required-docs matrix (warnings). The paths are the repository's own only for a Spec in its Specs folder: a Spec elsewhere (an
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
    here = path.resolve().is_relative_to((root / (cfg or config.EMPTY).specs_dir).resolve())
    for d in _written(data) if here else []:
        files = objects.files_matching(root, d["path"])
        if not files:
            out.append(f"{path}: docs {d['path']!r} ({d['type']}) does not exist; write it ({_new_hint(d['type'], sid)}) or drop the entry")
            continue
        for f in files:
            body = objects.document_text(root, f)
            if left := placeholders.found(body, markdown=f.endswith(".md")):
                out.append(placeholders.finding(path, f, left, frozen=d["path"] in frozen))
            if d["path"] in frozen and sid not in body:
                out.append(f"warning: {path}: frozen doc {f} does not name {sid}; start it with a back-link to the Spec")
        if d["type"] == "test-plan" and d["path"] in frozen:  # a living plan holds many Specs' ids: the generated trace checks those
            plan = list(dict.fromkeys(spec_warnings.ACCEPTANCE_ID.findall(markdown_section(objects.document_text(root, files[0]), "Test approach"))))
            out += [f"warning: {path}: test plan {files[0]} lists {i}, which the Spec's '## Acceptance' does not have" for i in plan if i not in ids]
            out += [f"warning: {path}: Acceptance item {i} is missing from the test plan {files[0]}" for i in ids if i not in plan]
            out += [
                f"warning: {path}: test plan {files[0]} maps {i}, but no test command covers it; add it to a command's covers"
                for i in plan
                if i in ids and i not in covered
            ]
    out += cited_id_warnings(path, root, data, ids) if here else []
    for ref in data.get("adrs") or [] if here else []:
        if "://" not in ref and "/" in ref and not objects.files_matching(root, ref):
            out.append(f"{path}: adrs {ref!r} does not exist; link an ADR in the repository, or a URL")
    if (root / authoring.REPO_TOKENS).is_file():
        out += [
            f"warning: {path}: the design files hold their own tokens file {f}, but the repository's design system is {authoring.REPO_TOKENS}. "
            "Use its tokens, and propose a token change as a separate change, or the two drift apart"
            for f in authoring.own_tokens(root, data)
        ]
    out += launch_readiness_warnings(path, text, data)
    docs_dir = (cfg or config.EMPTY).docs_dir
    if here:
        out += living_docs.threat_delta_warnings(path, root, data, [text, *(t for _, t in tech_specs(path, data))], docs_dir)
        out += living_docs.event_warnings(path, root, data, authoring.REPO_DOCS["metrics-dictionary"][0][0].replace("{docs}", docs_dir))
        out += living_docs.slo_warnings(path, root, data, globs.under(docs_dir, authoring.unlinked_folders()["service-card"]))
    docs = [d for d in data.get("docs") or [] if isinstance(d, dict)]
    linked = _linked_types(docs)
    for ask in authoring.required_docs(data, cfg):
        inline = INLINE_DOC_SECTIONS.get(ask.doc_type)
        answered = linked if ask.living is None else {d["type"] for d in docs if (d.get("frozen") is False) == ask.living}
        if ask.level != "warn" or ask.doc_type in answered or (inline and all(markdown_section(text, h) for h in inline)):
            continue
        own = f", or write {' and '.join(repr('## ' + h) for h in inline)} in the Spec" if inline else ""
        out.append(
            f"warning: {path}: the Spec ({ask.why}) links no {'living ' if ask.living else 'frozen ' if ask.living is False else ''}{ask.doc_type} doc"
            f"{' (a living plan does not stand in for it)' if ask.living is False and ask.doc_type in linked else ''}; "
            f"{_new_hint(ask.doc_type, sid, bool(ask.living), (cfg or config.EMPTY).docs_dir)}{own} (`docs.disabled.{ask.doc_type}: <reason>` turns this off)"
        )
    return out


def cited_id_warnings(path: Path, root: Path, data: dict, ids: list[str]) -> list[str]:
    """A warning for each Acceptance id a linked doc's table cites that the Spec does not have: Acceptance ids come from
    the Spec only, so a specialist cites one and never coins one. A frozen doc is this Spec's, so a bare id counts; a
    living doc is shared, so only an id named for this Spec does."""
    sid, frozen, out = str(data.get("id")), set(spec_file.frozen_docs(data)), []
    for d in _written(data):
        for f in objects.files_matching(root, d["path"]) if str(d["path"]).endswith(".md") else []:
            body = objects.document_text(root, f)
            cells = [v for row in living_docs.table_rows(body) for k, v in row.items() if k.startswith("acceptance id")]
            cited = [m.group(2) for c in cells for m in CITED_ID.finditer(c) if m.group(1) == sid or (m.group(1) is None and d["path"] in frozen)]
            out += [
                f"warning: {path}: {f} names {i}, which the Spec's '## Acceptance' does not have; cite the Spec's own ids, "
                "and ask the Spec's writer for a new item"
                for i in dict.fromkeys(cited)
                if i not in ids
            ]
    return out


def design_specs(path: Path, data: dict) -> list[tuple[str, str]]:
    """The design specs a Spec links (its Markdown `design-spec` docs), as (path, text), those that exist."""
    root = spec_warnings.repo_root_of(path)
    if root is None:
        return []
    rels = [
        f for d in data.get("docs") or [] if isinstance(d, dict) and d.get("type") == "design-spec" for f in objects.files_matching(root, str(d.get("path")))
    ]
    return [(rel, objects.document_text(root, rel)) for rel in rels if rel.endswith(".md")]


def tech_specs(path: Path, data: dict) -> list[tuple[str, str]]:
    """The tech-spec docs a Spec links, as (path, text), those that exist."""
    root = spec_warnings.repo_root_of(path)
    if root is None:
        return []
    found = [
        f for d in data.get("docs") or [] if isinstance(d, dict) and d.get("type") == "tech-spec" for f in objects.files_matching(root, str(d.get("path")))
    ]
    return [(f, objects.document_text(root, f)) for f in found]


# Below this many words, a Design section has not said what it is there to say.
DESIGN_PROSE_WORDS = 40


def has_diagram(text: str) -> bool:
    """A Mermaid block or an image anywhere in the document."""
    return "```mermaid" in text or bool(re.search(r"!\[[^\]]*\]\(", text))
