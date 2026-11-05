"""The test runner's controls and the `extends` fetch's defenses: what `aidd test` and a config's URL parent may
never do. Ported from the suite before the rebuild."""

from pathlib import Path
from unittest import mock
import contextlib
import io
import json
import os
import shlex
import shutil
import socket
import sys
import tempfile
import unittest

from helpers import git
from helpers import RepoTemplateCase
from helpers import aidd_here, build_once, repo_state

from aidd.cli import app
from aidd.config import extends
from aidd.testing import runner as test_runner
from aidd.testing.runner import select_tests
from aidd.kernel import documents, egress, http, processes
from aidd.kernel import git as gitutil

CONFIG = """aidd_version: "1.0.0"
profile: team
owners:
  approvers: [bob]
  specialists:
    security: ["@sec"]
tests:
  - name: unit
    command: ["{py}", -c, print('suite ok')]
"""
SPEC = """---
aidd_version: "1.0.0"
type: spec
id: SPEC-1
title: Greeting says hello
owner_team: core
change_type: feat
route: normal
confidence: high
open_questions: []
trace_id: spec-1
assisted_by: []
rollback: Revert the PR.
risk:
  summary: Adds a greeting function.
  dimensions: []
  reversible: true
tasks:
  - id: T1
    title: Implement greet
    scope: [app/]
tests:
  files: [checks/test_greet.py]
  commands:
    - name: greet
      command: ["{py}", checks/test_greet.py]
      new_behavior: true
---
## Context
Tiny example.
## Acceptance
Invariant: greet() returns "hello".
"""
TEST = "import sys\nsys.path.insert(0, '.')\nfrom app.greet import greet\nassert greet() == 'hello'\nprint('ok')\n"
SPEC_FIELDS = {
    "owner_team: maintainers": "owner_team: shop",  # solo's default team
    "assisted_by: []": "assisted_by: [claude-code/claude-opus-5-5]",
    'summary: "TODO: who or what behaves differently after this change"': "summary: Cart totals can apply a discount.",
    'title: "TODO: the first slice"': "title: Add discount()",
    'scope: ["src/TODO/"]': "scope: [app/discount.py]",
    'files: ["tests/TODO"]': "files: [tests/test_discount.py]",
    'command: ["TODO"]': f'command: [{json.dumps(sys.executable)}, "-m", "unittest", "tests.test_discount"]',
    "TODO: quote the request.": "Checkout needs a percentage discount.",
    "- A1: TODO: given ..., when ..., then ...": "- A1: given a total of 200, when a 10% discount applies, then the total is 180",
    "TODO: the approach.": "One pure function, discount(total, percent), in app/discount.py.",
    "TODO: how to undo it.": "Revert the change; nothing is stored.",
}


def _resolves_to(*ips):
    """getaddrinfo answering each call with the next address (the last one repeats): DNS rebinding in a box."""
    answers = list(ips)

    def getaddrinfo(host, port, proto=0, *a, **k):
        ip = answers.pop(0) if len(answers) > 1 else answers[0]
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (ip, port))]

    return getaddrinfo


PY = sys.executable


DOCS_CHECK = """  - name: docs
    command: ["{py}", -c, print('docs ok')]
    when_changed: ["docs/**"]
"""


