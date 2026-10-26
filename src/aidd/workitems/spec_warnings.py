"""What `aidd validate` warns about in a Spec, never a gate rule: Acceptance no test covers, a plan and tests that
disagree, vague Acceptance, a word the glossary says to avoid, unsourced claims, a stale stored status, and what a landed Spec still owes.
"""

from __future__ import annotations

import datetime as dt
import functools
import itertools
import re
from pathlib import Path

from aidd import config
from aidd.kernel import documents, git, resources
from aidd.kernel.documents import markdown_section
from aidd.workitems import backlog, repo_reads
from aidd.workitems import objects as workitems_objects
from aidd.workitems.spec_file import ACCEPTANCE_ID as ACCEPTANCE_ID
from aidd.workitems.spec_file import acceptance_ids

# From review on: a client who accepts by hand (`uat: true`) has an acceptance record that lists the Spec's ids.
_ACCEPTANCE_DUE = frozenset({"in_review", "landed", "done"})


def after_ship_warnings(path: Path, text: str, data: dict, today: dt.date | None = None) -> list[str]:
    """What a Spec owes once it is in review or landed, as warnings: the outcome of a hypothesis past its due date,
    and, with `uat: true`, an acceptance record that lists every Acceptance id. The status is the stored one, as a
    cache (a recorded `outcome.released_on` also says it landed); the gate never reads either."""
    from aidd.workitems import derived_status

    status = derived_status.spec_status(data)
    out = []
    due = derived_status.outcome_due(data, status, today or dt.date.today())
    if due is not None:
        how = "met, missed, or inconclusive, with the number, in the Spec's `outcome.result`"
        out.append(f"warning: {path}: the hypothesis was due {due} and no outcome.result is recorded; record the outcome ({how})")
    released = bool((data.get("outcome") or {}).get("released_on"))
    ids = acceptance_ids(text)
    root = repo_root_of(path)
    if data.get("uat") and ids and root is not None and (status in _ACCEPTANCE_DUE or released):
        sid = data.get("id")
        files = [
            f
            for d in data.get("docs") or []
            if isinstance(d, dict) and d.get("kind") == "acceptance"
            for f in workitems_objects.files_matching(root, str(d.get("path")))
        ]
        why = f"uat: true and the Spec is {status if status in _ACCEPTANCE_DUE else 'released'}"
        if not files:
            out.append(
                f"warning: {path}: {why}, but it links no acceptance record; `aidd new acceptance <topic> --spec {sid}`, "
                "and a person records the client's acceptance of each Acceptance id before it lands"
            )
        else:
            listed = {i for f in files for i in ACCEPTANCE_ID.findall((root / f).read_text(encoding="utf-8", errors="replace"))}
            missing = [i for i in ids if i not in listed]
            if missing:
                out.append(f"warning: {path}: {why}, but the acceptance record {', '.join(files)} does not list {', '.join(missing)}; add a row for each")
    return out


def coverage_warnings(path: Path, text: str, data: dict) -> list[str]:
    """Acceptance items no test command covers, and covered ids the Acceptance does not have, as warnings.
    Opt-in: only once a command declares `covers`, so a Spec written before the field existed stays quiet.
    The gate reads `covers` only under `tests.mode: with_code` (tests.with_uncovered); otherwise this only shows the gaps."""
    commands = (data.get("tests") or {}).get("commands", []) or []
    declared = [c for c in commands if isinstance(c, dict) and c.get("covers")]
    if not declared:
        return []
    ids = acceptance_ids(text)
    covered = {i for c in declared for i in c["covers"]}
    if not ids:
        return [f"warning: {path}: tests.commands declare covers, but the '## Acceptance' section names no item ids; start each item with its id (A1, A2, ...)"]
    out = [
        f"warning: {path}: Acceptance item {i} is covered by no test command; add it to a command's covers, or say why it is not provable"
        for i in ids
        if i not in covered
    ]
    for c in declared:
        out += [
            f"warning: {path}: test command {c.get('name')!r} covers {i}, which the '## Acceptance' section does not have" for i in c["covers"] if i not in ids
        ]
    return out


