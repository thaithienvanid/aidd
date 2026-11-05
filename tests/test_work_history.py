"""The work history reader (`aidd eval work`): baselines and signals from git and files, on a built repository."""

import datetime as dt
import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import SAMPLE_SPEC, git, run_cli

from aidd import records, workitems
from aidd.evals import work_history as wh
from aidd.kernel import git as git_kernel
from aidd.kernel import json_schema
from aidd.workitems import commit_text, handoff_notes, validation

BASE = dt.datetime(2026, 10, 1, tzinfo=dt.UTC)
IDENT = ("-c", "user.name=Test Person", "-c", "user.email=person@example.com", "-c", "commit.gpgsign=false")


def commit(root: Path, hours: float, subject: str, trailer: str | None = "claude-code/model-a", committed_hours: float | None = None) -> str:
    """Commit everything at `hours` after BASE, with an Assisted-by trailer unless `trailer` is None. A rebase or a squash
    moves the committer time and keeps the author time, so `committed_hours` sets the committer time apart."""
    when = (BASE + dt.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    committed = (BASE + dt.timedelta(hours=hours if committed_hours is None else committed_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    message = subject + (f"\n\nAssisted-by: {trailer}" if trailer else "")
    env = {**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": committed}
    git(root, *IDENT, "add", "-A", env=env)
    git(root, *IDENT, "commit", "-q", "--allow-empty", "-m", message, env=env)
    return git(root, "rev-parse", "HEAD")


def write_spec(root: Path, n: int, status: str, note: tuple[str, str, str] | None = None, approved_hours: float | None = None) -> None:
    approval = (
        f'approved_by: Pat\napproved_at: "{(BASE + dt.timedelta(hours=approved_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")}"\n' if approved_hours is not None else ""
    )
    block = ""
    if note:
        label, nxt, spend = note
        block = f'\n```aidd-handoff\ndone: {label}\nnext: {nxt}\nneeds: none\nstopped_at: none\nspend: "{spend}"\n```\n'
    (root / "specs").mkdir(exist_ok=True)
    (root / "specs" / f"SPEC-{n}.md").write_text(
        f"---\ntype: spec\nid: SPEC-{n}\ntitle: Thing {n}\nstatus: {status}\n{approval}---\n\nBody.\n{block}", encoding="utf-8"
    )


def build_history(root: Path) -> str:
    """Five Specs: draft at 0 h, ready at 1 h, approved (approved_at 3 h) after a 2 h wait, then a chain of handoff notes.
    SPEC-1 and SPEC-2 are sent back once by the verifier, the others pass to the reviewer. SPEC-1 idles 11 h before its last commit."""
    git(root, "init", "-q", "-b", "main")
    first = ""
    for n in range(1, 6):
        write_spec(root, n, "draft")
        sha = commit(root, 0, f"SPEC-{n}: write the spec")
        first = first or sha
        write_spec(root, n, "ready")
        commit(root, 1, f"SPEC-{n}: ask for approval")
        write_spec(root, n, "approved", approved_hours=3)
        commit(root, 3, f"SPEC-{n}: approved")
        write_spec(root, n, "approved", ("dev one", "verifier", "12k tokens"), 3)
        commit(root, 4, f"SPEC-{n}: implement")
        if n <= 2:
            write_spec(root, n, "approved", ("verify one", "developer", "$0.40"), 3)
            commit(root, 5, f"SPEC-{n}: verify", "codex/model-b")
            write_spec(root, n, "approved", ("dev two", "verifier", "unknown"), 3)
            commit(root, 6, f"SPEC-{n}: rework")
            write_spec(root, n, "approved", ("verify two", "reviewer", "$0.40"), 3)
            commit(root, 17 if n == 1 else 7, f"SPEC-{n}: verify again", "codex/model-b")
        else:
            write_spec(root, n, "approved", ("verify one", "reviewer", "$0.40"), 3)
            commit(root, 5, f"SPEC-{n}: verify", "codex/model-b")
    commit(root, 18, "a change by hand", None)
    return first


def add_records(root: Path) -> None:
    head = git(root, "rev-parse", "HEAD")
    for n in range(1, 6):
        for words in ("yes", "yes, go on"):
            data = {
                "action": "spec.approve",
                "question": {"type": "approval", "text": f"Approve SPEC-{n}?"},
                "answer": {"outcome": "accept", "words": words, "by": "Pat"},
            }
            records.add_record("decision", data, by="agent:test", subject=f"SPEC-{n}", cwd=str(root))
        for k in range(2):
            data = {"action": "workflow.run", "said": f"ran the tests {k}", "covers": {"head": f"{n}{head[1:8]}", "command": "aidd test"}}
            records.add_record("report", data, by="agent:test", cwd=str(root))
    # A pull request report that mentions a test in its command is no suite run, and no workflow run.
    data = {"action": "pr.open", "said": "opened it", "covers": {"head": head[:8], "command": "gh pr create --title 'Add test coverage'"}}
    records.add_record("report", data, by="agent:test", cwd=str(root))
    data = {"action": "git.push", "question": {"type": "approval", "text": "Push?"}, "answer": {"outcome": "decline", "words": "no", "by": "Pat"}}
    records.add_record("decision", data, by="agent:test", cwd=str(root))


class ParsingTests(unittest.TestCase):
    def test_a_trailer_block_gives_the_harness_and_model(self):
        for message, expected in (
            ("fix\n\nAssisted-by: claude-code/claude-opus-5-5", ("claude-code", "claude-opus-5-5")),
            ("fix\n\nSigned-off-by: A\nassisted-by: codex/gpt-9", ("codex", "gpt-9")),
            ("fix\n\nAssisted-by: someharness", ("someharness", wh.UNMARKED)),
            ("fix", (wh.UNMARKED, wh.UNMARKED)),
            ("fix\n\nbody that says Assisted-by: x/y in prose", (wh.UNMARKED, wh.UNMARKED)),
            ("fix\n\nAssisted-by: x/y\nand a stray line", ("x", "y")),  # the rule aidd status uses for a path: any line that starts with the key
        ):
            with self.subTest(message=message):
                self.assertEqual(wh.harness_and_model(message), expected)

    def test_each_spelling_of_one_harness_counts_under_its_id(self):
        for value, expected in (
            ("claude-code/claude-opus-5-5", ("claude-code", "claude-opus-5-5")),
            ("Claude Code/claude-opus-5-5", ("claude-code", "claude-opus-5-5")),
            ("claude_code/Claude-Opus-5-5", ("claude-code", "claude-opus-5-5")),
            ("GitHub Copilot/gpt-9", ("copilot", "gpt-9")),
            ("Some Tool/model x", ("some-tool", "model-x")),
        ):
            with self.subTest(value=value):
                self.assertEqual(wh.harness_and_model(f"fix\n\nAssisted-by: {value}"), expected)

    def test_a_spend_line_gives_tokens_and_cost_only_when_it_says_them(self):
        for text, expected in (
            ("12k tokens", (12000, None)),
            ("1,500 tokens, $0.25", (1500, 0.25)),
            ("about 1.2M tokens", (1_200_000, None)),
            ("$3", (None, 3)),
            ("unknown", (None, None)),
            ("", (None, None)),
        ):
            with self.subTest(text=text):
                self.assertEqual(wh.parse_spend(text), expected)


class BuiltRepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.first = build_history(cls.root)
        add_records(cls.root)
        cls.report = wh.read_work_history(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_commits_and_specs(self):
        self.assertEqual(self.report["commits"]["unmarked"], 1)
        self.assertEqual(self.report["specs"], {"approved": 5})
        self.assertEqual(self.report["records"], 22)

    def test_decision_wait_is_the_hours_from_ready_to_approved_at(self):
        wait = self.report["baselines"]["decision_wait"]
        self.assertEqual((wait["value"], wait["n"], wait["enough"]), (2.0, 5, True))

    def test_decisions_per_change_counts_the_decisions_that_name_a_spec(self):
        decisions = self.report["baselines"]["decisions_per_change"]
        self.assertEqual((decisions["value"], decisions["n"]), (2.0, 5))
        self.assertIn("1 of 11 decisions name no such Spec", decisions["says"])

    def test_suite_runs_per_head_counts_only_reported_workflow_runs(self):
        runs = self.report["baselines"]["suite_runs_per_head"]
        self.assertEqual((runs["value"], runs["n"], runs["most"]), (2.0, 5, 2))

    def test_flow_efficiency_is_the_share_of_the_span_in_short_gaps(self):
        flow = self.report["baselines"]["flow_efficiency"]
        # Four Specs never idle (1.0). SPEC-1 spans 17 h and idles 11 h before its last commit: 6 / 17. The median is 1.0.
        self.assertEqual((flow["value"], flow["n"]), (1.0, 5))
        times = [0, 1, 3, 4, 5, 6, 17]
        self.assertAlmostEqual(wh._efficiency([int(h * 3600) for h in times]), 6 / 17)

    def test_steps_count_the_verify_rejections_and_rework_by_harness_and_model(self):
        steps = {(r["step"], r["harness"], r["model"]): r for r in self.report["steps"]}
        first = steps[("first", "claude-code", "model-a")]
        self.assertEqual((first["notes"], first["rejected_at_verify"], first["rejected_at_verify_share"], first["tokens"]), (5, 2, 0.4, 60000))
        self.assertIsNone(first["sent_back_share"], "a step that does not check has no sent-back share")
        verifier = steps[("verifier", "codex", "model-b")]
        self.assertEqual(
            (verifier["notes"], verifier["sent_back"], verifier["sent_back_share"], verifier["cost_dollars"], verifier["spend_noted"]), (7, 2, 0.286, 2.8, 7)
        )
        developer = steps[("developer", "claude-code", "model-a")]
        self.assertEqual((developer["notes"], developer["rework_loops"], developer["rejected_at_verify_share"]), (2, 2, None))
        self.assertEqual(developer["spend_noted"], 0)

    def test_the_text_says_where_the_data_is_too_thin(self):
        text = wh.work_history_text(self.report)
        self.assertIn("verifier / codex / model-b: 7 notes, sent back 2 of 7 (share 0.286)", text)
        self.assertIn("first / claude-code / model-a: 5 notes, handed to Verify and sent back 2 of 5 (share 0.4)", text)
        self.assertIn("developer / claude-code / model-a: 2 notes, handed to Verify and sent back 0 of 2 (too little data)", text)
        self.assertNotIn("too little data: 5 Specs", text)

    def test_the_text_says_whose_harness_and_model_a_step_shows(self):
        self.assertIn("usually the lead's, not the role's own", wh.work_history_text(self.report))

    def test_the_text_names_the_measures_in_plain_words_and_prints_no_backlog_id(self):
        text = wh.work_history_text(self.report)
        for label, _ in wh.LABELS.values():
            self.assertIn(label, text)
        for backlog_id in ("R10", "E3", "R329", "R330", "E8"):
            self.assertNotIn(backlog_id, text)

    def test_the_reader_and_aidd_trace_agree_on_the_ids_and_the_agent_of_each_commit(self):
        traced = workitems.trace(self.root, None, "SPEC-1")["commits"]
        by_sha = {c.sha: c for c in wh._read_commits(self.root)[0]}
        self.assertTrue(traced)
        for entry in traced:
            commit_ = by_sha[entry["sha"]]
            harness, _, model = entry["assisted_by"][0].partition("/") if entry["assisted_by"] else (wh.UNMARKED, "", wh.UNMARKED)
            self.assertEqual((commit_.harness, commit_.model), (harness, model))
            self.assertEqual(entry["work_ids"], workitems.work_ids_in(commit_.message, {f"SPEC-{n}" for n in range(1, 6)}))
            self.assertIn("SPEC-1", entry["work_ids"])


class NoteWriterTests(unittest.TestCase):
    def test_a_note_s_by_names_its_step_s_harness_and_model_over_the_commit_that_posted_it(self):
        for by, expected in (
            ("agent:codex/model-b", ("codex", "model-b")),
            ("agent:Claude Code/model-c", ("claude-code", "model-c")),
            ("@pat", (wh.PERSON, "@pat")),  # a person wrote it: never the commit's agent
            (None, ("claude-code", "lead-model")),
        ):
            with self.subTest(by=by), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                git(root, "init", "-q", "-b", "main")
                write_spec(root, 1, "approved", ("dev one", "verifier", "1k tokens"), 3)
                path = root / "specs" / "SPEC-1.md"
                if by:
                    path.write_text(path.read_text(encoding="utf-8").replace("stopped_at: none\n", f'stopped_at: none\nby: "{by}"\n'), encoding="utf-8")
                commit(root, 0, "SPEC-1: hand off", "claude-code/lead-model")
                report = wh.read_work_history(root)
                (step,) = report["steps"]
                self.assertEqual((step["harness"], step["model"]), expected)
                self.assertEqual(report["notes_named_by"], {"named": int(bool(by)), "notes": 1})

    def test_a_by_that_holds_terminal_controls_reaches_no_output_with_them(self):
        """A note's `by` is repository text: an escape, a bidi override, or a line break in it never reaches the reading
        or a validate warning."""
        unsafe = ("\x1b", "\u202e", "\n", "\r", "\x07")
        for by in (
            "agent:claude-code/model\\u001b[2J",
            "agent:Claude\\u202eCode/model",
            "agent:claude-code/model\\nAssisted-by: x/y",
            "agent:claude code\\u001b]0;title\\u0007/model\\u202e\\r",
            "Pat \\u202eLee\\u001b[2J\\u0007",  # a person's `by`: the schema's own error quotes it
        ):
            with self.subTest(by=by), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                git(root, "init", "-q", "-b", "main")
                write_spec(root, 1, "approved", ("dev one", "verifier", "1k tokens"), 3)
                path = root / "specs" / "SPEC-1.md"
                path.write_text(path.read_text(encoding="utf-8").replace("stopped_at: none\n", f'stopped_at: none\nby: "{by}"\n'), encoding="utf-8")
                commit(root, 0, "SPEC-1: hand off")
                report = wh.read_work_history(root)
                warned = handoff_notes.handoff_warnings("specs/SPEC-1.md", path.read_text(encoding="utf-8"))
                self.assertTrue(any("by" in w for w in warned), warned)
                (step,) = report["steps"]
                # Each value `by` gives is one clean line, so the reading's lines and the warnings hold none of them.
                for text in (step["harness"], step["model"], *warned):
                    self.assertFalse([c for c in unsafe if c in text], repr(text))
                lines = wh.work_history_text(report).splitlines()
                self.assertFalse([c for c in unsafe[:2] + unsafe[3:] if any(c in ln for ln in lines)])
                self.assertFalse([ln for ln in lines if ln.startswith("Assisted-by")], lines)

    def test_a_schema_error_and_an_assisted_by_warning_quote_repository_text_with_no_control_in_it(self):
        bad = "a \u202eb\x1b[2J\x07"
        found = [
            *json_schema.validate({"done": "x", "next": "verifier", "needs": "none", "stopped_at": "none", "by": bad}, "handoff.schema.json"),
            *validation.validate(Path("specs/SPEC-1.md"), "", {"type": "spec", "id": "SPEC-1", "assisted_by": [bad, "Claude\u202eCode/m\x1b"]}, None),
        ]
        self.assertTrue([w for w in found if "assisted_by" in w] and [w for w in found if "$.by" in w], found)
        for text in found:
            self.assertFalse([c for c in ("\x1b", "\u202e", "\x07", "\n") if c in text], repr(text))
        self.assertIn("é", json_schema._fmt("é\u202e"), "a printable letter stays readable")
        keys = handoff_notes.handoff_warnings(
            "specs/SPEC-1.md", '```aidd-handoff\ndone: x\nnext: verifier\nneeds: none\nstopped_at: none\n"k\\u202ey\\u001b": 1\n```\n'
        )
        self.assertTrue([w for w in keys if "does not read" in w], keys)
        for text in keys:
            self.assertFalse([c for c in ("\x1b", "\u202e") if c in text], repr(text))

    def test_a_commit_in_an_encoding_python_cannot_replace_is_read_and_stops_nothing(self):
        raw = b"tree 0\nencoding idna\n\nfix\n\nAssisted-by: Claude Code/m\n"
        self.assertEqual(workitems.assisted_by_values(git_kernel.commit_message(raw)), ["Claude Code/m"])
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q", "-b", "main")
            commit(root, 0, "first")
            git(root, "checkout", "-q", "-b", "feat")
            git(root, *IDENT, "-c", "i18n.commitEncoding=idna", "commit", "-q", "--allow-empty", "-m", "odd\n\nAssisted-by: codex")
            commit(root, 1, "next", "Claude Code/m")
            self.assertEqual(wh.read_work_history(root)["commits"]["count"], 3)
            self.assertEqual(len(commit_text.branch_assisted_by_warnings(root)), 2, "each wrong value, the idna commit's too")


class TimesAndCapsTests(unittest.TestCase):
    def test_a_commit_keeps_its_author_time_when_a_rebase_moves_the_committer_time(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q", "-b", "main")
            commit(root, 1, "first", committed_hours=500)
            (only,) = wh._read_commits(root)[0]
            self.assertEqual(only.at, int((BASE + dt.timedelta(hours=1)).timestamp()))

    def test_a_revised_spec_waits_from_its_newest_ready_commit_before_the_approval(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q", "-b", "main")
            for status, hours, approved in (
                ("draft", 0, None),
                ("ready", 1, None),
                ("approved", 2, 2),
                ("draft", 50, None),
                ("ready", 51, None),
                ("approved", 53, 53),
            ):
                write_spec(root, 1, status, approved_hours=approved)
                commit(root, hours, f"SPEC-1: {status}")
            approved = int((BASE + dt.timedelta(hours=53)).timestamp())
            self.assertEqual(wh._ready_before(root, "specs/SPEC-1.md", approved), int((BASE + dt.timedelta(hours=51)).timestamp()))
            self.assertEqual(wh._approved_at(root, "specs/SPEC-1.md"), approved)

    def test_a_spec_with_more_versions_than_the_cap_reads_the_newest_and_says_so(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q", "-b", "main")
            for n in range(5):
                write_spec(root, 1, "approved", (f"note {n}", "verifier", "1k tokens"), 3)
                commit(root, n, f"SPEC-1: note {n}")
            with mock.patch.object(wh, "MAX_VERSIONS", 3):
                report = wh.read_work_history(root)
                text = wh.work_history_text(report)
            self.assertEqual(report["capped_specs"], 1)
            self.assertEqual(sum(r["notes"] for r in report["steps"]), 3, "the newest three versions hold the newest three notes")
            self.assertIn("only the newest 3 were read", text)


def stalled_spec(n: int, status: str = "draft", *, tests: bool = False, todo_body: bool = True, scope: str | None = None) -> str:
    """A Spec at one step: a TODO body is a stub, a clean body is filled, test commands are written tests."""
    scope = scope or f"src/s{n}/**"
    commands = "tests:\n  commands:\n    - name: t\n      command: [python3, -m, unittest]\n      covers: [A1]\n" if tests else ""
    body = "## Design\n\nTODO\n" if todo_body else "## Design\n\nDone.\n"
    return (
        f'---\naidd_version: "1.0.0"\ntype: spec\nid: SPEC-{n}\ntitle: t\nstatus: {status}\n'
        f'tasks:\n  - id: T1\n    title: t\n    scope: ["{scope}"]\n{commands}---\n\n{body}'
    )


class StallTests(unittest.TestCase):
    """R385 fix 5: Specs by furthest point across every branch, with the days since the last commit in scope."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        git(self.root, "init", "-q", "-b", "main")
        (self.root / ".aidd").mkdir()
        (self.root / ".aidd" / "config.yaml").write_text('aidd_version: "1.0.0"\nprofile: solo\n', encoding="utf-8")
        (self.root / "specs").mkdir()

    def branch(self, name: str, n: int, text: str) -> None:
        git(self.root, "checkout", "-q", "-b", name)
        (self.root / "specs" / f"SPEC-{n}.md").write_text(text, encoding="utf-8")
        (self.root / f"src_s{n}.txt").write_text("x", encoding="utf-8")
        commit(self.root, 0, f"SPEC-{n}: work")
        git(self.root, "checkout", "-q", "main")

    def test_each_spec_lands_at_its_furthest_point_across_branches_and_the_scope_age_shows(self):
        for n in (1, 2, 3):  # on main: three stubs
            (self.root / "specs" / f"SPEC-{n}.md").write_text(stalled_spec(n), encoding="utf-8")
        (self.root / "src" / "s1").mkdir(parents=True)
        (self.root / "src" / "s1" / "a.py").write_text("x = 1\n", encoding="utf-8")
        commit(self.root, 0, "SPEC-1: code")
        self.branch("spec/SPEC-2", 2, stalled_spec(2, todo_body=False))  # SPEC-2 is filled on its branch
        self.branch("spec/SPEC-4", 4, stalled_spec(4, tests=True, todo_body=False))
        self.branch("spec/SPEC-5", 5, stalled_spec(5, "ready", tests=True, todo_body=False))
        self.branch("spec/SPEC-6", 6, stalled_spec(6, "in_progress", tests=True, todo_body=False))
        stall = wh.work_stall.read_stall(self.root, today=(BASE + dt.timedelta(days=10)).date())
        self.assertEqual(stall["progress"], {"outline": 2, "filled": 1, "tests written": 1, "ready": 1, "approved": 1})
        rows = {s["id"]: s for s in stall["specs"]}
        self.assertEqual((rows["SPEC-1"]["progress"], rows["SPEC-2"]["progress"], rows["SPEC-6"]["progress"]), ("outline", "filled", "approved"))
        self.assertEqual(rows["SPEC-1"]["days_since_scope_commit"], 10)
        self.assertEqual(stall["days_since_last_scope_commit"], 10)

    def test_the_text_names_the_histogram_and_the_report_carries_it(self):
        (self.root / "specs" / "SPEC-1.md").write_text(stalled_spec(1), encoding="utf-8")
        for n in range(2, 5):
            text = stalled_spec(n).replace("status: draft\n", "status: draft\nrelations: [{type: blocked_by, id: SPEC-1}]\n")
            (self.root / "specs" / f"SPEC-{n}.md").write_text(text, encoding="utf-8")
        commit(self.root, 0, "plan")
        report = wh.read_work_history(self.root)
        text = wh.work_history_text(report)
        self.assertIn("Stall: Specs by furthest point across every worktree and branch: outline 4, filled 0, tests written 0, ready 0, approved 0", text)
        self.assertEqual((report["stall"]["no_holder"], report["stall"]["open_specs"]), (0, 4), "a blocked_by Spec keeps its agent step")

    def test_a_draft_that_validates_clean_is_counted_and_a_stub_is_not(self):
        (self.root / "specs" / "SPEC-1.md").write_text(SAMPLE_SPEC.replace("SPEC-220", "SPEC-1"), encoding="utf-8")
        (self.root / "specs" / "SPEC-2.md").write_text(stalled_spec(2), encoding="utf-8")
        (self.root / "tests").mkdir()
        (self.root / "tests" / "test_discount.py").write_text("", encoding="utf-8")  # the sample Spec lists it
        commit(self.root, 0, "plan")
        stall = wh.work_stall.read_stall(self.root)
        self.assertEqual((stall["drafts"], stall["drafts_valid"]), (2, 1))
        self.assertEqual((stall["progress"]["tests written"], stall["progress"]["outline"]), (1, 1))

    def test_a_read_error_is_reported_and_never_shown_as_zero_counts(self):
        with mock.patch("aidd.workitems.all_branches.all_branches_work", side_effect=ValueError("a Spec folder could not be read")):
            report = wh.read_work_history(self.root)
        self.assertIn("could not be read", report["stall"]["error"])
        text = wh.work_history_text(report)
        self.assertIn("Stall: not read (a Spec folder could not be read)", text)
        self.assertNotIn("stub 0", text)


class RevertsAndThinHistoryTests(unittest.TestCase):
    def test_a_reverted_commit_counts_against_the_model_that_made_it(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q", "-b", "main")
            shas = [commit(root, h, f"change {h}") for h in range(5)]
            commit(root, 6, f'Revert "change 0"\n\nThis reverts commit {shas[0]}.', "codex/model-b")
            rows = {(r["harness"], r["model"]): r for r in wh.model_rows(wh._read_commits(root)[0])}
            self.assertEqual((rows[("claude-code", "model-a")]["commits"], rows[("claude-code", "model-a")]["reverted"]), (5, 1))
            self.assertEqual(rows[("claude-code", "model-a")]["revert_rate"], 0.2)
            self.assertIsNone(rows[("codex", "model-b")]["revert_rate"])

    def test_a_thin_repository_and_a_folder_with_no_git_say_too_little_data_and_do_not_fail(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            plain = wh.read_work_history(root)
            self.assertEqual(plain["commits"]["count"], 0)
            git(root, "init", "-q", "-b", "main")
            commit(root, 0, "only commit")
            thin = wh.read_work_history(root)
        for report in (plain, thin):
            self.assertTrue(all(not m["enough"] and m["value"] is None for m in report["baselines"].values()))
            self.assertIn("too little data", wh.work_history_text(report))
        self.assertIn("no Spec holds a handoff note", wh.work_history_text(thin))
        self.assertIn("1 commit (", wh.work_history_text(thin))


class CommandTests(unittest.TestCase):
    def test_aidd_eval_work_prints_the_reading_as_text_and_as_json(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q", "-b", "main")
            commit(root, 0, "only commit")
            code, text = run_cli("eval", "work", "--root", str(root))
            self.assertEqual(code, 0)
            self.assertIn("Baselines, each marked", text)
            code, raw = run_cli("eval", "work", "--root", str(root), "--json")
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(raw)["commits"]["count"], 1)

    def test_run_from_a_folder_inside_the_repository_it_reads_the_whole_repository(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q", "-b", "main")
            write_spec(root, 1, "draft")
            commit(root, 0, "SPEC-1: write the spec")
            (root / "src" / "deep").mkdir(parents=True)
            with contextlib.chdir(root / "src" / "deep"):
                code, here = run_cli("eval", "work")
            code_root, named = run_cli("eval", "work", "--root", str(root / "src"))
            self.assertEqual((code, code_root), (0, 0))
            for text in (here, named):
                self.assertIn("Specs: 1 draft", text)
                self.assertIn(f"{root.name}: 1 commit", text)

    def test_aidd_eval_work_takes_no_files(self):
        code, text = run_cli("eval", "work", "somefile.jsonl")
        self.assertNotEqual(code, 0)
        self.assertIn("unexpected arguments", text)


if __name__ == "__main__":
    unittest.main()
