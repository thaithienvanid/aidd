"""A Spec says one polarity: `risk.irreversible`, as `aidd risk --irreversible` and the risk rules do. A flip read with the wrong
meaning inverts a control silently, so each reading is held to the one before it (tests/fixtures/start-answers/required-docs.json,
the answers of the commit that still said `reversible`): today's shape with the opposite value, and the old shape read in memory
or moved by `aidd upgrade`, ask for the same documents. A head that still says `reversible` fails to load, and names the way out."""

import json
import tempfile
import unittest
from pathlib import Path

import control_tables

from aidd import risk, workitems
from aidd.kernel import documents, retired_names
from aidd.setup import migrating
from aidd.workitems import spec_file

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
                self.assertEqual(workitems.todays_shape(data), todays(data), "the old shape, read as today's, is the shape written by hand")
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


SPEC = "---\ntype: spec\nid: SPEC-1\ntitle: T\nroute: normal\nchange_type: feat\nrisk:\n  summary: s\n  dimensions: []\n{line}rollback: r\n---\n\nBody\n"


class TheOldName(unittest.TestCase):
    def test_a_head_that_says_reversible_fails_and_names_the_way_out(self):
        for value in ("true", "false"):
            with self.subTest(value):
                _, _, errors = spec_file.load_object(SPEC.format(line=f"  reversible: {value}\n"), "specs/SPEC-1.md")
                said = " ".join(errors)
                for words in ("risk.reversible", "irreversible", "aidd upgrade --yes"):
                    self.assertIn(words, said)

    def test_the_old_name_read_in_memory_never_keeps_its_value_under_the_new_name(self):
        cases = {
            "true": ({"reversible": True}, {"irreversible": False}),
            "false": ({"reversible": False}, {"irreversible": True}),
            "absent": ({}, {}),
        }
        for name, (old, new) in cases.items():
            with self.subTest(name):
                data = {"type": "spec", "risk": {"summary": "s", **old}}
                self.assertEqual(workitems.todays_shape(data)["risk"], {"summary": "s", **new})
        # The upgrade leaves these for a person, so the reading refuses them too, and no check reads a guess at either value.
        for name, old in {"both": {"reversible": True, "irreversible": True}, "no boolean": {"reversible": "yes"}}.items():
            with self.subTest(name), self.assertRaises(retired_names.Refused):
                workitems.todays_shape({"type": "spec", "risk": {"summary": "s", **old}})

    def test_one_function_gives_the_value_for_the_reading_and_for_the_upgrade(self):
        self.assertEqual([workitems.irreversible_of(v) for v in (True, False, None, "false", 0)], [False, True, None, None, None])


class TheUpgrade(unittest.TestCase):
    def plan(self, files: dict[str, str]) -> tuple[migrating.Plan, Path]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / ".aidd").mkdir()
        (root / ".aidd" / "config.yaml").write_text('aidd_version: "1.0.0"\nprofile: solo\n', encoding="utf-8")
        for rel, text in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding="utf-8")
        return migrating.plan(root), root

    def test_true_false_and_absent_become_the_opposite_and_a_second_run_changes_nothing(self):
        cases = {
            "true": ("  reversible: true\n", False),
            "false": ("  reversible: false\n", True),
            "the template's comment": ("  reversible: true                # false when a revert cannot restore the prior state (forces major)\n", False),
        }
        for name, (line, expected) in cases.items():
            with self.subTest(name):
                found, root = self.plan({"specs/SPEC-1.md": SPEC.format(line=line)})
                text = found.texts["specs/SPEC-1.md"]
                self.assertEqual(documents.split_front_matter(text, "x")[0]["risk"]["irreversible"], expected)
                self.assertNotIn("false when", text, "a comment never says the old polarity beside the new name")
                (root / "specs/SPEC-1.md").write_text(text, encoding="utf-8")
                again = migrating.plan(root)
                self.assertEqual((again.lines, again.texts), ([], {}))
        found, _ = self.plan({"specs/SPEC-1.md": SPEC.format(line="")})
        self.assertEqual((found.lines, found.texts), ([], {}), "a Spec that left it out is reversible under either name")

    def test_a_value_it_cannot_flip_stays_and_a_comment_of_a_persons_is_named(self):
        found, _ = self.plan({"specs/SPEC-1.md": SPEC.format(line="  reversible: maybe\n")})
        self.assertEqual(found.texts, {})
        self.assertEqual([k for k, _ in found.lines], ["manual"])
        found, _ = self.plan({"specs/SPEC-1.md": SPEC.format(line="  reversible: false   # the dump cannot come back\n")})
        self.assertIn("# the dump cannot come back", found.texts["specs/SPEC-1.md"])
        self.assertEqual(sorted(k for k, _ in found.lines), ["migrate", "note"])

    def test_an_agent_role_moves_and_any_other_identity_says_nothing(self):
        spec = SPEC.format(line="  irreversible: false\n").replace(
            "rollback: r\n", "rollback: r\nsuggested_by: {who}\ntasks:\n  - id: T1\n    assignee: {who}\n"
        )
        found, _ = self.plan({"specs/SPEC-1.md": spec.replace("{who}", "agent:developer")})
        data = documents.split_front_matter(found.texts["specs/SPEC-1.md"], "x")[0]
        self.assertEqual((data["suggested_by"], data["tasks"][0]["assignee"]), ("role:developer", "role:developer"))
        for who in ("agent:claude-code/claude-opus-5-5", '"@alice"', "role:developer"):
            with self.subTest(who):
                found, _ = self.plan({"specs/SPEC-1.md": spec.replace("{who}", who)})
                self.assertEqual((found.lines, found.texts), ([], {}))


if __name__ == "__main__":
    unittest.main()
