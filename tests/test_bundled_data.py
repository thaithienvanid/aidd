"""aidd finds its bundled data (schemas, the skill, the CI templates, the aidd-team plugin, the standards library and
stacks) when it runs installed, not only from this checkout.

`resources` locates the data from the package's own folder: `aidd/_data` in a wheel, the archive in the zipapp, and the
repository root in a checkout. A checkout falls back to the repository root, so a wrong package folder (`resources`
moved one level down, into a subpackage) still passes every other test here and breaks only the installed forms. Each
form runs in a child interpreter, isolated (-I), with this checkout nowhere on its path:

- a wheel-shaped tree, laid out from pyproject.toml's wheel sources map with no build backend (always);
- the zipapp, built by `aidd.pyz` (always);
- a real wheel, built with the hash-locked backend and installed into a fresh venv (where BUILD_WHEEL_TEST=1 and uv
  are set, as ci.yml's test job does).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from helpers import ROOT, git, hermetic_environ

from aidd import pyz
from aidd.kernel import resources

# A file each data folder must hold.
MARKERS = {
    "schemas": "profiles.json",
    "skill": "SKILL.md",
    "templates": "AGENTS.snippet.md",
    "team": ".claude-plugin/plugin.json",
    "packs": ".claude-plugin/plugin.json",
    "standards": "python/import-linter.md",
    "stacks": "python-cli.yaml",
}

# Prints where the running aidd finds each data folder. With an argument, that path goes first on sys.path.
PROBE = """import json, sys
if len(sys.argv) > 1:
    sys.path.insert(0, sys.argv[1])
