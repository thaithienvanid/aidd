"""Move a repository's files from an earlier shape of aidd's to today's (`aidd upgrade`): the rows of schemas/retired-names.json
applied to the config, the work items, the runbooks and postmortems, the edited copies of library standards, and the product
prototype's sitemap, which is JSON. The shape is read from the keys, never from a
version: a row applies where its old name is in a file, and no file keeps a record of what ran, so a second run finds nothing. Each
file is edited as text, one key at a time (kernel.yaml_edit), so a person's comments, order, quoting, and line endings stay, and each
file is read again and compared with the data it should hold before it is changed. The data a row gives is the reading a check makes
of a commit before the upgrade: each row is read first through the function the readers share (`config.apply_row`,
`workitems.apply_row`, `retired_names.apply_row`), the edit must give that data, and a row that function refuses stays as it is,
with its reason. So the file the upgrade writes reads as the old one reads, and a name left for a person is one a reader refuses too.
A name the engine cannot place on a line of its own stays as it is and is named, with the next step. `plan` changes nothing; `apply` writes what `plan` returned, so a dry run and a real run are
one computation."""

from __future__ import annotations

import copy
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from aidd import config, workitems
from aidd.kernel import documents, globs, regular_files, retired_names, secret_patterns, yaml_edit
from aidd.kernel.retired_names import Row
from aidd.setup.migration_blocks import Block as _Block
from aidd.setup.migration_blocks import Key, Line
from aidd.setup.migration_blocks import Stays as _Stays
from aidd.setup.migration_blocks import at as _at

# The fence of a handoff note in a work item (workitems.handoff_notes owns the note's format).
_HANDOFF = re.compile(r"^```aidd-handoff[ \t]*\r?\n(.*?)^```[ \t]*$", re.S | re.M)
# The front matter types whose retired names the engine moves, each its own surface of schemas/retired-names.json.
_TYPE_SURFACE = {t: t for t in config.types_of_form("work_item", "typed_document")}
# The product prototype's sitemap, under the docs folder: the prototype tool's `APP` and `SITEMAP` (plugins/aidd-team/tools/prototype).
SITEMAP = "design/app/sitemap.json"


@dataclass
class Plan:
    """What `aidd upgrade` would change in the files migrating covers: a line for each change, note, and name left alone, and the
    new text of each file that changes, by its path from the repository's top."""

    lines: list[Line] = field(default_factory=list)
    texts: dict[str, str] = field(default_factory=dict)


@dataclass
class _Ctx:
    """What one run shares across files: the Intents and Specs by id, what the config said of which team owns which Intent, and the
    Specs that wait for another one (a `blocks` entry), by the id of the one waited for."""

    intents: dict[str, _Block] = field(default_factory=dict)
    specs: dict[str, _Block] = field(default_factory=dict)
    waits: dict[str, list[str]] = field(default_factory=dict)
    owners: dict[str, str] = field(default_factory=dict)
    teams: set[str] = field(default_factory=set)
    config_rel: str = config.CONFIG_PATH
    loose: list[Line] = field(default_factory=list)  # lines that belong to no file of the run


_shown_value = retired_names.shown_value


def _intents(block: _Block, path: Key, ctx: _Ctx) -> str:
    """`delivery_teams.<team>.intents` is cut, and each Intent it lists gets that team as its `delivery_team` once every file is read."""
    ids = _at(block.data, path)
    team = str(path[1])
    block.cut(path)
    for intent in ids:
        if ctx.owners.setdefault(intent, team) != team:
            block.say("note", f"{intent} is listed under {ctx.owners[intent]} and {team}; {ctx.owners[intent]} keeps it")
    return f"cut {retired_names.shown(path)} = {_shown_value(ids)}; each Intent it lists gets this team as its `delivery_team`"


