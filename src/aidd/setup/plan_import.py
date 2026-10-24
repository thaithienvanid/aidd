"""`aidd import`: a short aidd Spec from another planning tool's files. The Spec points at the plan; it never copies it.

Each reader takes the tool's own files as they are and fills what it can say for sure:

- Intent: the source's own words (the problem or story), quoted, and a `Source:` line linking every file read
- Acceptance: one item per acceptance scenario, EARS requirement, or acceptance criterion, with ids A1, A2, ...
- Design: a pointer to the source's design or plan, not a copy of it
- tasks: one Task per task group of the source that names file paths, those paths as its `scope`; with none, the
  template's TODO scope, which `aidd validate` flags
- tests.files and the test command stay TODO: a test file the source names is listed in a comment, never assumed
- route: computed from the scope with `routing.assess_paths`, as `aidd new spec --paths` does, and never below normal

Formats, checked on 2026-09-28 against each tool's templates:

- Spec Kit (github.com/github/spec-kit, v1.0.12): `specs/NNN-feature/spec.md` ("**Input**: User description:",
  "**Acceptance Scenarios**:" with "**Given** ..., **When** ..., **Then** ...", "- **FR-001**: System MUST ..."),
  `plan.md` ("## Summary"), and `tasks.md` ("## Phase N: ...", "- [ ] T012 [P] [US1] Create ... in src/x.py").
- OpenSpec (github.com/Fission-AI/OpenSpec, v1.13.2): `openspec/changes/<id>/proposal.md` ("## Why", "## What
  Changes", "## Impact"), `design.md`, `tasks.md` ("## 1. Group", "- [ ] 1.1 ..."), and spec deltas
  `specs/<capability>/spec.md` ("## ADDED Requirements", "### Requirement: ...", "#### Scenario: ...",
  "- **WHEN** ...", "- **THEN** ...").
- Kiro (kiro.dev/docs/specs): `.kiro/specs/<feature>/requirements.md` (or `bugfix.md`), `design.md`, and
  `tasks.md`. The docs show EARS as "WHEN [condition] THE SYSTEM SHALL [behavior]", on one line or two; numbered
  acceptance criteria ("1. WHEN ... THEN the system SHALL ...") and "- [ ] 1. Task" lists are read the same way.
- BMAD Method (github.com/bmad-code-org/BMAD-METHOD, v6.12.0): one story file,
  `_bmad-output/implementation-artifacts/<epic>-<story>-<slug>.md` ("# Story 1.2: Title", "## Story",
  "## Acceptance Criteria", "## Tasks / Subtasks" with "- [ ] Task 1 (AC: #1)", "## Dev Notes"). One story is one
  Spec; the PRD and the epics stay where they are.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from aidd import config, gate, workitems
from aidd.kernel import globs, strict_yaml

LABELS = {"speckit": "Spec Kit", "openspec": "OpenSpec", "kiro": "Kiro", "bmad": "BMAD"}
TOOLS = tuple(LABELS)
MAX_ACCEPTANCE = 50
MAX_TASKS = 20
MAX_QUOTE_CHARS = 1200  # characters of the source's own words in Intent; the rest stays in the source


@dataclass
class Group:
    """One task group of the source: its title and every path its lines name."""

    title: str
    paths: list[str] = field(default_factory=list)


@dataclass
class Plan:
    """What a reader found. Everything is the source's; nothing is guessed."""

    title: str
    intent: str
    acceptance: list[str]
    groups: list[Group]
    design: str
    sources: list[Path]
    ctype: str = "feat"
    notes: list[str] = field(default_factory=list)


# ---- Reading markdown --------------------------------------------------------------------------------------

_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_LIST = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+")
_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_CODE = re.compile(r"`([^`\n]+)`")
# A path: segments joined by "/", or a bare file name (only inside backticks), never a URL or a placeholder.
_SLASH_PATH = re.compile(r"(?<![\w./:-])((?:\.{0,2}/)?(?:[\w@.+-]+/)+[\w@.+-]*)")
_FILE_NAME = re.compile(r"^[\w@+-][\w@.+-]*\.[A-Za-z][A-Za-z0-9]{0,7}$")
_EXT = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,7}$")
_TEST_PART = re.compile(r"(^|/)(tests?|__tests__|spec|specs|e2e|test_\w+\.\w+|\w+_test\.\w+|\w+\.(test|spec)\.\w+)(/|$)")


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc


