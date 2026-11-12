"""What `aidd validate` warns about in a Spec, never a block: Acceptance no test covers, a plan and tests that
disagree, a word the glossary says to avoid, unsourced claims, a stale stored status, and what a landed Spec still owes.
"""

from __future__ import annotations

import datetime as dt
import functools
import itertools
import re
from pathlib import Path

from aidd import config
from aidd.kernel import command_names, documents, git, globs
from aidd.kernel.documents import markdown_section
from aidd.workitems import backlog, manifest_sections
from aidd.workitems import objects as workitems_objects
from aidd.workitems.spec_file import ACCEPTANCE_ID as ACCEPTANCE_ID
from aidd.workitems.spec_file import acceptance_ids
from aidd.workitems.status import ACCEPTANCE_DUE, PLACEHOLDER


def after_ship_warnings(path: Path, text: str, data: dict, today: dt.date | None = None) -> list[str]:
    """What a Spec owes once it is in review or merged, as warnings: the outcome of a hypothesis past its due date,
    and, with `manual_acceptance: true`, an acceptance record that lists every Acceptance id (a recorded `outcome.released_on` also
    says it shipped)."""
    from aidd.workitems import status as status_of

    status = status_of.spec_status(data)
    out = []
    due = status_of.outcome_due(data, status, today or dt.date.today())
    if due is not None:
        how = "met, missed, or inconclusive, with the number, in the Spec's `outcome.result`"
        out.append(f"warning: {path}: the hypothesis was due {due} and no outcome.result is recorded; record the outcome ({how})")
    released = bool((data.get("outcome") or {}).get("released_on"))
    ids = acceptance_ids(text)
    root = repo_root_of(path)
    if data.get("manual_acceptance") and ids and root is not None and (status in ACCEPTANCE_DUE or released):
        sid = data.get("id")
        files = [
            f
            for d in data.get("docs") or []
            if isinstance(d, dict) and d.get("type") == "acceptance"
            for f in workitems_objects.files_matching(root, str(d.get("path")))
        ]
        why = f"manual_acceptance: true and the Spec is {status if status in ACCEPTANCE_DUE else 'released'}"
        if not files:
            out.append(
                f"warning: {path}: {why}, but it links no acceptance record; `aidd new acceptance <topic> --spec {command_names.quoted(str(sid)) or '<ID>'}`, "
                "and a person records who accepted each Acceptance id before it merges"
            )
        else:
            listed = {i for f in files for i in ACCEPTANCE_ID.findall(workitems_objects.document_text(root, f))}
            missing = [i for i in ids if i not in listed]
            if missing:
                out.append(f"warning: {path}: {why}, but the acceptance record {', '.join(files)} does not list {', '.join(missing)}; add a row for each")
    return out


def coverage_warnings(path: Path, text: str, data: dict) -> list[str]:
    """Acceptance items no test command covers, and covered ids the Acceptance does not have, as warnings.
    Opt-in: only once a command declares `covers`, so a Spec with none stays quiet.
    It only shows the gaps."""
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


def open_question_warnings(path: Path, data: dict) -> list[str]:
    """Each open question a Spec still lists while it asks for approval (`ready`), as a warning: the person approves
    what is known, so each one is answered, or moved to the Spec's text as a known risk, and taken off the list."""
    from aidd.workitems import status

    if status.spec_status(data) not in status.ASKS_APPROVAL:
        return []
    return [
        f"warning: {path}: open question {documents.one_line(q, 200)!r} is still listed at the ask for Spec approval; "
        "answer it, or write it in the Spec's risk as a known unknown, and take it off open_questions"
        for q in data.get("open_questions") or []
        if isinstance(q, str) and q.strip()
    ]


def _approval_holds(data: dict) -> bool:
    """Whether the Spec is approved: its stored status is at or past approval."""
    from aidd.workitems import status

    return status.spec_status(data) in status.PAST_APPROVAL


def listed_files(path: Path, data: dict) -> list[str]:
    """The repository's files (tracked, and untracked but not ignored), read only when a Task's scope is a glob or a
    folder: what such a scope stands for. Empty outside a git checkout."""
    scopes = [s for task in data.get("tasks") or [] for s in task.get("scope") or [] if isinstance(s, str)]
    root = repo_root_of(path)
    if root is None or not (root / ".git").exists() or not any(globs.is_pattern(s) or s.endswith("/") for s in scopes):
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
        cfg = config.load_file(config.CONFIG_PATH, str(root), fetch=offline, skip_unread=True)
        return {t.get("name") for t in cfg.get("tests", default=[]) or []}
    except (config.ConfigError, documents.DocumentError, OSError):  # a parent out of reach: fall back to the file's own entries
        try:
            raw = documents.parse_yaml(workitems_objects.document_text(root, config.CONFIG_PATH), config.CONFIG_PATH)
        except (OSError, documents.DocumentError):
            return set()
        return {str(t.get("name")) for t in raw.get("tests", []) if isinstance(t, dict)}


