"""`aidd upgrade`'s fold of Initiatives and Epics into Intents, on a repository shaped like a real plan: one Initiative,
eight Epics as its milestones, 24 Specs with `parent` lines, an exploration in the Initiative's folder, a decision record
about it, and a brief at the repository's root. No id, path, or record is lost, and no agreement is ever written."""

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import git

from aidd.kernel import documents
from aidd.setup import work_item_migration
from aidd.workitems import intents, validation

# The plan's shape: each Epic and the Specs it lists, in order.
EPICS = {
    "EPIC-1": [1, 2, 3],
    "EPIC-2": [4, 5, 6, 7, 8],
    "EPIC-3": [9, 10],
    "EPIC-4": [11, 12],
    "EPIC-5": [13, 14, 15],
    "EPIC-6": [16, 17, 18, 19],
    "EPIC-7": [20, 21, 22],
    "EPIC-8": [23, 24],
}
RECORD_ID = "20261107T210119846Z-f818a44d"
BRIEF = "# What I want\n\nA traced agent chat in five minutes.\n"


def spec_text(n: int, parent: str, extra: str = "") -> str:
    return (
        f'---\naidd_version: "1.0.0"\ntype: spec\nparent: {parent}\nid: SPEC-{n}\ntitle: "Slice {n}"\nowner_team: maintainers\n'
        "change_type: feat\nroute: normal\nconfidence: medium\n"
        f'open_questions: ["Which stack for slice {n}?"]\nassisted_by: []\nrollback: Revert the change.\n{extra}'
        'risk:\n  summary: "TODO"\n  dimensions: []\n  reversible: true\n'
        f'tasks:\n  - id: SPEC-{n}-T1\n    title: "TODO: the first slice"\n    scope: ["src/TODO/"]\n'
        'tests:\n  files: ["tests/TODO"]\n  commands:\n    - name: acceptance\n      command: ["TODO"]\n'
        f"---\n\n## Intent\n\nSlice {n}.\n"
    )


def epic_text(eid: str, specs: list[int], extra: str = "") -> str:
    month = 11 + int(eid.split("-")[1]) // 3
    due = f"2026-{month:02d}-20" if month <= 12 else f"2027-{month - 12:02d}-20"
    listed = ", ".join(f"SPEC-{n}" for n in specs)
    return (
        f'---\naidd_version: "1.0.0"\ntype: epic\nid: {eid}\nparent: INIT-1\ntitle: "M{eid[-1]}: milestone {eid[-1]}"\n'
        f'goal: "the {eid} cells are green, by {due}"\nowner_team: maintainers\npriority: high\ncontext: "Terms of {eid}."\n'
        f"reaches: incremental\nspecs: [{listed}]\n{extra}---\n\n## Outcome\n\nWhat {eid} moves.\n\n## Exit criteria\n\n- done.\n"
    )


INITIATIVE = (
    '---\naidd_version: "1.0.0"\ntype: initiative\nid: INIT-1\ntitle: "Ship the kit"\n'
    'goal: "28 of 28 cells pass, by 2027-02-19"\nowner_team: maintainers\npriority: high\n---\n\n'
    "## Brief\n\n- Problem: a kit takes days (assumed).\n\n## Epics\n\n| Epic | Title |\n| --- | --- |\n| EPIC-1 | M1 |\n\n"
    "## Out of scope\n\n- Hosting.\n\n## Learn\n\nLater.\n"
)


