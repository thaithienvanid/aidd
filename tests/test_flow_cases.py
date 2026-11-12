"""A flow case for each of the team commands specify, implement, fix, and review, and a second for review: the
verifier's mismatch, since review runs Verify beside the readers.

Each case seeds a small repository with its fixture and scores the files the command leaves, and the roles it starts.
test_plugin_evals checks that every case parses. This checks what the five cases promise, by building each fixture:

- a grader named `leaves-*` that reads a file must fail on the seeded files, so a run that does nothing fails;
- a grader named `keeps-*` that reads a file must pass on the seeded files, so a run that leaves them alone passes;
- the seeded tests are red or green as the case needs, and the flaw a case hides is really in the seed.
"""

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT
from test_plugin_evals import case_yaml, front_matter

TEAM = ROOT / "plugins" / "aidd-team"
EVALS = ROOT / "evals" / "team"
FLOWS = ("specify", "implement", "fix", "review")
SPEC_TESTS = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."]


def cases() -> list[tuple[str, Path]]:
    """Each flow case, with the command it runs."""
    return [(flow, case) for flow in FLOWS for case in sorted(EVALS.glob(f"flow-{flow}-*"))]


def case_of(flow: str, named: str = "") -> Path:
    (case,) = [c for c in sorted(EVALS.glob(f"flow-{flow}-*")) if named in c.name]
    return case


def seed(case: Path, into: Path) -> None:
    """Run a case's fixture in `into`, as `claude plugin eval --scaffold` does in the case's workspace."""
    env = {**os.environ, "HOME": str(into), "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    subprocess.run(["bash", str(case / "fixture.sh")], cwd=into, env=env, check=True, capture_output=True, text=True, timeout=60)


def graders(case: Path) -> dict[str, tuple[dict, str]]:
    return {g.stem: front_matter(g) for g in sorted((case / "graders").glob("*.md"))}


def file_results(case: Path, work: Path) -> dict[str, bool]:
    """Whether each file grader of a case (a regex on a file) passes on the files in `work`."""
    out = {}
    for stem, (g, _) in graders(case).items():
        if g["type"] == "regex" and isinstance(g.get("target"), dict):
            path = work / g["target"]["path"]
            text = path.read_text(encoding="utf-8") if path.is_file() else ""
            found = re.search(g["pattern"], text, re.M if "m" in g.get("flags", "") else 0) is not None
            out[stem] = not found if g.get("match") == "not_contains" else found
    return out


def leaves_failing(case: Path, work: Path) -> list[str]:
    """The `leaves-*` file graders that fail on the files in `work`: what a run did not leave."""
    return [stem for stem, passes in file_results(case, work).items() if stem.startswith("leaves-") and not passes]


def runs(command: list[str], cwd: Path, code: str | None = None) -> int:
    argv = [sys.executable, "-c", code] if code else command
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=60).returncode


