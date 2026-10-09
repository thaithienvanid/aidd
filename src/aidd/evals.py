"""Evaluations.

examples: run every examples/<case>/ through the gate and compare with expected.json.
routing: ask any agent CLI to route each scenario in evals/routing/*.toml and score it.
roles: send each aidd-team role a task with a seeded defect (evals/roles/*.toml) and score the answer.
standards: list the team's standards registry and the entries past their review cadence (emerging 90 days, established
    365, or the entry's own) or their review_due.
tasks: send your own agent configuration real tasks (evals/tasks/*.toml), each in a scratch worktree, and grade it by commands that must pass.

The agent suites are measurements, not fixtures: `measure` runs a suite K times and reports each
scenario's pass@1 (the share of trials that passed) and pass^K (every trial passed); a control run
without the aidd material gives the baseline the material is measured against (the lift); and
`record` appends one JSON line per run, so scores are compared over time, not remembered. Each line names the
commit that holds its material and a hash of its material (`material_sha256`), so `report` marks a row stale once the material changed.
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import re
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

from . import __version__, docs, gitutil, model, resources, rules, runner, util
from . import config as cfgmod
from .verify import verify

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
    applied. Another implementation of the gate runs these and compares its decision and codes.
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
    """The minimum route the gate's own rules compute for a scenario's `paths`, `type`, `lines`, and `dependencies`
    (each `manifest:name`, a dependency the change adds; the library function behind `aidd assess --paths` and
    `aidd new spec --paths`); None for a scenario that names no paths."""
    if "paths" not in sc:
        return None
    cfg = cfgmod.load_text(_SCENARIO_CONFIG.format(profile=sc.get("profile", "team")))
    deps = [dict(zip(("file", "name"), d.split(":", 1), strict=True)) for d in sc.get("dependencies", [])]
    return rules.assess_paths(cfg, sc["paths"], ctype=sc.get("type", "feat"), changed_lines=sc.get("lines", 0), dependencies=deps).required_route


def _ask(cmd: str, prompt: str, timeout: int, cwd: Path | None = None) -> str:
    """The agent's answer on stdout; OSError or TimeoutExpired propagate."""
    return subprocess.run(
        util.split_command(cmd), input=prompt, cwd=cwd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace"
    ).stdout


def routing_reference(*, embed: bool = True, material: bool = True) -> str:
    """The reference a routing prompt carries: the skill's text, a line naming the skill (`embed=False`), or nothing (the control)."""
    if not material:
        return ""
    return f"\nReference:\n{reference_text()}\n" if embed else "\nUse the aidd skill.\n"


def routing_prompt(sc: dict, reference: str) -> str:
    return PROMPT.format(reference=reference, profile=sc.get("profile", "team"), situation=sc["situation"].strip())


def run_routing(directory: Path, cmd: str, *, embed: bool = True, material: bool = True, timeout: int = 600) -> list[dict]:
    """One trial of every scenario. `material=False` is the control: no reference and no mention of the skill."""
    reference = routing_reference(embed=embed, material=material)
    results = []
    for sc in load_scenarios(directory):
        prompt = routing_prompt(sc, reference)
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
    """Every dated entry the team applies: standards by role, by domain pack, and by practice skill, extensions, and the
    practice skills themselves, with `where` naming its owner."""
    data = resources.roles()
    out = []
    for key in data["order"]:
        out += [dict(s, where=f"role {key}") for s in data["roles"][key]["standards"]]
        out += [dict(s, where=f"extension {key}") for s in data["roles"][key].get("extends", [])]
    for d in data["domains"]:
        out += [dict(s, where=f"domain {d['slug']}") for s in d["standards"]]
    for name in docs.practice_names():
        out += [dict(s, where=f"practice {name}") for s in data.get("practices", {}).get(name, {}).get("standards", [])]
        # The skill's own date says when its text was last re-read; the editions it names are checked above, one entry
        # each, so its date is a review, never a source check, and a rewrite of many skills in a day is no bulk edit.
        front = docs.practice_front(name)
        out.append({"name": f"practice skill aidd-team:{name}", "reviewed": front["checked"], "where": f"practice {name}"})
    return out


