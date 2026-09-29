import datetime as dt
import hashlib
import tempfile
import unittest
from pathlib import Path

import helpers
from helpers import ROOT, example

from aidd import config, docs, evals, globs, model, repo, resources, rules, schema


class SchemaTests(unittest.TestCase):
    def test_every_schema_file_is_valid_json_with_an_id(self):
        for p in (ROOT / "schemas").glob("*.schema.json"):
            data = resources.load_json(p.name)
            self.assertTrue(data["$id"].startswith("urn:aidd:1:"), p.name)

    def test_required_enum_and_unknown_fields(self):
        errs = schema.validate({"aidd_version": "1.0.0", "profile": "chaos", "extra": 1}, "config.schema.json")
        self.assertTrue(any("profile" in e and "one of" in e for e in errs))
        self.assertTrue(any("unknown field 'extra'" in e for e in errs))

    def test_conditional_required(self):
        errs = schema.validate({"route": "minor"}, "change-request.schema.json")
        self.assertTrue(any("assisted_by" in e for e in errs))
        self.assertEqual(schema.validate({"spec": "specs/A.md"}, "change-request.schema.json"), [])

    def test_extends_needs_path_or_pinned_url(self):
        errs = schema.validate({"aidd_version": "1.0.0", "profile": "team", "extends": [{"url": "https://x/y.toml"}]}, "config.schema.json")
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
        self.assertTrue(globs.match(".aidd/**", ".aidd/config.toml"))

    def test_overlap(self):
        self.assertTrue(globs.overlap("src/", "src/a/**"))
        self.assertTrue(globs.overlap("**/*.py", "src/a.py"))
        self.assertFalse(globs.overlap("src/a/", "src/b/"))


class ConfigTests(unittest.TestCase):
    BASE = 'aidd_version = "1.0.0"\nprofile = "team"\n'

    def test_profile_defaults(self):
        c = config.load_text(self.BASE)
        self.assertTrue(c.gates["separation_of_duties"])
        self.assertEqual(c.gates["max_changed_lines"]["normal"], 400)

    def test_gates_only_tighten(self):
        c = config.load_text(
            self.BASE
            + '[gates]\nseparation_of_duties = false\napprovals = { normal = 0, major = 3 }\nmax_changed_lines = { normal = 999, minor = 20 }\nred_green = "warn"\n'
        )
        self.assertTrue(c.gates["separation_of_duties"])
        self.assertEqual(c.gates["approvals"]["normal"], 1)
        self.assertEqual(c.gates["approvals"]["major"], 3)
        self.assertEqual(c.gates["max_changed_lines"]["normal"], 400)
        self.assertEqual(c.gates["max_changed_lines"]["minor"], 20)
        self.assertEqual(c.gates["red_green"], "require")
        self.assertEqual(len(c.warnings), 4)

    def test_extends_merges_and_cannot_weaken_profile(self):
        parent = 'aidd_version = "1.0.0"\nprofile = "org"\nprotected_paths = ["infra/**"]\n[gates]\napprovals = { normal = 2 }\n'
        child = 'aidd_version = "1.0.0"\nprofile = "org"\nextends = [{ path = "org.toml" }]\n'
        c = config.load_text(child, prefetched={"org.toml": parent})
        self.assertIn("infra/**", c.get("protected_paths"))
        self.assertEqual(c.gates["approvals"]["normal"], 2)
        weak = child.replace('profile = "org"', 'profile = "team"')
        with self.assertRaises(config.ConfigError):
            config.load_text(weak, prefetched={"org.toml": parent})

    def test_url_extends_is_pinned(self):
        parent = 'aidd_version = "1.0.0"\nprofile = "team"\n'
        good = hashlib.sha256(parent.encode()).hexdigest()
        child = 'aidd_version = "1.0.0"\nprofile = "team"\nextends = [{ url = "https://example.com/p.toml", sha256 = "%s" }]\n'
        config.load_text(child % good, prefetched={"https://example.com/p.toml": parent})
        with self.assertRaises(config.ConfigError):
            config.load_text(child % ("0" * 64), prefetched={"https://example.com/p.toml": parent})