def _default_branch_deploys(block: _Block, path: Key, ctx: _Ctx) -> str:
    """`delegation.default_branch_deploys` is cut: `false` says nothing is lost, and `true` is cut only where an `environments` entry
    lists the default branch (`config.apply_row` refused any other), which the line names."""
    value = _at(block.data, path)
    covered = config.deploying_environments(block.data) if value is True else []
    block.cut(path)
    said = (
        f"; `environments` says it, in {', '.join(_shown_value(n) for n in covered)}"
        if covered
        else "; `environments` says where a merge deploys, and a delegated merge waits for a person until it lists the default branch"
    )
    return f"cut {retired_names.shown(path)} = {_shown_value(value)}{said}"


def _docs_required(block: _Block, path: Key, ctx: _Ctx) -> str:
    """`docs.required` becomes `docs.disabled`: `off` is a disabled type with a reason, and `warn`, the default, is dropped."""
    required = _at(block.data, path)
    disabled = block.data["docs"].get("disabled") or {}
    said = []
    for old, level in required.items():
        new = config.DOC_TYPES_RENAMED.get(str(old), str(old))
        if level == "warn":
            said.append(f"{old} warn dropped (the default)")
        elif new in disabled:
            said.append(f"{old} off dropped ({new} is disabled already)")
        else:
            block.add(("docs", "disabled", new), config.DISABLED_REASON)
            said.append(f"{old} off -> docs.disabled.{new}")
    block.cut(path)
    return f"docs.required -> docs.disabled ({'; '.join(said) or 'it was empty'})"


def _rule_check(block: _Block, path: Key, ctx: _Ctx) -> str:
    """A project rule's `check` that names a `tests` entry becomes `enforced_by: [that name]`; a command no entry holds stays."""
    value = _at(block.data, path)
    block.rename_key(path, "enforced_by")
    block.set_value((*path[:-1], "enforced_by"), [value])
    return f"{retired_names.shown(path)} {value} -> enforced_by [{value}]"


# A library standard's old keys, and the key each became under `citation`.
CITATION_KEYS = {"source": "url", "evidence": "quote"}


def _citation(block: _Block, path: Key, ctx: _Ctx) -> str:
    """A library standard's `source` and `evidence` become `citation.url` and `citation.quote`. They move together, so the row of the
    second one finds both moved."""
    old = str(path[-1])
    if old in block.data:
        text = yaml_edit.gather(block.text, "citation", CITATION_KEYS)
        if text is None:
            raise _Stays("it is not on one line of its own, with its value after the colon")
        block.text = text
        block.data["citation"] = {new: block.data.pop(key) for key, new in CITATION_KEYS.items() if key in block.data}
    return f"{retired_names.shown(path)} -> citation.{CITATION_KEYS[old]}"


def _into_risk(block: _Block, path: Key, key: str) -> str:
    """A top-level `residual_risk` or `cost_estimate` becomes `risk.<key>`; a `risk` that is no block, or that holds the key, stays."""
    value = _at(block.data, path)
    block.cut(path)
    block.add(("risk", key), value)
    return f"{retired_names.shown(path)} {_shown_value(value)} -> risk.{key}"


def _put_list(block: _Block, key: str, items: list) -> None:
    """The top-level `key` written as `items` on one line at the end of the front matter, whatever shape it had."""
    if key in block.data:
        block.cut((key,))
    block.add((key,), items)