# A Task's proof that names a test command: "test `rate-limit`", "command `unit`", or "`rate-limit` test".
_PROOF_COMMAND = re.compile(r"\b(?:tests?|commands?)\s+`([a-z0-9][a-z0-9_.-]{0,63})`|`([a-z0-9][a-z0-9_.-]{0,63})`\s+(?:tests?|commands?)\b", re.I)


def _approval_holds(root: Path, path: Path, data: dict) -> bool:
    from aidd.workitems import derived_status

    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return derived_status.stored_status(data) in derived_status.PAST_APPROVAL
    return derived_status.Observer(root, repo_reads.config_at(root)).holds(rel, data)


def listed_files(path: Path, data: dict) -> list[str]:
    """The repository's files (tracked, and untracked but not ignored), read only when a Task's scope is a glob or a
    folder: what such a scope stands for. Empty outside a git checkout."""
    scopes = [s for task in data.get("tasks") or [] for s in task.get("scope") or [] if isinstance(s, str)]
    root = repo_root_of(path)
    if root is None or not (root / ".git").exists() or not any(any(c in s for c in "*?") or s.endswith("/") for s in scopes):
        return []
    try:
        out = git.run(["ls-files", "-z", "--cached", "--others", "--exclude-standard"], str(root), check=False)
    except git.GitError:
        return []
    return [p for p in out.split("\0") if p]


def repo_root_of(path: Path) -> Path | None:
    for d in path.resolve().parents:
        if (d / ".aidd").is_dir() or (d / ".git").exists():
            return d
    return None


def _suite_names(root: Path | None) -> set[str]:
    """The repository suite's `tests` names, read offline; an unreadable config yields what its own file names."""
    if root is None or not (root / config.CONFIG_PATH).is_file():
        return set()

    def offline(url: str) -> bytes:
        raise config.ConfigError(f"not fetched: {url}")

    try:
        cfg = config.load_file(config.CONFIG_PATH, str(root), fetch=offline)
        return {t.get("name") for t in cfg.get("tests", default=[]) or []}
    except Exception:  # noqa: BLE001  # a parent out of reach: fall back to the file's own entries
        try:
            raw = documents.parse_yaml((root / config.CONFIG_PATH).read_text(encoding="utf-8"), config.CONFIG_PATH)
        except (OSError, documents.DocumentError):
            return set()
        return {str(t.get("name")) for t in raw.get("tests", []) if isinstance(t, dict)}


def consistency_warnings(path: Path, data: dict) -> list[str]:
    """Where a Spec's plan and its tests disagree, as warnings: a frozen test file that is not on disk, a Task
    proof naming a test command nobody defined, and an experiment with no guardrail or no hypothesis to decide.
    (A command that runs a file outside tests.files is a lint error.)"""
    out = []
    exp = data.get("experiment")
    if isinstance(exp, dict):
        if not exp.get("guardrails"):
            out.append(f"warning: {path}: the experiment names no guardrail; add `guardrails`, the metrics that must not get worse while it runs")
        if not data.get("hypothesis"):
            out.append(f"warning: {path}: the experiment has no hypothesis to decide; add the `hypothesis` its primary metric measures")
    tests = data.get("tests") or {}
    root = repo_root_of(path)
    # Once Spec approval holds (the check the guard and `aidd list` share), the test files are frozen: they must exist.
    if root is not None and _approval_holds(root, path, data):
        for f in tests.get("files", []):
            if not any(c in f for c in "*?[") and not (root / f.rstrip("/")).exists():
                out.append(f"warning: {path}: tests.files {f!r} does not exist, but Spec approval holds; Spec approval froze a test nobody wrote")
    known = {c.get("name") for c in tests.get("commands", [])} | _suite_names(root)
    for task in data.get("tasks", []):
        for m in _PROOF_COMMAND.finditer(task.get("proof", "")):
            name = m.group(1) or m.group(2)
            if name not in known:
                out.append(
                    f"warning: {path}: task {task['id']}: proof names test command {name!r}, which is neither in tests.commands nor the repository's `tests`"
                )
    return out


