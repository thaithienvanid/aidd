"""The summary of the worktree's last `aidd test` run (R377): what `aidd status` shows beside the one Spec the run tested.

It is for a person to read, never evidence: the runner's exit code on the head is. The summary names the tested commit, the
head now, how far behind it is, the verdict `aidd test` exits on, and when the run wrote its evidence. It sits on the one Spec
the run's base-to-head diff holds, and on nothing else. The repository below has three commits: the base, the one that adds
the Spec, and a later one.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import git, run_cli

from aidd import config, testing
from aidd.kernel import json_schema
from aidd.kernel.regular_files import link_on_the_way

CONFIG = 'aidd_version: "1.0.0"\nprofile: team\n'
SPEC = '---\naidd_version: "1.0.0"\ntype: spec\nid: SPEC-1\ntitle: one\nstatus: in_review\ntasks:\n  - id: T1\n    title: t\n    scope: ["src/**"]\n---\n'
RAN_AT = 1_794_042_720  # 2026-11-07T09:12:00Z


def green(name: str = "unit") -> dict:
    return {"name": name, "red_green": "green", "status": "passed", "exit": 0, "log": f"logs/green-{name}.log"}


class LastRunTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        git(self.root, "init", "-q", "-b", "main")
        self.write(".aidd/config.yaml", CONFIG)
        self.write("README.md", "base\n")
        self.commit("base")
        self.base = git(self.root, "rev-parse", "HEAD")
        git(self.root, "checkout", "-q", "-b", "feat")
        self.write("specs/SPEC-1.md", SPEC)
        self.commit("add the Spec")
        self.tested = git(self.root, "rev-parse", "HEAD")
        self.write("src/x.py", "x = 1\n")
        self.commit("later work")
        self.head = git(self.root, "rev-parse", "HEAD")

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self, message: str) -> None:
        git(self.root, "add", "-A")
        git(self.root, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", message)

    def evidence(self, results=None, *, head: str | None = None, **extra) -> None:
        body = {
            "aidd_version": "1.0.0",
            "head_sha": head or self.tested,
            "base_sha": self.base,
            "runner": {"ci": "local"},
            "results": results or [green()],
            **extra,
        }
        path = self.root / ".aidd" / "evidence" / "evidence.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body), encoding="utf-8")
        os.utime(path, (RAN_AT, RAN_AT))

    def summary(self):
        return self.summary_and_note()[0]

    def summary_and_note(self):
        return testing.last_run_summary(config.load_text(CONFIG), str(self.root))

    def test_the_summary_sits_on_the_one_spec_the_run_tested_and_says_how_far_behind_it_is(self):
        self.evidence()
        self.assertEqual(
            self.summary(),
            ("specs/SPEC-1.md", {"commit": self.tested[:7], "head": self.head[:7], "behind": 1, "result": "passed", "at": "2026-11-07T09:12:00Z"}),
        )

    def test_a_run_on_the_head_is_not_behind(self):
        self.evidence(head=self.head)
        path, found = self.summary()
        self.assertEqual((path, found["commit"], found["head"], "behind" in found), ("specs/SPEC-1.md", self.head[:7], self.head[:7], False))

    def test_a_commit_that_is_not_an_ancestor_of_the_head_has_no_behind(self):
        git(self.root, "checkout", "-q", "-b", "other", self.base)
        self.write("other.txt", "o\n")
        self.commit("elsewhere")
        self.evidence()
        path, found = self.summary()
        self.assertEqual((path, found["commit"], "behind" in found), ("specs/SPEC-1.md", self.tested[:7], False))

    def test_the_result_is_the_verdict_aidd_test_exits_on(self):
        failed = {"name": "unit", "red_green": "green", "status": "failed", "exit": 1, "log": "logs/green-unit.log"}
        cases = [
            ("passed", {}, [green()]),
            ("failed", {}, [green(), failed]),
            ("partial", {"partial": True}, [green()]),
            ("partial", {"dirty_tree": True}, [green()]),
            ("partial", {"partial": True, "dirty_tree": True}, [green()]),
        ]
        for result, extra, results in cases:
            with self.subTest(result=result, extra=extra, results=len(results)):
                self.evidence(results, **extra)
                self.assertEqual(self.summary()[1]["result"], result)

    def test_the_summary_is_valid_under_the_status_schema(self):
        self.evidence()
        code, out = self.cli("status", "--json")
        self.assertEqual(code, 0, out)
        answer = json.loads(out)
        self.assertEqual(json_schema.validate(answer, "status.schema.json"), [])
        spec = next(i for i in answer["items"] if i["id"] == "SPEC-1")
        self.assertEqual(spec["evidence"], self.summary()[1])

    def test_no_spec_or_two_specs_in_the_diff_mean_no_summary(self):
        self.evidence()
        self.write("specs/SPEC-2.md", SPEC.replace("SPEC-1", "SPEC-2"))
        self.commit("a second Spec")
        self.evidence(head=git(self.root, "rev-parse", "HEAD"))
        self.assertIsNone(self.summary())
        for rel in ("specs/SPEC-1.md", "specs/SPEC-2.md"):
            (self.root / rel).unlink()
        self.commit("no Spec")
        self.evidence(head=git(self.root, "rev-parse", "HEAD"))
        self.assertIsNone(self.summary())

    def test_no_evidence_or_evidence_that_cannot_be_read_means_no_summary(self):
        self.assertIsNone(self.summary())
        path = self.root / ".aidd" / "evidence" / "evidence.json"
        for text in ("not json", "[]", json.dumps({"head_sha": "0" * 40, "base_sha": self.base, "results": []})):
            with self.subTest(text=text[:20]):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
                self.assertIsNone(self.summary())

    def test_a_repository_with_no_commit_has_no_summary_and_status_still_runs(self):
        bare = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, bare, ignore_errors=True)
        git(bare, "init", "-q", "-b", "main")
        self.assertEqual(testing.last_run_summary(config.load_text(CONFIG), str(bare)), (None, ""))

    def test_evidence_the_repository_committed_is_data_so_a_hostile_one_gives_no_summary_and_says_why(self):
        """A repository can commit `evidence.json`, so its commit names reach git as arguments: only full lowercase hex ids pass,
        and only a regular file inside the repository, up to the cap, is read."""
        path = self.root / ".aidd" / "evidence" / "evidence.json"
        elsewhere = self.root / "elsewhere.json"
        hostile = f"--output={self.root}/pwned"

        def hostile_head():
            self.evidence(head=hostile)

        def hostile_base():
            self.evidence()
            body = json.loads(path.read_text(encoding="utf-8"))
            path.write_text(json.dumps({**body, "base_sha": hostile}), encoding="utf-8")

        def short_or_upper():
            self.evidence(head=self.tested[:12].upper())

        def symlink():
            self.evidence()
            elsewhere.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            path.unlink()
            path.symlink_to(elsewhere)

        def oversized():
            self.evidence(padding="x" * testing.EVIDENCE_MAX_BYTES)

        cases = (
            ("a head that is an option", hostile_head, "hex id"),
            ("a base that is an option", hostile_base, "hex id"),
            ("a short upper-case head", short_or_upper, "hex id"),
            ("a link", symlink, "link"),
            ("a file over the cap", oversized, "larger"),
            ("a valid file", self.evidence, ""),
        )
        for what, write, why in cases:
            with self.subTest(what):
                write()
                found, note = self.summary_and_note()
                self.assertEqual(found is None, bool(why), (found, note))
                self.assertIn(why, note)
                self.assertFalse((self.root / "pwned").exists())
                if path.is_symlink():
                    path.unlink()

    def test_evidence_that_git_tracks_is_not_this_worktrees_run(self):
        self.evidence()
        self.assertIsNotNone(self.summary(), "an untracked file is the run's own")
        git(self.root, "add", "-f", ".aidd/evidence/evidence.json")
        found, note = self.summary_and_note()
        self.assertEqual((found, "git tracks" in note), (None, True), note)

    def forge_through_a_linked_folder(self) -> Path:
        """A repository that commits `.aidd/evidence` as a link to a tracked folder with its own evidence.json."""
        self.evidence()
        forged = self.root / "docs" / "forged"
        forged.mkdir(parents=True)
        (forged / "evidence.json").write_text((self.root / ".aidd" / "evidence" / "evidence.json").read_text(encoding="utf-8"), encoding="utf-8")
        shutil.rmtree(self.root / ".aidd" / "evidence")
        (self.root / ".aidd" / "evidence").symlink_to("../docs/forged")
        git(self.root, "add", "-f", ".aidd/evidence", "docs")
        self.commit("forge the evidence")
        return forged

    def page_sentence(self) -> str:
        import page_dom

        self.assertEqual(self.cli("status", "--html")[0], 0)
        root = page_dom.parse((self.root / ".aidd" / "views" / "status-work.html").read_text(encoding="utf-8"))
        page = root.find("section", data_view="item", data_item="SPEC-1")
        assert page is not None
        return page.find(data_field="no-evidence").text  # type: ignore[union-attr]

    def test_a_run_whose_diff_holds_several_specs_or_none_says_the_one_sentence_that_holds(self):
        said = "The page has no test run for this Spec. It reads only this worktree's last aidd test run, when that run was for this Spec alone."
        self.write("specs/SPEC-2.md", SPEC.replace("SPEC-1", "SPEC-2"))
        self.commit("a second Spec")
        self.evidence(head=git(self.root, "rev-parse", "HEAD"))
        self.assertIsNone(self.summary(), "the run's diff holds two Specs")
        self.assertEqual(self.page_sentence(), said)
        for rel in ("specs/SPEC-2.md",):
            (self.root / rel).unlink()
        (self.root / "specs" / "SPEC-1.md").write_text(SPEC.replace("status: in_review", "status: draft"), encoding="utf-8")
        self.commit("back to one")
        git(self.root, "checkout", "-q", "main")
        git(self.root, "checkout", "-q", "-b", "empty")
        self.write("src/y.py", "y = 1\n")
        self.commit("no Spec at all")
        self.evidence(head=git(self.root, "rev-parse", "HEAD"))
        self.assertIsNone(self.summary(), "the run's diff holds no Spec")
        (self.root / "specs").mkdir(exist_ok=True)
        (self.root / "specs" / "SPEC-1.md").write_text(SPEC, encoding="utf-8")
        self.assertEqual(self.page_sentence(), said)

    def test_a_linked_folder_the_repository_commits_is_refused_as_a_link_and_as_tracked(self):
        self.forge_through_a_linked_folder()
        found, note = self.summary_and_note()
        self.assertEqual((found, "link" in note), (None, True), note)
        # The link alone is enough; git's own answer for the parents is the second guard, for a file a checkout cannot link.
        self.assertIn("120000", git(self.root, "ls-files", "-s", "--", ".aidd/evidence"), "git lists the folder as a link")

    def test_a_case_variant_of_the_evidence_folder_the_repository_commits_is_refused(self):
        """On a case-insensitive file system (macOS, Windows) `.aidd/EVIDENCE/evidence.json` is served for
        `.aidd/evidence/evidence.json`, and a case-sensitive ls-files check misses it: any tracked file under the folder, in any
        case of its letters, is refused. On a case-sensitive file system the file is simply not found, and the note still says why."""
        git(self.root, "config", "core.ignorecase", "true")
        self.evidence()
        path = self.root / ".aidd" / "evidence" / "evidence.json"
        variant = self.root / ".aidd" / "EVIDENCE"
        text = path.read_text(encoding="utf-8")
        shutil.rmtree(path.parent)
        variant.mkdir()
        (variant / "evidence.json").write_text(text, encoding="utf-8")
        git(self.root, "add", "-f", ".aidd/EVIDENCE/evidence.json")
        self.commit("a case variant")
        found, note = self.summary_and_note()
        self.assertEqual((found, "git tracks" in note), (None, True), note)
        # The step the note gives works for the variant: it untracks the folder whatever the case of its letters.
        step = note.split("`")[1]
        self.assertEqual(step, "git rm --cached -r ':(icase).aidd/evidence'")
        shlex_parts = shlex.split(step)
        git(self.root, *shlex_parts[1:])
        self.assertEqual(git(self.root, "ls-files", "--", ":(icase).aidd/evidence"), "", "nothing of the folder is tracked now")

    def test_a_link_is_found_when_the_path_is_spelled_through_a_link(self):
        """The repository is reached as `/var/...` for `/private/var/...`, or here through an alias: the link in the folder
        is still found, and is named as a path from the root."""
        (self.root / ".aidd").mkdir(exist_ok=True)
        (self.root / "elsewhere").mkdir()
        (self.root / ".aidd" / "evidence").symlink_to("../elsewhere")
        alias = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, alias, ignore_errors=True)
        (alias / "spelled").symlink_to(self.root)
        for spelled in (alias / "spelled" / ".aidd" / "evidence" / "evidence.json", self.root / ".aidd" / "evidence" / "evidence.json"):
            with self.subTest(spelled=str(spelled)[-40:]):
                self.assertEqual(link_on_the_way(self.root, spelled), ".aidd/evidence")
        self.assertEqual(link_on_the_way(self.root, alias / "spelled" / "specs" / "SPEC-1.md"), "", "no link, no answer")

    def test_each_note_is_one_sentence_with_a_step_that_works(self):
        self.forge_through_a_linked_folder()
        _, linked = self.summary_and_note()
        self.assertIn("remove the link .aidd/evidence, then run `aidd test`.", linked)
        git(self.root, "rm", "-q", "--cached", ".aidd/evidence")
        (self.root / ".aidd" / "evidence").unlink()
        self.evidence()
        git(self.root, "add", "-f", ".aidd/evidence/evidence.json")
        _, tracked = self.summary_and_note()
        self.assertIn("run `git rm --cached -r ':(icase).aidd/evidence'`, then run `aidd test`.", tracked)
        for note in (linked, tracked):
            self.assertEqual(note.count("aidd test"), 1, "the step is said once")
            self.assertEqual(note.count(". "), 0, "one sentence")

    def test_aidd_test_writes_through_no_link_whatever_it_writes(self):
        """A committed link at evidence.json, at the logs folder, or at a log must not send a write to a file outside the
        repository. The run is valid, as a person's would be: it has a test command, and nothing but the link stops it."""
        config_text = CONFIG + 'tests:\n  - name: unit\n    command: ["' + sys.executable + '", "-c", "print(1)"]\n'
        self.write(".aidd/config.yaml", config_text)
        (self.root / "specs" / "SPEC-1.md").unlink()  # the Spec of setUp is not a full one; with none in the diff, nothing but the link can stop the run
        self.commit("tests")
        out = self.root / ".aidd" / "evidence"
        cases = (
            ("evidence.json", lambda outside: (out / "evidence.json").symlink_to(outside / "target.json"), "evidence.json"),
            ("logs folder", lambda outside: (out / "logs").symlink_to(outside), "logs"),
            ("a log file", lambda outside: ((out / "logs").mkdir(), (out / "logs" / "green-unit.log").symlink_to(outside / "target.json")), "green-unit.log"),
        )
        for what, make, named in cases:
            with self.subTest(what):
                outside = Path(tempfile.mkdtemp())  # its own folder for each case, so one case's file never hides another's
                self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
                shutil.rmtree(out, ignore_errors=True)
                out.mkdir(parents=True)
                make(outside)
                (outside / "target.json").write_text("untouched", encoding="utf-8")
                with self.assertRaises((RuntimeError, OSError)) as caught:
                    testing.run_tests(repo=str(self.root), out_dir=str(out))
                self.assertIn("link", str(caught.exception))
                self.assertIn(named, str(caught.exception), "the message names the link, never the test as the cause")
                self.assertNotIn("test name", str(caught.exception))
                self.assertEqual((outside / "target.json").read_text(encoding="utf-8"), "untouched", "nothing outside was written")
                self.assertEqual(sorted(p.name for p in outside.iterdir()), ["target.json"], "nor was a file made there")

    def test_evidence_nested_deeper_than_the_parser_reads_is_unreadable_and_status_still_runs(self):
        """2 MB of brackets is under the size cap and past the parser's depth on every Python: the same note as any unreadable evidence, and
        `aidd status` in text, as JSON, and as a page still exits 0."""
        path = self.root / ".aidd" / "evidence" / "evidence.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[" * 1_000_000 + "]" * 1_000_000, encoding="utf-8")
        found, note = self.summary_and_note()
        self.assertEqual((found, "cannot be read" in note), (None, True), note)
        for argv in (("status",), ("status", "--json"), ("status", "--html")):
            with self.subTest(argv=argv):
                self.assertEqual(self.cli(*argv)[0], 0)

    def test_git_reads_a_revision_that_looks_like_an_option_as_a_name_and_never_as_an_option(self):
        from aidd.kernel import git as kernel_git

        out = self.root / "pwned"
        with self.assertRaises(kernel_git.GitError):
            kernel_git.numstat(f"--output={out}", "HEAD", str(self.root))
        self.assertIsNone(kernel_git.show(f"--output={out}", "README.md", str(self.root)))
        self.assertFalse(out.exists())

    def cli(self, *argv: str) -> tuple[int, str]:
        here = os.getcwd()
        os.chdir(self.root)
        try:
            return run_cli(*argv)
        finally:
            os.chdir(here)


if __name__ == "__main__":
    unittest.main()