def _relations(block: _Block, path: Key, ctx: _Ctx) -> str:
    """`relations` becomes `blocked_by`, a `parent` for a Spec's `implements`, and an entry in the other item's `blocked_by` for a
    `blocks`; an entry with no place now (`workitems.apply_row` refuses it), or a `blocks` whose target is no Spec or Intent of this
    repository, leaves the whole list as it is."""
    found = (workitems.sort_intent_relations if block.surface == "intent" else workitems.sort_relations)(_at(block.data, path))
    me = str(block.data.get("id"))
    if gone := [i for i in found.blocks if i not in ctx.specs and i not in ctx.intents]:
        raise _Stays(f"`blocks {gone[0]}` names no Spec or Intent in this repository, so add {me} to its `blocked_by` where it is")
    block.cut(path)
    if found.blocked_by:
        _put_list(block, "blocked_by", list(dict.fromkeys([*(block.data.get("blocked_by") or []), *found.blocked_by])))
    if found.parent and not block.data.get("parent"):
        block.add(("parent",), found.parent)
    for other in found.blocks:
        ctx.waits.setdefault(other, []).append(me)
    placed = [f"blocked_by {_shown_value(found.blocked_by)}" if found.blocked_by else "", f"parent {found.parent}" if found.parent else ""]
    placed += [f"`blocked_by: [{me}]` in {other}" for other in found.blocks]
    return f"relations -> {', '.join(p for p in placed if p) or 'nothing (it was empty)'}"


def _context(block: _Block, path: Key, ctx: _Ctx) -> str:
    """An Intent's `context` is the project glossary's now: an empty one is dropped, and any other value stays for a person to move."""
    value = block.cut(path)
    return f"cut context = {_shown_value(value)}; it held no text"


def _launch(block: _Block, path: Key, ctx: _Ctx) -> str:
    """An Intent's `launch` is its last slice now: one that names the last slice is dropped, and any other stays."""
    value = block.cut(path)
    return f"cut launch = {value}; it is the last slice, which is the launch"


def _slices(block: _Block, path: Key, ctx: _Ctx) -> str:
    """An Intent's `slices` list becomes `phases` with one phase, `P1`, named for the Intent's title. An Intent that lists `phases`
    too keeps both for a person."""
    phase = workitems.one_phase(block.data.get("title"), None)
    block.nest("slices", "phases", {"id": phase["id"], "name": phase["name"]})
    return f"slices -> phases (one phase, {phase['id']}, named {_shown_value(phase['name'])})"


# The comment the Spec templates wrote beside `reversible`, and the one they write beside `irreversible`.
_OLD_TEMPLATE_COMMENT = "false when a revert cannot restore the prior state"
_TEMPLATE_COMMENT = "true when a revert cannot restore the prior state"


def _irreversible(block: _Block, path: Key, ctx: _Ctx) -> str:
    """`risk.reversible` becomes `risk.irreversible` with the opposite value (`workitems.irreversible_of`), and the template's comment
    on its line says what `true` means now; any other comment there is named, because it was written for the old polarity."""
    value = _at(block.data, path)
    flipped = bool(workitems.irreversible_of(value))  # `workitems.apply_row` refused a value that is no boolean
    block.rename_key(path, "irreversible")
    new = (*path[:-1], "irreversible")
    block.set_value(new, flipped)
    lines = block.text.split("\n")
    spot = yaml_edit.locate(block.text, new)
    comment = lines[spot.first][spot.token_end :].partition("#")[2] if spot else ""  # the value is `true` or `false`, so a `#` starts the comment
    if spot and comment.strip().startswith(_OLD_TEMPLATE_COMMENT):
        lines[spot.first] = lines[spot.first].replace(_OLD_TEMPLATE_COMMENT, _TEMPLATE_COMMENT, 1)
        block.text = "\n".join(lines)
    elif comment.strip():
        block.say(
            "note", f"{retired_names.shown(new)} keeps the comment on its line, written for `reversible`: check it says what `{str(flipped).lower()}` means now"
        )
    return f"{retired_names.shown(path)} {_shown_value(value)} -> {retired_names.shown(new)} {_shown_value(flipped)}"


