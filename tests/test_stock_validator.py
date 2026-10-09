"""The schemas and the conformance corpus, checked with a stock JSON Schema validator (python-jsonschema).

An outside implementer validates the materialized corpus with whatever validator their language has, so the
schemas must resolve their cross-file $refs by `$id` alone (`urn:aidd:1:<name>`), and a stock validator must
agree with aidd.schema on every case: a case the gate rejects as `context.invalid` is invalid for it too, and
every other case is valid. The lint job in CI installs jsonschema hash-pinned (.github/requirements/lint.txt) and
sets REQUIRE_JSONSCHEMA=1 (a name tests/helpers.py leaves in the environment), so this test cannot skip there.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd import evals, schema

SCHEMAS = ROOT / "schemas"

try:
    import jsonschema
    from referencing import Registry, Resource
except ImportError:  # pragma: no cover - exercised where jsonschema is not installed
    jsonschema = None


def _registry():
    resources = []
    for p in sorted(SCHEMAS.glob("*.schema.json")):
        doc = json.loads(p.read_text(encoding="utf-8"))
        resources.append((doc["$id"], Resource.from_contents(doc)))
    return Registry().with_resources(resources)


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

    def test_the_materialized_corpus_validates_and_agrees_with_aidd_schema(self):
        context = self.validator("urn:aidd:1:context")
        conformance = self.validator("urn:aidd:1:conformance")
        with tempfile.TemporaryDirectory() as d:
            n = evals.materialize(ROOT, Path(d))
            self.assertGreater(n, 100)
            disagree = {}
            for case in sorted(Path(d).iterdir()):
                ctx = json.loads((case / "context.json").read_text(encoding="utf-8"))
                expected = json.loads((case / "expected.json").read_text(encoding="utf-8"))
                self.assertEqual([e.message for e in conformance.iter_errors(expected)], [], case.name)
                stock = sorted(e.message for e in context.iter_errors(ctx))
                ours = schema.validate(ctx, "context.schema.json")
                invalid = "fail context.invalid" in expected["findings"]
                if bool(stock) != invalid or bool(ours) != invalid:
                    disagree[case.name] = {"stock": stock[:3], "aidd": ours[:3], "expected_invalid": invalid}
            self.assertEqual(disagree, {})

    def test_roles_json_names_its_schema_and_validates_against_it(self):
        data = json.loads((SCHEMAS / "roles.json").read_text(encoding="utf-8"))
        self.assertTrue((SCHEMAS / data["$schema"]).resolve().samefile(SCHEMAS / "roles.schema.json"))
        self.assertEqual([e.message for e in self.validator("urn:aidd:1:roles").iter_errors(data)][:3], [])

    def test_every_case_and_mutation_file_validates(self):
        conformance = self.validator("urn:aidd:1:conformance")
        bad = {}
        for case in sorted(p for p in (ROOT / "examples").iterdir() if (p / "expected.json").is_file()):
            for f in [case / "expected.json", *sorted((case / "mutations").glob("*.json"))]:
                errs = [e.message for e in conformance.iter_errors(json.loads(f.read_text(encoding="utf-8")))]
                if errs:
                    bad[str(f.relative_to(ROOT))] = errs[:3]
        self.assertEqual(bad, {})


if __name__ == "__main__":
    unittest.main()
