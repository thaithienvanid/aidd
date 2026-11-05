"""Correctness of the hand-rolled parts against independent references.

- The JSON Schema validator runs the official JSON-Schema-Test-Suite (draft 2020-12,
  vendored in tests/jsonschema_suite/, MIT, commit in COMMIT) for every keyword it
  supports. Groups that use unsupported keywords or remote refs are skipped.
- The glob matcher is compared with a direct, segment-by-segment reference
  implementation of METHOD.md §6.1 on thousands of random patterns and paths.
"""

import json
import random
import unittest

import helpers
from helpers import ROOT

from aidd.kernel import globs

SUITE = ROOT / "tests" / "jsonschema_suite"
SUPPORTED = {
    "$schema",
    "$ref",
    "$defs",
    "type",
    "const",
    "enum",
    "required",
    "properties",
    "additionalProperties",
    "items",
    "minItems",
    "maxItems",
    "uniqueItems",
    "minLength",
    "maxLength",
    "pattern",
    "minimum",
    "maximum",
    "allOf",
    "anyOf",
    "oneOf",
    "not",
    "if",
    "then",
    "else",
    "description",
    "$comment",
    "title",
    "default",
}
# Python's re has no ECMA \p{...} classes; no aidd schema uses them.
KNOWN_LIMITS = {"pattern with Unicode property escape requires unicode mode"}


def _keywords(node) -> set[str]:
    out: set[str] = set()
    if isinstance(node, dict):
        for k, v in node.items():
            out.add(k)
            if k in ("properties", "$defs"):
                for sub in v.values():
                    out |= _keywords(sub)
            elif k not in ("const", "enum", "default"):
                out |= _keywords(v)
    elif isinstance(node, list):
        for v in node:
            out |= _keywords(v)
    return out


class JsonSchemaSuiteTests(unittest.TestCase):
    def test_official_suite(self):
        files = sorted(SUITE.glob("*.json"))
        self.assertEqual(len(files), 46, "all 46 draft 2020-12 conformance files must be vendored")
        ran = 0
        failures = []
        skipped_unimplemented = []
        skipped_remote_or_limits = []
        skipped_unexplained = []
        for f in files:
            for group in json.loads(f.read_text(encoding="utf-8")):
                s = group["schema"]
                text = json.dumps(s)
                unimplemented = _keywords(s) - SUPPORTED
                if unimplemented:
                    skipped_unimplemented.append((f.name, group["description"], sorted(unimplemented)))
                    continue
                if (
                    '"$id"' in text
                    or '"$ref": "http' in text
                    or '"$ref": "https' in text
                    or '"$ref": "urn:' in text
                    or group["description"] in KNOWN_LIMITS
                    or f.name == "format.json"
                ):
                    skipped_remote_or_limits.append((f.name, group["description"]))
                    continue
                tests_in_group = group.get("tests", [])
                if not tests_in_group:
                    skipped_unexplained.append((f.name, group["description"], "no tests in group"))
                    continue
                for t in tests_in_group:
                    ran += 1
                    if (helpers.validate_with(t["data"], s) == []) is not t["valid"]:
                        failures.append(f"{f.name}: {group['description']}: {t['description']}")
        self.assertEqual(failures, [])
        self.assertEqual(skipped_unexplained, [])
        self.assertGreater(ran, 500)


def reference_match(pattern: str, path: str) -> bool:
    """METHOD.md §6.1, directly: segments, `*` and `?` within one, `**` across any number, prefix semantics."""
    while "**/**" in pattern:
        pattern = pattern.replace("**/**", "**")
    prefix = pattern.endswith("/") or pattern.endswith("/**") or not any(c in pattern for c in "*?")
    body = pattern[:-3] if pattern.endswith("/**") else pattern.rstrip("/")
    pat, parts = body.split("/"), path.split("/")

    def seg(p: str, s: str) -> bool:
        if not p:
            return not s
        if p[0] == "*":
            return any(seg(p[1:], s[i:]) for i in range(len(s) + 1))
        return bool(s) and (p[0] == "?" or p[0] == s[0]) and seg(p[1:], s[1:])

    def walk(i: int, j: int) -> bool:
        if i == len(pat):
            return j == len(parts) or (prefix and j < len(parts))
        if pat[i] == "**":
            return any(walk(i + 1, k) for k in range(j, len(parts) + 1))
        return j < len(parts) and seg(pat[i], parts[j]) and walk(i + 1, j + 1)

    return walk(0, 0)


class GlobPropertyTests(unittest.TestCase):
    def test_matcher_agrees_with_the_reference(self):
        rng = random.Random(20260925)
        names = ["a", "b", "ab", "x.py", "a.md", ".env"]
        tokens = names + ["*", "?", "**", "*.py", "a*", "?b"]
        disagreements = []
        for _ in range(4000):
            pattern = "/".join(rng.choice(tokens) for _ in range(rng.randint(1, 4))) + rng.choice(["", "", "/", "/**"])
            path = "/".join(rng.choice(names) for _ in range(rng.randint(1, 5)))
            if globs.match(pattern, path) != reference_match(pattern, path):
                disagreements.append((pattern, path, globs.match(pattern, path)))
        self.assertEqual(disagreements[:10], [])

    def test_documented_examples(self):
        cases = [
            ("src/checkout", "src/checkout/x.py", True),
            (".claude/**", ".claude", True),
            ("*.py", "a/b.py", False),
            ("**/*.py", "b.py", True),
            ("docs/*", "docs/a/b.md", False),
            ("app/[tenant]", "app/[tenant]/p.tsx", True),
        ]
        for pattern, path, want in cases:
            self.assertEqual(globs.match(pattern, path), want, (pattern, path))
            self.assertEqual(reference_match(pattern, path), want, (pattern, path))


if __name__ == "__main__":
    unittest.main()