def _change_type(block: _Block, path: Key, ctx: _Ctx) -> str:
    """A retired change type becomes its type and its risk dimension (`workitems.change_type_of`): `deps` is `build`, `infra` is
    `build` with `availability` in `risk.dimensions`, and `data`, `security`, and `compliance` are `feat` with their dimension, which
    a line notes, since a person may pick another type. A type of today says nothing."""
    value = _at(block.data, path)
    moved = workitems.change_type_of(value)
    if moved is None:
        return ""
    kind, dimension = moved
    said = f"{retired_names.shown(path)} {value} -> {kind}"
    if dimension is not None:
        risk = block.data["risk"]  # `workitems.apply_row` refused a Spec with no `risk.dimensions` list to hold it
        if "dimensions" not in risk:
            block.add(("risk", "dimensions"), [dimension])
        elif dimension not in risk["dimensions"]:
            block.set_list(("risk", "dimensions"), [*risk["dimensions"], dimension])
        said += f", with {dimension} in risk.dimensions"
    block.set_value(path, kind)
    if kind == workitems.DEFAULT_CHANGE_TYPE:
        block.say(
            "note",
            f"{retired_names.shown(path)} is {kind}, the type a Spec takes when none is given: if another type fits the change, such as fix, set it by hand",
        )
    return said


def _role(block: _Block, path: Key, ctx: _Ctx) -> str:
    """An `agent:<role>` becomes `role:<role>` (`workitems.role_identity`); any other identity stays, and says nothing."""
    value = _at(block.data, path)
    role = workitems.role_identity(value)
    if role is None:
        return ""
    block.set_value(path, role)
    return f"{retired_names.shown(path)} {value} -> {role}"


def _sitemap_version(data: dict, path: Key) -> None:
    """The data `_sitemap_format` gives: a sitemap's `format`, a whole number, becomes `schema_version`, the same number as a string,
    in its place. Refused for any other value, or when `schema_version` is set too."""
    value = data[path[-1]]
    if type(value) is not int or value < 1:  # `True` is an int to Python, and no version
        raise retired_names.Refused(f"{_shown_value(value)} is no version number, so aidd cannot write it as `schema_version`")
    retired_names.apply_row(data, {"rule": "rename", "new": "schema_version"}, path, {})
    data["schema_version"] = str(value)


def _reads_as(block: _Block, text: str, data: dict) -> bool:
    try:
        return block.parsed(text) == data
    except documents.DocumentError:
        return False


# A JSON key and its whole-number value on a line of their own, as the prototype tool writes a sitemap.
_JSON_NUMBER_LINE = r'(?m)^([ \t]*)"{key}"([ \t]*:[ \t]*)(-?[0-9]+)([ \t]*,?[ \t]*)$'


def _sitemap_format(block: _Block, path: Key, ctx: _Ctx) -> str:
    """A sitemap's `format: 1` becomes `schema_version: "1"` on the line that held it. The line is the one whose edit reads back as the
    data the row gives, so a `format` key inside the sitemap's example data is never the one changed."""
    value = _at(block.data, path)
    expected = copy.deepcopy(block.data)
    _sitemap_version(expected, path)
    pattern = re.compile(_JSON_NUMBER_LINE.format(key=re.escape(str(path[-1]))))
    edits = [
        block.text[: m.start()] + f'{m.group(1)}"schema_version"{m.group(2)}"{value}"{m.group(4)}' + block.text[m.end() :] for m in pattern.finditer(block.text)
    ]
    fits = [text for text in edits if _reads_as(block, text, expected)]
    if len(fits) != 1:
        raise _Stays("it is not on a line of its own, with its number after the colon")
    block.text, block.data = fits[0], expected
    return f'{retired_names.shown(path)} {value} -> schema_version "{value}"'


VALUES: dict[str, Callable[[_Block, Key, _Ctx], str]] = {
    "delegation-default-branch-deploys": _default_branch_deploys,
    "delivery-team-intents": _intents,
    "docs-required": _docs_required,
    "intent-context": _context,
    "intent-launch": _launch,
    "intent-relations": _relations,
    "intent-slices": _slices,
    "project-rule-check": _rule_check,
    "sitemap-format": _sitemap_format,
    "spec-change-type": _change_type,
    "spec-cost-estimate": lambda block, path, ctx: _into_risk(block, path, "cost_estimate"),
    "spec-relations": _relations,
    "spec-residual-risk": lambda block, path, ctx: _into_risk(block, path, "residual"),
    "spec-risk-reversible": _irreversible,
    "spec-suggested-by": _role,
    "spec-task-assignee": _role,
    "standard-evidence": _citation,
    "standard-source": _citation,
}