def dated(s: dict) -> str:
    """An entry's date: `checked` against a source, or `reviewed` for a practice with no source to check."""
    return str(s.get("checked") or s.get("reviewed") or "")


_SENTENCE_END = re.compile(r"[.!?][\"'”’)\]]*$")


def confirms(s: dict) -> bool:
    """Whether an entry's `evidence` confirms its `checked` date on its own.

    The URL must name a page, by its path or its query (a homepage shows only that a site exists), and the quote must be one full
    sentence: eight words or more, ending in `.`, `!`, or `?`, and neither the page title (` | `), the entry's own
    name, nor a copyright line. A title, a fragment, or boilerplate every page of a publisher carries shows that a page
    loaded, not that the edition was read. An
    extension's quote may instead be the line that names its pinned release, commit, or endpoint.
    """
    ev = s.get("evidence") or {}
    url, quote = urlparse(str(ev.get("url", ""))), " ".join(str(ev.get("quote", "")).split())
    if not (url.path.strip("/") or url.query):
        return False
    pins = [t for t in re.split(r"[\s(),@]+|==", str(s.get("pin", ""))) if len(t) >= 5 and re.search(r"\d|://", t)]
    if any(t in quote for t in pins):
        return True
    return (
        len(quote.split()) >= 8
        and bool(_SENTENCE_END.search(quote))
        and " | " not in quote
        and quote.casefold().rstrip(".") != str(s.get("name", "")).casefold()
        and not quote.casefold().startswith(("copyright", "©", "(c)"))
    )


def bulk_checked_dates(threshold: int = 20) -> list[tuple[str, int]]:
    """`checked` dates shared by more than `threshold` unconfirmed entries, as (date, count), newest first.

    One date across ISO 42001, the EU AI Act, MITRE ATLAS, and 250 others is a bulk edit, not that
    many independent confirmations. The currency control is only as good as the dates are honest,
    so `eval standards` fails when they cluster. A `reviewed` date claims no source check, so it is
    not counted.
    """
    counts: dict[str, int] = {}
    seen: set[str] = set()
    for s in standards():
        # One entry referenced by five roles is one check, not five; an entry whose `evidence` quotes a
        # sentence from a real page (`confirms`) is an individual confirmation, whatever its date.
        key = str(s.get("id") or s.get("name"))
        if key in seen or confirms(s):
            continue
        seen.add(key)
        d = str(s.get("checked") or "")
        if d:
            counts[d] = counts.get(d, 0) + 1
    return sorted(((d, n) for d, n in counts.items() if n > threshold), key=lambda x: x[0], reverse=True)


_RENUMBERED = re.compile(r"\brenumbered from (\d{4})\b(.*)", re.I | re.S)
_MOVE = re.compile(r"\b([A-Z]{2,}\d{2})\s+to\s+([A-Z]{2,}\d{2})\b")


def stale_id_citations() -> list[dict]:
    """Entries that still cite a control by an ID another entry says moved.

    An entry whose `notes` say `renumbered from 2025 (Excessive Agency LLM06 to LLM03; ...)` makes the
    2025 IDs stale: any other entry whose source or evidence URL still carries one (`llm062025`) points
    agents at the old number. Each result carries `old`, `new`, `token`, and `moved_by`.
    """
    table = resources.load_json("roles.json").get("standards", {})
    moves = []
    for sid, e in table.items():
        m = _RENUMBERED.search(str(e.get("notes", "")))
        if m:
            moves += [(sid, old, new, f"{old}{m.group(1)}".lower()) for old, new in _MOVE.findall(m.group(2))]
    out = []
    for sid, e in table.items():
        urls = " ".join((str(e.get("source", "")), str((e.get("evidence") or {}).get("url", "")))).lower()
        out += [dict(e, id=sid, old=old, new=new, token=token, moved_by=by) for by, old, new, token in moves if by != sid and token in urls]
    return out


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