# Past these, a Spec is likely over its route's changed-line limit, which the gate checks only after Implement: split it before
# Spec approval, while splitting is cheap. A walking skeleton stays well under them (the mvp flow: three and six).
MAX_TASKS, MAX_ACCEPTANCE = 6, 12
# A Task that only reshapes code: a refactor is its own change, never part of a feature's Spec.
_REFACTOR_TASK = re.compile(r"^\s*(?:refactor|rename|move|extract|restructure|reorganize|clean ?up)\b", re.I)


# Git's convention for a commit subject: within 72 characters, so `git log --oneline` and every forge show it whole.
SUBJECT_CHARS = 72


# A Task's scope that lists this many files of one folder names the files, not the module (workitems.folder_scope).
FOLDER_FILES = 3


def size_warnings(path: Path, text: str, data: dict) -> list[str]:
    """A Spec that is likely too large to land as one change, a Task that lists the files of a folder instead of the
    folder, a refactor Task inside a feature Spec, and a title too long for the commit subject `aidd land` writes from
    it, as warnings `aidd validate` gives before Spec approval."""
    out = []
    subject = (f"{data['type']}: " if data.get("type") else "") + f"{data.get('title')} ({data.get('id')})"
    if data.get("title") and len(subject) > SUBJECT_CHARS:
        out.append(
            f"warning: {path}: `aidd land` writes the commit subject {subject!r}, {len(subject)} characters; shorten the title "
            f"so the subject keeps within {SUBJECT_CHARS}, as an imperative summary of the change"
        )
    tasks = [t for t in data.get("tasks") or [] if isinstance(t, dict)]
    n_acceptance = len(acceptance_ids(text))
    if len(tasks) > MAX_TASKS or n_acceptance > MAX_ACCEPTANCE:
        out.append(
            f"warning: {path}: {len(tasks)} Tasks and {n_acceptance} Acceptance items: likely over the changed-line limit the gate checks after "
            f"Implement. Split it into slices of at most {MAX_TASKS} Tasks and {MAX_ACCEPTANCE} Acceptance items before Spec approval, "
            "and move a specialist's further concern to a later slice"
        )
    for t in tasks:
        files = [g for g in t.get("scope") or [] if isinstance(g, str) and "/" in g and not g.endswith("/") and not any(c in g for c in "*?[")]
        for folder in sorted({f.rsplit("/", 1)[0] for f in files}):
            if (n := sum(1 for f in files if f.rsplit("/", 1)[0] == folder)) >= FOLDER_FILES:
                out.append(
                    f"warning: {path}: task {t.get('id')} lists {n} files in {folder}/: scope the folder (`{folder}/`) unless a "
                    "protected path or a risk rule matches them, so a file implementation adds beside them needs no new Spec approval"
                )
    if data.get("type") == "feat":
        for t in tasks:
            if _REFACTOR_TASK.match(str(t.get("title") or "")):
                out.append(
                    f"warning: {path}: task {t.get('id')} ({t.get('title')}) reshapes code inside a feature Spec. A refactor is its own "
                    "change: give it its own Spec or fast-lane change, before or after this one"
                )
    return out


def intent_and_conflict_warnings(path: Path, text: str, data: dict) -> list[str]:
    """Reminders for a normal or major Spec: the originator's words, and the conflicts only a human may settle.
    Warnings, never errors, and only from `aidd validate`: the gate never reads the Spec body's sections."""
    out = []
    if not markdown_section(text, "Intent"):
        quote = "quote the originator's problem, outcome, who is affected, constraints, and open questions before the design"
        out.append(f"warning: {path}: no '## Intent' section with content; {quote}")
    dims = (data.get("risk") or {}).get("dimensions") or []
    pools = {config.POOL_OF[d] for d in [*dims, data.get("type")] if d in config.POOL_OF}
    if (data.get("route") == "major" or len(pools) > 1) and not markdown_section(text, "Policy conflicts"):
        who = "list where specialist input, domain packs, or org policy disagree and who decides, or write 'none'"
        out.append(f"warning: {path}: no '## Policy conflicts' section with content; {who}")
    return out


