"""The guard hook stays cheap to start: `aidd hook pre-tool` runs before every edit and shell command an agent makes.

The CLI imports most domain modules inside the handlers that need them, so the hook loads only what the guard uses.
A package door (`__init__.py`) that eagerly imports its whole package, or a top-level import of a heavy module, would
pull the rest in. The measure is the source lines of the aidd modules the hook process has loaded when it exits,
which moving or splitting a module does not change: when this test was written, the most any event below loaded was
24,873 lines (of 34,584). The ceiling leaves about 15%.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, make_repo

MAX_LOADED_LINES = 28_600

# Runs the hook in this process and, at exit, writes the aidd modules it loaded and their line counts to argv[2].
PROBE = """import atexit, json, sys
sys.path.insert(0, sys.argv.pop(1))
out = sys.argv.pop(1)

def dump():
    mods = {n: m.__file__ for n, m in list(sys.modules.items()) if (n == "aidd" or n.startswith("aidd.")) and getattr(m, "__file__", None)}
    with open(out, "w", encoding="utf-8") as f:
        json.dump({n: sum(1 for _ in open(p, encoding="utf-8")) for n, p in mods.items()}, f)

atexit.register(dump)
from aidd.cli import main
sys.exit(main(["hook", "pre-tool"]))
"""

EVENTS = {
    "a merge command": {"tool_name": "Bash", "tool_input": {"command": "gh pr merge 1"}},
    "a shell write": {"tool_name": "Bash", "tool_input": {"command": "ls > listing.txt"}},
    "an edit of the config": {"tool_name": "Edit", "tool_input": {"file_path": ".aidd/config.yaml"}},
    "an edit of code": {"tool_name": "Edit", "tool_input": {"file_path": "app.py"}},
    "an MCP merge": {"tool_name": "mcp__github__merge_pull_request", "tool_input": {}},
}


class GuardStartupTests(unittest.TestCase):
    def test_the_pre_tool_hook_loads_only_what_the_guard_needs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp).resolve() / "repo", "team")
            for what, event in EVENTS.items():
                with self.subTest(what):
                    out = Path(tmp) / "loaded.json"
                    run = subprocess.run(
                        [sys.executable, "-I", "-c", PROBE, str(ROOT / "src"), str(out)],
                        input=json.dumps({**event, "cwd": str(root)}),
                        cwd=root,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        timeout=60,
                    )
                    self.assertEqual(run.returncode, 0, run.stderr)
                    loaded = json.loads(out.read_text(encoding="utf-8"))
                    self.assertIn("aidd.guard", loaded, "the probe did not run the guard")
                    lines = sum(loaded.values())
                    self.assertLessEqual(lines, MAX_LOADED_LINES, f"{what}: the hook loaded {lines} lines in {len(loaded)} modules: {sorted(loaded)}")


if __name__ == "__main__":
    unittest.main()
