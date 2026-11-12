"""The setup commands write into another person's repository, and a committed link can point a write outside it, such as
`.claude/settings.json -> ~/.ssh/authorized_keys`. `aidd init`, the delegation setup, `aidd upgrade`, `aidd doctor`,
`aidd uninstall`, and `aidd new` write a repository file only through the one safe writer
(`regular_files.write_safely`), never through a link at the file or on the way to it, and never into a pipe. Each
case plants a link at each file the command writes, or at each folder on the way, pointing outside a temporary
repository, and checks that nothing outside changed and that the output names the file it skipped. The command runs in
a child under a timeout, so a write that would hang on a pipe fails the test, never the suite.

A test also holds the class: no module of aidd writes a file, by an open for writing, a write method, a copy, a
rename, a link, or a database, outside a short list of calls, each with its reason (`write_calls` says what it misses)."""

import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT, aidd_subprocess, git, hermetic_environ, make_repo

from aidd.setup import mcp_wiring

POSIX = sys.platform != "win32" and hasattr(os, "mkfifo")
TIMEOUT = 60
LEDGERS = (".aidd/harness-rules.json",)
INIT = (
    "init",
    ".",
    "--profile",
    "solo",
    "--ci",
    "github",
    "--aidd-team",
    "--harness",
    "claude-code",
    "--harness",
    "codex",
    "--delegate",
    "--environment",
    "none",
)


def snapshot(folder: Path) -> dict[str, object]:
    """Everything under `folder`: each file's bytes, each link's target, and each folder, by its path."""
    out: dict[str, object] = {}
    for path in sorted(folder.rglob("*")):
        rel = path.relative_to(folder).as_posix()
        out[rel] = ("link", os.readlink(path)) if path.is_symlink() else "dir" if path.is_dir() else path.read_bytes()
    return out


