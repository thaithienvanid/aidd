"""This repository's own CI workflows (K14): one workflow for each trigger, so no job shows as skipped; each check runs
once; the one summary job a pull request must pass; the checks that run only when a path they read changed; and the
release's lookups, which find the runs the workflows now make. The table of event by workflow by job in ci.yml's header
is held equal to the files. Textual, as test_action_shape.py is: the runtime has no YAML parser."""

import json
import re
import subprocess
import unittest

from helpers import ROOT, repo_files

WORKFLOWS = ROOT / ".github" / "workflows"
CI_WORKFLOWS = ("ci", "main", "weekly", "standards", "aidd-tests")  # the table's rows; codeql, scorecard, evals, and release have headers of their own
EVENTS = {"pull_request", "push", "schedule", "workflow_dispatch", "merge_group"}


def code(name: str) -> str:
    """A workflow's text without its comment lines."""
    text = (WORKFLOWS / f"{name}.yml").read_text(encoding="utf-8")
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#")) + "\n"


def triggers(name: str) -> list[str]:
    """The events the workflow's top-level `on:` names, in file order."""
    block = re.search(r"(?m)^on:\n((?:[ ].*\n|\n)+)", code(name))
    assert block, name
    return re.findall(r"(?m)^  ([a-z_]+):", block.group(1))


def jobs(name: str) -> dict[str, str]:
    body = code(name).split("\njobs:\n", 1)[1]
    parts = re.split(r"(?m)^  ([a-z][\w-]*):\n", body)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def job_head(job: str) -> str:
    """A job's own keys, before its steps."""
    return job.split("\n    steps:", 1)[0]


def crons(name: str) -> list[str]:
    return re.findall(r'(?m)^    - cron: "([^"]+)"', code(name))


DAY = {"6": "saturday", "1": "monday"}


def events_of(name: str) -> set[str]:
    """The events of a workflow, a schedule named by its day: `schedule_saturday`."""
    out = set()
    for event in triggers(name):
        if event == "schedule":
            out |= {f"schedule_{DAY[c.split()[4]]}" for c in crons(name)}
        else:
            out.add(event)
    return out


class EachWorkflowHasOneTriggerTests(unittest.TestCase):
    def test_no_job_is_skipped_by_its_event(self):
        """A job exists only in the workflow whose trigger runs it: no job-level `if:` reads the event, and the only
        conditions left are the summary job's `always()` and the issue job's own (a stale quote, and an issue wanted)."""
        allowed = {("ci", "ci-passed"): "always()", ("standards", "standards-issue"): None}
        for name in CI_WORKFLOWS:
            for job_name, job in jobs(name).items():
                with self.subTest(workflow=name, job=job_name):
                    cond = re.search(r"(?m)^    if: (.+)$", job_head(job))
                    if (name, job_name) in allowed:
                        self.assertIsNotNone(cond)
                        assert cond is not None
                        if allowed[(name, job_name)]:
                            self.assertEqual(cond.group(1), allowed[(name, job_name)])
                    else:
                        self.assertIsNone(cond, "a job with a condition shows as skipped when it does not hold")
                    self.assertNotIn("github.event_name", cond.group(1) if cond else "")

    def test_the_triggers_of_each_workflow(self):
        want = {
            "ci": {"pull_request"},
            "main": {"push"},
            "weekly": {"schedule", "workflow_dispatch"},
            "standards": {"schedule", "workflow_dispatch"},
            "aidd-tests": {"pull_request", "merge_group"},  # its trigger and concurrency equal the adopter template's (test_release_surface.py)
        }
        for name, events in want.items():
            with self.subTest(name):
                self.assertEqual(set(triggers(name)), events)
        self.assertRegex(code("main"), r"(?m)^  push:\n    branches: \[main\]\n")
        self.assertEqual(crons("weekly"), ["37 3 * * 6"])
        self.assertEqual(crons("standards"), ["41 5 * * 1"])
        for name in ("ci", "main", "weekly", "standards"):
            self.assertNotIn("merge_group", code(name), "no merge queue is set up: RELEASING.md says how to add one")
            self.assertNotIn("pull_request_target", code(name))

    def test_the_header_table_equals_the_triggers_and_jobs_of_the_files(self):
        header = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8").split("\nname: ci\n", 1)[0]
        rows = re.findall(r"(?m)^#   (\S+)\s{2,}(\S+)\s{2,}(\S.*)$", header)
        table = {(wf, job): {e.strip() for e in events.split(",")} for wf, job, events in rows if wf != "workflow"}
        want = {(name, job): set(triggers(name)) for name in CI_WORKFLOWS for job in jobs(name)}
        self.assertEqual(table, want)
        self.assertEqual(len(rows) - 1, len(want), "one row for each job")
        self.assertTrue(set().union(*table.values()) <= EVENTS)

    def test_the_header_table_is_the_only_one_and_each_file_says_why(self):
        for name in CI_WORKFLOWS:
            with self.subTest(name):
                text = (WORKFLOWS / f"{name}.yml").read_text(encoding="utf-8")
                head = text.split("\nname: ", 1)[0]
                self.assertTrue(head.startswith(f"# {name}:") or name == "aidd-tests", head[:60])
                self.assertEqual(head.count("#   workflow "), 1 if name == "ci" else 0)


