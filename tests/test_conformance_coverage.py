"""The conformance suite (examples/) is the specification of the verifier's behavior.

AGENTS.md: every gate rule needs a passing and a failing case, and a row in src/aidd/rulebook.py.
These tests hold that invariant against the portable corpus itself, by running it once: every
level each rulebook row declares must be emitted by at least one case. A Python test does not
count, because another implementation of the verifier cannot run it.
"""

from __future__ import annotations

import copy
import functools
import json
import re
import unittest

from helpers import ROOT

from aidd import evals, rulebook
from aidd.verify import verify

# (rule, level) pairs no well-formed conformance case can produce, each with the reason. This list
# may only shrink: a new entry means a rule shipped without a portable case.
UNREACHABLE_BY_A_CASE = {
    ("internal", "fail"): "a verifier crash; a correct verifier has no input that triggers it (tests/test_verifier.py covers the fail-closed path)",
}


# Finding codes (`code=` in src/aidd/gates.py, rules.py, verify.py) no conformance case emits, each with the reason.
# The set must equal what the corpus leaves uncovered, so a code a new case covers comes off this list, and a new
# code without a case fails. Most entries are defense in depth: a schema the context or block passes first already
# rejects the input that would reach them.
UNREACHABLE_OR_UNTESTED = {
    "internal.crash": "a verifier crash; a correct verifier has no input that triggers it (tests/test_verifier.py covers the fail-closed path)",
    "tests.evidence_schema": "context.schema.json already validates evidence against evidence.schema.json, so context.invalid fires first",
    "emergency.no_block": "the Change Request schema requires the emergency block on route emergency, so change_request.invalid fires first",
    "emergency.review_due_invalid": "the Change Request schema checks review_due is an ISO date with the same parser, so change_request.invalid fires first",
}
# The size UNREACHABLE_OR_UNTESTED may not exceed. It may only shrink: lower it when a case covers an entry.
MAX_UNREACHABLE_OR_UNTESTED = 4
CODE_SOURCES = ("gates.py", "rules.py", "verify.py")


@functools.lru_cache(maxsize=1)
def _decisions() -> tuple[tuple[str, tuple], ...]:
    """Every case and mutation in examples/ with its decision's findings. Run once per test process."""
    out = []
    for case in sorted(p for p in (ROOT / "examples").iterdir() if (p / "context.json").is_file()):
        ctx, _ = evals.load_example(case)
        out.append((case.name, tuple(verify(copy.deepcopy(ctx)).findings)))
        for m in sorted((case / "mutations").glob("*.json")) if (case / "mutations").is_dir() else []:
            mutated = evals.apply_ops(copy.deepcopy(ctx), json.loads(m.read_text(encoding="utf-8"))["ops"])
            out.append((f"{case.name}/{m.stem}", tuple(verify(mutated).findings)))
    return tuple(out)


def corpus() -> tuple[tuple[str, frozenset[tuple[str, str]]], ...]:
    """Every case and mutation, with the (rule, level) pairs its decision holds."""
    return tuple((name, frozenset((f.rule, f.level) for f in findings)) for name, findings in _decisions())


def emitted_codes() -> set[str]:
    return {f.code for _, findings in _decisions() for f in findings}