def stale_standards(today: dt.date, max_days: int | None = None) -> list[dict]:
    """Entries due for review, each with `age_days` and `why`: older than their cadence (`review_every_days`, else 90
    days for an emerging entry and 365 for an established one; `max_days`, given by hand, for every entry), dated in
    the future or not at all, or past their `review_due`."""
    from . import knowledge

    stale = []
    for s in standards():
        limit = max_days if max_days is not None else knowledge.cadence_days(s)
        try:
            age = (today - dt.date.fromisoformat(dated(s))).days
        except (ValueError, TypeError):
            stale.append(dict(s, age_days=limit + 1, why="no valid date"))
            continue
        due = str(s.get("review_due") or "")
        if age < 0:
            stale.append(dict(s, age_days=age, why="dated in the future"))
        elif age > limit:
            stale.append(dict(s, age_days=age, why=f"older than its {limit}-day review cadence"))
        elif due and due < today.isoformat():
            stale.append(dict(s, age_days=age, why=f"its review_due {due} has passed"))
    return sorted(stale, key=lambda s: -s["age_days"])


def due_soon(today: dt.date, days: int = 90) -> list[dict]:
    """Entries not yet stale that come due for review within `days`, once each, soonest first, each with `due_on`."""
    from . import knowledge

    stale = {str(s.get("id") or s.get("name")) for s in stale_standards(today)}
    seen: set[str] = set()
    out = []
    for s in standards():
        key = str(s.get("id") or s.get("name"))
        if key in seen or key in stale:
            continue
        seen.add(key)
        try:
            due = dt.date.fromisoformat(dated(s)) + dt.timedelta(days=knowledge.cadence_days(s))
        except (ValueError, TypeError):
            continue
        if s.get("review_due"):
            due = min(due, dt.date.fromisoformat(str(s["review_due"])))
        if due <= today + dt.timedelta(days=days):
            out.append(dict(s, due_on=due.isoformat()))
    return sorted(out, key=lambda s: s["due_on"])


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


def role_prompt(sc: dict, *, material: bool = True) -> str:
    """The prompt a role scenario sends: the role's agent file and the task, or the task alone (the control)."""
    fields = {"role": sc["role"], "prompt": sc["prompt"].strip(), "fixture": sc["fixture"].strip()}
    return ROLE_PROMPT.format(playbook=role_playbook(sc["role"]), **fields) if material else CONTROL_ROLE_PROMPT.format(**fields)


def run_roles(directory: Path, cmd: str, *, material: bool = True, timeout: int = 900) -> list[dict]:
    """One trial of every scenario. `material=False` is the control: the role's name without its playbook."""
    results = []
    for sc in load_scenarios(directory):
        prompt = role_prompt(sc, material=material)
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


def task_prompt(task: dict) -> str:
    """What a task sends the agent: its own prompt, nothing added."""
    return task["prompt"].strip() + "\n"


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
                        answer = _ask(cmd, task_prompt(task), limit, cwd=work)
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


def head_sha(repo: Path) -> str | None:
    """The full commit SHA of HEAD in the repository at `repo`; None outside git, before the first commit, or on any git error."""
    try:
        return gitutil.run(["rev-parse", "--verify", "HEAD^{commit}"], str(repo)).strip() or None
    except (gitutil.GitError, OSError, subprocess.SubprocessError):
        return None


def repo_top(path: Path) -> Path | None:
    """The top level of the git repository that holds `path` (a file or a directory); None outside git or on any error."""
    where = path if path.is_dir() else path.parent
    try:
        top = gitutil.run(["rev-parse", "--show-toplevel"], str(where)).strip()
    except (gitutil.GitError, OSError, subprocess.SubprocessError):
        return None
    return Path(top).resolve() if top else None


