"""The recorded runs: one JSON line per suite run, tied to the commit and a hash of the material it measured, and `aidd eval report`, which marks a row stale once that material changed."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path

from aidd import __version__
from aidd.evals import suites
from aidd.kernel import git, resources


def head_sha(repo: Path) -> str | None:
    """The full commit SHA of HEAD in the repository at `repo`; None outside git, before the first commit, or on any git error."""
    try:
        return git.run(["rev-parse", "--verify", "HEAD^{commit}"], str(repo)).strip() or None
    except (git.GitError, OSError, subprocess.SubprocessError):
        return None


def repo_top(path: Path) -> Path | None:
    """The top level of the git repository that holds `path` (a file or a directory); None outside git or on any error."""
    where = path if path.is_dir() else path.parent
    try:
        top = git.run(["rev-parse", "--show-toplevel"], str(where)).strip()
    except (git.GitError, OSError, subprocess.SubprocessError):
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
        status = git.run(["status", "--porcelain", "--untracked-files=all", "--", *(p for p in paths if p)], str(top)) if paths else ""
        if all_tracked:
            skip = _inside(ignore, top) if ignore is not None else None
            status += git.run(["status", "--porcelain", "--untracked-files=no", "--", ".", *([f":(exclude){skip}"] if skip else [])], str(top))
    except (git.GitError, OSError, subprocess.SubprocessError):
        return head, None
    return head, bool(status.strip())


def material_files(suite: str, directory: Path, *, embed: bool = True) -> list[Path]:
    """The files `material_sha256` reads: the case files, and for routing and roles the text aidd adds to each prompt
    (the prompt templates in suites.py, this module, the skill's reference with `embed`, each named role's agent file)."""
    files = sorted(directory.glob("*.yaml")) if directory.is_dir() else []
    if suite == "routing":
        skill = resources.data_dir("skill")
        files += [Path(__file__), Path(suites.__file__)] + ([skill / "SKILL.md", skill / "references" / "routes.md"] if embed else [])
    elif suite == "roles":
        roles = sorted({str(sc.get("role")) for sc in suites.load_scenarios(directory)}) if files else []
        files += [Path(__file__), Path(suites.__file__)] + [resources.data_dir("team") / "agents" / f"{role}.md" for role in roles]
    return files


def material_sha256(suite: str, directory: Path, *, embed: bool = True) -> str | None:
    """A SHA-256 over what a suite run measures, so a recorded score is tied to the material it scored.

    It hashes two things, each framed by its kind and its length:

    1. The case files: every `*.yaml` in `directory`, sorted by name, as its file name and its bytes.
    2. The prompt text sent: for each scenario in load order, the prompt the run with the aidd material sends on
       stdin. For routing, `PROMPT` with the reference (`embed=False` gives the line naming the skill). For roles,
       `ROLE_PROMPT` with the role's agent file. For tasks, the task's own prompt (a task with a problem sends none).

    The control's prompts are left out: the control only reports and never gates. A tasks run also depends on the
    repository it runs in, which the record's `head` and `dirty` name. None when `directory` holds no case, or a prompt
    cannot be built from it (an unknown role, say).
    """
    files = sorted(directory.glob("*.yaml")) if directory.is_dir() else []
    if not files:
        return None
    try:
        scenarios = suites.load_scenarios(directory)
        if suite == "routing":
            reference = suites.routing_reference(embed=embed)
            prompts = [suites.routing_prompt(sc, reference) for sc in scenarios]
        elif suite == "roles":
            prompts = [suites.role_prompt(sc) for sc in scenarios]
        elif suite == "tasks":
            prompts = [suites.task_prompt(t) for t in scenarios if not suites.task_problems(t)]
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
    stats = suites.summary(results)
    control_stats = suites.summary(control) if control is not None else None
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
