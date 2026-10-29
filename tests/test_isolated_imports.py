"""Every aidd module imports on its own, first, in a fresh interpreter.

The modules import each other inside functions, so a cycle stays harmless only while the order of the top-level
imports keeps it so. A test process imports most modules early (helpers.py imports cli), which hides a module that only
works when another one was imported first. Each child here imports exactly one module, isolated (-I), from this
checkout's src/.
"""

from __future__ import annotations

import subprocess
import sys
import unittest

from helpers import ROOT

SRC = ROOT / "src"

# Run once per module, each in its own interpreter: a module imported earlier in the same process would hide the fault.
PROBE = "import importlib, sys; sys.path.insert(0, sys.argv[1]); importlib.import_module(sys.argv[2])"


def aidd_modules() -> list[str]:
    """Every module of the aidd package; `aidd.__main__` runs the CLI when imported, so it is left out."""
    out = []
    for path in sorted((SRC / "aidd").rglob("*.py")):
        parts = path.relative_to(SRC).with_suffix("").parts
        if parts[-1] != "__main__":
            out.append(".".join(parts[:-1] if parts[-1] == "__init__" else parts))
    return out


class IsolatedImportTests(unittest.TestCase):
    def test_every_module_imports_first_and_alone(self):
        modules = aidd_modules()
        self.assertGreater(len(modules), 50)
        failed = {}
        for name in modules:
            run = subprocess.run([sys.executable, "-I", "-c", PROBE, str(SRC), name], capture_output=True, text=True, encoding="utf-8", timeout=60)
            if run.returncode != 0:
                failed[name] = run.stderr.strip().splitlines()[-1:]
        self.assertEqual(failed, {})


if __name__ == "__main__":
    unittest.main()