class CiPassedTests(unittest.TestCase):
    """The branch ruleset requires `ci passed` and `tests` (.github/rulesets/main.json), so neither name changes."""

    def test_the_required_names_are_the_workflows_names(self):
        for rel in (".github/rulesets/main.json", "templates/github/rulesets/main.json"):
            rules = json.loads((ROOT / rel).read_text(encoding="utf-8"))["rules"]
            contexts = sorted(c["context"] for r in rules if r["type"] == "required_status_checks" for c in r["parameters"]["required_status_checks"])
            self.assertEqual(contexts, ["ci passed", "tests"] if "templates" not in rel else contexts, rel)
        ci = jobs("ci")
        self.assertIn("name: ci passed", ci["ci-passed"])
        self.assertIn("tests", jobs("aidd-tests"))
        self.assertEqual(
            json.loads((ROOT / ".github/rulesets/main.json").read_text(encoding="utf-8"))["rules"][3]["parameters"]["strict_required_status_checks_policy"],
            True,
        )

    def test_it_waits_on_every_other_job_and_runs_whatever_they_do(self):
        ci = jobs("ci")
        needs = re.search(r"(?m)^    needs: \[([^\]]*)\]", ci["ci-passed"])
        assert needs
        self.assertEqual(sorted(x.strip() for x in needs.group(1).split(",")), sorted(j for j in ci if j != "ci-passed"))
        self.assertIn("    if: always()", ci["ci-passed"])

    def test_it_fails_when_a_job_it_needs_did_not_succeed_and_passes_when_all_did(self):
        script = re.search(r"(?ms)^        run: \|\n(.*?)\Z", jobs("ci")["ci-passed"])
        assert script
        body = "\n".join(ln[10:] for ln in script.group(1).splitlines())
        cases = {
            "all passed": ("success success", 0),
            "one job": ("success", 0),
            "one failed": ("success failure", 1),
            "one cancelled": ("cancelled success", 1),
            "one skipped": ("success skipped", 1),
            "none": ("", 0),
        }
        for name, (results, status) in cases.items():
            with self.subTest(name):
                done = subprocess.run(["bash", "-ec", body], env={"RESULTS": results, "PATH": "/usr/bin:/bin"}, capture_output=True, text=True, timeout=30)
                self.assertEqual(done.returncode, status, done.stdout + done.stderr)


