"""One version everywhere: src/aidd/__init__.py is the source; every pin must match it (see RELEASING.md)."""

import json
import re
import subprocess
import unittest

from helpers import ROOT

from aidd import __version__

PATTERNS = [
    re.compile(r"aidd(?:/\.github/workflows/gate\.yml)?@v(\d+\.\d+\.\d+)"),
    re.compile(r'^aidd_version = "(\d+\.\d+\.\d+)"', re.M),
    re.compile(r'"version": "(\d+\.\d+\.\d+)"'),
    re.compile(r'^\s+version: "(\d+\.\d+\.\d+)"', re.M),
    re.compile(r'AIDD_VERSION: "v(\d+\.\d+\.\d+)"'),
    re.compile(r"AIDD_REF:-v(\d+\.\d+\.\d+)"),
    # A workflow that checks out aidd's source (aidd-observe.yml): the release on the `ref:` line after the repository.
    re.compile(r"repository:[ \t]*thaithienvanid/aidd[ \t]*\r?\n[ \t]*ref:[ \t]*v(\d+\.\d+\.\d+)"),
]


class VersionTests(unittest.TestCase):
    def test_every_pin_matches_the_package_version(self):
        files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout.split()
        if not files:  # an unpacked sdist: no git index, so walk the tree
            skip = {".git", "__pycache__", "dist", "build", ".venv", "node_modules"}
            files = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file() and not skip & set(p.relative_to(ROOT).parts)]
        found = 0
        for name in files:
            # tools/mermaid and .github/requirements pin third-party CI tools, whose versions are not aidd's.
            third_party = name.startswith(("tools/mermaid/", ".github/requirements/"))
            if name == "CHANGELOG.md" or third_party or name.startswith(("tests/", "examples/")) or not (ROOT / name).is_file():
                continue
            try:
                text = (ROOT / name).read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for pattern in PATTERNS:
                for m in pattern.finditer(text):
                    found += 1
                    self.assertEqual(m.group(1), __version__, f"{name}: {m.group(0)!r}")
        self.assertGreater(found, 15)

    def test_action_pins_agree(self):
        """Dependabot bumps .github/workflows; templates and action.yml must carry the same SHAs."""
        uses = re.compile(r"uses: ([\w.-]+/[\w.-]+)@([0-9a-f]{40})")
        pins: dict[str, set[str]] = {}
        files = [*(ROOT / ".github" / "workflows").glob("*.yml"), *(ROOT / "templates" / "github").glob("*.yml"), ROOT / "action.yml"]
        for f in files:
            for action, sha in uses.findall(f.read_text(encoding="utf-8")):
                pins.setdefault(action, set()).add(sha)
        self.assertTrue(pins)
        for action, shas in pins.items():
            self.assertEqual(len(shas), 1, f"{action} is pinned to several SHAs: {sorted(shas)}")

    def test_the_diagnose_cli_matches_the_locked_one(self):
        """Dependabot bumps tools/mermaid/package-lock.json; the diagnose template's CLI version and integrity must follow."""
        lock = json.loads((ROOT / "tools" / "mermaid" / "package-lock.json").read_text(encoding="utf-8"))["packages"]
        native = lock["node_modules/@anthropic-ai/claude-code-linux-x64"]
        self.assertEqual(native["version"], lock["node_modules/@anthropic-ai/claude-code"]["version"])
        diagnose = (ROOT / "templates" / "github" / "aidd-diagnose.yml").read_text(encoding="utf-8")
        self.assertIn(f'CLAUDE_CODE_VERSION: "{native["version"]}"', diagnose)
        self.assertIn(f"CLAUDE_CODE_INTEGRITY: {native['integrity']}", diagnose)
        self.assertNotIn("npm install", diagnose)  # nothing unlocked, and no install scripts


if __name__ == "__main__":
    unittest.main()
