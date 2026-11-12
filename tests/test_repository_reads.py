"""A repository's files are another person's text, so `aidd status`, `aidd validate`, and the MCP tools that run them read
a repository file only as a regular file inside the repository, at most a document's size, and never through a link or
from a device. A path a Spec names that is absolute or climbs out with `..` is refused before any read. A file aidd
refuses where a work item could be is listed by name, never dropped without a word. Each case below is the abuse: a
crafted repository a person clones and runs aidd in."""

import builtins
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import aidd_subprocess, git, hermetic_environ, run_cli
from test_intents import RepoCase
from test_workitems import intent, spec

from aidd.kernel import documents, regular_files, secret_patterns
from aidd.workitems import current_work, objects, saved_requests, spec_file

POSIX = sys.platform != "win32"
FIFO_TIMEOUT = 30  # a read that hangs on the pipe fails the test as subprocess.TimeoutExpired, never the run


def with_docs(sid: str, doc: str) -> str:
    """A Spec that names `doc` as a frozen linked document."""
    return spec(sid, "draft", extra=f"docs:\n  - type: runbook\n    path: {json.dumps(doc)}\n")


class OpenedPaths:
    """Every path opened while it is active, by `open`, `io.open`, and `os.open`, so a test can prove what was never read."""

    def __init__(self) -> None:
        self.paths: list[str] = []

    def __enter__(self):
        real_open, real_io, real_os = builtins.open, io.open, os.open

        def spy(real):
            def opened(file, *args, **kwargs):
                if isinstance(file, (str, os.PathLike)):
                    self.paths.append(os.path.realpath(os.fspath(file)))
                return real(file, *args, **kwargs)

            return opened

        self._patches = [mock.patch("builtins.open", spy(real_open)), mock.patch("io.open", spy(real_io)), mock.patch("os.open", spy(real_os))]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()

    def under(self, folder: Path) -> list[str]:
        top = os.path.realpath(folder)
        return [p for p in self.paths if p == top or p.startswith(top + os.sep)]


class StatusReadsNothingOutsideTests(RepoCase):
    def setUp(self):
        super().setUp()
        self.outside = Path(tempfile.mkdtemp(dir=self.tmp.name)).resolve()
        (self.outside / "secret.md").write_text("no placeholder here\n", encoding="utf-8")

    def test_a_doc_path_outside_the_repository_is_never_read(self):
        """Each path reads as unreadable, so the Spec still holds a placeholder, and the file outside is never opened."""
        os.symlink(self.outside / "secret.md", self.root / "docs-link.md")
        for what, doc in (
            ("an absolute path", str(self.outside / "secret.md")),
            ("a path through ..", os.path.relpath(self.outside / "secret.md", self.root)),
            ("a link out of the repository", "docs-link.md"),
        ):
            with self.subTest(what):
                self.write("specs/SPEC-1.md", with_docs("SPEC-1", doc))
                with OpenedPaths() as opened:
                    self.assertFalse(current_work.validates_clean(self.root, "specs/SPEC-1.md"))
                    run_cli("status", "--json")
                self.assertEqual(opened.under(self.outside), [], what)

    def test_a_test_file_outside_the_repository_is_never_there(self):
        name = str(self.outside / "secret.md")
        for listed in (name, os.path.relpath(name, self.root), "../*/secret.md"):
            with self.subTest(listed):
                self.assertFalse(current_work._tests_exist(self.root, {"tests": {"files": [listed]}}))