# The checks that ran on each event at the START of K14 (the ci.yml of commit 5864d063, the manual and scheduled runs
# included), and where each runs now. A check is a step that can fail the run, not a job name. `merge_group` never
# occurred (no queue was set up).
EVERY = {"pull_request", "push", "merge_group", "schedule_saturday", "workflow_dispatch"}
NOT_PR = EVERY - {"pull_request"}
SATURDAY_OR_BY_HAND = {"schedule_saturday", "workflow_dispatch"}
BASE = {
    "gitleaks": EVERY,
    "osv-scanner": EVERY,
    "actionlint": EVERY,
    "zizmor": EVERY,
    "ruff check": EVERY,
    "ruff format": EVERY,
    "mypy": EVERY,
    "import-linter": EVERY,
    "gen-docs check": EVERY | set(),
    "aidd validate": EVERY,
    "stock validator": EVERY,
    "stock yaml reader": EVERY,
    "compileall": EVERY,
    "install.sh syntax": EVERY,
    "shellcheck": EVERY,
    "plugin validation": EVERY,
    "mermaid parse": EVERY,
    "compile on 3.11": EVERY,
    "suite 3.14 with coverage": EVERY,
    "coverage floors": EVERY,
    "suite 3.15": NOT_PR,
    "wheel contents tests": EVERY,
    "wheel install 3.11, 3.14, 3.15": EVERY,
    "zipapp 3.14": EVERY,
    "browser tests 3.14": EVERY,
    "browser tests 3.15": NOT_PR,
    "suite 3.12 and 3.13 in a queue": {"merge_group"},
    "suite on Linux 3.11 to 3.13": SATURDAY_OR_BY_HAND,
    "suite on macOS and Windows": {"workflow_dispatch"},
    "gen-docs check and validate in the matrix": SATURDAY_OR_BY_HAND,
    "sdist tests": SATURDAY_OR_BY_HAND,
    "wheel install on Linux 3.11 and 3.15": SATURDAY_OR_BY_HAND,
    "wheel install on macOS and Windows": {"workflow_dispatch"},
    "standards online": {"schedule_monday", "workflow_dispatch"},
    "tests green on head, red on base, with the browser tests": {"pull_request", "merge_group"},
}
BASE["gen-docs check"] = EVERY


def marker(workflow: str, pattern: str, only: set[str] | None = None) -> tuple[str, str, set[str] | None]:
    return (workflow, pattern, only)


# Where each check is found now: the workflow, a pattern in its code, and the events that narrows the workflow's own (a
# matrix that adds the other operating systems by hand only).
HEAD = {
    "gitleaks": [marker("ci", r"gitleaks/gitleaks/releases")],
    "osv-scanner": [
        marker("ci", r"osv-scanner/v2/cmd/osv-scanner@v2\.7\.0 scan source"),
        marker("weekly", r"osv-scanner/v2/cmd/osv-scanner@v2\.7\.0 scan source"),
    ],
    "actionlint": [marker("ci", r"run: actionlint ")],
    "zizmor": [marker("ci", r"zizmor --config"), marker("weekly", r"zizmor --config")],
    "ruff check": [marker("ci", r"ruff check src")],
    "ruff format": [marker("ci", r"ruff format --check src")],
    "mypy": [marker("ci", r"- run: mypy\n")],
    "import-linter": [marker("ci", r"lint-imports --no-cache")],
    "gen-docs check": [marker("ci", r"python -m aidd gen-docs --check")],
    "aidd validate": [marker("ci", r"python -m aidd validate")],
    "stock validator": [marker("ci", r"test_stock_validator\.py")],
    "stock yaml reader": [marker("ci", r"test_strict_yaml\.py")],
    "compileall": [marker("ci", r"python -m compileall -q src tests")],
    "install.sh syntax": [marker("ci", r"sh -n install\.sh")],
    "shellcheck": [marker("ci", r"shellcheck install\.sh")],
    "plugin validation": [marker("ci", r"claude plugin validate")],
    "mermaid parse": [marker("ci", r"check-mermaid\.mjs")],
    "compile on 3.11": [marker("ci", r"python3\.11 -m compileall -q src tests")],
    "suite 3.14 with coverage": [marker("ci", r"python3\.14 tests/run\.py --coverage")],
    "coverage floors": [marker("ci", r"python3\.14 tests/coverage_floors\.py")],
    "suite 3.15": [marker("main", r"python3\.15 tests/run\.py\n"), marker("weekly", r'python: \["3\.11", "3\.12", "3\.13", "3\.14", "3\.15"\]')],
    "wheel contents tests": [marker("ci", r"test_release_surface\.WheelContentsTests test_bundled_data")],
    "wheel install 3.11, 3.14, 3.15": [marker("ci", r"for py in python3\.11 python3\.14 python3\.15; do")],
    "zipapp 3.14": [marker("ci", r"aidd\.pyz --version")],
    "browser tests 3.14": [
        marker("aidd-tests", r'AIDD_BROWSER_TESTS: "1"'),
        marker("weekly", r"AIDD_BROWSER_TESTS: \$\{\{ runner\.os == 'Linux' && '1' \|\| '' \}\}"),
    ],
    "browser tests 3.15": [
        marker("main", r"python3\.15 tests/run\.py --browser"),
        marker("weekly", r"AIDD_BROWSER_TESTS: \$\{\{ runner\.os == 'Linux' && '1' \|\| '' \}\}"),
    ],
    "suite 3.12 and 3.13 in a queue": [marker("weekly", r'python: \["3\.11", "3\.12", "3\.13", "3\.14", "3\.15"\]')],
    "suite on Linux 3.11 to 3.13": [marker("weekly", r'python: \["3\.11", "3\.12", "3\.13", "3\.14", "3\.15"\]')],
    "suite on macOS and Windows": [
        marker(
            "weekly",
            r"""github\.event_name == 'workflow_dispatch' && fromJSON\('\["ubuntu-latest", "macos-latest", "windows-latest"\]'\)""",
            {"workflow_dispatch"},
        )
    ],
    "gen-docs check and validate in the matrix": [marker("weekly", r"- run: python -m aidd gen-docs --check\n\s+- run: python -m aidd validate")],
    "sdist tests": [marker("weekly", r"The sdist runs its own tests")],
    "wheel install on Linux 3.11 and 3.15": [marker("weekly", r'python: \["3\.11", "3\.15"\]')],
    "wheel install on macOS and Windows": [
        marker(
            "weekly",
            r"""github\.event_name == 'workflow_dispatch' && fromJSON\('\["ubuntu-latest", "macos-latest", "windows-latest"\]'\)[^\n]*\n\s+python: \["3\.11", "3\.15"\]""",
            {"workflow_dispatch"},
        )
    ],
    "standards online": [marker("standards", r"eval standards --online")],
    "tests green on head, red on base, with the browser tests": [marker("aidd-tests", r"--require-green")],
}


