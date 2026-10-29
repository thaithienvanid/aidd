"""Which aidd-team role writes what: a subagent's role, its write area with the active Specs filled in, and the
roles that own a path.
"""

from __future__ import annotations

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


# Marks a frozen view entry with the Tasks its recorded approval froze (frozen_files.frozen_view): `{scope:assigned}`
# reads them there, never from the working tree, so a Task a role writes for itself opens nothing.
APPROVED_TASKS = "_approved_tasks"
START_DENY = "only the lead starts another aidd-team role: a role starts its own type, or a helper"


def start_denial(event: dict, started: str, cfg: config.Config | None, *, unheld: bool = False) -> str | None:
    """Why the agent in `event` may not start a subagent of type `started`, or None. The lead (the main session) starts
    any; a role starts its own type, so it can split its work; anyone starts a helper while helpers only read. So a
    verifier never starts a developer to fix the code it checks, and a helper never starts a role that writes. A type
    is read in any case and spacing, so `AIDD-Developer` is the developer; with `agents.helpers: write` a helper writes,
    so only the lead starts one. `unheld`: the harness would read the started agent as a main session the guard does not
    hold (OpenCode's own agents), so a subagent never starts one."""
    if not event.get("agent_type") or is_main_thread(event):  # the lead, also a main thread run with `--agent`
        return None
    asked = _started_role(started)
    if asked is None and unheld:
        return f"a subagent starts its own role type or a helper, never `{started.strip()}`, which the guard would read as the main session. Hand the step back to the lead"
    if asked is None:
        if cfg is None or config.helpers_mode(cfg.raw) == "read":
            return None
        return "only the lead starts a helper here, since helpers may write in this repository. Hand the step back to the lead"
    if role_of(event) == asked:
        return None
    return f"{START_DENY}. Hand the step back to the lead, which starts `{started.strip()}` itself"


def is_main_thread(event: dict) -> bool:
    """A Claude Code main thread run with `--agent`: Claude Code names a subagent by `agent_id` on every event, and such
    a main thread by `agent_type` alone (2.1.311, pinned live in tests/fixtures/live/claude-code-2.1.311*). Read from the
    event's own fields, only on an event with Claude Code's (`transcript_path`, `permission_mode`) and no other harness's."""
    from aidd.guard import dialects

    claude = isinstance(event.get("transcript_path"), str) and isinstance(event.get("permission_mode"), str)
    return claude and dialects.of(event) is dialects.CLAUDE_CODE and bool(event.get("agent_type")) and not event.get("agent_id")


def _started_role(started: str) -> str | None:
    """The aidd-team role a subagent type names, read in any case and spacing: `aidd-team:<role>`, `aidd-<role>`, or
    the plugin prefix around an `aidd-<role>` name; a bare `developer` is another project's agent (role_of)."""
    prefix, _, name = started.strip().casefold().rpartition(":")
    if prefix not in ("", "aidd-team") or not (prefix or name.startswith(config.TEAM_PREFIX)):
        return None
    name = name.removeprefix(config.TEAM_PREFIX)
    return name if name in knowledge.roles()["roles"] else None


def is_read_only_subagent(event: dict, cfg: config.Config | None) -> bool:
    """A helper, a subagent that is not an aidd-team role: the loop contract's helper rule ("Use AI as a delivery team
    does") lets it read, never write, unless the person's config says `agents.helpers: write`. A config the guard
    cannot read (None) keeps it reading."""
    return bool(event.get("agent_type")) and role_of(event) is None and (cfg is None or config.helpers_mode(cfg.raw) == "read")


def _mine(task: dict, role: str | None) -> bool:
    """A Task assigned to `agent:<role>` belongs to that role alone; an unassigned Task to any role that writes code."""
    who = str(task.get("assignee") or "")
    if not who.startswith("agent:") or who[len("agent:") :] not in knowledge.roles()["roles"]:
        return True
    return role is None or who == f"agent:{role}"


def living_files(role: str | None, docs_dir: str) -> list[str]:
    """The files of the product-level work `role` owns (`loop.documents`: `scope: product`, its `files`), in the
    configured docs folder: the product designer's prototype, `<docs>/design/app/**`, never the rest of `design/`. A kind
    `changed_only_in_a_task`, such as the design system, is left out: only a Task's scope opens its files."""
    documents = knowledge.roles()["loop"]["documents"].values()
    return [
        g.replace("{docs}", docs_dir)
        for d in documents
        if d.get("scope") == "product" and d.get("owner") == role and not d.get("changed_only_in_a_task")
        for g in d.get("files", [])
    ]


def unopened_assignment(role: str, rel: str, specs: list[tuple[str, dict]], drafts: set[str]) -> str | None:
    """Why a Task assigned to `role` by name, whose scope covers `rel`, does not open it yet, with the step that does;
    None when no such Task waits. A draft waits for Spec approval; an approved Spec with no approval recorded on this
    machine waits for one, because a stored status is text the role could write itself."""
    waiting = sorted(
        str(d.get("id"))
        for _, d in specs
        if APPROVED_TASKS not in d
        and any(
            isinstance(t, dict) and t.get("assignee") == f"agent:{role}" and globs.match_any([str(s) for s in t.get("scope") or []], rel)
            for t in d.get("tasks") or []
        )
    )
    if not waiting:
        return None
    ids = ", ".join(waiting)
    if set(waiting) <= drafts:
        return f"{rel} is in a Task of {ids} assigned to the {role}, which opens after Spec approval: ask the person to type `approve <ID>`"
    return (
        f"{rel} is in a Task of {ids} assigned to the {role}, but this machine has no recorded approval of {ids}, and a stored "
        f"status alone never opens a Task assigned by name. Next: the person types `approve {waiting[0]}` here, so aidd records "
        "it, or the Task goes to a builder"
    )


def task_only_files() -> list[str]:
    """The files of every kind `changed_only_in_a_task` (`loop.documents`), such as the design system: the product
    ships them, so only a Task's scope opens them."""
    documents = knowledge.roles()["loop"]["documents"].values()
    return [g for d in documents if d.get("changed_only_in_a_task") for g in d.get("files", [])]


def task_area(role: str | None, fill: dict[str, list[str]]) -> list[str]:
    """The Task scope a role writes in: every Task's for a builder (`{scope}`) and for the lead (no role), the Tasks
    assigned to it by name for a specialist (`{scope:assigned}`), else none."""
    if not role:
        return fill["{scope}"]
    writes = knowledge.roles()["roles"][role]["writes"]
    return [*(fill["{scope}"] if "{scope}" in writes else []), *(fill["{scope:assigned}"] if "{scope:assigned}" in writes else [])]


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
        # Only the Tasks a person assigned to this role by name (`agent:<role>`), as a recorded approval froze them: a
        # specialist's way into files the product ships, such as the product designer's design system.
        "{scope:assigned}": [
            s
            for _, d in specs
            for task in d.get(APPROVED_TASKS) or []
            if role and isinstance(task, dict) and task.get("assignee") == f"agent:{role}"
            for s in task.get("scope") or []
        ],
        # The walking skeleton's Tasks: the architect's or the SRE's to build.
        "{skeleton}": [s for _, d in specs for task in d.get("tasks", []) if task.get("skeleton") is True for s in task.get("scope", [])],
        # Tests written with the code (`tests.mode: with_code`): never frozen, and the builder's to write in its Task.
        "{tests:with}": [p for _, d in specs if workitems.tests_with(d) for p in (d.get("tests") or {}).get("files", [])],
        "{living}": living_files(role, cfg.docs_dir),
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
