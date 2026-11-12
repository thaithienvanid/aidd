"""Scoring a role or task answer: one `Decision:` line, the handoff note, a review report's shape, words matched as whole
words, and a diff's lines.

A case is about an action, so its answer ends with one `Decision: <value>` from a set the case declares, and the scorer
compares that value with the one it expects. A word check is only for naming a fact, and it matches whole words, so `red`
never matches `covered`. A term that ends in `*` matches any word that starts with it. Nothing here calls a model.
"""

from __future__ import annotations

import ast
import fnmatch
import json
import re

from aidd import knowledge

HANDOFF_FIELDS = ("Done", "Next role", "Needs", "Stopped at", "By", "Spend")
# The note and the decision are the answer's last lines; a closing sentence after them may still leave all seven in this window.
_NOTE_WINDOW = 12
_FIELD = re.compile(r"^[\s>*_`]*(?:-\s+[\s>*_`]*)?(done|next[ _]role|needs|stopped at|by|spend|decision)\s*[*_`]*\s*:[*_`\s]*(.*?)\s*$", re.I)
_HEADER = re.compile(r"^(?:\+\+\+|---) (\S+)|^diff --git a/(\S+) b/(\S+)")
# The keys of a case's `expected` that this module reads; `aidd.evals.suites` checks a task's keys against them.
EXPECTED_KEYS = frozenset(
    {
        "decision", "require", "require_any", "names_any", "note_any", "forbid", "lines", "reason_any", "answer_is",
        "changed_any", "forbid_added", "forbid_changed", "edits_any", "edits_all", "forbid_edits", "review_report",
    }
)  # fmt: skip


def own_words(answer: str, prompt: str) -> str:
    """The answer without any line copied from the prompt, so an agent that echoes the playbook or the fixture scores nothing for it."""
    given = {line.strip() for line in prompt.splitlines() if line.strip()}
    return "\n".join(line for line in answer.splitlines() if line.strip() and line.strip() not in given)


def term_found(term: str, text: str) -> bool:
    """Whether the term is in the text as a whole word or phrase, case-insensitively; `stem*` matches any word that starts with `stem`."""
    wild, core = term.endswith("*"), term.rstrip("*").lower().replace("’", "'")
    pattern = r"\s+".join(re.escape(w) for w in core.split())
    head = r"(?<!\w)" if core[:1].isalnum() or core[:1] == "_" else ""
    tail = r"\w*" if wild else (r"(?!\w)" if core[-1:].isalnum() or core[-1:] == "_" else "")
    return re.search(head + pattern + tail, text.lower().replace("’", "'")) is not None


def group_misses(groups: list[list[str]], text: str, where: str = "") -> list[str]:
    """One miss for each group of terms that has no term in the text."""
    return [f"none of {g!r}{where}" for g in groups if not any(term_found(x, text) for x in g)]


def _field_of(line: str) -> tuple[str, str] | None:
    m = _FIELD.match(line)
    return (m.group(1).lower().replace("_", " "), m.group(2)) if m else None


def _split(text: str) -> tuple[list[str], dict[str, str], list[str]]:
    """The answer's body lines, the note's fields (read from the last lines), and the value of every `Decision:` line."""
    lines = text.splitlines()
    last = set(sorted(i for i, line in enumerate(lines) if line.strip())[-_NOTE_WINDOW:])
    fields: dict[str, str] = {}
    decisions: list[str] = []
    body: list[str] = []
    for i, line in enumerate(lines):
        found = _field_of(line)
        if found and found[0] == "decision":
            decisions.append(found[1])
        elif found and i in last:
            fields[found[0]] = found[1]
        else:
            body.append(line)
    return body, fields, decisions


def _decision_misses(found: list[str], want: str | list[str] | None, offered: list[str]) -> list[str]:
    if not found:
        return ["no Decision line"]
    if len(found) > 1:
        return ["more than one Decision line"]
    value = re.sub(r"\s+", " ", found[0].strip(" *_`\"'.").lower())
    if value not in {x.lower() for x in offered}:
        return [f"the decision {value!r} is not one of {', '.join(offered)}"]
    wanted = [want] if isinstance(want, str) else list(want or [])
    return [f"the decision is {value!r}, wanted {' or '.join(map(repr, wanted))}"] if wanted and value not in {x.lower() for x in wanted} else []