@unittest.skipUnless(POSIX and hasattr(os, "mkfifo"), "a named pipe is needed")
class NoReadHangsOnAPipeTests(RepoCase):
    """A pipe where a document is, or where a Spec names one, never hangs status or validate. Each run is a child under a
    timeout, so a hang fails the test instead of the suite."""

    def run_aidd(self, *args: str) -> subprocess.CompletedProcess:
        return aidd_subprocess(*args, cwd=self.root, env=hermetic_environ(), timeout=FIFO_TIMEOUT)

    def test_a_pipe_never_hangs_status_or_validate(self):
        cases = (
            # (what, the pipe's path, the Spec's text or None, the command, a fragment its output holds)
            ("a Spec's linked doc", "docs/pipe.md", with_docs("SPEC-1", "docs/pipe.md"), ("status", "--json"), "SPEC-1"),
            ("a work item's file", "specs/SPEC-2.md", None, ("status", "--json"), "specs/SPEC-2.md"),
            ("a file validate is given", "specs/SPEC-3.md", None, ("validate", "specs/SPEC-3.md"), "not a regular file"),
            ("a saved request", "specs/requests/2026-11-08-x.md", None, ("validate",), "not a regular file"),
            ("the config", ".aidd/config.yaml", None, ("status",), "aidd init"),
            ("a doc a Spec links, for validate", "docs/linked.md", with_docs("SPEC-1", "docs/linked.md"), ("validate",), "SPEC-1"),
        )
        for what, pipe, text, command, fragment in cases:
            with self.subTest(what):
                (self.root / pipe).parent.mkdir(parents=True, exist_ok=True)
                kept = (self.root / pipe).read_bytes() if (self.root / pipe).is_file() else None
                if kept is not None:
                    (self.root / pipe).unlink()
                os.mkfifo(self.root / pipe)
                if text:
                    self.write("specs/SPEC-1.md", text)
                done = self.run_aidd(*command)
                self.assertIn(fragment, done.stdout + done.stderr, what)
                (self.root / pipe).unlink()
                if kept is not None:
                    (self.root / pipe).write_bytes(kept)


class RefusedWorkItemTests(RepoCase):
    """A link, a device, or a file past the cap where a work item could be is listed as unreadable and is an error of
    `aidd validate`, never a work item that silently vanishes."""

    def test_a_refused_work_item_file_is_listed_and_an_error(self):
        shared = self.root.parent / "shared"
        shared.mkdir()
        (shared / "SPEC-1.md").write_text(spec("SPEC-1"), encoding="utf-8")
        big = spec("SPEC-2") + "x" * (documents.MAX_DOCUMENT_BYTES + 1)
        for what, make, rel, fragment in (
            (
                "a link to a Spec elsewhere",
                lambda: os.symlink(shared / "SPEC-1.md", self.root / "specs/SPEC-1.md"),
                "specs/SPEC-1.md",
                "a link, which aidd never follows",
            ),
            ("a file past the cap", lambda: self.write("specs/SPEC-2.md", big), "specs/SPEC-2.md", "bytes"),
        ):
            with self.subTest(what):
                make()
                code, out = run_cli("status", "--json")
                unreadable = json.loads(out).get("unreadable", [])
                self.assertTrue([u for u in unreadable if u["path"] == rel and fragment in u["error"]], unreadable)
                errors, _ = self.findings()
                self.assertTrue([e for e in errors if e.startswith(rel) and fragment in e], errors)
                (self.root / rel).unlink()

    def test_a_config_that_links_elsewhere_is_never_read(self):
        outside = self.root.parent / "theirs.yaml"
        outside.write_text((self.root / ".aidd/config.yaml").read_text(encoding="utf-8"), encoding="utf-8")
        (self.root / ".aidd/config.yaml").unlink()
        os.symlink(outside, self.root / ".aidd/config.yaml")
        with OpenedPaths() as opened:
            code, out = run_cli("status")
        self.assertIn("a link, which aidd never follows", out)
        self.assertEqual(opened.under(outside), [])

    def test_a_linked_specs_folder_is_never_walked(self):
        outside = self.root.parent / "elsewhere"
        outside.mkdir()
        (outside / "SPEC-9.md").write_text(spec("SPEC-9"), encoding="utf-8")
        (self.root / "work").symlink_to(outside, target_is_directory=True)
        found, refused = objects.work_files(self.root, "work")
        self.assertEqual(found, [])
        self.assertEqual([why for _, why in refused], [objects.REFUSED[regular_files.LINK]])

    def test_a_spec_at_a_link_is_never_found_or_written_through(self):
        outside = self.root.parent / "theirs.md"
        outside.write_text(spec("SPEC-4"), encoding="utf-8")
        os.symlink(outside, self.root / "specs/SPEC-4.md")
        with self.assertRaisesRegex(ValueError, "a link, which aidd never follows"):
            objects.find_spec_by_id(self.root, "specs", "SPEC-4")
        self.assertEqual(outside.read_text(encoding="utf-8"), spec("SPEC-4"))

    def test_the_named_reader_refuses_before_it_reads(self):
        for rel, why in (
            ("/etc/hosts", regular_files.OUTSIDE),
            ("../x.md", regular_files.OUTSIDE),
            ("", regular_files.OUTSIDE),
            ("C:\\x.md", regular_files.OUTSIDE),
        ):
            with self.subTest(rel=rel), OpenedPaths() as opened:
                self.assertEqual(regular_files.named_file_bytes(self.root, rel, 10), (None, why))
                self.assertEqual(opened.paths, [], "nothing is opened")