def sections(text: str) -> list[tuple[int, str, list[str]]]:
    """(level, heading, lines) for every heading, in order; text before the first heading has level 0 and no name.
    Lines inside fenced code blocks never start a section."""
    out: list[tuple[int, str, list[str]]] = [(0, "", [])]
    fence = False
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
        m = None if fence else _HEADING.match(line)
        if m:
            out.append((len(m.group(1)), m.group(2).strip(), []))
        else:
            out[-1][2].append(line)
    return out


def first_section(text: str, *names: str) -> str:
    """The text under the first heading below the title (level 2 or deeper) whose name starts with one of `names`
    (case-insensitive), up to the next heading of the same or a higher level; "" when there is none."""
    secs = sections(text)
    wanted = [n.lower() for n in names]
    for i, (level, name, lines) in enumerate(secs):
        if level >= 2 and any(plain(name).lower().startswith(w) for w in wanted):
            body = list(lines)
            for lv, nm, ls in secs[i + 1 :]:
                if lv <= level:
                    break
                body += [f"{'#' * lv} {nm}", *ls]
            return "\n".join(body).strip()
    return ""


def plain(text: str) -> str:
    """Markdown emphasis and code marks removed, whitespace collapsed."""
    text = _BOLD.sub(lambda m: m.group(1) or m.group(2), text)
    text = _CODE.sub(lambda m: m.group(1), text)
    text = re.sub(r"(?<!\w)[*_](\S(?:.*?\S)?)[*_](?!\w)", r"\1", text)
    return " ".join(text.split())


def paragraphs(text: str) -> list[str]:
    """Prose paragraphs, without comments, headings, tables, and code blocks."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"(?ms)^[ \t]*(```|~~~).*?^[ \t]*\1[^\n]*$", "", text)
    out = []
    for block in re.split(r"\n[ \t]*\n", text):
        lines = [x for x in block.splitlines() if x.strip() and not _HEADING.match(x) and not x.lstrip().startswith("|")]
        if lines:
            out.append("\n".join(lines).strip())
    return out


def items(text: str) -> list[str]:
    """The list items in `text`, each joined with its continuation lines (nested items are items of their own)."""
    out: list[str] = []
    for line in re.sub(r"<!--.*?-->", "", text, flags=re.S).splitlines():
        if _LIST.match(line):
            out.append(_LIST.sub("", line, count=1))
        elif out and line.strip() and line[:1] in (" ", "\t") and not _HEADING.match(line.strip()):
            out[-1] += " " + line.strip()
        elif not line.strip() and out and out[-1] != "":
            out.append("")
    return [plain(x) for x in out if x.strip()]


def paths_in(text: str) -> list[str]:
    """The repository paths a line names: slash paths anywhere, bare file names only in backticks. Never a URL, a
    placeholder ([name], {name}, <name>), or an absolute path."""
    found: list[str] = []
    candidates = [m.group(1) for m in _CODE.finditer(text)]
    bare = _CODE.sub(" ", text)
    candidates += [m.group(1) for m in _SLASH_PATH.finditer(bare) if _EXT.search(m.group(1)) or m.group(1).endswith("/")]
    for raw in candidates:
        p = raw.strip().strip(".,;:()'\"").removeprefix("./")
        if not p or "://" in raw or p.startswith(("/", "~", "../")) or any(c in p for c in "[]{}<>*?$ \t|"):
            continue
        if "/" not in p and not _FILE_NAME.match(p):
            continue
        if "/" in p and not (_EXT.search(p) or p.endswith("/")):
            continue
        if ".." in p.split("/"):
            continue
        found.append(p)
    return list(dict.fromkeys(found))


def is_test_path(path: str) -> bool:
    return bool(_TEST_PART.search(path.lower()))


def quote(text: str) -> str:
    """The source's words as a Markdown quote, cut at MAX_QUOTE characters (the rest stays in the source)."""
    text = text.strip()
    if len(text) > MAX_QUOTE_CHARS:
        text = text[: MAX_QUOTE_CHARS - 3].rstrip() + "..."
    return "\n".join(f"> {x}" if x.strip() else ">" for x in text.splitlines())


def title_from_slug(slug: str) -> str:
    words = re.sub(r"^\d+[-_.]*", "", slug).replace("_", "-").split("-")
    text = " ".join(w for w in words if w)
    return text[:1].upper() + text[1:] if text else slug


