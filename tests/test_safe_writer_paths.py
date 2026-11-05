"""The safe writer and reader beyond the working tree: the git folder, hard links, a folder link above a document, the
person's own settings, and the approvals ledger. Each case plants a link, a hard link, or a pipe where a command reads
or writes, then checks that nothing outside changed, that the command names the file, and that nothing hangs: a
command that could read a pipe runs in a child under a timeout.

- `.git/aidd` holds the records, the list of pulled records, the index, and the delegation's stop file. A link there or
  on the way is refused, as in the working tree.
- A hard link is another name of a file that may lie anywhere on the disk, so aidd writes nothing into one.
- A document read through a folder link (`specs -> ../outside`) is refused as a link.
- The person's own Claude Code settings are theirs, so a dotfiles link there is read.
- A refused approvals ledger keeps the approvals as they are."""

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import aidd_subprocess, git, hermetic_environ, make_repo

from aidd import records
from aidd.config import harness_settings
from aidd.kernel import regular_files
from aidd.setup import detection, mcp_wiring

POSIX = sys.platform != "win32" and hasattr(os, "mkfifo")
TIMEOUT = 60
REPORT = json.dumps({"action": "pr.open", "said": "Opened PR #12."})


def snapshot(folder: Path) -> dict[str, object]:
    """Everything under `folder`: each file's bytes, each link's target, and each folder, by its path."""
    out: dict[str, object] = {}
    for path in sorted(folder.rglob("*")):
        rel = path.relative_to(folder).as_posix()
        out[rel] = ("link", os.readlink(path)) if path.is_symlink() else "dir" if path.is_dir() else path.read_bytes()
    return out


@unittest.skipUnless(POSIX and shutil.which("git"), "symlinks, a pipe, and git are needed")
class GitFolderTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.root, self.outside = self.base / "repo", self.base / "outside"
        self.outside.mkdir()
        make_repo(self.root, "solo", branch=None)
        self.aidd_dir = self.root / ".git" / "aidd"
        self.aidd_dir.mkdir(exist_ok=True)

    def run_aidd(self, *args: str, input: str | None = None):
        done = aidd_subprocess(*args, cwd=self.root, env=hermetic_environ(), input=input, timeout=TIMEOUT)
        return done.returncode, done.stdout + done.stderr

    def test_the_stop_file_and_a_new_record_go_through_no_link(self):
        (self.outside / "keep").write_text("keep\n", encoding="utf-8")
        os.symlink(self.outside / "keep", self.aidd_dir / "delegation-stopped")
        (self.outside / "records").mkdir()
        os.symlink(self.outside / "records", self.aidd_dir / "records")
        before = snapshot(self.outside)
        code, out = self.run_aidd("delegate", "stop")
        self.assertNotEqual(code, 0)
        self.assertIn("delegation-stopped is a link", out)
        self.assertIn("remove the link", out)
        code, out = self.run_aidd("records", "add", "--type", "report", "--by", "claude-code/claude-opus-5-5", "--data", "-", input=REPORT)
        self.assertNotEqual(code, 0)
        self.assertIn("aidd/records is a link", out)
        self.assertEqual(snapshot(self.outside), before, "a write went through a link")

    def test_a_record_and_the_pulled_list_that_are_pipes_never_hang_a_read(self):
        month = self.aidd_dir / "records" / "2026" / "11"
        month.mkdir(parents=True)
        os.mkfifo(month / "20261105T000000000Z-aaaaaaaa.json")
        code, out = self.run_aidd("records")
        self.assertEqual(code, 0, out)
        # Named from the records folder the message names already, so a long temporary folder never cuts the name off.
        self.assertIn("skipped: 2026/11/20261105T000000000Z-aaaaaaaa.json", out)
        os.mkfifo(self.aidd_dir / "records-pulled")
        code, out = self.run_aidd("records")
        self.assertNotEqual(code, 0)
        self.assertIn("records-pulled is not regular", out)
        self.assertIn("Replace it with the regular file it stands for", out)
        self.assertNotIn("remove it", out)

    def test_the_index_is_never_opened_through_a_link(self):
        db = self.outside / "theirs.sqlite"
        with sqlite3.connect(db) as conn:
            conn.execute("CREATE TABLE entry (x TEXT)")
            conn.execute("INSERT INTO entry VALUES ('keep')")
        conn.close()
        os.symlink(db, self.aidd_dir / "index.sqlite")
        before = snapshot(self.outside)
        code, out = self.run_aidd("recall", "anything")
        self.assertIn(code, (0, 1), out)
        self.assertEqual(snapshot(self.outside), before, "the index was opened through a link")
        code, out = self.run_aidd("doctor")
        self.assertIn("aidd/index.sqlite is a link", out)
        self.assertIn("remove the link, and aidd rebuilds the index", out)
        self.assertEqual(snapshot(self.outside), before, "doctor opened the index through a link")

    def test_a_pull_marks_nothing_through_a_link(self):
        remote = self.base / "remote.git"
        git(self.base, "init", "-q", "--bare", "-b", "main", str(remote))
        clones = []
        for name in ("ada", "bo"):
            git(self.base, "clone", "-q", str(remote), str(self.base / name))
            git(self.base / name, "config", "user.name", name)
            git(self.base / name, "config", "user.email", f"{name}@example.com")
            clones.append(self.base / name)
        ada, bo = clones
        records.add_record("report", json.loads(REPORT), by="agent:claude-code/claude-opus-5-5", cwd=str(ada))
        records.push_records("origin", str(ada))
        (bo / ".git" / "aidd").mkdir(parents=True, exist_ok=True)
        os.symlink(self.outside / "pulled", bo / ".git" / "aidd" / "records-pulled")
        with self.assertRaises(ValueError) as cm:
            records.pull_records("origin", str(bo))
        self.assertIn("records-pulled is a link", str(cm.exception))
        self.assertIn("copy its target into its place", str(cm.exception))
        self.assertIn("Never delete it", str(cm.exception))
        self.assertEqual(snapshot(self.outside), {}, "a write went through a link")


