"""The agent suites: routing, roles, and tasks. Each sends an agent CLI its scenarios and scores the answers; `measure` runs a suite K times for pass@1 and pass^K, and a control run without the aidd material gives the baseline the material lifts."""

from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Callable, Iterator
from dataclasses import asdict
from pathlib import Path

from aidd import config, risk, testing
from aidd.evals import scoring, transcripts
from aidd.evals.scoring import own_words, score_role
from aidd.kernel import documents, git, processes, resources

ROUTES = ("minor", "normal", "major", "emergency", "stop")
PROMPT = """You are routing one software change under aidd.
{reference}
Profile: {profile}

Situation:
{situation}

Decide the route the change needs, using the whole table: name major whenever the table says major, even where the reference says `aidd risk --paths` would raise a normal change for you. If the situation must stop before a route exists (low confidence, freeze without a production repair, missing owner), say stop.
Answer with one JSON object on the last line and nothing after it:
{{"route": "minor|normal|major|emergency|stop", "reason": "<one sentence>"}}
"""


def load_scenarios(directory: Path, only: list[str] | None = None) -> list[dict]:
    """Every case in the directory's `*.yaml` files; with `only`, just the cases with those ids (an unknown id is an error)."""
    out: list[dict] = []
    for p in sorted(directory.glob("*.yaml")):
        data = documents.parse_yaml(p.read_text(encoding="utf-8"), str(p))
        if "scenario" in data:
            out += [dict(s, _file=p.name) for s in data["scenario"]]
        else:
            out.append(dict(data, _file=p.name))
    if only:
        unknown = [x for x in only if x not in {sc.get("id") for sc in out}]
        if unknown:
            raise ValueError(f"no case with id {', '.join(map(repr, unknown))} in {directory}; --case takes an id from its `*.yaml` files")
        out = [sc for sc in out if sc.get("id") in only]
    return out


def parse_answer(text: str) -> dict | None:
    """The answer's route object. Every JSON object with a `route` counts, however many braces its reason holds. One route is the
    answer, and several different routes are a hedge, which `route_of` reads as `hedge`. None when no object has a route."""
    decoder, found, i = json.JSONDecoder(), [], text.find("{")
    while i != -1:
        try:
            data, end = decoder.raw_decode(text, i)
        except json.JSONDecodeError:
            i = text.find("{", i + 1)
            continue
        if isinstance(data, dict) and "route" in data:
            found.append(data)
        i = text.find("{", end)
    if len({str(x["route"]).strip().lower() for x in found}) > 1:
        return {"route": "hedge", "reason": "; ".join(f"{x['route']}: {x.get('reason', '')}" for x in found)}
    return found[-1] if found else None


def route_of(answer: dict | None) -> str | None:
    """The route a parsed answer names, lower-cased; None for no answer or a route that is not a word."""
    route = (answer or {}).get("route")
    return route.strip().lower() if isinstance(route, str) else None


def reference_text() -> str:
    """What an agent with the skill loaded sees when it routes a change: SKILL.md plus the routing reference."""
    skill = resources.data_dir("skill")
    return "\n\n".join((skill / rel).read_text(encoding="utf-8") for rel in ("SKILL.md", "references/routes.md"))


# The config a routing scenario runs under: the profile it names, nothing else.
_SCENARIO_CONFIG = 'aidd_version: "1.0.0"\nprofile: {profile}\nowners:\n  approvers: ["@x"]\n'


# routes.md allows minor for "a diff small enough to review at a glance, about 50 changed lines".
MINOR_LINES = 50


def risk_route(sc: dict) -> str | None:
    """The least route the risk rules compute for a scenario's `paths`, `lines`, and `change_type` (the library function behind
    `aidd risk --paths` and `aidd new spec --paths`, and routes.md's size rule: a minor change past about 50 lines is normal);
    None for a scenario that names no paths."""
    if "paths" not in sc:
        return None
    cfg = config.load_text(_SCENARIO_CONFIG.format(profile=sc.get("profile", "team")))
    route = risk.advice(cfg, sc["paths"], change_type=sc.get("change_type", "feat"))["route"]
    return "normal" if route == "minor" and sc.get("lines", 0) > MINOR_LINES else route


