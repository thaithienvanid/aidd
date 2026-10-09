"""Spec files, Change Request blocks, and the Spec hash."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import tomllib
from typing import Any

from . import globs, schema

FRONT_MATTER = re.compile(r"\A\+\+\+[ \t]*\r?\n(.*?)\r?\n\+\+\+[ \t]*(?:\r?\n|\Z)", re.S)
# Bookkeeping a person or an agent updates after Spec approval: never part of the Spec hash. The skill's hard
# rule 2 and references/loop.md name the same keys (tests/test_workitems.py checks it).
VOLATILE_SPEC_KEYS = {"status", "blocked_on", "outcome", "labels", "relations", "triage", "priority", "owner", "assisted_by"}
# A handoff note in a Spec's body (```aidd-handoff ... ```): a report between roles, written after Spec approval as
# often as before it, so it never voids one. Only a closed fence with exactly this info string is left out
# (`strip_handoffs`): an opening line of exactly that fence, and the first later line of exactly three backticks.
_HANDOFF_OPEN = re.compile(r"```aidd-handoff[ \t]*\r?")
_FENCE_CLOSE = re.compile(r"```[ \t]*")
# The most a Spec, Epic, Initiative, Proposal, or linked object file may hold, front matter and body together. A person
# reads and approves all of it; a file far past this is not something anyone reads.
MAX_DOCUMENT_BYTES = 256 * 1024
# The deepest nesting of tables and arrays a TOML document may have: far past any real config or Spec, and far short
# of the depth at which the parser, or any reader walking the result, runs out of stack.
MAX_TOML_DEPTH = 32
VOLATILE_TASK_KEYS = {"retry_count", "done"}
# The body sections a normal or major Spec needs, each satisfied by any of its names: the why (the full template's
# Context, or the short template's Intent, the originator's words) and the Acceptance.
REQUIRED_SECTIONS = (("context", "intent"), ("acceptance",))
# What an inline Change Request block (minor, standard, emergency) means when it leaves a field out.
INLINE_DEFAULTS = {"type": "chore", "confidence": "high", "rollback": "Revert the change.", "residual_risk": "none"}


class ModelError(ValueError):
    pass


def normalize(value: Any) -> Any:
    """TOML dates become ISO strings so records stay JSON-shaped."""
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    if isinstance(value, (_dt.date, _dt.datetime, _dt.time)):
        return value.isoformat()
    return value


def _depth(value: Any) -> int:
    """How deeply tables and arrays nest in a parsed document, walked without recursion."""
    deepest, stack = 0, [(value, 0)]
    while stack:
        v, d = stack.pop()
        if isinstance(v, dict):
            stack.extend((x, d + 1) for x in v.values())
        elif isinstance(v, list):
            stack.extend((x, d + 1) for x in v)
        else:
            continue
        deepest = max(deepest, d + 1)
        if deepest > MAX_TOML_DEPTH:
            break
    return deepest


def parse_toml(text: str, what: str) -> dict:
    """A TOML document as JSON-shaped data. Invalid TOML, and nesting deeper than MAX_TOML_DEPTH (which would exhaust
    the parser's stack), are a ModelError naming `what`, never a crash."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ModelError(f"{what}: invalid TOML: {exc}") from exc
    except RecursionError:
        raise ModelError(f"{what}: invalid TOML: tables or arrays nest more than {MAX_TOML_DEPTH} deep") from None
    if _depth(data) > MAX_TOML_DEPTH:
        raise ModelError(f"{what}: invalid TOML: tables or arrays nest more than {MAX_TOML_DEPTH} deep")
    return normalize(data)


def _front_matter(text: str, what: str) -> tuple[dict, str]:
    if len(text) > MAX_DOCUMENT_BYTES // 4 and (size := len(text.encode("utf-8", errors="replace"))) > MAX_DOCUMENT_BYTES:
        raise ModelError(f"{what}: {size} bytes; a document holds at most {MAX_DOCUMENT_BYTES}: split it, or link the detail")
    m = FRONT_MATTER.match(text.lstrip("﻿"))
    if not m:
        raise ModelError(f"{what}: missing +++ TOML front matter at the top of the file")
    return parse_toml(m.group(1), what), text[m.end() :]


def split_front_matter(text: str, what: str = "document") -> tuple[dict, str]:
    """The front matter and the body. A document larger than MAX_DOCUMENT_BYTES, or front matter that is not valid
    TOML, is a ModelError."""
    return _front_matter(text, what)


OBJECT_SCHEMAS = {kind: f"{kind}.schema.json" for kind in ("spec", "epic", "initiative", "proposal", "runbook", "postmortem")}

# A proposal's status says which human decisions must already be on record.
PROPOSAL_OUTCOMES = ("submitted", "accepted", "rejected", "withdrawn")
PROPOSAL_NEEDS_GO = ("drafting", "signed_off", "submitted", "accepted", "rejected")
PROPOSAL_NEEDS_SIGN_OFF = ("signed_off", "submitted", "accepted", "rejected")


def proposal_status(p: dict) -> str:
    """A proposal's derived status: the recorded outcome, else what go_no_go and sign_off say."""
    outcome = (p.get("outcome") or {}).get("decision")
    if outcome in PROPOSAL_OUTCOMES:
        return str(outcome)
    go = (p.get("go_no_go") or {}).get("decision")
    if go == "no_go":
        return "no_go"
    if go == "go":
        return "signed_off" if p.get("sign_off") else "drafting"
    return "exploring"


def load_object(text: str, what: str) -> tuple[dict, str, list[str]]:
    """Parse and schema-check a Spec, Epic, Initiative, Proposal, runbook, or postmortem file."""
    bad = control_characters(text)
    if bad:
        return {}, "", [f"{what}: {bad}; a Spec is plain text, and hidden bytes could change what the approver reads"]
    data, body = _front_matter(text, what)
    kind = str(data.get("kind"))
    schema_name = OBJECT_SCHEMAS.get(kind)
    if schema_name is None:
        return data, body, [f"{what}: kind must be {', '.join(OBJECT_SCHEMAS)}"]
    errors = [f"{what}: {e}" for e in schema.validate(data, schema_name)]
    if kind == "spec" and not errors:
        errors += [f"{what}: {e}" for e in lint_spec(data, body)]
    if kind == "proposal" and not errors:
        errors += [f"warning: {what}: {e[9:]}" if e.startswith("warning: ") else f"{what}: {e}" for e in lint_proposal(data)]
    if kind == "initiative" and not errors:
        errors += [f"{what}: {e}" for e in lint_decisions(data.get("decisions") or [])]
    return data, body, errors


_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def control_characters(text: str) -> str | None:
    """Where the first control character other than tab, newline, or carriage return is, for an error message."""
    m = _CONTROL.search(text)
    return f"control character {m.group(0)!r} at line {text.count(chr(10), 0, m.start()) + 1}" if m else None


def sections(body: str) -> set[str]:
    return {m.group(1).strip().lower() for m in re.finditer(r"^#{1,3}[ \t]+(.+?)[ \t]*#*$", body, re.M)}


def _unique_ids(field: str, items: list[dict]) -> list[str]:
    ids = [x["id"] for x in items]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    return [f"{field}: ids must be unique ({', '.join(dupes)})"] if dupes else []


# A claim seen only in simulation must not say it holds everywhere. Whole words, any case; a hyphen joins a word
# ("same-day", "all-in", "always-on" are not absolute).
ABSOLUTE_WORDS = re.compile(r"(?<![\w-])(every\w*|always|never|same|already works|all|none|guaranteed|100%)(?![\w-])", re.I)


def fmt_number(x: float) -> str:
    """A number as a person reads it: every digit, at most two decimals, no trailing zeros."""
    return f"{x:.2f}".rstrip("0").rstrip(".")


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
                f"estimate.parts {part['id']}: low <= likely <= high must hold (low {fmt_number(part['low'])}, likely {fmt_number(part['likely'])}, high {fmt_number(part['high'])})"
            )
    if parts:
        rollup = sum((x["low"] + 4 * x["likely"] + x["high"]) / 6 for x in parts)
        # Floating-point error grows with the numbers: allow a tolerance relative to the range, not a fixed one.
        tol = 1e-9 * max(1.0, abs(est["low"]), abs(est["high"]))
        if not est["low"] - tol <= rollup <= est["high"] + tol:
            errs.append(
                f"estimate.parts: the PERT roll-up of the parts is {fmt_number(rollup)} {est['unit']}, outside the total's range of "
                f"{fmt_number(est['low'])} to {fmt_number(est['high'])}; fix the parts or the range"
            )
    return errs