def head_cells() -> dict[str, set[str]]:
    """The events each check runs on now: the events of each workflow that holds it, narrowed where a marker says so."""
    out: dict[str, set[str]] = {}
    for check, places in HEAD.items():
        events: set[str] = set()
        for workflow, _pattern, only in places:
            found = events_of(workflow)
            events |= found & only if only else found
        out[check] = events
    return out


QUEUE = "no merge queue is set up, so a merge group never ran (RELEASING.md says how to add one)"
PROVED = "the pull request proved this tree and the ruleset requires an up-to-date branch, so a push to main repeats nothing a pull request ran"
WEEKLY = "the schedule and a manual run keep the matrix, the sdist, the wheel, and the two advisory scans, and drop the checks a change already ran: the release also requires the pull request's ci run and the push run of main.yml"
PUSH_REPEATS = [c for c in BASE if "push" in BASE[c] and c not in ("suite 3.15", "browser tests 3.15")]
# The checks a change ran on every event, which the schedule and a manual run no longer repeat. The two advisory scans stay,
# and the browser tests stay in the weekly matrix.
WEEKLY_DROPS = [c for c in BASE if BASE[c] == EVERY and c not in ("osv-scanner", "zizmor", "browser tests 3.14")]
# aidd-tests keeps its merge_group trigger: its trigger and concurrency equal the adopter template's, and an adopter with a queue needs it.
STILL_IN_A_QUEUE = ("tests green on head, red on base, with the browser tests", "browser tests 3.14")
# Each (event, check) cell that is in the table at the START and not at the head, with why, and each one gained.
LOST = (
    {("merge_group", c): QUEUE for c in BASE if "merge_group" in BASE[c] and c not in STILL_IN_A_QUEUE}
    | {("push", c): PROVED for c in PUSH_REPEATS}
    | {(e, c): WEEKLY for c in WEEKLY_DROPS for e in ("schedule_saturday", "workflow_dispatch")}
)
GAINED = {
    (e, "suite 3.12 and 3.13 in a queue"): "the weekly matrix runs every Linux Python, 3.12 and 3.13 included, where only a queue that does not exist ran them"
    for e in ("schedule_saturday", "workflow_dispatch")
}
RUNS_BEFORE_A_RELEASE = {"pull_request", "push", "schedule_saturday", "schedule_monday", "workflow_dispatch"}


