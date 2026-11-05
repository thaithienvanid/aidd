"""Classes of code a code scanner flagged once, held by a test so they never come back: an HTML tag filter that misses
`</script >` (CodeQL py/bad-tag-filter, alerts 8 and 9) and a file created world-writable (py/overly-permissive-file, 10)."""

import re
import unittest

from helpers import ROOT

SOURCES = sorted(p for d in ("src", "tests", "tools", "plugins") for p in (ROOT / d).rglob("*.py") if "__pycache__" not in p.parts)


class CodeScanningClassesTests(unittest.TestCase):
    def test_a_regex_that_ends_a_tag_allows_space_before_the_bracket(self):
        """A pattern ending `</script>` or `</style>` misses `</script >`, which a browser still reads as the end tag."""
        bad = re.compile(r"</(?:script|style)>")
        found = []
        for path in SOURCES:
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"\bre\.(?:sub|search|match|fullmatch|findall|finditer|compile|split)\(", line) and bad.search(line):
                    found.append(f"{path.relative_to(ROOT)}:{n}")
        self.assertEqual(found, [], "end the tag with \\s*> so `</script >` matches too")

    def test_no_file_is_created_writable_by_everyone(self):
        found = [
            f"{p.relative_to(ROOT)}:{n}"
            for p in SOURCES
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if re.search(r"os\.(?:open|makedirs|mkdir|chmod)\([^)]*0o[0-7]?[2367][2367]\b", line)
        ]
        self.assertEqual(found, [], "give a file 0o644 (or 0o600 for a secret), never a mode others may write")


if __name__ == "__main__":
    unittest.main()