@unittest.skipUnless(POSIX and shutil.which("git"), "symlinks, hard links, and git are needed")
class WorkingTreeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.root, self.outside = self.base / "repo", self.base / "outside"
        self.outside.mkdir()

    def test_init_writes_nothing_into_a_hard_link(self):
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        theirs = self.outside / "authorized_keys"
        theirs.write_text("{}\n", encoding="utf-8")  # JSON, so aidd would merge its rules in
        (self.root / ".claude").mkdir()
        os.link(theirs, self.root / ".claude" / "settings.json")
        done = aidd_subprocess(
            "init", ".", "--profile", "solo", "--ci", "none", "--harness", "claude-code", cwd=self.root, env=hermetic_environ(), timeout=TIMEOUT
        )
        self.assertIn(done.returncode, (0, 1, 2), done.stderr)
        self.assertEqual(theirs.read_text(encoding="utf-8"), "{}\n", "a write went into a hard link")
        self.assertIn("hard link", done.stdout + done.stderr)

    def test_a_document_behind_a_folder_link_is_read_as_a_link(self):
        make_repo(self.root, "solo", branch=None)
        shutil.rmtree(self.root / "specs", ignore_errors=True)
        (self.outside / "specs").mkdir()
        (self.outside / "specs" / "SPEC-1.md").write_text("---\ntype: spec\nid: SPEC-1\n---\n# Outside\n", encoding="utf-8")
        os.symlink("../outside/specs", self.root / "specs")
        done = aidd_subprocess("validate", "specs/SPEC-1.md", cwd=self.root, env=hermetic_environ(), timeout=TIMEOUT)
        self.assertIn("a link, which aidd never follows", done.stdout + done.stderr)

    def test_a_refused_ledger_keeps_the_allowed_tools_as_they_are(self):
        make_repo(self.root, "solo", branch=None)
        settings = self.root / ".claude" / "settings.json"
        settings.parent.mkdir(exist_ok=True)
        settings.write_text(json.dumps({"permissions": {"allow": []}}), encoding="utf-8")
        held = settings.read_bytes()
        ledger = self.root / mcp_wiring.LEDGER
        ledger.unlink(missing_ok=True)
        (self.outside / "ledger.json").write_text(json.dumps({mcp_wiring.TAKEN_OUT_KEY: mcp_wiring.claude_tool_names("mcp__aidd__")}), encoding="utf-8")
        os.symlink(self.outside / "ledger.json", ledger)
        said: list[str] = []
        mcp_wiring.allow_claude_tools(self.root, said, "mcp__aidd__")
        self.assertEqual(settings.read_bytes(), held, "the person's choice to take the tools out stays")
        self.assertTrue(any("stay as they are" in s and "harness-rules.json is a link" in s for s in said), said)
        # Withdrawing and uninstalling keep them too: aidd cannot tell its own names from a person's.
        names = mcp_wiring.claude_tool_names("mcp__aidd__")
        settings.write_text(json.dumps({"permissions": {"allow": names}}), encoding="utf-8")
        held = settings.read_bytes()
        for step in (
            lambda out: mcp_wiring.withdraw_claude_tools(self.root, out, "mcp__aidd__"),
            lambda out: mcp_wiring.remove_mcp(self.root, out, yes=True),
        ):
            said = []
            step(said)
            self.assertEqual(settings.read_bytes(), held)
            self.assertTrue(any("stay as they are" in s for s in said), said)
        # A ledger that does not parse is refused the same way.
        ledger.unlink()
        ledger.write_text("{not json", encoding="utf-8")
        settings.write_text(json.dumps({"permissions": {"allow": []}}), encoding="utf-8")
        said = []
        mcp_wiring.allow_claude_tools(self.root, said, "mcp__aidd__")
        self.assertEqual(json.loads(settings.read_text(encoding="utf-8")), {"permissions": {"allow": []}})
        self.assertTrue(any("harness-rules.json is not valid JSON; fix it" in s for s in said), said)

    def test_a_reader_with_a_root_refuses_a_folder_link_above_the_file(self):
        make_repo(self.root, "solo", branch=None)
        (self.outside / "a").mkdir()
        (self.outside / "a" / "exploration.md").write_text("---\ntype: exploration\n---\n# Outside\n", encoding="utf-8")
        (self.root / "specs" / "SPEC-1").mkdir(parents=True)
        os.symlink(self.outside, self.root / "specs" / "SPEC-1" / "explore")
        done = aidd_subprocess("explore", "specs/SPEC-1/explore/a", cwd=self.root, env=hermetic_environ(), timeout=TIMEOUT)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("is a link, a device, or larger than", done.stdout + done.stderr)

    def test_the_onboarding_secret_scan_reads_a_large_file_whole(self):
        make_repo(self.root, "solo", branch=None)
        big = self.root / "fixtures" / "big.txt"
        big.parent.mkdir()
        big.write_text("x = 1\n" * 50_000 + 'token = "' + "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8" + '"\n', encoding="utf-8")
        self.assertGreater(big.stat().st_size, 300_000)
        git(self.root, "add", "fixtures/big.txt")
        found = detection.secrets(self.root, [])
        self.assertEqual([rel for rel, _ in found["files"]], ["fixtures/big.txt"], "a token past the first 200 KB is still found")


