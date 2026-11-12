"""Move a repository's files from an earlier shape of aidd's to today's (`aidd upgrade`): the rows of schemas/retired-names.json applied to
the config, the work items, the runbooks and postmortems, and the edited copies of library standards. The shape is read from the keys,
never from a version: a row applies where its old name is in a file, and no file keeps a record of what ran, so a second run finds
nothing. Each file is edited as text, one key at a time (kernel.yaml_edit), so a person's comments, order, quoting, and line endings stay, and each file is read again and compared with the data it should hold before it
is changed. The data a row gives is the reading a check makes of a commit before the upgrade: each row is read first through the function
the readers share (`config.apply_row`, `workitems.apply_row`, `retired_names.apply_row`), the edit must give that data, and a row that
function refuses stays as it is, with its reason. So the file the upgrade writes reads as the old one reads, and a name left for a person
is one a reader refuses too. A name the engine cannot place on a line of its own stays as it is and is named, with the next step. `plan`
changes nothing; `apply` writes what `plan` returned, so a dry run and a real run are one computation."""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from aidd import config, workitems
from aidd.kernel import globs, regular_files, retired_names, secret_patterns
from aidd.kernel.retired_names import Row
from aidd.setup.migration_blocks import Block as _Block
from aidd.setup.migration_blocks import Key, Line
from aidd.setup.migration_blocks import Stays as _Stays
from aidd.setup.migration_files import Ctx as _Ctx
from aidd.setup.migration_files import config_sources, copy_sources, item_sources


@dataclass
class Plan:
    """What `aidd upgrade` would change in the files migrating covers: a line for each change, note, and name left alone, and the
    new text of each file that changes, by its path from the repository's top."""

    lines: list[Line] = field(default_factory=list)
    texts: dict[str, str] = field(default_factory=dict)


_shown_value = retired_names.shown_value


# The function of each `value` row, by the row's id: it edits one key of a file as text, and says in a few words what it did. Release 1.0.0 has no
# such row: the first one added later brings its function here, and `_Ctx` is the argument it shares across files.
VALUES: dict[str, Callable[[_Block, Key, _Ctx], str]] = {}

_READERS: dict[str, Callable[[dict, Row, Key], None]] = {
    "config": config.apply_row,
    "exploration": lambda data, row, path: retired_names.apply_row(data, row, path, {}),
    "handoff": lambda data, row, path: retired_names.apply_row(data, row, path, {}),
    "intent": workitems.apply_row,
    "postmortem": workitems.apply_row,
    "proposal": workitems.apply_row,
    "release": workitems.apply_row,
    "runbook": workitems.apply_row,
    "spec": workitems.apply_row,
    "standard": lambda data, row, path: retired_names.apply_row(data, row, path, {}),
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
    elif row["rule"] == "cut":
        value = block.cut(path)
        block.say("migrate", f"cut {block.name(path)} = {_shown_value(value)} ({since}): {row['note']}")
    elif said := VALUES[row["id"]](block, path, ctx):  # a value that is already today's says nothing
        block.say("migrate", f"{said} ({since})")


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


def plan(root: Path) -> Plan:
    """What migrating changes in `root`, without writing any of it. A config aidd cannot read is a ValueError that names its line."""
    result = Plan()
    ctx = _Ctx()
    configs = config_sources(root, result.lines)
    if not configs:
        return result
    main = configs[0].blocks[0].data
    folder = lambda key, default: globs.normal_dir(str(main.get(key) or default))  # noqa: E731
    items = item_sources(root, folder("specs_dir", "specs"), folder("proposals_dir", "proposals"), folder("product_dir", "product"))
    sources = [*configs, *items, *copy_sources(root, main)]
    for source in sources:
        for block in source.blocks:
            _migrate_block(block, ctx)
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
    return result


def apply(root: Path, found: Plan) -> None:
    """Write what `plan` returned: each file's new text."""
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
    verb = {
        "migrate": "migrated  " if yes else "would migrate ",
        "note": "note     ",
        "manual": "manual   ",
    }
    return [f"{verb[kind]}{_printable(text)}" for kind, text in found.lines]
