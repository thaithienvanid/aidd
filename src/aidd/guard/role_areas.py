"""Which aidd-team role writes what: a subagent's role, its write area with the active Specs filled in, and the
roles that own a path.
"""

from __future__ import annotations

import os
import re

from aidd import config, knowledge, workitems
from aidd.kernel import globs


def role_of(event: dict) -> str | None:
    """The aidd-team role a subagent plays: `aidd-team:<role>` from the plugin, or `aidd-<role>` that
    `aidd init --team` installed as a project agent. A bare `developer` or another plugin's agent with a
    role's name is not a role: any project may have its own agent called `reviewer`."""
    agent = event.get("agent_type") or ""
    prefix, _, name = agent.rpartition(":")
    if prefix == "aidd-team" or (not prefix and name.startswith(config.TEAM_PREFIX)):
        name = name if prefix else name[len(config.TEAM_PREFIX) :]
        return name if name in knowledge.roles()["roles"] else None
    return None


def is_read_only_subagent(event: dict) -> bool:
    """A subagent that is not an aidd-team role: the loop contract's helper rule ("Use AI as a delivery team does") lets it read, never write.

    The person running the session can lift this for their own helpers with AIDD_SUBAGENTS_MAY_WRITE=1 in the
    environment Claude Code starts with; an agent's shell cannot set it for the hook.
    """
    return bool(event.get("agent_type")) and role_of(event) is None and os.environ.get("AIDD_SUBAGENTS_MAY_WRITE") != "1"


def _mine(task: dict, role: str | None) -> bool:
    """A Task assigned to `agent:<role>` belongs to that role alone; an unassigned Task to any role that writes code."""
    who = str(task.get("assignee") or "")
    if not who.startswith("agent:") or who[len("agent:") :] not in knowledge.roles()["roles"]:
        return True
    return role is None or who == f"agent:{role}"


def placeholder_fill(cfg: config.Config, specs: list[tuple[str, dict]], role: str | None = None, *, drafts: set[str] | None = None) -> dict[str, list[str]]:
    """What each role-area placeholder covers. With several Specs on the branch, it covers them all. For a Spec not yet
    approved (`drafts`), a role's kind of document also covers its new files of that kind in the Spec's own folder, so it
    writes them before it links them (frozen_files.unlinked_paperwork)."""
    fill = {
        # The work items themselves, each one file directly in the specs folder; a work item's folder (`specs/<ID>/`)
        # holds documents that other roles own, each by its kind.
        "{specs_dir}": [globs.under(cfg.specs_dir, "*.md")],
        "{proposals_dir}": [globs.under(cfg.proposals_dir, "**")],
        "{spec}": [rel for rel, _ in specs],
        "{tests}": [p for _, d in specs for p in (d.get("tests") or {}).get("files", [])],
        "{design}": [p for _, d in specs for p in (d.get("design") or {}).get("files", [])],
        # Every exploration's home, Spec active or not: an exploration often comes before the Spec it informs.
        "{explorations}": [globs.under(cfg.specs_dir, "*/explore/**"), globs.under(cfg.specs_dir, "explore/**")],
        "{docs}": [p for _, d in specs for p in workitems.frozen_docs(d)],
        **{f"{{docs:{k}}}": _docs_of(specs, k) for k in config.DOC_KINDS},
        "{scope}": [s for _, d in specs for task in d.get("tasks", []) if _mine(task, role) for s in task.get("scope", [])],
        # The walking skeleton's Tasks: the architect's or the SRE's to build.
        "{skeleton}": [s for _, d in specs for task in d.get("tasks", []) if task.get("skeleton") is True for s in task.get("scope", [])],
        # Tests written with the code (`tests.mode: with_code`): never frozen, and the implementer's to write in its Task.
        "{tests:with}": [p for _, d in specs if workitems.tests_with(d) for p in (d.get("tests") or {}).get("files", [])],
    }
    # Only for a role that implements one of that Spec's Tasks.
    fill["{scope}"] += [
        p for _, d in specs if workitems.tests_with(d) and any(_mine(t, role) for t in d.get("tasks", [])) for p in (d.get("tests") or {}).get("files", [])
    ]
    # What Spec approval freezes: the tests of every Spec that tests first.
    fill["{tests:first}"] = [p for _, d in specs if not workitems.tests_with(d) for p in (d.get("tests") or {}).get("files", [])]
    for sid in safe_draft_ids(cfg, specs, drafts or set()):
        fill["{design}"].append(globs.under(cfg.specs_dir, f"{sid}/design/**"))
        for kind in config.DOC_KINDS:
            fill[f"{{docs:{kind}}}"].append(globs.under(cfg.specs_dir, f"{sid}/{kind}-*.md"))
    return fill