def _commit(root, message: str, files: dict[str, str] | None = None) -> str:
    for rel, text in (files or {}).items():
        p = Path(root, rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", message, "--allow-empty")
    return git(root, "rev-parse", "HEAD")


def _spec_and_tests(root) -> None:
    git(root, "switch", "-qc", "discount")
    run = aidd_here("new", "spec", "SPEC-1", "--title", "Apply a percentage discount", "--change-type", "feat", cwd=root)
    assert run.returncode == 0, run.stdout + run.stderr
    spec = Path(root, "specs/SPEC-1.md")
    text = spec.read_text(encoding="utf-8")
    for old, new in SPEC_FIELDS.items():
        text = text.replace(old, new)
    spec.write_text(text, encoding="utf-8")
    Path(root, "tests/test_discount.py").write_text(
        "import unittest\n\nfrom app.discount import discount\n\n\nclass Discount(unittest.TestCase):\n    def test_ten_percent(self):\n        self.assertEqual(discount(200, 10), 180)\n",
        encoding="utf-8",
    )
    _commit(root, "spec: SPEC-1 and its test\n\nAssisted-by: claude-code/claude-opus-5-5")


def spec_and_tests(root) -> None:
    """On a new branch: SPEC-1 and its failing test, committed. Built once in a test process from each starting state;
    a later call from the same state copies it."""
    build_once(("spec and tests", repo_state(root)), root, lambda: _spec_and_tests(root))


def run_cli(root, *argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.chdir(root), contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = app.main(list(argv))
    return code, out.getvalue()


def _build_shop(root: Path, profile: str, approvers: str, extra: str) -> None:
    git(root, "init", "-q", "-b", "main")
    for k, v in (("user.email", "me@example.com"), ("user.name", "Me"), ("commit.gpgsign", "false")):
        git(root, "config", k, v)
    for rel, text in {
        ".gitignore": "__pycache__/\n/.aidd/*/\n",
        "app/__init__.py": "",
        "tests/__init__.py": "",
        "app/cart.py": "def total(items):\n    return sum(items)\n",
        "tests/test_cart.py": "import unittest\nfrom app.cart import total\n\n\nclass Cart(unittest.TestCase):\n    def test_total(self):\n        self.assertEqual(total([1, 2]), 3)\n",
    }.items():
        Path(root, rel).parent.mkdir(parents=True, exist_ok=True)
        Path(root, rel).write_text(text, encoding="utf-8")
    _commit(root, "scaffold")
    suite = f"{shlex.quote(sys.executable)} -m unittest"
    run = aidd_here("init", "--profile", profile, "--approvers", approvers, "--test", suite, "--ci", "none", "--harness", "none", cwd=root)
    assert run.returncode == 0, run.stdout + run.stderr
    if extra:
        with open(Path(root, ".aidd", "config.yaml"), "a", encoding="utf-8") as fh:
            fh.write(extra)
    _commit(root, "chore: adopt aidd")


def shop(root: Path, profile: str = "solo", approvers: str = "email:me@example.com", extra: str = "") -> None:
    """A small Python shop adopted with `profile`: app/cart.py, its test, and the unittest suite as `tests`. Built once
    in a test process for each set of arguments; a later call copies it."""
    build_once(("shop", profile, approvers, extra), root, lambda: _build_shop(root, profile, approvers, extra))


@unittest.skipUnless(shutil.which("git"), "git is required")
class SpecPhaseTests(RepoTemplateCase):
    """A branch that holds only the Spec and its tests: `aidd test` exits 0 with the red runs as early proof, and the
    evidence marks the Spec phase."""

    keep_git_reads = True

    @classmethod
    def build_template(cls, root):
        shop(root, "team", "email:alice@example.com")
        spec_and_tests(root)

    def test_aidd_test_exits_0_and_keeps_the_red_runs(self):
        code, out = run_cli(self.root, "test", "--base", "main")
        self.assertEqual(code, 0, out)
        self.assertIn("[..] green", out)  # the failing green runs are expected, and marked so
        self.assertIn("[ok] red   acceptance", out)  # red on base: early proof the test detects the change
        self.assertIn("Spec phase", out)
        ev = test_runner.json.loads(Path(self.root, ".aidd/evidence/evidence.json").read_text(encoding="utf-8"))
        self.assertTrue(ev["spec_phase"])


class RunnerTests(unittest.TestCase):
    def test_timeout_and_not_started(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "x.log"
            r = test_runner.run_test_command([sys.executable, "-c", "import time; time.sleep(5)"], cwd=d, log=log, timeout_seconds=0.2)
            self.assertEqual((r["status"], r["exit"]), ("timeout", None))
            r = test_runner.run_test_command(["/nonexistent/binary"], cwd=d, log=log, timeout_seconds=5)
            self.assertEqual(r["status"], "not_started")


class StreamingLogCapTests(unittest.TestCase):
    """C-09: a test command's log stays under the cap while it runs, not only after it exits."""

    def test_the_log_never_grows_past_the_cap(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "green-x.log"
            probe = (
                "import os, sys, time\n"
                "sys.stdout.buffer.write(b'A' * 400000); sys.stdout.flush(); time.sleep(0.5)\n"
                "size = os.path.getsize(sys.argv[1])\n"
                "sys.exit(0 if size <= 3000 else 1)\n"
            )
            with mock.patch.object(test_runner, "MAX_LOG_BYTES", 2000):
                result = test_runner.run_test_command([sys.executable, "-c", probe, str(log)], cwd=d, log=log, timeout_seconds=60)
            self.assertEqual(result["status"], "passed", log.read_bytes()[-200:])
            data = log.read_bytes()
            self.assertLessEqual(len(data), 2000 + len(test_runner.TRUNCATED))
            self.assertTrue(data.endswith(test_runner.TRUNCATED))


@unittest.skipUnless(shutil.which("git"), "git is required")
class ChangedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        py = sys.executable.replace("\\", "/")
        git(self.root, "init", "-q", "-b", "main")
        for k, v in (("user.email", "alice@example.com"), ("user.name", "Alice"), ("commit.gpgsign", "false")):
            git(self.root, "config", k, v)
        (self.root / ".aidd").mkdir()
        (self.root / ".aidd/config.yaml").write_text(CONFIG.format(py=py) + DOCS_CHECK.format(py=py), encoding="utf-8")
        (self.root / ".gitignore").write_text("/.aidd/*/\n", encoding="utf-8")
        (self.root / "app").mkdir()
        (self.root / "app/__init__.py").write_text("", encoding="utf-8")
        (self.root / "docs").mkdir()
        (self.root / "docs/guide.md").write_text("guide\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "base")
        git(self.root, "checkout", "-qb", "feature")
        (self.root / "specs").mkdir()
        (self.root / "specs/SPEC-1.md").write_text(SPEC.format(py=py), encoding="utf-8")
        (self.root / "checks").mkdir()
        (self.root / "checks/test_greet.py").write_text(TEST, encoding="utf-8")
        (self.root / "app/greet.py").write_text("def greet():\n    return 'hello'\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "Add greet")
        self.out = self.root / ".aidd" / "evidence"

    def tearDown(self):
        self.tmp.cleanup()

    def names(self, ev):
        return sorted((r["name"], r["red_green"]) for r in ev["results"])

    def test_changed_runs_what_the_working_tree_selects_green_only_and_marks_it_partial(self):
        ev, notes = test_runner.run_tests(repo=str(self.root), base="main", out_dir=str(self.out), changed=True)
        # The Spec's command runs (its Task scope changed), the suite runs, the docs check does not; no red phase.
        self.assertEqual(self.names(ev), [("greet", "green"), ("unit", "green")])
        self.assertIs(ev["partial"], True)
        self.assertTrue(any(n.startswith("partial:") for n in notes))
        # An uncommitted docs edit selects the docs check too.
        (self.root / "docs/guide.md").write_text("guide, edited\n", encoding="utf-8")
        ev, _ = test_runner.run_tests(repo=str(self.root), base="main", out_dir=str(self.out), changed=True)
        self.assertEqual(self.names(ev), [("docs", "green"), ("greet", "green"), ("unit", "green")])

    def test_select_changed_needs_a_matching_path(self):
        spec_cmd = ({"name": "s", "command": ["x"]}, "spec")
        suite = ({"name": "u", "command": ["y"]}, "config")
        declared = {"tasks": [{"scope": ["app/"]}], "tests": {"files": ["checks/test_greet.py"]}}
        self.assertEqual(test_runner.select_changed([spec_cmd, suite], declared, []), [])
        self.assertEqual(test_runner.select_changed([spec_cmd, suite], declared, ["README.md"]), [suite])
        self.assertEqual(test_runner.select_changed([spec_cmd, suite], declared, ["checks/test_greet.py"]), [spec_cmd, suite])

    def test_watch_reruns_on_a_change_and_stops_on_ctrl_c(self):
        runs = []
        sleeps = iter(range(10))

        def sleep(_):
            n = next(sleeps)
            if n == 1:
                (self.root / "app/greet.py").write_text("def greet():\n    return 'hello!'\n", encoding="utf-8")
            if n == 3:
                raise KeyboardInterrupt

        code = test_runner.watch_tests(lambda: runs.append(1), repo=str(self.root), interval_seconds=0, exclude=".aidd/evidence", sleep=sleep)
        self.assertEqual((code, len(runs)), (0, 2))

    def test_watch_ignores_what_the_run_itself_writes_to_the_evidence_folder(self):
        runs = []

        def run_once():
            runs.append(1)
            self.out.mkdir(exist_ok=True)
            (self.out / "evidence.json").write_text(str(len(runs)), encoding="utf-8")

        sleeps = iter(range(3))

        def sleep(_):
            if next(sleeps) == 2:
                raise KeyboardInterrupt

        test_runner.watch_tests(run_once, repo=str(self.root), interval_seconds=0, exclude=".aidd/evidence", sleep=sleep)
        self.assertEqual(len(runs), 1)


class GitCallsAreBoundedTests(unittest.TestCase):
    """Every git call has a timeout, and a git failure is a GitError, never a leaked CalledProcessError."""

    def test_materialize_raises_git_error_for_a_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q", "-b", "main")
            git(d, "commit", "-q", "--allow-empty", "-m", "x")
            head = git(d, "rev-parse", "HEAD")
            with self.assertRaises(gitutil.GitError):
                test_runner._materialize(d, head, ["tests/missing.py"], str(Path(d) / "out"))

    def test_materialize_never_writes_outside_its_root(self):
        # S9: a test file reached through a symlink the base checkout holds, or by `..`, is refused before any write.
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
            git(d, "init", "-q", "-b", "main")
            (Path(d) / "tests").mkdir()
            (Path(d) / "tests" / "test_x.py").write_text("x = 1\n", encoding="utf-8")
            git(d, "add", ".")
            git(d, "commit", "-q", "-m", "x")
            head = git(d, "rev-parse", "HEAD")
            dest = Path(d) / "out"
            dest.mkdir()
            (dest / "tests").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(RuntimeError) as refused:
                test_runner._materialize(d, head, ["tests/test_x.py"], str(dest))
            self.assertIn("Rename it in the Spec's `tests.files`", str(refused.exception))
            self.assertEqual(list(Path(outside).iterdir()), [])
            with mock.patch.object(gitutil, "show_bytes", return_value=b"x = 1\n"), self.assertRaises(RuntimeError):
                test_runner._materialize(d, head, ["../escaped.py"], str(dest))
            self.assertFalse((Path(d) / "escaped.py").exists())
            test_runner._materialize(d, head, ["tests/test_x.py"], str(Path(d) / "fresh"))
            self.assertEqual((Path(d) / "fresh" / "tests" / "test_x.py").read_text(encoding="utf-8"), "x = 1\n")


class RunnerValidatesTheSpecTests(unittest.TestCase):
    """The runner reads the Spec with its schema, so a test name such as `../../x` never chooses where a log is written."""

    def test_a_spec_that_fails_its_schema_runs_nothing(self):

        py = PY.replace("\\", "/")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            root.mkdir()
            marker = Path(d) / "ran"
            git(root, "init", "-q", "-b", "main")
            (root / ".aidd").mkdir()
            (root / ".aidd/config.yaml").write_text(CONFIG.format(py=py), encoding="utf-8")
            git(root, "add", ".")
            git(root, "commit", "-qm", "base")
            git(root, "checkout", "-qb", "feature")
            (root / "specs").mkdir()
            (root / "checks").mkdir()
            (root / "checks/test_greet.py").write_text("print('x')\n", encoding="utf-8")
            spec = SPEC.format(py=py).replace("name: greet", 'name: "../../../../escape"')
            spec = spec.replace('command: ["' + py + '", "checks/test_greet.py"]', f"command: [{py!r}, '-c', \"open({str(marker)!r}, 'w')\"]")
            (root / "specs/SPEC-1.md").write_text(spec, encoding="utf-8")
            git(root, "add", ".")
            git(root, "commit", "-qm", "spec")
            with self.assertRaises(documents.DocumentError) as cm:
                test_runner.run_tests(repo=str(root), base="main", out_dir=str(root / ".aidd" / "evidence"))
            self.assertIn("name", str(cm.exception))
            self.assertFalse(marker.exists())
            self.assertFalse((Path(d) / "escape.log").exists())

    def test_a_run_that_writes_the_config_or_a_frozen_test_writes_no_evidence(self):
        """Containment by hashes: the config and every file the Spec freezes read the same after the run as before it,
        or the run fails and writes no evidence, so a test that rewrites its own test or the config proves nothing."""

        py = PY.replace("\\", "/")
        for target in (".aidd/config.yaml", "checks/test_greet.py"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as d:
                root = Path(d) / "repo"
                root.mkdir()
                git(root, "init", "-q", "-b", "main")
                (root / ".aidd").mkdir()
                (root / ".aidd/config.yaml").write_text(CONFIG.format(py=py), encoding="utf-8")
                git(root, "add", ".")
                git(root, "commit", "-qm", "base")
                git(root, "checkout", "-qb", "feature")
                (root / "specs").mkdir()
                (root / "checks").mkdir()
                (root / "checks/test_greet.py").write_text("print('x')\n", encoding="utf-8")
                write = f"open({target!r}, 'a').write('# changed by the run\\n')"
                spec = SPEC.format(py=py).replace('command: ["' + py + '", checks/test_greet.py]', f"command: [{py!r}, '-c', {write!r}]")
                self.assertIn("changed by the run", spec)
                (root / "specs/SPEC-1.md").write_text(spec, encoding="utf-8")
                git(root, "add", ".")
                git(root, "commit", "-qm", "spec")
                with self.assertRaises(RuntimeError) as cm:
                    test_runner.run_tests(repo=str(root), base="main", out_dir=str(root / ".aidd" / "evidence"), red=False)
                self.assertIn(target, str(cm.exception))
                self.assertFalse((root / ".aidd/evidence/evidence.json").exists())

    def test_bytecode_and_test_caches_beside_frozen_tests_are_no_change(self):
        """Running a Python test writes `__pycache__` and pytest's cache beside it: never a change to the frozen tests."""

        py = PY.replace("\\", "/")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            root.mkdir()
            git(root, "init", "-q", "-b", "main")
            (root / ".aidd").mkdir()
            (root / ".aidd/config.yaml").write_text(CONFIG.format(py=py), encoding="utf-8")
            git(root, "add", ".")
            git(root, "commit", "-qm", "base")
            git(root, "checkout", "-qb", "feature")
            (root / "specs").mkdir()
            (root / "checks").mkdir()
            (root / "checks/test_greet.py").write_text("print('x')\n", encoding="utf-8")
            write = "import os; os.makedirs('checks/__pycache__', exist_ok=True); open('checks/__pycache__/test_greet.cpython-314.pyc', 'w').write('x')"
            spec = SPEC.format(py=py).replace("files: [checks/test_greet.py]", "files: [checks/**]")
            spec = spec.replace('command: ["' + py + '", checks/test_greet.py]', f"command: [{py!r}, '-c', {write!r}]")
            self.assertIn("checks/**", spec)
            (root / "specs/SPEC-1.md").write_text(spec, encoding="utf-8")
            git(root, "add", ".")
            git(root, "commit", "-qm", "spec")
            test_runner.run_tests(repo=str(root), base="main", out_dir=str(root / ".aidd" / "evidence"), red=False)
            self.assertTrue((root / ".aidd/evidence/evidence.json").exists())

    def test_a_red_run_in_place_that_writes_a_frozen_test_writes_no_evidence(self):
        """CI runs red in place (`--red-in-place`), and its forced checkout back to the head would discard what a red
        command wrote: the check runs in the red tree, after each command, before that checkout."""

        py = PY.replace("\\", "/")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            root.mkdir()
            git(root, "init", "-q", "-b", "main")
            (root / ".aidd").mkdir()
            (root / ".aidd/config.yaml").write_text(CONFIG.format(py=py), encoding="utf-8")
            git(root, "add", ".")
            git(root, "commit", "-qm", "base")
            git(root, "checkout", "-qb", "feature")
            (root / "specs").mkdir()
            (root / "checks").mkdir()
            (root / "checks/test_greet.py").write_text("print('x')\n", encoding="utf-8")
            # Only on the base, where the Spec is not there yet: the red run rewrites its own frozen test.
            write = "import os; os.path.exists('specs/SPEC-1.md') or open('checks/test_greet.py', 'a').write('# red\\n')"
            spec = SPEC.format(py=py).replace('command: ["' + py + '", checks/test_greet.py]', f"command: [{py!r}, '-c', {write!r}]")
            (root / "specs/SPEC-1.md").write_text(spec, encoding="utf-8")
            git(root, "add", ".")
            git(root, "commit", "-qm", "spec")
            with self.assertRaises(RuntimeError) as cm:
                test_runner.run_tests(repo=str(root), base="main", out_dir=str(root / ".aidd" / "evidence"), red=True, red_in_place=True)
            self.assertIn("the red run of greet", str(cm.exception))
            self.assertFalse((root / ".aidd/evidence/evidence.json").exists())
            self.assertEqual(git(root, "rev-parse", "--abbrev-ref", "HEAD").strip(), "feature")  # back on the branch

    def test_log_path_refuses_a_name_that_climbs_out(self):
        with tempfile.TemporaryDirectory() as d:
            logs = Path(d) / "out" / "logs"
            self.assertEqual(test_runner.log_path(logs, "green", "unit"), logs / "green-unit.log")
            with self.assertRaises(RuntimeError):
                test_runner.log_path(logs, "green", "../../../escape")


class ExtendsFetchAddressTests(unittest.TestCase):
    """CGNAT addresses fail the check, and the fetch connects to the address it checked (no DNS rebinding)."""

    def test_non_public_classes_are_refused(self):
        for ip, address_type in (
            ("100.64.0.1", "CGNAT"),
            ("100.127.255.254", "CGNAT"),
            ("10.1.2.3", "private"),
            ("192.168.1.1", "private"),
            ("::ffff:10.0.0.1", "private"),
            ("::ffff:127.0.0.1", "loopback"),
            ("fd00::1", "private"),
        ):
            with self.subTest(ip=ip), mock.patch("socket.getaddrinfo", _resolves_to(ip)), self.assertRaises(http.HttpError) as cm:
                egress.check_public_address("presets.example.com")
            self.assertIn(address_type, str(cm.exception))

    def test_a_public_address_is_returned_for_pinning(self):
        with mock.patch("socket.getaddrinfo", _resolves_to("93.184.216.34")):
            self.assertEqual(egress.check_public_address("presets.example.com"), "93.184.216.34")

    def test_plain_http_is_refused_before_any_lookup(self):
        with mock.patch("socket.getaddrinfo", side_effect=AssertionError("resolved")), self.assertRaises(http.HttpError):
            egress.fetch_text("http://presets.example.com/aidd.yaml")

    def test_the_fetch_connects_to_the_vetted_address_even_if_dns_changes(self):
        connected = []

        def create_connection(address, *a, **k):
            connected.append(address[0])
            raise OSError("stop here")

        with (
            mock.patch.dict(os.environ, {"HTTPS_PROXY": "", "https_proxy": ""}),
            mock.patch("socket.getaddrinfo", _resolves_to("93.184.216.34", "127.0.0.1")),
            mock.patch("socket.create_connection", create_connection),
            mock.patch("time.sleep"),
            self.assertRaises(http.HttpError),
        ):
            egress.fetch_text("https://presets.example.com/aidd.yaml")
        self.assertTrue(connected)
        self.assertEqual(set(connected), {"93.184.216.34"})

    def test_the_extends_chain_stops_at_its_depth_limit_and_says_so(self):
        texts = {f"p{i}.toml": f'aidd_version: "1.0.0"\nprofile: solo\nextends: [{{path: "p{i + 1}.toml"}}]\n' for i in range(10)}
        warns: list[str] = []
        root = 'aidd_version: "1.0.0"\nprofile: solo\nextends: [{path: p0.toml}]\n'
        out = extends.collect_extends(root, read=texts.get, fetch=lambda u: None, warnings=warns)
        self.assertEqual(len(out), extends.MAX_EXTENDS_DEPTH + 1)
        self.assertTrue(any("deeper than" in w for w in warns), warns)


class RedTeamTests(unittest.TestCase):
    def test_runner_scrubs_secrets_from_child_processes(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "cmd.log"
            cmd = [sys.executable, "-c", "import os, json; print(json.dumps(dict(os.environ)))"]
            secret_env = {k: "secret_val" for k in processes.SECRET_ENV}
            with mock.patch.dict(os.environ, secret_env):
                test_runner.run_test_command(cmd, cwd=d, log=log, timeout_seconds=10)
            captured = json.loads(log.read_text(encoding="utf-8").strip())
            for k in processes.SECRET_ENV:
                self.assertNotIn(k, captured)

    def test_runner_scrubs_every_credential_like_variable_unless_passed_by_name(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "cmd.log"
            cmd = [sys.executable, "-c", "import os, json; print(json.dumps(dict(os.environ)))"]
            creds = {"NPM_TOKEN": "t", "AWS_SECRET_ACCESS_KEY": "s", "DB_PASSWORD": "p", "STRIPE_API_KEY": "k", "HARMLESS": "h"}
            with mock.patch.dict(os.environ, creds):
                test_runner.run_test_command(cmd, cwd=d, log=log, timeout_seconds=10)
                scrubbed = json.loads(log.read_text(encoding="utf-8").strip())
                test_runner.run_test_command(cmd, cwd=d, log=log, timeout_seconds=10, pass_env=["NPM_TOKEN"])
                passed = json.loads(log.read_text(encoding="utf-8").strip())
            self.assertEqual({k for k in creds if k in scrubbed}, {"HARMLESS"})
            self.assertEqual({k for k in creds if k in passed}, {"HARMLESS", "NPM_TOKEN"})

    def test_extends_ssrf_non_public_addresses_refused(self):
        warns = []
        cfg = 'aidd_version: "1.0.0"\nprofile: solo\nextends: [{ url: "https://169.254.169.254/meta", sha256: "' + ("0" * 64) + '" }]'
        out = extends.collect_extends(cfg, read=lambda p: None, fetch=lambda u: "forbidden", warnings=warns)
        self.assertEqual(out, {})
        self.assertTrue(any("link-local" in w for w in warns))


class RunnerIsolationTests(unittest.TestCase):
    def test_runner_caps_log_size(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "big.log"
            cmd = [sys.executable, "-c", f"import sys; sys.stdout.buffer.write(b'A' * {test_runner.MAX_LOG_BYTES + 500})"]
            r = test_runner.run_test_command(cmd, cwd=d, log=log, timeout_seconds=10)
            self.assertEqual(r["status"], "passed")
            self.assertLessEqual(log.stat().st_size, test_runner.MAX_LOG_BYTES + 200)
            self.assertIn(b"... [truncated by aidd runner: log exceeded limit] ...", log.read_bytes())


class ExtendsSSRFDefensesTests(unittest.TestCase):
    def test_refuse_file_scheme(self):
        config_text = 'aidd_version: "1.0.0"\nprofile: solo\nextends: [{ url: "file:///etc/hosts", sha256: "' + "0" * 64 + '" }]\n'
        calls = []
        warns = []
        res = extends.collect_extends(config_text, read=lambda p: None, fetch=lambda u, calls=calls: calls.append(u), warnings=warns)
        self.assertEqual(calls, [])
        self.assertEqual(res, {})
        self.assertTrue(any("refused scheme 'file'" in w for w in warns), warns)

    def test_refuse_https_without_sha256(self):
        config_text = 'aidd_version: "1.0.0"\nprofile: solo\nextends: [{url: https://example.com/parent.yaml}]\n'
        calls = []
        warns = []
        res = extends.collect_extends(config_text, read=lambda p: None, fetch=lambda u, calls=calls: calls.append(u), warnings=warns)
        self.assertEqual(calls, [])
        self.assertEqual(res, {})
        self.assertTrue(any("does not match schema" in w for w in warns), warns)

    def test_refuse_non_public_addresses(self):
        bad_ips = [
            ("127.0.0.1", "loopback"),
            ("10.0.0.1", "private"),
            ("169.254.169.254", "link-local"),
            ("::1", "loopback"),
        ]
        for ip, expected_class in bad_ips:
            host_part = f"[{ip}]" if ":" in ip else ip
            config_text = f'aidd_version: "1.0.0"\nprofile: solo\nextends: [{{url: "https://{host_part}/base.yaml", sha256: "{"0" * 64}"}}]\n'
            calls = []
            warns = []
            res = extends.collect_extends(config_text, read=lambda p: None, fetch=lambda u, calls=calls: calls.append(u), warnings=warns)
            self.assertEqual(calls, [], f"fetch should not be called for {ip}")
            self.assertEqual(res, {})
            self.assertTrue(any(expected_class in w for w in warns), f"expected {expected_class} in {warns}")


class ExtendsFailureTests(unittest.TestCase):
    """A parent config that cannot be read is named with its cause: a fetch that failed, or an org preset naming a
    parent by path, which it cannot do because it lives outside the repository."""

    URL = "https://example.com/org/base.yaml"

    def child(self) -> str:
        return f'aidd_version: "1.0.0"\nprofile: team\nextends: [{{url: "{self.URL}", sha256: "{"0" * 64}"}}]\nowners:\n  approvers: ["@x"]\n'

    def test_every_fetch_failure_is_a_warning(self):
        for exc, want in (
            (http.HttpError(404, self.URL, "not found"), "HTTP 404"),
            (http.HttpError(0, self.URL, "refusing to fetch a private address"), "refusing"),
            (RuntimeError("boom"), "RuntimeError"),
        ):
            with self.subTest(exc=type(exc).__name__):

                def fetch(url, exc=exc):
                    raise exc

                with mock.patch.object(egress, "check_public_address", lambda *a: None):
                    warnings: list[str] = []
                    got = extends.collect_extends(self.child(), lambda p: None, fetch, warnings=warnings)
                self.assertEqual(got, {})
                self.assertEqual(len(warnings), 1, warnings)
                self.assertIn(self.URL, warnings[0])
                self.assertIn(want, warnings[0])


@unittest.skipUnless(hasattr(os, "killpg"), "process groups are POSIX")
class ProcessGroupTests(unittest.TestCase):
    """A bounded command's process group is signalled while its leader is still unreaped, so the group id cannot have
    been recycled for an unrelated process."""

    def spy(self):
        seen: list[int | None] = []
        real = processes.kill_group

        def kill_group(proc):
            seen.append(proc.returncode)  # None until the leader is reaped
            real(proc)

        return seen, kill_group

    @unittest.skipUnless(hasattr(os, "waitid") and hasattr(os, "WNOWAIT"), "waiting without reaping needs os.waitid (macOS from Python 3.13)")
    def test_the_test_runner_signals_the_group_before_reaping_the_leader(self):
        seen, spy = self.spy()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(processes, "kill_group", spy):
            result = test_runner.run_test_command([sys.executable, "-c", "print('ok')"], cwd=tmp, log=Path(tmp) / "logs" / "green-unit.log", timeout_seconds=30)
        self.assertEqual((result["exit"], result["status"]), (0, "passed"))
        self.assertEqual(seen, [None])


class ConfigTests(unittest.TestCase):
    def test_when_changed_ignores_case(self):
        cmd = {"name": "db", "command": ["x"], "when_changed": ["db/migrations/**"]}
        self.assertEqual(select_tests([cmd], ["DB/Migrations/0042.sql"]), [cmd])


if __name__ == "__main__":
    unittest.main()


class DirtyTreeExitTests(unittest.TestCase):
    """The exit code of a full `aidd test` is the evidence, so a run in a dirty tree fails; a quick check may run there."""

    def code(self, ev: dict, **kw) -> int:
        from aidd.cli.commands import work

        with contextlib.redirect_stdout(io.StringIO()):
            return work._print_test_results(ev, [], ".aidd/evidence", **kw)

    def test_a_full_run_in_a_dirty_tree_fails(self):
        ok = [{"name": "unit", "red_green": "green", "status": "passed", "exit": 0, "attempts": [1], "log": "unit.log", "expected": True}]
        ev = {"head_sha": "a" * 40, "base_sha": "b" * 40, "results": ok}
        self.assertEqual(self.code(ev), 0)
        self.assertEqual(self.code(ev | {"dirty_tree": True}), 1)
        self.assertEqual(self.code(ev | {"dirty_tree": True, "partial": True}), 0)  # --changed
        self.assertEqual(self.code(ev | {"dirty_tree": True}, no_red=True), 0)
