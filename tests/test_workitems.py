"""Work items a team steers by, from the repository alone: the open work list and its next steps, status groups,
relations, labels, priority, and the handoff note.

None of it is evidence: the risk rules never read relations, labels, triage, priority, or handoff notes, and nothing here
needs git, because the status of a work item is stored in its front matter."""

import datetime as dt
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, git, modules_under, run_cli, source_of

from aidd import views, workitems
from aidd.docsgen import schema_tables
from aidd.kernel import json_schema, resources
from aidd.views import work_item_page
from aidd.workitems import backlog, spec_file, validation

TODAY = dt.date(2026, 9, 28)
NOW = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.UTC)


def spec(sid: str, status: str = "draft", extra: str = "", tasks: str = "", body: str = "") -> str:
    """A small Spec front matter; enough for `aidd status`, which read the fields they need and never validate."""
    tasks = tasks or f'tasks:\n  - id: "{sid}-T1"\n    title: t\n    scope: ["src/{sid.lower()}/**"]\n'
    return f'---\naidd_version: "1.0.0"\ntype: spec\nid: "{sid}"\ntitle: "{sid}"\nstatus: {status}\n{extra}\n{tasks}---\n{body}'


def container(item_type: str, cid: str, goal: str, extra: str = "") -> str:
    return f'---\naidd_version: "1.0.0"\ntype: "{item_type}"\nid: "{cid}"\ntitle: "{cid}"\ngoal: "{goal}"\nstatus: active\n{extra}---\n'


def handoff(nxt: str, needs: str = "none", done: str = "T1 built") -> str:
    return f'\n```aidd-handoff\ndone: "{done}"\nnext: "{nxt}"\nneeds: "{needs}"\nstopped_at: none\n```\n'


