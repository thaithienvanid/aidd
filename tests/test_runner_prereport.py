"""tests/run.py before a builder reports: `--changed` always runs the checks that read the whole repository, in a fresh worktree too,
and a run never leaves a tracked file changed.

The table of those checks (WHOLE_TREE) is data in the runner, held here to the files that exist and to the seeded misses in
tests/seeded_misses.py, which show by a run in a scratch copy that each kind of miss fails `--changed`.
"""

import contextlib
import io
import json
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import run
import seeded_misses
from helpers import IN_GIT_CHECKOUT, git

# The misses a builder's narrow run let through in the 1.0.0 build, each by a word in its kind.
KINDS_SEEN = (
    "an unused function",
    "a package door",
    "a schema keyword",
    "outside the safe reader",
    "a field name",
    "a work-item field word",
    "a role file or reference over its byte budget",
    "a long sentence copied between pages",
    "a core file that names a framework",
    "a command in agent text",
    "a glossary term",
    "an eval grader copy",
    "a pinned public fact",
    "code-scanning",
    "a finding code",
    "generated docs",
)


class WholeTreeTableTests(unittest.TestCase):
    def test_every_file_in_the_table_exists_and_each_kind_seen_is_covered(self):
        every = {p.stem for p in run.TESTS.glob("test_*.py")}
        for kind, names in run.WHOLE_TREE.items():
            with self.subTest(kind=kind):
                self.assertTrue(names, "a kind with no test file checks nothing")
                self.assertLessEqual({f"test_{n}" for n in names}, every)
        for name in run.SMOKE_FILES:
            self.assertIn(f"test_{name}", every)
        for seen in KINDS_SEEN:
            with self.subTest(seen=seen):
                self.assertTrue(any(seen in kind for kind in run.WHOLE_TREE), "a kind of miss the build saw has no row")

    def test_the_table_keeps_its_order_and_always_is_the_table_and_the_smoke_set(self):
        self.assertEqual(list(run.WHOLE_TREE), sorted(run.WHOLE_TREE), "kinds in alphabetical order")
        for names in run.WHOLE_TREE.values():
            self.assertEqual(list(names), sorted(names), "files in alphabetical order")
        self.assertEqual(set(run.ALWAYS), {*run.SMOKE_FILES, *(n for names in run.WHOLE_TREE.values() for n in names)})
        self.assertEqual(list(run.ALWAYS), sorted(run.ALWAYS))

    def test_each_kind_has_a_seeded_miss_that_its_own_files_catch_and_each_seed_still_applies(self):
        for kind, names in run.WHOLE_TREE.items():
            seeds = [s for s in seeded_misses.SEEDS if set(s[1]) <= set(names)]
            with self.subTest(kind=kind):
                self.assertTrue(seeds, "seed this kind in tests/seeded_misses.py and show `python3 tests/seeded_misses.py` catches it")
        for label, expected, edits in seeded_misses.SEEDS:
            with self.subTest(seed=label):
                self.assertTrue(any(set(expected) <= set(names) for names in run.WHOLE_TREE.values()), "a seed for a kind the table lacks")
                for edit in edits:
                    kind, rel, *rest = edit
                    path = run.ROOT / rel
                    self.assertEqual(path.exists(), kind != "new", f"{rel}: a seed makes a new file or edits one that exists")
                    if kind in ("replace", "after"):
                        self.assertIn(rest[0], path.read_text(encoding="utf-8"), f"{rel} no longer holds the text this seed edits")


RECORD = {
    "files": {
        "test_reads_x": ["src/aidd/x.py", "schemas/a.json"],
        "test_reads_y": ["src/aidd/y.py"],
        "test_anything": ["*"],
        "test_code_shape": ["src/aidd/z.py"],
        "test_overfit": ["src/aidd/z.py"],
        "test_unrelated": ["docs/other.md"],
    },
}
EVERY = ["test_reads_x", "test_reads_y", "test_anything", "test_code_shape", "test_overfit", "test_unrelated"]


def select(record, changed, base=None):
    """`select_changed` over a tests folder of the files in EVERY, with a fixed record and change."""
    with tempfile.TemporaryDirectory() as tmp:
        for name in EVERY:
            (Path(tmp) / f"{name}.py").write_text("", encoding="utf-8")
        with (
            mock.patch.object(run, "TESTS", Path(tmp)),
            mock.patch.object(run, "usable_record", return_value=(record, "")),
            mock.patch.object(run, "changed_since", return_value=changed),
        ):
            return run.select_changed(base)


