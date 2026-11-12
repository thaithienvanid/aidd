"""An Intent holds only what something reads: `aidd_version`, `labels`, `context`, and `launch` are cut, `relations` is `blocked_by`, and
`slices` is one phase of `phases` (schemas/retired-names.json, surface `intent`).

The invariant: `aidd upgrade --yes` keeps every value an Intent held and every line it did not name. A value with no place now
stays whole, with a line that says what to do by hand, and a second run finds nothing. The table of shapes is the input space:
each form a person may have written, and the boundary rows (empty, one, many, a neighbour that blocks the move)."""

import shutil
import unittest

from migration_fixture import CONFIG, FIXTURES, Repo

from aidd import workitems
from aidd.kernel import documents, retired_names
from aidd.setup import migrating
from aidd.workitems import spec_file

HEAD = "---\ntype: intent\nid: INT-1\ntitle: Cheaper checkout\ngoal: Shoppers pay less.\n"
SLICES = [{"id": "S1", "title": "One"}, {"id": "S2", "title": "Two"}]
# The old `slices` list as a person may have written it: the text, and whether a comment in it must stay.
SLICE_FORMS = {
    "a block list": ("slices:\n  - id: S1\n    title: One\n  - id: S2\n    title: Two\n", ""),
    "a flow list on one line": ("slices: [{id: S1, title: One}, {id: S2, title: Two}]\n", ""),
    "a list at the key's own column": ("slices:\n- id: S1\n  title: One\n- id: S2\n  title: Two\n", ""),
    "comments on the key and between items": (
        "slices:   # all of them\n  - id: S1\n    title: One\n  # the second\n  - id: S2\n    title: Two\n",
        "# the second",
    ),
}


def front(text: str) -> dict:
    return documents.split_front_matter(text, "x.md")[0]


