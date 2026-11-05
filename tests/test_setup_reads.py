"""The setup commands read another person's repository too: `aidd init`, `aidd upgrade`, `aidd doctor`, `aidd uninstall`,
`aidd new`, `aidd explore`, and `aidd test`. Each reads a repository file only as a regular file inside it, through the
one capped reader (`regular_files.named_text`), never through a link and never from a device or a pipe. Each case puts
a pipe, a link to a pipe, and a link to a device (/dev/null, which a read cannot fill memory from) in each place the
command reads, and the command runs in a child under a timeout, so a read that hangs fails the test, never the suite.

A test also holds the class: no module of aidd reads a file by `read_text`, `read_bytes`, or `open` outside the short
list of modules that read aidd's own data or files aidd itself wrote."""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, aidd_subprocess, fake_opencode, git, hermetic_environ, make_repo

POSIX = sys.platform != "win32" and hasattr(os, "mkfifo") and os.path.exists("/dev/null")
TIMEOUT = 40

# The places each command reads a repository file whole, by its name in the repository.
INIT_READS = ("package.json", "pyproject.toml", "setup.cfg", "mypy.ini", ".gitignore", "web/package.json", ".mcp.json", ".claude/settings.json", "REVIEW.md")
DOCTOR_READS = (
    ".mcp.json",
    ".claude/settings.json",
    ".claude/settings.local.json",
    ".aidd/harness-rules.json",
    ".codex/rules/aidd.rules",
    ".codex/config.toml",
    "opencode.json",
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".github/workflows/aidd.yml",
    "docs/runbooks/deploy.md",
    "specs/SPEC-9.md",
    "pyproject.toml",
    "docs/templates/spec.md",
)


def plant(root: Path, rels: tuple[str, ...]) -> None:
    """In each place: a pipe, a link to a pipe, or a link to /dev/null, in turn, the file that was there taken away."""
    pipe = root.parent / "pipe"
    if not pipe.exists():
        os.mkfifo(pipe)
    for n, rel in enumerate(rels):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        elif os.path.lexists(path):
            path.unlink()
        kind = n % 3
        if kind == 0:
            os.mkfifo(path)
        else:
            os.symlink(pipe if kind == 1 else "/dev/null", path)


@unittest.skipUnless(POSIX and shutil.which("git"), "a pipe, /dev/null, and git are needed")
class NoSetupReadHangsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / "repo"

    def run_aidd(self, *args: str) -> subprocess.CompletedProcess:
        return aidd_subprocess(*args, cwd=self.root, env=hermetic_environ(), timeout=TIMEOUT)

    def test_init_and_upgrade_read_no_pipe_and_follow_no_link(self):
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        (self.root / "web").mkdir()
        (self.root / "src").mkdir()
        os.mkfifo(self.root / "src" / "deep.py")
        os.symlink("/dev/null", self.root / "src" / "null.py")
        plant(self.root, INIT_READS)
        done = self.run_aidd("init", "--dry-run")
        self.assertIn(done.returncode, (0, 1, 2), done.stderr)

    def test_doctor_upgrade_uninstall_and_new_read_no_pipe_and_follow_no_link(self):
        make_repo(self.root, "solo", branch=None)
        plant(self.root, DOCTOR_READS)
        for command in (("doctor",), ("upgrade",), ("uninstall",), ("new", "spec", "--title", "A change")):
            with self.subTest(command=command), fake_opencode():  # doctor asks an installed OpenCode its version: never the machine's own
                done = self.run_aidd(*command)
                self.assertIn(done.returncode, (0, 1, 2), done.stderr)


# Every module that may still read a file with `read_text`, `read_bytes`, or `open`, and why each one's reads are not a
# repository's files read whole. Anything else reads a repository file through `regular_files` (`named_text`,
# `named_file_bytes`, `regular_file_bytes`) or `objects.read_document`.
READERS_ALLOWED = {
    "kernel/regular_files.py": "the one safe reader and writer",
    "kernel/resources.py": "aidd's own bundled data and its zipapp",
    "kernel/http.py": "a URL opener, no file",
    "knowledge/bounded_fetch.py": "a URL opener, no file",
    "config/extends.py": "the org preset at the path the person sets in AIDD_ORG_PRESET",
    "docsgen/generate.py": "gen-docs, run on aidd's own source by its maintainers",
    "docsgen/pack_budget.py": "gen-docs, run on aidd's own source by its maintainers",
    "docsgen/pack_render.py": "gen-docs, run on aidd's own source by its maintainers",
    "docsgen/product.py": "gen-docs, run on aidd's own source by its maintainers",
    "evals/suites.py": "`aidd eval` on aidd's own eval cases, run by hand",
    "evals/run_log.py": "`aidd eval` on aidd's own eval cases, run by hand",
    "evals/claims.py": "`aidd eval` on aidd's own eval cases, run by hand",
    "evals/grader_library.py": "`aidd eval` on its own grader library, in aidd's source checkout",
    "evals/held_out.py": "`aidd eval` on its own held-out cases and their lock, in aidd's source checkout",
    "evals/transcripts.py": "`aidd eval` on the transcripts the run itself wrote",
    "knowledge/command_pins.py": "aidd's own standards folders",
    "testing/junit.py": "a JUnit report the test run wrote, read capped after an inside and link check",
    "recall/sources.py": "read after refusing a link, a file outside, and one past the cap",
}
# A read of aidd's own bundled data, in a module that also reads repository files: the line holds one of these.
BUNDLED = ("resources.", "data_dir(", "(tpl /", "tpl.joinpath(")
READ = re.compile(r"\.read_text\(|\.read_bytes\(|(?<![\w.])open\(|\.open\(")
# An open for writing, appending, or a new file only, which reads nothing.
WRITE = re.compile(r"open\([^)]*[\"'][awx]b?[\"']")


class OneReaderTests(unittest.TestCase):
    def test_no_module_reads_a_repository_file_but_through_the_safe_reader(self):
        src = ROOT / "src" / "aidd"
        found, used = [], set()
        for path in sorted(src.rglob("*.py")):
            rel = path.relative_to(src).as_posix()
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                code = line.split("#", 1)[0]
                if READ.search(code) and not WRITE.search(code) and not any(b in code for b in BUNDLED) and "# aidd's own" not in line:
                    used.add(rel) if rel in READERS_ALLOWED else found.append(f"{rel}:{n}: {line.strip()}")
        self.assertEqual(found, [], "read a repository file through regular_files.named_text, or mark a read of aidd's own data `# aidd's own: why`")
        self.assertEqual(sorted(set(READERS_ALLOWED) - used), [], "an allowlisted module that reads no file this way now: take it out")


if __name__ == "__main__":
    unittest.main()
