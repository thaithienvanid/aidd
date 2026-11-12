"""The base commit's view of what decides an `aidd test` run.

The head belongs to the change's author, so a head's value never decides what must run or what is excused when the base
holds that value. Each value is read from the base commit when the base has it, and the head's value applies only to what
is new in the head:

- the config's `specs_dir` and `docs_dir`, and its `tests` with their `smoke` markers;
- a Spec the base holds as approved or later: its status, route, test commands, frozen files, and Task scopes.

Where the head changes such a value, the run decides by the base's and runs the head's too, then says so in a note. A team
that really moves `specs_dir`, or revises an approved Spec, sees that note and a person decides, as `spec.revise` asks.
"""

from __future__ import annotations

from dataclasses import dataclass

from aidd import config, workitems
from aidd.kernel import documents, git

_ORDER = {status: i for i, status in enumerate(workitems.SPEC_STATUSES)}
# The step when a base command the head changed or removed fails on the head. It needs no one's bypass: the author splits the change.
KEEP_THEN_REMOVE = (
    "A base command must still pass on the head. If one fails, keep the old command and its test file working in this change, "
    "adding any new command beside it, and remove them in a later change"
)


def load_config(repo: str, base_sha: str | None) -> tuple[config.Config | None, list[str]]:
    """The base commit's config, or None when the base has none (a first adoption) or it does not load, and a note when it
    does not load. A run that gates a merge stops on that note: the base decides, and a base that cannot be read decides nothing."""
    if not base_sha:
        return None, []
    text = git.show(base_sha, config.CONFIG_PATH, repo)
    if text is None:
        return None, []

    def read(path: str) -> str | None:
        parent = git.show(base_sha, path, repo)
        return None if parent is None else config.in_todays_shape(parent)

    try:  # a branch forked before an upgrade has the old names on its base, and they still decide the run
        return config.load_text(config.in_todays_shape(text), read=read, root_preset=config.org_preset_text(), skip_unread=True), []
    except (config.ConfigError, documents.DocumentError) as exc:
        note = (
            f"the base commit's {config.CONFIG_PATH} does not load ({documents.one_line(str(exc), 200)}). The base decides what a run holds the "
            "change to, so a run that gates a merge (--require-green) stops on it, and any other run reads the head's values. Ask whoever owns "
            "the base branch to fix that file, update this branch from it, then run `aidd test` again. If this change is that fix, a person "
            "merges it past the required check"
        )
        return None, [note]


def spec_dirs(head_dir: str, base: config.Config | None) -> list[str]:
    """The folders that hold Specs: the base's first, then the head's when it moves them, so a Spec is found where either says."""
    return list(dict.fromkeys([*([base.specs_dir] if base else []), head_dir]))


def docs_dir(head: config.Config, base: config.Config | None) -> str:
    return (base or head).docs_dir


def config_notes(head: config.Config, base: config.Config | None) -> list[str]:
    """One note for each folder setting the head changes from the base's."""
    if base is None:
        return []
    out = []
    if head.specs_dir != base.specs_dir:
        out.append(f"the head moves `specs_dir` from {base.specs_dir} to {head.specs_dir}, so aidd read the Specs under both, and decided by the base's")
    if head.docs_dir != base.docs_dir:
        out.append(f"the head moves `docs_dir` from {base.docs_dir} to {head.docs_dir}, so aidd decided by the base's")
    return out


@dataclass(frozen=True)
class BaseTests:
    """The base config's `tests` as held, and the copies the run adds: each of those the head no longer holds as they were,
    named `base.<name>`."""

    held: list[dict]
    copies: list[dict]


def base_tests(base: config.Config | None, head_tests: list[dict]) -> tuple[BaseTests | None, list[str]]:
    """The base's tests beside the head's, and a note when the head changes or removes any. None with no base config. A
    change cannot turn its own check green by removing or weakening the tests it is checked by."""
    if base is None:
        return None, []
    held = base.tests
    lost = [c for c in held if c not in head_tests]
    copies = [{**c, "name": f"base.{c['name']}"} for c in lost]
    notes = [
        f"the head's {config.CONFIG_PATH} changes or removes `tests` the base commit holds ({', '.join(c['name'] for c in lost)}), "
        f"so aidd also ran the base's, as base.<name>. {KEEP_THEN_REMOVE}"
    ]
    return BaseTests(held, copies), (notes if lost else [])


def emergency_subset(config_tests: list[dict], base: BaseTests | None) -> list[dict]:
    """The commands an emergency change runs of the repository suite: the `smoke: true` ones, when the suite marks any. The
    base decides which are marked, and whether the suite has a smoke set at all; a command new in the head carries its own marker."""
    if base is None:
        marked = {c["name"] for c in config_tests if c.get("smoke")}
        return [c for c in config_tests if c["name"] in marked] if marked else config_tests
    marked = {c["name"] for c in base.held if c.get("smoke")}
    if not marked:
        return config_tests
    known = {c["name"] for c in base.held}
    return [c for c in config_tests if c["name"] in marked or (c.get("smoke") and c["name"] not in known)]


def spec_view(head: dict, base: dict | None) -> tuple[dict, list[str]]:
    """The Spec as a run decides by it. A new Spec, or one the base holds as a draft or ready, is the head's. One the base holds
    as approved or later keeps the base's status and route, its Task scopes and frozen files, and its test commands: the head's
    commands run too, and any base command the head changes or removes runs as `base.<name>`."""
    if base is None or workitems.spec_status(base) not in workitems.PAST_APPROVAL:
        return head, []
    htests, btests = head.get("tests") or {}, base.get("tests") or {}
    hcmds = [c for c in htests.get("commands") or [] if isinstance(c, dict)]
    lost = [c for c in btests.get("commands") or [] if isinstance(c, dict) and c not in hcmds]
    htasks = [t for t in head.get("tasks") or [] if isinstance(t, dict)]
    btasks = [t for t in base.get("tasks") or [] if isinstance(t, dict)]
    changes = []
    if _ORDER.get(workitems.spec_status(head), 0) < _ORDER[workitems.spec_status(base)]:
        changes.append("status (lowered)")
    if head.get("triage") != base.get("triage"):
        changes.append("triage")
    if head.get("route") != base.get("route"):
        changes.append("route")
    if lost:
        changes.append("test commands")
    if set(workitems.frozen_files(head)) != set(workitems.frozen_files(base)):
        changes.append("frozen files")
    if [t.get("scope") for t in htasks] != [t.get("scope") for t in btasks]:
        changes.append("Task scope")
    view = {
        **head,
        "status": workitems.spec_status(base),  # the status reads `status` and `triage`: both come from the base
        "tasks": htasks + [t for t in btasks if t not in htasks],
        "tests": {
            **htests,
            "files": list(dict.fromkeys([*htests.get("files", []), *btests.get("files", [])])),
            "commands": hcmds + [{**c, "name": f"base.{c['name']}"} for c in lost],
        },
    }
    view.pop("triage", None)  # the base's status already holds a declined triage, and the head's would read as `cancelled`
    view.pop("route", None)  # the base's route decides; a Spec the base gave no route gets none from the head
    if base.get("route") is not None:
        view["route"] = base["route"]
    notes = (
        [
            f"{head.get('id')}: the head changes the {', '.join(changes)} of a Spec the base holds approved, so aidd decided by the base's"
            f"{' and ran its changed commands as base.<name>. ' + KEEP_THEN_REMOVE if lost else ''}. "
            "A change to an approved Spec is `spec.revise`: the person who agreed to it approves the Spec again"
        ]
        if changes
        else []
    )
    return view, notes