class TheIntentsCutsAndFolds(Repo):
    shape = "today"

    def run_on(self, files: dict[str, str]) -> migrating.Plan:
        shutil.rmtree(self.root / "specs")
        shutil.rmtree(self.root / "docs" / "standards", ignore_errors=True)
        for rel, text in files.items():
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_bytes(text.encode("utf-8"))
        (self.root / CONFIG).write_bytes((FIXTURES / "today" / CONFIG).read_bytes())
        return migrating.plan(self.root)

    def manual(self, found: migrating.Plan) -> list[str]:
        return [line for kind, line in found.lines if kind == "manual"]

    def test_slices_become_the_one_phase_of_phases_in_every_form_a_person_writes(self):
        for name, (slices, kept) in SLICE_FORMS.items():
            with self.subTest(name):
                found = self.run_on({"specs/INT-1.md": HEAD + slices + "---\n\nBody.\n"})
                new = found.texts["specs/INT-1.md"]
                data = front(new)
                self.assertEqual(data["phases"], [{"id": "P1", "name": "Cheaper checkout", "slices": SLICES}])
                self.assertNotIn("slices", data)
                self.assertEqual((data["type"], data["id"], data["goal"]), ("intent", "INT-1", "Shoppers pay less."))
                self.assertIn(kept, new)
                self.assertEqual(spec_file.load_object(new, "specs/INT-1.md")[2][:1], [], "the result is a valid Intent")
                self.assertEqual(self.manual(found), [])
                (self.root / "specs/INT-1.md").write_text(new, encoding="utf-8")
                again = migrating.plan(self.root)
                self.assertEqual((again.lines, again.texts), ([], {}), "a second run finds nothing")

    def test_an_empty_slices_list_becomes_an_empty_phase_and_a_phases_list_beside_it_stays(self):
        found = self.run_on({"specs/INT-1.md": HEAD + "slices: []\n---\n"})
        self.assertEqual(front(found.texts["specs/INT-1.md"])["phases"], [{"id": "P1", "name": "Cheaper checkout", "slices": []}])
        both = HEAD + "phases:\n  - {id: P1, name: p, slices: [{id: S1, title: One}]}\nslices: [{id: S2, title: Two}]\n---\n"
        found = self.run_on({"specs/INT-1.md": both})
        self.assertEqual(found.texts, {}, "nothing is half moved")
        [line] = self.manual(found)
        for part in ("specs/INT-1.md", "slices", "`phases` is set too", "`aidd upgrade` again"):
            self.assertIn(part, line)

    def test_a_phase_is_named_for_the_title_cut_to_a_name_and_a_blank_title_gets_a_number(self):
        for title, want in (("T" * 130, "T" * 120), ("  spaced  ", "spaced"), ("", "Phase 1"), (None, "Phase 1"), (7, "Phase 1")):
            with self.subTest(title=title):
                self.assertEqual(workitems.one_phase(title, [])["name"], want)

    def test_the_last_slice_is_read_from_either_shape(self):
        cases = (
            ({"slices": SLICES}, "S2"),
            ({"phases": [{"slices": SLICES[:1]}, {"slices": SLICES}]}, "S2"),
            ({"phases": [{"slices": SLICES}, {"slices": []}]}, None),
            ({"phases": []}, None),
            ({"slices": []}, None),
            ({"phases": ["x"]}, None),
            ({}, None),
        )
        for data, want in cases:
            with self.subTest(data=data):
                self.assertEqual(workitems.last_slice(data), want)

    def test_a_launch_that_is_the_last_slice_is_dropped_and_any_other_stays(self):
        phases = (
            "phases:\n  - {id: P1, name: a, slices: [{id: S1, title: One}]}\n  - {id: P2, name: b, slices: [{id: S2, title: Two}, {id: S3, title: Three}]}\n"
        )
        cases = {
            "the last slice of slices": ("slices: [{id: S1, title: One}, {id: S2, title: Two}]\nlaunch: S2\n", True),
            "the last slice of the last phase": (phases + "launch: S3\n", True),
            "a slice in the middle": ("slices: [{id: S1, title: One}, {id: S2, title: Two}]\nlaunch: S1\n", False),
            "the last slice of an earlier phase": (phases + "launch: S1\n", False),
            "an id no slice has": (phases + "launch: S9\n", False),
        }
        for name, (extra, dropped) in cases.items():
            with self.subTest(name):
                found = self.run_on({"specs/INT-1.md": HEAD + extra + "---\n"})
                if dropped:
                    self.assertNotIn("launch", front(found.texts["specs/INT-1.md"]))
                    self.assertEqual(self.manual(found), [])
                else:
                    [line] = self.manual(found)
                    self.assertIn("launch slice last", line)
                    self.assertTrue(not found.texts or "launch" in front(found.texts["specs/INT-1.md"]), "the value stays")

    def test_an_empty_context_is_dropped_and_one_with_text_stays_for_the_glossary(self):
        for value, dropped in (('""', True), ("''", True), ('"   "', True), ("The terms of this product.", False), ("[a, b]", False), ("0", False)):
            with self.subTest(value=value):
                found = self.run_on({"specs/INT-1.md": HEAD + f"context: {value}\n---\n"})
                if dropped:
                    self.assertNotIn("context", front(found.texts["specs/INT-1.md"]))
                else:
                    self.assertEqual(found.texts, {})
                    [line] = self.manual(found)
                    self.assertIn("docs/GLOSSARY.md", line)

    def test_a_relations_list_moves_by_entry_and_an_entry_with_no_place_leaves_the_whole_list(self):
        files = {
            "specs/INT-2.md": HEAD.replace("INT-1", "INT-2") + "---\n",
            "specs/SPEC-9.md": "---\ntype: spec\nid: SPEC-9\ntitle: T\n---\n",
        }
        cases = {
            "blocked_by only": ("[{type: blocked_by, id: SPEC-9}]", ["SPEC-9"], {}),
            "blocked_by twice": ("[{type: blocked_by, id: SPEC-9}, {type: blocked_by, id: SPEC-9}]", ["SPEC-9"], {}),
            "blocks an Intent": ("[{type: blocks, id: INT-2}]", None, {"specs/INT-2.md": ["INT-1"]}),
            "blocks a Spec": ("[{type: blocks, id: SPEC-9}]", None, {"specs/SPEC-9.md": ["INT-1"]}),
            "both ways": ("[{type: blocked_by, id: SPEC-9}, {type: blocks, id: INT-2}]", ["SPEC-9"], {"specs/INT-2.md": ["INT-1"]}),
            "empty": ("[]", None, {}),
        }
        for name, (relations, own, others) in cases.items():
            with self.subTest(name):
                found = self.run_on({**files, "specs/INT-1.md": HEAD + f"relations: {relations}\n---\n"})
                data = front(found.texts["specs/INT-1.md"])
                self.assertEqual((data.get("blocked_by"), "relations" in data), (own, False))
                for rel, waiting in others.items():
                    self.assertEqual(front(found.texts[rel])["blocked_by"], waiting)
                self.assertEqual(self.manual(found), [])
        stays = {
            "implements has no parent to go to": "[{type: implements, id: SPEC-9}]",
            "duplicates": "[{type: duplicates, id: INT-2}]",
            "relates_to": "[{type: relates_to, id: INT-2}]",
            "a blocks whose target is no item here": "[{type: blocks, id: INT-77}]",
            "an entry among entries that move": "[{type: blocked_by, id: SPEC-9}, {type: relates_to, id: INT-2}]",
        }
        for name, relations in stays.items():
            with self.subTest(name):
                found = self.run_on({**files, "specs/INT-1.md": HEAD + f"relations: {relations}\n---\n"})
                self.assertEqual(found.texts, {}, "nothing is half moved")
                [line] = self.manual(found)
                for part in ("specs/INT-1.md", "relations", "`aidd upgrade` again"):
                    self.assertIn(part, line)

    def test_aidd_version_and_labels_are_cut_with_their_values_shown_and_a_neighbour_keeps_its_line(self):
        found = self.run_on(
            {"specs/INT-1.md": '---\naidd_version: "1.0.0"\ntype: intent\nid: INT-1\ntitle: T   # kept\ngoal: G\nlabels: [a, b]\n---\n\nBody.\n'}
        )
        new = found.texts["specs/INT-1.md"]
        self.assertEqual(new, "---\ntype: intent\nid: INT-1\ntitle: T   # kept\ngoal: G\n---\n\nBody.\n")
        shown = "\n".join(line for _, line in found.lines)
        self.assertIn('cut aidd_version = "1.0.0"', shown)
        self.assertIn("cut labels = [a, b]", shown)

    def test_an_intent_in_todays_shape_is_left_as_it_is(self):
        text = HEAD + "blocked_by: [S9]\nphases:\n  - {id: P1, name: p, slices: [{id: S1, title: One}]}\n---\n"
        found = self.run_on({"specs/INT-1.md": text})
        self.assertEqual((found.lines, found.texts), ([], {}))