class NoWriteThroughALinkTests(RepoCase):
    """A folder on the way that links elsewhere never takes a write aidd makes: the file would land outside the
    repository. Each case leaves the folder outside as it was, and the command names the link."""

    def setUp(self):
        super().setUp()
        self.outside = self.root.parent / "elsewhere"
        self.outside.mkdir()

    def test_a_linked_folder_on_the_way_takes_no_write(self):
        from aidd.workitems import living_docs

        self.write("specs/SPEC-1.md", spec("SPEC-1"))
        (self.outside / "threat-models").mkdir()
        (self.outside / "threat-models" / "api.md").write_text("# api\n", encoding="utf-8")
        (self.root / "docs").mkdir(exist_ok=True)
        (self.root / "docs" / "security").symlink_to(self.outside, target_is_directory=True)
        (self.root / "specs" / "SPEC-1").symlink_to(self.outside, target_is_directory=True)
        for what, act in (
            ("the threat models' index", lambda: living_docs.write_threat_index(self.root, None, "docs")),
            ("a doc a Spec links, in the Spec's folder", lambda: run_cli("new", "tech-spec", "api", "--spec", "SPEC-1")),
        ):
            with self.subTest(what):
                before = sorted(p.relative_to(self.outside).as_posix() for p in self.outside.rglob("*"))
                found = act()
                self.assertEqual(sorted(p.relative_to(self.outside).as_posix() for p in self.outside.rglob("*")), before, what)
                if isinstance(found, tuple):
                    self.assertIn("is a link", found[1])
        self.assertTrue([w for w in living_docs.index_warnings(self.root, None, "docs") if "a link" in w])


