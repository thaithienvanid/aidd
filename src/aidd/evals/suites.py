"""The agent suites: routing, roles, and tasks. Each sends an agent CLI its scenarios and scores the answers; `measure` runs a suite K times for pass@1 and pass^K, and a control run without the aidd material gives the baseline the material lifts."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from aidd import config, gate
from aidd.kernel import documents, git, processes, resources

ANSWER = re.compile(r"\{[^{}]*\"route\"[^{}]*\}", re.S)
PROMPT = """You are routing one software change under aidd.
{reference}
Profile: {profile}

Situation:
{situation}

Decide the route the change needs, using the whole table: name major whenever the table says major, even where the reference says the gate would raise a normal change for you. If the situation must stop before a route exists (low confidence, freeze without a production repair, missing owner), say stop.
Answer with one JSON object on the last line and nothing after it:
{{"route": "standard|minor|normal|major|emergency|stop", "reason": "<one sentence>"}}
"""


def load_scenarios(directory: Path) -> list[dict]:
    out: list[dict] = []
    for p in sorted(directory.glob("*.yaml")):
        data = documents.parse_yaml(p.read_text(encoding="utf-8"), str(p))
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
    """What an agent with the skill loaded sees when it routes a change: SKILL.md plus the routing reference."""
    skill = resources.data_dir("skill")
    return "\n\n".join((skill / rel).read_text(encoding="utf-8") for rel in ("SKILL.md", "references/routes.md"))


# The config a routing scenario runs under: the profile it names, nothing else.
_SCENARIO_CONFIG = 'aidd_version: "1.0.0"\nprofile: {profile}\nowners:\n  approvers: ["@x"]\n'


def gate_route(sc: dict) -> str | None:
    """The minimum route the gate's own rules compute for a scenario's `paths`, `type`, `lines`, and `dependencies`
    (each `manifest:name`, a dependency the change adds; the library function behind `aidd gate --paths` and
    `aidd new spec --paths`); None for a scenario that names no paths."""
    if "paths" not in sc:
        return None
    cfg = config.load_text(_SCENARIO_CONFIG.format(profile=sc.get("profile", "team")))
    deps = [dict(zip(("file", "name"), d.split(":", 1), strict=True)) for d in sc.get("dependencies", [])]
    return gate.assess_paths(cfg, sc["paths"], ctype=sc.get("type", "feat"), changed_lines=sc.get("lines", 0), dependencies=deps).required_route


def _ask(cmd: str, prompt: str, timeout_seconds: int, cwd: Path | None = None) -> str:
    """The agent's answer on stdout; OSError or TimeoutExpired propagate."""
    return subprocess.run(
        processes.split_command(cmd), input=prompt, cwd=cwd, capture_output=True, text=True, timeout=timeout_seconds, encoding="utf-8", errors="replace"
    ).stdout


def routing_reference(*, embed: bool = True, material: bool = True) -> str:
    """The reference a routing prompt carries: the skill's text, a line naming the skill (`embed=False`), or nothing (the control)."""
    if not material:
        return ""
    return f"\nReference:\n{reference_text()}\n" if embed else "\nBefore you answer, load the aidd skill: its SKILL.md and references/routes.md.\n"


def routing_prompt(sc: dict, reference: str) -> str:
    return PROMPT.format(reference=reference, profile=sc.get("profile", "team"), situation=sc["situation"].strip())


def run_routing(directory: Path, cmd: str, *, embed: bool = True, material: bool = True, timeout_seconds: int = 600) -> list[dict]:
    """One trial of every scenario. `material=False` is the control: no reference and no mention of the skill."""
    reference = routing_reference(embed=embed, material=material)
    results = []
    for sc in load_scenarios(directory):
        prompt = routing_prompt(sc, reference)
        try:
            answer = parse_answer(_ask(cmd, prompt, timeout_seconds))
        except (OSError, subprocess.TimeoutExpired) as exc:
            answer = None
            print(f"{sc['id']}: {exc}")
        want, got = sc["expected"]["route"], (answer or {}).get("route")
        # `gate`: what the rules compute from the paths alone, when the scenario names them.
        row = {"id": sc["id"], "want": want, "got": got, "ok": got == want, "reason": (answer or {}).get("reason", ""), "judgment": bool(sc.get("judgment"))}
        results.append(row | {"gate": gate_route(sc)})
    return results


_ROLE_TASK = """Task:
{prompt}

Material:
{fixture}

Answer in plain text. End with your five-line handoff note: Done, Next, Needs, Stopped at, Spend.
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


def role_prompt(sc: dict, *, material: bool = True) -> str:
    """The prompt a role scenario sends: the role's agent file and the task, or the task alone (the control)."""
    fields = {"role": sc["role"], "prompt": sc["prompt"].strip(), "fixture": sc["fixture"].strip()}
    return ROLE_PROMPT.format(playbook=role_playbook(sc["role"]), **fields) if material else CONTROL_ROLE_PROMPT.format(**fields)


def run_roles(directory: Path, cmd: str, *, material: bool = True, timeout_seconds: int = 900) -> list[dict]:
    """One trial of every scenario. `material=False` is the control: the role's name without its playbook."""
    results = []
    for sc in load_scenarios(directory):
        prompt = role_prompt(sc, material=material)
        try:
            answer = _ask(cmd, prompt, timeout_seconds)
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


def task_prompt(task: dict) -> str:
    """What a task sends the agent: its own prompt, nothing added."""
    return task["prompt"].strip() + "\n"


def _scratch_checkout(repo: Path, dest: Path) -> None:
    """A detached worktree of the repository at its current state: HEAD plus uncommitted changes to tracked files."""
    snapshot = git.run(["stash", "create"], str(repo)).strip() or "HEAD"
    git.run(["worktree", "add", "--detach", "--quiet", str(dest), snapshot], str(repo))


def run_tasks(directory: Path, cmd: str, *, repo: Path, timeout_seconds: int = 900) -> list[dict]:
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
        limit = int(task.get("timeout", timeout_seconds))
        with tempfile.TemporaryDirectory(prefix="aidd-eval-") as tmp:
            work, logs = Path(tmp) / "work", Path(tmp) / "logs"
            misses: list[str] = []
            try:
                _scratch_checkout(repo, work)
            except git.GitError as exc:
                results.append({"id": task["id"], "ok": False, "misses": [f"no scratch worktree: {exc}"]})
                continue
            try:
                if "setup" in task:
                    r = gate.run_test_command(task["setup"], cwd=str(work), log=logs / "setup.log", timeout_seconds=limit)
                    if r["status"] != "passed":
                        misses.append(f"setup {r['status']}: {_tail(logs / 'setup.log')}")
                answer = ""
                if not misses:
                    try:
                        answer = _ask(cmd, task_prompt(task), limit, cwd=work)
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        misses.append(f"agent: {exc}")
                    for i, check in enumerate(task.get("checks", [])):
                        log = logs / f"check-{i}.log"
                        r = gate.run_test_command(check["run"], cwd=str(work), log=log, timeout_seconds=limit)
                        if r["status"] != "passed":
                            misses.append(f"check {check.get('name', ' '.join(check['run']))!r} {r['status']}: {_tail(log)}")
                    if task.get("expected"):
                        misses += score_role(own_words(answer, task["prompt"]), task["expected"])[1]
            finally:
                git.run(["worktree", "remove", "--force", str(work)], str(repo), check=False)
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
