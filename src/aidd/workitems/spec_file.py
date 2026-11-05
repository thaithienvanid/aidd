"""Spec files and the other work items: loading and linting them, the Specs a diff changes, their frozen paths, the next free id, and the proposal hash."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aidd import config
from aidd.kernel import documents, git, globs, json_schema, retired_names
from aidd.workitems import intents, objects, old_shape
from aidd.workitems.manifest_sections import frozen_section, section_changed, section_problem

# The body sections a normal or major Spec needs, each satisfied by any of its names: the why (the full template's
# Context, or the short template's Request, the person's own words) and the Acceptance.
REQUIRED_SECTIONS = (("context", "request"), ("acceptance",))


# The schema that checks each object `load_object` reads: a work item or a typed document with a schema of its own, that is
# not an exploration, whose own reader checks it (schemas/item-types.json).
OBJECT_SCHEMAS = {
    t: config.item_type_rows()[t]["schema"] for t in objects.OBJECT_TYPES if "schema" in config.item_type_rows()[t] and t not in objects.DOCUMENT_TYPES
}

# A proposal's status says which human decisions must already be on record: the sets of its status table (`x-sets`).
PROPOSAL_OUTCOMES = config.status_set("proposal", "recorded_outcome")
PROPOSAL_NEEDS_GO = config.status_set("proposal", "needs_go")
PROPOSAL_NEEDS_SIGN_OFF = config.status_set("proposal", "needs_sign_off")


def proposal_status(proposal: dict) -> str:
    """A proposal's derived status: the recorded outcome, else what go_no_go and sign_off say."""
    outcome = (proposal.get("outcome") or {}).get("decision")
    if outcome in PROPOSAL_OUTCOMES:
        return str(outcome)
    go = (proposal.get("go_no_go") or {}).get("decision")
    if go == "no_go":
        return "no_go"
    if go == "go":
        return "signed_off" if proposal.get("sign_off") else "drafting"
    return "qualifying"


def load_object(text: str, what: str, *, read_old_shape: bool = False) -> tuple[dict, str, list[str]]:
    """Parse and schema-check a Spec, Intent, Proposal, runbook, or postmortem file. With `read_old_shape`, one in an earlier shape
    is read as today's first (`old_shape`): for a commit before an upgrade, never for the head."""
    bad = documents.control_characters(text)
    if bad:
        return {}, "", [f"{what}: {bad}; a Spec is plain text, and hidden bytes could change what the approver reads"]
    data, body = documents.split_front_matter(text, what)
    if read_old_shape:
        try:
            data = old_shape.todays_shape(data)
        except retired_names.Refused as exc:  # the upgrade leaves it for a person, so the reader does not guess either
            return data, body, [f"{what}: {exc}. `aidd upgrade --yes` names the step, and a person makes it"]
    item_type = str(data.get("type"))
    schema_name = OBJECT_SCHEMAS.get(item_type)
    if schema_name is None:
        return data, body, [f"{what}: type must be {', '.join(OBJECT_SCHEMAS)}"]
    errors = [f"{what}: {old_shape.explained(item_type, e, data)}" for e in json_schema.validate(data, schema_name)]
    if item_type == "spec" and not errors:
        errors += [f"{what}: {e}" for e in lint_spec(data, body)]
    if item_type == "proposal" and not errors:
        errors += [f"warning: {what}: {e[9:]}" if e.startswith("warning: ") else f"{what}: {e}" for e in lint_proposal(data)]
    if item_type == "intent" and not errors:
        errors += [f"{what}: {e}" for e in lint_decisions(data.get("decisions") or [])]
    return data, body, errors


def sections(body: str) -> set[str]:
    return {m.group(1).strip().lower() for m in re.finditer(r"^#{1,3}[ \t]+(.+?)[ \t]*#*$", body, re.M)}


def _unique_ids(field: str, items: list[dict]) -> list[str]:
    ids = [x["id"] for x in items]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    return [f"{field}: ids must be unique ({', '.join(dupes)})"] if dupes else []