# A work item's id that may name its folder in a path pattern: letters and digits, a hyphen, a number (`SPEC-3`).
_PLAIN_ID = re.compile(r"[A-Za-z][A-Za-z0-9]*-[0-9]+")


def safe_draft_ids(cfg: config.Config, specs: list[tuple[str, dict]], drafts: set[str]) -> list[str]:
    """The draft Specs' ids that may name a folder in a path pattern: a plain id (`SPEC-3`, no glob or path character)
    that is also the Spec file's own name (`specs/SPEC-3.md`). An agent writes a draft's `id`, so `*` never opens every
    Spec's folder."""
    return sorted(
        str(d.get("id"))
        for rel, d in specs
        if str(d.get("id")) in drafts and _PLAIN_ID.fullmatch(str(d.get("id"))) and rel == globs.under(cfg.specs_dir, f"{d.get('id')}.md")
    )


def _docs_of(specs: list[tuple[str, dict]], kind: str) -> list[str]:
    """The docs of one kind the active Specs link, frozen or living: `{docs:<kind>}` in a role's write area. A frozen
    one is then frozen by Spec approval; a living one (`frozen: false`) is implementation, so it must also sit in a
    Task's scope, as the gate's scope rule reads it."""
    return [d["path"] for _, s in specs for d in s.get("docs") or [] if isinstance(d, dict) and d.get("kind") == kind and isinstance(d.get("path"), str)]


def write_area(role: str, unfrozen: bool) -> list[str]:
    """The role's write area. `unfrozen`: every active Spec is an emergency backfill, where nothing is frozen yet, so
    the role's `writes_unfrozen` (the developer's regression test) joins its area."""
    r = knowledge.roles()["roles"][role]
    return list(r["writes"]) + (list(r.get("writes_unfrozen", [])) if unfrozen else [])


def role_allows(role: str, rel: str, fill: dict[str, list[str]], unfrozen: bool = False) -> tuple[bool, str]:
    """Whether `rel` is in the role's area, and the area in words."""

    writes = write_area(role, unfrozen)
    patterns = [p for w in writes for p in fill.get(w, [w])]
    return globs.match_any(patterns, rel), knowledge.role_writes(writes)


def outside_area(role: str, rel: str, fill: dict[str, list[str]], unfrozen: bool = False, fill_of=None) -> str:
    """Why `rel` is outside the role's area, and where its work goes instead: to the aidd command that writes aidd's
    output, to the role whose area holds it, or, when no role writes it, into the handoff note for a person. `fill_of`
    gives another role's own fill: a Task assigned to `agent:<role>` is in that role's scope alone."""
    if globs.match_any([".aidd/*/**"], rel):  # a folder in .aidd/ is aidd's output (config.OUTPUT_IGNORE)
        return (
            f"{rel} is aidd's output, outside the area of the {role} role: run the aidd command that writes it instead "
            "(`aidd test` for the evidence, `aidd record artifacts <head-sha>` for the preview list, `--html` for a page)"
        )
    writes = write_area(role, unfrozen)
    head = f"the {role} role writes only {role_allows(role, rel, fill, unfrozen)[1]}" if writes else f"the {role} role is read-only and writes no file"
    roles = knowledge.roles()
    owners = [r for r in roles["order"] if r != role and roles["roles"][r]["writes"] and role_allows(r, rel, fill_of(r) if fill_of else fill)[0]]
    if owners:
        return f"{head}; {rel} belongs to the {' or the '.join(owners)} role. Hand it off in your handoff note"
    return f"{head}; no role's area holds {rel} now. Put what you found in your handoff note: a Task's scope, or a person, decides who writes it"


def owners_of(root: str, cfg: config.Config, rel: str) -> list[str]:
    """The aidd-team roles whose write area holds `rel`, in the registry's order."""
    fill = placeholder_fill(cfg, workitems.active_specs(root, cfg))
    roles = knowledge.roles()
    return [r for r in roles["order"] if roles["roles"][r]["writes"] and role_allows(r, rel, fill)[0]]