@unittest.skipUnless(POSIX and shutil.which("git"), "symlinks, a pipe, and git are needed")
class NoSetupWriteFollowsALinkTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.root, self.outside, self.home = self.base / "repo", self.base / "outside", self.base / "home"
        self.outside.mkdir()
        self.home.mkdir()

    def fresh_repo(self, root: Path) -> None:
        root.mkdir()
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.name", "Maya Lee")
        git(root, "config", "user.email", "maya@users.noreply.github.com")
        git(root, "commit", "-q", "--allow-empty", "-m", "start")

    def run_aidd(self, *args: str, root: Path | None = None) -> subprocess.CompletedProcess:
        env = {**hermetic_environ(), "HOME": str(self.home)}
        done = aidd_subprocess(*args, cwd=root or self.root, env=env, timeout=TIMEOUT)
        self.assertIn(done.returncode, (0, 1, 2), done.stderr)
        return done

    def written_by_init(self) -> list[str]:
        """The files `aidd init` writes into a fresh repository, found by running it once in another."""
        probe = self.base / "probe"
        self.fresh_repo(probe)
        self.run_aidd(*INIT, root=probe)
        listed = git(probe, "ls-files", "-z", "--others", "--exclude-standard").split("\0")
        return sorted({p for p in listed if p} - set(LEDGERS) | {".gitignore"})

    def init_through_links(self, rels: list[str]) -> None:
        """In a fresh repository, a link at each of `rels` to a file outside, every other one missing; then `aidd init`
        writes nothing outside, and names each file a link left missing, or the folder it copies whole (the skill)."""
        self.fresh_repo(self.root)
        for n, rel in enumerate(rels):
            if n % 2:
                (self.outside / f"{n}").write_text("keep\n", encoding="utf-8")
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            os.symlink(self.outside / f"{n}", self.root / rel)
        before = snapshot(self.outside)
        out = self.run_aidd(*INIT).stdout
        self.assertEqual(snapshot(self.outside), before, "a write went through a link")
        for rel in rels[::2]:
            names = [rel, *(p.as_posix() for p in Path(rel).parents if p.name)]
            self.assertTrue(any(f"{name} " in out for name in names), f"the output names {rel}, which aidd left alone")

    def test_init_and_the_delegation_setup_write_through_no_link_at_a_file(self):
        written = self.written_by_init()
        self.assertIn(".claude/settings.json", written)
        self.init_through_links(written)

    def test_init_writes_through_no_link_at_a_ledger(self):
        # A ledger is written after the settings file it lists, so it gets a case of its own.
        self.init_through_links(list(LEDGERS))

    def test_init_and_the_launcher_write_through_no_link_on_the_way(self):
        self.fresh_repo(self.root)
        for folder in (".claude", ".codex", ".github", ".agents", "specs"):
            (self.outside / folder).mkdir()
            os.symlink(self.outside / folder, self.root / folder)
        out = self.run_aidd(*INIT).stdout
        self.assertEqual(snapshot(self.outside), {f: "dir" for f in (".agents", ".claude", ".codex", ".github", "specs")}, "a write went through a link")
        for folder in (".claude", ".codex", ".github", "specs"):
            self.assertIn(f"{folder} is a link", out)

    def test_the_launcher_of_an_installed_aidd_writes_through_no_link_on_the_way(self):
        # A source run writes no launcher, so a child of this checkout never gets as far as the link: the installed case is in process.
        (self.home / ".aidd").mkdir()
        (self.outside / "bin").mkdir()
        os.symlink(self.outside / "bin", self.home / ".aidd" / "bin")
        actions: list[str] = []
        with mock.patch.dict(os.environ, {"HOME": str(self.home)}), mock.patch.object(mcp_wiring, "_on_default_path", return_value=True):
            mcp_wiring.install_user_launcher(self.root, actions)
        self.assertEqual(snapshot(self.outside), {"bin": "dir"}, "a write went through a link")
        self.assertIn("~/.aidd/bin is a link", actions[0])

    def test_init_writes_into_no_pipe_it_reads_first(self):
        self.fresh_repo(self.root)
        pipes = (".gitignore", "AGENTS.md", ".mcp.json", ".claude/settings.json", ".codex/config.toml", ".aidd/harness-rules.json")
        for rel in pipes:
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            os.mkfifo(self.root / rel)
        out = self.run_aidd(*INIT).stdout
        for rel in pipes:
            self.assertTrue((self.root / rel).is_fifo(), rel)
            self.assertIn(rel, out)

    def test_upgrade_doctor_and_uninstall_write_through_no_link_on_the_way(self):
        make_repo(self.root, "solo", branch=None, harnesses=["claude-code", "codex"], aidd_team=True)
        for folder in (".claude", ".codex"):
            shutil.move(self.root / folder, self.outside / folder)
            os.symlink(self.outside / folder, self.root / folder)
        for rel in (".claude/settings.json", ".codex/config.toml", ".codex/rules/aidd.rules"):  # missing behind the link
            (self.outside / rel).unlink(missing_ok=True)
        before = snapshot(self.outside)
        for command in (("upgrade", "--yes"), ("doctor",), ("uninstall", "--yes")):
            with self.subTest(command=command):
                out = self.run_aidd(*command).stdout
                self.assertEqual(snapshot(self.outside), before, "a write or a removal went through a link")
                if command[0] != "doctor":
                    self.assertIn(".claude is a link", out)

    def test_new_writes_through_no_link(self):
        make_repo(self.root, "solo", branch=None)
        (self.outside / "specs").mkdir()
        shutil.rmtree(self.root / "specs", ignore_errors=True)
        os.symlink(self.outside / "specs", self.root / "specs")
        (self.root / "AGENTS.md").unlink(missing_ok=True)
        os.symlink(self.outside / "agents.md", self.root / "AGENTS.md")
        self.run_aidd("new", "proposal", "--title", "A client's request")
        proposal = next((self.root / "proposals").glob("*/proposal.md")).parent
        os.symlink(self.outside / "contract.md", proposal / "contract.md")
        cases = (("spec", "--title", "A change"), "specs is a link"), (("agents",), "AGENTS.md"), (("contract", proposal.name), "contract.md is a link")
        for command, named in cases:
            with self.subTest(command=command):
                done = self.run_aidd("new", *command)
                self.assertIn(named, done.stdout + done.stderr)
        self.assertEqual(snapshot(self.outside), {"specs": "dir"}, "a write went through a link")