class SelectionTests(unittest.TestCase):
    def test_the_checks_of_the_whole_repository_run_with_the_files_that_read_what_changed(self):
        cases = [
            ("a module", {"src/aidd/x.py"}, {"test_reads_x"}),
            ("a schema, which does not run every file", {"schemas/a.json"}, {"test_reads_x"}),
            ("a path no file reads", {"docs/none.md"}, set()),
            ("nothing", set(), set()),
        ]
        for name, changed, reads in cases:
            with self.subTest(name):
                picked, why = select(RECORD, (changed, set()))
                self.assertIsNotNone(picked, why)
                self.assertEqual(set(picked), reads | {"test_anything", "test_code_shape", "test_overfit"})
                self.assertNotIn("test_unrelated", picked)
                self.assertIn("checks of the whole repository", why)

    def test_a_change_to_the_runner_or_its_helpers_runs_every_file(self):
        for rel in ("tests/run.py", "tests/helpers.py", "tests/record_reads/sitecustomize.py"):
            with self.subTest(rel):
                self.assertEqual(select(RECORD, ({rel}, set()))[0], None)

    def test_with_no_record_the_files_that_name_a_changed_path_run_and_the_note_says_a_full_run_makes_it_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, text in (("test_names_it", "from aidd.evals import scoring\n"), ("test_other", "from aidd.risk import rules\n")):
                (Path(tmp) / f"{name}.py").write_text(text, encoding="utf-8")
            with (
                mock.patch.object(run, "TESTS", Path(tmp)),
                mock.patch.object(run, "usable_record", return_value=(None, "no record yet")),
                mock.patch.object(run, "status_since", return_value={"src/aidd/evals/scoring.py": "M"}),
            ):
                picked, why = run.select_changed(None)
                (Path(tmp) / "test_code_shape.py").write_text("x = 1\n", encoding="utf-8")
                again, _ = run.select_changed(None)
        self.assertEqual(picked, ["test_names_it"])
        self.assertEqual(again, ["test_code_shape", "test_names_it"], "a check of the whole repository joins when its file exists")
        self.assertIn("full run makes this exact", why)

    def test_with_no_record_a_clean_tree_says_to_name_the_commit_it_started_from(self):
        with (
            mock.patch.object(run, "usable_record", return_value=(None, "no record yet")),
            mock.patch.object(run, "status_since", return_value={}),
        ):
            picked, why = run.select_changed(None)
            _, with_base = run.select_changed("HEAD")
        self.assertTrue(picked and set(picked) >= {"test_code_shape", "test_untrusted_input"}, "it never runs nothing")
        self.assertIn("--base <the commit you started from>", why)
        self.assertNotIn("--base <the commit", with_base)

    def test_it_runs_every_file_only_when_git_cannot_say_what_changed(self):
        with (
            mock.patch.object(run, "usable_record", return_value=(None, "no record yet")),
            mock.patch.object(run, "status_since", return_value=None),
        ):
            self.assertEqual(run.select_changed(None)[0], None)

    def test_another_python_or_a_record_git_cannot_compare_falls_back_to_naming_not_to_everything(self):
        with (
            mock.patch.object(run, "usable_record", return_value=(RECORD, "")),
            mock.patch.object(run, "changed_since", return_value="git cannot compare the working tree with abc"),
            mock.patch.object(run, "status_since", return_value={"docs/x.md": "M"}),
        ):
            picked, why = run.select_changed(None)
        self.assertIsNotNone(picked)
        self.assertIn("git cannot compare", why)

    def test_the_names_a_test_file_can_use_for_a_changed_path(self):
        cases = {
            "src/aidd/evals/scoring.py": [("src/aidd/evals/scoring.py",), ("scoring.py",), ("aidd.evals.scoring",), ("aidd.evals", "scoring")],
            "src/aidd/evals/__init__.py": [("src/aidd/evals/__init__.py",), ("aidd.evals",)],
            "src/aidd/foo.py": [("src/aidd/foo.py",), ("foo.py",), ("aidd.foo",)],
            "src/aidd/__init__.py": [("src/aidd/__init__.py",)],
            "tests/browser_driver.py": [("tests/browser_driver.py",), ("browser_driver.py",), ("browser_driver",)],
            "schemas/risks.json": [("schemas/risks.json",), ("risks.json",)],
        }
        for rel, expected in cases.items():
            with self.subTest(rel):
                self.assertEqual(run.needles(rel), expected)