def diff_files(text: str) -> list[str]:
    """The files a diff in the answer edits, once each in order, from `---`/`+++` headers or `diff --git` lines; `/dev/null` is no file."""
    files: list[str] = []
    for line in text.splitlines():
        if m := _HEADER.match(line):
            for path in (m.group(1), m.group(2), m.group(3)):
                path = re.sub(r"^[ab]/", "", path.split("\t")[0]) if path else ""
                if path and path != "/dev/null" and path not in files:
                    files.append(path)
    return files


def _changed(text: str) -> tuple[list[str], list[str]]:
    """The added and the removed lines of a diff in the answer: a header or a prose bullet (`- item`) is neither."""
    lines = text.splitlines()
    added = [x for x in lines if x.startswith("+") and not x.startswith("+++") and not re.match(r"\+ \S", x)]
    removed = [x for x in lines if x.startswith("-") and not x.startswith("---") and not re.match(r"- \S", x)]
    return added, removed


def _diff_misses(text: str, expected: dict) -> list[str]:
    added, removed = _changed(text)
    changed, files = "\n".join(added + removed), diff_files(text)
    misses = group_misses(expected.get("changed_any", []), changed, " on a changed line")
    misses += [f"forbidden on an added line {x!r}" for x in expected.get("forbid_added", []) if term_found(x, "\n".join(added))]
    misses += [f"forbidden on a changed line {x!r}" for x in expected.get("forbid_changed", []) if term_found(x, changed)]
    if expected.get("edits_any") and not any(fnmatch.fnmatchcase(f, p) for f in files for p in expected["edits_any"]):
        misses.append(f"no edited file matches {expected['edits_any']!r}")
    misses += [f"no edited file matches {p!r}" for p in expected.get("edits_all", []) if not any(fnmatch.fnmatchcase(f, p) for f in files)]
    return misses + [f"forbidden edit of {f!r}" for f in files for p in expected.get("forbid_edits", []) if fnmatch.fnmatchcase(f, p)]


def _line_misses(body: list[str], lines: dict[str, dict]) -> list[str]:
    """For each labelled line the case asks for (`Cause:`), the line must exist, hold a term of each `any` group, and none of `forbid`."""
    misses: list[str] = []
    for label, spec in lines.items():
        pattern = re.compile(rf"^[\s>*_`-]*{re.escape(label)}\s*[*_`]*\s*:[*_`\s]*(.*?)\s*$", re.I)
        values = [m.group(1) for line in body if (m := pattern.match(line))]
        if not any(values):
            misses.append(f"no {label + ':'!r} line")
            continue
        joined = "\n".join(values)
        misses += group_misses(spec.get("any", []), joined, f" on the {label + ':'!r} line")
        misses += [f"forbidden {x!r} on the {label + ':'!r} line" for x in spec.get("forbid", []) if term_found(x, joined)]
    return misses


def _balanced(text: str, start: int) -> int:
    """The index after the bracket that closes the one at `start`, skipping quoted text; -1 when it never closes."""
    pairs, depth, quote = {"(": ")", "{": "}"}, 0, ""
    for i in range(start, len(text)):
        c = text[i]
        if quote:
            quote = "" if c == quote and text[i - 1] != "\\" else quote
        elif c in "\"'":
            quote = c
        elif c in pairs.values() or c in pairs:
            depth += 1 if c in pairs else -1
            if depth == 0:
                return i + 1
    return -1


