"""`aidd metrics --roles`: one row per aidd-team role, from what the records prove, never from what a role says of itself.

The sources are the gate events (CI's and the local ones), the Specs (each Task's `assignee: agent:<role>` and
`retry_count`, the Spec's `revisions` and `outcome`), the guard's log, the trunk's revert commits, and a role eval
record file (`aidd eval roles --record`). Never the autopilot journal or a handoff note: a role writes those itself.

A Spec-level measure counts in full for each role that had a Task in the Spec, as `--autonomy` credits a change to each
agent that assisted it. A Task-level measure, a Task out of retries, counts for its assignee alone.

Display only: no row sets an exit code, decides a gate, or changes a role. Never put a role's number into its prompt or
its agent file, because a measure that becomes a target stops measuring (Goodhart's law). A person reads the rows at a
retrospective. Under ROLE_MIN_CHANGES changes, a row says it is too few to judge.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from pathlib import Path

from aidd.kernel import git, resources
from aidd.kernel.text import na
from aidd.tracking.metrics import METRICS_SCHEMA_VERSION, _by_change, _first_pass, gate_events, guard_denials

# A row with fewer changes than this says "too few to judge": its shares are noise.
ROLE_MIN_CHANGES = 10
# The line `git revert` writes into its commit message.
REVERTS = re.compile(r"^This reverts commit ([0-9a-f]{40})\b", re.M)
AGENT_PREFIX = "agent:"


def role_names() -> list[str]:
    """Every aidd-team role, in schemas/roles.json order."""
    return list(resources.load_json("roles.json")["roles"])


def _assignee_role(task: object, names: set[str]) -> str | None:
    who = str(task.get("assignee") or "") if isinstance(task, dict) else ""
    role = who[len(AGENT_PREFIX) :] if who.startswith(AGENT_PREFIX) else ""
    return role if role in names else None


def spec_roles(specs_dir: Path, root: Path | None = None) -> list[dict]:
    """One entry per Spec under `specs_dir`: its id, its path from `root`, the roles its Tasks name, its Tasks out of
    retries by role, its revisions, and whether its outcome failed. A file that is not a readable Spec is skipped."""
    from aidd import workitems
    from aidd.kernel import documents

    known, out = set(role_names()), []
    for path in sorted(specs_dir.rglob("*.md")) if specs_dir.is_dir() else []:
        try:
            data, _ = documents.split_front_matter(path.read_text(encoding="utf-8"), str(path))
        except (documents.DocumentError, OSError, UnicodeDecodeError):
            continue
        if data.get("kind") != "spec" or not data.get("id"):
            continue
        tasks = {str(t.get("id")): _assignee_role(t, known) for t in data.get("tasks") or [] if isinstance(t, dict)}
        try:
            rel = path.resolve().relative_to((root or Path(".")).resolve()).as_posix()
        except ValueError:
            rel = path.as_posix()
        out.append(
            {
                "id": str(data["id"]),
                "path": rel,
                "roles": {r for r in tasks.values() if r},
                "out_of_retries": Counter(r for t in workitems.retries_used(data) if (r := tasks.get(t))),
                "revisions": len(data.get("revisions") or []),
                "rolled_back": workitems.spec_status(data) == "rolled_back",  # the recorded outcome, as `aidd list` derives it
            }
        )
    return out


def trunk_reverts(root: str, base: str, since: str | None = None) -> list[dict]:
    """The revert commits on `base`: each one's sha, the commit it reverts, that commit's parents, and the paths it
    changed against its first parent. A reverted commit git cannot find is kept with no parents and no paths."""
    args = [base, "--grep=^This reverts commit ", *([f"--since={since}"] if since else [])]
    shas = [r[0] for r in git.log_fields(args, ["%H"], root)]
    out = []
    for sha, message in git.messages(shas, root).items():
        for reverted in dict.fromkeys(REVERTS.findall(message)):
            parents = git.run(["rev-list", "--parents", "-n", "1", f"{reverted}^{{commit}}", "--"], root, check=False).split()[1:]
            paths = git.run(["diff", "--name-only", "-z", f"{reverted}^1", reverted], root, check=False).split("\0") if parents else []
            out.append({"sha": sha, "reverts": reverted, "parents": parents, "paths": [p for p in paths if p]})
    return out


def _change_spec(events: list[dict]) -> str | None:
    """The Spec a change's events name, by id: the last `spec_id`, else the stem of the last `spec` path."""
    for e in reversed(events):
        if e.get("spec_id"):
            return str(e["spec_id"])
        if e.get("spec"):
            return Path(str(e["spec"])).stem
    return None


def _reverted_specs(reverts: list[dict], by_change: dict[str, list[dict]], specs: list[dict]) -> tuple[Counter, int]:
    """How often each Spec was reverted, and how many reverts joined no Spec. A revert joins the Spec of a change whose
    head is the reverted commit or one of its parents (a merge), else each Spec file the reverted commit changed."""
    by_head = {e["head_sha"]: spec for evs in by_change.values() if (spec := _change_spec(evs)) for e in evs if e.get("head_sha")}
    by_path = {s["path"]: s["id"] for s in specs}
    counts: Counter = Counter()
    unjoined = 0
    for r in reverts:
        hit = {by_head[h] for h in [r["reverts"], *r["parents"]] if h in by_head} or {by_path[p] for p in r["paths"] if p in by_path}
        counts.update(hit)
        unjoined += not hit
    return counts, unjoined