def _first(text: str) -> str:
    paras = paragraphs(text)
    return paras[0] if paras else ""


def _h1_title(text: str, slug: str) -> str:
    """The title after the colon of the first level-1 heading ("# Feature: Photo albums"), else one from the slug."""
    head = next((name for level, name, _ in sections(text) if level == 1), "")
    return plain(head.split(":", 1)[1]) if ":" in head else title_from_slug(slug)


def _design(md: Path, first: str) -> str:
    """A pointer to the source's design file, with its first paragraph; `{link:...}` becomes a relative link on write."""
    return f"The approach is in [{md.name}]({{link:{md}}})" + (f": {plain(first)}" if first else ".")


# ---- Spec Kit --------------------------------------------------------------------------------------------------


_GWT = re.compile(r"\bGiven\b.*\bThen\b", re.I)


def _task_groups(tasks_text: str, group_level: int, item: re.Pattern | None = None) -> list[Group]:
    """One Group per heading of `group_level` (or, with `item`, per top-level list item it matches), with the paths
    its lines name."""
    groups: list[Group] = []
    if item is None:
        for level, name, lines in sections(tasks_text):
            if level == group_level:
                groups.append(Group(plain(name)))
            elif level > group_level and groups:
                groups[-1].paths += paths_in(name)
            if groups and level >= group_level:
                for line in lines:
                    groups[-1].paths += paths_in(line)
    else:
        fence = False
        for line in tasks_text.splitlines():
            if line.lstrip().startswith(("```", "~~~")):
                fence = not fence
                continue
            m = None if fence else item.match(line)
            if m:
                groups.append(Group(plain(m.group(1))))
            if groups and not fence:
                groups[-1].paths += paths_in(line)
    for g in groups:
        g.paths = list(dict.fromkeys(g.paths))
    return groups


def read_speckit(path: Path) -> Plan:
    folder = path.parent if path.is_file() else path
    spec_md = folder / "spec.md"
    if not spec_md.is_file():
        raise ValueError(f"{folder}: no spec.md; pass a Spec Kit feature folder, such as specs/001-photo-albums/")
    spec = read(spec_md)
    sources = [spec_md]
    title = _h1_title(spec, folder.name)
    m = re.search(r"\*\*Input\*\*:\s*(?:User description:\s*)?(.+)", spec)
    intent = m.group(1).strip().strip('"') if m and "$ARGUMENTS" not in m.group(1) else _first(first_section(spec, "user scenarios"))
    acceptance: list[str] = []
    story = ""
    for level, name, lines in sections(spec):
        if level:
            story = plain(name.split(" - ")[0].split("(")[0]).strip() if level == 3 and name.lower().startswith("user story") else ""
        for it in items("\n".join(lines)):
            if _GWT.search(it):
                acceptance.append(f"{it[:1].upper() + it[1:]}" + (f" ({story})" if story else ""))
    if not acceptance:
        for it in items(first_section(spec, "requirements")):
            m2 = re.match(r"((?:FR|NFR|SC)-\d+):\s*(.+)", it)
            if m2 and "NEEDS CLARIFICATION" not in it:
                acceptance.append(f"{m2.group(2)} ({m2.group(1)})")
    notes = [] if acceptance else ["spec.md has no acceptance scenario or functional requirement: write the Acceptance items"]
    plan_md, tasks_md = folder / "plan.md", folder / "tasks.md"
    design = ""
    if plan_md.is_file():
        sources.append(plan_md)
        design = _design(plan_md, _first(first_section(read(plan_md), "summary")))
    groups: list[Group] = []
    if tasks_md.is_file():
        sources.append(tasks_md)
        groups = _task_groups(read(tasks_md), 2)
        groups = [
            g for g in groups if not g.title.lower().startswith(("format", "path conventions", "dependencies", "parallel", "implementation strategy", "notes"))
        ]
    for extra in ("research.md", "data-model.md", "quickstart.md"):
        if (folder / extra).is_file():
            sources.append(folder / extra)
    return Plan(title, intent, acceptance, groups, design, sources, notes=notes)


# ---- OpenSpec --------------------------------------------------------------------------------------------------


_KEYWORD = re.compile(r"^(WHEN|THEN|AND|GIVEN|BUT)\b")