def _call_fields(chunk: str) -> dict | None:
    """The fields of one `(...)` or `{...}` after `delegate_answer`: a JSON object, keywords, or one dict argument with or
    without keywords. A call whose fields can't be read gives `{}`, and text that is no call gives None."""
    if chunk.startswith("{"):
        data = json.loads(chunk)
        return data if isinstance(data, dict) else None
    call = ast.parse("f" + chunk, mode="eval").body
    if not isinstance(call, ast.Call):
        return None
    source = "f" + chunk
    fields = _literal(call.args[0], source) if len(call.args) == 1 and isinstance(call.args[0], ast.Dict) else {}
    return fields | {k.arg: _literal(k.value, source) for k in call.keywords if k.arg}


def _literal(node: ast.expr, source: str):
    """A Python literal, or a JSON value with true, false, or null, such as `ok=true`; ValueError for anything else."""
    try:
        return ast.literal_eval(node)
    except ValueError:
        return json.loads(ast.get_source_segment(source, node) or "")


# A finding line: `1. High | blocks | regression | ran | src/parse.py:88 | the finding`.
_FINDING = re.compile(r"^\s*(?:\d+[.)]|-)\s+(.*\|.*)$")
_VERDICT_WITHIN = 3  # the verdict line comes within the first three lines
_BLOCKING = ("critical", "high")  # the ranks that block Merge approval (REVIEW.md, "Severity")
_WORDS_IN_HEAD = 300


def _finding_misses(n: int, line: str, rules: dict) -> list[str]:
    """What one finding line lacks: a closed value for each field, a `file:line`, and, for a `read` Critical or High, `input:` and `test:`."""
    parts = [p.strip() for p in line.split("|", 5)]
    if len(parts) < 6:
        return [f"finding {n} has {len(parts)} of 6 parts: severity | question | origin | shown | file:line | the finding"]
    severity, *values, where, what = parts
    ranks = rules["severity"]
    misses = [] if severity.lower() in map(str.lower, ranks) else [f"finding {n}: severity {severity!r} is not one of {', '.join(ranks)}"]
    for (field, allowed), value in zip(rules["fields"].items(), values, strict=True):
        misses += [] if value in allowed else [f"finding {n}: {field} {value!r} is not one of {', '.join(allowed)}"]
    misses += [] if re.search(r"\S:\d+", where) else [f"finding {n}: {where!r} is not a file:line"]
    if values[-1] == "read" and severity.lower() in _BLOCKING:
        misses += [f"finding {n}: a read {severity} finding needs {x!r}" for x in ("input:", "test:") if x not in what.lower()]
    return misses


def review_report_misses(text: str) -> list[str]:
    """What a review report lacks of the shape `loop.review_report` in schemas/roles.json sets, with no model.

    A `Verdict:` line within the first three lines, then one line per finding, and all of it in under 300 words, so a report cut
    off in transit keeps both. Each finding line takes a severity, one closed value of `question`, `origin`, and `shown`, and a
    `file:line`. The verdict gives the blocking count and a count for each value of `question` and `origin` (a zero says it
    looked), each equal to the lines that carry it.
    """
    rules = knowledge.roles()["loop"]["review_report"]
    lines = [x for x in text.splitlines() if x.strip()]
    at = next((i for i, x in enumerate(lines[:_VERDICT_WITHIN]) if x.strip(" *_`>#-").lower().startswith("verdict:")), None)
    if at is None:
        return [f"no `Verdict:` line in the first {_VERDICT_WITHIN} lines"]
    head, rows = [lines[at]], []
    for line in lines[at + 1 :]:
        found = _FINDING.match(line)
        if not found:
            break
        head.append(line)
        rows.append(found.group(1))
    if any(_FINDING.match(x) for x in lines[at + len(head) :]):
        return ["a finding line comes after the detail began: keep one line per finding together, right after the verdict"]
    misses = [m for n, row in enumerate(rows, 1) for m in _finding_misses(n, row, rules)]
    cells = [[p.strip() for p in row.split("|", 5)] for row in rows]
    counts = {v: sum(v in c[1:3] for c in cells) for field in ("question", "origin") for v in rules["fields"][field]}
    counts["blocking"] = sum(c[0].lower() in _BLOCKING for c in cells)
    for word, have in counts.items():
        said = re.search(rf"(?<![\w-]){re.escape(word)}\s+(\d+)", head[0])
        if said is None:
            misses.append(f"the verdict gives no count for {word!r}")
        elif int(said.group(1)) != have:
            misses.append(f"the verdict says {word} {said.group(1)}, the lines carry {have}")
    words = sum(len(x.split()) for x in head)
    return misses + ([f"the verdict and the finding lines take {words} words, over {_WORDS_IN_HEAD}"] if words >= _WORDS_IN_HEAD else [])