def lint_claims(claims: list[dict]) -> list[str]:
    """Unique ids; a warning for a claim with no evidence, and for an absolute word in a claim seen only in simulation."""
    errs = _unique_ids("claims", claims)
    for c in claims:
        if not c.get("evidence"):
            errs.append(f"warning: claims {c['id']} has no evidence; add a file:line, a test, or a recording, or take the claim out")
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
        elif old is not None and str(d["on"]) < str(seen[old]):
            errs.append(f"decisions {d['id']} replaces {old} but is dated {d['on']}, before {old} ({seen[old]})")
        seen[d["id"]] = d["on"]
    return errs


def lint_proposal(p: dict) -> list[str]:
    """Rules a schema cannot express: unique ids, consistent ranges, the claims and the decisions logs, and the
    decisions the status claims."""
    errs: list[str] = []
    for field in ("needs", "options", "risks", "questions"):
        errs += _unique_ids(field, p.get(field, []))
    if p.get("estimate"):
        errs += lint_estimate(p["estimate"])
    errs += lint_claims(p.get("claims") or [])
    errs += lint_decisions(p.get("decisions") or [])
    if len([o for o in p.get("options", []) if o.get("recommended")]) > 1:
        errs.append("options: recommend one option at most")
    go, derived = (p.get("go_no_go") or {}).get("decision"), proposal_status(p)
    outcome = (p.get("outcome") or {}).get("decision")
    if outcome in ("submitted", "accepted", "rejected"):
        if go != "go":
            errs.append(f'outcome {outcome} needs go_no_go.decision = "go": a person decides to pursue it before the team drafts')
        if not p.get("sign_off"):
            errs.append(f"outcome {outcome} needs sign_off: a person signs the proposal off before it is sent")
        if not p.get("needs"):
            errs.append(f"outcome {outcome} needs the needs it answers")
    status = p.get("status")
    if status is None or status == derived:
        return errs
    # The stored status is a cache. One the decisions do not support claims a decision nobody recorded: an error.
    if status == "no_go" and go != "no_go":
        errs.append('status no_go needs go_no_go.decision = "no_go", with who decided and when')
    elif status in PROPOSAL_NEEDS_GO and go != "go":
        errs.append(f'status {status} needs go_no_go.decision = "go": a person decides to pursue it before the team drafts')
    elif status in PROPOSAL_NEEDS_SIGN_OFF and not p.get("sign_off"):
        errs.append(f"status {status} needs sign_off: a person signs the proposal off before it is sent")
    elif status in PROPOSAL_OUTCOMES and outcome != status:
        errs.append(f'status {status} needs outcome = {{ decision = "{status}", by = "@you", on = "YYYY-MM-DD" }}: a person records it')
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
                (test_files, "test file", "tests are frozen at Spec approval and are not implementation scope"),
                (design_files, "design file", "the design is frozen at Spec approval and is not implementation scope"),
                (docs, "frozen doc", "it is approved with the Spec and is not implementation scope (set frozen = false for a living doc a Task changes)"),
            ):
                errs += [f"task {t['id']}: scope {pattern!r} overlaps {what} {f!r}; {why}" for f in files if globs.overlap(pattern, f)]
    for tf in test_files:
        if globs.is_catch_all(tf):
            errs.append(f"tests.files {tf!r} matches every path; name the test files or directories")
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
    if spec.get("route") in ("normal", "major"):
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

    def visit(n: str) -> bool:
        if seen.get(n) == 1:
            return False
        if seen.get(n) == 2:
            return True
        seen[n] = 1
        for d in deps.get(n, []):
            if d in deps and not visit(d):
                return False
        seen[n] = 2
        out.append(n)
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


