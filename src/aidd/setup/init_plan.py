"""What `aidd init` would do (`aidd init --dry-run`): the real init, run inside a plan, so every write is held and none is
made. The dry run prints the lines the real run prints and the config the real run writes, because they come from one code
path, `adoption.init`. Only what the machine alone decides can differ: a Claude Code plugin install is taken as it would go."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from aidd import config
from aidd.kernel import regular_files
from aidd.setup import adoption

# The past-tense word a line of init's output starts with, and what it reads as before the action: init has not run.
_WOULD = {
    "wrote": "would write",
    "vendored": "would vendor",
    "linked": "would link",
    "copied": "would copy",
    "updated": "would update",
    "appended": "would append",
    "ran": "would run",
    "removed": "would remove",
    "pinned": "would pin",
}
# The same for a line that starts with the topic it is about (`risk     wrote the sensitive areas`, `config   changed owners`).
_TOPIC_WOULD = {"wrote": "would write", "changed": "would change", "added": "would add", "dropped": "would drop"}
_VERB = re.compile(r"^(\w+)\s+(.*)$", re.S)
_TOPIC = re.compile(r"^((?:risk|config)\s+)(\w+)(\s+.*)$", re.S)


@dataclass(frozen=True)
class Plan:
    """What a run of init with these options does. `actions` are its lines; `writes` each repository file it writes, by path
    from the top, with the text it would hold; `removals` each it deletes. `config` is the config the run leaves, and `config_heading` says what it is:
    the file as the run writes it, the one `--force` leaves as it is, or, when init keeps the file there, the config it
    generates for you to compare."""

    actions: list[str]
    writes: dict[str, str]
    removals: list[str]
    config: str
    config_heading: str


def plan_init(root: Path, options: adoption.InitOptions) -> Plan:
    """Run `adoption.init` with every write held, and read what it would have written."""
    with regular_files.holding_writes() as held:
        actions = adoption.init(root, options)
        removals = regular_files.held_removals()
    planned = adoption.planned_config(root, options)
    if config.CONFIG_PATH in held:
        text, heading = held[config.CONFIG_PATH], "The config `aidd init` writes"
    elif planned.old is not None:
        text, heading = planned.text, "The config `aidd init --force` leaves as it is"
    else:
        text, heading = planned.fresh, "The config `aidd init` generates; it keeps the one that is there"
    return Plan(actions, dict(held), removals, text, heading)


def dry_run_lines(actions: list[str]) -> list[str]:
    """A plan's lines as a dry run says them: `wrote x` is `would write x`, `config   changed x` is `config   would change x`,
    and a line that says what init kept, skipped, noted, or hints is as it is."""
    out = []
    for line in actions:
        m, topic = _VERB.match(line), _TOPIC.match(line)
        if m and m.group(1) in _WOULD:
            out.append(f"{_WOULD[m.group(1)]} {m.group(2)}")
        elif topic and topic.group(2) in _TOPIC_WOULD:
            out.append(f"{topic.group(1)}{_TOPIC_WOULD[topic.group(2)]}{topic.group(3)}")
        else:
            out.append(line)
    return out