def _standard_citation(data: dict, path: Key) -> None:
    """The data `_citation` gives: a library standard's `source` and `evidence` under `citation`, unless `citation` is set too."""
    if path[-1] not in data:
        return  # the row of the other key moved both
    if "citation" in data:
        raise retired_names.Refused("`citation` is set too, so remove the old keys by hand")
    data["citation"] = {new: data.pop(key) for key, new in CITATION_KEYS.items() if key in data}


# A library standard's copy, a handoff note, an exploration, and the sitemap are read only as they are, at the head, so the upgrade
# is their one reader of an earlier shape: these functions give the data their rows move to.
STANDARD_VALUES = {"standard-evidence": _standard_citation, "standard-source": _standard_citation}
SITEMAP_VALUES = {"sitemap-format": _sitemap_version}
_READERS: dict[str, Callable[[dict, Row, Key], None]] = {
    "config": config.apply_row,
    "exploration": lambda data, row, path: retired_names.apply_row(data, row, path, {}),
    "handoff": lambda data, row, path: retired_names.apply_row(data, row, path, {}),
    "intent": workitems.apply_row,
    "postmortem": workitems.apply_row,
    "proposal": workitems.apply_row,
    "runbook": workitems.apply_row,
    "sitemap": lambda data, row, path: retired_names.apply_row(data, row, path, SITEMAP_VALUES),
    "spec": workitems.apply_row,
    "standard": lambda data, row, path: retired_names.apply_row(data, row, path, STANDARD_VALUES),
}


def _reading(block: _Block, row: Row, path: Key) -> dict:
    """The data the block must hold once `row` moves the place `path` names: the reading a check makes of a commit before the
    upgrade, from the function the readers share. Where that function refuses, the row stays, with its reason."""
    moved = copy.deepcopy(block.data)
    try:
        _READERS[block.surface](moved, row, path)
    except retired_names.Refused as exc:
        raise _Stays(str(exc)) from None
    return moved


def _apply_row(block: _Block, row: Row, path: Key, ctx: _Ctx) -> None:
    expected = _reading(block, row, path)
    _move(block, row, path, ctx)
    if block.data != expected:
        raise _Stays("the edit would not give the data a reader of an earlier shape gives: make the change by hand")


def _move(block: _Block, row: Row, path: Key, ctx: _Ctx) -> None:
    since = f"retired in {row['retired_in']}"
    if row["rule"] == "rename":
        new = row["new"].rsplit(".", 1)[-1].removesuffix("[]")
        block.rename_key(path, new)
        block.say("migrate", f"{block.name(path)} -> {new} ({since})")
        if block.surface == "spec" and path[0] == "tests" and (block.data.get("approved_by") or block.data.get("approved_at")):
            block.say(
                "note",
                f"{block.name(path)} is in the tests of an approved Spec: the rename is no revision, so `aidd test` and `aidd delegate check` read the approved copy in today's shape and nothing waits for a person",
            )
        if row["id"].endswith("owner-team"):
            _check_team(block, (*path[:-1], new), ctx)
    elif row["rule"] == "cut":
        value = block.cut(path)
        block.say("migrate", f"cut {block.name(path)} = {_shown_value(value)} ({since}): {row['note']}")
    elif said := VALUES[row["id"]](block, path, ctx):  # a value that is already today's says nothing
        block.say("migrate", f"{said} ({since})")


def _check_team(block: _Block, path: Key, ctx: _Ctx) -> None:
    team = _at(block.data, path)
    if ctx.teams and isinstance(team, str) and team not in ctx.teams:
        block.say(
            "note", f"{retired_names.shown(path)} is {team}, which is no key of `delivery_teams` in {ctx.config_rel}: add the team there, or name one that is"
        )