_HTML_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.S)


def _extract_change_blocks(body: str) -> list[str]:
    fence_char: str | None = None
    fence_len = 0
    in_aidd = False
    current: list[str] = []
    blocks: list[str] = []
    for line in _HTML_COMMENT.sub("", body or "").splitlines(keepends=True):
        m = re.match(r"^[ ]{0,3}(`{3,}|~{3,})", line)
        marker = m.group(1) if m else ""
        info = line.strip()[len(marker) :].strip()
        if fence_char:
            if m and marker[0] == fence_char and len(marker) >= fence_len and not info:
                if in_aidd:
                    blocks.append("".join(current))
                fence_char, in_aidd = None, False
            elif in_aidd:
                current.append(line)
        elif m:
            fence_char, fence_len = marker[0], len(marker)
            in_aidd, current = bool(re.match(r"^toml[ \t]+aidd$", info)), []
    return blocks


def parse_change_block(body: str) -> tuple[dict | None, list[str]]:
    """The one Change Request block of a description. A block inside an HTML comment is not rendered, so it does not count."""
    blocks = _extract_change_blocks(body)
    if not blocks:
        return None, []
    if len(blocks) > 1:
        return None, ["the description has more than one Change Request block (```toml aidd)"]
    try:
        data = parse_toml(blocks[0], "Change Request block")
    except ModelError as exc:
        return None, [str(exc)]
    errs = schema.validate(data, "change-request.schema.json")
    if "spec" not in data and data.get("route") in ("normal", "major"):
        # The gate reports a missing Spec under `spec`; the enum error would only restate it.
        errs = [e for e in errs if not e.startswith("$.route:")]
    return data, [f"Change Request block: {e}" for e in errs]


