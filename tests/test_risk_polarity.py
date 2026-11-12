"""A Spec says one polarity: `risk.irreversible`, as `aidd risk --irreversible` and the risk rules do. A flip read with the wrong
meaning inverts a control silently, so the reading is held to the one before it (tests/fixtures/start-answers/required-docs.json,
the answers of the commit that still said `reversible`): today's shape, with the value the table held written as its opposite, asks
for the same documents."""

import json
import unittest

import control_tables

from aidd import risk, workitems

START = json.loads((control_tables.ANSWERS / "required-docs.json").read_text(encoding="utf-8"))
OLD = control_tables.risk_specs()


def asked(data: dict) -> list[str]:
    return sorted(f"{a.doc_type} {a.level} {a.living}" for a in workitems.required_docs(data, None))


def todays(data: dict) -> dict:
    """`data` written by hand in today's shape: `irreversible` the opposite of `reversible`, and absent where it was absent; and the
    retired change type `data` as the type `feat` with the dimension `data`."""
    risk_ = {k: v for k, v in data["risk"].items() if k != "reversible"}
    if "reversible" in data["risk"]:
        risk_["irreversible"] = not data["risk"]["reversible"]
    out = {**data, "risk": risk_}
    if data["change_type"] == "data":
        out["change_type"] = "feat"
        risk_["dimensions"] = list(dict.fromkeys([*risk_["dimensions"], "data"]))
    return out


class TheRequiredDocumentsAsBefore(unittest.TestCase):
    def test_each_reading_asks_for_what_the_old_one_asked(self):
        """The old type `data` reads as its dimension, which asks for a threat model too (`threat-model` on normal and major): a
        reading may ask for more than the commit before it, never less."""
        self.assertEqual(sorted(START), sorted(OLD), "the table and its answers are one set")
        for key, data in OLD.items():
            with self.subTest(key):
                now, then = asked(todays(data)), START[key]
                if data["change_type"] == "data" and "data" not in data["risk"]["dimensions"]:
                    self.assertLessEqual(set(then), set(now))
                    self.assertEqual(set(now) - set(then), {"threat-model warn None"})
                else:
                    self.assertEqual(now, then)

    def test_an_irreversible_change_asks_for_its_documents(self):
        """The revert proof of the flip: were the rule to read `reversible` again, these would ask for nothing more."""
        base = {"type": "spec", "change_type": "feat", "tasks": [{"id": "T1", "scope": ["src/a/"]}]}
        for route, doc, level in (("normal", "migration-plan", "suggest"), ("major", "tech-spec", "warn"), ("major", "runbook", "warn")):
            with self.subTest(route=route, doc=doc):
                one_way = asked({**base, "route": route, "risk": {"summary": "s", "dimensions": [], "irreversible": True}})
                two_way = asked({**base, "route": route, "risk": {"summary": "s", "dimensions": [], "irreversible": False}})
                self.assertIn(f"{doc} {level} None", one_way)
                self.assertNotIn(f"{doc} {level} None", two_way)

    def test_the_route_reads_the_flag_of_the_same_name(self):
        rs = risk.rule_set(None)
        self.assertEqual(risk.route_for(rs, ["README.md"], risk.DeclaredRisk(irreversible=True)).route, "major")
        self.assertNotEqual(risk.route_for(rs, ["README.md"]).route, "major")


if __name__ == "__main__":
    unittest.main()
