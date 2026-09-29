"""Evaluations.

examples: run every examples/<case>/ through the verifier and compare with expected.json.
routing: ask any agent CLI to route each scenario in evals/routing/*.toml and score it.
roles: send each aidd-team role a task with a seeded defect (evals/roles/*.toml) and score the answer.
standards: list the team's standards registry and the entries nobody has checked within a year.
tasks: send your own agent configuration real tasks (evals/tasks/*.toml), each in a scratch worktree, and grade it by commands that must pass.

The agent suites are measurements, not fixtures: `measure` runs a suite K times and reports each
scenario's pass@1 (the share of trials that passed) and pass^K (every trial passed); a control run
without the aidd material gives the baseline the material is measured against (the lift); and
`record` appends one JSON line per run, so scores are compared over time, not remembered.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import re
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from . import __version__, docs, gitutil, model, resources, rules, runner, util
from . import config as cfgmod
from .verify import verify

ANSWER = re.compile(r"\{[^{}]*\"route\"[^{}]*\}", re.S)
PROMPT = """You are routing one software change under aidd.
{reference}
Profile: {profile}

Situation:
{situation}

Decide the route. If the situation must stop before a route exists (low confidence, freeze without a production repair, missing owner), say stop.
Answer with one JSON object on the last line and nothing after it:
{{"route": "standard|minor|normal|major|emergency|stop", "reason": "<one sentence>"}}
"""


def load_example(case: Path) -> tuple[dict, dict]:
    ctx = json.loads((case / "context.json").read_text(encoding="utf-8"))
    expected = json.loads((case / "expected.json").read_text(encoding="utf-8"))
    cfg_file = ctx.pop("base_config_from", None)
    ctx["base_config"] = (case / cfg_file).read_text(encoding="utf-8") if cfg_file else None
    for repo_path, local in ctx.pop("head_files_from", {}).items():
        ctx["head_files"][repo_path] = (case / local).read_text(encoding="utf-8")
    spec_path = ctx.pop("spec_hash_of", None)
    if spec_path:
        h = model.spec_hash(ctx["head_files"][spec_path], ctx["head_tree"])
        for c in ctx["comments"]:
            c["body"] = c["body"].replace("{{spec_hash}}", h)
    for c in ctx["comments"]:
        c["body"] = c["body"].replace("{{head}}", ctx["head_sha"])
    for r in ctx["reviews"]:
        if r.get("commit_sha") == "{{head}}":
            r["commit_sha"] = ctx["head_sha"]
    if ctx.get("evidence") and ctx["evidence"].get("head_sha") == "{{head}}":
        ctx["evidence"]["head_sha"] = ctx["head_sha"]
    return ctx, expected


def _pointer(doc, path: str):
    """The parent container and last key of a JSON pointer (/a/b~1c)."""
    parts = [p.replace("~1", "/").replace("~0", "~") for p in path.lstrip("/").split("/")]
    node = doc
    for part in parts[:-1]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    last = parts[-1]
    return node, (int(last) if isinstance(node, list) and last.lstrip("-").isdigit() else last)


def apply_ops(ctx: dict, ops: list[dict]) -> dict:
    """Mutation operations, as data, so any reimplementation can replay them:
    set, remove, append (to a list), and replace_text (exactly one occurrence in a string)."""
    for op in ops:
        node, key = _pointer(ctx, op["path"])
        if op["op"] == "set":
            node[key] = op["value"]
        elif op["op"] == "remove":
            del node[key]
        elif op["op"] == "append":
            node[key].append(op["value"])
        elif op["op"] == "replace_text":
            n = node[key].count(op["old"])
            if n != 1:
                raise ValueError(f"replace_text: {op['old']!r} occurs {n} times at {op['path']}; it must occur exactly once")
            node[key] = node[key].replace(op["old"], op["new"], 1)
        else:
            raise ValueError(f"unknown op {op['op']!r}")
    return ctx


EXPECTED_KEYS = ("decision", "failed_rules", "pending_rules", "warn_rules", "findings")


def _compare(d, expected: dict) -> tuple[bool, dict, dict]:
    """Every key is compared: a missing key is a failed case, never a silently narrower one."""
    got = {
        "decision": d.decision,
        "failed_rules": d.rules_at("fail"),
        "pending_rules": d.rules_at("pending"),
        "warn_rules": d.rules_at("warn"),
        "findings": d.codes(),
    }
    want = {k: expected.get(k) for k in EXPECTED_KEYS}
    return all(got[k] == want[k] for k in EXPECTED_KEYS), got, want


def _cases(root: Path, sep: str):
    """(name, context, expected) for every case, then every mutation of it (examples/<case>/mutations/*.json), named
    `<case><sep><mutation>`."""
    for case in sorted(p for p in (root / "examples").iterdir() if (p / "context.json").is_file()):
        ctx, expected = load_example(case)
        yield case.name, ctx, expected
        for mfile in sorted((case / "mutations").glob("*.json")) if (case / "mutations").is_dir() else []:
            m = json.loads(mfile.read_text(encoding="utf-8"))
            yield f"{case.name}{sep}{mfile.stem}", apply_ops(copy.deepcopy(ctx), m["ops"]), m["expected"]


def run_examples(root: Path) -> list[dict]:
    results = []
    for name, ctx, expected in _cases(root, "/"):
        ok, got, want = _compare(verify(ctx), expected)
        results.append({"case": name, "ok": ok, "got": got, "want": want})
    return results


def materialize(root: Path, out: Path) -> int:
    """Write every case and mutation as `<name>/context.json` (resolved) and `<name>/expected.json`.

    A resolved context needs no loader: shared configs, Spec files, hashes, and mutations are all
    applied. Another implementation of the verifier runs these and compares its decision and codes.
    """
    n = 0
    for name, ctx, expected in _cases(root, "--"):
        d = out / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "context.json").write_text(json.dumps(ctx, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (d / "expected.json").write_text(json.dumps(expected, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        n += 1
    return n


def load_scenarios(directory: Path) -> list[dict]:
    out: list[dict] = []
    for p in sorted(directory.glob("*.toml")):
        data = model.parse_toml(p.read_text(encoding="utf-8"), str(p))
        if "scenario" in data:
            out += [dict(s, _file=p.name) for s in data["scenario"]]
        else:
            out.append(dict(data, _file=p.name))
    return out


def parse_answer(text: str) -> dict | None:
    for m in reversed(list(ANSWER.finditer(text))):
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "route" in data:
            return data
    return None


def reference_text() -> str:
    """What an agent with the skill loaded sees when it assesses: SKILL.md plus the routing reference."""
    skill = resources.data_dir("skill")
    return "\n\n".join((skill / rel).read_text(encoding="utf-8") for rel in ("SKILL.md", "references/routes.md"))


# The config a routing scenario runs under: the profile it names, nothing else.
_SCENARIO_CONFIG = 'aidd_version = "1.0.0"\nprofile = "{profile}"\n[owners]\napprovers = ["@x"]\n'


def gate_route(sc: dict) -> str | None:
    """The minimum route the gate's own rules compute for a scenario's `paths`, `type`, and `lines` (the library function
    behind `aidd next` and `aidd new spec --paths`); None for a scenario that names no paths."""
    if "paths" not in sc:
        return None
    cfg = cfgmod.load_text(_SCENARIO_CONFIG.format(profile=sc.get("profile", "team")))
    return rules.assess_paths(cfg, sc["paths"], ctype=sc.get("type", "feat"), changed_lines=sc.get("lines", 0)).required_route


def _ask(cmd: str, prompt: str, timeout: int, cwd: Path | None = None) -> str:
    """The agent's answer on stdout; OSError or TimeoutExpired propagate."""
    return subprocess.run(
        util.split_command(cmd), input=prompt, cwd=cwd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace"
    ).stdout


def run_routing(directory: Path, cmd: str, *, embed: bool = True, material: bool = True, timeout: int = 600) -> list[dict]:
    """One trial of every scenario. `material=False` is the control: no reference and no mention of the skill."""
    if not material:
        reference = ""
    else:
        reference = f"\nReference:\n{reference_text()}\n" if embed else "\nUse the aidd skill.\n"
    results = []
    for sc in load_scenarios(directory):
        prompt = PROMPT.format(reference=reference, profile=sc.get("profile", "team"), situation=sc["situation"].strip())
        try:
            answer = parse_answer(_ask(cmd, prompt, timeout))
        except (OSError, subprocess.TimeoutExpired) as exc:
            answer = None
            print(f"{sc['id']}: {exc}")
        want, got = sc["expected"]["route"], (answer or {}).get("route")
        # `gate`: what the rules compute from the paths alone, when the scenario names them.
        row = {"id": sc["id"], "want": want, "got": got, "ok": got == want, "reason": (answer or {}).get("reason", ""), "judgment": bool(sc.get("judgment"))}
        results.append(row | {"gate": gate_route(sc)})
    return results


def standards() -> list[dict]:
    """Every dated entry the team applies: standards by role and by domain pack, extensions, and practice skills, with `where` naming its owner."""
    data = resources.roles()
    out = []
    for key in data["order"]:
        out += [dict(s, where=f"role {key}") for s in data["roles"][key]["standards"]]
        out += [dict(s, where=f"extension {key}") for s in data["roles"][key].get("extends", [])]
    for d in data["domains"]:
        out += [dict(s, where=f"domain {d['slug']}") for s in d["standards"]]
    for name in docs.practice_names():
        front = docs.practice_front(name)
        out.append({"name": f"practice skill aidd-team:{name}", "checked": front["checked"], "where": f"practice {name}"})
    return out


def dated(s: dict) -> str:
    """An entry's date: `checked` against a source, or `reviewed` for a practice with no source to check."""
    return str(s.get("checked") or s.get("reviewed") or "")


def bulk_checked_dates(threshold: int = 20) -> list[tuple[str, int]]:
    """`checked` dates shared by more than `threshold` entries, as (date, count), newest first.

    One date across ISO 42001, the EU AI Act, MITRE ATLAS, and 250 others is a bulk edit, not that
    many independent confirmations. The currency control is only as good as the dates are honest,
    so `eval standards` says when they cluster.
    """
    counts: dict[str, int] = {}
    seen: set[str] = set()
    for s in standards():
        # One entry referenced by five roles is one check, not five; an entry that records what was
        # read and where (`evidence`) is an individual confirmation, whatever its date.
        key = str(s.get("id") or s.get("name"))
        if key in seen or s.get("evidence"):
            continue
        seen.add(key)
        d = dated(s)
        if d:
            counts[d] = counts.get(d, 0) + 1
    return sorted(((d, n) for d, n in counts.items() if n > threshold), key=lambda x: x[0], reverse=True)


def unsourced_standards() -> list[dict]:
    """Entries in the registry's standards table that name an edition but no source to check it against.

    Read from the raw table: the resolved view folds a practice's `notes` into its displayed edition.
    """
    table = resources.load_json("roles.json").get("standards", {})
    return [dict(e, id=k) for k, e in table.items() if e.get("edition") and not e.get("source")]


def unevidenced_standards() -> list[dict]:
    """Entries in the standards table dated `checked` without the `source` and `evidence` that make the date a check.

    A practice with nothing to check against carries `reviewed` instead, so a `checked` date always names what was read.
    """
    table = resources.load_json("roles.json").get("standards", {})
    return [dict(e, id=k) for k, e in table.items() if e.get("checked") and not (e.get("source") and e.get("evidence"))]


def unpinned_extensions() -> list[dict]:
    """Tools, plugins, and skills with no `license` or no `pin`: third-party code a role would run with its permissions,
    unreviewable until a team knows what it may do with it and which exact release it installs. Each carries `missing`."""
    out = []
    for key in resources.roles()["order"]:
        for x in resources.roles()["roles"][key].get("extends", []):
            missing = [f for f in ("license", "pin") if not str(x.get(f, "")).strip()]
            if x["kind"] in ("tool", "plugin", "skill") and missing:
                out.append(dict(x, where=f"extension {key}", missing=missing))
    return out


def stale_standards(today: dt.date, max_days: int = 365) -> list[dict]:
    """Entries whose `checked` date is older than `max_days`, each with `age_days`."""
    stale = []
    for s in standards():
        try:
            age = (today - dt.date.fromisoformat(dated(s))).days
            if age < 0 or age > max_days:
                stale.append(dict(s, age_days=age))
        except (ValueError, TypeError):
            stale.append(dict(s, age_days=max_days + 1))
    return sorted(stale, key=lambda s: -s["age_days"])


_ROLE_TASK = """Task:
{prompt}

Material:
{fixture}

Answer in plain text. End with your four-line handoff note: Done, Next, Needs, Stopped at.
"""
ROLE_PROMPT = (
    "You are the {role} of an aidd delivery team. Your agent file follows: apply its playbook, its loop contract, and its standards.\n\n{playbook}\n\n"
    + _ROLE_TASK
)
# The control: the same task and material with no playbook, so the lift is what the agent file adds.
CONTROL_ROLE_PROMPT = "You are the {role} of a software delivery team.\n\n" + _ROLE_TASK


def role_playbook(role: str) -> str:
    """The role's agent file without its front matter."""
    text = (resources.data_dir("team") / "agents" / f"{role}.md").read_text(encoding="utf-8")
    return text.split("---", 2)[2].strip() if text.startswith("---") else text


def score_role(text: str, expected: dict) -> tuple[bool, list[str]]:
    """Case-insensitive substring scoring: `require` (all), `require_any` (one per group), `forbid` (none)."""
    low = text.lower()
    misses = [f"missing {x!r}" for x in expected.get("require", []) if x.lower() not in low]
    misses += [f"none of {group!r}" for group in expected.get("require_any", []) if not any(x.lower() in low for x in group)]
    misses += [f"forbidden {x!r}" for x in expected.get("forbid", []) if x.lower() in low]
    return not misses, misses


def run_roles(directory: Path, cmd: str, *, material: bool = True, timeout: int = 900) -> list[dict]:
    """One trial of every scenario. `material=False` is the control: the role's name without its playbook."""
    results = []
    for sc in load_scenarios(directory):
        fields = {"role": sc["role"], "prompt": sc["prompt"].strip(), "fixture": sc["fixture"].strip()}
        prompt = ROLE_PROMPT.format(playbook=role_playbook(sc["role"]), **fields) if material else CONTROL_ROLE_PROMPT.format(**fields)
        try:
            answer = _ask(cmd, prompt, timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            answer = ""
            print(f"{sc['id']}: {exc}")
        ok, misses = score_role(own_words(answer, prompt), sc["expected"])
        results.append({"id": sc["id"], "role": sc["role"], "ok": ok, "misses": misses})
    return results


TASK_KEYS = {"id", "prompt", "setup", "checks", "expected", "source", "timeout"}


def task_problems(task: dict) -> list[str]:
    """What is wrong with one task scenario: an id and a prompt, and something to grade (`checks`, `expected`, or both)."""
    tid = task.get("id", "?")
    problems = [f"{tid}: unknown key {k!r}" for k in sorted(set(task) - TASK_KEYS - {"_file"})]
    if not isinstance(task.get("id"), str) or not task["id"].strip():
        problems.append(f"{tid}: `id` is required")
    if not isinstance(task.get("prompt"), str) or not task["prompt"].strip():
        problems.append(f"{tid}: `prompt` is required")
    if not task.get("checks") and not task.get("expected"):
        problems.append(f"{tid}: nothing grades it; give `checks` (commands that must pass) or `expected` (what the answer must say)")
    commands = [c.get("run") for c in task.get("checks", [])] + ([task["setup"]] if "setup" in task else [])
    for cmd in commands:
        if not (isinstance(cmd, list) and cmd and all(isinstance(x, str) for x in cmd)):
            problems.append(f'{tid}: a command is an argv list such as ["npm", "test"], got {cmd!r}')
    if set(task.get("expected", {})) - {"require", "require_any", "forbid"}:
        problems.append(f"{tid}: `expected` takes require, require_any, and forbid")
    return problems


def _scratch_checkout(repo: Path, dest: Path) -> None:
    """A detached worktree of the repository at its current state: HEAD plus uncommitted changes to tracked files."""
    snapshot = gitutil.run(["stash", "create"], str(repo)).strip() or "HEAD"
    gitutil.run(["worktree", "add", "--detach", "--quiet", str(dest), snapshot], str(repo))


def run_tasks(directory: Path, cmd: str, *, repo: Path, timeout: int = 900) -> list[dict]:
    """Each task in a fresh worktree: run `setup`, send the agent the prompt there, then run every check.

    A task passes when every check exits 0 and the answer meets `expected`. The agent edits the scratch
    worktree, never the repository, and the worktree is removed afterwards. Checks run with the secrets
    stripped from their environment, as `aidd test` runs a Spec's commands.
    """
    results = []
    for task in load_scenarios(directory):
        problems = task_problems(task)
        if problems:
            results.append({"id": task.get("id", "?"), "ok": False, "misses": problems})
            continue
        limit = int(task.get("timeout", timeout))
        with tempfile.TemporaryDirectory(prefix="aidd-eval-") as tmp:
            work, logs = Path(tmp) / "work", Path(tmp) / "logs"
            misses: list[str] = []
            try:
                _scratch_checkout(repo, work)
            except gitutil.GitError as exc:
                results.append({"id": task["id"], "ok": False, "misses": [f"no scratch worktree: {exc}"]})
                continue
            try:
                if "setup" in task:
                    r = runner.execute(task["setup"], cwd=str(work), log=logs / "setup.log", timeout=limit)
                    if r["status"] != "passed":
                        misses.append(f"setup {r['status']}: {_tail(logs / 'setup.log')}")
                answer = ""
                if not misses:
                    try:
                        answer = _ask(cmd, task["prompt"].strip() + "\n", limit, cwd=work)
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        misses.append(f"agent: {exc}")
                    for i, check in enumerate(task.get("checks", [])):
                        log = logs / f"check-{i}.log"
                        r = runner.execute(check["run"], cwd=str(work), log=log, timeout=limit)
                        if r["status"] != "passed":
                            misses.append(f"check {check.get('name', ' '.join(check['run']))!r} {r['status']}: {_tail(log)}")
                    if task.get("expected"):
                        misses += score_role(own_words(answer, task["prompt"]), task["expected"])[1]
            finally:
                gitutil.run(["worktree", "remove", "--force", str(work)], str(repo), check=False)
        results.append({"id": task["id"], "ok": not misses, "misses": misses})
    return results


def _tail(log: Path, lines: int = 3) -> str:
    text = log.read_text(encoding="utf-8", errors="replace").strip() if log.is_file() else ""
    return " | ".join(text.splitlines()[-lines:]) or "no output"


def own_words(answer: str, prompt: str) -> str:
    """The answer without any line copied from the prompt, so an agent that echoes the playbook or the fixture scores nothing for it."""
    given = {line.strip() for line in prompt.splitlines() if line.strip()}
    return "\n".join(line for line in answer.splitlines() if line.strip() and line.strip() not in given)


def measure(run: Callable[[], list[dict]], repeat: int = 1) -> list[dict]:
    """Run a suite `repeat` times and fold each scenario's trials into one result.

    Each result keeps the detail of its last failing trial (or its last trial, when all passed) and adds
    `trials`, `passed`, `pass_at_1` (the share of trials that passed), and `pass_all` (all of them did,
    pass^K); `ok` is `pass_all`, so a single trial reads exactly as before. A routing result also lists
    every trial's answer in `answers`.
    """
    if repeat < 1:
        raise ValueError("--repeat must be at least 1")
    trials = [run() for _ in range(repeat)]
    out = []
    for i, first in enumerate(trials[0]):
        runs = [t[i] for t in trials]
        if any(r["id"] != first["id"] for r in runs):
            raise RuntimeError(f"the scenarios changed between trials at {first['id']!r}")
        passed = sum(bool(r["ok"]) for r in runs)
        shown = next((r for r in reversed(runs) if not r["ok"]), runs[-1])
        result = dict(shown, trials=repeat, passed=passed, pass_at_1=passed / repeat, pass_all=passed == repeat, ok=passed == repeat)
        if "got" in first:
            result["answers"] = [r.get("got") for r in runs]
        out.append(result)
    return out


def summary(results: list[dict]) -> dict:
    """The suite's mean pass@1 and the share of scenarios that passed every trial (pass^K)."""
    n = len(results) or 1
    return {"mean_pass_at_1": sum(r["pass_at_1"] for r in results) / n, "pass_k_share": sum(bool(r["pass_all"]) for r in results) / n}


def record_line(
    *,
    suite: str,
    cmd: str,
    model: str | None,
    repeat: int,
    results: list[dict],
    threshold: float,
    control: list[dict] | None = None,
    options: dict | None = None,
    now: dt.datetime | None = None,
) -> dict:
    """One run as a JSON-ready record: what ran, on what, and how each scenario did.

    `model` is whatever the operator passed with --model-label; aidd never infers it from the command.
    """
    stats = summary(results)
    control_stats = summary(control) if control is not None else None
    by_id = {r["id"]: r for r in control or []}
    scenarios = []
    for r in results:
        row = {k: r[k] for k in ("id", "trials", "passed", "pass_at_1", "pass_all")} | {k: r[k] for k in ("role", "judgment", "answers", "misses") if r.get(k)}
        if r["id"] in by_id:
            row["control_pass_at_1"] = by_id[r["id"]]["pass_at_1"]
        scenarios.append(row)
    when = (now or dt.datetime.now(dt.UTC)).astimezone(dt.UTC)
    return {
        "suite": suite,
        "date": when.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "aidd_version": __version__,
        "cmd": cmd,
        "model": model,
        "repeat": repeat,
        "options": options or {},
        "scenarios": scenarios,
        "mean_pass_at_1": stats["mean_pass_at_1"],
        "pass_k_share": stats["pass_k_share"],
        "threshold": threshold,
        "passed": stats["mean_pass_at_1"] >= threshold,
        "control": control_stats,
        "lift": None if control_stats is None else stats["mean_pass_at_1"] - control_stats["mean_pass_at_1"],
    }


def append_record(path: Path, line: dict) -> None:
    """Append one run to a JSON-lines file, creating it (and its directory) on first use."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n")


def load_records(paths: list[Path]) -> list[dict]:
    """Every recorded run in these JSON-lines files, oldest first; a line that is not a run is an error, not skipped."""
    runs = []
    for path in paths:
        for n, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not text.strip():
                continue
            try:
                run = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{n}: not JSON: {exc}") from None
            if not isinstance(run, dict) or not {"suite", "date", "mean_pass_at_1"} <= set(run):
                raise ValueError(f"{path}:{n}: not a recorded eval run (no suite, date, or mean_pass_at_1)")
            runs.append(run)
    return sorted(runs, key=lambda r: (str(r["date"]), str(r["suite"])))


def report_markdown(runs: list[dict]) -> str:
    """Recorded runs over time as a markdown table, one row per run."""

    def pct(x) -> str:
        return "" if x is None else f"{x:.1%}"

    rows = [
        "| Date | Suite | Model | aidd | K | Scenarios | Mean pass@1 | pass^K | Control pass@1 | Lift | Threshold |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in runs:
        control, lift = r.get("control") or {}, r.get("lift")
        cells = [r["date"], r["suite"], r.get("model") or "(not given)", r.get("aidd_version", ""), r.get("repeat", 1), len(r.get("scenarios", []))]
        cells += [pct(r["mean_pass_at_1"]), pct(r.get("pass_k_share")), pct(control.get("mean_pass_at_1"))]
        cells += ["" if lift is None else f"{lift * 100:+.1f} pts", pct(r.get("threshold"))]
        rows.append("| " + " | ".join(map(str, cells)) + " |")
    return "\n".join(rows)
