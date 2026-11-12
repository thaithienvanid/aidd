"""Write work items and their documents from templates (`aidd new`): a Spec, Intent, or proposal, a document a
Spec links, a repository document, and a contract; and which documents a Spec needs.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import functools
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from aidd import config
from aidd.kernel import documents, globs, regular_files, resources, strict_yaml
from aidd.kernel import text as kernel_text
from aidd.workitems import backlog, item_folder, living_docs, manifest_sections, objects, repo_reads, slice_start, spec_file, srs, status
from aidd.workitems.ids import is_id

OBSERVE_BLOCK = (
    "\n\nobserve:                          # required on major\n"
    '  window: "24h"\n'
    '  signals: "TODO: dashboard or SLO"\n'
    '  rollback_trigger: "TODO: condition that starts the rollback"'
)

# A project's own templates: `aidd new <type>` starts from `<docs.dir>/templates/<type>.md` when it exists, else from the
# skill's asset. They live beside the linked docs, because git ignores every folder in `.aidd/` (config.OUTPUT_IGNORE).
TEMPLATES_FOLDER = "templates"


def templates_dir(root: Path) -> str:
    """The repo-relative folder of the project's own templates: `templates/` in the config's `docs.dir`."""
    cfg = repo_reads.config_at(root)
    return f"{(cfg or config.EMPTY).docs_dir}/{TEMPLATES_FOLDER}"


def template_text(root: Path, name: str, asset: str) -> str:
    """The text `aidd new` starts from: the project's `<docs.dir>/templates/<name>.md` when it exists, else the skill's
    `asset`. `aidd validate` checks the result as it checks any other, so a template can add sections but never drop a
    required one. A project template that resolves outside that folder, such as through a symlink, is refused."""
    if not re.fullmatch(r"[a-z][a-z0-9-]*", name):
        raise ValueError(f"{name!r} is not a template name")
    rel = templates_dir(root)
    folder = root / rel
    own = folder / f"{name}.md"
    if not os.path.lexists(own):
        return (resources.data_dir("skill") / "assets" / asset).read_text(encoding="utf-8")
    base = Path(os.path.realpath(root)) / rel
    real = Path(os.path.realpath(own))
    if Path(os.path.realpath(folder)) != base or real.parent != base or not real.is_file():
        raise ValueError(f"{rel}/{name}.md leads outside {rel}/: make it a plain file there, or remove it to use aidd's template")
    text = regular_files.repository_text(root, f"{rel}/{name}.md", documents.MAX_DOCUMENT_BYTES)
    if text is None:
        raise ValueError(f"{rel}/{name}.md is a link, a pipe, or past {documents.MAX_DOCUMENT_BYTES} bytes: make it a plain file there, or remove it")
    return text


def spec_template(route: str, full: bool = False, profile: str = "") -> str:
    """The Spec template `aidd new spec` writes, picked by the route and the profile together: the short one (Request,
    Context, Acceptance, Design, Concerns, Policy conflicts, Rollback) for a normal Spec, and for a major one on the solo profile,
    whose tech spec holds the alternatives and the pre-mortem; the full one for `--full`, for major on another profile,
    and for an emergency backfill."""
    variant = "default" if full or route == "emergency" or (route == "major" and profile != "solo") else "short"
    return str(_ROWS["spec"]["templates"][variant]).removesuffix(".md")


def design_spec_variant(text: str, light: bool) -> str:
    """The design spec as `aidd new` writes it. Its comment on the light variant is an instruction for this function, so
    neither variant keeps it. The light variant keeps only the sections the comment names after "keeps these
    sections:", and the link line at the end; a template without that comment is written whole."""
    note = re.search(r"<!-- The light variant.*?-->\n*", text, re.S)
    names = re.search(r"keeps these sections: ([^.]+)\.", note.group(0)) if note else None
    text = text.replace(note.group(0), "") if note else text
    if not (light and names):
        return text
    keep = {" ".join(n.split()) for n in names.group(1).split(",")}
    link = re.compile(r"(?m)^\[[a-z]+\]: .*\n?")
    head, *parts = re.split(r"(?m)^(?=## )", link.sub("", text))
    kept = [p.rstrip("\n") + "\n\n" for p in parts if p[3:].split("\n", 1)[0].strip() in keep]
    return head + "".join(kept) + "".join(m.group(0) for m in link.finditer(text))