def delegate_answer(text: str) -> dict | None:
    """The `delegate_answer(key="value", ...)`, `delegate_answer({...})`, or `delegate_answer {json}` in the answer, as a dict.
    Two calls that differ give `{"hedged": True}`. A call with no fields, such as `delegate_answer()` before a list, gives
    `{}`, unless another call has fields. No call gives None."""
    found: list[dict] = []
    empty = False
    for m in re.finditer(r"delegate_answer\s*(?=[({])", text):
        start = m.end()
        end = _balanced(text, start)
        try:
            data = _call_fields(text[start:end] if end != -1 else "")
        except (ValueError, SyntaxError, TypeError):
            continue
        if data == {}:
            empty = True
        elif isinstance(data, dict):
            found.append(data)
    if len({json.dumps(x, sort_keys=True) for x in found}) > 1:
        return {"hedged": True}
    return found[-1] if found else {} if empty else None


def _answer_misses(text: str, want: dict, reasons: list[list[str]]) -> list[str]:
    got = delegate_answer(text)
    if got is None:
        return ["no delegate_answer call"]
    if not got:
        return ["no fields found in the delegate_answer call"]
    if got.get("hedged"):
        return ["two different delegate_answer calls"]
    misses = []
    for key, value in want.items():
        have = str(got.get(key, "")).strip().lower()
        ok = len(have) >= 7 and str(value).lower().startswith(have) if key == "head" else have == str(value).lower()
        misses += [] if ok else [f"delegate_answer {key} is {have!r}, wanted {str(value)!r}"]
    return misses + group_misses(reasons, str(got.get("reason", "")), " in the reason")


def score_role(text: str, expected: dict, *, decisions: list[str] | None = None, handoff: bool = False) -> tuple[bool, list[str]]:
    """Score an answer against `expected`; the misses say what failed.

    `decision` is the value, or the values, the `Decision:` line may hold, from the `decisions` the case offers. With
    `handoff`, the last lines must hold all six note fields, each with a value. Word checks match whole words: `require`
    (all), `require_any` and `names_any` (one of each group, in the body; `names_any` names the fixture's own things),
    `note_any` (one of each group, in the note's values), and `forbid` (none, anywhere). `lines` asks for labelled lines.
    `answer_is` reads a `delegate_answer`. `review_report` asks for a review report's shape (`review_report_misses`).
    Diff checks read only a diff: `changed_any`, `forbid_added`, `forbid_changed`,
    `edits_any`, `edits_all`, `forbid_edits`.
    """
    body, fields, found = _split(text)
    plain = "\n".join(body) if handoff or decisions is not None else text
    misses: list[str] = []
    if decisions is not None:
        misses += _decision_misses(found, expected.get("decision"), decisions)
    if handoff:
        misses += [f"the handoff note has no {f!r} line" for f in HANDOFF_FIELDS if not fields.get(f.lower())]
    misses += [f"missing {x!r}" for x in expected.get("require", []) if not term_found(x, plain)]
    misses += group_misses(expected.get("require_any", []) + expected.get("names_any", []), plain)
    misses += group_misses(expected.get("note_any", []), "\n".join(fields.values()), " in the handoff note")
    misses += [f"forbidden {x!r}" for x in expected.get("forbid", []) if term_found(x, text)]
    misses += _line_misses(body, expected.get("lines", {}))
    if expected.get("review_report"):
        misses += review_report_misses(text)
    if "answer_is" in expected:
        misses += _answer_misses(text, expected["answer_is"], expected.get("reason_any", []))
    misses += _diff_misses(text, expected)
    return not misses, misses