# A line that states a target, or names what proves it: a number, inline code, a link, or a file path.
_MEASURABLE = re.compile(r"\d|`|\]\(|https?://|[\w.-]+/[\w./-]*\.\w+")
# Numbers that state no target: list numbering, an Acceptance id (A1, AC-1), and a work-item id (SPEC-4, EPIC-2).
_NOT_A_TARGET = re.compile(r"^[ \t]*(?:[-*|][ \t]*)?\d+[.)][ \t]|\bA[1-9][0-9]{0,3}\b|\b[A-Z][A-Z0-9]*-\d+\b")
# A Gherkin name line: it names the behavior, and its steps carry the target.
_GHERKIN_NAME = re.compile(r"^[ \t]*(?:Feature|Rule|Background|Scenario Outline|Scenario|Examples?)[ \t]*:", re.I)


@functools.cache
def _whole_words(words: tuple[str, ...]) -> re.Pattern[str]:
    """`words` as whole words in any case, the longest first; any run of spaces joins a phrase, a hyphen joins a word."""
    alternatives = "|".join(r"\s+".join(map(re.escape, w.split())) for w in sorted(words, key=len, reverse=True))
    return re.compile(rf"(?<![\w-])({alternatives})(?![\w-])", re.I)


def _vague_words() -> re.Pattern[str]:
    """The words in schemas/vague-words.json, as whole words."""
    return _whole_words(tuple(resources.load_json("vague-words.json")["words"]))


def vague_lines(text: str) -> list[tuple[str, str, list[str], str]]:
    """(section, Acceptance id or "", the vague words, the line) for each line of a Spec's Acceptance and
    Non-functional requirements sections that uses a vague word and states no target."""
    out = []
    for name in ("Acceptance", "Non-functional requirements"):
        item = ""
        for line in markdown_section(text, name, fences=False).splitlines():
            if m := ACCEPTANCE_ID.match(line):
                item = m.group(1)
            if _GHERKIN_NAME.match(line):
                continue
            words = list(dict.fromkeys(" ".join(w.group(1).lower().split()) for w in _vague_words().finditer(line)))
            if words and not _MEASURABLE.search(_NOT_A_TARGET.sub("", line)):
                out.append((name, item if name == "Acceptance" else "", words, line.strip()))
    return out


def vague_warnings(path: Path, text: str) -> list[str]:
    """A warning per vague line (`vague_lines`): never an error, and the gate never reads it."""
    out = []
    for name, item, words, line in vague_lines(text):
        where = f"Acceptance {item}" if item else f"a line of '## {name}'"
        shown = line if len(line) <= 60 else line[:59] + "…"
        out.append(
            f"warning: {path}: {where} says {', '.join(repr(w) for w in words)} with no number, unit, or test reference ({shown!r}); "
            'state a measurable target, such as "p95 under 300 ms" or "returns 429"'
        )
    return out


# The Spec sections a glossary's Avoid words are checked in. Intent quotes the originator's own words, so it is never one.
GLOSSARY_SECTIONS = ("Goals", "Acceptance", "Design")
# An Avoid entry longer than this is an explanation, not a word (a glossary written before the cell held only words).
_AVOID_MAX_WORDS = 3
_INLINE_CODE = re.compile(r"`[^`]*`")


# A performance budget's words: a percentile (p95, P99.9, the 99.9th percentile) or a Core Web Vitals name, then a
# number with its unit (200 ms, 2.5 s, 0.1 for CLS is unitless, so a vital takes any number).
_BUDGET = re.compile(r"\b[pP]\d{1,2}(?:\.\d+)?\b|\b\d{1,2}(?:\.\d+)?(?:st|nd|rd|th) percentile\b|\b(?:LCP|INP|CLS|TTFB)\b")
_BUDGET_NUMBER = re.compile(r"\b\d+(?:\.\d+)?\s*(?:ms|s|%|seconds?|milliseconds?)(?![\w])")
_VITAL_NUMBER = re.compile(r"\b(?:LCP|INP|CLS|TTFB)\b.*\b\d+(?:\.\d+)?\b")