def consistency_warnings(path: Path, data: dict) -> list[str]:
    """Where a Spec's plan and its tests disagree, as warnings: a frozen test file that is not on disk, and a Task
    proof naming a test command nobody defined. (A command that runs a file outside tests.files is a lint error.)"""
    out = []
    tests = data.get("tests") or {}
    root = repo_root_of(path)
    # Once Spec approval holds, the test files are frozen: they must exist.
    if root is not None and _approval_holds(data):
        for f in tests.get("files", []):
            on_disk = f.partition("#")[0]  # a frozen section (`pyproject.toml#tool.pytest`) is its manifest's
            if not globs.is_pattern(on_disk) and not (root / on_disk.rstrip("/")).exists():
                out.append(f"warning: {path}: tests.files {f!r} does not exist, but Spec approval holds; Spec approval froze a test nobody wrote")
    for f in tests.get("files", []) if root is not None else []:
        found = manifest_sections.frozen_section(f)
        if found and root is not None and found[0] not in workitems_objects.files_matching(root, found[0]):
            continue  # a manifest outside the repository is never read
        manifest = root / found[0] if found else None  # type: ignore[operator]
        if found and root is not None and manifest and manifest.is_file():
            value = manifest_sections.section_value(found[0], workitems_objects.document_text(root, found[0]), found[1])
            if value is None:
                out.append(f"warning: {path}: tests.files {f!r} names a section {found[0]} does not hold, so it freezes nothing; check the key")
    known = {c.get("name") for c in tests.get("commands", [])} | _suite_names(root)
    for task in data.get("tasks", []):
        for m in _PROOF_COMMAND.finditer(task.get("proof", "")):
            name = m.group(1) or m.group(2)
            if name not in known:
                out.append(
                    f"warning: {path}: task {task['id']}: proof names test command {name!r}, which is neither in tests.commands nor the repository's `tests`"
                )
    return out


# Past these, a Spec is likely too large to review as one change: split it before
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
    folder, a refactor Task inside a feature Spec, and a title too long for the commit subject written from
    it, as warnings `aidd validate` gives before Spec approval."""
    out = []
    subject = (f"{data['change_type']}: " if data.get("change_type") else "") + f"{data.get('title')} ({data.get('id')})"
    if data.get("title") and len(subject) > SUBJECT_CHARS:
        out.append(
            f"warning: {path}: the commit subject would be {subject!r}, {len(subject)} characters; shorten the title "
            f"so the subject keeps within {SUBJECT_CHARS}, as an imperative summary of the change"
        )
    tasks = [t for t in data.get("tasks") or [] if isinstance(t, dict)]
    n_acceptance = len(acceptance_ids(text))
    if len(tasks) > MAX_TASKS or n_acceptance > MAX_ACCEPTANCE:
        out.append(
            f"warning: {path}: {len(tasks)} Tasks and {n_acceptance} Acceptance items: likely too large to review as one change. "
            f"Split it into slices of at most {MAX_TASKS} Tasks and {MAX_ACCEPTANCE} Acceptance items before Spec approval, "
            "and move a specialist's further concern to a later slice"
        )
    for t in tasks:
        files = [g for g in t.get("scope") or [] if isinstance(g, str) and "/" in g and not g.endswith("/") and not globs.is_pattern(g)]
        for folder in sorted({f.rsplit("/", 1)[0] for f in files}):
            if (n := sum(1 for f in files if f.rsplit("/", 1)[0] == folder)) >= FOLDER_FILES:
                out.append(
                    f"warning: {path}: task {t.get('id')} lists {n} files in {folder}/: scope the folder (`{folder}/`) unless a "
                    "path in an area or a risk rule matches them, so a file implementation adds beside them needs no new Spec approval"
                )
    if data.get("change_type") == "feat":
        for t in tasks:
            if _REFACTOR_TASK.match(str(t.get("title") or "")):
                out.append(
                    f"warning: {path}: task {t.get('id')} ({t.get('title')}) reshapes code inside a feature Spec. A refactor is its own "
                    "change: give it its own Spec or change with no Spec, before or after this one"
                )
    return out


def intent_and_conflict_warnings(path: Path, text: str, data: dict) -> list[str]:
    """Reminders for a normal or major Spec: the person's request, quoted, and the conflicts only a human may settle.
    Warnings, never errors, and only from `aidd validate`: no other check reads the Spec body's sections."""
    out = []
    if not markdown_section(text, "Request"):
        quote = (
            "quote the person's request, their own words: the problem, the outcome, who is affected, the constraints, and the open questions, before the design"
        )
        out.append(f"warning: {path}: no '## Request' section with content; {quote}")
    dims = (data.get("risk") or {}).get("dimensions") or []
    pools = {config.POOL_OF[d] for d in dims if d in config.POOL_OF}
    if (data.get("route") == "major" or len(pools) > 1) and not markdown_section(text, "Policy conflicts"):
        who = "list where specialist input, domain packs, or org policy disagree and who decides, or write 'none'"
        out.append(f"warning: {path}: no '## Policy conflicts' section with content; {who}")
    return out


