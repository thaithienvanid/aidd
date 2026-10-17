"""The edit check: whether an agent, a role, or a helper may write a repository path under the active Specs
(`check_edit`, `check_agent_edit`), and what a branch changed that the rules deny (`forbidden_changes`).
"""

from __future__ import annotations

from pathlib import Path

from aidd import config, gate, knowledge, workitems
from aidd.guard import decision_files, frozen_files, path_location, repo_config, review_dismissals, role_areas, verdicts
from aidd.kernel import documents, git, globs, repo_paths

# The files that load aidd's guard into a coding agent. On an explore branch, where every other edit is free, an agent
# never changes them: a person does, as the branch name alone is what frees the edits there.
GUARD_WIRING = (".claude/settings.json", ".claude/settings.local.json", ".agents/hooks.json", ".grok/hooks/aidd.json")
WIRING_DENY = "{rel} loads aidd's guard into the coding agent: an agent never changes it on an explore branch. A person edits it"
# The allow where the guard does not hold edits: an explore branch, or a repository whose config switches the loop off.
FREE_EDITS = (
    "edits are free here: an explore branch (free work; nothing merges from it as it is), or components.loop: false in the config. Every edit is allowed"
)


def check_edit(root: str, rel: str, role: str | None = None, old_text: str | None = None, new_text: str | None = None) -> verdicts.Verdict:
    """(decision, reason) for editing the repo-relative path `rel`, optionally as an aidd-team role.

    `old_text` and `new_text`, when the caller knows them (the hook's Edit and Write input), are the file before and
    after the edit: a proposal's go/no-go and sign-off are checked on them. A role first limits the paths to its own
    area; every edit then meets the same Spec rules, listed in the module docstring.
    """
    if loosened := decision_files.config_loosening(rel, old_text, new_text):
        return "deny", f"{rel}: {decision_files.CONFIG_DENY.format(what=loosened)}"
    try:
        cfg = config.load_file(config.CONFIG_PATH, root, fetch=repo_config.offline_fetch, skip_unread=True)
    except (OSError, config.ConfigError, documents.DocumentError, RuntimeError, ValueError):
        problem = path_location.config_problem(root)
        if role and problem:  # an invalid config never disables the guard: a role writes nothing until it is fixed
            return "deny", f"{rel}: {problem}. Until then no aidd-team role writes here; hand the fix to the person"
        return "allow", "no valid .aidd/config.yaml"
    if not workitems.edits_held(cfg, root):
        if rel.casefold() in GUARD_WIRING and config.component_on(cfg.raw, "loop"):
            return "deny", WIRING_DENY.format(rel=rel)
        return "allow", FREE_EDITS
    roles = knowledge.roles()["roles"]
    if role and role not in roles:
        return "deny", f"unknown aidd-team role {role!r}; name one of {', '.join(roles)}"
    protected = globs.first_match(gate.protected_paths(cfg), rel, fold_case=True)
    try:
        return _check_with_specs(root, cfg, rel, role, roles, protected, old_text, new_text)
    except Exception as exc:  # noqa: BLE001  # a protected path's deny never depends on reading a Spec
        if protected:
            return frozen_files.protected_deny(
                rel, protected, f"the guard could not read the active Spec ({type(exc).__name__}), so no approved scope covers it"
            )
        raise


MAX_STOP_PATHS = 500  # the stop check reads at most this many changed paths: it runs inside a hook's time limit