def read_openspec(path: Path) -> Plan:
    folder = path.parent if path.is_file() else path
    proposal_md = folder / "proposal.md"
    if not proposal_md.is_file():
        raise ValueError(f"{folder}: no proposal.md; pass an OpenSpec change folder, such as openspec/changes/add-dark-mode/")
    proposal = read(proposal_md)
    sources = [proposal_md]
    title = _h1_title(proposal, folder.name)
    intent = first_section(proposal, "why") or _first(proposal)
    acceptance: list[str] = []
    for delta in sorted((folder / "specs").rglob("spec.md")) if (folder / "specs").is_dir() else []:
        sources.append(delta)
        kind = requirement = ""
        for level, name, lines in sections(read(delta)):
            if level == 2:
                kind, requirement = name.split()[0].upper(), ""
            elif kind in ("ADDED", "MODIFIED") and level == 3:
                requirement = plain(name.split(":", 1)[-1])
            elif kind in ("ADDED", "MODIFIED") and level == 4 and name.lower().startswith("scenario"):
                scenario = plain(name.split(":", 1)[-1])
                steps = ", ".join(_KEYWORD.sub(lambda k: k.group(1).lower(), x) for x in items("\n".join(lines)))
                if steps:
                    acceptance.append(f"{requirement} / {scenario}: {steps}" if requirement else f"{scenario}: {steps}")
    if not acceptance:
        acceptance = [plain(x) for x in re.findall(r"^.*\b(?:SHALL|MUST)\b.*$", proposal, re.M) if not x.lstrip().startswith("#")]
    tasks_md, design_md = folder / "tasks.md", folder / "design.md"
    groups: list[Group] = []
    if tasks_md.is_file():
        sources.append(tasks_md)
        groups = _task_groups(read(tasks_md), 2)
    impact = paths_in(first_section(proposal, "impact"))
    if impact and not any(g.paths for g in groups):
        groups.append(Group("The code the proposal's Impact names", impact))
    design = ""
    if design_md.is_file():
        sources.insert(1, design_md)
        design = _design(design_md, _first(first_section(read(design_md), "decisions") or first_section(read(design_md), "context")))
    else:
        changes = items(first_section(proposal, "what changes"))
        design = "What changes, from the proposal: " + "; ".join(changes) if changes else ""
    notes = [] if acceptance else ["the change has no spec delta scenario: write the Acceptance items"]
    return Plan(title, intent, acceptance, groups, design, sources, notes=notes)


# ---- Kiro -----------------------------------------------------------------------------------------------------

_EARS_START = re.compile(r"^(WHEN|IF|WHILE|WHERE|GIVEN)\b", re.I)


def ears(text: str) -> list[str]:
    """EARS requirements: every line holding SHALL, joined with the WHEN / IF / WHILE / WHERE lines just before it
    (the docs' two-line form), each tagged with the heading it sits under."""
    out: list[str] = []
    heading = ""
    pending: list[str] = []
    for line in re.sub(r"<!--.*?-->", "", text, flags=re.S).splitlines():
        m = _HEADING.match(line)
        if m:
            heading = plain(m.group(2)) if len(m.group(1)) <= 3 else heading
            pending = []
            continue
        body = plain(_LIST.sub("", line, count=1))
        if not body:
            pending = []
            continue
        if re.search(r"\bSHALL\b", body):
            full = " ".join([*pending, body])
            out.append(f"{full} ({heading})" if heading else full)
            pending = []
        elif _EARS_START.match(body):
            pending.append(body)
    return out


def read_kiro(path: Path) -> Plan:
    folder = path.parent if path.is_file() else path
    req, bug = folder / "requirements.md", folder / "bugfix.md"
    first_file = req if req.is_file() else bug
    if not first_file.is_file():
        raise ValueError(f"{folder}: no requirements.md or bugfix.md; pass a Kiro spec folder, such as .kiro/specs/user-auth/")
    text = read(first_file)
    sources = [first_file]
    title = title_from_slug(folder.name)
    if first_file is bug:
        intent = first_section(text, "current behavior") or _first(text)
        acceptance = ears(first_section(text, "expected behavior") + "\n\n" + first_section(text, "unchanged behavior"))
        ctype = "fix"
    else:
        intent = first_section(text, "introduction") or _first(text)
        acceptance = ears(text)
        ctype = "feat"
    design_md, tasks_md = folder / "design.md", folder / "tasks.md"
    design = ""
    if design_md.is_file():
        sources.append(design_md)
        design = _design(design_md, _first(first_section(read(design_md), "overview") or read(design_md)))
    groups: list[Group] = []
    if tasks_md.is_file():
        sources.append(tasks_md)
        groups = _task_groups(read(tasks_md), 0, re.compile(r"^[-*+][ \t]+\[[ xX~-]?\][ \t]*\d*\.?[ \t]*(.+)$"))
    notes = [] if acceptance else [f"{first_file.name} has no EARS requirement (a line with SHALL): write the Acceptance items"]
    return Plan(title, intent, acceptance, groups, design, sources, ctype=ctype, notes=notes)


