"""The steps of a built change: Verify and Review of a head, and the observe window of a merged change. Each is read from the
Spec's file alone: its status, its Tasks, and its `outcome`."""

import unittest

from test_workitems import TODAY, Base, handoff, spec

from aidd.workitems import status, work_list

DONE_TASKS = 'tasks:\n  - {id: "SPEC-1-T1", title: t, scope: ["src/a/**"], done: true}\n  - {id: "SPEC-1-T2", title: t, scope: ["src/b/**"], done: true}\n'
ONE_OPEN = 'tasks:\n  - {id: "SPEC-1-T1", title: t, scope: ["src/a/**"], done: true}\n  - {id: "SPEC-1-T2", title: t, scope: ["src/b/**"]}\n'


class VerifyTests(Base):
    """A Spec in progress whose every Task is done stands at Verify and Review. No file records what a checker said, so a note
    never moves the step: the head is neither known clean (that is `in_review`) nor known failed."""

    # The note orders a run can leave, each as the `next_role` of its notes in order. Each is a way a reading of `next_role`
    # guesses: a clean reviewer report to the author, a failing verifier report to a role that is not a builder, one checker's
    # clean note while the other still runs, and a finding handed to a builder.
    NOTES = (
        (),
        ("verifier",),
        ("reviewer", "developer"),  # a clean reviewer report, posted by the author
        ("reviewer", "sre"),
        ("verifier", "architect"),  # a failing verifier report
        ("verifier", "reviewer"),
        ("verifier", "security-engineer", "developer"),  # one checker finished, another still runs
        ("developer", "verifier", "developer", "verifier"),
        ("unknown-role", "DEVELOPER"),
    )

    def step_of(self, notes: tuple[str, ...], tasks: str = DONE_TASKS, state: str = "in_progress") -> str:
        self.write("specs/SPEC-1.md", spec("SPEC-1", state, tasks=tasks, body="".join(handoff(n) for n in notes)))
        return self.codes()["SPEC-1"]

    def test_a_built_head_is_at_verify_whatever_its_notes_say(self):
        for notes in self.NOTES:
            with self.subTest(notes=notes):
                self.assertEqual(self.step_of(notes), "spec.verify")

    def test_only_a_built_spec_in_progress_stands_at_verify(self):
        for tasks, state, code in (
            (ONE_OPEN, "in_progress", "spec.in_progress"),  # a Task is not done
            (DONE_TASKS, "approved", "spec.approved"),
            (DONE_TASKS, "in_review", "pr.merge"),  # Verify and Review were clean
            ("", "in_progress", "spec.in_progress"),  # the sample's one Task is not done
        ):
            for notes in self.NOTES[:3]:
                with self.subTest(status=state, tasks=tasks[:20], notes=notes):
                    self.assertEqual(self.step_of(notes, tasks=tasks, state=state), code)

    def test_a_branch_tip_gives_the_same_step(self):
        text = spec("SPEC-1", "in_progress", tasks=DONE_TASKS, body=handoff("developer"))
        found, _ = work_list.parse_work([("specs/SPEC-1.md", text)])
        answer = work_list.open_items(found, [], None, today=TODAY)
        self.assertEqual(answer["items"][0]["next"]["code"], "spec.verify")

    def test_the_words_of_the_step(self):
        self.step_of(())
        item = self.items()["SPEC-1"]["next"]
        self.assertEqual((item["code"], item["who"], item["words"]), ("spec.verify", "agent", "Verify and review SPEC-1 on its head"))