def forbidden_changes(root: str, cfg: config.Config) -> list[tuple[str, str]]:
    """(path, reason) for each path the branch changed that the edit rules deny, once an active Spec's approval holds.

    The edit hook sees only the harness's own edit tools; a shell write through an interpreter, a script, or a build tool
    reaches the file unseen. The stop hook calls this to name those changes after the fact. Before Spec approval
    nothing is named: the Spec is still open, and the gate's scope rule reads the real diff. A test, design file, or
    frozen doc is named only while it differs from what was approved: changed since HEAD, and not what an approval of
    the working tree's hash covers."""
    specs = workitems.active_specs(root, cfg)
    held = frozen_files.approved_spec_ids(root, cfg, specs) if specs else set()
    if not held:
        return []
    roles = knowledge.roles()["roles"]
    fill = role_areas.placeholder_fill(cfg, specs)
    frozen = fill["{tests:first}"] + fill["{design}"] + fill["{docs}"]
    dirty = set(git.dirty(root, untracked=True, check=False))
    worktree_approved: bool | None = None
    found = []
    for rel in git.changed_since(root, git.branch_base(root))[:MAX_STOP_PATHS]:
        if globs.match_any(frozen, rel):
            if rel not in dirty:
                continue  # as committed, which the approval of HEAD's hash covers, or the gate finds stale
            if worktree_approved is None:
                worktree_approved = _worktree_approved(root, cfg, specs)
            if worktree_approved:
                continue
        protected = globs.first_match(gate.protected_paths(cfg), rel, fold_case=True)
        decision, reason = _check_with_specs(root, cfg, rel, None, roles, protected, None, None, specs=specs, held=held)
        if decision == "deny":
            found.append((rel, reason))
    return found


def _worktree_approved(root: str, cfg: config.Config, specs: list[tuple[str, dict]]) -> bool:
    """Whether a local Spec approval names the hash of an active Spec as the working tree holds it (its frozen files as
    they are on disk): then the frozen files are what was approved, committed or not."""
    obs = workitems.Observer(Path(root), cfg)
    if not obs.knows_approvals():
        return False
    for rel, data in specs:
        path = Path(root) / rel
        if path.is_file() and obs.approved(str(data.get("id")), obs.hash_worktree(path.read_text(encoding="utf-8", errors="replace"), data)):
            return True
    return False