class FlowCaseTests(unittest.TestCase):
    def test_each_command_has_one_case_that_runs_it(self):
        self.assertEqual([f for f, _ in cases()], [*FLOWS[:-1], "review", "review"])
        for flow, case in cases():
            with self.subTest(case=case.name):
                data, body = front_matter(case / "prompt.md")
                self.assertTrue(body.strip().startswith(f"/aidd-team:{flow} "), body)
                self.assertTrue((TEAM / "commands" / f"{flow}.md").is_file())
                self.assertEqual(data["plugins"], ["../../../plugins/aidd-team", "../../.."])
                self.assertIn("flow", data["tags"])
                self.assertEqual(case_yaml(case / "case.yaml")["context"], {"scaffold_script": "fixture.sh"})

    def test_each_case_scores_the_files_it_leaves_and_the_roles_it_starts(self):
        for _, case in cases():
            with self.subTest(case=case.name):
                found = graders(case)
                file_graders = [d for d, _ in found.values() if d["type"] == "regex" and "target" in d]
                self.assertTrue(file_graders, "no grader reads a file")
                for d in file_graders:
                    self.assertIn(d["target"] if isinstance(d["target"], str) else d["target"]["source"], ("file", "files", "trace"))
                self.assertEqual(sum(d["type"] == "llm" for d, _ in found.values()), 1)
                for stem, (d, _) in found.items():
                    if stem.startswith("starts-"):
                        (role,) = re.findall(r"aidd-team:([a-z-]+)", d["input_match"])
                        self.assertEqual((d["type"], d["tool"], d["min"]), ("tool_used", "Agent", 1))
                        self.assertTrue((TEAM / "agents" / f"{role}.md").is_file(), role)
                        # The Agent tool's input names the role as `subagent_type`.
                        call = f'{{"description": "x", "subagent_type": "aidd-team:{role}", "prompt": "y"}}'
                        self.assertRegex(call, d["input_match"])
                        self.assertNotRegex(call.replace(role, "other"), d["input_match"])

    def test_a_file_grader_fails_on_the_seed_when_it_leaves_and_passes_when_it_keeps(self):
        for _, case in cases():
            with self.subTest(case=case.name), tempfile.TemporaryDirectory() as d:
                work = Path(d)
                seed(case, work)
                for stem, passes in file_results(case, work).items():
                    self.assertEqual(passes, stem.startswith("keeps-"), f"{stem} on the seeded files")
                self.assertEqual(subprocess.run(["git", "status", "--porcelain"], cwd=work, capture_output=True, text=True).stdout, "")

    def test_a_wrong_or_half_done_result_still_fails_a_leaves_grader(self):
        with tempfile.TemporaryDirectory() as d:
            case, work = case_of("fix"), Path(d)
            seed(case, work)
            summary = work / "notes" / "summary.py"
            original = summary.read_text(encoding="utf-8")
            for wrong in ("sum(lengths) / (len(lengths)+1)", "sum(lengths) / (len(lengths) - 1)", "sum(lengths) / 2"):
                summary.write_text(original.replace("sum(lengths) / (len(lengths) + 1)", wrong), encoding="utf-8")
                (work / "tests" / "test_summary.py").write_text(
                    "from notes.summary import average_length\n\n\ndef test():\n    assert average_length(['abcd', 'abcdef']) == 5\n", encoding="utf-8"
                )
                self.assertTrue(leaves_failing(case, work), wrong)
            summary.write_text(original.replace("sum(lengths) / (len(lengths) + 1)", "sum(lengths) / len(lengths)"), encoding="utf-8")
            self.assertEqual(leaves_failing(case, work), [])
        with tempfile.TemporaryDirectory() as d:
            case, work = case_of("implement"), Path(d)
            seed(case, work)
            limit = work / "notes" / "limit.py"
            for stub in (
                "class NoteLimitReached(Exception):\n    pass\n",
                "class NoteLimitReached(Exception):\n    pass\n\n\ndef check_note_limit(count):\n    pass\n",
            ):
                limit.write_text(stub, encoding="utf-8")
                self.assertTrue(leaves_failing(case, work), stub)
            limit.write_text(
                "LIMIT = 100\n\n\nclass NoteLimitReached(Exception):\n    pass\n\n\n"
                'def check_note_limit(count):\n    if count >= LIMIT:\n        raise NoteLimitReached(f"You can keep at most {LIMIT} notes.")\n',
                encoding="utf-8",
            )
            # Smoke baseline 0: the Task's scope left out the store, so a rule no caller ran was the whole Task.
            self.assertEqual(leaves_failing(case, work), ["leaves-the-check-in-the-store"])
            self.assertNotEqual(runs(SPEC_TESTS, work), 0, "a rule that add_note never runs refuses no caller")
            store = work / "notes" / "store.py"
            seeded = store.read_text(encoding="utf-8")
            store.write_text(seeded.replace('"""\n\n_NOTES', '"""\n\nfrom notes.limit import check_note_limit\n\n_NOTES'), encoding="utf-8")
            self.assertEqual(leaves_failing(case, work), ["leaves-the-check-in-the-store"], "an import alone runs no check")
            store.write_text(seeded + "\n\ndef can_add(user):\n    return check_note_limit(count_notes(user))\n", encoding="utf-8")
            self.assertEqual(leaves_failing(case, work), ["leaves-the-check-in-the-store"], "a check outside add_note refuses no note")
            store.write_text(seeded, encoding="utf-8")
            store.write_text(
                store.read_text(encoding="utf-8")
                .replace('"""\n\n_NOTES', '"""\n\nfrom notes.limit import check_note_limit\n\n_NOTES')
                .replace("def add_note(user, text):\n", "def add_note(user, text):\n    check_note_limit(count_notes(user))\n"),
                encoding="utf-8",
            )
            self.assertEqual(leaves_failing(case, work), [])
            self.assertEqual(runs(SPEC_TESTS, work), 0, "the right code makes the frozen test pass")
            store.write_text(
                store.read_text(encoding="utf-8").replace("def add_note(user, text):", "def add_note(user: str, text: str) -> None:"), encoding="utf-8"
            )
            self.assertEqual(leaves_failing(case, work), [], "an annotated signature is the same add_note")
        with tempfile.TemporaryDirectory() as d:
            case, work = case_of("specify"), Path(d)
            seed(case, work)
            spec = work / "specs" / "SPEC-1.md"
            text = spec.read_text(encoding="utf-8")
            partly = text.replace("confidence: medium", "confidence: medium\nstatus: ready").replace(
                "- A1: TODO: given ..., when ..., then ...", "- A1: Given 100 notes, when one more is added, then it is refused."
            )
            spec.write_text(partly, encoding="utf-8")
            self.assertIn("leaves-no-todo", leaves_failing(case, work), "a Spec that still says TODO is not ready")
            spec.write_text(partly.replace("TODO", "done"), encoding="utf-8")
            self.assertEqual(leaves_failing(case, work), [])

    def test_the_implement_case_also_needs_a_run_of_the_tests(self):
        found = graders(case_of("implement"))
        data, _ = found["runs-the-tests"]
        self.assertEqual((data["type"], data["tool"], data["min"]), ("tool_used", "Bash", 1))
        for command in ("python3 -m unittest discover", "pytest -q", "aidd test --spec specs/SPEC-2.md"):
            self.assertRegex(command, data["input_match"])

    def test_the_seeded_tests_and_flaws_are_what_the_cases_need(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            seed(case_of("implement"), work)
            self.assertNotEqual(runs(SPEC_TESTS, work), 0, "the frozen test is red until the Task is built")
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            seed(case_of("fix"), work)
            self.assertEqual(runs(SPEC_TESTS, work), 0)
            wrong = "from notes.summary import average_length as a; assert a(['abcd', 'abcdef']) != 5"
            self.assertEqual(runs([], work, wrong), 0, "the bug is in the seed")
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            seed(case_of("review", "mismatch"), work)
            self.assertEqual(runs(SPEC_TESTS, work), 0, "the tests pass while A2 is not met")
            a2 = "from notes import store\nfor n in range(101):\n    store.add_note('bo', str(n))\nassert store.count_notes('bo') == 101"
            self.assertEqual(runs([], work, a2), 0, "A2: a caller's 101st note is accepted")

    def test_the_review_and_implement_histories_follow_the_loop(self):
        """Smoke baseline 0: the reviewer's findings were about the fixture, a frozen test first seen with the code and an
        approval with no commit of its own. So the test is committed and red before the approval, which has its own
        commit with an Approved-by trailer, and the Implement commit carries Assisted-by."""
        for case, head in ((case_of("implement"), "main"), (case_of("review", "mismatch"), "feature/limit")):
            with self.subTest(case.name), tempfile.TemporaryDirectory() as d:
                work = Path(d)
                seed(case, work)
                log = subprocess.run(["git", "log", "--reverse", "--format=%s%n%b%x00", head], cwd=work, capture_output=True, text=True).stdout
                messages = [m.strip() for m in log.split("\0") if m.strip()]
                self.assertTrue(messages[1].startswith("test: freeze"), messages)
                self.assertTrue(messages[2].startswith("docs: approve"), messages)
                self.assertIn("Approved-by: @org/leads", messages[2])
                self.assertEqual(len(messages), 3 if head == "main" else 4)
                if head != "main":
                    self.assertEqual(len(re.findall(r"^Assisted-by: (\S+)$", messages[3], re.M)), 1)
                commits = subprocess.run(["git", "rev-list", "--reverse", head], cwd=work, capture_output=True, text=True).stdout.split()
                subprocess.run(["git", "checkout", "-q", commits[1]], cwd=work, check=True, capture_output=True)
                self.assertNotEqual(runs(SPEC_TESTS, work), 0, "the frozen test is red where it was committed")
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            seed(case_of("review", "ranks"), work)
            self.assertEqual(runs(SPEC_TESTS, work), 0, "the tests pass while the query can be rewritten")
            attack = (
                "import sqlite3\nfrom notes.search import find_notes\n"
                "db = sqlite3.connect(':memory:'); db.execute('CREATE TABLE notes (user TEXT, text TEXT)')\n"
                "db.execute(\"INSERT INTO notes VALUES ('bo', 'secret')\")\n"
                "assert find_notes(db, \"x' OR '1'='1' --\", 'secret') == ['secret']"
            )
            self.assertEqual(runs([], work, attack), 0, "a crafted user name returns another user's note")
            self.assertEqual(subprocess.run(["git", "branch", "--show-current"], cwd=work, capture_output=True, text=True).stdout.strip(), "feature/search")


if __name__ == "__main__":
    unittest.main()
