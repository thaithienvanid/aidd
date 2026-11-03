import datetime as dt
import hashlib
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd import config
from aidd.workitems import validation
from aidd.workitems import authoring
from aidd.workitems import spec_file
from aidd.kernel import documents, globs, json_schema, resources


class SchemaTests(unittest.TestCase):
    def test_every_schema_file_is_valid_json_with_an_id(self):
        for p in (ROOT / "schemas").glob("*.schema.json"):
            data = resources.load_json(p.name)
            self.assertTrue(data["$id"].startswith("urn:aidd:1:"), p.name)

    def test_required_enum_and_unknown_fields(self):
        errs = json_schema.validate({"aidd_version": "1.0.0", "profile": "chaos", "extra": 1}, "config.schema.json")
        self.assertTrue(any("profile" in e and "one of" in e for e in errs))
        self.assertTrue(any("unknown field 'extra'" in e for e in errs))

    def test_extends_needs_path_or_pinned_url(self):
        errs = json_schema.validate({"aidd_version": "1.0.0", "profile": "team", "extends": [{"url": "https://x/y.yaml"}]}, "config.schema.json")
        self.assertTrue(errs)


class GlobTests(unittest.TestCase):
    def test_semantics(self):
        self.assertTrue(globs.match("**/AGENTS.md", "AGENTS.md"))
        self.assertTrue(globs.match("**/AGENTS.md", "pkg/a/AGENTS.md"))
        self.assertTrue(globs.match("src/checkout", "src/checkout/x.py"))
        self.assertTrue(globs.match("src/checkout/", "src/checkout/a/b.py"))
        self.assertFalse(globs.match("src/checkout", "src/checkout2/x.py"))
        self.assertTrue(globs.match("src/*.py", "src/a.py"))
        self.assertFalse(globs.match("src/*.py", "src/a/b.py"))
        self.assertTrue(globs.match(".aidd/**", ".aidd/config.yaml"))

    def test_overlap(self):
        self.assertTrue(globs.overlap("src/", "src/a/**"))
        self.assertTrue(globs.overlap("**/*.py", "src/a.py"))
        self.assertFalse(globs.overlap("src/a/", "src/b/"))


class ConfigTests(unittest.TestCase):
    BASE = 'aidd_version: "1.0.0"\nprofile: team\n'

    def test_url_extends_is_pinned(self):
        parent = 'aidd_version: "1.0.0"\nprofile: team\n'
        good = hashlib.sha256(parent.encode()).hexdigest()
        child = 'aidd_version: "1.0.0"\nprofile: team\nextends: [{url: https://example.com/p.yaml, sha256: "%s"}]\n'
        config.load_text(child % good, prefetched={"https://example.com/p.yaml": parent})
        with self.assertRaises(config.ConfigError):
            config.load_text(child % ("0" * 64), prefetched={"https://example.com/p.yaml": parent})


class RedRunTests(unittest.TestCase):
    """A red run proves new behavior only when the test failed. pytest says in its exit code when it did not get that
    far: 3 internal error, 4 usage error, 5 no tests collected. Exit 2 (a collection error, as from importing a module
    that does not exist yet) is the usual first red and still counts."""

    def red(self, command, exit_code):
        from aidd.testing import red_ok

        return red_ok({"status": "failed", "exit": exit_code, "command": command})

    def test_pytest_exit_codes_that_are_not_a_failing_test(self):
        for command in (
            ["pytest", "-q", "t.py"],
            ["python3", "-m", "pytest", "t.py"],
            ["uv", "run", "pytest"],
            ["/usr/bin/py.test"],
            ["python", "-P", "-m", "pytest"],
        ):
            for code in (3, 4, 5):
                self.assertFalse(self.red(command, code), (command, code))
            self.assertTrue(self.red(command, 1), command)
            self.assertTrue(self.red(command, 2), command)

    def test_other_runners_keep_every_real_exit_code(self):
        for command in (["go", "test", "./..."], ["npm", "test"], ["python3", "-m", "unittest", "tests/test_x.py"], ["cargo", "test"]):
            for code in (1, 2, 5):
                self.assertTrue(self.red(command, code), (command, code))
        for code in (126, 127, None):
            self.assertFalse(self.red(["go", "test"], code))


class ModelTests(unittest.TestCase):
    spec_text = (ROOT / "tests/fixtures/specs/SPEC-220.md").read_text(encoding="utf-8")

    def test_example_specs_are_valid(self):
        for p in (ROOT / "tests/fixtures/specs").glob("*.md"):
            _, _, errs = spec_file.load_object(p.read_text(encoding="utf-8"), p.name)
            self.assertEqual(errs, [], p.name)

    def test_lint_catches_scope_over_tests_and_overlap(self):
        spec, body = documents.split_front_matter(self.spec_text)
        spec["tasks"][0]["scope"].append("tests/")
        spec["tasks"].append({"id": "T2", "title": "x", "scope": ["src/checkout/"]})
        errs = spec_file.lint_spec(spec, body)
        self.assertTrue(any("overlaps test file" in e for e in errs))
        spec["tests"]["files"] = ["**"]
        self.assertTrue(any("matches every path" in e for e in spec_file.lint_spec(spec, body)))
        self.assertTrue(any("must depend_on" in e for e in errs))
        spec["tasks"][1]["depends_on"] = ["TASK-220"]
        self.assertFalse(any("must depend_on" in e for e in spec_file.lint_spec(spec, body)))