def cra_section(text: str, keep: bool) -> str:
    """The vulnerability policy as `aidd new` writes it: the section on the EU Cyber Resilience Act stays only with the
    `cra` compliance target (`keep`), and runs to the next `## ` heading."""
    return text if keep else re.sub(r"(?ms)^## EU Cyber Resilience Act.*?(?=^## |\Z)", "", text)


@dataclass(frozen=True)
class NewObject:
    """One work item for `new_object` to write: its type, id, and title, and the options that type reads. The CLI and
    the issue and plan imports fill it; an option one type adds is one field here."""

    item_type: str
    id: str
    title: str
    route: str = "normal"
    ctype: str = "feat"
    delivery_team: str = ""  # a Spec, an Intent, a proposal, a runbook, or a postmortem
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
    profile: str = ""


def _check_names(item: NewObject) -> None:
    """The id and the Spec it names, each a plain name, or ValueError."""
    if not is_id(item.id):
        raise ValueError(f"id {item.id!r} must be letters, digits, and . _ : - (such as SPEC-42), at most 64 characters")
    if item.spec and not is_id(item.spec):
        raise ValueError(f"spec {item.spec!r} must be a Spec id, such as INC-481")


def _frozen_tests(root: Path) -> list[str]:
    """What a new Spec's tests.files freezes: the verifier's acceptance tests, still a TODO, and the test sections the
    top-level manifests hold, so a later edit of one voids the approval while a dependency bump never does; empty for
    the template's own."""
    sections = [s for name in manifest_sections.SECTION_MANIFESTS for s in _held(root, name)]
    return ["tests/TODO", *sections] if sections else []


def _held(root: Path, name: str) -> list[str]:
    """The test sections the manifest `name` holds, as tests.files entries; none when it is missing or unreadable."""
    try:
        text = regular_files.repository_text(root, name)
        return manifest_sections.test_sections_in(name, text) if text is not None else []
    except (OSError, UnicodeDecodeError):
        return []


def _from_slice(item: NewObject, found: slice_start.SliceFound | None) -> NewObject:
    """`item` as its slice line fills it: the slice's title when none is given, the Intent as its parent, and the
    slice's team."""
    if found is None:
        return item
    team = str(found.line.get("delivery_team") or "") or item.delivery_team
    return dataclasses.replace(item, title=item.title or str(found.line.get("title") or ""), parent=item.parent or found.intent_id, delivery_team=team)


def _slice_text(root: Path, item: NewObject, found: slice_start.SliceFound | None, text: str) -> tuple[str, str | None]:
    """The Spec's text and its Intent's new text once the slice's facts move into the Spec: the draft its line names,
    else `text` with the slice's `blocked_by`. The Intent's text is None when its line keeps its facts."""
    if found is None:
        return text, None
    intent_text = slice_start.moved_out(found)
    if draft := slice_start.drafted_text(root, item.specs_dir, found):
        return draft, intent_text
    waits = [str(w) for w in found.line.get("blocked_by") or []] if intent_text is not None else []
    return slice_start.with_blocked_by(text, waits), intent_text