def with_defaults(block: dict, changed_paths: list[str]) -> dict:
    """An inline Change Request block with every optional field filled: chore, high confidence, no risk dimension, revert to undo,
    and, when no scope is declared, the changed paths themselves."""
    out = dict(block)
    for key, value in INLINE_DEFAULTS.items():
        out.setdefault(key, value)
    out.setdefault("risk", {"summary": "Small and reversible.", "dimensions": [], "reversible": True})
    out.setdefault("scope", list(changed_paths))
    return out


def tests_files(patterns: list[str], tree: dict[str, str]) -> list[str]:
    return sorted(p for p in tree if globs.match_any(patterns, p))


_WINDOWS_DRIVE = re.compile(r"[A-Za-z]:[\\/]")


def _path_literals(cmd: object) -> list[str]:
    """The relative file paths a test command's argument list names literally (a token with a "/" and a file extension).
    An absolute path (`/usr/bin/python3`, `C:/Python311/python.exe`) is outside the repository, so it is never one."""
    if not isinstance(cmd, list):
        return []
    out = []
    for tok in cmd:
        if not isinstance(tok, str) or tok.startswith(("-", "/", "\\")) or _WINDOWS_DRIVE.match(tok):
            continue
        if "/" in tok and not any(c in tok for c in " >|<;&*"):
            name = tok.rsplit("/", 1)[-1]
            if "." in name and not name.startswith("."):
                out.append(tok)
    return out


def command_path_literals(spec: dict) -> list[str]:
    return [p for tc in (spec.get("tests") or {}).get("commands", []) for p in _path_literals(tc.get("command", []))]


# The kinds of document a Spec links in `[[docs]]` (spec.schema.json#/$defs/doc).
DOC_KINDS = (
    "tech-spec",
    "test-plan",
    "design-spec",
    "adr",
    "threat-model",
    "authz",
    "api",
    "runbook",
    "slo",
    "compliance",
    "analytics",
    "migration",
    "acceptance",
    "data-map",
    "vendors",
    "other",
)