# A claim seen only in simulation must not say it holds everywhere. Whole words, any case; a hyphen joins a word
# ("same-day", "all-in", "always-on" are not absolute).
ABSOLUTE_WORDS = re.compile(r"(?<![\w-])(every\w*|always|never|same|already works|all|none|guaranteed|100%)(?![\w-])", re.I)


def lint_estimate(est: dict) -> list[str]:
    """The total's range in order; each part's range in order; and the parts' PERT roll-up inside the total's range."""
    errs: list[str] = []
    if not est["low"] <= est["likely"] <= est["high"]:
        errs.append("estimate: low <= likely <= high must hold")
    parts = est.get("parts") or []
    errs += _unique_ids("estimate.parts", parts)
    for part in parts:
        if not part["low"] <= part["likely"] <= part["high"]:
            errs.append(
                f"estimate.parts {part['id']}: low <= likely <= high must hold (low {documents.fmt_number(part['low'])}, likely {documents.fmt_number(part['likely'])}, high {documents.fmt_number(part['high'])})"
            )
    if parts:
        rollup = sum((x["low"] + 4 * x["likely"] + x["high"]) / 6 for x in parts)
        # Floating-point error grows with the numbers: allow a tolerance relative to the range, not a fixed one.
        tol = 1e-9 * max(1.0, abs(est["low"]), abs(est["high"]))
        if not est["low"] - tol <= rollup <= est["high"] + tol:
            errs.append(
                f"estimate.parts: the PERT roll-up of the parts is {documents.fmt_number(rollup)} {est['unit']}, outside the total's range of "
                f"{documents.fmt_number(est['low'])} to {documents.fmt_number(est['high'])}; fix the parts or the range"
            )
    return errs


def lint_claims(claims: list[dict]) -> list[str]:
    """Unique ids; a warning for a claim with no basis, and for an absolute word in a claim seen only in simulation."""
    errs = _unique_ids("claims", claims)
    for c in claims:
        if not c.get("basis"):
            errs.append(f"warning: claims {c['id']} has no basis; add a file:line, a test, or a recording, or take the claim out")
        word = ABSOLUTE_WORDS.search(c["text"])
        if word and c["scope"] == "simulated":
            errs.append(
                f'warning: claims {c["id"]} says "{word.group(0)}" but was seen only in simulation; '
                "narrow the words, or add evidence from a real device or production"
            )
    return errs


def lint_decisions(decisions: list[dict]) -> list[str]:
    """Unique ids, and each `replaces` names an earlier entry of the same log, dated on or before it."""
    errs = _unique_ids("decisions", decisions)
    seen: dict[str, Any] = {}
    for d in decisions:
        old = d.get("replaces")
        if old is not None and old not in seen:
            errs.append(f"decisions {d['id']} replaces {old}, which is not an earlier entry of the log")
        elif old is not None and str(d["decided_on"]) < str(seen[old]):
            errs.append(f"decisions {d['id']} replaces {old} but is dated {d['decided_on']}, before {old} ({seen[old]})")
        seen[d["id"]] = d["decided_on"]
    return errs


