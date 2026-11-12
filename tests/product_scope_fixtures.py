"""The files of a product scope and its Intents, built as data and written as a repository, for the tests of what
`aidd validate` and `aidd status` say of them. A test names only what its case turns on."""

from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts src on sys.path)
from helpers import git

from aidd import config, workitems
from aidd.kernel import strict_yaml
from aidd.workitems import product_checks, product_scope, spec_warnings, work_list

PERSON = "Dana <dana@example.com>"
OTHER = "Eli <eli@example.com>"
CONFIG = 'aidd_version: "1.0.0"\nprofile: solo\n'
TODAY = dt.date(2027, 1, 15)
METRIC = {"name": "Tickets answered within a day", "source": "support report", "baseline": "40%", "target": "80%"}
RETIRED = {"measured_on": "2027-01-02", "decision": "retire"}
MET = {"measured_on": "2027-01-02", "actual": "90%", "source": "support report", "decision": "met"}
CONTINUE = {"measured_on": "2027-01-02", "actual": "50%", "source": "support report", "decision": "continue"}
CRITERION = {"id": "S1", "metric": {"name": "Wait", "source": "support report", "target": "1 day"}, "measure_after_days": 30}


def objective(n: int = 1, results: list | None = None) -> dict:
    return {"id": f"Objective-{n}", "title": "Answer support faster", "metric": METRIC, "due": "2027-06-30", **({"results": results} if results else {})}


def requirement(n: int = 1, serves: str | None = "Objective-1", results: list | None = None) -> dict:
    return {
        "id": f"Requirement-{n}",
        "title": "Customers reach an answer",
        **({"serves": serves} if serves else {}),
        **({"results": results} if results else {}),
    }


def outcome(n: int = 1, serves: str | None = "Requirement-1", results: list | None = None) -> dict:
    return {
        "id": f"Outcome-{n}",
        "title": "Customers get a quick answer",
        "metric": METRIC,
        **({"serves": serves} if serves else {}),
        **({"results": results} if results else {}),
    }


def standing(n: int = 1, results: list | None = None) -> dict:
    return {
        "id": f"Outcome-{n}",
        "title": "Answers stay quick",
        "metric": {k: v for k, v in METRIC.items() if k != "baseline"},
        **({"results": results} if results else {}),
    }


def brd(objectives: list | None = None, requirements: list | None = None, **extra) -> dict:
    return {"type": "brd", "sponsor": PERSON, "objectives": objectives or [objective()], "requirements": requirements or [requirement()], **extra}


def smallest_brd(requirements: list | None = None, **extra) -> dict:
    """A BRD of a sponsor and requirements, with no objective for a requirement to serve."""
    return {"type": "brd", "sponsor": PERSON, "requirements": requirements or [requirement(serves=None)], **extra}


def prd(outcomes: list | None = None, **extra) -> dict:
    return {"type": "prd", "outcomes": outcomes or [outcome()], **extra}


def standing_outcomes(outcomes: list | None = None, **extra) -> dict:
    return {"type": "standing-outcomes", "outcomes": outcomes or [standing()], **extra}


def order(ids: list[str], **extra) -> dict:
    return {"type": "intent-order", "owner": PERSON, "order": ids, **extra}


def intent(iid: str = "INTENT-1", serves: str | None = None, phases: tuple[int, ...] = (1,), **extra) -> dict:
    """An Intent with one phase for each count in `phases`, that many slices in it, and, with `serves`, a success criterion."""
    number, listed = 0, []
    for p, count in enumerate(phases, 1):
        slices = []
        for _ in range(count):
            number += 1
            slices.append({"id": f"{iid.replace('INTENT', 'SPEC')}-{number}", "title": "A slice"})
        listed.append({"id": f"P{p}", "name": "A phase", "specs": slices})
    served = {"serves": serves, "success_criteria": [CRITERION]} if serves else {}
    return {"type": "intent", "id": iid, "title": "Quicker answers", "outcome": "Customers wait under a day.", **served, "phases": listed, **extra}