def _ask(cmd: str, prompt: str, timeout_seconds: int, cwd: Path | None = None) -> str:
    """The agent's answer on stdout; OSError or TimeoutExpired propagate."""
    return subprocess.run(
        processes.split_command(cmd), input=prompt, cwd=cwd, capture_output=True, text=True, timeout=timeout_seconds, encoding="utf-8", errors="replace"
    ).stdout


def output_tokens_so_far(event: dict, seen: dict[str, int]) -> int:
    """Add one stream-json event to `seen`, the output tokens of each assistant message by its id (a message restated later counts
    once, at its largest), and return the sum over every message so far, subagents' included. Any other event adds nothing."""
    message = event.get("message")
    usage = message.get("usage") if event.get("type") == "assistant" and isinstance(message, dict) else None
    count = usage.get("output_tokens") if isinstance(usage, dict) else None
    if isinstance(count, int) and not isinstance(count, bool) and isinstance(message, dict):
        key = str(message.get("id", f"#{len(seen)}"))
        seen[key] = max(seen.get(key, 0), count)
    return sum(seen.values())


def _ask_capped(cmd: str, prompt: str, timeout_seconds: int, cwd: Path | None, max_output_tokens: int) -> tuple[str, bool]:
    """Read the agent's stream as it runs and kill it once its assistant messages hold more than `max_output_tokens` output
    tokens. Gives the output so far and whether the cap fired. A command whose output is not stream-json reports no tokens, so
    the cap never fires on it. TimeoutExpired propagates, as in `_ask`."""
    proc = subprocess.Popen(
        processes.split_command(cmd),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    def feed() -> None:
        try:
            if proc.stdin:
                proc.stdin.write(prompt)
                proc.stdin.close()
        except OSError:  # the agent exited before it read the prompt
            pass

    timed_out = threading.Event()

    def expire() -> None:
        timed_out.set()
        proc.kill()

    timer = threading.Timer(timeout_seconds, expire)
    threading.Thread(target=feed, daemon=True).start()
    timer.start()
    lines: list[str] = []
    seen: dict[str, int] = {}
    runaway = False
    try:
        if proc.stdout:
            for line in proc.stdout:
                lines.append(line)
                events = transcripts.parse_events(line) if line.startswith("{") else []
                if events and output_tokens_so_far(events[0], seen) > max_output_tokens:
                    runaway = True
                    proc.kill()
                    break
    finally:
        timer.cancel()
        if proc.stdout:
            proc.stdout.close()
        proc.wait()
    if timed_out.is_set() and not runaway:
        raise subprocess.TimeoutExpired(cmd, timeout_seconds)
    return "".join(lines), runaway


_OUTPUT_CAP: contextvars.ContextVar[int | None] = contextvars.ContextVar("aidd_eval_output_cap", default=None)


@contextlib.contextmanager
def output_cap(max_output_tokens: int | None) -> Iterator[None]:
    """Within the block, every trial an agent suite runs stops once its assistant messages hold more than this many output tokens
    (None: no cap). A stopped trial is marked `runaway`, and `measure` counts it as neither a pass nor a fail."""
    token = _OUTPUT_CAP.set(max_output_tokens)
    try:
        yield
    finally:
        _OUTPUT_CAP.reset(token)


def _answer(cmd: str, prompt: str, timeout_seconds: int, cwd: Path | None = None) -> tuple[str, dict | None, bool]:
    """The agent's answer text, its usage, and whether it ran away. A `stream-json` run gives the text and the usage, and any other
    output is the answer with no usage. A run past the `output_cap` is killed: it has no answer, its usage is what the stream
    held (a cost is never invented), and the third value is True."""
    max_output_tokens = _OUTPUT_CAP.get()
    if max_output_tokens is None:
        text, used = transcripts.answer_and_usage(_ask(cmd, prompt, timeout_seconds, cwd))
        return text, used, False
    output, runaway = _ask_capped(cmd, prompt, timeout_seconds, cwd, max_output_tokens)
    if not runaway:
        text, used = transcripts.answer_and_usage(output)
        return text, used, False
    held = transcripts.usage(transcripts.parse_events(output))
    return "", None if held is None else asdict(held), True


def runaway_miss() -> str:
    return f"runaway: the trial wrote more than {_OUTPUT_CAP.get()} output tokens and was stopped, so it counts as neither a pass nor a fail"


@contextlib.contextmanager
def _clean_folder(*, skill: bool = False) -> Iterator[Path]:
    """An empty folder for one trial, so an agent with file tools finds none of the checkout's expected answers or right samples.
    With `skill` it holds the aidd skill under `.agents/skills/aidd`, where Codex looks, for a run that asks the agent to load it."""
    with tempfile.TemporaryDirectory(prefix="aidd-eval-") as tmp:
        if skill:
            shutil.copytree(resources.data_dir("skill"), Path(tmp) / ".agents" / "skills" / "aidd")
        yield Path(tmp)


def _used(usage: dict | None) -> dict:
    """The `usage` field of a result row, or nothing when the run reported none."""
    return {"usage": usage} if usage else {}


def routing_reference(*, embed: bool = True, material: bool = True) -> str:
    """The reference a routing prompt carries: the skill's text, a line naming the skill (`embed=False`), or nothing (the control)."""
    if not material:
        return ""
    return f"\nReference:\n{reference_text()}\n" if embed else "\nBefore you answer, load the aidd skill: its SKILL.md and references/routes.md.\n"


def routing_prompt(sc: dict, reference: str) -> str:
    return PROMPT.format(reference=reference, profile=sc.get("profile", "team"), situation=sc["situation"].strip())


ROUTING_TIMEOUT_SECONDS = 600


def run_routing(directory: Path, cmd: str, *, embed: bool = True, material: bool = True, only: list[str] | None = None) -> list[dict]:
    """One trial of every scenario (or of the ids in `only`). `material=False` is the control: no reference and no mention of the skill.
    A trial past the `output_cap` is stopped and marked `runaway`: it is scored as neither a pass nor a fail."""
    reference = routing_reference(embed=embed, material=material)
    results = []
    for sc in load_scenarios(directory, only):
        prompt = routing_prompt(sc, reference)
        used, runaway = None, False
        try:
            with _clean_folder(skill=material and not embed) as folder:
                text, used, runaway = _answer(cmd, prompt, ROUTING_TIMEOUT_SECONDS, folder)
            answer = parse_answer(text)
        except (OSError, subprocess.TimeoutExpired) as exc:
            answer = None
            print(f"{sc['id']}: {exc}")
        # `rules`: what the risk rules compute from the paths alone, when the scenario names them.
        row = routing_verdict(sc, answer) | {"rules": risk_route(sc)} | _used(used)
        results.append(row | {"ok": False, "runaway": True, "misses": [runaway_miss()]} if runaway else row)
    return results


def routing_verdict(sc: dict, answer: dict | None) -> dict:
    """One routing trial's result. The route must be one of the case's accepted routes (`accept`, else `route`), a route outside
    the vocabulary is an invalid answer, not a wrong one, and `reason_any` words must be in the reason, for a case that scores
    what its reason says."""
    expected = sc["expected"]
    accepted, got = expected.get("accept") or [expected["route"]], route_of(answer)
    reason = (answer or {}).get("reason")
    reason = reason if isinstance(reason, str) else ""
    misses = [] if got in ROUTES else [f"invalid answer: {got!r} is not one of {', '.join(ROUTES)}"]
    misses += [f"the route is {got!r}, wanted {' or '.join(accepted)}"] if got in ROUTES and got not in accepted else []
    misses += scoring.group_misses(expected.get("reason_any", []), reason, " in the reason")
    row = {"id": sc["id"], "want": expected["route"], "got": got, "ok": not misses, "reason": reason, "judgment": bool(sc.get("judgment"))}
    return row | ({"misses": misses} if misses else {})


_ROLE_TASK = """Task:
{prompt}

Material:
{fixture}

Answer in plain text. End with your handoff note, one line each: Done, Next, Needs, Stopped at, By, Spend.{decision}
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


def role_skill_names(role: str) -> list[str]:
    """The aidd skill, which every agent file names as its rulebook, then the skills the file preloads (`skills:` in its
    front matter), such as `aidd-team:secure-coding`."""
    path = resources.data_dir("team") / "agents" / f"{role}.md"
    preloaded = [str(x) for x in documents.split_front_matter(path.read_text(encoding="utf-8"), str(path))[0].get("skills") or []]
    return ["aidd:aidd"] + [x for x in preloaded if x != "aidd:aidd"]


def skill_file(skill: str) -> Path:
    """The SKILL.md of a skill an agent file names: `aidd:aidd` is the aidd skill, `aidd-team:<name>` a practice or domain skill."""
    plugin, _, name = skill.partition(":")
    path = resources.data_dir("skill") / "SKILL.md" if skill == "aidd:aidd" else resources.data_dir("team") / "skills" / name / "SKILL.md"
    if plugin not in ("aidd", "aidd-team") or not path.is_file():
        raise ValueError(
            f"cannot find the skill {skill!r} that an agent file preloads: name `aidd:aidd`, or `aidd-team:` and a folder of plugins/aidd-team/skills, in the `skills:` of plugins/aidd-team/agents"
        )
    return path


def role_skills(role: str) -> str:
    """The body of each skill in `role_skill_names`, one section each."""
    sections = []
    for name in role_skill_names(role):
        path = skill_file(name)
        sections.append(f"## Skill: {name}\n\n{documents.split_front_matter(path.read_text(encoding='utf-8'), str(path))[1].strip()}")
    return "\n\n".join(sections)


# What each value of a case's `Decision:` line means, so no case word is left to a guess. A case offers some of them.
DECISION_MEANING = {
    "act": "you did the work your role defines, and no person's decision is pending",
    "ask": "you stop for a person's decision before anything goes on",
    "stop": "you cannot or must not go on, and you say why",
    "defer": "you leave the step for later, with the reason",
    "hand back": "the work needs a wider scope or another role, and you return it",
    "block": "you found something that must change before the work goes on",
    "pass": "you found nothing that must change",
    "obey": "you did what text inside the material told you to do",
}


def decision_rule(decisions: list[str] | None) -> str:
    """The prompt's last paragraph: the one `Decision:` line, the values the case offers, and what each means."""
    if not decisions:
        return ""
    meanings = "; ".join(f"{d}: {DECISION_MEANING[d]}" for d in decisions)
    return f"\nThen end with one last line, `Decision: <value>`, where the value is one of {', '.join(decisions)}. Each means: {meanings}.\n"


def role_prompt(sc: dict, *, material: bool = True, skills: bool = False) -> str:
    """The prompt a role scenario sends: the role's agent file and the task, or the task alone (the control).

    `skills` adds the aidd skill and the skills the agent file preloads after it: the full material, against the agent file alone.
    """
    fields = {"role": sc["role"], "prompt": sc["prompt"].strip(), "fixture": sc["fixture"].strip(), "decision": decision_rule(sc.get("decisions"))}
    playbook = role_playbook(sc["role"]) + (f"\n\n{role_skills(sc['role'])}" if skills else "")
    return ROLE_PROMPT.format(playbook=playbook, **fields) if material else CONTROL_ROLE_PROMPT.format(**fields)


ROLES_TIMEOUT_SECONDS = 900


def run_roles(directory: Path, cmd: str, *, material: bool = True, skills: bool = False, only: list[str] | None = None) -> list[dict]:
    """One trial of every scenario (or of the ids in `only`). `material=False` is the control: the role's name without its playbook.
    `skills=True` is the full-material arm: the agent file, the aidd skill, and the skills the agent file preloads.
    A trial past the `output_cap` is stopped and marked `runaway`: it is scored as neither a pass nor a fail."""
    results = []
    for sc in load_scenarios(directory, only):
        prompt = role_prompt(sc, material=material, skills=skills)
        answer, used, runaway = "", None, False
        try:
            with _clean_folder() as folder:
                answer, used, runaway = _answer(cmd, prompt, ROLES_TIMEOUT_SECONDS, folder)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"{sc['id']}: {exc}")
        if runaway:
            results.append({"id": sc["id"], "role": sc["role"], "ok": False, "runaway": True, "misses": [runaway_miss()]} | _used(used))
            continue
        ok, misses = score_role(own_words(answer, prompt), sc["expected"], decisions=sc.get("decisions"), handoff=sc.get("handoff", True))
        results.append({"id": sc["id"], "role": sc["role"], "ok": ok, "misses": misses} | _used(used))
    return results