def _migrate_block(block: _Block, ctx: _Ctx) -> None:
    """Every row that applies to `block`, each one whole or not at all."""
    for row, path in retired_names.steps(block.data, block.surface):
        before = (block.text, copy.deepcopy(block.data), list(block.lines))
        try:
            _apply_row(block, row, path, ctx)
        except (_Stays, KeyError, IndexError, TypeError, AttributeError) as exc:
            block.text, block.data, block.lines = before
            reason = f"{exc}" if isinstance(exc, _Stays) else retired_names.PLACE_PROBLEM
            block.say("manual", f"{block.name(path)} was retired in {row['retired_in']} and aidd leaves it: {reason}. {_NEXT[row['rule']](row)}")


_NEXT: dict[str, Callable[[Row], str]] = {
    "rename": lambda row: f"Rename it to `{row['new'].rsplit('.', 1)[-1].removesuffix('[]')}` by hand, then run `aidd upgrade` again",
    "cut": lambda row: f"Remove it by hand ({row['note']}), then run `aidd upgrade` again",
    "value": lambda row: f"Move it by hand ({row['note']}), then run `aidd upgrade` again",
}


class _Source:
    """A file that holds blocks of YAML: its text, and each block's place in it."""

    def __init__(self, rel: str, text: str) -> None:
        self.rel, self.text = rel, text
        self.blocks: list[_Block] = []

    def add(self, surface: str, span: tuple[int, int]) -> None:
        raw = self.text[span[0] : span[1]]
        try:
            self.blocks.append(_Block(self.rel, surface, raw.replace("\r\n", "\n"), span))
        except documents.DocumentError:
            pass  # not YAML aidd reads: `aidd validate` names it

    def rendered(self) -> str:
        """The file with each changed block in place. A block that cannot be written whole stays as it was, with a `manual` line."""
        out, last = [], 0
        for block in self.blocks:
            if not any(kind == "migrate" for kind, _ in block.lines):
                continue
            raw = self.text[block.span[0] : block.span[1]]
            mixed = "\r\n" in raw and re.search(r"(?<!\r)\n", raw)
            if mixed or not block.reads_back():
                why = (
                    "it mixes two kinds of line ending: make them one kind"
                    if mixed
                    else "the edit did not read back as the data it should hold: make the changes by hand"
                )
                block.lines = [(k, w) for k, w in block.lines if k != "migrate"]
                block.say("manual", f"not changed, because {why}. Then run `aidd upgrade` again; `aidd validate` names each retired name")
                continue
            out += [self.text[last : block.span[0]], block.text.replace("\n", "\r\n") if "\r\n" in raw else block.text]
            last = block.span[1]
        return "".join([*out, self.text[last:]])


def _read(root: Path, rel: str) -> str | None:
    text = regular_files.repository_text(root, rel, documents.MAX_DOCUMENT_BYTES)
    return None if text is None or "�" in text or text.startswith("﻿") else text


def _config_sources(root: Path, ctx: _Ctx, lines: list[Line]) -> list[_Source]:
    """The config, and each parent it extends from the repository (a remote parent is only named)."""
    out: list[_Source] = []
    queue, seen = [(config.CONFIG_PATH, 0)], set()
    while queue:
        rel, depth = queue.pop(0)
        if rel in seen or (text := _read(root, rel)) is None:
            continue
        seen.add(rel)
        source = _Source(rel, text)
        source.add("config", (0, len(text)))
        if not source.blocks:
            if rel == config.CONFIG_PATH:
                try:
                    documents.parse_yaml(text, rel)
                except documents.DocumentError as exc:  # a config aidd cannot read stops the upgrade, naming its line
                    raise ValueError(f"{exc}. Fix that line, then run `aidd upgrade` again") from None
            continue
        out.append(source)
        for parent in source.blocks[0].data.get("extends") or []:
            if isinstance(parent, dict) and isinstance(parent.get("path"), str) and depth < 5:
                queue.append((parent["path"], depth + 1))
            elif isinstance(parent, dict) and isinstance(parent.get("url"), str):
                lines.append(
                    (
                        "note",
                        f"{rel}: the parent {documents.one_line(parent['url'], 100)} is remote, so aidd reads and moves nothing in it: if it holds a retired name, its owner moves it",
                    )
                )
        ctx.teams |= set(source.blocks[0].data.get("delivery_teams") or {})
    return out


