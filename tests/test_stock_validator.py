"""The schemas, checked with a stock JSON Schema validator (python-jsonschema).

Someone who reads aidd's files with another tool validates them with whatever validator their language has, so the
schemas must resolve their cross-file $refs by `$id` alone (`urn:aidd:1:<name>`), and a stock validator must agree with
aidd's own (`aidd.kernel.json_schema`) on the data aidd ships and on real configs, valid and invalid. CI installs
jsonschema hash-pinned (.github/requirements/lint.txt) and sets REQUIRE_JSONSCHEMA=1, so this test cannot skip there.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path

import helpers
from helpers import ROOT

from aidd.kernel import documents, json_schema, resources

SCHEMAS = ROOT / "schemas"

try:
    import jsonschema
    from referencing import Registry, Resource
except ImportError:  # pragma: no cover - exercised where jsonschema is not installed
    jsonschema = None


def _registry():
    found = []
    for p in sorted(SCHEMAS.glob("*.schema.json")):
        doc = json.loads(p.read_text(encoding="utf-8"))
        found.append((doc["$id"], Resource.from_contents(doc)))
    return Registry().with_resources(found)


# Real configs, each with whether it is valid: aidd's validator and a stock one must say the same of each.
CONFIGS = {
    'aidd_version: "1.0.0"\nprofile: solo\n': True,
    'aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@lead", "email:me@example.com"]\n': True,
    'aidd_version: "1.0.0"\nprofile: team\nrisks:\n  areas:\n    billing: {paths: ["src/billing/**"], route: major}\n'
    "  rules:\n    - {action: code.edit, area: billing, level: ask}\n    - {action: pr.open, level: allow}\n": True,
    'aidd_version: "1.0.0"\nprofile: audited\n': False,  # the profile is gone
    'aidd_version: "1.0.0"\nprofile: solo\nrisks:\n  rules:\n    - {action: git.push, level: maybe}\n': False,
    'aidd_version: "1.0.0"\nprofile: solo\nrisks:\n  areas:\n    Bad-Name: {paths: ["x/**"]}\n': False,  # an area id is snake_case
    'aidd_version: "1.0.0"\nprofile: solo\ngates: {spec_approval: required}\n': False,  # a key the rebuild removed
}


@unittest.skipIf(jsonschema is None and os.environ.get("REQUIRE_JSONSCHEMA") != "1", "jsonschema is not installed")
class StockValidatorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if jsonschema is None:
            raise AssertionError("REQUIRE_JSONSCHEMA=1, but jsonschema is not importable")
        cls.registry = _registry()

    def validator(self, urn: str):
        sch = self.registry.contents(urn)
        return jsonschema.Draft202012Validator(sch, registry=self.registry, format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER)

    def test_every_schema_is_a_valid_2020_12_schema_and_every_ref_resolves(self):
        for p in sorted(SCHEMAS.glob("*.schema.json")):
            doc = json.loads(p.read_text(encoding="utf-8"))
            jsonschema.Draft202012Validator.check_schema(doc)
            self.assertEqual(doc["$id"], "urn:aidd:1:" + p.name.removesuffix(".schema.json"), p.name)
            refs: list[str] = []

            def walk(node, refs=refs):
                if isinstance(node, dict):
                    if isinstance(node.get("$ref"), str):
                        refs.append(node["$ref"])
                    for v in node.values():
                        walk(v)
                elif isinstance(node, list):
                    for v in node:
                        walk(v)

            walk(doc)
            resolver = self.registry.resolver(base_uri=doc["$id"])
            for ref in refs:
                self.assertFalse(ref.split("#")[0].endswith(".json"), f"{p.name}: {ref} names a file; use the $id")
                resolver.lookup(ref)  # raises when a stock resolver cannot follow it

    def test_the_shipped_data_validates_with_both(self):
        for data_file, urn in (("risks.json", "urn:aidd:1:risks"), ("roles.json", "urn:aidd:1:roles")):
            with self.subTest(data_file):
                data = resources.load_json(data_file)  # with any parts in place, as aidd reads it
                self.assertEqual([e.message for e in self.validator(urn).iter_errors(data)][:3], [])
                self.assertEqual(json_schema.validate(data, urn.rsplit(":", 1)[1] + ".schema.json")[:3], [])

    def test_a_config_is_valid_for_both_or_for_neither(self):
        stock = self.validator("urn:aidd:1:config")
        for text, valid in CONFIGS.items():
            data = documents.parse_yaml(text, "config.yaml")
            with self.subTest(config=text[:60]):
                self.assertEqual(not list(stock.iter_errors(data)), valid, "stock")
                self.assertEqual(not json_schema.validate(data, "config.schema.json"), valid, "aidd")

    def test_the_cli_output_validates_with_a_stock_validator(self):
        with tempfile.TemporaryDirectory() as d:
            root = helpers.make_repo(Path(d) / "repo", spec="specs/SPEC-220.md")
            with contextlib.chdir(root):
                runs = {
                    "urn:aidd:1:risk": [
                        ["risk", "--paths", "src/auth/x.py", "--json"],
                        ["risk", "--command", "git push -f", "--json"],
                        ["risk", "--list", "--json"],
                    ],
                    "urn:aidd:1:status": [["status", "--json"]],
                }
                for urn, argvs in runs.items():
                    for argv in argvs:
                        code, out = helpers.run_cli(*argv)
                        with self.subTest(argv=argv):
                            self.assertEqual(code, 0, out)
                            self.assertEqual([e.message for e in self.validator(urn).iter_errors(json.loads(out))][:3], [])


if __name__ == "__main__":
    unittest.main()