@functools.cache
def _whole_words(words: tuple[str, ...]) -> re.Pattern[str]:
    """`words` as whole words in any case, the longest first; any run of spaces joins a phrase, a hyphen joins a word."""
    alternatives = "|".join(r"\s+".join(map(re.escape, w.split())) for w in sorted(words, key=len, reverse=True))
    return re.compile(rf"(?<![\w-])({alternatives})(?![\w-])", re.I)


# The Spec sections a glossary's Avoid words are checked in. Request quotes the person's own words, so it is never one.
GLOSSARY_SECTIONS = ("Goals", "Acceptance", "Design")
# An Avoid entry longer than this is an explanation, not a word.
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
        if term and PLACEHOLDER not in term and PLACEHOLDER not in avoid:
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
    (`glossary_lines`): never an error, and no other check reads it."""
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
    return not claim.strip() or PLACEHOLDER in claim or "(assumed)" in claim.lower() or bool(_SOURCE.search(claim))


def evidence_warnings(path: Path, text: str) -> list[str]:
    """An Intent's Problem section: its Problem line and its Evidence each cite a source, or are marked "(assumed)".
    Warnings, never errors: an invented claim reads like a found one, and only its source tells them apart."""
    fix = 'add a link, a file path, a quote with its source, or a dated note, or mark it "(assumed)"'
    lines = markdown_section(text, "Problem").splitlines()
    claims = []
    for i, line in enumerate(lines):
        if m := _PROBLEM_LINE.match(line):
            wrapped = itertools.takewhile(lambda ln: ln[:1] in " \t" and not _PROBLEM_LINE.match(ln) and not ln.lstrip().startswith(("-", "*")), lines[i + 1 :])
            claims.append(("the Problem line", " ".join([m.group(1), *wrapped])))
        elif line.lstrip().startswith("|") and line.strip("| \t").lower().startswith("evidence"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")[1:]]
            claims += [("a journey Evidence cell", c) for c in cells]
        elif m := _EVIDENCE.search(line):
            claims.append(("the journey's Evidence", m.group(1)))
    return [f"warning: {path}: {where} cites no source; {fix}" for where, claim in claims if not _sourced(claim)]


def statuses(objects: list[tuple[str, dict]]) -> dict[str, str]:
    """Every work item's status, by id, as `aidd status` shows it: each Spec's stored status, each slice's with no Spec
    file from its line, and each Intent's from its children's."""
    from aidd.workitems import intents, status

    work = [d for _, d in objects if d.get("type") in backlog.WORK_TYPES]
    specs = {str(d.get("id")): status.spec_status(d) for d in work if d.get("type") == "spec"}
    return intents.intent_statuses(work, specs)[0]


def status_warnings(objects: list[tuple[str, dict]], derived: dict[str, str] | None) -> list[str]:
    """A done Intent that still has an open child, and an approved Spec with no `approved_by`."""
    from aidd.workitems import intents, status

    work = [(p, d) for p, d in objects if d.get("type") in backlog.WORK_TYPES]
    if not work or derived is None:
        return []
    _, _, children = intents.intent_statuses([d for _, d in work], derived)
    out = []
    for p, d in work:
        oid, stored = str(d.get("id")), status.stored_status(d)
        if d.get("type") == "spec" and stored in status.PAST_APPROVAL and not d.get("approved_by") and d.get("route") in config.SPEC_FIRST_ROUTES:
            out.append(
                f"{p}: status {stored}, but no approved_by says who approved it; on the person's yes, the agent writes them as `Name <email>` or `@handle`, the form the aidd skill's `references/spec.md` gives"
            )
        if stored in status.INTENT_NEEDS_FINISHED_CHILDREN and d.get("type") == "intent":
            open_ = [c for c in children.get(oid, []) if not status.finished(derived.get(c, "draft"))]
            if open_:
                out.append(f"{p}: status done, but {', '.join(open_)} {'is' if len(open_) == 1 else 'are'} not finished; reopen it or finish them")
    return out