def _check_with_specs(
    root: str,
    cfg: config.Config,
    rel: str,
    role: str | None,
    roles: dict,
    protected: str | None,
    old_text: str | None,
    new_text: str | None,
    *,
    specs: list[tuple[str, dict]] | None = None,
    held: set[str] | None = None,
) -> verdicts.Verdict:
    specs = workitems.active_specs(root, cfg) if specs is None else specs
    if not role and not specs:
        return frozen_files.protected_deny(rel, protected, "there is no active Spec") if protected else ("allow", "no active Spec")
    if not role and len(specs) > 1 and not protected:
        return "allow", "several Specs on the branch; the gate's scope rule checks the diff"
    if frozen := frozen_files.frozen_by_carried(root, cfg, specs, rel):
        return "deny", frozen
    held = frozen_files.approved_spec_ids(root, cfg, specs) if held is None and specs else held or set()
    drafts = frozen_files.draft_spec_ids(specs, held)
    fill = role_areas.placeholder_fill(cfg, specs, role, drafts=set(drafts))
    writes = roles[role]["writes"] if role else []
    in_scope = bool(role and roles[role].get("in_scope"))
    own_spec = "{specs_dir}" in writes and globs.match_any(fill["{specs_dir}"], rel)
    if (
        role
        and decision_files.is_exploration(cfg, rel)
        and decision_files.changes_decisions(rel, old_text, new_text, ("outcome",), review_dismissals.OUTCOME_KEY)
    ):
        return "deny", (
            f"{rel}: this edit adds or changes an exploration's outcome, which only a person records. Write the evidence and "
            "the rest, and leave the outcome to the person who decides"
        )
    if role and review_dismissals.changes_dismissals(rel, old_text, new_text):
        return "deny", f"{rel}: {review_dismissals.DISMISSAL_DENY}"
    if role and decision_files.initiative_decision(rel, old_text, new_text):
        return "deny", (
            f"{rel}: this edit adds or changes an Initiative's go_no_go, which only a person records. Leave it to the person who decides, and write the rest"
        )
    if role and "{proposals_dir}" in writes and globs.match_any(fill["{proposals_dir}"], rel):
        # A proposal comes before any Spec: nothing ships from it, and humans decide it at go/no-go and sign-off.
        return decision_files.proposal_edit(role, rel, old_text, new_text)
    if role and "{explorations}" in writes and globs.match_any(fill["{explorations}"], rel):
        # An exploration often comes before the Spec it informs; its outcome stays a person's (checked above).
        return "allow", f"an exploration, inside the {role} role's area: a person records its outcome"
    if role and globs.match_any([globs.under(cfg.docs_dir, "feedback/**")], rel):
        # The feedback log belongs to no Spec: one agent writes it, and a person confirms each entry.
        if role == decision_files.FEEDBACK_WRITER:
            return "allow", "the feedback log, which belongs to no Spec: write each entry with its source for a person to confirm"
        return "deny", (
            f"the feedback log is the {decision_files.FEEDBACK_WRITER}'s: draft the entry, with its source, in your handoff note for the {decision_files.FEEDBACK_WRITER}, "
            "and a person confirms it"
        )
    if role and in_scope and not specs and not own_spec:
        # The fast and emergency lanes have no Spec: the scope lives in the Change Request block, which the gate
        # checks. Keep the role's own paths and leave the lane to the gate rather than stop to ask.
        paths = [w for w in writes if not w.startswith("{")]
        if paths and "{scope}" not in writes and not globs.match_any(paths, rel):
            return "deny", role_areas.outside_area(role, rel, fill)
        if protected:
            return frozen_files.protected_deny(rel, protected, "there is no active Spec")
        return "allow", (
            f"no active Spec: {rel} is fine only on the fast or emergency lane, and only inside the Change Request's scope. "
            "The lane is fast or emergency when `aidd gate --paths` shows minor or standard, or the author declared an emergency. "
            "On the spec lane, implementation waits for Spec approval"
        )
    unfrozen = bool(specs) and all(d.get("route") == "emergency" for _, d in specs)
    if (
        role
        and drafts
        and "{tests}" in writes
        and repo_paths.looks_like_test(rel)
        and not protected
        and not globs.match_any(fill["{tests}"] + fill["{scope}"], rel)
    ):
        # The test writer's own new file, before Spec approval: write it now, and list it while the Spec is still open.
        # Only a file new on this branch: a test the base already holds is another change's.
        if frozen_files.new_on_branch(root, rel):
            return "allow", frozen_files.unlisted_test(rel, ", ".join(drafts))
        return "deny", frozen_files.draft_hint(rel, ", ".join(drafts))
    if role:
        if not role_areas.role_allows(role, rel, fill, unfrozen)[0]:
            return "deny", role_areas.outside_area(role, rel, fill, unfrozen, lambda r: role_areas.placeholder_fill(cfg, specs, r, drafts=set(drafts)))
        if own_spec:
            return "allow", f"a Spec, inside the {role} role's area"
        # A Specify role's own folders (`docs/adr/**`); an implementation role's files go in a Task's scope instead.
        literal = [] if in_scope else [w for w in writes if not w.startswith("{")]
        if not protected and (paperwork := frozen_files.unlinked_paperwork(root, specs, role_areas.safe_draft_ids(cfg, specs, set(drafts)), rel, literal)):
            return "allow", paperwork
        if not specs:
            return "deny", (
                f"no active Spec, so {rel} has no approved scope. Start Specify with `aidd new spec`, or name the branch "
                "`spec/<ID>` (or set AIDD_SPEC=specs/<ID>.md) when it carries several Specs"
            )
    if rel in fill["{spec}"] and not in_scope:
        if drafts:
            return "allow", (
                "the active Spec, before Spec approval: finish its scope, tests.files, and tests. Then `aidd validate` it, and "
                "ask for Spec approval (`aidd hash --line` prints the line)"
            )
        return "allow", "the active Spec"
    if waits := _waits_for_approval(cfg, specs, set(drafts), role, rel):
        return "deny", waits
    if globs.match_any(fill["{tests:with}"], rel) and not globs.match_any(fill["{tests:first}"], rel):
        return "allow", f"{rel}: a test written with the code (`tests.mode: with`), never frozen: Merge approval reviews it with the code"
    if globs.match_any(fill["{tests}"], rel):
        return frozen_files.frozen_file(specs, rel, role, "test", unfrozen, held)
    if globs.match_any(fill["{design}"], rel):
        return frozen_files.frozen_file(specs, rel, role, "design", unfrozen, held)
    if globs.match_any(fill["{docs}"], rel):
        return frozen_files.frozen_file(specs, rel, role, "doc", unfrozen, held)
    if not protected and globs.match_any([p for _, d in specs for p in workitems.threat_models(d, cfg.docs_dir)], rel):
        return "allow", (
            f"{rel}: the living threat model of a component an active Spec links: keep it in step with the threat-model delta "
            "in the Spec's Design. It is never frozen, and Merge approval reviews it with the code"
        )
    if globs.match_any(fill["{scope}"] + cfg.get("scope_exempt_paths", default=[]), rel):
        if protected:
            return "allow", f"inside the approved scope; {rel} is a protected path ({protected}), so the gate makes the change major with a specialist approval"
        return "allow", "inside the scope"
    ids = ", ".join(str(d.get("id")) for _, d in specs)
    if protected:
        return frozen_files.protected_deny(rel, protected, f"it is outside the scope of {ids}")
    if role and not in_scope:
        return "deny", (
            f"{rel} is outside the scope of {ids}. Next: add a Task whose scope covers the file to the Spec, and write the file in "
            "Implement, after the person types `approve <ID>`. Editing the Spec after Spec approval voids that approval."
        )
    if drafts and len(drafts) == len(specs):
        return "deny", frozen_files.draft_hint(rel, ids)
    return "deny", (
        f"{rel} is outside the scope of {ids} ({', '.join(fill['{scope}']) or 'none'}). "
        "Next: widen a Task's scope in the Spec, then ask the person to type `approve <ID>` again. Or leave this file alone."
    )


