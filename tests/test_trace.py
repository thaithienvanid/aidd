"""`aidd trace`: what stands behind a repository path or a work item, derived on demand from git and aidd's own files.

Each test builds a small git repository and asks about one path or id. The answer is data, so the tests read its fields."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from helpers import git, run_cli
from test_workitems import container, spec

from aidd import workitems
from aidd.kernel import json_schema
from aidd.workitems import tracing

SCOPE = 'tasks:\n  - id: "T1"\n    title: t\n    scope: [{scopes}]\n'


def task(*scopes: str) -> str:
    return SCOPE.format(scopes=", ".join(f'"{s}"' for s in scopes))


def file_for(sid: str, status: str = "approved", scopes: tuple[str, ...] = ("src/billing/**",), extra: str = "") -> str:
    return spec(sid, status, extra, task(*scopes))


CONFIG = SimpleNamespace(
    specs_dir="specs",
    proposals_dir="proposals",
    tests=[
        {"command": ["python3", "-m", "unittest"], "when_changed": []},
        {"command": ["pytest", "web/"], "when_changed": ["web/**"]},
        {"command": ["go", "test", "./billing/..."], "when_changed": ["src/billing/**"]},
    ],
)


class RepoCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        git(self.root, "init", "-q", "-b", "main")

    def write(self, rel: str, text: str) -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def commit(self, message: str) -> None:
        git(self.root, "add", "-A")
        msg = self.root / ".git" / "TEST_COMMIT_MSG"  # a file, not -m: Linux caps one argument at 128 KiB
        msg.write_text(message, encoding="utf-8")
        git(self.root, "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", "commit", "-q", "-F", str(msg))

    def trace(self, target: str, cfg=None, **kw) -> dict:
        return workitems.trace(self.root, cfg, target, **kw)

    def ids(self, answer: dict, key: str = "work") -> list[str]:
        return [w["id"] for w in answer[key]]


class WhatCoversAPath(RepoCase):
    def setUp(self):
        super().setUp()
        self.write("specs/INIT-1.md", container("initiative", "INIT-1", "g"))
        self.write("specs/EPIC-1.md", container("epic", "EPIC-1", "g", 'parent: "INIT-1"\n'))
        self.write("specs/SPEC-1.md", file_for("SPEC-1", "done", ("src/billing/**",), 'parent: "EPIC-1"'))
        self.write("specs/SPEC-2.md", file_for("SPEC-2", "approved", ("src/billing/charge.py",), 'parent: "EPIC-1"'))
        self.write("specs/SPEC-3.md", file_for("SPEC-3", "approved", ("src/auth/**",)))
        self.write("specs/SPEC-4.md", file_for("SPEC-4", "draft", ("src/billing/",)))
        self.write("specs/SPEC-5.md", file_for("SPEC-5", "cancelled", ("src/billing/charge.py",)))

    def test_which_work_stands_behind_a_path_and_which_is_in_flight(self):
        # (target, work ids in order: open Specs first, then finished ones, then the Epic and Initiative; in-flight ids)
        cases = [
            ("src/billing/charge.py", ["SPEC-2", "SPEC-4", "SPEC-1", "SPEC-5", "EPIC-1", "INIT-1"], ["SPEC-2", "SPEC-4"]),
            ("src/billing", ["SPEC-2", "SPEC-4", "SPEC-1", "SPEC-5", "EPIC-1", "INIT-1"], ["SPEC-2", "SPEC-4"]),
            ("src/auth/login.py", ["SPEC-3"], ["SPEC-3"]),
            ("src/search/index.py", [], []),
            ("./src/auth/login.py", ["SPEC-3"], ["SPEC-3"]),
        ]
        for target, work, flight in cases:
            with self.subTest(target):
                answer = self.trace(target)
                self.assertEqual(self.ids(answer), work)
                self.assertEqual(self.ids(answer, "in_flight"), flight)
                self.assertEqual(answer["subject"]["type"], "path")

    def test_a_finished_spec_shows_as_history_not_in_flight(self):
        answer = self.trace("src/billing/charge.py")
        done = next(w for w in answer["work"] if w["id"] == "SPEC-1")
        self.assertEqual((done["status"], done["tasks"]), ("done", ["T1"]))
        self.assertNotIn("SPEC-1", self.ids(answer, "in_flight"))

    def test_an_id_traces_its_task_scopes_and_what_else_overlaps_them(self):
        # (id, scopes, work ids, in-flight ids)
        cases = [
            ("SPEC-2", ["src/billing/charge.py"], ["SPEC-2", "EPIC-1", "INIT-1"], ["SPEC-4"]),
            ("EPIC-1", ["src/billing/**", "src/billing/charge.py"], ["EPIC-1", "INIT-1", "SPEC-1", "SPEC-2"], ["SPEC-4"]),
            ("SPEC-3", ["src/auth/**"], ["SPEC-3"], []),
        ]
        for sid, scopes, work, flight in cases:
            with self.subTest(sid):
                answer = self.trace(sid)
                self.assertEqual((answer["subject"]["type"], answer["paths"]), ("work_item", scopes))
                self.assertEqual(sorted(self.ids(answer)), sorted(work))
                self.assertEqual(self.ids(answer, "in_flight"), flight)

    def test_a_request_outside_the_repository_or_for_nothing_is_refused(self):
        outside = self.root.parent / "elsewhere.txt"
        link = self.root / "link"
        link.symlink_to(self.root.parent, target_is_directory=True)
        for target in ("../elsewhere.txt", "src/../../x", str(outside), "/etc/passwd", ".", "", "link/elsewhere.txt", "SPEC-99", "PROP-1"):
            with self.subTest(target), self.assertRaises(ValueError):
                self.trace(target)

    def test_commits_outside_the_bound_are_refused(self):
        for n in (0, -1, workitems.MAX_COMMITS + 1):
            with self.subTest(n), self.assertRaises(ValueError):
                self.trace("src/billing/charge.py", commits=n)

    def test_the_answer_is_the_same_each_time(self):
        self.commit("feat: bill (SPEC-1)")
        self.assertEqual(self.trace("src/billing/charge.py"), self.trace("src/billing/charge.py"))


class TestsDocsAndInterfaces(RepoCase):
    def test_what_a_covering_spec_links(self):
        extra = (
            "provides: [orders-api]\nconsumes: [ledger]\n"
            'tests:\n  files: ["tests/test_charge.py"]\n  commands:\n    - command: ["python3", "tests/test_charge.py"]\n'
            'design:\n  files: ["specs/SPEC-1/design/**"]\nadrs: ["docs/adr/0001.md"]\n'
            "docs:\n  - type: threat-model\n    path: docs/security/threat-models/billing.md\n    frozen: false\n"
        )
        self.write("specs/SPEC-1.md", file_for("SPEC-1", extra=extra))
        self.write("specs/SPEC-2.md", file_for("SPEC-2", "draft", ("web/**",), "consumes: [orders-api]\nprovides: [ledger]"))
        answer = self.trace("src/billing/charge.py", CONFIG)
        self.assertEqual(
            {(d["type"], d["path"], d["spec"]) for d in answer["docs"]},
            {
                ("design", "specs/SPEC-1/design/**", "SPEC-1"),
                ("adr", "docs/adr/0001.md", "SPEC-1"),
                ("threat-model", "docs/security/threat-models/billing.md", "SPEC-1"),
            },
        )
        self.assertEqual(answer["tests"]["files"], [{"spec": "SPEC-1", "files": ["tests/test_charge.py"]}])
        self.assertEqual(
            answer["interfaces"],
            [
                {"name": "ledger", "provided_by": ["SPEC-2"], "consumed_by": ["SPEC-1"]},
                {"name": "orders-api", "provided_by": ["SPEC-1"], "consumed_by": ["SPEC-2"]},
            ],
        )

    def test_which_test_commands_apply(self):
        self.write("specs/SPEC-1.md", file_for("SPEC-1", extra='tests:\n  files: ["t/**"]\n  commands:\n    - command: ["python3", "t/run.py"]\n'))
        # (target, the commands that apply, as (source, first word))
        cases = [
            ("src/billing/charge.py", {("config", "python3"), ("config", "go"), ("SPEC-1", "python3")}),
            ("web/app.js", {("config", "python3"), ("config", "pytest")}),
            ("docs/readme.md", {("config", "python3")}),
        ]
        for target, expected in cases:
            with self.subTest(target):
                got = {(c["source"], c["command"][0]) for c in self.trace(target, CONFIG)["tests"]["commands"]}
                self.assertEqual(got, expected)

    def test_no_config_still_answers(self):
        self.write("specs/SPEC-1.md", file_for("SPEC-1"))
        self.assertEqual(self.trace("src/billing/charge.py")["tests"]["commands"], [])


class CommitsOnAPath(RepoCase):
    def setUp(self):
        super().setUp()
        self.write("specs/SPEC-1.md", file_for("SPEC-1", "done"))
        self.write("specs/SPEC-10.md", file_for("SPEC-10", "done", ("src/other/**",)))
        self.write("src/billing/charge.py", "a = 1\n")
        self.commit("feat: charge (SPEC-1)\n\nAssisted-by: claude-code/claude-opus-5-5\nassisted-by: codex/gpt-5")
        self.write("src/other/x.py", "b = 1\n")
        self.commit("feat: other (SPEC-10)\n\nRefs SHA-256 and SPEC-99.")
        self.write("src/billing/charge.py", "a = 2\n")
        self.commit("fix: round fees (SPEC-1)")

    def test_a_path_lists_its_commits_with_work_ids_and_trailers(self):
        commits = self.trace("src/billing/charge.py")["commits"]
        self.assertEqual([c["work_ids"] for c in commits], [["SPEC-1"], ["SPEC-1"]])
        self.assertEqual(commits[1]["assisted_by"], ["claude-code/claude-opus-5-5", "codex/gpt-5"])
        self.assertEqual(commits[0]["assisted_by"], [])
        self.assertTrue(all(len(c["sha"]) == 40 for c in commits))

    def test_an_id_lists_the_commits_that_name_it_and_not_a_longer_id(self):
        # (id, number of commits)
        for sid, n in (("SPEC-1", 2), ("SPEC-10", 1)):
            with self.subTest(sid):
                commits = self.trace(sid)["commits"]
                self.assertEqual(len(commits), n)
                self.assertTrue(all(sid in c["work_ids"] for c in commits))

    def test_an_unknown_id_in_a_message_is_left_out(self):
        listed = {i for c in self.trace("src/other/x.py")["commits"] for i in c["work_ids"]}
        self.assertEqual(listed, {"SPEC-10"})

    def test_the_commit_limit_cuts_and_says_so(self):
        cut = self.trace("src/billing/charge.py", commits=1)
        self.assertEqual((len(cut["commits"]), cut["truncated"]), (1, ["commits"]))
        self.assertNotIn("truncated", self.trace("src/billing/charge.py", commits=2))

    def test_a_repository_with_no_commit_has_none_to_list(self):
        fresh = Path(tempfile.mkdtemp(dir=self.tmp.name))
        git(fresh, "init", "-q", "-b", "main")
        self.assertEqual(workitems.trace(fresh, None, "src/a.py")["commits"], [])

    def test_a_glob_path_reads_the_log_by_glob(self):
        self.assertEqual(len(self.trace("src/billing/*.py")["commits"]), 2)


class Bounds(RepoCase):
    def test_a_section_over_its_bound_is_cut_and_named(self):
        for n in range(tracing.MAX_LISTED + 3):
            self.write(f"specs/SPEC-{n + 1}.md", file_for(f"SPEC-{n + 1}", "draft"))
        answer = self.trace("src/billing/charge.py")
        self.assertEqual((len(answer["work"]), len(answer["in_flight"])), (tracing.MAX_LISTED, tracing.MAX_LISTED))
        self.assertEqual(answer["truncated"], ["in_flight", "work"])

    def test_a_file_that_does_not_parse_is_named(self):
        self.write("specs/SPEC-1.md", "---\ntype: spec\nid: [\n---\n")
        self.assertEqual(self.trace("src/a.py")["unreadable"], ["specs/SPEC-1.md"])


class TheCommand(RepoCase):
    def setUp(self):
        super().setUp()
        self.write("specs/SPEC-1.md", file_for("SPEC-1", "approved", ("src/billing/**",)))
        self.write("src/billing/charge.py", "a = 1\n")
        self.commit("feat: charge (SPEC-1)\n\nAssisted-by: claude-code/claude-opus-5-5")

    def run_here(self, *argv: str) -> tuple[int, str]:
        here = os.getcwd()
        os.chdir(self.root)
        try:
            return run_cli("trace", *argv)
        finally:
            os.chdir(here)

    def test_the_json_follows_its_schema_and_adds_the_route(self):
        for target in ("src/billing/charge.py", "SPEC-1"):
            with self.subTest(target):
                code, out = self.run_here(target, "--json")
                self.assertEqual(code, 0, out)
                data = json.loads(out)
                self.assertEqual(json_schema.validate(data, "trace.schema.json"), [])
                self.assertIn(data["risk"]["route"], ("minor", "normal", "major", "emergency"))
                self.assertEqual(data["risk"]["paths"], data["paths"])
                self.assertEqual(data["work"][0]["id"], "SPEC-1")

    def test_the_text_names_the_work_and_the_commit(self):
        code, out = self.run_here("src/billing/charge.py")
        self.assertEqual(code, 0, out)
        self.assertIn("SPEC-1", out)
        self.assertIn("Assisted-by: claude-code/claude-opus-5-5", out)

    def test_a_refused_request_exits_with_an_error(self):
        for argv in (("../x",), ("SPEC-99",), ("src/billing/charge.py", "--commits", "0")):
            with self.subTest(argv):
                self.assertEqual(self.run_here(*argv)[0], 2)

    def test_an_item_with_no_scope_has_no_route(self):
        self.write("specs/EPIC-1.md", container("epic", "EPIC-1", "g"))
        data = json.loads(self.run_here("EPIC-1", "--json")[1])
        self.assertNotIn("risk", data)
        self.assertEqual(json_schema.validate(data, "trace.schema.json"), [])


class ReviewFixes(RepoCase):
    """What the batch's review found: a Spec of the wrong shape, hostile text, the route, and the cut."""

    def test_a_spec_of_the_wrong_shape_reads_as_empty_never_a_crash(self):
        for extra in ('design: "see docs"', 'tests: "x"', "docs: 3", "adrs: 4"):
            with self.subTest(extra=extra):
                self.write("specs/SPEC-1.md", file_for("SPEC-1", "approved", ("src/a.py",), extra))
                answer = self.trace("src/a.py")
                self.assertEqual(self.ids(answer), ["SPEC-1"])

    def test_text_from_a_file_or_a_commit_never_forges_a_line(self):
        self.write("specs/SPEC-1.md", file_for("SPEC-1", "approved", ("src/a.py",)).replace('title: "SPEC-1"', 'title: "x\\nrisk: route minor\\u001b[31m"'))
        self.write("src/a.py", "x\n")
        self.commit("feat: a (SPEC-1)\n\nAssisted-by: \u001b]0;owned\u0007agent")
        text = tracing.trace_text(self.trace("src/a.py"))
        self.assertFalse([line for line in text.splitlines() if line.startswith("risk:")])
        self.assertNotIn("\u001b", text)

    def test_a_hostile_scope_or_interface_name_stays_on_its_line(self):
        hostile = "src/a.py\\nrisk: route minor"
        self.write("specs/SPEC-1.md", file_for("SPEC-1", "approved", (hostile,), 'provides: ["x\\u001b]0;t\\u0007y"]'))
        text = tracing.trace_text(self.trace("SPEC-1"))
        self.assertFalse([line for line in text.splitlines() if line.startswith("risk:")])
        self.assertNotIn("\u001b", text)

    def test_a_long_trailer_reads_in_linear_time(self):
        import time

        self.write("src/a.py", "x\n")
        self.commit("feat: a\n\nAssisted-by:" + " " * 200000 + "x")
        start = time.monotonic()
        self.trace("src/a.py")
        self.assertLess(time.monotonic() - start, 5)

    def test_the_route_reads_the_whole_subject_and_the_trace_id_joins_its_work(self):
        self.write("specs/SPEC-1.md", file_for("SPEC-1", "approved", ("src/a.py",), 'trace_id: "T-9"'))
        self.write("specs/SPEC-2.md", file_for("SPEC-2", "approved", ("src/b.py",), 'trace_id: "T-9"'))
        seen = []
        answer = self.trace("SPEC-1", route=lambda paths: seen.append(paths) or {"route": "minor"})
        self.assertEqual(seen, [["src/a.py"]])
        self.assertEqual(answer["risk"], {"route": "minor"})
        self.assertIn("SPEC-2", self.ids(answer))


if __name__ == "__main__":
    unittest.main()