class RuleTests(unittest.TestCase):
    cfg = config.load_text('aidd_version = "1.0.0"\nprofile = "team"\n')

    def assess(self, paths, **kw):
        args = dict(cfg=self.cfg, ctype="feat", risk={"dimensions": [], "reversible": True}, confidence="high", task_count=1, changed_lines=10)
        args.update(kw)
        return rules.assess(paths=paths, **args)

    def test_minor_and_normal(self):
        self.assertEqual(self.assess(["docs/a.md"]).required_route, "minor")
        self.assertEqual(self.assess(["docs/a.md"], changed_lines=51).required_route, "normal")
        self.assertEqual(self.assess(["src/a.py"], task_count=2).required_route, "normal")

    def test_protected_and_baseline(self):
        self.assertEqual(self.assess([".github/workflows/ci.yml"]).required_route, "major")
        self.assertEqual(self.assess(["AGENTS.md"]).required_route, "major")
        c = self.assess(["package.json"])
        self.assertEqual(c.required_route, "normal")
        self.assertIn("third_party", c.dimensions)
        self.assertEqual(self.assess(["db/migrations/1.sql"]).required_route, "major")

    def test_risk_and_type(self):
        self.assertEqual(self.assess(["src/a.py"], risk={"dimensions": ["security"], "reversible": True}).required_route, "major")
        self.assertEqual(self.assess(["src/a.py"], risk={"dimensions": [], "reversible": False}).required_route, "major")
        self.assertEqual(self.assess(["src/a.py"], ctype="security").required_route, "major")

    def test_standard_never_covers_major(self):
        self.assertEqual(self.assess(["package.json"], standard_ok=True).required_route, "standard")
        self.assertEqual(self.assess([".github/workflows/x.yml"], standard_ok=True).required_route, "major")

    def test_disable_baseline_rule(self):
        cfg = config.load_text('aidd_version = "1.0.0"\nprofile = "team"\ndisable_rules = ["baseline:auth"]\n')
        c = rules.assess(
            paths=["src/auth/x.ts"], cfg=cfg, ctype="feat", risk={"dimensions": [], "reversible": True}, confidence="high", task_count=1, changed_lines=1
        )
        self.assertEqual(c.required_route, "minor")


class ModelTests(unittest.TestCase):
    spec_text = (ROOT / "examples/_specs/SPEC-220.md").read_text(encoding="utf-8")

    def test_example_specs_are_valid(self):
        for p in (ROOT / "examples/_specs").glob("*.md"):
            _, _, errs = model.load_object(p.read_text(encoding="utf-8"), p.name)
            self.assertEqual(errs, [], p.name)

    def test_hash_ignores_status_but_covers_tests(self):
        tree = {"tests/checkout/test_rate_limit.py": "1" * 40}
        h = model.spec_hash(self.spec_text, tree)
        with_status = self.spec_text.replace('route = "normal"', 'route = "normal"\nstatus = "in_progress"')
        self.assertEqual(model.spec_hash(with_status, tree), h)
        self.assertNotEqual(model.spec_hash(self.spec_text, {"tests/checkout/test_rate_limit.py": "2" * 40}), h)
        self.assertNotEqual(model.spec_hash(self.spec_text.replace("61 requests", "62 requests"), tree), h)

    def test_lint_catches_scope_over_tests_and_overlap(self):
        spec, body = model.split_front_matter(self.spec_text)
        spec["tasks"][0]["scope"].append("tests/")
        spec["tasks"].append({"id": "T2", "title": "x", "scope": ["src/checkout/"]})
        errs = model.lint_spec(spec, body)
        self.assertTrue(any("overlaps test file" in e for e in errs))
        spec["tests"]["files"] = ["**"]
        self.assertTrue(any("matches every path" in e for e in model.lint_spec(spec, body)))
        self.assertTrue(any("must depend_on" in e for e in errs))
        spec["tasks"][1]["depends_on"] = ["TASK-220"]
        self.assertFalse(any("must depend_on" in e for e in model.lint_spec(spec, body)))

    def test_change_block(self):
        cr, errs = model.parse_change_block('x\n```toml aidd\nspec = "specs/A.md"\n```\n')
        self.assertEqual((cr, errs), ({"spec": "specs/A.md"}, []))
        _, errs = model.parse_change_block('```toml aidd\nspec = "a"\n```\n```toml aidd\nspec = "b"\n```\n')
        self.assertTrue(errs)