def _waits_for_approval(cfg: config.Config, specs: list[tuple[str, dict]], drafts: set[str], role: str | None, rel: str) -> str | None:
    """Why `rel` waits for Spec approval, or None: it is implementation (a Task's scope, or a test written with the code)
    of a Spec still in draft, on a route where the profile asks for Spec approval, and of no Spec whose approval holds.
    Implementation starts once the person agrees to the contract; before that, the roles write the Spec, its tests,
    its design files, and its documents, and a spike goes in an exploration."""
    routes = set(cfg.gates.get("spec_approval_routes") or [])
    waiting = [(r, d) for r, d in specs if str(d.get("id")) in drafts and d.get("route") in routes]
    exempt = list(cfg.get("scope_exempt_paths", default=[]))
    for _, d in waiting:  # its documents and design files are the Spec's own paperwork, written before approval
        exempt += [p for p in _paperwork(d) if _in_paper_folder(cfg, p)]
    if not waiting or globs.match_any(exempt, rel):
        return None
    closed = role_areas.placeholder_fill(cfg, waiting, role)
    if not globs.match_any(closed["{scope}"] + closed["{tests:with}"], rel):
        return None
    if globs.match_any(closed["{tests:first}"], rel) and repo_paths.looks_like_test(rel):
        return None  # a test the Spec lists, written first, inside a scope that covers the tests folder too
    others = [s for s in specs if s not in waiting]
    if others:
        opened = role_areas.placeholder_fill(cfg, others, role)
        if globs.match_any(opened["{scope}"] + opened["{tests:with}"], rel):
            return None
    ids = ", ".join(str(d.get("id")) for _, d in waiting)
    return (
        f"{rel} is in the scope of {ids}, which waits for Spec approval: the code starts once the person agrees to the "
        "contract. Next: finish the Spec, its tests, and its documents, `aidd validate` it, and ask for Spec approval (the "
        "person types `approve <ID>`, or their standing approval records it). A spike goes in an exploration "
        "(`aidd new exploration`)"
    )