def new_object(root: Path, item: NewObject) -> Path:
    planned = slice_start.find_slice(root, item.specs_dir, item.id) if item.item_type == "spec" and is_id(item.id) else None
    item = _from_slice(item, planned)
    today, scope = item.today, item.scope
    _check_names(item)
    if item.parent and item.item_type in objects.PARENT_TYPE:
        found = objects.type_of(root, item.parent, (item.specs_dir, item.proposals_dir))
        if found and (why := objects.parent_type_error(item.item_type, item.parent, found)):
            raise ValueError(f"{why}; name {objects.TYPE_NAMES[objects.PARENT_TYPE[item.item_type]]} as --parent")
    today = today or dt.date.today()
    name = spec_template(item.route, item.full, item.profile) if item.item_type == "spec" else item.item_type
    tpl = template_text(root, name, f"{name}.md" if item.item_type == "spec" else _ROWS[item.item_type]["templates"]["default"])
    values = dict(id=item.id, title=item.title, delivery_team=item.delivery_team or status.PLACEHOLDER, today=today.isoformat())
    if item.item_type == "proposal":
        values |= dict(audience=item.audience, addressee=item.addressee or "TODO: who receives it and decides")
    elif item.item_type in objects.OPS_DIRS:
        values |= dict(spec=item.spec or ("none" if item.item_type == "runbook" else status.PLACEHOLDER))
    else:
        values |= dict(route=item.route, change_type=item.ctype, trace_id=item.id.lower())
    text = kernel_text.fill_template(tpl, **values)
    if item.parent and item.item_type not in objects.OPS_DIRS:
        text = text.replace(f"type: {item.item_type}\n", f"type: {item.item_type}\nparent: {strict_yaml.scalar(item.parent)}\n", 1)
    if item.delivery_team and item.item_type in backlog.WORK_TYPES:
        text = text.replace(f"type: {item.item_type}\n", f"type: {item.item_type}\ndelivery_team: {strict_yaml.scalar(item.delivery_team)}\n", 1)
    if item.item_type == "spec":
        # `aidd new spec --paths`: the planned paths are the first Task's scope, its unit tests too, and the declared risk
        # is the Spec's. The acceptance tests are the verifier's, in their own folder, so tests.files starts as a TODO.
        if scope:
            text = re.sub(r"(?m)^( +)scope: \[[^\]\n]*\]", lambda m: f"{m.group(1)}scope: {strict_yaml.flow(scope)}", text, count=1)
        if frozen := _frozen_tests(root):
            text = re.sub(r'(?m)^( +)files: \["tests/TODO"\]', lambda m: f"{m.group(1)}files: {strict_yaml.flow(frozen)}", text, count=1)
        if item.dimensions:
            text = re.sub(r"(?m)^( +)dimensions: \[\]", lambda m: f"{m.group(1)}dimensions: {strict_yaml.flow(item.dimensions)}", text, count=1)
        if item.irreversible:
            text = re.sub(r"(?m)^( +)irreversible: false", r"\1irreversible: true ", text, count=1)
    if item.item_type == "spec" and item.route in ("major", "emergency"):
        # Observe is required on major (spec.schema.json).
        block = OBSERVE_BLOCK
        if item.route == "emergency":
            due = (today + dt.timedelta(days=2)).isoformat()
            block += f'\n\nemergency:\n  severity: sev2\n  type: outage\n  commander: "@TODO"\n  incident: INC-TODO\n  backfill_due: "{due}"'
        head, sep, rest = text.partition("\n---\n")
        text = head + block + sep + rest
    path = object_path(root, item)
    text, intent_text = _slice_text(root, item, planned, text)
    titled = item.item_type in config.types_of_form("work_item")
    write_new(path, text, f'edit it, or run `aidd new {item.item_type} "<title>"` for the next free id' if titled else "edit it, or give another id", root)
    if planned is not None and intent_text is not None:
        regular_files.write_text_safely(root, planned.intent_path, intent_text)
    return path


def object_path(root: Path, item: NewObject) -> Path:
    """Where `aidd new` writes `item`. A proposal gets its own folder: each role writes its part beside it, and one
    addressee's material stays apart."""
    folder = _ROWS[item.item_type]["folder"].replace("{specs}", item.specs_dir).replace("{proposals}", item.proposals_dir)
    if item.item_type == "proposal":
        return root / folder / item.id / "proposal.md"
    return root / folder / f"{item.id}.md"


def refuse_link_on_the_way(root: Path, path: Path) -> None:
    """A ValueError, naming the link and the next step, when a link lies between `root` and `path`, the path's own last
    part included: a write through it would land outside the repository."""
    if link := regular_files.link_on_the_way(root, path.relative_to(root) if path.is_relative_to(root) else path):
        raise ValueError(f"{link} is a link, and aidd writes nothing through a link: replace it with the folder or the file it points to, then run this again")