def _item_sources(root: Path, specs_dir: str, proposals_dir: str, ctx: _Ctx) -> list[_Source]:
    """The work items under the specs and proposals folders, and the runbooks and postmortems in theirs (`workitems.OPS_DIRS`): each
    one's front matter by its type, and each handoff note in it."""
    out: list[_Source] = []
    folders = list(dict.fromkeys([specs_dir, proposals_dir, *workitems.OPS_DIRS.values()]))
    paths = {p for d in folders for p in workitems.object_files(root, d)}
    paths |= {p for p in (root / specs_dir.rstrip("/")).rglob("exploration.md")} if (root / specs_dir.rstrip("/")).is_dir() else set()
    for path in sorted(paths):
        rel = path.relative_to(root).as_posix()
        if (text := _read(root, rel)) is None:
            continue
        source = _Source(rel, text)
        if front := documents.FRONT_MATTER.match(text):
            try:
                kind = str(documents.parse_yaml(front.group(1), rel).get("type"))
            except documents.DocumentError:
                kind = ""
            if kind in _TYPE_SURFACE:
                source.add(_TYPE_SURFACE[kind], front.span(1))
        for note in _HANDOFF.finditer(text):
            source.add("handoff", note.span(1))
        for block in source.blocks:
            if block.surface in workitems.WORK_TYPES and isinstance(block.data.get("id"), str):
                (ctx.intents if block.surface == "intent" else ctx.specs)[block.data["id"]] = block
        out.append(source)
    return out


def _copy_sources(root: Path, main: dict) -> list[_Source]:
    """The edited copies of library standards that the config lists, each one's front matter. An unedited copy is not here:
    `aidd upgrade` writes it again from the library, in today's shape."""
    from aidd import knowledge

    folder = globs.under(globs.normal_dir(str((main.get("docs") or {}).get("dir") or "docs")), "standards/")
    library = knowledge.standards_library()
    out: list[_Source] = []
    for entry in main.get("standards") or []:
        recorded = entry.get("from_library") if isinstance(entry, dict) else None
        if not isinstance(recorded, dict):
            continue
        rel = entry.get("path")
        if not isinstance(rel, str) or not rel.startswith(folder) or any(s.rel == rel for s in out) or (text := _read(root, rel)) is None:
            continue
        front = documents.FRONT_MATTER.match(text)
        if front and knowledge.copy_edited(text, recorded, library.get(str(recorded.get("id")))):
            source = _Source(rel, text)
            source.add("standard", front.span(1))
            out.append(source)
    return out


def _sitemap_sources(root: Path, docs_dir: str) -> list[_Source]:
    """The product prototype's sitemap, read as JSON, when the docs folder holds one."""
    try:
        rel = globs.under(docs_dir, SITEMAP)
    except ValueError:  # a docs folder at the repository's top, which `aidd validate` names
        return []
    if (text := _read(root, rel)) is None:
        return []
    source = _Source(rel, text)
    source.add("sitemap", (0, len(text)))
    return [source] if source.blocks else []