# ---- BMAD -----------------------------------------------------------------------------------------------------


def read_bmad(path: Path) -> Plan:
    if not path.is_file():
        raise ValueError(f"{path}: pass one BMAD story file, such as _bmad-output/implementation-artifacts/1-2-user-login.md; one story becomes one Spec")
    text = read(path)
    head = next((name for level, name, _ in sections(text) if level == 1), "")
    m = re.match(r"Story\s+[\w.-]+\s*:\s*(.+)", plain(head), re.I)
    title = m.group(1).strip() if m else (plain(head) or title_from_slug(path.stem))
    intent = first_section(text, "story") or first_section(text, "description") or _first(text)
    acceptance = items(first_section(text, "acceptance criteria"))
    tasks_text = first_section(text, "tasks")
    groups = _task_groups(tasks_text, 0, re.compile(r"^[-*+][ \t]+\[[ xX]?\][ \t]*(.+)$"))
    notes_paths = paths_in(first_section(text, "dev notes"))
    if notes_paths and not any(g.paths for g in groups):
        groups.append(Group("The files the story's Dev Notes name", notes_paths))
    design = "The story's Dev Notes and References hold the approach and the architecture it follows." if first_section(text, "dev notes") else ""
    notes = [] if acceptance else ["the story has no Acceptance Criteria: write the Acceptance items"]
    return Plan(title, intent, acceptance, groups, design, [path], notes=notes)


READERS = {"speckit": read_speckit, "openspec": read_openspec, "kiro": read_kiro, "bmad": read_bmad}


# ---- Writing the Spec ---------------------------------------------------------------------------------------------


def next_id(root: Path, specs_dir: str) -> str:
    """SPEC-<n>, one past the highest SPEC-<n> under the Specs folder, here or on any local branch."""
    return workitems.next_id(root, "SPEC", specs_dir)


def _replace_section(body: str, name: str, content: str) -> str:
    """The body with the text under `## name` replaced by `content` (template comments included)."""
    m = re.search(rf"(?m)^## {re.escape(name)}[ \t]*\n", body)
    if not m:
        return body
    nxt = re.search(r"(?m)^## ", body[m.end() :])
    end = m.end() + nxt.start() if nxt else len(body)
    return body[: m.end()] + "\n" + content.strip() + "\n\n" + body[end:].lstrip("\n")


def _tasks_yaml(spec_id: str, groups: list[Group], scopes: list[list[str]] | None = None) -> str:
    """The `tasks` list, one entry per group in the source's order, with `scopes` as their scopes when given (the
    folders, workitems.folder_scope); each depends on every earlier one whose files it overlaps, so two Tasks that change
    different files of one folder still run side by side."""
    tasks = []
    kept: list[tuple[str, list[str]]] = []
    for i, g in enumerate(groups, 1):
        tid = f"{spec_id}-T{i}"
        deps = [kid for kid, files in kept if any(globs.overlap(a, b) for a in g.paths for b in files)]
        scope = scopes[i - 1] if scopes else g.paths
        tasks.append({"id": tid, "title": g.title[:200], "scope": scope} | ({"depends_on": deps} if deps else {}))
        kept.append((tid, g.paths))
    return strict_yaml.dump({"tasks": tasks}).rstrip("\n")


def _link(target: Path, spec_dir: Path) -> str:
    return Path(os.path.relpath(target.resolve(), spec_dir.resolve())).as_posix()