@unittest.skipUnless(POSIX and shutil.which("git"), "symlinks and git are needed")
class RootAsTypedTests(unittest.TestCase):
    """The repository root is whatever the person types: `sub`, or `../sub` from a sibling. Each command writes there once,
    prints the paths as typed, and still refuses a folder link on the way."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.sub, self.other, self.outside = self.base / "sub", self.base / "other", self.base / "outside"
        for folder in (self.sub, self.other, self.outside, self.base / "home"):
            folder.mkdir()
        git(self.sub, "init", "-q", "-b", "main")
        git(self.sub, "config", "user.name", "Maya Lee")
        git(self.sub, "config", "user.email", "maya@users.noreply.github.com")
        git(self.sub, "commit", "-q", "--allow-empty", "-m", "start")

    def run_aidd(self, cwd: Path, *args: str) -> str:
        done = aidd_subprocess(*args, cwd=cwd, env={**hermetic_environ(), "HOME": str(self.base / "home")}, timeout=TIMEOUT)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done.stdout + done.stderr

    def test_init_on_a_folder_below_writes_there_and_prints_the_path_as_typed(self):
        out = self.run_aidd(self.base, "init", "sub", "--profile", "solo", "--ci", "none")
        self.assertTrue((self.sub / ".aidd" / "config.yaml").is_file())
        self.assertFalse((self.sub / "sub").exists(), "the root was joined onto itself")
        self.assertFalse((self.base / ".aidd").exists())
        self.assertIn("wrote    sub/.aidd/config.yaml", out)
        self.assertNotIn("is a link", out)

    def test_init_on_a_sibling_through_dot_dot_writes_every_file_and_skips_none(self):
        out = self.run_aidd(self.other, "init", "../sub", "--profile", "solo", "--ci", "none", "--harness", "claude-code")
        self.assertTrue((self.sub / ".aidd" / "config.yaml").is_file())
        self.assertTrue((self.sub / "AGENTS.md").is_file())
        self.assertEqual(sorted(p.name for p in self.other.iterdir()), [], "nothing was written beside the sibling")
        self.assertIn("wrote    ../sub/.aidd/config.yaml", out)
        self.assertNotIn("skipped", out)
        self.assertNotIn("is a link", out)

    def test_upgrade_on_a_folder_below_updates_there_and_still_refuses_a_folder_link_on_the_way(self):
        self.run_aidd(self.base, "init", "sub", "--profile", "solo", "--ci", "none", "--harness", "claude-code")
        config = self.sub / ".aidd" / "config.yaml"
        current = config.read_text(encoding="utf-8")
        old = re.sub(r'aidd_version: "[^"]*"', 'aidd_version: "0.0.1"', current, count=1)
        self.assertNotEqual(old, current)
        config.write_text(old, encoding="utf-8")
        out = self.run_aidd(self.base, "upgrade", "sub", "--yes")
        self.assertNotIn('aidd_version: "0.0.1"', config.read_text(encoding="utf-8"), "the config under sub/ was not updated")
        self.assertIn("sub/.aidd/config.yaml", out)
        self.assertFalse((self.sub / "sub").exists(), "the root was joined onto itself")
        self.assertFalse((self.base / ".aidd").exists())
        shutil.move(self.sub / ".claude", self.outside / ".claude")
        os.symlink(self.outside / ".claude", self.sub / ".claude")
        before = snapshot(self.outside)
        out = self.run_aidd(self.base, "upgrade", "sub", "--yes")
        self.assertEqual(snapshot(self.outside), before, "a write went through a link")
        self.assertIn("skipped  .claude/settings.json (a link", out)

    def test_doctor_on_a_folder_below_reads_the_config_there(self):
        self.run_aidd(self.base, "init", "sub", "--profile", "solo", "--ci", "none", "--harness", "claude-code")
        out = self.run_aidd(self.base, "doctor", "sub")
        self.assertIn("config: profile solo", out)
        self.assertNotIn("[fail]", out)

    def test_uninstall_on_a_folder_below_removes_there_and_touches_nothing_else(self):
        self.run_aidd(self.base, "init", "sub", "--profile", "solo", "--ci", "none", "--harness", "claude-code")
        for kept in (self.base / "REVIEW.md", self.base / "AGENTS.md"):
            kept.write_text("not aidd's\n", encoding="utf-8")
        out = self.run_aidd(self.base, "uninstall", "sub", "--yes")
        self.assertFalse((self.sub / ".aidd" / "config.yaml").exists(), out)
        self.assertFalse((self.sub / "sub").exists())
        self.assertEqual((self.base / "REVIEW.md").read_text(encoding="utf-8"), "not aidd's\n")
        self.assertEqual((self.base / "AGENTS.md").read_text(encoding="utf-8"), "not aidd's\n")


# Each write call that may stay outside the safe writer, by module and call ("*" for every call in a module that writes
# no repository file), and why. Anything else writes through `regular_files` (`write_safely`, `open_for_write`).
WRITERS_ALLOWED = {
    ("kernel/regular_files.py", "*"): "the one safe writer",
    ("kernel/resources.py", "*"): "aidd's own bundled data, unpacked into its cache",
    ("pyz.py", "*"): "the zipapp build, into a folder of its own",
    ("docsgen/generate.py", "*"): "gen-docs, run on aidd's own source by its maintainers",
    ("evals/run_log.py", "*"): "`aidd eval` results, run by hand",
    ("evals/suites.py", "*"): "`aidd eval`, run by hand, into a temporary folder of its own",
    ("records/sharing.py", "write_bytes"): "a copy in a temporary folder of its own, for `git hash-object`",
    ("kernel/index.py", "sqlite3.connect"): "after write_refusal on the index and its journal",
    ("knowledge/standards.py", "tempfile.mkstemp"): "a new temporary file (O_EXCL) in the target's folder, after a check for a link on the way",
    ("knowledge/standards.py", "os.fdopen"): "a temporary file from mkstemp (O_EXCL), after a check for a link on the way",
    ("knowledge/standards.py", "os.replace"): "a rename over the target, which replaces a link there, never follows it",
    ("views/html_parts.py", "tempfile.mkstemp"): "a new temporary file (O_EXCL) in the target's folder, after a check for a link on the way",
    ("views/html_parts.py", "os.fdopen"): "a temporary file from mkstemp (O_EXCL), after a check for a link on the way",
    ("views/html_parts.py", "os.replace"): "a rename over the target, which replaces a link there, never follows it",
    ("setup/mcp_wiring.py", "os.replace"): "the launcher, renamed into ~/.aidd after a check for a link there",
    ("setup/skill_files.py", "shutil.copytree"): "the vendored skill, after refuses_link_on_the_way; a link inside is copied as a link",
    ("setup/skill_files.py", "symlink_to"): "the skill's link, after refuses_link_on_the_way",
    ("setup/upgrading.py", "shutil.copytree"): "a copy of the skill, after refuses_link_on_the_way",
    ("setup/self_updating.py", "touch"): "the daily check's stamp in aidd's own cache folder, outside any repository",
}
WRITE_METHODS = {"write_text", "write_bytes", "touch", "symlink_to", "hardlink_to", "rename"}
WRITE_FUNCTIONS = {f"shutil.{n}" for n in ("copy", "copy2", "copyfile", "copytree", "move")} | {f"os.{n}" for n in ("replace", "rename", "symlink", "link")}
WRITE_FUNCTIONS |= {"sqlite3.connect", "tempfile.mkstemp"}
WRITE_FLAGS = {"O_WRONLY", "O_RDWR", "O_CREAT", "O_APPEND", "O_TRUNC"}
MODULES = ("os", "io", "shutil", "sqlite3", "tempfile")


def dotted(node: ast.expr, aliases: dict[str, str]) -> str:
    """A called name as written: `open`, `os.open`, `shutil.copytree`, or one `from os import replace` brought in, by its
    module's name; `.name` for a method on anything else."""
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        return f"{node.value.id}.{node.attr}" if isinstance(node.value, ast.Name) and node.value.id in MODULES else f".{node.attr}"
    return ""