def _give_intents(ctx: _Ctx) -> None:
    """Every Intent a team listed gets that team, unless it names one already (the cross-file write, after every file has its new shape)."""
    for intent, team in ctx.owners.items():
        block = ctx.intents.get(intent)
        if block is None:
            ctx.loose.append(
                ("note", f"{ctx.config_rel}: delivery_teams.{team}.intents listed {intent}, and no Intent file has that id, so it only left the list")
            )
        elif "delivery_team" in block.data:
            if block.data["delivery_team"] != team:
                block.say("note", f"{intent} names {block.data['delivery_team']}, so it keeps that; {ctx.config_rel} listed it under {team}")
        else:
            try:
                block.add(("delivery_team",), team)
                block.say("migrate", f"delivery_team {team} set, from delivery_teams.{team}.intents in {ctx.config_rel} (retired in 1.0.0)")
            except _Stays as exc:
                block.say("manual", f"set delivery_team: {team} by hand ({exc}), then run `aidd upgrade` again")


def _give_waits(ctx: _Ctx) -> None:
    """Every Spec that a `blocks` entry named gets the id of the Spec that waits for it in its `blocked_by` (the cross-file write, after
    every file has its new shape)."""
    for target, waiting in ctx.waits.items():
        block = ctx.specs.get(target) or ctx.intents[target]
        held = block.data.get("blocked_by")
        ids = list(dict.fromkeys([*(held if isinstance(held, list) else []), *waiting]))
        if ids == held:
            continue
        try:
            _put_list(block, "blocked_by", ids)
            block.say("migrate", f"blocked_by {_shown_value(ids)} set, from the `blocks` entries of {', '.join(waiting)} (retired in 1.0.0)")
        except _Stays as exc:
            block.say("manual", f"set blocked_by: {ids} by hand ({exc}), then run `aidd upgrade` again")


def plan(root: Path) -> Plan:
    """What migrating changes in `root`, without writing any of it. A config aidd cannot read is a ValueError that names its line."""
    result = Plan()
    ctx = _Ctx()
    configs = _config_sources(root, ctx, result.lines)
    if not configs:
        return result
    main = configs[0].blocks[0].data
    folder = lambda key, default: globs.normal_dir(str(main.get(key) or default))  # noqa: E731
    items = _item_sources(root, folder("specs_dir", "specs"), folder("proposals_dir", "proposals"), ctx)
    docs = globs.normal_dir(str((main.get("docs") or {}).get("dir") or "docs"))
    sources = [*configs, *items, *_copy_sources(root, main), *_sitemap_sources(root, docs)]
    for source in sources:
        for block in source.blocks:
            _migrate_block(block, ctx)
    _give_intents(ctx)
    _give_waits(ctx)
    for source in sources:
        text = source.rendered()
        lines = [line for block in source.blocks for line in block.lines]
        if text != source.text:
            if refused := regular_files.write_refusal(root, root / source.rel):
                # Nothing is written to this file, so no line names a change to it: only what stays for a person.
                lines = [(kind, words) for kind, words in lines if kind == "manual"]
                lines.append(("manual", f"{source.rel}: not changed, because {refused}"))
            else:
                result.texts[source.rel] = text
        result.lines += lines
    result.lines += ctx.loose
    return result


def apply(root: Path, found: Plan) -> None:
    """Write what `plan` returned."""
    for rel, text in found.texts.items():
        regular_files.write_text_safely(root, rel, text)


def _printable(text: str) -> str:
    """A line with every credential in it hidden (the scrub records and evidence share, `secret_patterns`), and a sentence that says
    where the full value is when one was."""
    hidden = secret_patterns.scrubbed(text)
    return hidden + HISTORY if secret_patterns.REDACTED in hidden else hidden


HISTORY = " A credential is hidden above: the file's own history in git holds the full value."


def words(found: Plan, yes: bool) -> list[str]:
    """`plan`'s lines as `aidd upgrade` prints them: `migrated` once written, `would migrate` in a dry run. A value a line shows
    passes the scrub first, so the output holds no credential the file holds."""
    verb = {"migrate": "migrated  " if yes else "would migrate ", "note": "note     ", "manual": "manual   "}
    return [f"{verb[kind]}{_printable(text)}" for kind, text in found.lines]