def lint_proposal(proposal: dict) -> list[str]:
    """Rules a schema cannot express: unique ids, consistent ranges, the claims and the decisions logs, and the
    decisions the status claims."""
    errs: list[str] = []
    for field in ("needs", "options", "risks", "questions"):
        errs += _unique_ids(field, proposal.get(field, []))
    if proposal.get("estimate"):
        errs += lint_estimate(proposal["estimate"])
    errs += lint_claims(proposal.get("claims") or [])
    errs += lint_decisions(proposal.get("decisions") or [])
    if len([o for o in proposal.get("options", []) if o.get("recommended")]) > 1:
        errs.append("options: recommend one option at most")
    go, derived = (proposal.get("go_no_go") or {}).get("decision"), proposal_status(proposal)
    outcome = (proposal.get("outcome") or {}).get("decision")
    if outcome in PROPOSAL_OUTCOMES & PROPOSAL_NEEDS_SIGN_OFF:  # an outcome that is sent, and so signed off
        if go != "go":
            errs.append(f'outcome {outcome} needs go_no_go.decision: "go": a person decides to pursue it before the team drafts')
        if not proposal.get("sign_off"):
            errs.append(f"outcome {outcome} needs sign_off: a person signs the proposal off before it is sent")
        if not proposal.get("needs"):
            errs.append(f"outcome {outcome} needs the needs it answers")
    status = proposal.get("status")
    if status is None or status == derived:
        return errs
    # The stored status is a cache. One the decisions do not support claims a decision nobody recorded: an error.
    if status == "no_go" and go != "no_go":
        errs.append('status no_go needs go_no_go.decision: "no_go", with who decided and when')
    elif status in PROPOSAL_NEEDS_GO and go != "go":
        errs.append(f'status {status} needs go_no_go.decision: "go": a person decides to pursue it before the team drafts')
    elif status in PROPOSAL_NEEDS_SIGN_OFF and not proposal.get("sign_off"):
        errs.append(f"status {status} needs sign_off: a person signs the proposal off before it is sent")
    elif status in PROPOSAL_OUTCOMES and outcome != status:
        errs.append(f'status {status} needs `outcome: {{decision: {status}, by: "@you", decided_on: YYYY-MM-DD}}`: a person records it')
    else:
        errs.append(f"warning: status {status} is behind the recorded decisions, which make it {derived}; update or remove it")
    return errs


def lint_spec(spec: dict, body: str) -> list[str]:
    """Rules a schema cannot express."""
    errs: list[str] = []
    tasks = spec.get("tasks", [])
    ids = [t["id"] for t in tasks]
    if len(ids) != len(set(ids)):
        errs.append("task ids must be unique")
    known = set(ids)
    test_files = (spec.get("tests") or {}).get("files", [])
    design_files = (spec.get("design") or {}).get("files", [])
    docs = frozen_docs(spec)
    for t in tasks:
        for dep in t.get("depends_on", []):
            if dep not in known and ":" not in dep:
                errs.append(f"task {t['id']}: depends_on {dep!r} is not a task in this Spec (cross-team ids use team:ID)")
        for pattern in t["scope"]:
            if globs.is_catch_all(pattern):
                errs.append(f"task {t['id']}: scope {pattern!r} matches every path; name the directories the Task changes")
            for files, what, why in (
                (test_files, "test file", "acceptance tests are frozen at Spec approval; narrow the scope to the unit-test folder, such as tests/unit/"),
                (design_files, "design file", "the design is frozen at Spec approval and is not implementation scope"),
                (docs, "frozen doc", "it is approved with the Spec and is not implementation scope (set frozen: false for a living doc a Task changes)"),
            ):
                errs += [f"task {t['id']}: scope {pattern!r} overlaps {what} {f!r}; {why}" for f in files if globs.overlap(pattern, f)]
    for tf in test_files:
        if globs.is_catch_all(tf):
            errs.append(f"tests.files {tf!r} matches every path; name the test files or directories")
        if problem := section_problem(tf):
            errs.append(problem)
    for df in design_files:
        if globs.is_catch_all(df):
            errs.append(f"design.files {df!r} matches every path; name the design folder")
    for d in spec.get("docs", []):
        if globs.is_catch_all(d["path"]):
            errs.append(f"docs {d['path']!r} matches every path; name the document")
    for tc in (spec.get("tests") or {}).get("commands", []):
        for tok in _path_literals(tc.get("command", [])):
            if not globs.match_any(test_files, tok):
                errs.append(f"tests.commands {tc.get('name', '')!r}: command runs {tok!r} which is not covered by tests.files")
    order = _dependency_order(tasks)
    if order is None:
        errs.append("tasks: depends_on has a cycle")
    else:
        for i, a in enumerate(tasks):
            for b in tasks[i + 1 :]:
                if any(globs.overlap(x, y) for x in a["scope"] for y in b["scope"]):
                    if not (_reaches(tasks, a["id"], b["id"]) or _reaches(tasks, b["id"], a["id"])):
                        errs.append(f"tasks {a['id']} and {b['id']}: scope overlaps, so one must depend_on the other")
    if spec.get("route") in config.SPEC_FIRST_ROUTES:
        have = sections(body)
        for names in REQUIRED_SECTIONS:
            if not any(n in have for n in names):
                errs.append("body: missing " + " or ".join(f"'## {n.title()}'" for n in names) + " section")
    if spec.get("confidence") == "low":
        errs.append("confidence is low: stop and answer the open_questions before Specify")
    return errs