def text(data: dict, body: str = "\n## Notes\n\nSaid in words.\n") -> str:
    return f"---\n{strict_yaml.dump(data)}---\n{body}"


def split(found: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Findings as errors, warnings, and notes."""
    return (
        [f for f in found if not f.startswith(("warning: ", "note: "))],
        [f for f in found if f.startswith("warning: ")],
        [f for f in found if f.startswith("note: ")],
    )


class ScopeCase(unittest.TestCase):
    """A repository in a temporary folder, with a config and the files a case writes. Git starts when a case first commits."""

    def setUp(self):
        self.fresh()

    def fresh(self) -> None:
        """A new repository, for the next row of a table."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root, self.started = Path(tmp.name), False
        self.write(".aidd/config.yaml", CONFIG)

    def write(self, rel: str, content: str | dict) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if isinstance(content, str) else text(content), encoding="utf-8")

    def start(self) -> None:
        """Make the folder a git repository, once."""
        if not self.started:
            git(self.root, "init", "-q", "-b", "main")
            git(self.root, "config", "user.email", "dana@example.com")
            git(self.root, "config", "user.name", "Dana")
            git(self.root, "config", "commit.gpgsign", "false")
            self.started = True

    def commit(self, message: str = "work", *trailers: str, allow_empty: bool = False) -> None:
        self.start()
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", message, *(["--allow-empty"] if allow_empty else []), *[a for t in trailers for a in ("--trailer", t)])

    def hold(self, rel: str, data: dict, approved: dict, ident: str, who: str) -> dict:
        """Commit `data` as it stands without the yes, then `approved` alone, the yes and nothing else, with the person's
        `Approved-by` line and `Approves: <ident>`: the one commit that holds a yes."""
        self.write(rel, data)
        self.commit(f"write {rel}", allow_empty=True)
        self.write(rel, approved)
        self.commit(f"approve {rel}", f"Approved-by: {who}", f"Approves: {ident}")
        return approved

    def approve(self, rel: str, data: dict, at: str = "2027-01-10T09:00:00Z", who: str = PERSON) -> dict:
        """`data` as the person approved it: written with `approved_by` and `approved_at`, in a commit of its own that holds them."""
        return self.hold(rel, data, {**data, "approved_by": who, "approved_at": at}, rel, who)

    def approve_intent(self, rel: str, data: dict, at: str = "2027-01-10T09:00:00Z", who: str = PERSON) -> dict:
        """The Intent `data` as the person approved it: written with `approval`, in a commit of its own that holds it."""
        return self.hold(rel, data, {**data, "approval": {"by": who, "at": at}}, str(data.get("id")), who)

    def config(self) -> config.Config:
        return config.load_file(config.CONFIG_PATH, str(self.root))

    def check(self, today: dt.date = TODAY, max_specs: int = 10) -> tuple[list[str], list[str], list[str]]:
        """What `aidd validate` says of the product scope: each file's own findings, then what the files and the Intents owe
        each other. It is the repository's check without the walk of the other work items, so a table of rows stays quick."""
        scope = product_scope.read(self.root, "product")
        found, _ = work_list.read_work(self.root, None)
        intents = [(p, d) for p, d in found if d.get("type") == "intent"]
        out = [e for f in scope.files.values() for e in workitems.validate_file(self.root / f.path, f.path)]
        out += product_checks.scope_findings(
            scope,
            product_checks.Repository(
                self.root, intents, spec_warnings.statuses(found, frozenset(work_list.approved_versions(self.root, found))), today, max_specs
            ),
        )
        return split(out)

    def repository_check(self, today: dt.date = TODAY) -> tuple[list[str], list[str], list[str]]:
        """What `aidd validate` finds in the whole repository."""
        errors, others = workitems.check_repo(self.root, today)
        return errors, [w for w in others if not w.startswith("note: ")], [w for w in others if w.startswith("note: ")]

    def said(self, found: list[str], *words: str) -> list[str]:
        """The findings that hold every one of `words`."""
        return [f for f in found if all(w in f for w in words)]