class Base(unittest.TestCase):
    """A directory of work items: the open work reads the files alone."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

    def write(self, rel: str, text: str) -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def work(self, **kw) -> dict:
        return workitems.open_work(self.root, None, today=kw.pop("today", TODAY), **kw)

    def items(self, **kw) -> dict[str, dict]:
        return {i["id"]: i for i in self.work(**kw)["items"]}

    def codes(self, **kw) -> dict[str, str]:
        return {i: x["next"]["code"] for i, x in self.items(**kw).items() if "next" in x}

    def cli(self, *argv: str) -> tuple[int, str]:
        git(self.root, "init", "-q", "-b", "main")
        here = os.getcwd()
        os.chdir(self.root)
        try:
            return run_cli(*argv)
        finally:
            os.chdir(here)


class OpenWorkTests(Base):
    """The open work: each item with its stored status, its group, and the next step."""

    def test_each_status_has_its_next_step_and_finished_work_is_left_out(self):
        for sid, status in (
            ("SPEC-1", "draft"),
            ("SPEC-2", "ready"),
            ("SPEC-3", "approved"),
            ("SPEC-4", "in_progress"),
            ("SPEC-5", "in_review"),
            ("SPEC-6", "done"),
            ("SPEC-7", "cancelled"),
            ("SPEC-8", "rolled_back"),
        ):
            self.write(f"specs/{sid}.md", spec(sid, status))
        self.assertEqual(
            self.codes(),
            {
                "SPEC-1": "spec.draft",
                "SPEC-2": "spec.approval",
                "SPEC-3": "spec.approved",
                "SPEC-4": "spec.in_progress",
                "SPEC-5": "spec.merge",
            },
        )
        by = self.items()
        self.assertEqual([by[i]["group"] for i in sorted(by)], ["backlog", "unstarted", "unstarted", "started", "started"])
        everything = self.items(include_done=True)
        self.assertEqual((everything["SPEC-6"]["group"], everything["SPEC-8"]["group"], everything["SPEC-7"]["group"]), ("completed", "completed", "cancelled"))
        self.assertEqual(everything["SPEC-8"]["next"]["code"], "spec.rolled_back")

    def test_who_takes_each_step(self):
        self.write("specs/SPEC-1.md", spec("SPEC-1", "ready"))
        self.write("specs/SPEC-2.md", spec("SPEC-2", "approved"))
        by = self.items()
        self.assertEqual((by["SPEC-1"]["next"]["who"], by["SPEC-2"]["next"]["who"]), ("person", "agent"))

    def test_nothing_open_says_so(self):
        answer = self.work()
        self.assertEqual((answer["items"], answer["next"]["code"]), ([], "nothing_open"))
        self.write("specs/SPEC-1.md", spec("SPEC-1", "done"))
        self.assertEqual(self.work()["next"]["code"], "nothing_open")

    def test_a_blocker_and_a_blocked_by_item_block_a_spec(self):
        self.write("specs/SPEC-1.md", spec("SPEC-1", "in_progress"))
        self.write("specs/SPEC-2.md", spec("SPEC-2", "ready", "relations: [{type: blocked_by, id: SPEC-1}]"))
        self.write("specs/SPEC-3.md", spec("SPEC-3", "ready", "blockers: the vendor"))
        self.write("specs/SPEC-4.md", spec("SPEC-4", "draft", "relations: [{type: blocks, id: SPEC-5}]"))
        self.write("specs/SPEC-5.md", spec("SPEC-5", "draft"))
        self.write("specs/SPEC-6.md", spec("SPEC-6", "ready", "blockers: legal must sign the DPA\nrelations: [{type: blocked_by, id: SPEC-1}]"))
        steps = {i: s["next"] for i, s in self.items().items()}
        self.assertEqual(
            {i: (steps[i]["code"], steps[i]["who"]) for i in ("SPEC-2", "SPEC-3", "SPEC-5", "SPEC-6")},
            {
                "SPEC-2": ("spec.blocked_by", "nobody"),
                "SPEC-3": ("spec.blocked", "person"),
                "SPEC-5": ("spec.blocked_by", "nobody"),
                "SPEC-6": ("spec.blocked", "person"),  # a blocker a person must clear stays theirs beside a blocked_by
            },
        )
        self.assertTrue(work_item_page.words_to_type(self.items()["SPEC-6"]), "the person's blocker has words to type")
        self.assertIn("blocked by SPEC-1", self.items()["SPEC-2"]["next"]["what"])
        self.assertIn("the vendor", self.items()["SPEC-3"]["next"]["what"])
        # Once SPEC-1 is done, SPEC-2 goes ahead.
        self.write("specs/SPEC-1.md", spec("SPEC-1", "done"))
        self.assertEqual(self.codes()["SPEC-2"], "spec.approval")

    def test_a_task_that_used_its_retries_blocks_the_spec(self):
        tasks = 'tasks:\n  - id: T1\n    title: t\n    scope: ["a/**"]\n    retry_count: 3\n'
        self.write("specs/SPEC-1.md", spec("SPEC-1", "in_progress", tasks=tasks))
        self.assertEqual(self.codes()["SPEC-1"], "spec.blocked")
        self.assertIn("T1 used its 3 retries", self.items()["SPEC-1"]["next"]["what"])

    def test_a_declined_suggestion_is_cancelled_and_an_untriaged_one_waits_for_a_person(self):
        self.write("specs/SPEC-1.md", spec("SPEC-1", "draft", "suggested_by: agent:sre"))
        self.write("specs/SPEC-2.md", spec("SPEC-2", "draft", 'suggested_by: agent:sre\ntriage: {decision: declined, by: "@lead"}'))
        self.assertEqual(self.codes(), {"SPEC-1": "spec.triage"})
        self.assertEqual(self.items(include_done=True)["SPEC-2"]["group"], "cancelled")

    def test_an_emergency_spec_comes_first_and_is_urgent(self):
        self.write("specs/SPEC-1.md", spec("SPEC-1", "ready"))
        self.write("specs/INC-1.md", spec("INC-1", "in_progress", "route: emergency"))
        self.assertEqual(self.codes()["INC-1"], "spec.emergency")
        self.assertEqual(list(self.items()), ["INC-1", "SPEC-1"])

    def test_priority_sorts_within_a_group_and_is_inherited_from_the_epic(self):
        self.write("specs/EPIC-1.md", container("epic", "EPIC-1", "g", "priority: high\n"))
        self.write("specs/SPEC-9.md", spec("SPEC-9", "ready", "parent: EPIC-1"))
        self.write("specs/SPEC-10.md", spec("SPEC-10", "ready", "priority: urgent"))
        self.write("specs/SPEC-11.md", spec("SPEC-11", "ready", "priority: low"))
        order = [i for i, x in self.items().items() if x["type"] == "spec"]
        self.assertEqual(order[0], "SPEC-10")
        self.assertEqual(sorted(order[1:]), ["SPEC-11", "SPEC-9"])

    def test_an_epic_closes_once_every_child_is_finished(self):
        self.write("specs/EPIC-1.md", container("epic", "EPIC-1", "retry payouts").replace("status: active\n", ""))
        self.write("specs/SPEC-20.md", spec("SPEC-20", "done", "parent: EPIC-1"))
        self.write("specs/SPEC-21.md", spec("SPEC-21", "ready", "parent: EPIC-1"))
        epic = self.items()["EPIC-1"]
        self.assertEqual((epic["status"], epic["progress"]), ("active", {"finished": 1, "of": 2}))
        self.assertNotIn("next", epic)
        self.write("specs/SPEC-21.md", spec("SPEC-21", "done", "parent: EPIC-1"))
        self.assertEqual(self.codes()["EPIC-1"], "epic.close")
        self.write("specs/EPIC-1.md", container("epic", "EPIC-1", "retry payouts").replace("status: active", "status: done"))
        self.assertEqual(self.items(), {})

    def test_a_proposal_shows_its_state(self):
        self.write(
            "proposals/PROP-1/proposal.md",
            '---\naidd_version: "1.0.0"\ntype: proposal\nid: PROP-1\ntitle: t\naudience: internal\naddressee: the board\ngoal: g\n---\n',
        )
        self.assertEqual(self.codes()["PROP-1"], "proposal.qualifying")

    def test_a_hypothesis_past_due_with_no_result_is_work(self):
        self.write("specs/SPEC-1.md", spec("SPEC-1", "done", 'hypothesis: "refunds drop to 1% by 2026-09-01"'))
        self.assertEqual(self.codes()["SPEC-1"], "spec.outcome_due")
        self.assertEqual(self.codes(today=dt.date(2026, 8, 1)), {})
        self.write("specs/SPEC-1.md", spec("SPEC-1", "done", 'hypothesis: "refunds drop to 1% by 2026-09-01"\noutcome: {result: "met: 0.9%"}'))
        self.assertEqual(self.codes(), {})

    def test_the_status_command_lists_filters_by_id_and_prints_json(self):
        self.write("specs/SPEC-1.md", spec("SPEC-1", "ready", "labels: [area:billing]"))
        self.write("specs/SPEC-2.md", spec("SPEC-2", "approved"))
        (self.root / ".aidd").mkdir()
        self.write(".aidd/config.yaml", 'aidd_version: "1.0.0"\nprofile: team\n')
        code, out = self.cli("status", "--json")
        self.assertEqual(code, 0, out)
        data = json.loads(out)
        self.assertEqual({i["id"] for i in data["items"]}, {"SPEC-1", "SPEC-2"})
        code, out = self.cli("status", "SPEC-1", "--json")
        self.assertEqual((code, [i["id"] for i in json.loads(out)["items"]]), (0, ["SPEC-1"]))
        code, out = self.cli("status", "SPEC-1")
        self.assertEqual(code, 0, out)
        self.assertIn("SPEC-1", out)
        self.assertIn("next (person)", out)
        self.assertNotEqual(self.cli("status", "SPEC-404")[0], 0)

    def test_an_item_not_set_up_says_what_to_run(self):
        code, out = self.cli("status")
        self.assertEqual(code, 0, out)
        self.assertIn("aidd init", out)


class StatusPageTests(Base):
    """R307: `aidd status --html` writes one read-only page: the open work by whose move it is, each item with its next step
    and the words to type, and the Initiatives and Epics with their children. Every value is a file's text, so the page
    escapes it."""

    HOSTILE = "</style><script>alert(1)</script>"

    def setUp(self):
        super().setUp()
        self.write("specs/INIT-1.md", container("initiative", "INIT-1", "Grow"))
        self.write("specs/EPIC-1.md", container("epic", "EPIC-1", "Checkout", "parent: INIT-1\n"))
        self.write("specs/SPEC-1.md", spec("SPEC-1", "in_progress", "parent: EPIC-1"))
        self.write(
            "specs/SPEC-2.md",
            spec("SPEC-2", "ready", "parent: EPIC-1\nrelations: [{type: blocked_by, id: SPEC-1}]").replace('title: "SPEC-2"', f'title: "{self.HOSTILE}"'),
        )

    def test_the_answer_names_each_parent_and_what_each_item_waits_on(self):
        items = self.items()
        self.assertEqual((items["SPEC-2"]["parent"], items["SPEC-2"]["waiting_on"]), ("EPIC-1", ["SPEC-1"]))
        self.assertNotIn("waiting_on", items["SPEC-1"])
        self.assertEqual(json_schema.validate({"schema_version": "1", **self.work()}, "status.schema.json"), [])

    def test_the_page_holds_the_tree_the_board_and_the_words_and_escapes_every_value(self):
        code, out = self.cli("status", "--html")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.root / ".aidd" / "views" / "status-work.html").is_file(), out)
        page = views.status_page(self.work())
        self.assertNotIn(self.HOSTILE, page)
        self.assertIn("&lt;/style&gt;&lt;script&gt;", page)
        # Every script tag in any case, with or without attributes: an injected one must never go uncounted.
        self.assertEqual(len(re.findall(r"<script\b", page, re.IGNORECASE)), 1, "the one copy script, pinned by the page's policy")
        self.assertNotIn("<form", page)

        def section(key: str) -> str:
            return page.split(f'id="{key}"', 1)[1].split("</section>", 1)[0]

        plans = section("plans")
        self.assertLess(plans.index("INIT-1"), plans.index("EPIC-1"))
        self.assertLess(plans.index("EPIC-1"), plans.index("SPEC-1"))
        self.assertNotIn("SPEC-2", section("needs-you"), "a Spec that waits for other work is blocked, never a person's step")
        self.assertRegex(section("blocked"), r'href="#w-\d+">SPEC-1</a> finishes', "a blocked Spec links the work it waits for")
        self.assertEqual(page.count('<span class="id">EPIC-1</span>'), 1, "a container shows with its children, never as an empty step")
        self.assertIn("Go on with SPEC-1", page, "an agent's step is started by the words to type")

    def test_nobody_takes_a_blocked_step_so_mine_leaves_it_out(self):
        self.assertEqual(self.items()["SPEC-2"]["next"]["who"], "nobody")
        code, out = self.cli("status", "--mine")
        self.assertEqual(code, 0, out)
        self.assertNotIn("SPEC-2", out)

    def test_the_page_names_its_folder_the_time_it_was_written_and_each_copy_button(self):
        self.assertEqual(self.cli("status", "--html")[0], 0)
        page = (self.root / ".aidd" / "views" / "status-work.html").read_text(encoding="utf-8")
        self.assertIn(f"<title>The open work in {self.root.name}</title>", page)
        self.assertRegex(page, r"Written \d{1,2} [A-Z][a-z]+ \d{4} at \d\d:\d\d\.")
        self.assertIn('aria-label="Copy the words for SPEC-1"', views.status_page(self.work()))

    def test_whose_move_reads_who_takes_the_step_first(self):
        cases = [
            ("completed", {"who": "person", "code": "spec.outcome_due"}, "spec", "needs-you"),
            ("completed", {"who": "agent", "code": "spec.rolled_back"}, "spec", "agents"),
            ("completed", {"who": "nobody", "code": "spec.done"}, "spec", "finished"),
            ("cancelled", {"who": "nobody", "code": "spec.cancelled"}, "spec", "finished"),
            ("unstarted", {"who": "nobody", "code": "spec.blocked_by"}, "spec", "blocked"),
            ("started", {"who": "person", "code": "spec.blocked"}, "spec", "needs-you"),
            ("started", None, "epic", None),
        ]
        for group, step, kind, move in cases:
            with self.subTest(group=group, step=step):
                self.assertEqual(work_item_page.whose_move({"id": "X-1", "type": kind, "group": group} | ({"next": step} if step else {})), move)

    def test_a_page_with_only_past_due_work_shows_it_and_no_start(self):
        due = [{"path": "specs/SPEC-9.md", "what": "flag x was due", "next": {"code": "flag.overdue", "who": "agent", "what": "remove it"}}]
        page = views.status_page({"items": [], "due": due})
        self.assertIn('id="due"', page)
        self.assertNotIn('id="start"', page)

    def test_an_item_in_a_loop_of_parents_still_shows(self):
        work = {
            "items": [
                {"id": "SPEC-7", "type": "spec", "title": "itself", "status": "draft", "group": "backlog", "path": "specs/SPEC-7.md", "parent": "SPEC-7"},
                {"id": "EPIC-8", "type": "epic", "title": "a", "status": "active", "group": "started", "path": "specs/EPIC-8.md", "parent": "EPIC-9"},
                {"id": "EPIC-9", "type": "epic", "title": "b", "status": "active", "group": "started", "path": "specs/EPIC-9.md", "parent": "EPIC-8"},
            ]
        }
        plans = views.status_page(work).split('id="plans"', 1)[1].split("</section>", 1)[0]
        for ident in ("SPEC-7", "EPIC-8", "EPIC-9"):
            self.assertIn(f">{ident}</", plans)

    def test_an_empty_page_says_what_to_do_next(self):
        page = views.status_page({"items": [], "due": [], "next": {"code": "nothing_open", "who": "person", "what": "nothing is open"}})
        self.assertIn('id="start"', page)
        self.assertNotIn('id="needs-you"', page)


class GroupTests(unittest.TestCase):
    def test_every_status_has_a_group(self):
        common = resources.load_json("common.schema.json")["$defs"]
        proposal = resources.load_json("proposal.schema.json")["properties"]["status"]
        groups = set(common["status_group"]["enum"])
        self.assertEqual(groups, set(backlog.GROUPS))
        for vocab in (common["status"], common["container_status"], proposal):
            self.assertEqual(set(vocab["x-groups"]), set(vocab["enum"]))
            self.assertLessEqual(set(vocab["x-groups"].values()), groups)
        self.assertEqual(backlog.group({"type": "spec"}), "backlog")  # no status is a draft
        self.assertEqual(backlog.group({"type": "epic", "status": "active"}), "started")
        self.assertEqual(backlog.group({"type": "proposal", "status": "no_go"}), "cancelled")
        self.assertEqual(backlog.group({"type": "proposal"}, "signed_off"), "started")
        self.assertEqual(
            {s: backlog.group({"type": "spec", "status": s}) for s in ("ready", "approved", "in_review", "rolled_back")},
            {"ready": "unstarted", "approved": "unstarted", "in_review": "started", "rolled_back": "completed"},
        )
        self.assertIsNone(backlog.group({"type": "runbook"}))

    def test_the_method_carries_the_generated_table(self):
        text = (ROOT / "docs" / "METHOD.md").read_text(encoding="utf-8")
        self.assertIn("<!-- aidd:gen status:groups -->\n" + schema_tables.groups_table() + "\n<!-- aidd:end -->", text)
        self.assertIn("| `completed` |", schema_tables.groups_table())


class ValidateStatusTests(Base):
    def test_validate_warns_about_a_done_epic_with_an_open_child_and_refuses_an_unknown_status(self):
        self.write("specs/EPIC-1.md", container("epic", "EPIC-1", "g").replace("status: active", "status: done"))
        self.write("specs/SPEC-1.md", spec("SPEC-1", "ready", "parent: EPIC-1"))
        warnings = validation.check_repo(self.root, today=TODAY)[1]
        self.assertIn("specs/EPIC-1.md: status done, but SPEC-1 is not finished; reopen it or finish them", warnings)
        for sid, bad in (("SPEC-2", "released"), ("SPEC-3", "blocked"), ("SPEC-4", "landed")):
            self.write(f"specs/{sid}.md", spec(sid, bad))
            found = validation.validate_file(self.root / f"specs/{sid}.md")
            self.assertTrue(any("status" in e and not e.startswith("warning:") for e in found), (bad, found))


class RelationTests(Base):
    def test_validate_checks_targets_self_links_and_cycles(self):
        self.write("specs/EPIC-1.md", container("epic", "EPIC-1", "g", "relations: [{type: relates_to, id: SPEC-9}]\n"))
        self.write("specs/INIT-1.md", container("initiative", "INIT-1", "g", "relations: [{type: blocks, id: INIT-1}]\n"))
        errors = backlog.relation_errors(
            [
                ("specs/EPIC-1.md", {"type": "epic", "id": "EPIC-1", "relations": [{"type": "relates_to", "id": "SPEC-9"}]}),
                ("specs/INIT-1.md", {"type": "initiative", "id": "INIT-1", "relations": [{"type": "blocks", "id": "INIT-1"}]}),
                ("specs/A.md", {"type": "spec", "id": "A", "relations": [{"type": "blocks", "id": "B"}]}),
                ("specs/B.md", {"type": "spec", "id": "B", "relations": [{"type": "blocked_by", "id": "C"}]}),
                ("specs/C.md", {"type": "spec", "id": "C", "relations": [{"type": "blocked_by", "id": "B"}]}),
                ("specs/D.md", {"type": "spec", "id": "D", "relations": [{"type": "duplicates", "id": "Z"}]}),
            ]
        )
        self.assertEqual(len(errors), 4, errors)
        self.assertTrue(any("relates_to SPEC-9: no Spec, Epic, or Initiative" in e for e in errors))
        self.assertTrue(any("blocks INIT-1 points at itself" in e for e in errors))
        self.assertTrue(any("duplicates Z: no Spec, Epic, or Initiative" in e for e in errors))
        (cycle,) = [e for e in errors if "cycle" in e]
        self.assertIn("B -> C -> B", cycle)
        # A blocks B with B blocked_by A is one edge, not a cycle.
        ok = [
            ("a", {"type": "spec", "id": "A", "relations": [{"type": "blocks", "id": "B"}]}),
            ("b", {"type": "spec", "id": "B", "relations": [{"type": "blocked_by", "id": "A"}]}),
        ]
        self.assertEqual(backlog.relation_errors(ok), [])
        # `aidd validate` on the repository reports them.
        errors, _ = validation.check_repo(self.root, today=TODAY)
        self.assertTrue(any("relates_to SPEC-9" in e for e in errors), errors)
        self.assertTrue(any("points at itself" in e for e in errors), errors)

    def test_labels_and_relations_are_schema_checked(self):
        bad = {"labels": ["Upper"]}, {"labels": [f"l{i}" for i in range(9)]}, {"relations": [{"type": "parent_of", "id": "X"}]}
        base = {"aidd_version": "1.0.0", "type": "epic", "id": "E", "title": "t", "goal": "g", "status": "active"}
        self.assertEqual(
            json_schema.validate(base | {"labels": ["area:billing", "customer-ask"], "relations": [{"type": "implements", "id": "I-1"}]}, "epic.schema.json"),
            [],
        )
        for extra in bad:
            self.assertTrue(json_schema.validate(base | extra, "epic.schema.json"), extra)

    def test_a_duplicate_is_dropped_from_the_work_it_blocks(self):
        self.write("specs/SPEC-1.md", spec("SPEC-1", "in_progress"))
        self.write("specs/SPEC-3.md", spec("SPEC-3", "ready", "relations: [{type: duplicates, id: SPEC-1}]"))
        self.write("specs/SPEC-2.md", spec("SPEC-2", "ready", "relations: [{type: blocked_by, id: SPEC-3}]"))
        # SPEC-3 repeats SPEC-1, which carries the work: SPEC-2 waits for SPEC-1's work only through SPEC-3, so it goes ahead.
        self.assertEqual(self.codes()["SPEC-2"], "spec.approval")


class HandoffTests(unittest.TestCase):
    def test_the_skill_names_bookkeeping_fields_that_leave_spec_approval_standing(self):
        text = (ROOT / ".agents" / "skills" / "aidd" / "references" / "state.md").read_text(encoding="utf-8")
        line = next(ln for ln in text.splitlines() if "is a change to the approved Spec" in ln)
        self.assertIn("none needs `spec.revise`", line)
        for key in ("blockers", "priority", "owner", "provides", "consumes"):
            self.assertIn(f"`{key}`", text, key)
            self.assertIn(key, spec_file.VOLATILE_SPEC_KEYS)
        self.assertIn("retry_count", spec_file.VOLATILE_TASK_KEYS)


class AdviceNeverReadsTests(unittest.TestCase):
    """Relations, labels, triage, priority, and handoff notes are for people; the risk rules' advice is the same with or
    without them."""

    def test_the_risk_modules_never_name_the_work_item_fields(self):
        for module in modules_under("aidd.risk"):
            text = source_of(module)
            for word in ("relations", "labels", "triage", "priority", "aidd-handoff", "workitems", "blockers", "hypothesis"):
                self.assertIsNone(re.search(rf"\b{re.escape(word)}\b", text), f"{module} reads {word}")


if __name__ == "__main__":
    unittest.main()