def _dependency_order(tasks: list[dict]) -> list[str] | None:
    deps = {t["id"]: [d for d in t.get("depends_on", []) if ":" not in d] for t in tasks}
    seen: dict[str, int] = {}
    out: list[str] = []

    def visit(name: str) -> bool:
        if seen.get(name) == 1:
            return False
        if seen.get(name) == 2:
            return True
        seen[name] = 1
        for d in deps.get(name, []):
            if d in deps and not visit(d):
                return False
        seen[name] = 2
        out.append(name)
        return True

    return out if all(visit(n) for n in deps) else None


def _reaches(tasks: list[dict], src: str, dst: str) -> bool:
    deps = {t["id"]: t.get("depends_on", []) for t in tasks}
    stack, seen = [src], set()
    while stack:
        n = stack.pop()
        if n == dst and n != src:
            return True
        if n in seen:
            continue
        seen.add(n)
        stack.extend(deps.get(n, []))
    return False


def find_specs_in_diff(files: list[dict], specs_dir: str, head_files_reader) -> list[str]:
    """Every Spec a diff adds or changes, in path order: the Markdown files under `specs_dir` whose head type is spec,
    a saved request left out, since it is never a work item whatever its text says. A work item that does not parse is
    `unparsable_work_items`', which `aidd validate` reports first."""
    specs = []
    folder = globs.under(specs_dir, "")
    changed = (f["path"] for f in files if f["path"].startswith(folder) and f["path"].endswith(".md"))
    for p in sorted(p for p in changed if not objects.is_saved_request(p, specs_dir.rstrip("/"))):
        text = head_files_reader(p)
        try:
            if text is not None and documents.split_front_matter(text, p)[0].get("type") == "spec":
                specs.append(p)
        except (documents.DocumentError, RecursionError):
            continue
    return specs


def tests_files(patterns: list[str], tree: dict[str, str]) -> list[str]:
    return sorted(p for p in tree if globs.match_any(patterns, p))


_WINDOWS_DRIVE = re.compile(r"[A-Za-z]:[\\/]")


# The extensions of a script a test command runs from the repository's top, with no folder in its name (`test.sh`).
SCRIPT_EXTENSIONS = (".sh", ".bash", ".zsh", ".ps1", ".py", ".js", ".mjs", ".cjs", ".ts", ".mts", ".rb", ".pl")


def _path_literals(cmd: object) -> list[str]:
    """The relative file paths a test command's argument list names literally, the files its tests run through: a
    token with a "/" and a file extension (`tests/test_x.py`, a pytest node id read as its file), a script at the top
    with a script's extension (`test.sh`, `run_tests.py`), and the program itself when it is a relative path
    (`scripts/run-tests`, `./test`). A leading `./` is dropped. A program on PATH (`pytest`), a folder, and an absolute
    path (`/usr/bin/python3`, `C:/Python311/python.exe`), which is outside the repository, are never one."""
    if not isinstance(cmd, list):
        return []
    out = []
    for i, tok in enumerate(cmd):
        if not isinstance(tok, str) or tok.startswith(("-", "/", "\\")) or _WINDOWS_DRIVE.match(tok):
            continue
        path = tok.split("::", 1)[0]
        while path.startswith("./"):
            path = path[2:]
        if not path or any(c in path for c in " >|<;&*?["):
            continue
        name = path.rsplit("/", 1)[-1]
        has_extension = "." in name and not name.startswith(".")
        program = i == 0 and (tok.startswith("./") or "/" in path)
        top_script = "/" not in path and has_extension and name.endswith(SCRIPT_EXTENSIONS)
        if ("/" in path and has_extension) or program or top_script:
            out.append(path)
    return out


def command_path_literals(spec: dict) -> list[str]:
    return [p for tc in (spec.get("tests") or {}).get("commands", []) for p in _path_literals(tc.get("command", []))]


