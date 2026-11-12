"""One hostile Spec never breaks `aidd status`.

A Spec file is another person's text. A field of the wrong type, such as `retry_count: "many"` or `approvers: 5`, must not
crash `aidd status` in text, as JSON, or as the work-items page, and must not take the other items with it: the Spec is set
aside as unreadable, whole, for `aidd validate` to name. What the answer does say about a hostile Spec must match its schema.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import helpers
import page_dom

from aidd.kernel import json_schema

GOOD = '---\ntype: spec\nid: SPEC-2\ntitle: A fine Spec\nstatus: ready\ntasks:\n  - id: T1\n    title: t\n    scope: ["a/**"]\n---\n'
TASK = "tasks:\n  - id: T1\n    title: t\n    scope: [a/**]\n{task}"
EMERGENCY = "route: emergency\nemergency:\n  severity: sev1\n  type: outage\n  commander: Lan\n  incident: INC-1\n  backfill_due: {due}\n"


def spec(status: str = "ready", extra: str = "", tasks: str | None = None) -> str:
    body = tasks if tasks is not None else TASK.format(task="")
    return f"---\ntype: spec\nid: SPEC-1\ntitle: Hostile\nstatus: {status}\n{extra}{body}---\n"


CASES = (
    # (what, the Spec's text, whether the answer must set it aside as unreadable)
    ("a retry count that is no number", spec("in_progress", tasks=TASK.format(task='    retry_count: "many"\n')), True),
    ("suggested_by as a list", spec("draft", "suggested_by: [agent, x]\n"), True),
    ("approvers as a number", spec("ready", "approvers: 5\n"), True),
    ("outcome as a string", spec("done", 'hypothesis: "x by 2026-01-01"\noutcome: "x"\n'), True),
    ("triage as a list", spec("draft", "suggested_by: agent:x\ntriage: [1]\n"), True),
    ("depends_on as a number", spec("approved", tasks=TASK.format(task="    depends_on: 5\n")), True),
    ("blocked_by as a number", spec("draft", "blocked_by: 5\n"), True),
    ("blocked_by as a string", spec("draft", "blocked_by: SPEC-2\n"), True),
    ("blocked_by with a number in it", spec("draft", "blocked_by: [SPEC-2, 5]\n"), False),
    ("flags as a number", spec("draft", "flags: 5\n"), True),
    ("deprecations as a string", spec("draft", "deprecations: x\n"), False),
    ("a route that is a list", spec("in_progress", "route: [major]\n"), False),
    ("a route outside the list", spec("in_progress", "route: sideways\n"), False),
    ("a review date that is a timestamp", spec("in_progress", EMERGENCY.format(due='"2026-11-09T10:00:00Z"')), False),
    ("a review date that is no date", spec("in_progress", EMERGENCY.format(due="soon")), False),
    ("an owner that is a list", spec("in_progress", "owner: [a, b]\n"), False),
    ("blockers as a list", spec("in_progress", "blockers: [a, b]\n"), False),
)


class HostileSpecTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        (self.root / ".aidd").mkdir()
        (self.root / ".aidd" / "config.yaml").write_text('aidd_version: "1.0.0"\nprofile: team\n', encoding="utf-8")
        (self.root / "specs").mkdir()
        (self.root / "specs" / "SPEC-2.md").write_text(GOOD, encoding="utf-8")
        helpers.git(self.root, "init", "-q", "-b", "main")
        here = os.getcwd()
        self.addCleanup(os.chdir, here)
        os.chdir(self.root)

    def test_one_hostile_field_never_breaks_a_mode_or_the_other_items(self):
        for what, text, unreadable in CASES:
            with self.subTest(what):
                (self.root / "specs" / "SPEC-1.md").write_text(text, encoding="utf-8")
                for argv in (("status",), ("status", "--html")):
                    code, out = helpers.run_cli(*argv)
                    self.assertEqual(code, 0, f"{argv}: {out[-300:]}")
                code, out = helpers.run_cli("status", "--json")
                self.assertEqual(code, 0, out[-300:])
                answer = json.loads(out)
                self.assertEqual(json_schema.validate(answer, "status.schema.json"), [], "what it says matches the schema")
                self.assertIn("SPEC-2", [i["id"] for i in answer["items"]], "the other items still show")
                aside = [u["path"] for u in answer.get("unreadable", [])]
                self.assertEqual("specs/SPEC-1.md" in aside, unreadable, f"{aside}")
                if unreadable:
                    self.assertNotIn("SPEC-1", [i["id"] for i in answer["items"]])

    EMERGENCY_CASES = (
        # (what, the emergency block's lines, what the banner says, what Details says, whether the block is incomplete)
        (
            "a commander and a bad date",
            "  severity: sev1\n  type: outage\n  commander: Lan\n  incident: INC-1\n  backfill_due: soon\n",
            ["Lan leads the incident", "Review due: can't be read"],
            {"Commander": "Lan", "Review due": "can't be read"},
            True,
        ),
        (
            "a commander and an incident that is a list",
            '  severity: sev1\n  type: outage\n  commander: Lan\n  incident: [1]\n  backfill_due: "2099-01-01"\n',
            ["Lan leads the incident"],
            {"Commander": "Lan", "Incident": "has a value aidd can't read"},
            True,
        ),
        (
            "a good date and no commander",
            '  severity: sev1\n  type: outage\n  incident: INC-1\n  backfill_due: "2099-01-01"\n',
            ["No commander is named", "Review due"],
            {"Commander": "not named"},
            True,
        ),
        (
            "no review date",
            "  severity: sev1\n  type: outage\n  commander: Lan\n",
            ["Lan leads the incident", "Review due: not set"],
            {"Review due": "not set", "Commander": "Lan"},
            True,
        ),
        (
            "a whole block",
            '  severity: sev1\n  type: outage\n  commander: Lan\n  incident: INC-1\n  backfill_due: "2099-01-01"\n',
            ["Lan leads the incident"],
            {"Commander": "Lan", "Incident": "INC-1"},
            False,
        ),
    )

    def test_an_incomplete_emergency_keeps_its_good_fields_and_names_only_what_is_absent_or_unreadable(self):
        """A commander who is named is never shown as missing because another field is bad: the page keeps each field that passes
        its own sub-schema, `--json` leaves the broken block out, and the banner always shows."""
        for what, lines, banner_says, details_say, incomplete in self.EMERGENCY_CASES:
            with self.subTest(what):
                (self.root / "specs" / "SPEC-1.md").write_text(spec("in_progress", "route: emergency\nemergency:\n" + lines), encoding="utf-8")
                self.assertEqual(helpers.run_cli("status", "--html")[0], 0)
                root = page_dom.parse((self.root / ".aidd" / "views" / "status-work.html").read_text(encoding="utf-8"))
                banner = root.find(data_testid="emergency-banner")
                assert banner is not None, "the banner always shows"
                for text in banner_says:
                    self.assertIn(text, banner.text)
                note = banner.find(data_field="incomplete")
                self.assertEqual(note is not None, incomplete)
                if note is not None:
                    self.assertIn("Its emergency block is incomplete: run aidd validate specs/SPEC-1.md", note.text)
                page = root.find("section", data_view="item", data_item="SPEC-1")
                assert page is not None
                rows = {dt.text: dd.text for dt, dd in zip(page.find_all("dt"), page.find_all("dd"), strict=True)}
                for label, said in details_say.items():
                    self.assertEqual(rows[label], said, (label, rows))
                self.assertNotIn("Review due no date", root.text)
                answer = json.loads(helpers.run_cli("status", "--json")[1])
                item = next(i for i in answer["items"] if i["id"] == "SPEC-1")
                self.assertEqual(item.get("route"), "emergency", "--json keeps the route")
                self.assertEqual("emergency" in item, not incomplete, "--json leaves a broken block out")
                self.assertEqual(json_schema.validate(answer, "status.schema.json"), [])

    def test_all_branches_shows_no_raw_emergency_block_of_this_worktree_for_another_branch(self):
        """Two places name different commanders and a third has no block: the page shows this worktree's own commander for its own
        version only, and for another place says the block is incomplete or differs, and claims no field of it."""
        whole = 'route: emergency\nemergency:\n  severity: sev1\n  type: outage\n  commander: "@mai"\n  incident: INC-1\n  backfill_due: "2099-01-01"\n'
        broken = 'route: emergency\nemergency:\n  severity: sev1\n  type: outage\n  commander: "@lan"\n  incident: INC-1\n'
        path = self.root / "specs" / "SPEC-1.md"
        path.write_text(spec("in_progress", whole), encoding="utf-8")
        helpers.git(self.root, "add", "-A")
        helpers.git(self.root, "commit", "-q", "-m", "main")
        for branch, text in (("lan", broken), ("none", "route: emergency\n")):
            helpers.git(self.root, "checkout", "-q", "-b", branch, "main")
            path.write_text(spec("in_progress", text), encoding="utf-8")
            helpers.git(self.root, "commit", "-q", "-am", branch)
        helpers.git(self.root, "checkout", "-q", "main")
        self.assertEqual(helpers.run_cli("status", "--all-branches", "--html")[0], 0)
        root = page_dom.parse((self.root / ".aidd" / "views" / "status-work-all-branches.html").read_text(encoding="utf-8"))
        banners = root.find_all(data_testid="emergency-banner")
        texts = sorted(b.text for b in banners)
        self.assertEqual(len(banners), 2, "this version, and the one version the other two places share")
        mine = [t for t in texts if "@mai leads the incident" in t]
        other = [t for t in texts if "differs by place" in t]
        self.assertEqual((len(mine), len(other)), (1, 1), texts)
        self.assertIn("Its emergency block is incomplete or differs by place: run aidd validate specs/SPEC-1.md in that branch", other[0])
        for claim in ("No commander is named", "@lan", "@mai", "Review due"):
            self.assertNotIn(claim, other[0], "no claim about a field this version may not have")
        pages = [p for p in root.find_all("section", data_view="item", data_item="SPEC-1") if "differs by place" in p.text]
        self.assertEqual(len(pages), 1)
        self.assertNotIn("Commander", pages[0].text)

    def test_a_spec_with_no_id_gets_no_words_and_never_the_word_none(self):
        text = spec("in_progress").replace("id: SPEC-1\n", "")
        (self.root / "specs" / "SPEC-1.md").write_text(text, encoding="utf-8")
        items = json.loads(helpers.run_cli("status", "--json")[1])["items"]
        bare = next(i for i in items if i["id"] != "SPEC-2")
        self.assertNotIn("words", bare["next"], "no id, no words")
        self.assertNotIn("None", bare["next"].get("words", ""))

    def test_a_route_outside_the_list_or_a_broken_emergency_leaves_the_route_the_schema_allows(self):
        (self.root / "specs" / "SPEC-1.md").write_text(spec("in_progress", EMERGENCY.format(due='"2026-11-09T10:00:00Z"')), encoding="utf-8")
        item = next(i for i in json.loads(helpers.run_cli("status", "--json")[1])["items"] if i["id"] == "SPEC-1")
        self.assertEqual((item.get("route"), "emergency" in item), ("emergency", False), "the route stays, the broken object is left out")
        (self.root / "specs" / "SPEC-1.md").write_text(spec("in_progress", "route: [major]\n"), encoding="utf-8")
        item = next(i for i in json.loads(helpers.run_cli("status", "--json")[1])["items"] if i["id"] == "SPEC-1")
        self.assertNotIn("route", item)


if __name__ == "__main__":
    unittest.main()