def role_evals(runs: list[dict], fresh: list[bool]) -> dict[str, dict]:
    """Each role's latest fresh role eval: the mean pass@1 of its scenarios in the newest `roles` run whose material is
    still the current one, and the lift over the control run when it ran. A stale or unknown run never counts."""
    out: dict[str, dict] = {}
    for run, ok in sorted(zip(runs, fresh, strict=True), key=lambda p: str(p[0].get("date"))):
        if not ok or run.get("suite") != "roles":
            continue
        by_role: dict[str, list[dict]] = {}
        for sc in run.get("scenarios") or []:
            if isinstance(sc, dict) and sc.get("role") and isinstance(sc.get("pass_at_1"), int | float):
                by_role.setdefault(str(sc["role"]), []).append(sc)
        for role, scs in by_role.items():
            lifts = [sc["pass_at_1"] - sc["control_pass_at_1"] for sc in scs if isinstance(sc.get("control_pass_at_1"), int | float)]
            out[role] = {
                "pass_at_1": round(statistics.mean(sc["pass_at_1"] for sc in scs), 3),
                "lift": round(statistics.mean(lifts), 3) if lifts else None,
                "date": str(run.get("date")),
                "model": run.get("model"),
                "scenarios": len(scs),
            }
    return out


def _failing_heads(events: list[dict]) -> int:
    """The heads of one change whose tests failed in some gate event."""
    return len({e.get("head_sha") for e in events if "tests" in (e.get("failed_rules") or [])})


def _role_row(role: str, changes: list[list[dict]], specs: list[dict], reverted: Counter, extra: dict) -> dict:
    passed = [fp for fp in (_first_pass(evs) for evs in changes) if fp is not None]
    mine = [s for s in specs if role in s["roles"]]
    return {
        "role": role,
        "changes": len(changes),
        "specs": len(mine),
        "first_pass_share": round(sum(passed) / len(passed), 3) if passed else None,
        "failing_heads_per_change": round(sum(_failing_heads(evs) for evs in changes) / len(changes), 2) if changes else None,
        "tasks_out_of_retries": sum(s["out_of_retries"][role] for s in specs),
        "revisions": sum(s["revisions"] for s in mine),
        "rolled_back": sum(s["rolled_back"] for s in mine),
        "reverts": sum(reverted[s["id"]] for s in mine),
        **extra,
        "too_few_to_judge": len(changes) < ROLE_MIN_CHANGES,
    }


def role_measures(events: list[dict], specs: list[dict], *, guard: list[dict], reverts: list[dict], evals: dict[str, dict]) -> dict:
    """The `--roles` view: one row per role in schemas/roles.json order. `events` are event lines (only the gate decisions
    count), `specs` come from `spec_roles`, `guard` is the guard log's lines, `reverts` come from `trunk_reverts`, and
    `evals` from `role_evals`."""
    by_change = _by_change(gate_events(events))
    roles_of = {s["id"]: s["roles"] for s in specs}
    reverted, unjoined = _reverted_specs(reverts, by_change, specs)
    denials = guard_denials(guard)["by_role"]  # `session`, a denial with no role, is no row
    rows = []
    for role in role_names():
        changes = [evs for evs in by_change.values() if role in roles_of.get(_change_spec(evs) or "", set())]
        rows.append(_role_row(role, changes, specs, reverted, {"guard_denials": denials.get(role, 0), "eval": evals.get(role)}))
    return {
        "schema_version": METRICS_SCHEMA_VERSION,
        "min_changes": ROLE_MIN_CHANGES,
        "rows": rows,
        "reverts": len(reverts),
        "unjoined_reverts": unjoined,
        "display_only": True,
    }


def _eval_cell(e: dict | None) -> str:
    if not e:
        return "no eval record"
    lift = "" if e["lift"] is None else f", lift {e['lift'] * 100:+.1f} pts"
    return f"{e['pass_at_1']:.0%}{lift}"


def roles_markdown(out: dict) -> str:
    head = (
        "| Role | n | First-pass share | Failing heads per change | Tasks out of retries | Revisions | Rolled back | Reverts | Guard denials | Eval pass@1 | |\n"
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |\n"
    )
    body = "".join(
        f"| {r['role']} | {r['changes']} | {na(r['first_pass_share'])} | {na(r['failing_heads_per_change'])} | {r['tasks_out_of_retries']} | "
        f"{r['revisions']} | {r['rolled_back']} | {r['reverts']} | {r['guard_denials']} | {_eval_cell(r['eval'])} | "
        f"{'too few to judge' if r['too_few_to_judge'] else ''} |\n"
        for r in out["rows"]
    )
    notes = [
        "",
        f"n is the changes whose Spec has a Task for the role; under {out['min_changes']}, a row is too few to judge.",
        f"Trunk reverts: {out['reverts']}, and {out['unjoined_reverts']} joined no Spec.",
        "Display only: never put a role's number into its prompt, because a measure that becomes a target stops measuring.",
    ]
    return head + body + "\n".join(notes) + "\n"