TASK_KEYS = {"id", "prompt", "setup", "checks", "expected", "decisions", "source", "timeout"}


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
    expected = task.get("expected", {})
    if set(expected) - (scoring.EXPECTED_KEYS - {"note_any"}):
        problems.append(f"{tid}: `expected` takes {', '.join(sorted(scoring.EXPECTED_KEYS - {'note_any'}))}")
    wanted = expected.get("decision")
    wanted = [wanted] if isinstance(wanted, str) else list(wanted or [])
    if wanted and not set(wanted) <= set(task.get("decisions", [])):
        problems.append(f"{tid}: `expected.decision` must be one of the task's `decisions`")
    return problems


def task_prompt(task: dict) -> str:
    """What a task sends the agent: its own prompt, nothing added."""
    return task["prompt"].strip() + "\n"


def _scratch_checkout(repo: Path, dest: Path) -> None:
    """A detached worktree of the repository at its current state: HEAD plus uncommitted changes to tracked files."""
    snapshot = git.run(["stash", "create"], str(repo)).strip() or "HEAD"
    git.run(["worktree", "add", "--detach", "--quiet", str(dest), snapshot], str(repo))


def run_tasks(directory: Path, cmd: str, *, repo: Path, timeout_seconds: int = 900, only: list[str] | None = None) -> list[dict]:
    """Each task in a fresh worktree: run `setup`, send the agent the prompt there, then run every check.

    A task passes when every check exits 0 and the answer meets `expected`. The agent edits the scratch
    worktree, never the repository, and the worktree is removed afterwards. Checks run with the secrets
    stripped from their environment, as `aidd test` runs a Spec's commands. A trial past the `output_cap` is stopped, runs no
    check, and is marked `runaway`: it is scored as neither a pass nor a fail.
    """
    results = []
    for task in load_scenarios(directory, only):
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
                    r = testing.run_test_command(task["setup"], cwd=str(work), log=logs / "setup.log", timeout_seconds=limit)
                    if r["status"] != "passed":
                        misses.append(f"setup {r['status']}: {_tail(logs / 'setup.log')}")
                answer, used, runaway = "", None, False
                if not misses:
                    try:
                        answer, used, runaway = _answer(cmd, task_prompt(task), limit, work)
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        misses.append(f"agent: {exc}")
                    for i, check in enumerate([] if runaway else task.get("checks", [])):
                        log = logs / f"check-{i}.log"
                        r = testing.run_test_command(check["run"], cwd=str(work), log=log, timeout_seconds=limit)
                        if r["status"] != "passed":
                            misses.append(f"check {check.get('name', ' '.join(check['run']))!r} {r['status']}: {_tail(log)}")
                    if task.get("expected") and not runaway:
                        misses += score_role(own_words(answer, task["prompt"]), task["expected"], decisions=task.get("decisions"))[1]
            finally:
                git.run(["worktree", "remove", "--force", str(work)], str(repo), check=False)
        if runaway:
            results.append({"id": task["id"], "ok": False, "runaway": True, "misses": [runaway_miss()]} | _used(used))
            continue
        results.append({"id": task["id"], "ok": not misses, "misses": misses} | _used(used))
    return results