class NoCheckIsDroppedTests(unittest.TestCase):
    """Every (event, check) cell at the START of K14 and at the head: what changed is listed with its reason, and every
    check that ran on an event before a release still runs on at least one."""

    def test_each_check_is_found_where_the_table_says(self):
        for check, places in HEAD.items():
            for workflow, pattern, _only in places:
                with self.subTest(check=check, workflow=workflow):
                    self.assertRegex(code(workflow), pattern)
        self.assertEqual(sorted(HEAD), sorted(BASE), "one row for each check, at the start and now")

    def test_the_cells_that_changed_are_the_cells_we_decided(self):
        head = head_cells()
        lost = {(e, c) for c in BASE for e in BASE[c] - head[c]}
        gained = {(e, c) for c in BASE for e in head[c] - BASE[c]}
        self.assertEqual(lost, set(LOST), "a cell lost without a stated reason, or a stated one still there")
        self.assertEqual(gained, set(GAINED))

    def test_every_check_that_ran_before_a_release_still_runs_before_one(self):
        head = head_cells()
        for check, events in BASE.items():
            with self.subTest(check):
                # The queue's own check never ran, because no queue exists; it must run before a release now.
                self.assertTrue(events & RUNS_BEFORE_A_RELEASE or events == {"merge_group"}, "the table has a check that never ran")
                self.assertTrue(head[check] & RUNS_BEFORE_A_RELEASE, f"{check} runs on no event before a release")
        # A pull request still runs every check it ran, in one place or two: the browser tests moved to aidd-tests.
        for check, events in BASE.items():
            if "pull_request" in events:
                with self.subTest(pull_request=check):
                    self.assertIn("pull_request", head[check])

    def test_the_browser_tests_run_once_on_a_pull_request_and_the_rest_of_the_suite_skips_them(self):
        self.assertIn('AIDD_BROWSER_TESTS: "1"', jobs("aidd-tests")["tests"])
        self.assertNotIn("AIDD_BROWSER_TESTS", code("ci"))
        self.assertNotIn("npm ci --prefix tools/axe", code("ci"))
        self.assertNotIn("apparmor", code("ci"))
        self.assertNotIn("browser", jobs("ci"), "ci has no browser job: aidd-tests runs the browser tests on a pull request")
        main = jobs("main")
        self.assertIn('AIDD_BROWSER_TESTS: "1"', main["browser"])
        self.assertIn('browser: "true"', main["browser"])
        self.assertNotIn("AIDD_BROWSER_TESTS", main["suite"])
        self.assertIn("python3.15 tests/run.py --browser", main["browser"])
        self.assertNotIn("coverage", main["browser"])