class TheOldShapeReadAsTodays(unittest.TestCase):
    """`workitems.todays_shape` reads an Intent in an earlier shape as today's, in memory: what a commit before an upgrade holds."""

    OLD = {
        "type": "intent",
        "id": "INT-1",
        "title": "Cheaper checkout",
        "goal": "g",
        "aidd_version": "1.0.0",
        "labels": ["a"],
        "context": "",
        "launch": "S2",
        "relations": [{"type": "blocked_by", "id": "INT-9"}, {"type": "blocks", "id": "INT-3"}],
        "owner_team": "core",
        "slices": [{"id": "S1", "title": "One", "owner_team": "core"}, {"id": "S2", "title": "Two"}],
    }
    NEW = {
        "type": "intent",
        "id": "INT-1",
        "title": "Cheaper checkout",
        "goal": "g",
        "blocked_by": ["INT-9"],
        "delivery_team": "core",
        "phases": [{"id": "P1", "name": "Cheaper checkout", "slices": [{"id": "S1", "title": "One", "delivery_team": "core"}, {"id": "S2", "title": "Two"}]}],
    }

    def test_every_retired_name_moves_and_today_is_read_as_it_is(self):
        self.assertEqual(workitems.todays_shape(self.OLD), self.NEW)
        self.assertEqual(workitems.todays_shape(self.NEW), self.NEW)
        self.assertEqual(workitems.todays_shape(workitems.todays_shape(self.OLD)), self.NEW, "reading twice is reading once")

    def test_what_the_upgrade_leaves_for_a_person_is_refused(self):
        """Each of these stays in the file with a `manual` line, so a reader of a commit before the upgrade cannot read it either."""
        cases = {
            "slices beside phases": {**self.NEW, "slices": [{"id": "S7", "title": "x"}]},
            "a context that holds text": {**self.OLD, "context": "terms"},
            "a launch that is not the last slice": {**self.OLD, "launch": "S1"},
            "a relation with no place": {**self.OLD, "relations": [{"type": "duplicates", "id": "INT-4"}]},
            "an implements, which an Intent has no place for": {**self.OLD, "relations": [{"type": "implements", "id": "INT-4"}]},
        }
        for name, held in cases.items():
            with self.subTest(name), self.assertRaises(retired_names.Refused):
                workitems.todays_shape(held)


if __name__ == "__main__":
    unittest.main()
