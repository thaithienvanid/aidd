"""Every aidd module imports on its own, first, in a fresh interpreter.

The modules import each other inside functions, so a cycle stays harmless only while the order of the top-level
imports keeps it so. A test process imports most modules early (helpers.py imports cli), which hides a module that only
works when another one was imported first. The same holds for the standard library: a module that forgets
`import logging.handlers` works whenever an earlier module loaded it. So each module imports in a child that holds only
what a fresh interpreter holds, isolated (-I), from this checkout's src/.

Where the platform can fork, one isolated parent imports nothing of aidd and forks a child for each module, so a child
costs a fork and not a start-up. Where it cannot (Windows), each module gets its own interpreter, a few at a time.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from helpers import ROOT

SRC = ROOT / "src"
AT_ONCE = min(8, os.cpu_count() or 1)

# The parent imports no more than a fresh interpreter holds (not json, not traceback), so a forked child sees what a fresh
# one sees. A child imports its module and ends with the exit code 0 or 1; on a failure it first writes the last line of
# its error to its own pipe, which the parent reads once the child is gone. The parent prints "module<TAB>error" lines.
FORK_PROBE = """
import importlib, os, sys
sys.path.insert(0, sys.argv[1])
modules, at_once, failed = sys.argv[3:], int(sys.argv[2]), []

def child(name, write):
    code = 1  # whatever goes wrong, the child ends here and never runs the parent's loop
    try:
        importlib.import_module(name)
        code = 0
    except BaseException as error:
        import traceback
        os.write(write, traceback.format_exception_only(error)[-1].strip()[:500].encode())
    finally:
        os._exit(code)

for start in range(0, len(modules), at_once):
    running = []
    for name in modules[start:start + at_once]:
        read, write = os.pipe()
        pid = os.fork()
        if pid == 0:
            os.close(read)
            child(name, write)
        os.close(write)
        running.append((name, pid, read))
    for name, pid, read in running:
        _, status = os.waitpid(pid, 0)
        with os.fdopen(read, encoding="utf-8") as pipe:
            error = pipe.read()
        if status:
            failed.append(name + "\\t" + (error or "ended with status " + str(status)))
print("\\n".join(failed))
"""

# Where there is no fork: the same import, in a process of its own.
ONE_PROBE = "import importlib, sys; sys.path.insert(0, sys.argv[1]); importlib.import_module(sys.argv[2])"


def aidd_modules() -> list[str]:
    """Every module of the aidd package; `aidd.__main__` runs the CLI when imported, so it is left out."""
    return package_modules(SRC, "aidd")


def package_modules(src: Path, package: str) -> list[str]:
    out = []
    for path in sorted((src / package).rglob("*.py")):
        parts = path.relative_to(src).with_suffix("").parts
        if parts[-1] != "__main__":
            out.append(".".join(parts[:-1] if parts[-1] == "__init__" else parts))
    return out


def failures_by_fork(src: Path, modules: list[str]) -> dict[str, str]:
    """The modules that fail to import in a forked child of one fresh interpreter, each with its error."""
    run = subprocess.run(
        [sys.executable, "-I", "-c", FORK_PROBE, str(src), str(AT_ONCE), *modules], capture_output=True, text=True, encoding="utf-8", timeout=120
    )
    assert run.returncode == 0, run.stderr
    return dict(line.split("\t", 1) for line in run.stdout.splitlines() if line)


def failures_by_process(src: Path, modules: list[str]) -> dict[str, str]:
    """The same, with an interpreter for each module, a few at a time: the way where the platform cannot fork."""

    def one(name: str) -> tuple[str, str]:
        run = subprocess.run([sys.executable, "-I", "-c", ONE_PROBE, str(src), name], capture_output=True, text=True, encoding="utf-8", timeout=60)
        return name, "" if run.returncode == 0 else (run.stderr.strip().splitlines() or ["failed"])[-1]

    with ThreadPoolExecutor(AT_ONCE) as pool:
        return {name: error for name, error in pool.map(one, modules) if error}


failures = failures_by_fork if hasattr(os, "fork") else failures_by_process


class IsolatedImportTests(unittest.TestCase):
    def test_every_module_imports_first_and_alone(self):
        modules = aidd_modules()
        self.assertGreater(len(modules), 50)
        self.assertEqual(failures(SRC, modules), {})


class FreshInterpreterTests(unittest.TestCase):
    """A module that leans on a standard-library module another module loaded first must fail, by either way."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.src = Path(folder.name)
        package = self.src / "fake"
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "a_writer.py").write_text("import logging.handlers\n", encoding="utf-8")
        (package / "b_reader.py").write_text("import logging\nHANDLER = logging.handlers.MemoryHandler\n", encoding="utf-8")
        (package / "c_fine.py").write_text("import logging.handlers\nHANDLER = logging.handlers.MemoryHandler\n", encoding="utf-8")
        self.modules = package_modules(self.src, "fake")

    def test_a_module_that_forgets_its_own_standard_library_import_fails(self):
        for way in (failures_by_process, failures_by_fork) if hasattr(os, "fork") else (failures_by_process,):
            with self.subTest(way=way.__name__):
                found = way(self.src, self.modules)
                self.assertEqual(list(found), ["fake.b_reader"])
                self.assertIn("handlers", found["fake.b_reader"])


if __name__ == "__main__":
    unittest.main()
