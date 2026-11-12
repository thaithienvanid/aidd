"""A test command's JUnit XML report: which test cases failed, read with the standard library's expat parser.

The report is written by a command the change controls, so it is untrusted input. It is read within a size and a depth
limit, a DOCTYPE or an entity declaration is refused, and a report that is missing, stale, or unreadable is a problem in
the evidence, never a crash. The report adds detail to a result. The exit code stays the evidence.
"""

from __future__ import annotations

from pathlib import Path
from xml.parsers import expat

MAX_REPORT_BYTES = 10 * 1024 * 1024
MAX_DEPTH = 32
MAX_FAILED_NAMES = 20
MAX_NAME_CHARS = 200


class _Refused(ValueError):
    pass


def _refuse_dtd(*_args: object) -> None:
    raise _Refused("it declares a DOCTYPE or an entity, which aidd refuses")


def _name(attrs: dict[str, str]) -> str:
    full = ".".join(x for x in (attrs.get("classname"), attrs.get("name")) if x) or "(unnamed)"
    return "".join(ch if ch.isprintable() else " " for ch in full[:MAX_NAME_CHARS])


def parse_report(data: bytes) -> dict:
    """Counts and the first failed names of a JUnit XML document. A test case fails when it holds a `failure` or an
    `error` element. Raises ValueError, naming why, when the document is not a report aidd will read."""
    tests = failed = skipped = 0
    names: list[str] = []
    stack: list[str] = []
    case: dict = {}

    def start(tag: str, attrs: dict[str, str]) -> None:
        nonlocal tests
        if len(stack) >= MAX_DEPTH:
            raise _Refused(f"it nests deeper than {MAX_DEPTH} elements")
        if not stack and tag not in ("testsuites", "testsuite"):
            raise ValueError(f"its root element is <{tag}>, not <testsuites> or <testsuite>")
        if tag == "testcase":
            tests += 1
            case.clear()
            case.update(name=_name(attrs), failed=False, skipped=False)
        elif stack and stack[-1] == "testcase" and tag in ("failure", "error"):
            case["failed"] = True
        elif stack and stack[-1] == "testcase" and tag == "skipped":
            case["skipped"] = True
        stack.append(tag)

    def end(tag: str) -> None:
        nonlocal failed, skipped
        stack.pop()
        if tag == "testcase":
            if case["failed"]:
                failed += 1
                if len(names) < MAX_FAILED_NAMES:
                    names.append(case["name"])
            elif case["skipped"]:
                skipped += 1

    parser = expat.ParserCreate()
    parser.StartElementHandler, parser.EndElementHandler = start, end
    parser.StartDoctypeDeclHandler = parser.EntityDeclHandler = _refuse_dtd
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    try:
        parser.Parse(data, True)
    except expat.ExpatError as exc:
        raise ValueError(f"it is not well-formed XML ({expat.ErrorString(exc.code)})") from exc
    except LookupError as exc:  # an encoding the declaration names and Python lacks
        raise ValueError(f"it declares an encoding aidd cannot read ({exc})") from exc
    return {"tests": tests, "failed": failed, "skipped": skipped, "failed_tests": names}


def stamp(root: Path, rel: str) -> tuple[int, int] | None:
    """The report file's modification time and size, or None when it is not there: taken before a command runs."""
    try:
        st = (root / rel).stat()
    except (OSError, ValueError):  # a path no file system holds, such as one with a NUL
        return None
    return (st.st_mtime_ns, st.st_size)


def read_report(root: Path, rel: str, before: tuple[int, int] | None) -> dict:
    """What the command's report says, for the evidence: counts, or a `problem` when it cannot be read. `before` is
    the file's `stamp` from before the run, so a report the run did not write is a problem, not a result."""
    out: dict = {"path": rel}
    try:
        path = (root / rel).resolve()
        now = stamp(root, rel)
        if now is None:
            raise ValueError("the command wrote no report there")
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError("the path is not a regular file inside the repository")
        if now == before:
            raise ValueError("the report was not rewritten by this run, so it is from an earlier one")
        if now[1] > MAX_REPORT_BYTES:
            raise ValueError(f"it is over {MAX_REPORT_BYTES} bytes")
        with open(path, "rb") as f:
            data = f.read(MAX_REPORT_BYTES + 1)
        out.update(parse_report(data))
    except (ValueError, OSError, RuntimeError) as exc:  # RuntimeError: a symlink loop, on Python 3.11 and 3.12
        out["problem"] = f"report {rel}: {exc}"
    return out


def report_notes(results: list[dict]) -> list[str]:
    """Notes for the author where a report and an exit code disagree, or the report is unusable. Red and green keep the
    exit code's meaning: a note never turns a red run green."""
    notes = []
    for r in results:
        rep = r.get("report")
        if not rep:
            continue
        who = f"{r['red_green']} run of {r['name']}"
        if "problem" in rep:
            notes.append(f"{who}: {rep['problem']}. The exit code stays the evidence")
        elif r["status"] == "failed" and rep["failed"] == 0:
            notes.append(f"{who}: exit {r['exit']} but its report lists no failed test case, so it may not have run a test; read its log")
        elif r["status"] == "passed" and rep["failed"]:
            notes.append(f"{who}: exit 0 but its report lists {rep['failed']} failed test case(s); read the report")
    return notes