def _inside(path: Path, top: Path) -> str | None:
    """`path` relative to `top`, in POSIX form; None when it lies outside."""
    try:
        return path.resolve().relative_to(top).as_posix()
    except ValueError:
        return None


def repo_state(repo: Path | None, files: list[Path], *, all_tracked: bool = False, ignore: Path | None = None) -> tuple[str | None, bool | None]:
    """The head of `repo` and whether `files` differ from it.

    `dirty` is True when any of `files` has an uncommitted change or is not committed at all (with `all_tracked`, also
    when any tracked file has an uncommitted change), False when the head holds them all as they are, and None when
    that is unknown: no head, a file outside the repository, or a git error. `ignore` (the record file) never counts,
    so appending a record does not make the next run dirty.
    """
    head = head_sha(repo) if repo is not None else None
    top = repo_top(repo) if head and repo is not None else None
    if head is None or top is None:
        return head, None
    paths = [_inside(f, top) for f in files]
    if any(p is None for p in paths):
        return head, None
    try:
        status = gitutil.run(["status", "--porcelain", "--untracked-files=all", "--", *(p for p in paths if p)], str(top)) if paths else ""
        if all_tracked:
            skip = _inside(ignore, top) if ignore is not None else None
            status += gitutil.run(["status", "--porcelain", "--untracked-files=no", "--", ".", *([f":(exclude){skip}"] if skip else [])], str(top))
    except (gitutil.GitError, OSError, subprocess.SubprocessError):
        return head, None
    return head, bool(status.strip())


def material_files(suite: str, directory: Path, *, embed: bool = True) -> list[Path]:
    """The files `material_sha256` reads: the case files, and for routing and roles the text aidd adds to each prompt
    (this module's prompt templates, the skill's reference with `embed`, each named role's agent file)."""
    files = sorted(directory.glob("*.toml")) if directory.is_dir() else []
    if suite == "routing":
        skill = resources.data_dir("skill")
        files += [Path(__file__)] + ([skill / "SKILL.md", skill / "references" / "routes.md"] if embed else [])
    elif suite == "roles":
        roles = sorted({str(sc.get("role")) for sc in load_scenarios(directory)}) if files else []
        files += [Path(__file__)] + [resources.data_dir("team") / "agents" / f"{role}.md" for role in roles]
    return files


def material_sha256(suite: str, directory: Path, *, embed: bool = True) -> str | None:
    """A SHA-256 over what a suite run measures, so a recorded score is tied to the material it scored.

    It hashes two things, each framed by its kind and its length:

    1. The case files: every `*.toml` in `directory`, sorted by name, as its file name and its bytes.
    2. The prompt text sent: for each scenario in load order, the prompt the run with the aidd material sends on
       stdin. For routing, `PROMPT` with the reference (`embed=False` gives the line naming the skill). For roles,
       `ROLE_PROMPT` with the role's agent file. For tasks, the task's own prompt (a task with a problem sends none).

    The control's prompts are left out: the control only reports and never gates. A tasks run also depends on the
    repository it runs in, which the record's `head` and `dirty` name. None when `directory` holds no case, or a prompt
    cannot be built from it (an unknown role, say).
    """
    files = sorted(directory.glob("*.toml")) if directory.is_dir() else []
    if not files:
        return None
    try:
        scenarios = load_scenarios(directory)
        if suite == "routing":
            reference = routing_reference(embed=embed)
            prompts = [routing_prompt(sc, reference) for sc in scenarios]
        elif suite == "roles":
            prompts = [role_prompt(sc) for sc in scenarios]
        elif suite == "tasks":
            prompts = [task_prompt(t) for t in scenarios if not task_problems(t)]
        else:
            return None
    except (OSError, KeyError, TypeError, AttributeError, ValueError):
        return None
    digest = hashlib.sha256()
    for kind, name, data in [("case", p.name, p.read_bytes()) for p in files] + [("prompt", "", x.encode("utf-8")) for x in prompts]:
        digest.update(f"{kind}\0{name}\0{len(data)}\0".encode())
        digest.update(data)
    return digest.hexdigest()