def frozen_docs(spec: dict) -> list[str]:
    """The paths of the Spec's frozen `docs` (frozen unless it says `frozen: false`)."""
    return [d["path"] for d in spec.get("docs") or [] if isinstance(d, dict) and isinstance(d.get("path"), str) and d.get("frozen", True) is not False]


# Where a component's living threat model lives, under the docs folder: one file per component, never per Spec.
THREAT_MODELS = "security/threat-models"
# Where a component's living test plan lives, under the docs folder: one file per component, which each Spec's own plan feeds.
TEST_PLANS = "testing/test-plans"
_THREAT_MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.md")


def threat_models(spec: dict, docs_dir: str) -> list[str]:
    """The living threat models the Spec links (`type: threat-model`, `frozen: false`): each one plain file in
    `<docs_dir>/security/threat-models/`, the component's model that outlives each Spec. Its delta is frozen in the
    Spec's Design; the file itself is documentation, never implementation, so it may change
    before and after Spec approval and Merge approval reviews it. Any other path a Spec links as a living threat
    model counts as nothing here, so a link never widens the scope."""
    home = f"{docs_dir.strip('/')}/{THREAT_MODELS}/"
    return [
        d["path"]
        for d in spec.get("docs") or []
        if isinstance(d, dict)
        and d.get("type") == "threat-model"
        and d.get("frozen", True) is False
        and isinstance(d.get("path"), str)
        and d["path"].startswith(home)
        and _THREAT_MODEL_NAME.fullmatch(d["path"][len(home) :])
    ]


def design_paths(spec: dict) -> list[str]:
    """The files approved with the Spec that are neither tests nor implementation: its design files and its frozen
    docs. The runner and the hash treat each one alike."""
    return list(dict.fromkeys(list((spec.get("design") or {}).get("files", [])) + frozen_docs(spec)))


def frozen_paths(spec: dict) -> list[str]:
    """What Spec approval freezes besides the Spec file: the test files, the design files, the frozen docs, and
    literal test paths."""
    files = list((spec.get("tests") or {}).get("files", []))
    return list(dict.fromkeys(files + design_paths(spec) + command_path_literals(spec)))


def frozen_files(spec: dict) -> list[str]:
    """frozen_paths as files and globs on disk: a frozen section (`pyproject.toml#tool.pytest`) is its manifest, so a
    worktree hash, a dirty check, or the history reads the file the section lives in."""
    return list(dict.fromkeys(e.partition("#")[0] for e in frozen_paths(spec)))


def frozen_change(spec: dict, path: str, texts: Callable[[str], tuple[str | None, str | None]]) -> bool:
    """Whether a change to the bytes of `path` changes what `spec` froze: the whole file when an entry other than a section names
    it, else the value of each section of it the Spec froze (`pyproject.toml#tool.pytest`), so a dependency bump in the same
    manifest changes nothing frozen. A whole-file entry wins over a section of the same file. `texts` gives the file's text on
    each side, None where it is not there; a section that cannot be read on either side counts as changed."""
    entries = frozen_paths(spec)
    if globs.match_any([e for e in entries if "#" not in e], path):
        return True
    keys = [found[1] for e in entries if (found := frozen_section(e)) and found[0] == path]
    if not keys:
        return False
    before, after = texts(path)
    return any(section_changed(path, key, before, after) for key in keys)


# The id each work item type is numbered under: `aidd new spec "Title"` takes the next SPEC-<n>.
ID_PREFIXES = {t: config.item_type_rows()[t]["id_prefix"] for t in config.types_with("id_prefix")}
# A work item's id as aidd writes one (`SPEC-1`, `PROP-3`).
WORK_ID = re.compile(r"[A-Za-z][A-Za-z0-9]*-[0-9]+")