def writes_by_mode(call: ast.Call, index: int, *, unknown: bool) -> bool:
    """Whether an open's mode, the argument at `index` or `mode=`, writes: any of w, a, x, or +. A mode that is not
    written out counts as `unknown` says."""
    mode = next((k.value for k in call.keywords if k.arg == "mode"), call.args[index] if len(call.args) > index else None)
    if mode is None:
        return False
    if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
        return any(c in mode.value for c in "wax+")
    return unknown


def write_calls(source: str) -> list[tuple[int, str]]:
    """Each call in `source` that writes a file, by its line and name: an open for writing, a write method of a path, a
    copy, a rename, a link, a temporary file, or a database connection. A call split over lines counts once.

    It does not catch a mode or flags held in a variable for a path's `open`, `Path.replace` (too like `str.replace` to
    tell apart), a module imported under another name (`import os as o`), a function held in a variable, `os.write` on
    a file opened elsewhere, or a file a child process such as git writes. The review holds those."""
    tree = ast.parse(source)
    aliases = {a.asname or a.name: f"{n.module}.{a.name}" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module in MODULES for a in n.names}
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = dotted(node.func, aliases)
        flags = name == "os.open" and any(isinstance(n, ast.Attribute) and n.attr in WRITE_FLAGS for a in node.args[1:2] for n in ast.walk(a))
        if (
            flags
            or (name in ("open", "io.open", "os.fdopen") and writes_by_mode(node, 1, unknown=True))
            or (name == ".open" and writes_by_mode(node, 0, unknown=False))
            or name.lstrip(".") in WRITE_METHODS
            and name.startswith(".")
            or name in WRITE_FUNCTIONS
        ):
            found.append((node.lineno, name.lstrip(".")))
    return sorted(found)