def write_new(path: Path, text: str, next_step: str, root: Path) -> None:
    """Write a new file at `path`, never over one: the open fails when the file exists, even one another run wrote a
    moment ago. Its error names `next_step`, such as "edit it, or give another topic". A link between `root` and `path`
    is refused first (`refuse_link_on_the_way`)."""
    refuse_link_on_the_way(root, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with regular_files.open_for_write(path, text=True, root=root, way="new", mode=regular_files.REPOSITORY_FILE_MODE) as fh:
            fh.write(text)
    except FileExistsError:
        raise FileExistsError(f"{path} exists: {next_step}") from None


# The documents `aidd new <type>` writes from a template of its own, and the template each starts from: the linked ones
# (`<topic> --spec <ID>`) and the living ones that stand alone, from schemas/item-types.json. The design-spec doc is the
# design spec; `--prototype` writes its HTML prototype instead (PROTOTYPE), one file per Spec or flow in the design
# folder (`specs/<ID>/design/prototype.html`, or `specs/<ID>/design/<flow>/prototype.html`), linked as the same type.
_ROWS = config.item_type_rows()
DOC_TEMPLATES: dict[str, str] = {t: _ROWS[t]["templates"]["default"] for g in ("linked", "standalone") for t in config.types_in(g)}
PROTOTYPE = "prototype.html"
# The living form of a type that has one (`--living`), and the template it starts from: the test plan of one component.
LIVING_TEMPLATES: dict[str, str] = {t: row["templates"]["living"] for t, row in _ROWS.items() if "living" in row.get("templates", {})}


def _home(doc_type: str) -> str:
    """The one file or folder glob `loop.documents` in schemas/roles.json gives a repository document, with {docs}."""
    files = resources.load_json("roles.json")["loop"]["documents"][doc_type]["files"]
    if len(files) != 1:
        raise ValueError(f"schemas/roles.json: loop.documents.{doc_type} must name one file or folder, not {files}")
    return str(files[0])


@functools.cache
def repo_docs() -> dict[str, tuple[tuple[str, str], ...]]:
    """The files of each document the repository has one of, as (path, template): the rows' `files` of
    schemas/item-types.json, with each path roles.json owns read from it."""
    return {
        t: tuple((_home(t) if f["path"] == config.ROLES_HOME else f["path"], f["template"]) for f in row["files"]) for t, row in _ROWS.items() if "files" in row
    }


def _folder_under_docs(doc_type: str) -> str:
    return _home(doc_type).removeprefix("{docs}/").removesuffix("/**")


@functools.cache
def unlinked_folders() -> dict[str, str]:
    """The folder under `<docs_dir>` of each stand-alone document that has one (the feedback log, the services' files), from roles.json."""
    return {t: _folder_under_docs(t) for t in config.types_in("standalone") if _ROWS[t].get("folder") == config.ROLES_HOME}


@functools.cache
def adr_folder() -> str:
    """The ADRs' folder under `<docs_dir>`, from roles.json: `aidd new adr` numbers each one there, as `NNNN-<topic>.md`."""
    return _folder_under_docs("adr")


if TYPE_CHECKING:
    REPO_DOCS: dict[str, tuple[tuple[str, str], ...]]
    LIVING_DOCS: frozenset[str]


def __getattr__(name: str) -> dict | frozenset:
    """`REPO_DOCS` and `LIVING_DOCS`, read from roles.json when first asked for, never on import."""
    if name == "REPO_DOCS":
        return repo_docs()
    if name == "LIVING_DOCS":
        return living_doc_types()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Documents that belong to no one Spec, each in its own folder under `<docs_dir>`: the feedback log is a living record
# of what customers said after launch, and a service's file is the SRE's living record of its objectives. The SRS is
# derived: `aidd new srs <INTENT-ID>` writes it to the views folder (git ignores it) and writes it again each time.
UNLINKED_DOCS: frozenset[str] = frozenset(config.types_in("standalone"))


# Documents humans keep filling after Spec approval: linked as living (`frozen: false`), only checked to exist. They are the
# types `aidd new` links to a Spec (a linked document, or a repository document a Spec links later) whose `lifecycle` in
# `loop.documents` of schemas/roles.json is living. A threat model is one per component and outlives each Spec: a Spec
# freezes only its delta, in its Design. An SLO doc is the same kind of delta: frozen with its Spec, while the service card
# (UNLINKED_DOCS) holds the current objectives. A runbook is living too, and `aidd new runbook --spec` links it as such on
# its own path. Read from roles.json when first used.
@functools.cache
def living_doc_types() -> frozenset[str]:
    """The types `aidd new` links to a Spec as living docs, from the schema's list of types and roles.json's lifecycles."""
    documents_table = resources.load_json("roles.json")["loop"]["documents"]
    linked = resources.load_json("spec.schema.json")["$defs"]["doc"]["properties"]["type"]["enum"]
    written = {*DOC_TEMPLATES, *repo_docs()}
    return frozenset(t for t in linked if t in written and documents_table.get(t, {}).get("lifecycle") == "living")


# The repository documents of `repo_docs()` are one per repository, never per Spec: `aidd new <type>` writes each file (repository
# path, with {docs} for the configured docs folder, and its template). The glossary holds the project's terms, one meaning each,
# for every writer. Living documents: each later change to one is a change of its own. A Spec that touches personal data or a
# vendor links the data map or the vendor register as a living `docs` entry. The design system's build script (dependency-free
# Node) writes its CSS and DESIGN.md's token mirror, and checks them for drift. The agents' guide is the team's, written around
# aidd's own section that `aidd init` puts there. The product-level living documents of the product manager, the compliance
# analyst, and the SRE each take a Spec's tracking plan or compliance record, and `aidd validate` checks the fold (living_docs).
# The marker of aidd's own section in AGENTS.md (setup/adoption.AGENTS_MARK): the team's guide goes above it.
SECTION_MARK = "<!-- aidd -->"
# The engagement's documents, in the accepted proposal's folder: the contract (a statement of work), then each change
# order to it, `change-orders/CO-<n>.md`, from the same template family.
CONTRACT = "contract.md"
CHANGE_ORDERS = "change-orders"
# The design system's tokens: a Spec's design files that hold their own tokens beside it drift from it.
REPO_TOKENS = "design/tokens.json"


def new_repo_doc(root: Path, *, doc_type: str, title: str = "", docs_dir: str = "docs", today: dt.date | None = None) -> list[Path]:
    """Write a repository's design system or architecture overview from its templates; refuse when any file exists.
    AGENTS.md is the one that may exist already, holding only aidd's own section (`aidd init`): the guide goes above it."""
    targets = [(root / rel.replace("{docs}", docs_dir), tpl) for rel, tpl in repo_docs()[doc_type]]
    if doc_type == "agents":
        return [_project_guide(root, targets[0][0])]
    taken = [p for p, _ in targets if p.exists()]
    if taken:
        raise FileExistsError(f"{taken[0].relative_to(root).as_posix()} exists: the repository has one {doc_type}; change it in its own change")
    values = dict(title=title or root.resolve().name, today=(today or dt.date.today()).isoformat())
    for path, tpl in targets:
        text = template_text(root, doc_type, tpl) if tpl.endswith(".md") else (resources.data_dir("skill") / "assets" / tpl).read_text(encoding="utf-8")
        if doc_type == "vulnerability-policy":
            text = cra_section(text, "cra" in config.project_compliance(repo_reads.config_at(root))["targets"])
        refuse_link_on_the_way(root, path)
        regular_files.write_text_safely(root, path, kernel_text.fill_template(text, **values) if tpl.endswith(".md") else text)
    return [p for p, _ in targets]


def _project_guide(root: Path, path: Path) -> Path:
    """AGENTS.md with the project's guide (assets/agents.md) above aidd's own section; refuse when it holds one already."""
    guide = template_text(root, "agents", repo_docs()["agents"][0][1]).strip("\n")
    refuse_link_on_the_way(root, path)
    found, why = regular_files.named_text(root, path.relative_to(root).as_posix())
    if found is None and why != regular_files.MISSING:
        raise ValueError(f"{path.relative_to(root).as_posix()} is {why}, which aidd never reads or writes through: replace it with the file")
    current = found or ""
    head, mark, rest = current.partition(SECTION_MARK)
    if head.strip() not in ("", "# Agents"):
        raise FileExistsError(f"{path.relative_to(root).as_posix()} holds the project's guide already: change it in its own change")
    regular_files.write_text_safely(root, path, f"# Agents\n\n{guide}\n\n" + (f"{mark}{rest}" if mark else ""))
    return path


def new_contract(root: Path, proposal_id: str, *, proposals_dir: str = "proposals", today: dt.date | None = None) -> Path:
    """The engagement's contract in the proposal's folder, from its template; once it exists, the next change order."""
    folder = root / proposals_dir / proposal_id
    if not is_id(proposal_id) or not (folder / "proposal.md").is_file():
        raise ValueError(f"no proposal {proposal_id} in {proposals_dir}/: `aidd new contract <proposal id>` writes the contract of an accepted proposal")
    values = dict(proposal=proposal_id, today=(today or dt.date.today()).isoformat())
    templates = _ROWS["contract"]["templates"]
    if not (folder / CONTRACT).exists():
        path, tpl = folder / CONTRACT, templates["default"]
    else:
        taken = [int(m.group(1)) for p in (folder / CHANGE_ORDERS).glob("CO-*.md") for m in [re.fullmatch(r"CO-(\d+)\.md", p.name)] if m]
        number = max(taken, default=0) + 1
        path, tpl, values["number"] = folder / CHANGE_ORDERS / f"CO-{number}.md", templates["change_order"], str(number)
    text = kernel_text.fill_template(template_text(root, tpl.removesuffix(".md"), tpl), **values)
    regular_files.write_text_safely(root, path, text)
    return path


def own_tokens(root: Path, data: dict) -> list[str]:
    """The tokens files a Spec's design files hold, other than the repository's own."""
    found = [f for pattern in spec_file.design_files(data) for f in objects.files_matching(root, pattern)]
    return sorted({f for f in found if f != REPO_TOKENS and re.search(r"(?:^|[/.])tokens(?:\.json)?$", f.lower())})


def link_doc(spec_path: Path, doc_type: str, rel: str, *, root: Path, frozen: bool = True) -> None:
    """Append an entry to the Spec's `docs` list in its front matter; refuse when the result would not parse, or when a
    link lies between `root` and the Spec, since the write would land elsewhere."""
    refuse_link_on_the_way(root, spec_path)
    found = regular_files.file_text(root, spec_path, documents.MAX_DOCUMENT_BYTES)
    if found is None:
        raise ValueError(f"{spec_path.as_posix()}: not a regular file aidd can read; replace it with the Spec's file")
    text = found.lstrip("﻿")
    m = documents.FRONT_MATTER.match(text)
    if not m:
        raise ValueError(f"{spec_path.as_posix()}: missing YAML front matter between `---` lines")
    entry = {"type": doc_type, "path": rel} | ({} if frozen else {"frozen": False})
    try:
        front = strict_yaml.append_item(m.group(1), "docs", entry)
        new = text[: m.start(1)] + front + text[m.end(1) :].lstrip("\n")
        documents.split_front_matter(new, spec_path.as_posix())
    except (ValueError, documents.DocumentError) as exc:
        raise ValueError(f"{spec_path.as_posix()}: cannot add a `docs` entry ({exc}); write docs as a block list, one `- type:` item per doc") from exc
    with regular_files.open_for_write(spec_path, text=True) as f:
        f.write(new)


@dataclass(frozen=True)
class NewDoc:
    """One linked document for `new_doc` to write: its type and topic, the Spec it belongs to, and where it goes."""

    doc_type: str
    topic: str
    spec_id: str = ""
    doc_folder: str = ""
    title: str = ""
    docs_dir: str = "docs"
    specs_dir: str = "specs"
    today: dt.date | None = None
    link: bool = True
    prototype: bool = False
    # The component's living form of the type (`LIVING_TEMPLATES`), linked with `frozen: false`.
    living: bool = False
    # The solo profile writes the design spec's light variant, unless `full` asks for every section.
    profile: str = ""
    full: bool = False


def _template(doc: NewDoc, root: Path) -> str:
    """The text a document starts from: the prototype's is aidd-team's prototype tool's starting design, with the
    project's own tokens when it keeps a design system; every other template is the skill's."""
    if doc.prototype:
        tool = resources.team_tool("prototype")
        return tool.with_project_tokens((resources.data_dir("team") / "tools" / "prototype" / "design.html").read_text(encoding="utf-8"), root)
    if doc.living:
        return template_text(root, f"{doc.doc_type}-living", LIVING_TEMPLATES[doc.doc_type])
    text = template_text(root, doc.doc_type, DOC_TEMPLATES[doc.doc_type])
    return design_spec_variant(text, doc.profile == "solo" and not doc.full) if doc.doc_type == "design-spec" else text


def _write_unlinked(root: Path, doc: NewDoc, name: str, tpl: str, values: dict[str, str]) -> Path:
    """A document no Spec links, written once: the feedback log and a service's file, in their folders under the docs
    folder. The SRS is derived from the work items and git, so it is written again each time, to the views folder."""
    if doc.doc_type != "srs":
        path = root / doc.docs_dir / unlinked_folders()[doc.doc_type] / f"{name}.md"
        write_new(path, kernel_text.fill_template(tpl, **values), "edit it, or give another topic", root)
        return path
    path = root / config.VIEWS_DIR / f"srs-{name}.md"
    regular_files.write_text_safely(root, path, srs.render(root, repo_reads.config_at(root), doc.topic, tpl, today=doc.today))
    return path


def new_doc(root: Path, doc: NewDoc) -> tuple[Path, Path | None]:
    """Write a linked document from its template and link it from the Spec (unless `link` is false: a specialist
    writes its own doc and the Spec's writer adds the `docs` entry, one writer per file): an ADR in `adr_folder()`, as `NNNN-<topic>.md`
    with the next number, a project-wide record; a threat model as `<docs_dir>/security/threat-models/<component>.md`,
    one living model per component that a later Spec only links again; anything else in the work item's own folder, beside it: the design spec's
    prototype (`prototype`) as `<specs_dir>/<Spec id>/design/prototype.html` (a second flow, `--doc-folder <flow>`, in
    `design/<flow>/`), and any other document as `<specs_dir>/<doc folder or Spec id>/<type>-<topic>.md`. The document's header names the Spec (its back-link). Returns the document and the Spec.
    A feedback log or a service's file has no Spec: it is written as `<docs_dir>/feedback/<topic>.md` or `<docs_dir>/services/<topic>.md`,
    and the Spec returned is None; so is the SRS's, which `aidd new srs <INTENT-ID>` derives (srs.py). A threat model also rewrites the
    folder's index (living_docs.py)."""
    if doc.doc_type not in DOC_TEMPLATES:
        raise ValueError(f"no template for {doc.doc_type!r}; one of {', '.join(DOC_TEMPLATES)}")
    if doc.doc_folder and not is_id(doc.doc_folder):
        raise ValueError(f"--doc-folder {doc.doc_folder!r} must be letters, digits, and . _ : - (such as checkout)")
    name = kernel_text.slug(doc.topic)
    values = dict(title=doc.title or doc.topic, today=(doc.today or dt.date.today()).isoformat())
    if doc.prototype and doc.doc_type != "design-spec":
        raise ValueError("--prototype writes the design spec's HTML prototype: `aidd new design-spec <topic> --spec <ID> --prototype`")
    if doc.living and doc.doc_type not in LIVING_TEMPLATES:
        raise ValueError(
            f"--living is for {', '.join(LIVING_TEMPLATES)}"
            + (": a threat model takes its component as the topic" if doc.doc_type == "threat-model" else f"; {doc.doc_type} has no living form to write")
        )
    tpl = _template(doc, root)
    if doc.doc_type in UNLINKED_DOCS:
        return _write_unlinked(root, doc, name, tpl, values), None
    spec_path = objects.find_spec_by_id(root, doc.specs_dir, doc.spec_id)
    values |= dict(spec=doc.spec_id, number="")
    if doc.doc_type == "adr":
        folder = root / doc.docs_dir / adr_folder()
        taken = [int(m.group(1)) for p in (folder.iterdir() if folder.is_dir() else []) for m in [re.match(r"(\d{4})-", p.name)] if m]
        number = max(taken, default=0) + 1
        path, values["number"] = folder / f"{number:04d}-{name}.md", f"{number:04d}"
    elif doc.prototype:
        path = root / doc.specs_dir / doc.spec_id / item_folder.DESIGN_FOLDER / doc.doc_folder / PROTOTYPE  # a second flow: --doc-folder
    elif doc.doc_type == "threat-model" or doc.living:
        # The component's living model or test plan: written once, then each Spec that changes the component links it again.
        if name == "readme" and not doc.living:
            raise ValueError("readme is the index of the threat models, not a component: name the component")
        path = root / doc.docs_dir / (spec_file.TEST_PLANS if doc.living else spec_file.THREAT_MODELS) / f"{name}.md"
        if path.exists():
            rel = path.relative_to(root).as_posix()
            spec_text = regular_files.file_text(root, spec_path, documents.MAX_DOCUMENT_BYTES) or ""
            linked = documents.split_front_matter(spec_text, spec_path.as_posix())[0].get("docs") or []
            if doc.link and not any(isinstance(d, dict) and d.get("path") == rel for d in linked):
                link_doc(spec_path, doc.doc_type, rel, root=root, frozen=False)
            if doc.doc_type == "threat-model":
                living_docs.write_threat_index(root, repo_reads.config_at(root), doc.docs_dir)
            return path, spec_path
    else:
        path = root / doc.specs_dir / (doc.doc_folder or doc.spec_id) / f"{doc.doc_type}-{name}.md"
    values |= dict(spec_link=Path(os.path.relpath(spec_path, path.parent)).as_posix(), path=path.relative_to(root).as_posix())
    again = "edit it, or give a second flow its own folder: `--doc-folder <flow>`" if doc.prototype else "edit it, or give another topic"
    write_new(path, kernel_text.fill_template(tpl, **values), again, root)
    if doc.link:
        link_doc(spec_path, doc.doc_type, path.relative_to(root).as_posix(), root=root, frozen=not (doc.living or doc.doc_type in living_doc_types()))
    if doc.doc_type == "threat-model":
        living_docs.write_threat_index(root, repo_reads.config_at(root), doc.docs_dir)  # the folder's index lists the models and their Specs
    return path, spec_path


class DocAsk(NamedTuple):
    """One document the required-docs matrix asks a Spec for: its type, the level (`warn` or `suggest`), why, and whether
    it must be a living doc (`True`), a frozen one (`False`), or either (`None`)."""

    doc_type: str
    level: str
    why: str
    living: bool | None


def required_docs(data: dict, cfg: config.Config | None) -> list[DocAsk]:
    """The documents the required-docs matrix asks this Spec for: level `warn` on the routes a row warns on, `suggest`
    on those it only suggests. Each type holds rows; of the rows that match, the highest level wins for each `living`
    answer, and the first row of that level gives the reason. Advice only: `aidd validate` warns, and no other check reads it."""
    route = data.get("route")
    out = []
    for doc_type, rows in (cfg or config.EMPTY).docs_required.items():
        best: dict[bool | None, tuple[str, list[str]]] = {}
        for row in rows:
            level = "warn" if route in row.get("routes", []) else "suggest" if route in row.get("suggest", []) else None
            why = _row_conditions(row, data, cfg) if level else None
            if why is not None and (row.get("living") not in best or (level == "warn" and best[row.get("living")][0] == "suggest")):
                best[row.get("living")] = (str(level), why)
        out += [DocAsk(doc_type, level, ", ".join([f"route {route}", *why]), living) for living, (level, why) in best.items()]
    return out


def _row_conditions(row: dict, data: dict, cfg: config.Config | None) -> list[str] | None:
    """Why a matrix row holds for this Spec: its own conditions, and one of its `any_of` sets. None when one does not."""
    why = _doc_conditions(row, data, cfg)
    if why is None or not row.get("any_of"):
        return why
    alt = next((w for w in (_doc_conditions(c, data, cfg) for c in row["any_of"]) if w is not None), None)
    return None if alt is None else why + alt


def _doc_conditions(rule: dict, data: dict, cfg: config.Config | None) -> list[str] | None:
    """Why a doc rule's conditions hold for this Spec (every one must), or None when one does not."""
    risk = data.get("risk") or {}
    why = []
    if rule.get("dimensions"):
        hit = sorted(set(risk.get("dimensions") or []) & set(rule["dimensions"]))
        if not hit:
            return None
        why.append(f"risk {', '.join(hit)}")
    if rule.get("change_types"):
        if data.get("change_type") not in rule["change_types"]:
            return None
        why.append(f"change type {data.get('change_type')}")
    if rule.get("paths"):
        scopes = [s for task in data.get("tasks") or [] for s in task.get("scope") or [] if isinstance(s, str)]
        if not any(globs.match_any(rule["paths"], s) or globs.match_any(rule["paths"], globs.sample_path(s)) for s in scopes):
            return None
        why.append("a matching path in scope")
    if rule.get("profiles"):
        if cfg is None or cfg.profile not in rule["profiles"]:
            return None
        why.append(f"profile {cfg.profile}")
    if "compliance" in rule:
        on = config.project_compliance(cfg)["on"]
        if on is not rule["compliance"]:
            return None
        why.append("compliance on" if on else "compliance off")
    for key, said in (("manual_acceptance", "manual acceptance"), ("hypothesis", "a hypothesis"), ("irreversible", "irreversible")):
        if key not in rule:
            continue
        value = risk.get("irreversible") is True if key == "irreversible" else bool(data.get(key))
        if value is not rule[key]:
            return None
        why.append(said if rule[key] else f"not {said}")
    return why


# Where a new Spec's acceptance tests go: the template's placeholder and the folder its comment names.
ACCEPTANCE_FOLDERS = ("tests/TODO", "tests/acceptance/")


def scope_over_acceptance_tests(scope: list[str]) -> list[str]:
    """The entries of a planned scope that would overlap the acceptance tests' folder, such as a bare `tests/`: Spec
    approval freezes those tests, so `aidd new spec` leaves the entry out and names the unit-test folder instead."""
    return [s for s in scope if any(globs.overlap(s, f) for f in ACCEPTANCE_FOLDERS)]


def folder_scope(paths: list[str], exact_globs: set[str]) -> list[str]:
    """The scope the planned `paths` declare: each file's folder, so a file implementation finds next to it needs no new
    Spec approval, and a glob or folder as written. A file in `exact_globs` stays exact (one a path in an area or a risk rule
    matched: widening it to its folder would let the change touch its neighbours unflagged), and so do a test file (it
    may sit beside the frozen acceptance tests) and a file at the repository's top. A folder inside another listed folder goes."""
    out: list[str] = []
    for p in paths:
        p = p.strip().removeprefix("./")
        is_glob = p.endswith("/") or globs.is_pattern(p)
        folder = p if is_glob or p in exact_globs or "/" not in p or config.looks_like_test(p) else p.rsplit("/", 1)[0] + "/"
        if folder not in out:
            out.append(folder)
    folders = [f for f in out if f.endswith("/")]
    return [s for s in out if not any(s != f and s.startswith(f) for f in folders)]