def build_imported_spec(
    tool: str,
    source: Path,
    root: Path,
    cfg: config.Config,
    *,
    spec_id: str | None = None,
    out: str | None = None,
    title: str | None = None,
    ctype: str | None = None,
) -> tuple[Path, list[str]]:
    """Write the Spec for `source` (a path under `root`) and return it with the lines to print."""
    if tool not in READERS:
        raise ValueError(f"unknown tool {tool!r}: one of {', '.join(LABELS)}")
    if not source.exists():
        raise ValueError(f"{source} does not exist")
    plan = READERS[tool](source)
    specs_dir = globs.normal_dir(out) if out else cfg.specs_dir
    spec_id = spec_id or next_id(root, specs_dir)
    kind = ctype or plan.ctype
    # A path inside a planning tool's own folders is the plan, never the code a Task changes.
    groups = [Group(g.title, [p for p in g.paths if not is_test_path(p) and not p.startswith(_PLANNING)]) for g in plan.groups]
    test_paths = list(dict.fromkeys(p for g in plan.groups for p in g.paths if is_test_path(p) and not p.startswith(_PLANNING)))
    groups = [g for g in groups if g.paths][:MAX_TASKS]
    lines: list[str] = []
    scope = [p for g in groups for p in g.paths]
    dimensions: list[str] = []
    scopes: list[list[str]] | None = None
    if scope:
        a = gate.assess_paths(cfg, list(dict.fromkeys(scope)), ctype=kind)
        route = max("normal", a.required_route, key=gate.ROUTE_RANK.__getitem__)
        dimensions = sorted(a.dimensions)
        lines.append(f"route: {route} (the minimum for the paths the source names is {a.required_route}, {a.lane} lane; an imported plan is a Spec)")
        lines += [f"  - {x}" for x in gate.reason_lines(a)]
        # Each Task's scope is the folders its files sit in, as `aidd new spec --paths` writes it: a protected or risky
        # file stays exact.
        scopes = [workitems.folder_scope(g.paths, {h.path for h in a.hits}) for g in groups]
    else:
        route = "normal"
        lines.append("route: normal (the source names no file path, so the route could not be computed: fill the Task's scope, then `aidd gate --paths`)")
    path = workitems.new_object(
        root,
        workitems.NewObject(
            kind="spec",
            id=spec_id,
            title=title or plan.title,
            route=route,
            ctype=kind,
            owner_team=cfg.get("owners", "default_owner_team", default="") or "",
            specs_dir=specs_dir,
            dimensions=dimensions or None,
        ),
    )
    text = path.read_text(encoding="utf-8")
    head, sep, body = text.partition("\n---\n")
    if groups:
        start = head.index("\ntasks:\n") + 1
        end = head.index("\n\n", start)
        head = head[:start] + _tasks_yaml(spec_id, groups, scopes) + head[end:]
    if test_paths:
        shown = ", ".join(test_paths[:5]) + (f", and {len(test_paths) - 5} more" if len(test_paths) > 5 else "")
        head = re.sub(
            r'(?m)^( +files: \["tests/TODO"\])[^\n]*$',
            lambda m: f"{m.group(1)}  # the source names these test files: {shown}; list the ones this Spec freezes",
            head,
            count=1,
        )
    spec_dir = path.parent
    links = ", ".join(f"[{_link(s, root)}]({_link(s, spec_dir)})" for s in plan.sources)
    intent = f"Source: {LABELS[tool]}, {links}. The plan stays there; this Spec points at it.\n\n"
    intent += quote(plan.intent) if plan.intent.strip() else "TODO: quote the request."
    body = _replace_section(body, "Intent", intent)
    accepted = plan.acceptance[:MAX_ACCEPTANCE]
    acceptance = "\n".join(f"- A{i}: {a}" for i, a in enumerate(accepted, 1)) or "- A1: TODO: given ..., when ..., then ..."
    if len(plan.acceptance) > MAX_ACCEPTANCE:
        acceptance += f"\n\nThe source has {len(plan.acceptance) - MAX_ACCEPTANCE} more; this change is probably more than one Spec."
    body = _replace_section(body, "Acceptance", acceptance)
    design = re.sub(r"\{link:([^}]+)\}", lambda m: _link(Path(m.group(1)), spec_dir), plan.design)
    if design:
        body = _replace_section(body, "Design", design)
    path.write_text(head + sep + body, encoding="utf-8")
    todo = ["tests.files and the test command (the source's tests are not assumed)", "Rollback"]
    if not groups:
        todo.insert(0, "the Task's scope")
    if not design:
        todo.append("Design")
    lines += [f"note: {n}" for n in plan.notes]
    lines.append(f"next: fill {', '.join(todo)}, write the test files, then `aidd validate {path.relative_to(root).as_posix()}`")
    return path, lines


_PLANNING = ("specs/", "openspec/", ".kiro/", "_bmad-output/", "_bmad/", ".specify/", ".bmad-core/")