def next_id(root: Path | str, prefix: str, folder: str) -> str:
    """<prefix>-<n>, one past the highest <prefix>-<n> in `folder`, in the working tree or on any local branch, so two
    branches started apart never take the same id. A file (`SPEC-3.md`) or a folder (`PROP-2/`) counts."""
    named = re.compile(rf"{re.escape(prefix)}-(\d+)(?:\.md)?")
    where = Path(root) / folder
    names = {p.name for p in where.iterdir()} if where.is_dir() else set()
    for ref in git.run(["for-each-ref", "--format=%(refname)", "refs/heads"], str(root), check=False).split():
        listed = git.run(["ls-tree", "--name-only", ref, "--", f"{folder.rstrip('/')}/"], str(root), check=False)
        names |= {line.rsplit("/", 1)[-1] for line in listed.splitlines()}
    names |= set(_slice_ids(Path(root), folder))  # a slice is a Spec to be, so its id is taken
    nums = [int(m.group(1)) for name in names if (m := named.fullmatch(name))]
    return f"{prefix}-{max(nums, default=0) + 1}"


def _slice_ids(root: Path, folder: str) -> list[str]:
    """Every slice id the Intents in `folder` list, in the working tree."""
    found: list[str] = []
    for path in objects.object_files(root, folder):
        if objects.front_type(path) == "intent":
            try:
                data, _ = documents.split_front_matter(objects.document_text(root, path.relative_to(root).as_posix()), path.as_posix())
            except documents.DocumentError:
                continue
            found += intents.slice_ids(data)
    return found


# The decisions a person records about a proposal at or after its sign-off, and the scope decisions log: the proposal
# hash leaves them out, so recording them never changes what was signed off.
PROPOSAL_UNSIGNED_KEYS = frozenset({"sign_off", "outcome", "status", "decisions"})
# The living fields: the bookkeeping the schema says people fill in over time, after sign-off too, which the proposal
# hash leaves out. Each list of the front matter, and the keys of its items that the hash leaves out.
PROPOSAL_LIVING_FIELDS: dict[str, tuple[str, ...]] = {
    "questions": ("answer",),
    "risks": ("status",),
    "assumptions": ("status",),
    "issues": ("status",),
    "dependencies": ("status",),
    "phases": ("finished_on", "invoice_ref"),
    "needs": ("phase",),
}


def proposal_hash(text: str) -> str:
    """Hash of what a person signs off in a proposal: the whole body and the front matter, except these.

    - The decisions, PROPOSAL_UNSIGNED_KEYS: `sign_off`, `outcome`, `status`, and the scope decisions log, `decisions`.
    - The living fields, PROPOSAL_LIVING_FIELDS: each question's `answer`, each RAID item's `status`, each phase's
      `finished_on` and `invoice_ref`, and each need's `phase`.

    It is one canonical JSON document, then the first 128 bits of its SHA-256, in hex. YAML
    comments, key order, and CRLF line endings change nothing. Any other change to the needs, the estimate and its parts,
    the price, the exclusions, the claims, the RAID log, or the body does. It keeps `aidd-handoff` blocks: a block in a
    proposal could hold terms that the sign-off must bind.
    """
    data, body = documents.split_front_matter(text.replace("\r\n", "\n"), "proposal")
    front: dict[str, Any] = {k: v for k, v in data.items() if k not in PROPOSAL_UNSIGNED_KEYS}
    for key, living in PROPOSAL_LIVING_FIELDS.items():
        if isinstance(front.get(key), list):
            front[key] = [{k: v for k, v in item.items() if k not in living} if isinstance(item, dict) else item for item in front[key]]
    payload = {"front": front, "body": body.strip()}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:32]


# An Acceptance item's id (A1, A2, ...), where the item starts: at the head of a line, a list item, or a table row,
# or right after a Gherkin keyword such as `Scenario:`.
ACCEPTANCE_ID = re.compile(r"^[ \t]*(?:[-*|#]+[ \t]*)?\**(?:(?:Scenario Outline|Scenario|Example|Rule)[ \t]*:[ \t]*)?\**(A[1-9][0-9]{0,3})\b", re.M)


def acceptance_ids(text: str) -> list[str]:
    """The ids of the Acceptance items in a Spec's body, in order of first appearance."""
    return list(dict.fromkeys(ACCEPTANCE_ID.findall(documents.markdown_section(text, "Acceptance"))))