class WhatEachWorkflowRunsTests(unittest.TestCase):
    def test_a_pull_request_runs_the_suite_on_3_14_under_coverage_and_never_3_15(self):
        test = jobs("ci")["test"]
        steps = test.split("\n      - ")
        suite = [s for s in steps if "tests/run.py" in s or "-m unittest discover -s tests" in s]
        self.assertEqual(len(suite), 1, suite)
        self.assertIn("python3.14 tests/run.py --coverage", suite[0])
        self.assertNotIn("if:", suite[0])
        floors = [s for s in steps if "python3.14 tests/coverage_floors.py" in s]
        self.assertEqual(len(floors), 1, floors)
        self.assertNotIn("coverage combine", suite[0], "tests/run.py joins the data itself")
        runner = (ROOT / "tests" / "run.py").read_text(encoding="utf-8")
        self.assertIn('"coverage", "combine"', runner)
        self.assertIn('"coverage", "run", "-p", "--branch"', runner)
        self.assertNotIn("fail-under", test)
        self.assertNotIn("python3.15 tests/run.py", test)
        self.assertIn("for py in python3.11 python3.14 python3.15; do", test)
        # It never skips: about sixty test modules read Markdown, so no change is documentation only.
        self.assertNotIn("steps.scope", test)
        self.assertNotIn("paths", code("ci").split("\njobs:\n", 1)[0])
        self.assertIn('python-version: "3.14"', (WORKFLOWS / "aidd-tests.yml").read_text(encoding="utf-8"))

    def test_the_push_to_main_runs_what_a_pull_request_did_not(self):
        main = jobs("main")
        self.assertEqual(sorted(main), ["browser", "suite"])
        self.assertIn('python-version: "3.15"', main["suite"])
        self.assertIn('python-version: "3.15"', main["browser"])
        self.assertNotIn("3.14", code("main"))

    def test_the_weekly_matrix_runs_every_python_on_linux_and_every_os_only_by_hand(self):
        """macOS bills at ten times and Windows at twice the Linux rate in a private repository: the schedule runs Linux
        only, and every OS runs by hand, which the release requires."""
        weekly = jobs("weekly")
        self.assertIn('python: ["3.11", "3.12", "3.13", "3.14", "3.15"]', weekly["matrix"])
        self.assertNotIn("exclude", weekly["matrix"], "no job of ci runs 3.14 or 3.15 on Linux weekly now")
        for name in ("matrix", "wheel"):
            os_line = next(ln for ln in weekly[name].splitlines() if ln.strip().startswith("os:"))
            self.assertIn("github.event_name == 'workflow_dispatch'", os_line, name)
            linux_only = os_line.split("||", 1)[1]
            self.assertIn('["ubuntu-latest"]', linux_only, name)
            self.assertNotIn("macos", linux_only, name)
            self.assertNotIn("windows", linux_only, name)
        for name in ("ci", "main", "standards"):
            self.assertNotIn("macos", code(name))
            self.assertNotIn("windows", code(name))
        self.assertNotIn(
            "pip install -e", "".join(code(n) for n in ("ci", "main", "weekly", "standards")), "an editable install would fetch an unpinned build backend"
        )

    def test_the_dependency_scan_names_every_lock_file_and_allows_none_to_be_missed(self):
        """OSV-Scanner v2.7.0 finds a requirements file only by a name with "requirements" in it, so each lock is named
        with -L; `--allow-no-lockfiles` would hide a lock it did not read. A pull request and the weekly run scan the same."""
        locks = sorted(p.name for p in (ROOT / ".github" / "requirements").iterdir() if p.suffix == ".txt")
        self.assertTrue(locks)
        npm = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "tools").rglob("package-lock.json") if "node_modules" not in p.parts)
        for workflow, job in (("ci", "checks"), ("weekly", "advisories")):
            scan = jobs(workflow)[job].split("osv-scanner/v2/cmd/osv-scanner", 1)[1].split("\n      - ", 1)[0]
            with self.subTest(workflow=workflow):
                for name in locks:
                    self.assertIn(f"-L requirements.txt:.github/requirements/{name}", scan, f"{name} is not passed to the scan")
                for path in npm:
                    self.assertIn(f"-L package-lock.json:{path}", scan, f"{path} is not passed to the scan")
                self.assertNotIn("--allow-no-lockfiles", scan)
                self.assertNotIn("--recursive", scan)

    def test_the_standards_workflow_keeps_the_template_s_conditions(self):
        """The check runs on its own two triggers with no condition; only the issue job has one (test_knowledge_maintenance.py)."""
        standards = jobs("standards")
        self.assertNotRegex(job_head(standards["standards"]), r"(?m)^    if:")
        self.assertIn("open_issue", code("standards"))
        self.assertNotIn("run_standards", code("standards"))


