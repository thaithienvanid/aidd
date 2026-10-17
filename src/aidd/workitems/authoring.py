"""Write work items and their documents from templates (`aidd new`): a Spec, Epic, Initiative, or proposal, a document a
Spec links, a repository document, and a contract; and which documents a Spec needs.
"""

from __future__ import annotations

import datetime as dt
import os
import re
from dataclasses import dataclass
from pathlib import Path

from aidd import config
from aidd.kernel import documents, globs, resources, strict_yaml
from aidd.kernel import text as kernel_text
from aidd.workitems import item_folder, objects, spec_file

OBSERVE_BLOCK = (
    "\n\nobserve:                          # required on major (and on normal under audited)\n"
    '  window: "24h"\n'
    '  signals: "TODO: dashboard or SLO"\n'
    '  rollback_trigger: "TODO: condition that starts the rollback"'
)

ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")


def spec_template(route: str, full: bool = False) -> str:
    """The Spec template `aidd new spec` writes: the short one (Intent, Context, Acceptance, Design, Policy conflicts, Rollback) for a normal Spec,
    the full one for `--full`, for major (whose Alternatives, Pre-mortem, and diagram `aidd validate` asks for), and for
    an emergency backfill."""
    return "spec" if full or route in ("major", "emergency") else "spec-short"


@dataclass(frozen=True)
class NewObject:
    """One work item for `new_object` to write: its kind, id, and title, and the options that kind reads. The CLI and
    the issue and plan imports fill it; an option one kind adds is one field here."""

    kind: str
    id: str
    title: str
    route: str = "normal"
    ctype: str = "feat"
    owner_team: str = ""
    parent: str = ""
    specs_dir: str = "specs"
    today: dt.date | None = None
    audience: str = "client"
    addressee: str = ""
    proposals_dir: str = "proposals"
    spec: str = ""
    scope: list[str] | None = None
    dimensions: list[str] | None = None
    irreversible: bool = False
    full: bool = False
    base: str = ""


# A branch a Spec ships into (`base`): a plain branch name, never an option or a revision expression.
BASE_PATTERN = re.compile(r"^(?!-)(?!.*\.\.)[A-Za-z0-9._/-]{1,200}\Z")


def _check_names(item: NewObject) -> None:
    """The id, the Spec it names, and the base it ships into, each a plain name, or ValueError."""
    if not ID_PATTERN.match(item.id):
        raise ValueError(f"id {item.id!r} must be letters, digits, and . _ : - (such as SPEC-42), at most 64 characters")
    if item.spec and not ID_PATTERN.match(item.spec):
        raise ValueError(f"spec {item.spec!r} must be a Spec id, such as INC-481")
    if item.base and (item.kind != "spec" or not BASE_PATTERN.match(item.base)):
        raise ValueError(f"--base {item.base!r}: a Spec's base is a branch name, such as goal/booking")


def _epic_goal(root: Path, item: NewObject) -> str:
    """The goal branch a new Spec ships into when its parent Epic ships batched, else ""."""
    from aidd.workitems import small_goals

    path = root / item.specs_dir / f"{item.parent}.md"
    try:
        epic = documents.split_front_matter(path.read_text(encoding="utf-8"), path.as_posix())[0] if path.is_file() else {}
    except documents.DocumentError:
        return ""
    return small_goals.goal_branch(item.parent) if epic.get("kind") == "epic" and small_goals.ships(epic) == "batched" else ""