@unittest.skipUnless(shutil.which("git"), "git is required")
class FoldTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "T")
        self.write("specs/INIT-1.md", INITIATIVE)
        for eid, specs in EPICS.items():
            self.write(f"specs/{eid}.md", epic_text(eid, specs))
            for n in specs:
                waits = f"relations:\n  - {{type: blocked_by, id: SPEC-{n - 1}}}\n" if n > 1 else ""
                self.write(f"specs/SPEC-{n}.md", spec_text(n, eid, waits))
        self.write("specs/INIT-1/explore/design-direction/exploration.md", "# Which direction?\n")
        self.write("intent.md", BRIEF)
        record = {"id": RECORD_ID, "type": "decision", "at": "2026-11-07T21:01:19Z", "by": "agent:claude-code/claude-opus-5-5", "subject": "INIT-1"}
        record["data"] = {"action": "plan.agree", "answer": {"outcome": "accept", "by": "the person"}}
        self.write(f".git/aidd/records/2026/11/{RECORD_ID}.json", json.dumps(record, indent=2) + "\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "the plan")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def read(self, rel: str) -> dict:
        data, _ = documents.split_front_matter((self.root / rel).read_text(encoding="utf-8"), rel)
        return data

    def fold(self, *, collapse: bool = False) -> work_item_migration.Migration:
        return work_item_migration.plan(self.root, "specs", "proposals", self.root / ".aidd" / "config.yaml", collapse=collapse)

    def apply(self, fold: work_item_migration.Migration) -> None:
        self.assertEqual(fold.stops, [])
        for path, text in fold.writes.items():
            path.write_text(text, encoding="utf-8")
        for path in fold.removes:
            path.unlink()

    def ids_present(self) -> set[str]:
        """Every id the Specs folder still names: a file's id, a phase's, or a slice's."""
        found = set()
        for path in sorted((self.root / "specs").glob("*.md")):
            data = self.read(path.relative_to(self.root).as_posix())
            found.add(str(data.get("id")))
            found |= {str(p.get("id")) for p in intents.phases_of(data) if p.get("id")} | set(intents.slice_ids(data))
        return found - {"None"}

    def test_the_fold_keeps_every_id_path_and_record(self):
        record = (self.root / f".git/aidd/records/2026/11/{RECORD_ID}.json").read_bytes()
        before = {"INIT-1", *EPICS, *(f"SPEC-{n}" for n in range(1, 25))}
        spec_errors = {e for e in validation.check_repo(self.root)[0] if "specs/SPEC-" in e}
        fold = self.fold()
        self.assertFalse(any("agreed_by" in text for text in fold.writes.values()))
        self.apply(fold)
        intent = self.read("specs/INIT-1.md")
        self.assertEqual(intent["type"], "intent")
        self.assertEqual([p["id"] for p in intent["phases"]], list(EPICS))
        self.assertEqual([s["id"] for p in intent["phases"] for s in p["slices"]], [f"SPEC-{n}" for n in range(1, 25)])
        self.assertTrue(all(p.get("due") for p in intent["phases"]))
        self.assertNotIn("agreed_by", intent)
        self.assertEqual(before - self.ids_present(), set())
        self.assertEqual({self.read(f"specs/SPEC-{n}.md")["parent"] for n in range(1, 25)}, {"INIT-1"})
        self.assertFalse(any((self.root / f"specs/{e}.md").exists() for e in EPICS))
        for kept, text in (("specs/INIT-1/explore/design-direction/exploration.md", "# Which direction?\n"), ("intent.md", BRIEF)):
            self.assertEqual((self.root / kept).read_text(encoding="utf-8"), text, kept)
        self.assertEqual((self.root / f".git/aidd/records/2026/11/{RECORD_ID}.json").read_bytes(), record)
        body = (self.root / "specs/INIT-1.md").read_text(encoding="utf-8")
        self.assertEqual(body.count("### EPIC-"), len(EPICS))  # each Epic's goal and text stay, under `## Phases`
        self.assertIn("Terms of EPIC-8.", intent["context"])
        errors, _ = validation.check_repo(self.root)
        self.assertEqual({e for e in errors if "specs/" in e} - spec_errors, set())  # the fold adds no error to any file

    def test_the_agent_asks_once_about_the_recorded_agreement(self):
        notes = self.fold().notes
        self.assertTrue(any(RECORD_ID in n and "INIT-1" in n and "2026-11-07" in n for n in notes), notes)

    def test_collapse_turns_only_unstarted_specs_into_lines(self):
        approved = (self.root / "specs/SPEC-1.md").read_text(encoding="utf-8").replace("rollback:", 'approved_at: "2026-11-08T10:00:00Z"\nrollback:')
        self.write("specs/SPEC-1.md", approved.replace("confidence: medium", "status: approved\nconfidence: medium"))
        self.write("specs/SPEC-3.md", spec_text(3, "EPIC-1", "relations:\n  - {type: relates_to, id: SPEC-1}\n"))
        git(self.root, "commit", "-qam", "SPEC-1 approved")
        git(self.root, "branch", "spec/SPEC-2")
        git(self.root, "checkout", "-q", "spec/SPEC-2")
        self.write("specs/SPEC-2.md", spec_text(2, "EPIC-1", "labels: [started]\n"))
        git(self.root, "commit", "-qam", "SPEC-2 started")
        git(self.root, "checkout", "-q", "main")
        head = git(self.root, "rev-parse", "HEAD")
        plan_commit = git(self.root, "rev-list", "--max-parents=0", "HEAD")
        fold = self.fold(collapse=True)
        self.apply(fold)
        intent = self.read("specs/INIT-1.md")
        lines = {s["id"]: s for p in intent["phases"] for s in p["slices"]}
        kept = {"SPEC-1": "started", "SPEC-2": "branch", "SPEC-3": "relation"}
        for sid in kept:
            with self.subTest(kept=sid):
                self.assertTrue((self.root / f"specs/{sid}.md").is_file())
                self.assertNotIn("drafted_in", lines[sid])
        for n in range(4, 25):
            with self.subTest(collapsed=n):
                self.assertFalse((self.root / f"specs/SPEC-{n}.md").exists())
                self.assertIn(lines[f"SPEC-{n}"]["drafted_in"], (head, plan_commit))
                self.assertEqual(lines[f"SPEC-{n}"]["blocked_by"], [f"SPEC-{n - 1}"])
        self.assertIn("SPEC-24: Which stack for slice 24?", (self.root / "specs/INIT-1.md").read_text(encoding="utf-8"))
        self.assertEqual({"INIT-1", *EPICS, *(f"SPEC-{n}" for n in range(1, 25))} - self.ids_present(), set())

    def test_a_collapsed_draft_returns_whole_when_its_slice_starts(self):
        self.apply(self.fold(collapse=True))
        from aidd import workitems

        workitems.new_object(self.root, workitems.NewObject(item_type="spec", id="SPEC-5", title=""))
        back = self.read("specs/SPEC-5.md")
        self.assertEqual((back["parent"], back["title"]), ("INIT-1", "Slice 5"))
        self.assertEqual(back["relations"], [{"type": "blocked_by", "id": "SPEC-4"}])
        line = next(s for p in self.read("specs/INIT-1.md")["phases"] for s in p["slices"] if s["id"] == "SPEC-5")
        self.assertNotIn("blocked_by", line)  # one owner: the Spec
        self.assertNotIn("drafted_in", line)  # spent: the Spec file holds the draft again

    def test_what_has_no_home_in_an_intent_stops_the_fold(self):
        cases = {
            "reaches differ": {"specs/EPIC-2.md": epic_text("EPIC-2", EPICS["EPIC-2"]).replace("reaches: incremental", "reaches: flagged")},
            "an Epic's own relation": {"specs/EPIC-3.md": epic_text("EPIC-3", EPICS["EPIC-3"], "relations: [{type: blocked_by, id: EPIC-2}]\n")},
            "a relation names an Epic": {"specs/SPEC-9.md": spec_text(9, "EPIC-3", "relations:\n  - {type: relates_to, id: EPIC-1}\n")},
            "an unknown parent": {"specs/EPIC-4.md": epic_text("EPIC-4", EPICS["EPIC-4"]).replace("parent: INIT-1", "parent: INIT-9")},
            "two launches": {f"specs/{e}.md": epic_text(e, EPICS[e], f"launch: SPEC-{EPICS[e][-1]}\n") for e in ("EPIC-5", "EPIC-6")},
            "milestones beside Epics": {
                "specs/INIT-1.md": INITIATIVE.replace(
                    "priority: high\n", "priority: high\nmilestones: [{id: M1, name: one, due: '2027-01-01', trigger: {event: signed}}]\n", 1
                )
            },
            "a file that does not parse": {"specs/SPEC-7.md": "---\ntype: spec\nid: [\n---\n"},
        }
        for name, files in cases.items():
            with self.subTest(name):
                original = {rel: (self.root / rel).read_text(encoding="utf-8") for rel in files}
                for rel, text in files.items():
                    self.write(rel, text)
                fold = self.fold()
                self.assertTrue(fold.stops)
                self.assertEqual((fold.writes, fold.removes), ({}, []))
                for rel, text in original.items():
                    self.write(rel, text)

    def test_proposals_and_delivery_teams_follow_the_fold(self):
        self.write(".aidd/config.yaml", "delivery_teams:\n  core:\n    people: ['@a']\n    epics: [EPIC-1, EPIC-2, EPIC-3, EPIC-4, EPIC-5, EPIC-6, EPIC-7, EPIC-8]\n"
                   "  web:\n    people: ['@b']\n    areas: [ci]\n    epics:\n      - EPIC-7\n")  # fmt: skip
        need = "needs:\n  - {id: N1, text: fast, answer: met, epic: EPIC-1}\n"
        self.write("proposals/PROP-1/proposal.md", f'---\naidd_version: "1.0.0"\ntype: proposal\nid: PROP-1\n{need}---\n')
        fold = self.fold()
        teams = documents.parse_yaml(fold.writes[self.root / ".aidd/config.yaml"], "config")["delivery_teams"]
        self.assertEqual(teams["core"].get("intents"), ["INIT-1"])
        self.assertNotIn("epics", teams["web"])
        self.assertEqual(teams["web"]["areas"], ["ci"])
        phases = documents.split_front_matter(fold.writes[self.root / "specs/INIT-1.md"], "INIT-1")[0]["phases"]
        self.assertEqual({s.get("owner_team") for s in phases[6]["slices"]}, {"web"})
        proposal = documents.split_front_matter(fold.writes[self.root / "proposals/PROP-1/proposal.md"], "PROP-1")[0]
        self.assertEqual(proposal["needs"][0].get("phase"), "EPIC-1")
        self.assertNotIn("epic", proposal["needs"][0])

    def test_a_proposal_names_phases_and_its_sign_off_still_matches(self):
        from aidd.workitems import spec_file

        phase = 'milestones:\n  - id: M-1\n    name: live\n    due: "2026-12-01"\n    trigger: {event: go-live}\n    reached_on: "2026-12-02"\n'
        text = f'---\naidd_version: "1.0.0"\ntype: proposal\nid: PROP-1\n{phase}needs:\n  - {{id: N1, epic: EPIC-1}}\n---\n\nThe deal.\n'
        self.write("proposals/PROP-1/proposal.md", text)
        folded = self.fold().writes[self.root / "proposals/PROP-1/proposal.md"]
        data = documents.split_front_matter(folded, "PROP-1")[0]
        self.assertEqual((data["phases"][0]["finished_on"], data["needs"][0]["phase"]), ("2026-12-02", "EPIC-1"))
        self.assertNotIn("milestones", data)
        self.assertEqual(spec_file.proposal_hash(folded), spec_file.proposal_hash(text))

    def test_a_team_left_with_nothing_stops_the_fold(self):
        self.write(".aidd/config.yaml", "delivery_teams:\n  web:\n    people: ['@b']\n    epics: [EPIC-7]\n")
        self.assertTrue(self.fold().stops)

    def test_an_epic_with_no_parent_becomes_an_intent(self):
        self.write("specs/EPIC-9.md", epic_text("EPIC-9", []).replace("parent: INIT-1\n", "").replace("specs: []", "specs: [SPEC-30]"))
        fold = self.fold()
        self.apply(fold)
        alone = self.read("specs/EPIC-9.md")
        self.assertEqual((alone["type"], intents.slice_ids(alone)), ("intent", ["SPEC-30"]))

    def test_the_note_cites_only_a_record_that_accepted_an_agreement(self):
        path = self.root / f".git/aidd/records/2026/11/{RECORD_ID}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        cases = [
            ("an accepted agreement", "plan.agree", "accept", True),
            ("a declined agreement", "plan.agree", "decline", False),
            ("an accepted approval of something else", "spec.approve", "accept", False),
        ]
        for name, action, outcome, cites in cases:
            with self.subTest(name):
                record["data"] = {"action": action, "answer": {"outcome": outcome, "by": "the person"}}
                path.write_text(json.dumps(record), encoding="utf-8")
                notes = [n for n in self.fold().notes if "INIT-1" in n and "records no agreement" in n]
                self.assertEqual(len(notes), 1, notes)
                self.assertEqual(RECORD_ID in notes[0], cites)
                self.assertIn("Agreed-by", notes[0])

    def commit_plan(self, message: str = "the plan changes") -> None:
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", message)

    def test_a_draft_that_no_slice_line_replaces_stays_a_file(self):
        self.write("specs/SPEC-30.md", spec_text(30, "INIT-1"))  # a child of the Initiative itself: no phase lists it
        self.commit_plan()
        fold = self.fold(collapse=True)
        self.assertEqual(fold.stops, [])
        self.assertNotIn(self.root / "specs/SPEC-30.md", fold.removes)
        self.assertTrue(any("SPEC-30.md" in n and "INIT-1" in n for n in fold.notes), fold.notes)
        self.apply(fold)
        self.assertEqual(self.read("specs/SPEC-30.md")["parent"], "INIT-1")

    def test_a_draft_whose_epic_ranks_it_differently_stays_a_file(self):
        self.write("specs/EPIC-4.md", epic_text("EPIC-4", EPICS["EPIC-4"]).replace("priority: high", "priority: low"))
        self.commit_plan()
        fold = self.fold(collapse=True)
        for n in EPICS["EPIC-4"]:
            with self.subTest(n=n):
                path = self.root / f"specs/SPEC-{n}.md"
                self.assertNotIn(path, fold.removes)
                self.assertEqual(documents.split_front_matter(fold.writes[path], "x")[0]["priority"], "low")
        self.assertIn(self.root / "specs/SPEC-13.md", fold.removes)  # an Epic that ranks as its Initiative does still collapses

    def approve(self, n: int, parent: str, extra: str) -> None:
        """Spec `n` as a started Spec: approved, so the fold keeps its file."""
        text = spec_text(n, parent, extra).replace("rollback:", 'approved_at: "2026-11-08T10:00:00Z"\nrollback:')
        self.write(f"specs/SPEC-{n}.md", text.replace("confidence: medium", "status: approved\nconfidence: medium"))

    def test_a_draft_whose_interface_another_spec_consumes_stays_a_file(self):
        self.write("specs/SPEC-20.md", spec_text(20, "EPIC-7", "provides: [x]\n"))
        self.write("specs/SPEC-21.md", spec_text(21, "EPIC-7", "consumes: [x]\n"))  # a draft too: it collapses, and still counts as a reader
        self.approve(22, "EPIC-7", "consumes: [x]\n")
        self.commit_plan()
        fold = self.fold(collapse=True)
        self.assertNotIn(self.root / "specs/SPEC-20.md", fold.removes)
        self.assertIn(self.root / "specs/SPEC-21.md", fold.removes)
        self.assertTrue(any("SPEC-20.md" in n and "provides" in n and "x" in n and "SPEC-21" in n for n in fold.notes), fold.notes)
        self.apply(fold)
        self.assertEqual(self.read("specs/SPEC-20.md")["provides"], ["x"])
        warnings = [e for e in validation.check_repo(self.root)[1] if "no Spec provides it" in e]
        self.assertEqual(warnings, [])

    def test_a_draft_whose_interface_nobody_consumes_still_collapses(self):
        self.write("specs/SPEC-20.md", spec_text(20, "EPIC-7", "provides: [x]\n"))
        self.write("specs/SPEC-21.md", spec_text(21, "EPIC-7", "consumes: [z]\n"))
        self.commit_plan()
        fold = self.fold(collapse=True)
        self.assertIn(self.root / "specs/SPEC-20.md", fold.removes)
        self.assertFalse(any("SPEC-20.md" in n for n in fold.notes), fold.notes)

    def test_a_cancelled_epic_with_unfinished_specs_stops_the_fold(self):
        self.write("specs/EPIC-3.md", epic_text("EPIC-3", EPICS["EPIC-3"], "status: cancelled\n"))
        stops = self.fold().stops
        self.assertTrue(any("EPIC-3" in s and "SPEC-9" in s and "SPEC-10" in s and "cancel" in s for s in stops), stops)
        for n in EPICS["EPIC-3"]:
            self.write(f"specs/SPEC-{n}.md", spec_text(n, "EPIC-3", "status: cancelled\n"))
        self.assertEqual(self.fold().stops, [], "every Spec of the cancelled Epic ended, so the fold loses no live slice")

    def test_a_cancelled_epic_that_lists_a_spec_with_no_file_says_to_remove_it_from_the_list(self):
        """A Spec with no file cannot be cancelled, so the stop names the one step that works: take it off the Epic's `specs`."""
        for n in EPICS["EPIC-3"]:
            self.write(f"specs/SPEC-{n}.md", spec_text(n, "EPIC-3", "status: cancelled\n"))
        self.write("specs/EPIC-3.md", epic_text("EPIC-3", [*EPICS["EPIC-3"], 99], "status: cancelled\n"))
        stops = self.fold().stops
        found = [s for s in stops if "EPIC-3" in s and "SPEC-99" in s]
        self.assertEqual(len(found), 1, stops)
        self.assertIn("remove it from the Epic's `specs`", found[0])
        self.assertNotIn("status: cancelled", found[0], "that step cannot work for a Spec with no file")

    def test_a_proposal_is_only_renamed_never_rewritten(self):
        from aidd.workitems import spec_file

        quoted = 'needs:\n  - {id: N1, text: "ship it, epic: later", epic: EPIC-1}\n'
        text = f'---\naidd_version: "1.0.0"\ntype: proposal\nid: PROP-1\n{quoted}---\n\nThe deal.\n'
        self.write("proposals/PROP-1/proposal.md", text)
        fold = self.fold()
        self.assertTrue(any("PROP-1" in s for s in fold.stops), fold.stops)
        self.assertEqual(fold.writes, {})
        # The sign-off check stands apart from the rename: a write that changes what was signed stops the fold.
        changed = work_item_migration.Migration(writes={self.root / "proposals/PROP-1/proposal.md": text.replace("The deal.", "A new deal.")})
        work_item_migration._checked(changed, self.root)
        self.assertTrue(any("sign" in s for s in changed.stops), changed.stops)
        self.assertEqual(spec_file.proposal_hash(text), spec_file.proposal_hash(text.replace("epic: EPIC-1", "phase: EPIC-1")))

    def test_collapsed_questions_come_in_number_order_in_one_place(self):
        self.write("specs/INIT-1.md", INITIATIVE.replace("## Out of scope", "## Open questions\n\nnone\n\n## Out of scope"))
        self.commit_plan()
        self.apply(self.fold(collapse=True))
        body = (self.root / "specs/INIT-1.md").read_text(encoding="utf-8")
        asked = [int(n) for n in re.findall(r"^- SPEC-(\d+): Which stack", body, re.M)]
        self.assertEqual(asked, sorted(asked))
        self.assertTrue(asked)
        self.assertNotRegex(body, r"(?m)^none$")

    def test_the_old_templates_guidance_and_epic_table_leave_the_folded_intent(self):
        guide = "<!-- An Initiative holds Epics. Write the prose at the ste-80 level. -->\n"
        table = "| Epic | Title | Owner team | Order | Why this order |\n| --- | --- | --- | --- | --- |\n| EPIC- | | | 1 | |\n"
        kept = "| Epic | Title | Owner team | Order | Why this order |\n| --- | --- | --- | --- | --- |\n| EPIC-1 | M1 | core | 1 | Money comes first. |\n"
        cases = [("the template's rows", table, False), ("a row a person wrote", kept, True)]
        for name, rows, survives in cases:
            with self.subTest(name):
                self.write(
                    "specs/INIT-1.md", INITIATIVE.replace("## Epics\n\n| Epic | Title |\n| --- | --- |\n| EPIC-1 | M1 |\n", f"{guide}\n## Epics\n\n{rows}")
                )
                text = self.fold().writes[self.root / "specs/INIT-1.md"]
                self.assertNotIn("<!--", text)
                self.assertEqual("| Epic |" in text, survives)
                self.assertEqual("Money comes first." in text, survives)

    def test_a_slice_whose_draft_commit_is_missing_stops_and_names_the_next_step(self):
        from aidd import workitems

        intent = INITIATIVE.replace("---\n\n## Brief", f"slices:\n  - {{id: SPEC-31, title: Nine, drafted_in: {'a' * 40}}}\n---\n\n## Brief", 1).replace(
            "type: initiative", "type: intent"
        )
        self.write("specs/INIT-1.md", intent)
        with self.assertRaisesRegex(ValueError, "git fetch --unshallow"):
            workitems.new_object(self.root, workitems.NewObject(item_type="spec", id="SPEC-31", title=""))
        self.assertFalse((self.root / "specs/SPEC-31.md").exists())

    def test_a_repository_with_nothing_to_fold_is_left_alone(self):
        self.apply(self.fold())
        again = self.fold()
        self.assertEqual((again.writes, again.removes, again.stops), ({}, [], []))