import aidd
from aidd.kernel import resources
print(json.dumps({
    "package": aidd.__file__,
    "repo_root": None if resources.repo_root() is None else str(resources.repo_root()),
    "profiles": sorted(resources.load_json("profiles.json")["profiles"]),
    "data": {name: str(resources.data_dir(name)) for name in resources.LAYOUT},
}))
"""


def isolated_env(tmp: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    return env | {"XDG_CACHE_HOME": str(tmp / "cache"), "HOME": str(tmp / "home")}


# `aidd` from an install at argv[1], as the wheel's console script runs it.
INSTALLED_AIDD = "import sys; sys.path.insert(0, sys.argv.pop(1)); sys.argv[0] = 'aidd'; from aidd.cli import main; sys.exit(main())"


def wheel_shaped(site: Path) -> Path:
    """A site-packages folder laid out from pyproject.toml's wheel sources, holding what the wheel holds: the files git
    tracks (the wheel honors .gitignore), less its `exclude` patterns, with no build backend."""
    wheel = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["hatch"]["build"]["targets"]["wheel"]
    excluded = [str(p) for p in wheel["exclude"]]
    tracked = pyz.tracked_files(ROOT)
    for source, target in wheel["sources"].items():
        files = [f.removeprefix(source + "/") for f in tracked if f.startswith(source + "/")] if tracked is not None else None
        if files is None:
            files = [p.relative_to(ROOT / source).as_posix() for p in (ROOT / source).rglob("*") if p.is_file()]
        for inside in files:
            rel = f"{source}/{inside}"
            if any(f"/{p}/" in f"/{rel}/" for p in excluded) or not (ROOT / rel).is_file():
                continue
            (site / target / inside).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, site / target / inside)
    return site


class BundledDataTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()

    def probe(self, python: str, *path: str, cwd: Path) -> dict:
        run = subprocess.run(
            [python, "-I", "-c", PROBE, *path], cwd=cwd, env=isolated_env(self.tmp), capture_output=True, text=True, encoding="utf-8", timeout=120
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout)

    def assert_bundled(self, found: dict, inside: Path) -> None:
        """Every data folder resolves inside `inside` (the install), holds its marker, and none comes from the checkout."""
        self.assertIsNone(found["repo_root"])
        self.assertFalse(Path(found["package"]).resolve().is_relative_to(ROOT), found["package"])
        self.assertEqual(set(found["data"]), set(resources.LAYOUT))
        self.assertIn("solo", found["profiles"])
        for name, folder in found["data"].items():
            with self.subTest(name):
                folder = Path(folder).resolve()
                self.assertTrue(folder.is_relative_to(inside), f"{name}: {folder} is outside {inside}")
                self.assertFalse(folder.is_relative_to(ROOT), f"{name}: {folder} is the checkout's")
                self.assertTrue((folder / MARKERS[name]).is_file(), f"{name}: no {MARKERS[name]} in {folder}")

    def test_a_wheel_shaped_install_reads_its_own_data(self):
        site = wheel_shaped(self.tmp / "site-packages")
        self.assert_bundled(self.probe(sys.executable, str(site), cwd=self.tmp), site / "aidd")

    def test_a_wheel_shaped_install_runs_the_core_commands_in_a_new_project(self):
        """What the wheel leaves out must be nothing an adopter runs: from the shipped files alone, init with the team,
        risk, status, validate, test, delegate, and the MCP server all work, and the team gets its detected pack."""
        site = wheel_shaped(self.tmp / "site-packages")
        project = self.tmp / "project"
        files = {
            "package.json": json.dumps({"dependencies": {"react": "^19"}}),
            "app/__init__.py": "def add(a, b):\n    return a + b\n",
            "tests/test_add.py": "import unittest\n\nfrom app import add\n\n\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(1, 2), 3)\n",
        }
        for rel, text in files.items():
            (project / rel).parent.mkdir(parents=True, exist_ok=True)
            (project / rel).write_text(text, encoding="utf-8")
        env = hermetic_environ(isolated_env(self.tmp)) | {"GIT_AUTHOR_NAME": "a", "GIT_AUTHOR_EMAIL": "a@example.com"}
        env |= {"GIT_COMMITTER_NAME": "a", "GIT_COMMITTER_EMAIL": "a@example.com", "CLAUDE_CONFIG_DIR": str(self.tmp / "home" / ".claude")}
        (self.tmp / "home").mkdir(exist_ok=True)
        git(project, "init", "-q", "-b", "main", env=env)
        git(project, "add", "-A", env=env)
        git(project, "commit", "-qm", "start", env=env)

        def aidd(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
            run = subprocess.run(
                [sys.executable, "-I", "-c", INSTALLED_AIDD, str(site), *args],
                cwd=project,
                env=env,
                input=stdin,
                stdin=None if stdin is not None else subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=120,
            )
            self.assertNotIn("Traceback", run.stderr, args)
            return run

        init = aidd("init", "--profile", "solo", "--ci", "none", "--harness", "claude-code", "--aidd-team", "--test", "python3 -m unittest discover -s tests")
        self.assertEqual(init.returncode, 0, init.stdout + init.stderr)
        skills = sorted(p.name for p in (project / ".claude" / "skills").iterdir())
        self.assertIn("aidd-web-front-end", skills)  # the pack react calls for
        self.assertIn("aidd-code-review", skills)  # a practice skill
        self.assertNotIn("aidd-insurance", skills)  # a pack nothing calls for
        for rel in (".claude/agents/aidd-developer.md", ".claude/commands/aidd-implement.md", ".aidd/team-roles.md"):
            self.assertTrue((project / rel).is_file(), rel)  # the roles, the flows, and the roles reference
        git(project, "add", "-A", env=env)
        git(project, "commit", "-qm", "adopt aidd", env=env)
        head = git(project, "rev-parse", "HEAD", env=env)
        for args, code, said in (
            (("risk", "--paths", "app/__init__.py"), 0, "route: minor"),
            (("status",), 0, "nothing is open"),
            (("validate",), 0, "0 error(s)"),
            (("test",), 0, "[ok] green unit"),
            (("delegate", "check", "--action", "pr.merge", "--head", head), 1, "defer: pr.merge"),  # no delegation: it goes to the person
            (("new", "spec", "Add two numbers", "--paths", "app/__init__.py"), 0, "SPEC-1"),  # the Spec template and its schema
            (("validate",), 0, "0 error(s)"),
            (("standard", "list"), 0, "python/ruff-lint-format"),  # the standards library
            (("standard", "list", "--stacks"), 0, "python-cli"),  # its stacks
            (("prototype", "--example"), 0, ".aidd/views/"),  # the prototype tool
        ):
            run = aidd(*args)
            self.assertEqual((run.returncode, said in run.stdout), (code, True), (args, run.stdout, run.stderr))
        hello = {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": hello},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ]
        run = aidd("mcp", stdin="".join(json.dumps(m) + "\n" for m in messages))
        self.assertEqual(run.returncode, 0, run.stderr)
        replies = {r["id"]: r for r in map(json.loads, run.stdout.splitlines())}
        self.assertIn("risk", [t["name"] for t in replies[2]["result"]["tools"]])

    def test_the_zipapp_reads_its_own_data(self):
        archive = pyz.build(self.tmp / "out" / "aidd.pyz", ROOT)
        self.assert_bundled(self.probe(sys.executable, str(archive), cwd=self.tmp), self.tmp / "cache" / "aidd")

    # It builds with the hash-locked backend, so it runs where that is allowed: ci.yml's test job sets BUILD_WHEEL_TEST=1.
    @unittest.skipUnless(shutil.which("uv") and os.environ.get("BUILD_WHEEL_TEST") == "1", "set BUILD_WHEEL_TEST=1 with uv on PATH to build a wheel")
    def test_an_installed_wheel_reads_its_own_data(self):
        constraint = ROOT / ".github" / "requirements" / "build.txt"
        build = ["uv", "build", "--wheel", "-o", str(self.tmp / "dist"), "--build-constraint", str(constraint), "--require-hashes"]
        subprocess.run(build, cwd=ROOT, check=True, capture_output=True, timeout=600)
        (wheel,) = (self.tmp / "dist").glob("*.whl")
        venv = self.tmp / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, capture_output=True, timeout=300)
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run([str(python), "-m", "pip", "install", "--quiet", "--no-index", "--no-deps", str(wheel)], check=True, capture_output=True, timeout=300)
        found = self.probe(str(python), cwd=self.tmp)
        self.assert_bundled(found, Path(found["package"]).resolve().parent)


if __name__ == "__main__":
    unittest.main()