class ReaderAndWriterUnitTests(unittest.TestCase):
    @unittest.skipUnless(POSIX, "symlinks are needed")
    def test_the_persons_own_settings_read_through_a_dotfiles_link(self):
        with tempfile.TemporaryDirectory() as d:
            dotfiles, home = Path(d) / "dotfiles", Path(d) / "claude"
            dotfiles.mkdir()
            home.mkdir()
            (dotfiles / "settings.json").write_text(json.dumps({"enabledPlugins": {"aidd@aidd": True}}), encoding="utf-8")
            os.symlink(dotfiles / "settings.json", home / "settings.json")
            with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(home)}):
                self.assertIn("aidd@aidd", harness_settings.user_plugins_enabled())
            (home / "settings.json").unlink()
            os.mkfifo(home / "settings.json")
            with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(home)}):
                self.assertEqual(harness_settings.user_plugins_enabled(), set(), "a pipe is never read")

    def test_the_writer_refuses_a_path_outside_its_folder(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            root.mkdir()
            for path in ("../elsewhere.txt", Path(d) / "elsewhere.txt"):
                with self.subTest(path=path):
                    self.assertIn("lies outside", regular_files.write_refusal(root, path))
                    with self.assertRaises(regular_files.WriteRefused):
                        regular_files.write_safely(root, path, "x")
            self.assertFalse((Path(d) / "elsewhere.txt").exists())
            self.assertEqual(regular_files.write_refusal(root, "inside/file.txt"), "")

    @unittest.skipUnless(POSIX, "symlinks are needed")
    def test_a_dot_dot_after_a_link_is_refused_whole(self):
        """After a link, `..` climbs out of the link's target, which a folded path never shows."""
        with tempfile.TemporaryDirectory() as d:
            base = Path(d).resolve()
            root, outside = base / "repo", base / "outside"
            root.mkdir()
            (outside / "deep").mkdir(parents=True)
            os.symlink(outside / "deep", root / "a")
            self.assertEqual(regular_files.link_on_the_way(root, "a/../b"), "a/../b")
            self.assertIn("goes through `..`", regular_files.write_refusal(root, "a/../b"))
            self.assertIn("goes through `..`", regular_files.write_refusal(root, root / "a" / ".." / "b"))
            with self.assertRaises(regular_files.WriteRefused):
                regular_files.write_safely(root, "a/../b", "x")
            self.assertEqual((sorted(p.name for p in root.iterdir()), sorted(p.name for p in outside.iterdir())), (["a"], ["deep"]))

    def test_a_dot_dot_in_the_root_itself_is_no_part_of_the_path(self):
        """`aidd init ../sub`: the root keeps its `..`, and a file under it is written once, where it belongs."""
        with tempfile.TemporaryDirectory() as d:
            base = Path(d).resolve()
            (base / "sub").mkdir()
            (base / "other").mkdir()
            root = base / "other" / ".." / "sub"
            target = root / ".aidd" / "config.yaml"
            self.assertEqual(regular_files.write_refusal(root, target), "")
            regular_files.write_safely(root, target, "x")
            self.assertEqual((base / "sub" / ".aidd" / "config.yaml").read_text(encoding="utf-8"), "x")
            self.assertEqual(sorted(p.name for p in (base / "other").iterdir()), [])
            self.assertIn("lies outside", regular_files.write_refusal(root, base / "elsewhere.txt"))
            self.assertIn("lies outside", regular_files.write_refusal(root, "../elsewhere.txt"))

    @unittest.skipUnless(POSIX, "symlinks are needed")
    def test_a_relative_root_other_than_dot_is_refused_and_an_absolute_one_checks_the_path_it_opens(self):
        """A relative root leaves it unsaid whether a path already holds the root, so nothing is read or written under one."""
        with tempfile.TemporaryDirectory() as d:
            base = Path(d).resolve()
            outside = base / "outside"
            (base / "sub" / "real").mkdir(parents=True)
            outside.mkdir()
            os.symlink(outside, base / "sub" / "linked")
            before = os.getcwd()
            os.chdir(base)
            self.addCleanup(os.chdir, before)
            (base / "sub" / "real" / "f.txt").write_text("held\n", encoding="utf-8")
            for path in ("real/f.txt", Path("sub/real/f.txt"), base / "sub" / "real" / "f.txt", "linked/g.txt"):
                with self.subTest(path=path):
                    self.assertIn("relative path", regular_files.write_refusal(Path("sub"), path))
                    self.assertIn("relative path", regular_files.link_on_the_way(Path("sub"), path))
                    with self.assertRaises(regular_files.WriteRefused):
                        regular_files.write_safely(Path("sub"), path, "x")
            self.assertIn("relative path", regular_files.named_text(Path("sub"), "real/f.txt")[1])
            self.assertIsNone(regular_files.repository_text(Path("sub"), "real/f.txt"))
            self.assertEqual(regular_files.regular_file_bytes(Path("sub"), "real/f.txt", 100)[0], None)
            self.assertEqual(regular_files.repository_text(Path("."), "sub/real/f.txt"), "held\n")
            root = base / "sub"
            self.assertIn("linked is a link", regular_files.write_refusal(root, root / "linked" / "f.txt"))
            self.assertEqual(regular_files.write_refusal(root, root / "real" / "f.txt"), "")
            self.assertEqual(sorted(p.name for p in outside.iterdir()), [])
            self.assertFalse((base / "sub" / "sub").exists())

    def test_the_working_root_of_a_path_outside_the_working_folder_is_absolute(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d).resolve()
            (base / "repo").mkdir()
            (base / "elsewhere").mkdir()
            before = os.getcwd()
            os.chdir(base / "repo")
            self.addCleanup(os.chdir, before)
            root = regular_files.working_root(Path("../elsewhere/f.md"))
            self.assertEqual(root, base / "elsewhere")
            regular_files.write_text_safely(root, root / "f.md", "x")
            self.assertEqual((base / "elsewhere" / "f.md").read_text(encoding="utf-8"), "x")

    def test_a_path_that_is_not_inside_the_root_is_refused_never_passed(self):
        """No front of the path is the root: the check says so, and the writer opens nothing."""
        with tempfile.TemporaryDirectory() as d:
            base = Path(d).resolve()
            (base / "repo").mkdir()
            (base / "elsewhere").mkdir()
            root, other = base / "repo", base / "elsewhere" / "f.txt"
            self.assertIn("not inside", regular_files.link_on_the_way(root, other))
            self.assertIn("lies outside", regular_files.write_refusal(root, other))
            with self.assertRaises(regular_files.WriteRefused):
                regular_files.write_safely(root, other, "x")
            self.assertEqual(list((base / "elsewhere").iterdir()), [])
            self.assertEqual(regular_files.link_on_the_way(root, root / "inside" / "f.txt"), "")


if __name__ == "__main__":
    unittest.main()


class FileModeTests(unittest.TestCase):
    def test_a_new_repository_file_is_never_more_open_than_its_folder_and_never_writable_by_others(self):
        cases = (  # umask, the folder's mode, the file's mode
            (0o022, 0o755, 0o644),
            (0o002, 0o775, 0o664),
            (0o000, 0o777, 0o664),
            (0o022, 0o700, 0o600),
            (0o000, 0o750, 0o640),
        )
        for umask, folder_mode, want in cases:
            with self.subTest(umask=oct(umask), folder=oct(folder_mode)), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve()
                root.chmod(folder_mode)
                old = os.umask(umask)
                try:
                    regular_files.write_safely(root, "f.md", "x\n")
                finally:
                    os.umask(old)
                    root.chmod(0o700)
                self.assertEqual((root / "f.md").stat().st_mode & 0o777, want)

    def test_a_file_that_exists_keeps_its_own_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "f.md").write_text("old\n", encoding="utf-8")
            (root / "f.md").chmod(0o640)
            regular_files.write_safely(root, "f.md", "new\n")
            self.assertEqual((root / "f.md").stat().st_mode & 0o777, 0o640)
