"""What the load refuses in a config's `delegation` block beyond what the schema's shape says: a delegation names the person it
stands for, so an agent's or a bot's identity in `by` fails the load, and a delegation that fails to load widens nothing."""

from __future__ import annotations

from aidd.config import identities
from aidd.kernel import json_schema
from aidd.kernel.documents import one_line


def delegation_problems(raw: dict) -> list[tuple[str, str]]:
    """(schema path, message) for a delegation set by an agent or a bot, by the rule a waiver's `by` meets (`approver_is_agent`). The
    load refuses it, so a delegation that names no person widens nothing. It reads only a string, and the schema judges any other value."""
    delegation = raw.get("delegation")
    who = delegation.get("by") if isinstance(delegation, dict) else None
    if not isinstance(who, str) or not identities.approver_is_agent(who):
        return []
    shown = one_line(who, 120)
    return [
        (
            "$.delegation.by",
            f"delegation.by `{shown}` is an agent or a bot, and a delegation stands for a person: write the `Name <email>` you commit with ({identities.one_word_hint(takes_email=False)})",
        )
    ]


def delegation_refusals(raw: dict) -> list[str]:
    """Why the load refuses the `delegation` of a config's data, each as the load words it (`$.delegation.by: ...`): the schema's
    errors under `delegation`, then `delegation_problems`. An empty list when it loads. A problem elsewhere in the config is no part of it."""
    schema = [e for e in json_schema.validate(raw, "config.schema.json") if e.startswith("$.delegation")]
    return schema + [message for _, message in delegation_problems(raw)]


def delegation_by_refusal(who: str) -> str | None:
    """Why the load refuses `who` as `delegation.by`, the schema's own error, or None when it loads as one: what `aidd init --delegate` asks
    of git's name and address before it writes a block that would not load. The pattern in schemas/config.schema.json is the one owner of
    what `by` may hold, so nothing here restates it."""
    return next((e for e in delegation_refusals({"delegation": {"by": who}}) if e.startswith("$.delegation.by")), None)