class RecordPlaceTests(unittest.TestCase):
    def test_the_record_lives_in_the_git_folder_the_checkouts_share_and_falls_back_to_pycache(self):
        shared = run.reads_path()
        if IN_GIT_CHECKOUT:  # an unpacked sdist has no git folder to share, so there the fallback is the only place
            self.assertEqual(shared.name, "aidd-test-reads.json")
            self.assertNotEqual(shared, run.READS)
        else:
            self.assertEqual(shared, run.READS)
        with mock.patch.object(run, "git", return_value=None):
            self.assertEqual(run.reads_path(), run.READS)

    def test_a_record_is_replaced_whole_and_read_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "aidd-test-reads.json"
            logs = Path(tmp) / "logs"
            logs.mkdir()
            (logs / "test_a.log").write_text("src/a.py\nsrc/a.py\n", encoding="utf-8")
            results = [run.Result("test_a", 0, 0.1, 1, 0, ""), run.Result("test_b", 1, 0.1, 1, 0, "")]
            with mock.patch.object(run, "reads_path", return_value=target):
                run.keep_reads({"head": "abc", "python": list(run.sys.version_info[:2]), "dirty": {}}, results, logs)
                record, why = run.usable_record()
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["aidd-test-reads.json", "logs"], "no half-written file stays")
        self.assertEqual(why, "")
        self.assertEqual(record["files"], {"test_a": ["src/a.py"], "test_b": ["*"]}, "a file that failed may read anything")

    def test_a_record_of_another_python_or_no_record_is_not_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "r.json"
            with mock.patch.object(run, "reads_path", return_value=target):
                self.assertIsNone(run.usable_record()[0])
                target.write_text(json.dumps({"python": [2, 7], "files": {}}), encoding="utf-8")
                self.assertIn("another Python", run.usable_record()[1])
                target.write_text("not json", encoding="utf-8")
                self.assertIn("no record", run.usable_record()[1])


class BranchChangesTests(unittest.TestCase):
    def test_a_record_taken_in_one_checkout_serves_another_that_has_the_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            git(root, "init", "-q", "-b", "main")
            (root / "a.txt").write_text("a", encoding="utf-8")
            git(root, "add", "-A")
            git(root, "commit", "-q", "-m", "first")
            first = git(root, "rev-parse", "HEAD")
            git(root, "switch", "-q", "-c", "feature")
            (root / "b.txt").write_text("b", encoding="utf-8")
            git(root, "add", "-A")
            git(root, "commit", "-q", "-m", "second")
            record = {"head": first, "python": list(run.sys.version_info[:2]), "dirty": {}, "files": {}}
            with mock.patch.object(run, "ROOT", root):
                changed, moved = run.changed_since(record, None)
                with_base = run.changed_since({**record, "head": git(root, "rev-parse", "HEAD")}, "main")
                lost = run.changed_since({**record, "head": "0" * 40}, None)
                nobase = run.changed_since(record, "no-such-branch")
        self.assertEqual((changed, moved), ({"b.txt"}, {"b.txt"}), "the commit made after the record counts, so no --base is needed")
        self.assertEqual(with_base, ({"b.txt"}, {"b.txt"}), "--base adds what the branch changed since main")
        self.assertIsInstance(lost, str)
        self.assertIn("git cannot find where this branch left", nobase)


def fake_repo(tmp: Path, tests: dict[str, str]) -> Path:
    """A git repository with `tracked.txt` committed, `ignored.txt` ignored, and the given test files committed under tests/."""
    git(tmp, "init", "-q", "-b", "main")
    (tmp / "tracked.txt").write_text("one\n", encoding="utf-8")
    (tmp / ".gitignore").write_text("ignored.txt\n__pycache__/\n", encoding="utf-8")
    (tmp / "tests").mkdir()
    for name, body in tests.items():
        lines = "".join(f"        {line}\n" for line in body.splitlines())
        (tmp / "tests" / f"{name}.py").write_text(f"import unittest\n\n\nclass T(unittest.TestCase):\n    def test_it(self):\n{lines}", encoding="utf-8")
    git(tmp, "add", "-A")
    git(tmp, "commit", "-q", "-m", "first")
    return tmp


def run_fake(tmp: Path, names: list[str], before=None, patches=()):
    """`run.main` over the repository in `tmp`: its exit code and output. `before` changes the tree before the run starts."""
    if before:
        before(tmp)
    out = io.StringIO()
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(run, "ROOT", tmp))
        stack.enter_context(mock.patch.object(run, "TESTS", tmp / "tests"))
        stack.enter_context(mock.patch.object(run, "DURATIONS", tmp / "tests" / "durations.json"))
        for patch in patches:
            stack.enter_context(patch)
        stack.enter_context(contextlib.redirect_stdout(out))
        code = run.main(names)
    return code, out.getvalue()


WRITES = "open('tracked.txt', 'a').write('changed by a test\\n')"
SCRATCH = "open('ignored.txt', 'w').write('x')\nopen('scratch.txt', 'w').write('x')"
IDLE = "pass"