def _paperwork(d: dict) -> list[str]:
    """The paths a Spec lists as its documents and design files."""
    return workitems.design_paths(d) + [str(e["path"]) for e in d.get("docs") or [] if isinstance(e, dict) and e.get("path")]


def _in_paper_folder(cfg: config.Config, pattern: str) -> bool:
    """Whether a path the Spec lists as paperwork sits in the Specs folder or the docs folder. The agent writes the
    Spec, so a listing never makes product code paperwork: `docs: [{path: src/app.py}]` still waits for approval."""
    parts = pattern.replace("\\", "/").split("/")
    return ".." not in parts and any(pattern.startswith(f"{folder.rstrip('/')}/") for folder in (cfg.specs_dir, cfg.docs_dir) if folder)


HELPER_DENY = (
    'a subagent that is not an aidd-team role may only read (the loop contract\'s helper rule, "Use AI as a delivery team does"). Spawn the helper as your own '
    "`aidd-team:<role>` type to write, or hand the edit back to the role or the author"
)


def _edit_texts(root: str, rel: str, event: dict) -> tuple[str | None, str | None]:
    """(before, after) of the file an Edit, MultiEdit, or Write event changes; (None, None) when the event does not say."""
    tool, ti = event.get("tool_name"), event.get("tool_input") or {}
    if tool not in ("Edit", "MultiEdit", "Write"):
        return None, None
    path = Path(root) / rel
    try:
        old = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    except OSError:
        old = ""
    if tool == "Write":
        return old, str(ti.get("content") or "")
    edits = ti.get("edits") if tool == "MultiEdit" else [ti]
    new = old
    for e in edits or []:
        if not isinstance(e, dict):
            continue
        a, b = str(e.get("old_string") or ""), str(e.get("new_string") or "")
        new = new.replace(a, b) if e.get("replace_all") else (new.replace(a, b, 1) if a else b + new)
    return old, new


def check_agent_edit(root: str, rel: str, event: dict) -> verdicts.Verdict:
    """(decision, reason) for an edit by whoever `event` says is editing: a role, a helper subagent, or the session."""
    old, new = _edit_texts(root, rel, event)
    cfg = repo_config.load_config(root) if repo_config.is_adopted(root) else None
    if cfg is not None and not workitems.edits_held(cfg, root):
        # Free edits (an explore branch, or the loop switched off in the config): no Spec, scope, or role area, but an
        # agent still never loosens who must approve. The guard's commands (no approve, merge, ship, or rewrite of
        # main; held commands) stay on.
        if loosened := decision_files.config_loosening(rel, old, new):
            return "deny", f"{rel}: {decision_files.CONFIG_DENY.format(what=loosened)}"
        if rel.casefold() in GUARD_WIRING and config.component_on(cfg.raw, "loop"):
            return "deny", WIRING_DENY.format(rel=rel)
        return "allow", FREE_EDITS
    if role_areas.is_helper(event) and repo_config.is_adopted(root):
        return "deny", f"{rel}: {HELPER_DENY}"
    if new is None and event.get("agent_type") and repo_config.is_adopted(root) and (holds_decision := decision_files.decision_file(root, rel)):
        # A shell write, a git checkout, an MCP tool, or a tool that gives no new text: the decision rules cannot read
        # it, so it is denied.
        if holds_decision == "dismissal":
            return "deny", f"{rel}: {review_dismissals.DISMISSAL_DENY}; {decision_files.UNREADABLE_DECISION}"
        return "deny", f"{rel}: this file holds {holds_decision}, which only a person records; {decision_files.UNREADABLE_DECISION}"
    return check_edit(root, rel, role_areas.role_of(event), old, new)