def cases_path(directory: Path) -> str | None:
    """Where a record says its cases are: relative to the top level of the git repository that holds them, so a
    record never names a path on one machine. None outside git."""
    top = repo_top(directory) if directory.is_dir() else None
    return _inside(directory, top) if top else None


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
    head: str | None = None,
    dirty: bool | None = None,
    material: str | None = None,
    cases: str | None = None,
) -> dict:
    """One run as a JSON-ready record: what ran, on what, and how each scenario did.

    `model` is whatever the operator passed with --model-label; aidd never infers it from the command. `head` and
    `dirty` come from `repo_state` on the repository that holds the material, `material` is the suite's
    `material_sha256`, and `cases` is `cases_path`, so `aidd eval report` can tell a stale row from a fresh one.
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
        "head": head,
        "dirty": dirty,
        "material_sha256": material,
        "cases": cases,
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


def current_material(run: dict, top: Path | None) -> str | None:
    """The material a recorded run's suite has now: its `cases` resolved against `top`, the top level of the repository
    that holds the record file. None when there is no `top`, no `cases`, or `cases` leaves the repository."""
    cases = run.get("cases")
    if top is None or not isinstance(cases, str) or not cases:
        return None
    directory = top / cases
    if Path(cases).is_absolute() or _inside(directory, top) is None:
        return None
    options = run.get("options") or {}
    return material_sha256(str(run.get("suite")), directory, embed=bool(options.get("embed", True)))


def material_state(run: dict, current: str | None) -> str:
    """`fresh` when the run's material is the current one, `stale` when it differs, `unknown` when either is missing."""
    recorded = run.get("material_sha256")
    if not recorded or not current:
        return "unknown"
    return "fresh" if recorded == current else "stale"


STALE_NOTE = (
    "stale rows ({n}): the case files or the prompt text changed after the run. Their scores measured other material, so rerun them before you compare them."
)


def report_markdown(runs: list[dict], states: list[str] | None = None) -> str:
    """Recorded runs over time as a markdown table, one row per run, and a note below it when a row is stale.

    `states` holds each run's Material cell (`material_state`); without it every row reads `unknown`.
    """

    def pct(x) -> str:
        return "" if x is None else f"{x:.1%}"

    states = states if states is not None else ["unknown"] * len(runs)
    rows = [
        "| Date | Suite | Model | aidd | K | Scenarios | Mean pass@1 | pass^K | Control pass@1 | Lift | Threshold | Material |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r, state in zip(runs, states, strict=True):
        control, lift = r.get("control") or {}, r.get("lift")
        cells = [r["date"], r["suite"], r.get("model") or "(not given)", r.get("aidd_version", ""), r.get("repeat", 1), len(r.get("scenarios", []))]
        cells += [pct(r["mean_pass_at_1"]), pct(r.get("pass_k_share")), pct(control.get("mean_pass_at_1"))]
        cells += ["" if lift is None else f"{lift * 100:+.1f} pts", pct(r.get("threshold")), state]
        rows.append("| " + " | ".join(map(str, cells)) + " |")
    stale = states.count("stale")
    return "\n".join(rows) + ("\n\n" + STALE_NOTE.format(n=stale) if stale else "")


def report(paths: list[Path]) -> str:
    """`aidd eval report`: the runs in these JSON-lines files, oldest first, each compared with the material it has now.

    A record's `cases` resolves against the top level of the repository that holds its file, never the current directory.
    """
    pairs = [(run, repo_top(path.resolve())) for path in paths for run in load_records([path])]
    pairs.sort(key=lambda p: (str(p[0]["date"]), str(p[0]["suite"])))
    return report_markdown([run for run, _ in pairs], [material_state(run, current_material(run, top)) for run, top in pairs])