def frozen_docs(spec: dict) -> list[str]:
    """The paths of the Spec's frozen `[[docs]]` (frozen unless it says `frozen = false`)."""
    return [d["path"] for d in spec.get("docs") or [] if isinstance(d, dict) and isinstance(d.get("path"), str) and d.get("frozen", True) is not False]


def design_paths(spec: dict) -> list[str]:
    """The files approved with the Spec that are neither tests nor implementation: its design files and its frozen
    docs. The gate, the runner, the guard, and the hash treat each one alike."""
    return list(dict.fromkeys(list((spec.get("design") or {}).get("files", [])) + frozen_docs(spec)))


def frozen_paths(spec: dict) -> list[str]:
    """What Spec approval freezes besides the Spec file: the test files, the design files, the frozen docs, and
    literal test paths."""
    declared = list((spec.get("tests") or {}).get("files", [])) + design_paths(spec)
    return list(dict.fromkeys(declared + command_path_literals(spec)))


def strip_handoffs(body: str) -> str:
    """The body without its closed ```aidd-handoff blocks: each from its opening fence line to the first later line of
    exactly three backticks (and that line's newline). One pass over the lines, whatever the body holds."""
    lines = body.split("\n")
    n = len(lines)
    # close_at[i]: the first line at or after i that closes a fence, or n when none does.
    close_at = [n] * (n + 1)
    for i in range(n - 1, -1, -1):
        close_at[i] = i if _FENCE_CLOSE.fullmatch(lines[i]) else close_at[i + 1]
    out: list[str] = []
    i = 0
    while i < n:
        # An opening fence needs a newline after it (a line follows) and a closing line after that.
        if i < n - 1 and _HANDOFF_OPEN.fullmatch(lines[i]) and close_at[i + 1] < n:
            j = close_at[i + 1]
            if j == n - 1:  # the block ends the body: the newline before it stays
                out.append("")
            i = j + 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def spec_hash(spec_text: str, tree: dict[str, str]) -> str:
    """Hash of what a human approves: the stable Spec fields, the body, the test files, the design files, and the
    frozen docs.

    The bookkeeping keys (VOLATILE_SPEC_KEYS and VOLATILE_TASK_KEYS) and handoff notes are excluded, so bookkeeping
    never voids an approval. Any change to acceptance, tasks, scope, or a test file does.
    """
    data, body = split_front_matter(spec_text, "spec")
    body = strip_handoffs(body)
    stable = {k: v for k, v in data.items() if k not in VOLATILE_SPEC_KEYS}
    stable["tasks"] = [{k: v for k, v in t.items() if k not in VOLATILE_TASK_KEYS} for t in data.get("tasks", [])]
    # One canonical JSON document, never concatenated parts: JSON escapes every quote and
    # control character, so no part can absorb the bytes of another (the body could
    # otherwise carry a deleted test file's path and blob and keep the hash).
    payload = {"front": stable, "body": body.strip().replace("\r\n", "\n"), "files": {path: tree[path] for path in tests_files(frozen_paths(data), tree)}}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    # 128 bits: the agent writes both the approved and any substitute Spec, so the
    # hash must resist a birthday search, not just an accidental collision.
    return hashlib.sha256(blob).hexdigest()[:32]


# The decisions a person records about a proposal at or after its sign-off, and the scope decisions log: the proposal
# hash leaves them out, so recording them never changes what was signed off.
PROPOSAL_UNSIGNED_KEYS = frozenset({"sign_off", "outcome", "status", "decisions"})
# The living fields: the bookkeeping the schema says people fill in over time, after sign-off too. The proposal hash
# leaves them out, as the Spec hash leaves out a Spec's bookkeeping. Each list of the front matter, and the keys of
# its items that the hash leaves out.
PROPOSAL_LIVING_FIELDS: dict[str, tuple[str, ...]] = {
    "questions": ("answer",),
    "risks": ("status",),
    "assumptions": ("status",),
    "issues": ("status",),
    "dependencies": ("status",),
    "milestones": ("reached_on", "invoice_ref"),
    "needs": ("epic",),
}