class ScopeTests(unittest.TestCase):
    """Three checks of the `checks` job run only when a path they read changed. Each list is held to what its check reads."""

    @classmethod
    def setUpClass(cls):
        text = jobs("ci")["checks"]
        cls.patterns = dict(re.findall(r"(?m)^          scope (\w+) '([^']+)' '", text))
        cls.files = repo_files()

    def reads(self, name: str, path: str) -> bool:
        return re.search(self.patterns[name], path) is not None

    def test_there_are_exactly_three_scopes_and_every_step_that_uses_one_names_it(self):
        self.assertEqual(sorted(self.patterns), ["mermaid", "plugins", "workflows"])
        text = jobs("ci")["checks"]
        for name in self.patterns:
            self.assertIn(f"steps.scope.outputs.{name} == 'true'", text)
        for step in text.split("\n      - "):
            if "steps.scope" in step and "id: scope" not in step:
                with self.subTest(step=step.splitlines()[0]):
                    self.assertTrue(re.search(r"steps\.scope\.outputs\.(workflows|mermaid|plugins) == 'true'", step))

    def test_the_mermaid_check_reads_every_markdown_file_and_its_own_tool(self):
        """tools/mermaid/check-mermaid.mjs parses the diagrams of `git ls-files "*.md"`: every tracked Markdown file. A
        diagram in another kind of file would never be read, so the test finds none."""
        self.assertIn('git ls-files "*.md"', (ROOT / "tools" / "mermaid" / "check-mermaid.mjs").read_text(encoding="utf-8"))
        for path in self.files:
            if path.endswith(".md") or path.startswith("tools/mermaid/"):
                self.assertTrue(self.reads("mermaid", path), path)
        for path in ("src/aidd/cli/app.py", "pyproject.toml", "schemas/risks.json", "tests/test_ci_workflows.py", ".github/workflows/weekly.yml"):
            self.assertFalse(self.reads("mermaid", path), f"{path} cannot change a diagram")
        self.assertTrue(self.reads("mermaid", ".github/workflows/ci.yml"))
        self.assertTrue(self.reads("mermaid", ".github/actions/setup/action.yml"))

    def test_the_plugin_validation_reads_the_marketplace_the_plugins_and_what_they_name(self):
        """`claude plugin validate` runs on the plugin manifest, the marketplace, and each folder of plugins/. The root
        plugin names its skills folder, and the marketplace names each plugin's folder. Run on a copy that holds only
        these folders (and no src/ or schemas/) it passes, which is how the list was found."""
        step = jobs("ci")["checks"].split("The Claude Code marketplace and plugins validate", 1)[1].split("\n      - ", 1)[0]
        targets = re.search(r"for target in (.+); do", step)
        assert targets
        self.assertEqual(targets.group(1).split(), [".claude-plugin/plugin.json", ".", "plugins/*/"])
        manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        named = [manifest["skills"].removeprefix("./"), ".claude-plugin/marketplace.json", ".claude-plugin/plugin.json"]
        named += [p["source"].removeprefix("./") + "/x" for p in marketplace["plugins"] if p["source"] != "./"]
        for path in named:
            self.assertTrue(self.reads("plugins", path), path)
        for path in self.files:
            if path.startswith((".claude-plugin/", ".agents/", "plugins/", "tools/mermaid/")):
                self.assertTrue(self.reads("plugins", path), path)
        for path in ("src/aidd/cli/app.py", "docs/GUIDE.md", "pyproject.toml", "schemas/risks.json"):
            self.assertFalse(self.reads("plugins", path), f"{path} is no input of the plugin validation")
        for path in (".github/workflows/ci.yml", ".github/actions/setup/action.yml"):
            self.assertTrue(self.reads("plugins", path))

    def test_actionlint_and_zizmor_read_the_workflows_the_actions_the_action_and_the_templates(self):
        text = jobs("ci")["checks"]
        self.assertIn(".github/workflows/*.yml templates/github/aidd-*.yml", text)
        self.assertIn(".github/workflows .github/actions action.yml", text)
        for path in self.files:
            if path.startswith((".github/workflows/", ".github/actions/", "templates/github/")) or path in (
                "action.yml",
                ".github/zizmor.yml",
                ".github/zizmor-templates.yml",
            ):
                self.assertTrue(self.reads("workflows", path), path)
        for path in ("src/aidd/cli/app.py", "docs/GUIDE.md", "tests/test_ci_workflows.py"):
            self.assertFalse(self.reads("workflows", path))

    def test_the_scope_step_reads_the_pull_request_s_diff_without_a_pipe(self):
        """`grep -q` stops at the first match and a pipe would then fail under pipefail, so the step reads a variable."""
        step = jobs("ci")["checks"].split("- id: scope", 1)[1].split("\n      - ", 1)[0]
        self.assertIn("git diff --name-only HEAD^1 HEAD", step)
        self.assertNotRegex(step, r"\|\s*grep")

    def test_a_scope_output_gates_each_skippable_check_and_never_the_suite(self):
        ci = code("ci")
        self.assertEqual(len(re.findall(r"(?m)^\s+(?:- )?if: steps\.scope", ci)), 6)
        self.assertNotIn("steps.scope", jobs("ci")["test"])


class LocalActionTests(unittest.TestCase):
    """.github/actions/setup holds the steps the workflows repeat. A local action is read from the checked-out tree, so
    the checkout stays in each job, before the first step that uses it."""

    def setUp(self):
        self.action = (ROOT / ".github" / "actions" / "setup" / "action.yml").read_text(encoding="utf-8")

    def test_every_action_in_it_is_pinned_by_sha_with_its_version(self):
        uses = re.findall(r"(?m)^\s*-?\s*uses: (\S+)(.*)$", self.action)
        self.assertTrue(uses)
        for ref, comment in uses:
            self.assertRegex(ref, r"@[0-9a-f]{40}$", ref)
            self.assertRegex(comment, r"# v\d+\.\d+\.\d+", ref)

    def test_no_input_reaches_a_script(self):
        for script in re.findall(r"(?m)^\s+run: (.+)$", self.action):
            self.assertNotIn("${{", script)
            self.assertNotIn("inputs.", script)

    def test_each_job_that_uses_it_checks_out_first_and_keeps_no_credentials(self):
        for name in ("ci", "main", "weekly", "standards"):
            for job_name, job in jobs(name).items():
                steps = job.split("\n      - ")[1:]
                for i, step in enumerate(steps):
                    if "uses: ./.github/actions/setup" in step:
                        with self.subTest(workflow=name, job=job_name):
                            self.assertTrue(any("actions/checkout@" in s for s in steps[:i]), "no checkout before the local action")
                self.assertEqual(job.count("actions/checkout@"), job.count("persist-credentials: false"), (name, job_name))

    def test_aidd_tests_and_the_adopter_templates_keep_their_own_steps(self):
        for path in [WORKFLOWS / "aidd-tests.yml", *sorted((ROOT / "templates" / "github").glob("*.yml"))]:
            self.assertNotIn("./.github/actions", path.read_text(encoding="utf-8"), path.name)