def budget_warnings(path: Path, text: str, data: dict) -> list[str]:
    """A Spec whose risk names `performance`: a warning, never an error, until an Acceptance item states a budget (a
    percentile with a number) and a test command covers it, as the performance skill writes one."""
    if "performance" not in ((data.get("risk") or {}).get("dimensions") or []):
        return []
    budgets, item = [], ""
    for line in markdown_section(text, "Acceptance", fences=False).splitlines():
        if m := ACCEPTANCE_ID.match(line):
            item = m.group(1)
        bare = re.sub(r"`[^`]*`", "", ACCEPTANCE_ID.sub("", line, count=1))  # the item id and inline code are no number
        if item and _BUDGET.search(bare) and (_BUDGET_NUMBER.search(_BUDGET.sub("", bare)) or _VITAL_NUMBER.search(bare)):
            budgets.append(item)
    if not budgets:
        example = '"A3: p95 of GET /orders under 200 ms at 50 requests a second on staging"'
        return [
            f"warning: {path}: risk names performance, but no Acceptance item states a budget; add one with a percentile, a load, and an environment, such as {example} (aidd-team:performance)"
        ]
    commands = (data.get("tests") or {}).get("commands", []) or []
    covered = {i for c in commands if isinstance(c, dict) for i in c.get("covers") or []}
    if covered:
        return []  # coverage_warnings already names each Acceptance item no command covers
    return [
        f"warning: {path}: the performance budget {i} is covered by no test command; add the regression guard to tests.commands with covers: [{i}]"
        for i in dict.fromkeys(budgets)
        if i not in covered
    ]


def glossary_avoid(text: str) -> dict[str, str]:
    """{avoided word, in lower case: its term} from a glossary's table: each row's Avoid cell, split on commas. A
    placeholder, "none", an entry of more than three words, and any row's term are skipped; the first row wins."""
    rows: list[tuple[str, str]] = []
    header: list[str] | None = None
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if not {"term", "avoid"} <= set(header) or set("".join(cells)) <= set("-: ") or len(cells) < len(header):
            continue
        term, avoid = cells[header.index("term")], cells[header.index("avoid")]
        if term and "TODO" not in term and "TODO" not in avoid:
            rows.append((term, avoid))
    terms = {" ".join(t.lower().split()) for t, _ in rows}
    out: dict[str, str] = {}
    for term, avoid in rows:
        for entry in re.split(r"[,;]", avoid):
            word = " ".join(entry.strip().strip("`\"'*").lower().split())
            if word and word not in ("none", "-") and word not in terms and len(word.split()) <= _AVOID_MAX_WORDS:
                out.setdefault(word, term)
    return out


def glossary_lines(text: str, avoid: dict[str, str]) -> list[tuple[str, str, list[tuple[str, str]], str]]:
    """(section, Acceptance id or "", [(avoided word, its term)], the line) for each line of a Spec's Goals,
    Acceptance, and Design that uses a word the glossary's Avoid column names. Code, fenced or inline, is skipped."""
    if not avoid:
        return []
    pattern = _whole_words(tuple(sorted(avoid)))
    out = []
    for name in GLOSSARY_SECTIONS:
        item, fenced = "", False
        for line in markdown_section(text, name).splitlines():
            if line.lstrip().startswith("```"):
                fenced = not fenced
                continue
            if fenced:
                continue
            if m := ACCEPTANCE_ID.match(line):
                item = m.group(1)
            words = list(dict.fromkeys(" ".join(w.group(1).lower().split()) for w in pattern.finditer(_INLINE_CODE.sub("", line))))
            if words:
                out.append((name, item if name == "Acceptance" else "", [(w, avoid[w]) for w in words], line.strip()))
    return out


def glossary_warnings(path: Path, text: str, glossary: str, glossary_text: str) -> list[str]:
    """A warning per line that uses a word the repository glossary (`glossary`, its path) says to avoid
    (`glossary_lines`): never an error, and the gate never reads it."""
    out = []
    for name, item, found, line in glossary_lines(text, glossary_avoid(glossary_text)):
        where = f"Acceptance {item}" if item else f"a line of '## {name}'"
        shown = line if len(line) <= 60 else line[:59] + "…"
        words = ", ".join(f"{w!r} (the glossary's term is {term!r})" for w, term in found)
        out.append(
            f"warning: {path}: {where} uses {words}, which {glossary} lists under Avoid ({shown!r}); "
            "write the glossary's term, or change its row in the glossary if the word is right here"
        )
    return out


