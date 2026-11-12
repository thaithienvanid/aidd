"""Interface consumers: a revised Spec that provides an interface makes `aidd status` name the open Specs that consume it,
and `aidd validate` warns about an interface nobody provides. Advice only: nothing here blocks a revision."""

import unittest

import helpers  # noqa: F401  (hermetic setup)
from test_workitems import Base, spec

from aidd.kernel import json_schema
from aidd.workitems import interfaces, validation

REVISED = "revisions: [{why: the payload changed}]"


def provider(sid="SPEC-1", status="draft", interfaces="orders-api", revised=True) -> str:
    extra = f"provides: [{interfaces}]" + (f"\n{REVISED}" if revised else "")
    return spec(sid, status, extra)


def consumer(sid, interfaces="orders-api", status="approved", owner="owner: alice") -> str:
    return spec(sid, status, f"consumes: [{interfaces}]\n{owner}")


class StatusNamesConsumers(Base):
    def step(self, sid: str = "SPEC-1") -> dict:
        return self.items()[sid]["next"]

    def test_who_hears_first(self):
        # (name, provider file, other files, expected code, names that appear in the step, names that do not)
        cases = [
            (
                "draft revised",
                provider(),
                {"SPEC-2": consumer("SPEC-2"), "SPEC-3": consumer("SPEC-3", owner="development_team: pay")},
                "spec.consumers",
                ["SPEC-2", "alice", "SPEC-3", "pay", "orders-api"],
                [],
            ),
            ("ready revised keeps the approval step", provider(status="ready"), {"SPEC-2": consumer("SPEC-2")}, "spec.approve", ["SPEC-2", "alice"], []),
            ("never revised", provider(revised=False), {"SPEC-2": consumer("SPEC-2")}, "spec.draft", [], ["SPEC-2"]),
            ("a finished consumer", provider(), {"SPEC-2": consumer("SPEC-2", status="done")}, "spec.draft", [], ["SPEC-2"]),
            ("another interface", provider(), {"SPEC-2": consumer("SPEC-2", interfaces="billing-api")}, "spec.draft", [], ["SPEC-2"]),
            ("approved again", provider(status="approved"), {"SPEC-2": consumer("SPEC-2")}, "spec.approved", [], ["SPEC-2"]),
        ]
        for name, main, others, code, present, absent in cases:
            with self.subTest(name):
                self.write("specs/SPEC-1.md", main)
                for sid, text in others.items():
                    self.write(f"specs/{sid}.md", text)
                step = self.step()
                self.assertEqual(step["code"], code)
                for text in present:
                    self.assertIn(text, step["what"])
                for text in absent:
                    self.assertNotIn(text, step["what"])
                for sid in others:
                    (self.root / f"specs/{sid}.md").unlink()

    def test_the_consumer_is_not_told_about_itself(self):
        self.write("specs/SPEC-1.md", spec("SPEC-1", "draft", f"provides: [orders-api]\nconsumes: [orders-api]\n{REVISED}"))
        self.assertEqual(self.step()["code"], "spec.draft")

    def test_the_step_is_the_agents_and_blocks_nothing(self):
        self.write("specs/SPEC-1.md", provider())
        self.write("specs/SPEC-2.md", consumer("SPEC-2"))
        self.assertEqual(self.step()["who"], "agent")
        self.assertNotIn("blocked", self.items()["SPEC-1"]["next"]["what"])


class ValidateWarnsOfUnprovidedContracts(unittest.TestCase):
    def warnings(self, *objects: dict) -> list[str]:
        return interfaces.unprovided_warnings([(f"specs/{d['id']}.md", {"type": "spec", **d}) for d in objects])

    def test_which_consumers_are_named(self):
        cases = [
            ("provided", [{"id": "A", "provides": ["orders-api"]}, {"id": "B", "consumes": ["orders-api"]}], 0),
            ("nobody provides it", [{"id": "B", "consumes": ["orders-api"]}], 1),
            ("one of two", [{"id": "A", "provides": ["x"]}, {"id": "B", "consumes": ["x", "y"]}], 1),
            ("no interfaces", [{"id": "A"}], 0),
            ("a malformed field", [{"id": "A", "consumes": "orders-api"}], 0),
        ]
        for name, objects, count in cases:
            with self.subTest(name):
                self.assertEqual(len(self.warnings(*objects)), count)

    def test_a_warning_names_the_file_and_the_contract(self):
        (line,) = self.warnings({"id": "B", "consumes": ["orders-api"]})
        self.assertTrue(line.startswith("specs/B.md: "))
        self.assertIn("orders-api", line)


class ValidateRepoWarnsOnly(Base):
    def test_an_unprovided_contract_is_a_warning_never_an_error(self):
        self.write("specs/SPEC-2.md", consumer("SPEC-2"))
        errors, warnings = validation.check_repo(self.root)
        self.assertTrue(any("SPEC-2.md: consumes orders-api" in w for w in warnings))
        self.assertFalse(any("orders-api" in e for e in errors))
        self.write("specs/SPEC-1.md", provider(revised=False))
        self.assertFalse(any("orders-api" in w for w in validation.check_repo(self.root)[1]))


class TheFieldsAreInTheSchema(unittest.TestCase):
    def test_contract_names_are_stable_names(self):
        for name, ok in [("orders-api", True), ("order.created", True), ("billing:invoice-v2", True), ("GET /orders", False), ("", False), ("-x", False)]:
            for field in ("provides", "consumes"):
                with self.subTest(f"{field} {name!r}"):
                    errors = json_schema.validate({field: [name]}, "spec.schema.json")
                    self.assertEqual(not any(field in e for e in errors), ok, errors)


if __name__ == "__main__":
    unittest.main()