def declared_codes() -> tuple[set[str], list[str]]:
    """The finding codes the verifier can emit, as `code="..."` literals, and where a code is not a literal."""
    import ast

    codes, dynamic = set(), []
    for name in CODE_SOURCES:
        tree = ast.parse((ROOT / "src" / "aidd" / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "code":
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    codes.add(node.value.value)
                else:
                    dynamic.append(f"{name}:{node.value.lineno}")
    return codes, dynamic


def declared_levels(rule: rulebook.Rule) -> set[str]:
    """The levels a rulebook row names, from prose such as "fail, pending, or warn"."""
    return set(re.findall(r"\b(fail|pending|warn)\b", rule.levels))


class ConformanceCoverageTests(unittest.TestCase):
    def test_every_rulebook_level_is_emitted_by_a_case(self):
        emitted = set().union(*(pairs for _, pairs in corpus()))
        missing = []
        for name, rule in sorted(rulebook.BY_NAME.items()):
            levels = declared_levels(rule)
            if rule.levels == "as reported":  # policy:<rule>: the Policy command picks the level
                if not any(r.startswith(name.split(":")[0] + ":") for r, _ in emitted):
                    missing.append(f"{name} (any level)")
                continue
            self.assertTrue(levels, f"rulebook row {name!r} names no level: {rule.levels!r}")
            for level in sorted(levels):
                if (name, level) in UNREACHABLE_BY_A_CASE:
                    continue
                prefix = name.split(":")[0] + ":" if ":" in name else None  # policy:<rule> is any policy finding
                hit = (name, level) in emitted or bool(prefix and any(r.startswith(prefix) and lv == level for r, lv in emitted))
                if not hit:
                    missing.append(f"{name} {level}")
        self.assertEqual(missing, [], "add an examples/ mutation that produces each of these")

    def test_every_finding_code_is_emitted_by_a_case(self):
        declared, dynamic = declared_codes()
        self.assertEqual(dynamic, [], "a finding code that is not a string literal cannot be checked here; make it one")
        self.assertGreater(len(declared), 50, "the code collection found almost nothing; did the gates move?")
        self.assertLessEqual(set(UNREACHABLE_OR_UNTESTED), declared, "an allowlist entry names no code the verifier declares")
        self.assertLessEqual(len(UNREACHABLE_OR_UNTESTED), MAX_UNREACHABLE_OR_UNTESTED, "the allowlist may only shrink")
        uncovered = declared - emitted_codes()
        self.assertEqual(
            sorted(uncovered - set(UNREACHABLE_OR_UNTESTED)), [], "add an examples/ mutation that emits each of these codes and pins it in its expectation"
        )
        self.assertEqual(sorted(set(UNREACHABLE_OR_UNTESTED) - uncovered), [], "a case now emits these: remove them from UNREACHABLE_OR_UNTESTED")

    def test_the_exception_list_holds_only_real_rules(self):
        for name, level in UNREACHABLE_BY_A_CASE:
            self.assertIn(level, declared_levels(rulebook.BY_NAME[name]))

    def test_the_rulebook_names_every_finding_code_the_verifier_declares(self):
        declared, _ = declared_codes()
        listed: dict[str, str] = {}
        for rule in rulebook.RULES:
            self.assertTrue(rule.codes, f"rulebook row {rule.name!r} lists no finding code")
            for code, meaning in rule.codes.items():
                self.assertNotIn(code, listed, f"{code} is listed under both {listed.get(code)} and {rule.name}")
                listed[code] = rule.name
                self.assertTrue(meaning.strip(), code)
                if rule.name != "policy:<rule>":
                    self.assertEqual(code.split(".", 1)[0], rule.name, f"{code} is listed under {rule.name}")
        self.assertEqual(sorted(set(listed) - {"policy:<rule>"}), sorted(declared))
        readme = (ROOT / "examples" / "README.md").read_text(encoding="utf-8")
        from aidd import docs

        self.assertIn("<!-- aidd:gen rules:codes -->\n" + docs.render("rules:codes") + "\n<!-- aidd:end -->", readme)
        self.assertIn("`merge_approval.unsigned`", docs.render("rules:codes"))

    def test_every_rule_the_verifier_emits_has_a_rulebook_row(self):
        emitted = {r for _, pairs in corpus() for r, _ in pairs}
        unknown = sorted(r for r in emitted if r not in rulebook.BY_NAME and not (":" in r and r.split(":")[0] + ":<rule>" in rulebook.BY_NAME))
        self.assertEqual(unknown, [])

    def test_every_case_file_matches_the_conformance_schema(self):
        from aidd import schema

        bad = {}
        for case in sorted(p for p in (ROOT / "examples").iterdir() if (p / "expected.json").is_file()):
            for f in [case / "expected.json", *sorted((case / "mutations").glob("*.json"))]:
                errs = schema.validate(json.loads(f.read_text(encoding="utf-8")), "conformance.schema.json")
                if errs:
                    bad[str(f.relative_to(ROOT))] = errs[:3]
        self.assertEqual(bad, {})

    def test_materialized_cases_decide_the_same_without_the_loader(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            n = evals.materialize(ROOT, Path(d))
            self.assertEqual(n, len(corpus()))
            for case in sorted(Path(d).iterdir()):
                ctx = json.loads((case / "context.json").read_text(encoding="utf-8"))
                expected = json.loads((case / "expected.json").read_text(encoding="utf-8"))
                self.assertEqual(verify(ctx).codes(), expected["findings"], case.name)

    def test_every_case_matches_its_expectation(self):
        results = evals.run_examples(ROOT)
        self.assertTrue(all(r["ok"] for r in results), [r["case"] for r in results if not r["ok"]])
        self.assertGreaterEqual(len(results), 112, "the corpus shrank; a failing case was removed, not fixed")

    def test_every_case_has_a_title_and_a_summary_for_the_generated_table(self):
        from aidd import docs

        found = docs.example_cases(ROOT)
        self.assertEqual(len(found), len([p for p in (ROOT / "examples").iterdir() if (p / "context.json").is_file()]))
        self.assertEqual([c["name"] for c in found if not (c["title"] and c["summary"])], [])
        readme = (ROOT / "examples" / "README.md").read_text(encoding="utf-8")
        self.assertIn("<!-- aidd:gen examples:cases -->\n" + docs.examples_table(ROOT) + "\n<!-- aidd:end -->", readme)
        with self.assertRaises(KeyError):
            docs.render("examples:nothing")

    def test_the_quality_config_and_workspace_script_rules_have_a_passing_and_a_failing_case(self):
        names = {name for name, _ in corpus()}
        for failing, passing in (
            ("01-minor-docs/lint-config-in-a-minor-change", "02-normal-feature/lint-config-inside-a-normal-spec"),
            ("01-minor-docs/workspace-script-config-in-a-minor-change", "04-major-permission/worktree-include-in-a-major-change"),
        ):
            self.assertIn(failing, names)
            self.assertIn(passing, names)
        by = dict(_decisions())
        self.assertEqual([f.code for f in by["01-minor-docs/lint-config-in-a-minor-change"]], ["route.too_low"])
        self.assertIn("baseline:quality-config", by["01-minor-docs/lint-config-in-a-minor-change"][0].message)
        self.assertEqual([f.code for f in by["01-minor-docs/lint-ignore-file-in-a-minor-change"]], ["route.too_low"])
        self.assertIn("baseline:quality-config", by["01-minor-docs/lint-ignore-file-in-a-minor-change"][0].message)
        self.assertIn("orca.yaml", by["01-minor-docs/workspace-script-config-in-a-minor-change"][0].message)
        # A normal change is raised to major by either workspace file, even when the config exempts it from scope.
        for name, path in (
            ("02-normal-feature/workspace-script-config-raises-to-major", "orca.yaml"),
            ("02-normal-feature/worktree-include-raises-to-major", ".worktreeinclude"),
        ):
            raised = [f for f in by[name] if f.code == "route.raised_to_major"]
            self.assertEqual(len(raised), 1, name)
            self.assertIn(f"protected path matched {path}", raised[0].message)
            self.assertIn("specialist_review.missing", [f.code for f in by[name] if f.level == "pending"])


if __name__ == "__main__":
    unittest.main()