class ObserveTests(Base):
    """A merged Spec with an observe window and no result stands at Roll out: open work, though its status is `done`."""

    def test_a_merged_change_in_its_window_is_work_until_a_result_or_the_window_ends(self):
        window = 'observe: {window: "7d", rollback_trigger: "errors up"}\n'
        released = 'outcome: {released_on: "2026-09-25"}\n'
        table = (
            ("done", window + released, TODAY, "spec.observe"),  # inside the window
            ("done", window, TODAY, "spec.observe"),  # released today or not yet recorded
            ("done", window + 'outcome: {released_on: "2026-09-28"}\n', TODAY, "spec.observe"),  # the day of release
            ("done", window + 'outcome: {released_on: "2026-09-05"}\n', TODAY, None),  # the window ended
            ("done", window + 'outcome: {released_on: "2026-09-21"}\n', TODAY, "spec.observe"),  # its last day
            ("done", window + 'outcome: {released_on: "2026-09-20"}\n', TODAY, None),  # the day after
            ("done", window + 'outcome: {released_on: "2026-09-25", observe_result: pass}\n', TODAY, None),  # a clean window is recorded
            ("done", window + 'outcome: {released_on: "2026-09-25", observe_result: fail}\n', TODAY, None),  # a failed one is for Learn
            ("done", "", TODAY, None),  # no window to watch
            ("rolled_back", window + released, TODAY, None),
            ("in_review", window + released, TODAY, "pr.merge"),  # not merged yet
            ("cancelled", window + released, TODAY, None),
        )
        for state, extra, today, code in table:
            with self.subTest(status=state, extra=extra, today=str(today)):
                self.write("specs/SPEC-1.md", spec("SPEC-1", state, extra))
                self.assertEqual(self.codes(today=today).get("SPEC-1"), code)

    def test_a_hypothesis_past_due_is_the_persons_step_before_the_window(self):
        extra = 'hypothesis: "refunds drop by 2026-09-01"\nobserve: {window: "7d", rollback_trigger: "errors up"}\n'
        self.write("specs/SPEC-1.md", spec("SPEC-1", "done", extra))
        self.assertEqual(self.codes()["SPEC-1"], "spec.outcome_due")

    def test_the_step_is_an_agents_with_its_words_and_stays_with_the_open_work_only(self):
        self.write("specs/SPEC-1.md", spec("SPEC-1", "done", 'observe: {window: "7d", rollback_trigger: "x"}\n'))
        step = self.items()["SPEC-1"]["next"]
        self.assertEqual((step["code"], step["who"], step["words"]), ("spec.observe", "agent", "Watch SPEC-1 through its observe window"))
        self.assertEqual(self.items()["SPEC-1"]["group"], "completed")


class OnlyTheseStepsChangeTests(Base):
    """The two new codes replace two old ones in exact cells, and no other Spec's step moves."""

    WINDOWS = (
        "",
        'observe: {window: "7d", rollback_trigger: "x"}\n',
        'observe: {window: "7d", rollback_trigger: "x"}\noutcome: {released_on: "2026-09-25"}\n',
        'observe: {window: "7d", rollback_trigger: "x"}\noutcome: {released_on: "2026-09-25", observe_result: pass}\n',
        'observe: {window: "7d", rollback_trigger: "x"}\noutcome: {released_on: "2026-08-01"}\n',
    )
    TASKS = (DONE_TASKS, ONE_OPEN, "")
    NOTES = ((), ("developer",), ("verifier",), ("reviewer", "developer"))

    def test_a_step_moves_only_from_in_progress_when_built_and_from_done_when_observed(self):
        generated = {}
        for status_name in status.SPEC_STATUSES:
            for window in self.WINDOWS:
                for tasks in self.TASKS:
                    for notes in self.NOTES:
                        sid = f"SPEC-{len(generated) + 1}"
                        text = spec(
                            sid, status_name, window, tasks=tasks.replace("SPEC-1-", f"{sid}-") if tasks else "", body="".join(handoff(n) for n in notes)
                        )
                        self.write(f"specs/{sid}.md", text)
                        generated[sid] = (status_name, window, tasks, notes)
        new = {i: x["next"]["code"] for i, x in self.items(include_done=True).items() if "next" in x}
        found, _ = work_list.read_work(self.root, None)
        moved = 0
        for _path, data in found:
            sid = str(data["id"])
            old = work_list.spec_step(data, status.spec_status(data), [], None)["code"]  # the function this change left as it was
            status_name, window, tasks, notes = generated[sid]
            built = status_name == "in_progress" and tasks == DONE_TASKS
            watched = status_name == "done" and window and "observe_result" not in window and "2026-08-01" not in window
            expected = "spec.verify" if built else "spec.observe" if watched else old
            with self.subTest(spec=sid, status=status_name, window=window[:30], notes=notes):
                self.assertEqual(new.get(sid), expected)
            moved += expected != old
        self.assertEqual(len(generated), len(status.SPEC_STATUSES) * len(self.WINDOWS) * len(self.TASKS) * len(self.NOTES))
        self.assertGreater(moved, 0)


if __name__ == "__main__":
    unittest.main()