class TrackedFileGuardTests(unittest.TestCase):
    """A run fails when a test leaves a tracked file changed, compared with the tree before the run."""

    def check(self, tests, names, before=None, patches=()):
        with tempfile.TemporaryDirectory() as tmp:
            return run_fake(fake_repo(Path(tmp).resolve(), tests), names, before, patches)

    def test_a_test_that_writes_a_tracked_file_fails_the_run_and_is_named_with_the_path(self):
        code, out = self.check({"test_writes": WRITES, "test_idle": IDLE}, ["test_writes", "test_idle"])
        self.assertEqual(code, 1, out)
        self.assertIn("the run changed tracked files", out)
        self.assertRegex(out, r"tracked\.txt: written while these ran: .*test_writes")

    def test_a_test_that_writes_only_untracked_or_ignored_files_passes(self):
        code, out = self.check({"test_scratch": SCRATCH}, ["test_scratch"])
        self.assertEqual(code, 0, out)
        self.assertNotIn("tracked files", out)

    def test_a_tree_that_was_dirty_before_the_run_and_is_unchanged_after_passes(self):
        def dirty(tmp):
            (tmp / "tracked.txt").write_text("my work in progress\n", encoding="utf-8")

        code, out = self.check({"test_idle": IDLE}, ["test_idle"], before=dirty)
        self.assertEqual(code, 0, out)

    def test_a_dirty_file_a_test_changes_again_fails_though_git_status_reads_the_same(self):
        def dirty(tmp):
            (tmp / "tracked.txt").write_text("my work in progress\n", encoding="utf-8")

        code, out = self.check({"test_writes": WRITES}, ["test_writes"], before=dirty)
        self.assertEqual(code, 1, out)
        self.assertIn("tracked.txt", out)

    def test_a_test_that_removes_a_tracked_file_fails_the_run(self):
        code, out = self.check({"test_removes": "import os\nos.remove('tracked.txt')"}, ["test_removes"])
        self.assertEqual(code, 1, out)
        self.assertIn("tracked.txt: written while these ran: it is gone", out)

    def test_with_no_git_it_skips_the_check_and_says_so_in_one_line(self):
        code, out = self.check({"test_writes": WRITES}, ["test_writes"], patches=[mock.patch.object(run, "tracked_state", return_value=None)])
        self.assertEqual(code, 0, out)
        self.assertEqual(len(re.findall(r"^Tracked-file check skipped", out, re.M)), 1)

    def test_a_failing_test_and_a_tracked_change_both_show(self):
        code, out = self.check({"test_writes": WRITES + "\nself.fail('red')"}, ["test_writes"])
        self.assertEqual(code, 1, out)
        self.assertIn("FAILED: test_writes", out)
        self.assertIn("the run changed tracked files", out)


@unittest.skipIf(run.fcntl is None, "the shared turn needs fcntl")
class OneSuiteAtATimeTests(unittest.TestCase):
    """Two large runs in two checkouts of one repository never run at once: the second waits for the first and says so."""

    def turn_in(self, folder: str, count: int) -> tuple[bool, str]:
        """Whether a run of `count` files got its turn at once while another process holds the lock in `folder`, and what it printed."""
        holder = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import fcntl,sys,time; f=open(sys.argv[1],'a+'); fcntl.flock(f, fcntl.LOCK_EX); print('held', flush=True); time.sleep(1.5)",
                str(Path(folder) / "aidd-test-turn.lock"),
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        try:
            assert holder.stdout is not None
            self.assertEqual(holder.stdout.readline().strip(), "held")
            out = io.StringIO()
            start = time.monotonic()
            with mock.patch.object(run, "git", return_value=folder), contextlib.redirect_stdout(out), run.turn(count):
                waited = time.monotonic() - start
            return waited < 0.5, out.getvalue()
        finally:
            holder.wait()

    def test_a_large_run_waits_and_a_small_one_does_not(self):
        cases = {
            "one file": (1, True),
            "at the line": (run.TURN_ABOVE_FILES, True),
            "past the line": (run.TURN_ABOVE_FILES + 1, False),
            "every file": (350, False),
        }
        for name, (count, at_once) in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as folder:
                got, said = self.turn_in(folder, count)
                self.assertEqual(got, at_once, name)
                self.assertEqual("Waiting for it to end" in said, not at_once, name)

    def test_the_turn_is_free_again_after_a_run(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(run, "git", return_value=folder):
            for _ in range(2):
                out = io.StringIO()
                with contextlib.redirect_stdout(out), run.turn(350):
                    pass
                self.assertEqual(out.getvalue(), "")

    def test_outside_a_repository_the_run_goes_at_once(self):
        with mock.patch.object(run, "git", return_value=None), run.turn(350):
            pass


if __name__ == "__main__":
    unittest.main()
