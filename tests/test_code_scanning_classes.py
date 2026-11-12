"""Classes of code a code scanner flagged, held by a test so they never come back under another spelling. Both tests read
the code's syntax tree, so a pattern or a mode counts however its line is written.

- CodeQL's py/bad-tag-filter (alerts 8, 9, and 11): a pattern for a script or style end tag that misses one a browser
  ends on. A browser ends one at `</script` followed by whitespace, `/`, or `>`, and anything up to the next `>`.
- Its py/overly-permissive-file (alerts 10 and 12): a mode that gives the group or others any bit, readable or writable.
"""

import ast
import re
import unittest
from pathlib import Path

from helpers import ROOT

SOURCES = sorted(p for d in ("src", "tests", "tools", "plugins") for p in (ROOT / d).rglob("*.py") if "__pycache__" not in p.parts)
# The end tag as a browser reads it: `</script >`, `</script/>`, and `</script foo>` end it, and `</scriptx>` does not.
END_TAG = r"(?:[\s/][^>]*)?>"
# Where each call takes its mode: the argument's position, or `mode=`.
MODE_AT = {"open": 2, "chmod": 1, "fchmod": 1, "mkdir": 1, "makedirs": 1}


# Each file's calls, so both tests share one parse and one walk of each file.
_CALLS: dict[Path, list[tuple[str, str, ast.Call]]] = {}


def calls(path: Path) -> list[tuple[str, str, ast.Call]]:
    """(module, name, call) for each call such as `re.compile(...)` in the file."""
    if path not in _CALLS:
        _CALLS[path] = [
            (node.func.value.id, node.func.attr, node)
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
        ]
    return _CALLS[path]


class CodeScanningClassesTests(unittest.TestCase):
    def test_a_pattern_for_an_end_tag_ends_where_a_browser_does(self):
        found = []
        for path in SOURCES:
            for module, _name, call in calls(path):
                if module != "re" or not call.args or not isinstance(call.args[0], ast.Constant) or not isinstance(call.args[0].value, str):
                    continue
                pattern = call.args[0].value
                for m in re.finditer(r"</(?:script|style)", pattern, re.I):
                    if not pattern.startswith(END_TAG, m.end()):
                        found.append(f"{path.relative_to(ROOT)}:{call.lineno} {pattern[m.start() : m.end() + 12]!r}")
        self.assertEqual(found, [], f"end the tag {END_TAG}, or find the element with page_dom's parser")

    def test_no_mode_gives_the_group_or_others_a_bit(self):
        found = []
        for path in SOURCES:
            for module, name, call in calls(path):
                if module != "os" or name not in MODE_AT:
                    continue
                mode = next((k.value for k in call.keywords if k.arg == "mode"), None)
                if mode is None and len(call.args) > MODE_AT[name]:
                    mode = call.args[MODE_AT[name]]
                if isinstance(mode, ast.Constant) and isinstance(mode.value, int) and mode.value & 0o077:
                    found.append(f"{path.relative_to(ROOT)}:{call.lineno} os.{name} 0o{mode.value:o}")
        self.assertEqual(found, [], "give a file 0o600, a folder or a program 0o700: no bit for the group or others")


if __name__ == "__main__":
    unittest.main()