def new_object(root: Path, item: NewObject) -> Path:
    today, scope = item.today, item.scope
    _check_names(item)
    if item.parent and item.kind in objects.PARENT_KIND:
        found = objects.kind_of(root, item.parent, (item.specs_dir, item.proposals_dir))
        if found and (why := objects.parent_kind_error(item.kind, item.parent, found)):
            raise ValueError(f"{why}; name {objects.KIND_NAMES[objects.PARENT_KIND[item.kind]]} as --parent")
    today = today or dt.date.today()
    tpl = (resources.data_dir("skill") / "assets" / f"{spec_template(item.route, item.full) if item.kind == 'spec' else item.kind}.md").read_text(
        encoding="utf-8"
    )
    values = dict(id=item.id, title=item.title, owner_team=item.owner_team or "TODO", today=today.isoformat())
    if item.kind == "proposal":
        values |= dict(audience=item.audience, addressee=item.addressee or "TODO: who receives it and decides")
    elif item.kind in objects.OPS_DIRS:
        values |= dict(spec=item.spec or ("none" if item.kind == "runbook" else "TODO"))
    else:
        values |= dict(route=item.route, type=item.ctype, trace_id=item.id.lower())
    text = kernel_text.fill_template(tpl, **values)
    if item.parent and item.kind not in objects.OPS_DIRS:
        text = text.replace(f"kind: {item.kind}\n", f"kind: {item.kind}\nparent: {strict_yaml.scalar(item.parent)}\n", 1)
    base = item.base or (_epic_goal(root, item) if item.kind == "spec" and item.parent else "")
    if base:
        text = text.replace("kind: spec\n", f"kind: spec\nbase: {strict_yaml.scalar(base)}\n", 1)
    if item.kind == "spec":
        # `aidd new spec --paths`: the planned paths are the first Task's scope, and the declared risk is the Spec's.
        from aidd.kernel.repo_paths import looks_like_test

        tests = [s for s in scope or [] if looks_like_test(s)]
        scope = [s for s in scope or [] if not looks_like_test(s)]
        if scope:
            text = re.sub(r"(?m)^( +)scope: \[[^\]\n]*\]", lambda m: f"{m.group(1)}scope: {strict_yaml.flow(scope)}", text, count=1)
        if tests:  # a Task's scope never holds a test file; the Spec freezes it in tests.files
            text = re.sub(r'(?m)^( +)files: \["tests/TODO"\]', lambda m: f"{m.group(1)}files: {strict_yaml.flow(tests)}", text, count=1)
        if item.dimensions:
            text = re.sub(r"(?m)^( +)dimensions: \[\]", lambda m: f"{m.group(1)}dimensions: {strict_yaml.flow(item.dimensions)}", text, count=1)
        if item.irreversible:
            text = re.sub(r"(?m)^( +)reversible: true", r"\1reversible: false", text, count=1)
    if item.kind == "spec" and item.route in ("major", "emergency"):
        # Observe is required on major (and on normal under audited, where the gate asks for it).
        block = OBSERVE_BLOCK
        if item.route == "emergency":
            due = (today + dt.timedelta(days=2)).isoformat()
            block += f'\n\nemergency:\n  severity: sev2\n  kind: outage\n  commander: "@TODO"\n  incident: INC-TODO\n  review_due: "{due}"'
        head, sep, rest = text.partition("\n---\n")
        text = head + block + sep + rest
    # A proposal gets its own folder: each role writes its part beside it, and one addressee's material stays apart.
    if item.kind == "proposal":
        path = root / item.proposals_dir / item.id / "proposal.md"
    elif item.kind in objects.OPS_DIRS:
        path = root / objects.OPS_DIRS[item.kind] / f"{item.id}.md"
    else:
        path = root / item.specs_dir / f"{item.id}.md"
    if path.exists():
        raise FileExistsError(f"{path} exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# The linked documents `aidd new <kind> <topic> --spec <ID>` writes, and the template each starts from. The design-spec doc
# is the design spec; `--prototype` writes its HTML prototype instead (PROTOTYPE), one file per Spec or flow in the design
# folder (`<docs_dir>/design/<area or Spec id>/prototype.html`), linked as the same kind.
DOC_TEMPLATES: dict[str, str] = {
    "tech-spec": "tech-spec.md",
    "test-plan": "test-plan.md",
    "adr": "adr.md",
    "threat-model": "threat-model.md",
    "authz": "authz-matrix.md",
    "design-spec": "design-spec.md",
    "api": "api.md",
    "slo": "slo.md",
    "compliance": "compliance.md",
    "analytics": "tracking-plan.md",
    "migration": "migration-plan.md",
    "acceptance": "acceptance.md",
    "feedback": "feedback.md",
}
PROTOTYPE = "prototype.html"
# Documents humans keep filling after Spec approval: linked as living (`frozen: false`), only checked to exist. A
# threat model is one per component and outlives each Spec: a Spec freezes only its delta, in its Design.
LIVING_DOCS: frozenset[str] = frozenset({"slo", "acceptance", "data-map", "vendors", "threat-model"})
# Documents that belong to no one Spec, each in its own folder under `<docs_dir>`: the feedback log is a living record
# of what customers said after launch.
UNLINKED_DOCS: frozenset[str] = frozenset({"feedback"})
UNLINKED_FOLDERS = {"feedback": "feedback"}


# One per repository, never per Spec: `aidd new <kind>` writes each file (repository path, with {docs} for the configured
# docs folder, and its template). The glossary holds the project's terms, one meaning each, for every writer. Living documents: each later change to one is a change of its own. A Spec that
# touches personal data or a vendor links the data map or the vendor register as a living `docs` entry. The design
# system's build script (dependency-free Node) writes its CSS and DESIGN.md's token mirror, and checks them for drift.
REPO_DOCS: dict[str, tuple[tuple[str, str], ...]] = {
    "design-system": (("DESIGN.md", "DESIGN.md"), ("design/tokens.json", "tokens.json"), ("design/build.mjs", "design-build.mjs")),
    "architecture": (("{docs}/architecture/README.md", "architecture.md"),),
    "data-map": (("{docs}/data-map.md", "data-map.md"),),
    "vendors": (("{docs}/vendors.md", "vendors.md"),),
    "glossary": (("{docs}/GLOSSARY.md", "glossary.md"),),
    # The project's guide for every agent: the team's, written around aidd's own section that `aidd init` puts there.
    "agents": (("AGENTS.md", "agents.md"),),
}
# The marker of aidd's own section in AGENTS.md (setup/adoption.AGENTS_MARK): the team's guide goes above it.
SECTION_MARK = "<!-- aidd -->"
# The engagement's documents, in the accepted proposal's folder: the contract (a statement of work), then each change
# order to it, `change-orders/CO-<n>.md`, from the same template family.
CONTRACT = "contract.md"
CHANGE_ORDERS = "change-orders"
# Every kind `aidd new` writes besides the Spec and its containers, the proposal, and the postmortem.
DOC_KINDS_NEW: tuple[str, ...] = (*DOC_TEMPLATES, "runbook", *REPO_DOCS, "contract", "exploration")
# The design system's tokens: a Spec's design files that hold their own tokens beside it drift from it.
REPO_TOKENS = "design/tokens.json"


def new_repo_doc(root: Path, *, kind: str, title: str = "", docs_dir: str = "docs", today: dt.date | None = None) -> list[Path]:
    """Write a repository's design system or architecture overview from its templates; refuse when any file exists.
    AGENTS.md is the one that may exist already, holding only aidd's own section (`aidd init`): the guide goes above it."""
    targets = [(root / rel.replace("{docs}", docs_dir), tpl) for rel, tpl in REPO_DOCS[kind]]
    if kind == "agents":
        return [_project_guide(root, targets[0][0])]
    taken = [p for p, _ in targets if p.exists()]
    if taken:
        raise FileExistsError(f"{taken[0].relative_to(root).as_posix()} exists: the repository has one {kind}; change it in its own change")
    values = dict(title=title or root.resolve().name, today=(today or dt.date.today()).isoformat())
    for path, tpl in targets:
        text = (resources.data_dir("skill") / "assets" / tpl).read_text(encoding="utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(kernel_text.fill_template(text, **values) if tpl.endswith(".md") else text, encoding="utf-8")
    return [p for p, _ in targets]


def _project_guide(root: Path, path: Path) -> Path:
    """AGENTS.md with the project's guide (assets/agents.md) above aidd's own section; refuse when it holds one already."""
    guide = (resources.data_dir("skill") / "assets" / "agents.md").read_text(encoding="utf-8").strip("\n")
    current = path.read_text(encoding="utf-8") if path.is_file() else ""
    head, mark, rest = current.partition(SECTION_MARK)
    if head.strip() not in ("", "# Agents"):
        raise FileExistsError(f"{path.relative_to(root).as_posix()} holds the project's guide already: change it in its own change")
    path.write_text(f"# Agents\n\n{guide}\n\n" + (f"{mark}{rest}" if mark else ""), encoding="utf-8")
    return path


def new_contract(root: Path, proposal_id: str, *, proposals_dir: str = "proposals", today: dt.date | None = None) -> Path:
    """The engagement's contract in the proposal's folder, from its template; once it exists, the next change order."""
    folder = root / proposals_dir / proposal_id
    if not ID_PATTERN.match(proposal_id) or not (folder / "proposal.md").is_file():
        raise ValueError(f"no proposal {proposal_id} in {proposals_dir}/: `aidd new contract <proposal id>` writes the contract of an accepted proposal")
    values = dict(proposal=proposal_id, today=(today or dt.date.today()).isoformat())
    if not (folder / CONTRACT).exists():
        path, tpl = folder / CONTRACT, "contract.md"
    else:
        taken = [int(m.group(1)) for p in (folder / CHANGE_ORDERS).glob("CO-*.md") for m in [re.fullmatch(r"CO-(\d+)\.md", p.name)] if m]
        number = max(taken, default=0) + 1
        path, tpl, values["number"] = folder / CHANGE_ORDERS / f"CO-{number}.md", "change-order.md", str(number)
    text = kernel_text.fill_template((resources.data_dir("skill") / "assets" / tpl).read_text(encoding="utf-8"), **values)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def own_tokens(root: Path, data: dict) -> list[str]:
    """The tokens files a Spec's design files hold, other than the repository's own."""
    found = [f for pattern in (data.get("design") or {}).get("files") or [] for f in objects.files_matching(root, str(pattern))]
    return sorted({f for f in found if f != REPO_TOKENS and re.search(r"(?:^|[/.])tokens(?:\.json)?$", f.lower())})


def link_doc(spec_path: Path, kind: str, rel: str, *, frozen: bool = True) -> None:
    """Append an entry to the Spec's `docs` list in its front matter; refuse when the result would not parse."""
    text = spec_path.read_text(encoding="utf-8").lstrip("﻿")
    m = documents.FRONT_MATTER.match(text)
    if not m:
        raise ValueError(f"{spec_path.as_posix()}: missing YAML front matter between `---` lines")
    entry = {"kind": kind, "path": rel} | ({} if frozen else {"frozen": False})
    try:
        front = strict_yaml.append_item(m.group(1), "docs", entry)
        new = text[: m.start(1)] + front + text[m.end(1) :].lstrip("\n")
        documents.split_front_matter(new, spec_path.as_posix())
    except (ValueError, documents.DocumentError) as exc:
        raise ValueError(f"{spec_path.as_posix()}: cannot add a `docs` entry ({exc}); write docs as a block list, one `- kind:` item per doc") from exc
    spec_path.write_text(new, encoding="utf-8")


@dataclass(frozen=True)
class NewDoc:
    """One linked document for `new_doc` to write: its kind and topic, the Spec it belongs to, and where it goes."""

    kind: str
    topic: str
    spec_id: str = ""
    area: str = ""
    title: str = ""
    docs_dir: str = "docs"
    specs_dir: str = "specs"
    today: dt.date | None = None
    link: bool = True
    prototype: bool = False


def new_doc(root: Path, doc: NewDoc) -> tuple[Path, Path | None]:
    """Write a linked document from its template and link it from the Spec (unless `link` is false: a specialist
    writes its own doc and the Spec's writer adds the `docs` entry, one writer per file): an ADR as `<docs_dir>/adr/NNNN-<topic>.md`
    with the next number, a project-wide record; a threat model as `<docs_dir>/security/threat-models/<component>.md`,
    one living model per component that a later Spec only links again; anything else in the work item's own folder, beside it: the design spec's
    prototype (`prototype`) as `<specs_dir>/<Spec id>/design/prototype.html` (a second flow, `--area <flow>`, in
    `design/<flow>/`), and any other document as `<specs_dir>/<area or Spec id>/<kind>-<topic>.md`. The document's header names the Spec (its back-link). Returns the document and the Spec.
    A feedback log has no Spec: it is written as `<docs_dir>/feedback/<topic>.md`, and the Spec returned is None."""
    if doc.kind not in DOC_TEMPLATES:
        raise ValueError(f"no template for {doc.kind!r}; one of {', '.join(DOC_TEMPLATES)}")
    if doc.area and not ID_PATTERN.match(doc.area):
        raise ValueError(f"area {doc.area!r} must be letters, digits, and . _ : - (such as checkout)")
    name = kernel_text.slug(doc.topic)
    values = dict(title=doc.title or doc.topic, today=(doc.today or dt.date.today()).isoformat())
    if doc.prototype and doc.kind != "design-spec":
        raise ValueError("--prototype writes the design spec's HTML prototype: `aidd new design-spec <topic> --spec <ID> --prototype`")
    tpl = (resources.data_dir("skill") / "assets" / (PROTOTYPE if doc.prototype else DOC_TEMPLATES[doc.kind])).read_text(encoding="utf-8")
    if doc.kind in UNLINKED_DOCS:
        path = root / doc.docs_dir / UNLINKED_FOLDERS[doc.kind] / f"{name}.md"
        if path.exists():
            raise FileExistsError(f"{path} exists")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(kernel_text.fill_template(tpl, **values), encoding="utf-8")
        return path, None
    spec_path = objects.find_spec_by_id(root, doc.specs_dir, doc.spec_id)
    values |= dict(spec=doc.spec_id, number="")
    if doc.kind == "adr":
        folder = root / doc.docs_dir / "adr"
        taken = [int(m.group(1)) for p in (folder.iterdir() if folder.is_dir() else []) for m in [re.match(r"(\d{4})-", p.name)] if m]
        number = max(taken, default=0) + 1
        path, values["number"] = folder / f"{number:04d}-{name}.md", f"{number:04d}"
    elif doc.prototype:
        path = root / doc.specs_dir / doc.spec_id / item_folder.DESIGN_FOLDER / doc.area / PROTOTYPE  # a second flow: --area
    elif doc.kind == "threat-model":
        # The component's living model: written once, then each Spec that changes the component links it again.
        path = root / doc.docs_dir / spec_file.THREAT_MODELS / f"{name}.md"
        if path.exists():
            rel = path.relative_to(root).as_posix()
            linked = documents.split_front_matter(spec_path.read_text(encoding="utf-8"), spec_path.as_posix())[0].get("docs") or []
            if doc.link and not any(isinstance(d, dict) and d.get("path") == rel for d in linked):
                link_doc(spec_path, doc.kind, rel, frozen=False)
            return path, spec_path
    else:
        path = root / doc.specs_dir / (doc.area or doc.spec_id) / f"{doc.kind}-{name}.md"
    if path.exists():
        more = "; a second flow gets its own folder: `--area <flow>`" if doc.prototype else ""
        raise FileExistsError(f"{path} exists{more}")
    values["spec_link"] = Path(os.path.relpath(spec_path, path.parent)).as_posix()
    text = kernel_text.fill_template(tpl, **values)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if doc.link:
        link_doc(spec_path, doc.kind, path.relative_to(root).as_posix(), frozen=doc.kind not in LIVING_DOCS)
    return path, spec_path


def required_docs(data: dict, acceptance: int, cfg: config.Config | None) -> list[tuple[str, str, str]]:
    """The documents the required-docs matrix asks this Spec for, as (kind, level, why): level `warn` on the routes a
    rule warns on, `suggest` on those it only suggests. Advice only: `aidd validate` warns, the gate never reads it."""
    route = data.get("route")
    matrix = cfg.docs_required if cfg is not None else config.default_docs_required()
    out = []
    for kind, rule in matrix.items():
        level = "warn" if route in rule.get("routes", []) else "suggest" if route in rule.get("suggest", []) else None
        if level is None:
            continue
        why = _doc_conditions(rule, data, acceptance, cfg)
        if why is None:
            continue
        if rule.get("any_of"):
            alt = next((w for w in (_doc_conditions(c, data, acceptance, cfg) for c in rule["any_of"]) if w is not None), None)
            if alt is None:
                continue
            why += alt
        out.append((kind, level, ", ".join([f"route {route}", *why])))
    return out


def _doc_conditions(rule: dict, data: dict, acceptance: int, cfg: config.Config | None) -> list[str] | None:
    """Why a doc rule's conditions hold for this Spec (every one must), or None when one does not."""
    risk = data.get("risk") or {}
    why = []
    if rule.get("dimensions"):
        hit = sorted(set(risk.get("dimensions") or []) & set(rule["dimensions"]))
        if not hit:
            return None
        why.append(f"risk {', '.join(hit)}")
    if rule.get("types"):
        if data.get("type") not in rule["types"]:
            return None
        why.append(f"type {data.get('type')}")
    if rule.get("paths"):
        scopes = [s for task in data.get("tasks") or [] for s in task.get("scope") or [] if isinstance(s, str)]
        if not any(globs.match_any(rule["paths"], s) or globs.match_any(rule["paths"], globs.sample_path(s)) for s in scopes):
            return None
        why.append("a matching path in scope")
    if rule.get("min_acceptance"):
        if acceptance < rule["min_acceptance"]:
            return None
        why.append(f"{acceptance} Acceptance items")
    if rule.get("profiles"):
        if cfg is None or cfg.profile not in rule["profiles"]:
            return None
        why.append(f"profile {cfg.profile}")
    if "compliance" in rule:
        on = config.project_compliance(cfg)["on"]
        if on is not rule["compliance"]:
            return None
        why.append("compliance on" if on else "compliance off")
    for key, said in (("uat", "uat"), ("hypothesis", "a hypothesis"), ("reversible", "reversible")):
        if key not in rule:
            continue
        value = risk.get("reversible", True) if key == "reversible" else bool(data.get(key))
        if value is not rule[key]:
            return None
        why.append(said if rule[key] else f"not {said}")
    return why