# A source behind a claim: a link, a file path, a quote, or a dated note (an ISO date, or a year and a month).
_SOURCE = re.compile(r"\]\(|https?://|`[^`]+`|[\w.-]+/[\w./-]*\.\w+|\"[^\"]{3,}\"|“[^”]{3,}”|\b\d{4}-\d{2}\b")
_PROBLEM_LINE = re.compile(r"^[ \t]*(?:[-*][ \t]+)?\**Problem\**[ \t]*:\**(.*)$", re.I)
_EVIDENCE = re.compile(r"\bEvidence[ \t]*:\**(.*)$", re.I)


def _sourced(claim: str) -> bool:
    """Whether a claim names its source, says it is assumed, or is still a template placeholder."""
    return not claim.strip() or "TODO" in claim or "(assumed)" in claim.lower() or bool(_SOURCE.search(claim))


def evidence_warnings(path: Path, text: str) -> list[str]:
    """An Initiative's Brief: its Problem line and its journey's Evidence each cite a source, or are marked "(assumed)".
    Warnings, never errors: an invented claim reads like a found one, and only its source tells them apart."""
    fix = 'add a link, a file path, a quote with its source, or a dated note, or mark it "(assumed)"'
    lines = markdown_section(text, "Brief").splitlines()
    claims = []
    for i, line in enumerate(lines):
        if m := _PROBLEM_LINE.match(line):
            wrapped = itertools.takewhile(lambda ln: ln[:1] in " \t" and not _PROBLEM_LINE.match(ln) and not ln.lstrip().startswith(("-", "*")), lines[i + 1 :])
            claims.append(("the Brief's Problem line", " ".join([m.group(1), *wrapped])))
        elif line.lstrip().startswith("|") and line.strip("| \t").lower().startswith("evidence"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")[1:]]
            claims += [("a journey Evidence cell", c) for c in cells]
        elif m := _EVIDENCE.search(line):
            claims.append(("the journey's Evidence", m.group(1)))
    return [f"warning: {path}: {where} cites no source; {fix}" for where, claim in claims if not _sourced(claim)]


def derived_statuses(root: Path, specs_dir: str, objects: list[tuple[str, dict]], texts: dict[str, str]) -> dict[str, str] | None:
    """The derived status of every work item, by id, as `aidd list` shows it; None when git cannot answer."""
    from aidd.workitems import derived_status

    work = [(p, d, texts.get(p, "")) for p, d in objects if d.get("kind") in backlog.WORK_KINDS]
    if not work:
        return {}
    try:
        return derived_status.Observer(root, repo_reads.config_at(root)).working_tree(specs_dir, work)
    except git.GitError:
        return None


def status_warnings(objects: list[tuple[str, dict]], derived: dict[str, str] | None) -> list[str]:
    """Where a stored status, a cache, disagrees with the status aidd derives (derived_statuses), and a done Epic or
    Initiative that still has an open child. Warnings: the derived status is what `aidd list` shows, and the gate reads
    neither."""
    from aidd.workitems import derived_status

    work = [(p, d) for p, d in objects if d.get("kind") in backlog.WORK_KINDS]
    if not work or derived is None:
        return []
    _, _, children = derived_status.container_statuses([d for _, d in work], derived)
    out = []
    for p, d in work:
        oid, stored = str(d.get("id")), derived_status.stored_status(d)
        now = derived.get(oid)
        if stored is None or now is None:
            continue
        if d.get("kind") == "spec" and stored != now:
            out.append(f"{p}: the stored status {stored} disagrees with the derived status {now}; aidd list shows {now}. Update the status or remove it")
        elif d.get("kind") != "spec" and stored in ("draft", "active") and stored != now:
            out.append(f"{p}: the stored status {stored} disagrees with the derived status {now} (from its children); update the status or remove it")
        if stored == "done" and d.get("kind") != "spec":
            open_ = [c for c in children.get(oid, []) if not derived_status.finished(derived.get(c, "draft"))]
            if open_:
                out.append(f"{p}: status done, but {', '.join(open_)} {'is' if len(open_) == 1 else 'are'} not finished; reopen it or finish them")
    return out