class TemplateTests(unittest.TestCase):
    def test_new_objects_validate(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for kind, route in (("spec", "normal"), ("spec", "major"), ("spec", "emergency"), ("epic", "normal"), ("initiative", "normal")):
                p = authoring.new_object(
                    root,
                    authoring.NewObject(item_type=kind, id=f"X-{kind}-{route}", title="Example", route=route, owner_team="core", today=dt.date(2026, 9, 23)),
                )
                errs = [e for e in validation.validate_file(p) if not e.startswith("warning: ") and "TODO placeholders" not in e]
                self.assertEqual(errs, [], p.name)
                if kind == "spec":
                    # A fresh Spec cannot reach Spec approval until its tests and scope are real.
                    self.assertTrue(any("TODO placeholders" in e for e in validation.validate_file(p)), p.name)
                    self.assertEqual("\nobserve:" in p.read_text(encoding="utf-8"), route != "normal", p.name)


class SkillTests(unittest.TestCase):
    def test_the_skill_links_nowhere_outside_its_folder(self):
        import re as _re

        skill = ROOT / ".agents" / "skills" / "aidd"
        for path in skill.rglob("*.md"):
            for m in _re.finditer(r"\]\(([^)\s#]+)(?:#[^)]*)?\)", path.read_text(encoding="utf-8")):
                target = m.group(1)
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                resolved = (path.parent / target).resolve()
                self.assertTrue(resolved.is_relative_to(skill.resolve()), f"{path.relative_to(ROOT)} links outside the skill: {target}")
                self.assertTrue(resolved.exists(), f"{path.relative_to(ROOT)} links to a missing file: {target}")


class ShortSpecTests(unittest.TestCase):
    """`aidd new spec` writes the short Spec for a normal change; filled in, it validates with no warning at all."""

    def fill(self, text: str) -> str:
        for old, new in (
            ('summary: "TODO: who or what behaves differently after this change"', "summary: Cart totals can apply a discount."),
            ('title: "TODO: the first slice"', "title: Add discount()"),
            ('scope: ["src/TODO/"]', "scope: [app/discount.py]"),
            ('files: ["tests/TODO"]', "files: [tests/test_discount.py]"),
            ('command: ["TODO"]', "command: [python3, -m, unittest, tests.test_discount]"),
            ("TODO: quote the request.", "Checkout needs a percentage discount."),
            ("TODO: the context.", "Totals are computed in app/; no discount exists yet."),
            ("- A1: TODO: given ..., when ..., then ...", "- A1: given a total of 200, when a 10% discount applies, then the total is 180"),
            ("TODO: the approach.", "One pure function, discount(total, percent), in app/discount.py."),
            ("TODO: how to undo it.", "Revert the change; nothing is stored."),
        ):
            self.assertIn(old, text)
            text = text.replace(old, new, 1)
        return text

    def test_the_short_spec_is_the_default_and_validates_clean(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = authoring.new_object(root, authoring.NewObject(item_type="spec", id="SPEC-1", title="Discount", owner_team="shop", today=dt.date(2026, 9, 28)))
            text = p.read_text(encoding="utf-8")
            self.assertEqual(spec_file.sections(text.split("---", 2)[2]), {"intent", "context", "acceptance", "design", "policy conflicts", "rollback"})
            self.assertIn("covers: [A1]", text)
            p.write_text(self.fill(text), encoding="utf-8")
            self.assertEqual(validation.validate_file(p), [])
            # --full is the long template; a major Spec gets it by default, and so does an emergency backfill.
            # Its detail (Alternatives, cross-cutting concerns, the Pre-mortem) lives in a linked tech spec.
            full = authoring.new_object(root, authoring.NewObject(item_type="spec", id="SPEC-2", title="t", owner_team="shop", full=True)).read_text(
                encoding="utf-8"
            )
            self.assertIn("## Problem", full)
            self.assertIn("# docs:", full)
            major = authoring.new_object(root, authoring.NewObject(item_type="spec", id="SPEC-3", title="t", owner_team="shop", route="major")).read_text(
                encoding="utf-8"
            )
            self.assertNotIn("## Rollout", major)  # the rollout is the runbook's, which the Spec links
            self.assertIn("aidd new runbook", major)
            self.assertIn("aidd new tech-spec", major)

    def test_the_short_template_stays_in_step_with_the_full_one(self):
        """The same front matter keys, so a short Spec can grow into a full one by adding sections."""
        assets = ROOT / ".agents" / "skills" / "aidd" / "assets"
        short = documents.parse_yaml((assets / "spec-short.md").read_text(encoding="utf-8").split("---")[1], "short")
        full = documents.parse_yaml((assets / "spec.md").read_text(encoding="utf-8").split("---")[1], "full")
        self.assertLessEqual(set(short), set(full))
        self.assertLessEqual(set(short["tests"]["commands"][0]), set(full["tests"]["commands"][0]))


if __name__ == "__main__":
    unittest.main()