@unittest.skipUnless(shutil.which("git"), "git is required")
class UpgradeFoldTests(unittest.TestCase):
    """The fold through `aidd upgrade`: a dry run writes nothing, and `--yes` waits for a clean Specs folder."""

    def test_upgrade_folds_on_a_clean_tree_only(self):
        from aidd.setup import adoption, upgrading

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
            git(root, "config", "user.email", "t@example.com")
            git(root, "config", "user.name", "T")
            adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["claude-code"], ref="v1.0.0"))
            (root / "specs").mkdir(exist_ok=True)
            (root / "specs/INIT-1.md").write_text(INITIATIVE, encoding="utf-8")
            (root / "specs/EPIC-1.md").write_text(epic_text("EPIC-1", [1]), encoding="utf-8")
            (root / "specs/SPEC-1.md").write_text(spec_text(1, "EPIC-1"), encoding="utf-8")
            (root / "intent.md").write_text(BRIEF, encoding="utf-8")
            git(root, "add", "-A")
            git(root, "commit", "-qm", "setup and plan")
            upgrading.upgrade(root)
            self.assertEqual(json.loads(json.dumps(documents.split_front_matter((root / "specs/INIT-1.md").read_text(), "x")[0]))["type"], "initiative")
            (root / "specs/SPEC-1.md").write_text(spec_text(1, "EPIC-1") + "\nmore\n", encoding="utf-8")
            actions = upgrading.upgrade(root, yes=True)
            self.assertTrue(any("commit" in a and "specs/SPEC-1.md" in a for a in actions), actions)
            self.assertTrue((root / "specs/EPIC-1.md").is_file())
            git(root, "commit", "-qam", "the open work")
            upgrading.upgrade(root, yes=True)
            self.assertFalse((root / "specs/EPIC-1.md").exists())
            self.assertEqual(documents.split_front_matter((root / "specs/INIT-1.md").read_text(), "x")[0]["type"], "intent")
            self.assertEqual((root / "intent.md").read_text(encoding="utf-8"), BRIEF)

    def test_a_dry_run_reads_the_config_as_the_fold_leaves_it(self):
        from aidd.setup import adoption, upgrading

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
            git(root, "config", "user.email", "t@example.com")
            git(root, "config", "user.name", "T")
            adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["claude-code"], ref="v1.0.0"))
            cfg = root / ".aidd" / "config.yaml"
            cfg.write_text(cfg.read_text(encoding="utf-8") + "delivery_teams:\n  core:\n    people: ['@a']\n    epics: [EPIC-1]\n", encoding="utf-8")
            (root / "specs").mkdir(exist_ok=True)
            (root / "specs/INIT-1.md").write_text(INITIATIVE, encoding="utf-8")
            (root / "specs/EPIC-1.md").write_text(epic_text("EPIC-1", [1]), encoding="utf-8")
            (root / "specs/SPEC-1.md").write_text(spec_text(1, "EPIC-1"), encoding="utf-8")
            git(root, "add", "-A")
            git(root, "commit", "-qm", "setup and plan")
            shown = "\n".join(upgrading.upgrade(root))
            self.assertIn("delivery teams name Intents", shown)  # the fold would rewrite the config
            for stale in ("skipped  the ask rules", "remove line", "`delivery_teams.core.epics`"):
                self.assertNotIn(stale, shown)  # what the fold removes is not asked of the person again
            self.assertIn("epics: [EPIC-1]", cfg.read_text(encoding="utf-8"), "a dry run writes nothing")


if __name__ == "__main__":
    unittest.main()