class SavedRequestTests(RepoCase):
    """The saved requests are a person's words: a crafted line costs no more than a short one, a link to the folder
    walks nothing, and no reader takes a file there for a work item."""

    REQUESTS = "specs/requests"

    def test_a_long_line_is_read_only_to_the_line_cap(self):
        self.write(f"{self.REQUESTS}/2026-11-08-x.md", "eyJ-" * (32 * 1024) + "\n")
        with mock.patch.object(secret_patterns, "secret_types", wraps=secret_patterns.secret_types) as read:
            saved_requests.credential_findings(self.root, "specs", 1000)
        self.assertTrue(read.call_args_list)
        self.assertTrue(all(len(c.args[0]) <= secret_patterns.MAX_SECRET_LINE for c in read.call_args_list))

    def test_the_jwt_pattern_reads_a_crafted_run_once_per_start(self):
        """The header part is bounded, so a run of `eyJ-` costs a bounded scan from each start, never the whole run."""
        rx = dict(secret_patterns.SECRET_PATTERNS)["a JSON web token"]
        self.assertIsNone(rx.search("eyJ-" * (64 * 1024)))
        self.assertRegex("x eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ" + "a" * 3000 + ".sigsigsigsig", rx)
        self.assertIn("{10,1024}", rx.pattern)

    def test_a_link_to_the_requests_folder_walks_nothing(self):
        elsewhere = self.root.parent / "disk"
        (elsewhere / "deep").mkdir(parents=True)
        (elsewhere / "deep" / "a.md").write_text("x\n", encoding="utf-8")
        (self.root / "specs").mkdir(exist_ok=True)
        (self.root / self.REQUESTS).symlink_to(elsewhere, target_is_directory=True)
        with mock.patch("os.walk", wraps=os.walk) as walk:
            found = saved_requests.credential_findings(self.root, "specs", 1000)
        walk.assert_not_called()
        self.assertEqual(found, [f"{self.REQUESTS}: {objects.REFUSED[regular_files.LINK]}"])

    def test_the_walk_stops_at_the_file_cap(self):
        for n in range(4):
            self.write(f"{self.REQUESTS}/2026-11-0{n + 1}-x.md", "fine\n")
        with mock.patch.object(saved_requests, "request_findings", return_value=[]) as each:
            found = saved_requests.credential_findings(self.root, "specs", 2)
        self.assertEqual(each.call_count, 2)
        self.assertTrue([f for f in found if "more than 2" in f], found)

    def test_no_reader_takes_a_saved_request_for_a_spec(self):
        hidden = spec("SPEC-1").replace('title: "SPEC-1"', 'title: "hidden"')
        self.write(f"{self.REQUESTS}/a.md", hidden)
        self.write("specs/x/SPEC-1.md", spec("SPEC-1"))
        files = [{"path": f"{self.REQUESTS}/a.md"}, {"path": "specs/x/SPEC-1.md"}]
        self.assertEqual(spec_file.find_specs_in_diff(files, "specs", lambda p: (self.root / p).read_text(encoding="utf-8")), ["specs/x/SPEC-1.md"])
        code, out = run_cli("validate", f"{self.REQUESTS}/a.md")
        self.assertEqual(code, 1, out)
        self.assertIn("never a work item", out)
        self.assertNotIn("Acceptance", out, "only the request checks run on a saved request")

    def test_the_delegate_and_recall_never_take_a_saved_request_for_a_spec(self):
        from aidd.delegation import local_run
        from aidd.recall import sources

        self.write(f"{self.REQUESTS}/a.md", spec("SPEC-1").replace('title: "SPEC-1"', 'title: "hidden"'))
        self.write("specs/x/SPEC-1.md", spec("SPEC-1"))
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "a request that names a Spec's id")
        found = local_run.spec_by_id(str(self.root), "HEAD", "specs", "SPEC-1")
        self.assertEqual(found[0] if found else None, "specs/x/SPEC-1.md")
        listed = [p.relative_to(self.root).as_posix() for p in sources._document_files(self.root, None)["spec"]]
        self.assertNotIn(f"{self.REQUESTS}/a.md", listed)

    def test_the_delegate_takes_only_a_spec_for_a_spec_id(self):
        from aidd.delegation import local_run

        self.write("specs/SPEC-1.md", intent("SPEC-1", "a work item that is no Spec, named for the id"))
        self.write("specs/README.md", "no front matter\n")
        self.write("specs/x/real.md", spec("SPEC-1"))
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "an Intent that takes a Spec's id")
        found = local_run.spec_by_id(str(self.root), "HEAD", "specs", "SPEC-1")
        self.assertEqual(found[0] if found else None, "specs/x/real.md")
        self.assertIsNone(local_run.spec_by_id(str(self.root), "HEAD", "specs", "SPEC-2"))

    def test_a_requests_folder_inside_a_work_item_is_its_own(self):
        self.assertFalse(objects.is_saved_request(Path("specs/SPEC-1/requests/notes.md"), Path("specs")))
        self.assertTrue(objects.is_saved_request(Path("specs/requests/notes.md"), Path("specs")))


if __name__ == "__main__":
    unittest.main()