class TemplateTests(unittest.TestCase):
    def test_new_objects_validate(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for kind, route in (("spec", "normal"), ("spec", "major"), ("spec", "emergency"), ("epic", "normal"), ("initiative", "normal")):
                p = repo.new_object(root, kind=kind, id=f"X-{kind}-{route}", title="Example", route=route, owner_team="core", today=dt.date(2026, 9, 23))
                errs = [e for e in repo.validate_file(p) if not e.startswith("warning: ") and "TODO placeholders" not in e]
                self.assertEqual(errs, [], p.name)
                if kind == "spec":
                    # A fresh Spec cannot reach Spec approval until its tests and scope are real.
                    self.assertTrue(any("TODO placeholders" in e for e in repo.validate_file(p)), p.name)
                    self.assertEqual("[observe]" in p.read_text(encoding="utf-8"), route != "normal", p.name)

    def test_config_template_validates_for_every_profile(self):
        for profile in resources.profiles()["order"]:
            config.load_text(repo.config_text(profile, approvers=["@org/leads"]))
        text = repo.config_text("team", approvers=["@a"], reviewers={"security": ["@s"], "data": ["@d"]}, test=["npm", "test"], policy=["./p"])
        c = config.load_text(text)
        self.assertEqual(
            (c.approvers, c.reviewers, c.get("tests")[0]["command"], c.policy_command), (["@a"], {"security": ["@s"], "data": ["@d"]}, ["npm", "test"], ["./p"])
        )
        with self.assertRaises(ValueError):
            repo.fill("{{missing}}")

    def test_change_request_template_blocks_validate(self):
        text = (resources.data_dir("skill") / "assets" / "change-request.md").read_text(encoding="utf-8")
        blocks = helpers.CHANGE_BLOCK.findall(text)
        self.assertEqual(len(blocks), 4)
        for b in blocks:
            b = b.replace("YYYY-MM-DD", "2026-09-25")  # the template's placeholder date
            self.assertEqual(schema.validate(model.parse_toml(b, "block"), "change-request.schema.json"), [])


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


class DiagramWarningTests(unittest.TestCase):
    def test_a_spec_without_a_diagram_gets_a_warning_never_an_error(self):
        normal = example("02-normal-feature")["head_files"]["specs/SPEC-220.md"]
        # Only on major: a normal Spec may be the short one, whose Design is a few lines.
        spec = normal.replace('route = "normal"', 'route = "major"', 1)
        self.assertFalse(repo.has_diagram(spec))
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "SPEC-220.md"
            path.write_text(normal, encoding="utf-8")
            self.assertFalse(any("no diagram" in x or "Alternatives" in x for x in repo.validate_file(path)))
            path.write_text(spec, encoding="utf-8")
            out = repo.validate_file(path)
            self.assertTrue(any("warning:" in x and "no diagram" in x for x in out), out)
            self.assertFalse(any("no diagram" in x and not x.startswith("warning:") for x in out))
            path.write_text(spec + "\n## Design\n\n```mermaid\nflowchart LR\n  a --> b\n```\n", encoding="utf-8")
            self.assertFalse(any("no diagram" in x for x in repo.validate_file(path)))
            path.write_text(spec + "\n## Design\n\n![flow](docs/design/flow.svg)\n", encoding="utf-8")
            self.assertFalse(any("no diagram" in x for x in repo.validate_file(path)))
        template = (ROOT / ".agents" / "skills" / "aidd" / "assets" / "spec.md").read_text(encoding="utf-8")
        self.assertIn("```mermaid", template)


class ShortSpecTests(unittest.TestCase):
    """`aidd new spec` writes the short Spec for a normal change; filled in, it validates with no warning at all."""

    def fill(self, text: str) -> str:
        for old, new in (
            ('summary = "TODO: who or what behaves differently after this change"', 'summary = "Cart totals can apply a discount."'),
            ('title = "TODO: the first slice"', 'title = "Add discount()"'),
            ('scope = ["src/TODO/"]', 'scope = ["app/discount.py"]'),
            ('files = ["tests/TODO"]', 'files = ["tests/test_discount.py"]'),
            ('command = ["TODO"]', 'command = ["python3", "-m", "unittest", "tests.test_discount"]'),
            ("TODO: quote the request.", "Checkout needs a percentage discount."),
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
            p = repo.new_object(root, kind="spec", id="SPEC-1", title="Discount", owner_team="shop", today=dt.date(2026, 9, 28))
            text = p.read_text(encoding="utf-8")
            self.assertEqual(model.sections(text.split("+++", 2)[2]), {"intent", "acceptance", "design", "rollback"})
            self.assertIn('covers = ["A1"]', text)
            p.write_text(self.fill(text), encoding="utf-8")
            self.assertEqual(repo.validate_file(p), [])
            # --full is the long template; a major Spec gets it by default, and so does an emergency backfill.
            full = repo.new_object(root, kind="spec", id="SPEC-2", title="t", owner_team="shop", full=True).read_text(encoding="utf-8")
            self.assertIn("## Alternatives considered", full)
            major = repo.new_object(root, kind="spec", id="SPEC-3", title="t", owner_team="shop", route="major").read_text(encoding="utf-8")
            self.assertIn("## Pre-mortem", major)

    def test_the_quickstart_table_fills_the_short_spec_to_zero_warnings(self):
        """docs/QUICKSTART.md step 3 edits the Spec in place from a table; applied as written, it validates clean."""
        import re as _re

        doc = (ROOT / "docs" / "QUICKSTART.md").read_text(encoding="utf-8")
        step = doc.split("## 3. ", 1)[1].split("\n## ", 1)[0]
        self.assertIn("aidd new spec SPEC-1", step)
        self.assertNotIn("aidd assess", doc)
        self.assertIn("../approvals.json", doc)  # the dry-run file stays out of the repository
        self.assertIn("--ref HEAD~1` hashes", doc)
        rows = []
        for line in step.splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 3 and cells[1].startswith("`"):
                rows.append((_re.match(r"`([^`]*)`", cells[1]).group(1), _re.match(r"`([^`]*)`", cells[2]).group(1)))
        self.assertGreaterEqual(len(rows), 8)
        with tempfile.TemporaryDirectory() as d:
            p = repo.new_object(Path(d), kind="spec", id="SPEC-1", title="Apply a percentage discount", owner_team="shop", scope=["app/discount.py"])
            text = p.read_text(encoding="utf-8")
            for old, new in rows:
                self.assertEqual(text.count(old), 1, old)
                text = text.replace(old, new)
            self.assertNotIn("TODO", text)
            p.write_text(text, encoding="utf-8")
            self.assertEqual(repo.validate_file(p), [])

    def test_the_short_template_stays_in_step_with_the_full_one(self):
        """The same front matter keys, so a short Spec can grow into a full one by adding sections."""
        assets = ROOT / ".agents" / "skills" / "aidd" / "assets"
        short = model.parse_toml((assets / "spec-short.md").read_text(encoding="utf-8").split("+++")[1], "short")
        full = model.parse_toml((assets / "spec.md").read_text(encoding="utf-8").split("+++")[1], "full")
        self.assertLessEqual(set(short), set(full))
        self.assertLessEqual(set(short["tests"]["commands"][0]), set(full["tests"]["commands"][0]))


class ExampleSuiteTests(unittest.TestCase):
    def test_examples_match_expected(self):
        results = evals.run_examples(ROOT)
        self.assertGreaterEqual(len(results), 13)
        for r in results:
            self.assertTrue(r["ok"], f"{r['case']}: got {r['got']} want {r['want']}")

    def test_every_record_validates_against_its_schema(self):
        import copy
        import json as _json

        from aidd import schema
        from aidd.verify import verify

        seen = set()
        for case in sorted(p for p in (ROOT / "examples").iterdir() if (p / "context.json").is_file()):
            ctx, _ = evals.load_example(case)
            records = [(case.name, verify(copy.deepcopy(ctx)).record)]
            for mfile in sorted((case / "mutations").glob("*.json")) if (case / "mutations").is_dir() else []:
                ops = _json.loads(mfile.read_text(encoding="utf-8"))["ops"]
                records.append((f"{case.name}/{mfile.stem}", verify(evals.apply_ops(copy.deepcopy(ctx), ops)).record))
            for name, record in records:
                self.assertEqual(schema.validate(record, "record.schema.json"), [], name)
                seen |= set(record)
        # The schema documents every field the gate can write, and nothing it never writes.
        documented = set(docs._node("record.schema.json", ["properties"]))
        self.assertTrue(seen <= documented, seen - documented)
        self.assertTrue(documented - seen <= {"shared_with", "status_checks", "spec_approval_before_implementation"}, documented - seen)


if __name__ == "__main__":
    unittest.main()