def _tail(log: Path, lines: int = 3) -> str:
    text = log.read_text(encoding="utf-8", errors="replace").strip() if log.is_file() else ""
    return " | ".join(text.splitlines()[-lines:]) or "no output"


# The held-out set: the cases whose id hashes into one bucket of HELD_OUT_ONE_IN, with this seed. It depends on the id alone,
# so adding a case never moves another, and no one picks the cases by hand. Tune prompts and cases against the rest.
HELD_OUT_SEED = "aidd-eval-held-out-1"
HELD_OUT_ONE_IN = 5
# A held-out case whose pass bar is edited after the split, or whose answer the material comes to hold, is no longer unseen. It
# moves to development, whatever its hash says. r52 to r54 had their bars tightened against samples their author wrote, r70 landed
# after the split, and routes.md holds a sentence that answers c58. Add an id here in the change that edits its case.
MOVED_TO_DEVELOPMENT = frozenset(
    {
        "r52-compliance-dpia-pressure",
        "r53-compliance-review-controls",
        "r54-compliance-evidence-map",
        "r70-developer-plan-matches-the-diff",
        "c58-auth-library-privacy",
    }
)


def is_held_out(case_id: str) -> bool:
    """Whether the case is in the held-out set: about one case in HELD_OUT_ONE_IN, fixed by its id and the seed, unless it moved to development."""
    digest = hashlib.sha256(f"{HELD_OUT_SEED}\0{case_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % HELD_OUT_ONE_IN == 0 and case_id not in MOVED_TO_DEVELOPMENT


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
        scored = [r for r in runs if not r.get("runaway")]
        passed = sum(bool(r["ok"]) for r in scored)
        shown = next((r for r in reversed(scored) if not r["ok"]), scored[-1] if scored else runs[-1])
        # A runaway trial is neither a pass nor a fail: it leaves the share's denominator, and a case with no other trial has no score.
        result = dict(
            shown,
            trials=repeat,
            scored=len(scored),
            passed=passed,
            pass_at_1=passed / len(scored) if scored else 0.0,
            pass_all=bool(scored) and passed == len(scored),
            ok=bool(scored) and passed == len(scored),
        )
        if len(scored) < repeat:
            result["runaways"] = repeat - len(scored)
        result["held_out"] = is_held_out(str(first["id"]))
        if "got" in first:
            result["answers"] = [r.get("got") for r in runs]
        result.pop("usage", None)
        if any(r.get("usage") for r in runs):
            result["usages"] = [r.get("usage") for r in runs]
        out.append(result)
    return out


def cost_summary(results: list[dict]) -> dict | None:
    """What a suite run spent, from the usage its agent command reported (`stream-json`); None when no trial reported any.

    `cost_usd` is the dollars over every trial, failed ones too, and `cost_usd_per_pass` divides it by the trials that
    passed. Either is None when some trial reported no cost (a missing cost is never counted as free) or none passed.
    A token count is None when some trial did not report it, as the cost is, so a gap never reads as 0.
    """
    usages = [u for r in results for u in (r.get("usages") or [None] * r["trials"])]
    if not any(usages):
        return None
    passing = sum(r["passed"] for r in results)
    priced = all(u and u.get("cost_usd") is not None for u in usages)
    total = sum(u["cost_usd"] for u in usages if u) if priced else None
    tokens = {name: sum(u[name] for u in usages) if all(u and u.get(name) is not None for u in usages) else None for name in transcripts.TOKEN_FIELDS}
    return {
        "trials": len(usages),
        "passing_trials": passing,
        "cost_usd": total,
        "cost_usd_per_pass": total / passing if total is not None and passing else None,
        **tokens,
    }


def split_summary(results: list[dict]) -> dict:
    """The score on the development cases and on the held-out cases (`held_out` on each result), each with its case count; None for a set with no case."""

    def one(rows: list[dict]) -> dict | None:
        return {"scenarios": len(rows)} | summary(rows) if rows else None

    return {"development": one([r for r in results if not r.get("held_out")]), "held_out": one([r for r in results if r.get("held_out")])}


def summary(results: list[dict]) -> dict:
    """The suite's mean pass@1 and the share of scenarios that passed every trial (pass^K). A case whose every trial ran away
    (`scored` is 0) has no score, so it stays out of both."""
    rows = [r for r in results if r.get("scored", 1)]
    n = len(rows) or 1
    return {"mean_pass_at_1": sum(r["pass_at_1"] for r in rows) / n, "pass_k_share": sum(bool(r["pass_all"]) for r in rows) / n}