class OneWriterTests(unittest.TestCase):
    def test_no_module_writes_a_file_but_through_the_safe_writer(self):
        src = ROOT / "src" / "aidd"
        found, used = [], set()
        for path in sorted(src.rglob("*.py")):
            rel = path.relative_to(src).as_posix()
            for line, name in write_calls(path.read_text(encoding="utf-8")):
                key = next((k for k in ((rel, "*"), (rel, name)) if k in WRITERS_ALLOWED), None)
                used.add(key) if key else found.append(f"{rel}:{line}: {name}")
        self.assertEqual(found, [], "write through regular_files.write_safely, or open_for_write with its root, or allowlist the call with its reason")
        self.assertEqual(sorted(set(WRITERS_ALLOWED) - used), [], "an allowlisted call that no module makes now: take it out")

    def test_the_walk_finds_each_way_to_write(self):
        writes = (
            'p.write_text("x")',
            "p.write_bytes(b)",
            "p.touch()",
            "p.symlink_to(t)",
            'open(p, "a", encoding="utf-8")',
            'open(p, "wt")',
            'open(p, "w+b")',
            'open(p, "r+")',
            'open(p, mode="x")',
            "open(p, how)",
            'io.open(p, "w")',
            'p.open("x")',
            'os.fdopen(fd, "w")',
            "os.open(p, os.O_WRONLY | os.O_CREAT)",
            "shutil.copy2(a, b)",
            "shutil.copytree(a, b)",
            "os.replace(a, b)",
            "os.rename(a, b)",
            "sqlite3.connect(p)",
            "p.rename(q)",
            "tempfile.mkstemp(dir=d)",
            "from os import replace\nreplace(a, b)",
            "from shutil import copy2 as cp\ncp(a, b)",
            'open(\n    p,\n    "w",\n)',
        )
        for line in writes:
            self.assertTrue(write_calls(line), line)
        for line in ('p.read_text(encoding="utf-8")', "open(p)", 'open(p, "rb")', 'p.open("rb")', "os.open(p, os.O_RDONLY)", "webbrowser.open(url)"):
            self.assertFalse(write_calls(line), line)


if __name__ == "__main__":
    unittest.main()