def proposal_hash(text: str) -> str:
    """Hash of what a person signs off in a proposal: the whole body and the front matter, except these.

    - The decisions, PROPOSAL_UNSIGNED_KEYS: `sign_off`, `outcome`, `status`, and the scope decisions log, `decisions`.
    - The living fields, PROPOSAL_LIVING_FIELDS: each question's `answer`, each RAID item's `status`, each milestone's
      `reached_on` and `invoice_ref`, and each need's `epic`.

    It is built like the Spec hash: one canonical JSON document, then the first 128 bits of its SHA-256, in hex. TOML
    comments, key order, and CRLF line endings change nothing. Any other change to the needs, the estimate and its parts,
    the price, the exclusions, the claims, the RAID log, or the body does. Unlike the Spec hash, it keeps `aidd-handoff`
    blocks: a block in a proposal could hold terms that the sign-off must bind.
    """
    data, body = split_front_matter(text.replace("\r\n", "\n"), "proposal")
    front: dict[str, Any] = {k: v for k, v in data.items() if k not in PROPOSAL_UNSIGNED_KEYS}
    for key, living in PROPOSAL_LIVING_FIELDS.items():
        if isinstance(front.get(key), list):
            front[key] = [{k: v for k, v in item.items() if k not in living} if isinstance(item, dict) else item for item in front[key]]
    payload = {"front": front, "body": body.strip()}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:32]


def set_outcome(text: str, key: str, value: str) -> str:
    """Set one `[outcome]` field in a Spec's front matter, adding the table when it is missing.

    Outcome is bookkeeping: the Spec hash ignores it, so recording it never voids Spec approval.
    """
    m = FRONT_MATTER.match(text.lstrip("﻿"))
    if not m:
        raise ModelError("missing +++ TOML front matter")
    front = m.group(1)
    line = f'{key} = "{value}"'
    if re.search(r"^outcome[ \t]*=", front, re.M):
        raise ModelError("outcome is an inline table; write it as a [outcome] table so fields can be recorded")
    table = re.search(r"^\[outcome\][ \t]*(?:#.*)?$", front, re.M)
    if table:
        rest = front[table.end() :]
        nxt = re.search(r"^\[", rest, re.M)
        body = rest[: nxt.start()] if nxt else rest
        if re.search(rf"^{key}[ \t]*=", body, re.M):
            body = re.sub(rf"^{key}[ \t]*=.*$", line, body, count=1, flags=re.M)
        else:
            body = body.rstrip("\n") + "\n" + line + "\n" + ("\n" if nxt else "")
        front = front[: table.end()] + body + (rest[nxt.start() :] if nxt else "")
    else:
        front = front.rstrip("\n") + "\n\n[outcome]\n" + line + "\n"
    return text[: m.start(1)] + front + text[m.end(1) :]


_HEADING = re.compile(r"^##[ \t]+(.+?)[ \t]*$", re.M)


def section(text: str, heading: str, *, fences: bool = True) -> str:
    """The body of a `## <heading>` section, with HTML comments and a Markdown table's skeleton removed (and code fence
    lines, unless `fences`): empty when the heading is absent or holds only the template's guidance, so a heading nobody
    filled in counts as missing."""
    matches = list(_HEADING.finditer(text))
    for i, m in enumerate(matches):
        if m.group(1).strip().lower() != heading.lower():
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        # A table nobody filled in is rules and empty cells, not prose.
        lines = [ln for ln in _HTML_COMMENT.sub("", text[m.end() : end]).splitlines() if ln.strip() and not re.fullmatch(r"\|[\s|:-]*\|", ln.strip())]
        return "\n".join(ln for ln in lines if fences or not ln.strip().startswith("```")).strip()
    return ""