class ReleaseLookupTests(unittest.TestCase):
    """release.yml finds the runs the workflows now make: the full matrix is a manual run of weekly.yml, the push run is
    main.yml's, and the pull request's ci run is read on its head."""

    def setUp(self):
        self.release = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
        self.queries = re.findall(r"actions/workflows/([\w.-]+)/runs\?([^\"']+)", self.release)

    def test_each_query_names_a_workflow_that_has_the_event_it_asks_for(self):
        self.assertEqual(sorted(w for w, _ in self.queries), ["aidd-tests.yml", "ci.yml", "main.yml", "weekly.yml"])
        for workflow, query in self.queries:
            with self.subTest(workflow=workflow):
                self.assertTrue((WORKFLOWS / workflow).is_file())
                event = re.search(r"event=(\w+)", query)
                if event:
                    self.assertIn(event.group(1), triggers(workflow.removesuffix(".yml")), f"{workflow} never runs on {event.group(1)}")
                self.assertIn("status=success", query)

    def test_the_lookups(self):
        queries = dict(self.queries)
        self.assertEqual(queries["main.yml"], "head_sha=$GITHUB_SHA&branch=main&event=push&status=success")
        self.assertEqual(queries["weekly.yml"], "head_sha=$GITHUB_SHA&event=workflow_dispatch&status=success")
        self.assertEqual(queries["ci.yml"], "head_sha=$head&event=pull_request&status=success")
        self.assertEqual(queries["aidd-tests.yml"], "head_sha=$head&status=success")
        self.assertNotIn("event=schedule", self.release)
        self.assertNotIn("event=$event", self.release)


class LeastPrivilegeTests(unittest.TestCase):
    """The split gives no workflow more than the one workflow had: read-only at the top, `issues: write` only in the
    standards issue job, no secret, no `pull_request_target`, and no event field in a script."""

    def test_read_only_at_the_top_and_no_wider_job(self):
        for name in ("ci", "main", "weekly", "standards"):
            with self.subTest(name):
                text = code(name)
                self.assertIn("\npermissions:\n  contents: read\n", text)
                self.assertNotRegex(text, r"(?m)^\s+(contents|pull-requests|actions|checks|statuses|packages|id-token|attestations): write")
                self.assertNotIn("secrets.", text)
                self.assertNotIn("pull_request_target", text)
        self.assertEqual(code("standards").count("issues: write"), 1)
        self.assertIn("issues: write", jobs("standards")["standards-issue"])
        for name in ("ci", "main", "weekly"):
            self.assertNotIn("issues: write", code(name))
            for job in jobs(name).values():
                self.assertNotIn("permissions:", job, "no job holds more than the top level gives")

    def test_every_action_is_pinned_by_sha_and_no_event_field_reaches_a_script(self):
        for name in ("ci", "main", "weekly", "standards"):
            text = code(name)
            for ref, comment in re.findall(r"(?m)^\s+(?:- )?uses: (\S+)(.*)$", text):
                if ref.startswith("./.github/actions/"):
                    continue
                with self.subTest(workflow=name, ref=ref):
                    self.assertRegex(ref, r"@[0-9a-f]{40}$")
                    self.assertRegex(comment, r"# v\d+\.\d+\.\d+")
            for script in re.findall(r"(?ms)^\s+run: \|\n(.*?)(?=^\s{6}- |^  \w|\Z)", text):
                self.assertNotIn("github.event", script, name)
                self.assertNotIn("${{ github.head_ref", script, name)


if __name__ == "__main__":
    unittest.main()
