"""Local gate events: a local `aidd gate` run and an `aidd land` run keep their decision as one gate event in the git
directory (INIT-1's first measure; CHANGELOG 1.0.0).

The write side, on real temporary git repositories and real files (hard links, symbolic links, a `\\xff` byte, a read-only
folder, a held `.lock`). The tests name the Acceptance ids they were written for (A1, A3 to A9, A11); the read side (A2,
A10) is tests/test_local_gate_events_read.py. A test of a refused store compares the gate's exit code and stdout with a
run that has no store, and counts the one warning on stderr.

Cases that need hard links, symbolic links, file modes, or a user who is not root are POSIX only.
"""

import contextlib
import io
import json
import os
import re
import shutil
import stat
import unittest
from pathlib import Path
from unittest import mock

from helpers import MCP_LEGACY_INITIALIZE, ROOT, RepoTemplateCase, git
from test_flows import FIX, _commit, as_person, shop

from aidd import gate
from aidd.autopilot import lease, store
from aidd.cli import app, mcp_server
from aidd.evals import examples
from aidd.kernel import git as gitutil
from aidd.kernel import json_schema

KEPT = "the gate event was not kept"
CAP = 8 * 1024 * 1024  # the writer's size cap: it skips a file over this many bytes
POSIX = unittest.skipUnless(os.name == "posix" and os.geteuid() != 0, "needs POSIX links and file modes, and a user who is not root")
SECOND_FIX = "def total(items):\n    return sum(i for i in items if i)\n"


def cli(root, *argv: str) -> tuple[int, str, str]:
    """`aidd <argv>` in this process from `root`: its exit code, stdout, and stderr, kept apart."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.chdir(root), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = app.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def gate_run(root, *extra: str) -> tuple[int, str, str]:
    """`aidd gate --base main <extra>` in this process from `root`, inside git.memo(): a read-only git query the gate
    asks twice runs once. The gate writes nothing to git (its event goes to a file), so its answer is the same; only the
    time it takes changes."""
    with gitutil.memo():
        return cli(root, "gate", "--base", "main", *extra)


def described_fix(root: Path, branch: str, body: str) -> None:
    """A branch off main with one fast-lane commit that carries its Change Request block: the gate waits for Merge approval."""
    git(root, "switch", "-q", "main")
    git(root, "switch", "-qc", branch)
    _commit(root, f"fix(cart): skip empty items on {branch}\n\nAssisted-by: claude-code/claude-opus-5-5", {"app/cart.py": body})
    code, out, err = cli(root, "describe", "--commit", "--base", "main")
    assert code == 0, out + err


def gate_lines(path: Path) -> list[dict]:
    """The gate lines of an events file: every line that is not an autopilot run line."""
    if not path.is_file():
        return []
    lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [x for x in lines if x.get("kind", "gate") == "gate" and "run" not in x]


def only(lines: list[dict]) -> dict:
    """The one gate line a run left; an assertion failure, never an unpacking error, when there is none or more."""
    if len(lines) != 1:
        raise AssertionError(f"expected exactly one gate line, found {len(lines)}")
    return lines[0]


def warnings_in(err: str) -> list[str]:
    return [x for x in err.splitlines() if KEPT in x]


class Local(RepoTemplateCase):
    """A shop on main with two described fast-lane branches, `fix` (checked out) and `fix2`, and the gate's reference output."""

    @classmethod
    def build_template(cls, root):
        shop(root, "solo")
        described_fix(root, "fix2", SECOND_FIX)
        described_fix(root, "fix", FIX)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The same gate run with no store to write: the output every refused or forged store must leave unchanged.
        reference = cls._template.parent / "reference"
        shutil.copytree(cls._template, reference, symlinks=True)
        cls.reference = {extra: gate_run(reference, *extra)[:2] for extra in ((), ("--json",))}

    def setUp(self):
        super().setUp()
        self.store = self.root / ".git" / "aidd"
        self.events = self.store / "events.jsonl"
        self.outside = Path(self.tmp.name) / "outside"  # where the links point: never inside the store
        self.outside.mkdir()

    def gate(self, *extra: str, root=None) -> tuple[int, str, str]:
        return gate_run(root or self.root, *extra)

    def make_store(self) -> Path:
        self.store.mkdir(mode=0o700, exist_ok=True)
        return self.store

    def sentinel(self, text: bytes = b"sentinel: not an event\n") -> Path:
        path = self.outside / "sentinel.txt"
        path.write_bytes(text)
        return path

    def lock_down(self, folder: Path) -> None:
        os.chmod(folder, 0o500)
        self.addCleanup(os.chmod, folder, 0o700)  # runs before the temporary folder is removed

    def assert_unchanged_with_one_warning(self, got: tuple[int, str, str], extra: tuple = ()) -> None:
        """The gate said what it says with no store (exit code and stdout), and told the person once, on stderr."""
        code, out, err = got
        self.assertEqual((code, out), self.reference[extra])
        self.assertEqual(len(warnings_in(err)), 1, err)
        self.assertNotIn("Traceback", err)
        self.assertNotIn(KEPT, out)

    # A1: what the line holds

    def test_a_local_gate_run_leaves_one_valid_gate_line_and_no_tracked_change(self):  # A1
        status = git(self.root, "status", "--porcelain")
        self.assertEqual(gate_lines(self.events), [])
        code, out, err = self.gate("--json")
        self.assertEqual(code, 3, out + err)  # only the Merge approval is missing
        line = only(gate_lines(self.events))
        shown = json.loads(out)
        self.assertEqual((line["decision"], line["head_sha"]), (shown["decision"], shown["head_sha"]))
        self.assertIn(line.get("kind", "gate"), ("gate",))
        self.assertNotIn("run", line)
        self.assertIsNone(line["author"])
        self.assertIsNone(line["run_url"])
        self.assertIn(line["platform"], ("local", "preflight"))
        self.assertEqual(json_schema.validate(line, "event.schema.json"), [])
        self.assertEqual((line["change"], line["repo"]), ("fix", self.root.name))  # the branch, never HEAD; the folder of the git directory
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(os.stat(self.events).st_mode), 0o600)
        self.assertEqual(git(self.root, "status", "--porcelain"), status)
        self.assertEqual(warnings_in(err), [])

    def test_one_branch_run_in_two_worktrees_is_one_change_in_one_repository(self):  # A1
        self.assertEqual(self.gate()[0], 3)
        git(self.root, "switch", "-q", "main")
        other = Path(self.tmp.name) / "wt"
        git(self.root, "worktree", "add", "-q", str(other), "fix")
        self.assertTrue((other / ".git").is_file())  # a linked worktree: its git directory is the repository's
        self.assertEqual(self.gate(root=other)[0], 3)
        lines = gate_lines(self.events)
        self.assertEqual(len(lines), 2)
        self.assertEqual({(x["change"], x["repo"]) for x in lines}, {("fix", self.root.name)})

    def test_a_detached_head_names_the_change_by_its_commit(self):  # A1
        git(self.root, "switch", "-q", "--detach")
        head = git(self.root, "rev-parse", "HEAD")
        self.assertEqual(self.gate()[0], 3)
        line = only(gate_lines(self.events))
        self.assertNotEqual(line["change"], "HEAD")
        self.assertTrue(len(line["change"]) >= 7 and head.startswith(line["change"]), line["change"])

    @POSIX
    def test_a_branch_name_with_shell_syntax_is_written_as_data(self):  # A1 (abuse: a name a shell would run)
        name = "fix-$(touch${IFS}pwned);`id`|x"
        git(self.root, "branch", "-m", name)
        self.assertEqual(self.gate()[0], 3)
        line = only(gate_lines(self.events))
        self.assertEqual(line["change"], name)
        self.assertEqual(json_schema.validate(line, "event.schema.json"), [])
        self.assertFalse((self.root / "pwned").exists())

    def test_a_forecast_an_explanation_a_replay_and_an_explicit_events_file_write_no_local_event(self):  # A1 (assumption 6)
        context = self.outside / "context.json"
        context.write_text(json.dumps(examples.load_example(ROOT / "examples" / "02-normal-feature")[0]), encoding="utf-8")
        ci = self.root / "aidd-events.jsonl"
        runs = [
            ("gate", "--paths", "src/aidd/x.py"),
            ("gate", "--explain", "merge_approval"),
            ("gate", "--context", str(context)),
            ("gate", "--base", "main", "--events", str(ci)),
        ]
        for argv in runs:
            with self.subTest(argv=argv[1:]):
                code, out, err = cli(self.root, *argv)
                self.assertIn(code, (0, 3), out + err)
        self.assertFalse(self.events.exists())
        self.assertEqual(len(gate_lines(ci)), 1)  # `--events PATH` writes there, as today

    def test_a_gate_run_writes_to_one_file_only(self):  # A1, A2: no event is counted twice
        ci = self.root / "aidd-events.jsonl"
        ci.write_text('{"repo":"o/r","change":"7","ts":"2026-09-01T00:00:00Z","decision":"pass"}\n', encoding="utf-8")
        before = ci.read_bytes()
        self.assertEqual(self.gate()[0], 3)
        self.assertEqual(ci.read_bytes(), before)
        self.assertEqual(len(gate_lines(self.events)), 1)
        self.assertEqual(self.gate("--events", "aidd-events.jsonl")[0], 3)
        self.assertEqual(len(gate_lines(self.events)), 1)  # an explicit target replaces the default
        self.assertEqual(len(gate_lines(ci)), 2)

    # A2, end to end: what the gate wrote is what metrics reads

    def test_metrics_summarizes_the_gate_runs_of_two_branches_as_two_changes(self):  # A2
        self.assertEqual(self.gate()[0], 3)
        git(self.root, "switch", "-q", "fix2")
        self.assertEqual(self.gate()[0], 3)
        code, out, err = cli(self.root, "metrics", "--json")
        self.assertEqual(code, 0, out + err)
        summary = json.loads(out)
        self.assertEqual((summary["events"], summary["changes"]), (2, 2))  # one change named HEAD would be 1

    # A3: the gate's verdict and output

    def test_the_verdict_and_the_report_do_not_change_with_the_store_present_absent_or_unwritable(self):  # A3
        head = git(self.root, "rev-parse", "HEAD")
        forged = "".join(
            json.dumps(
                gate.event_header()
                | {"repo": self.root.name, "change": "fix", "ts": f"2026-10-15T0{n}:00:00Z", "decision": "pass", "route": "minor", "head_sha": head}
                | {"approvals": 5, "platform": "github", "failed_rules": [], "pending_rules": []}
            )
            + "\n"
            for n in (1, 2)
        )
        for extra in ((), ("--json",)):
            with self.subTest(extra=extra):
                shutil.rmtree(self.store, ignore_errors=True)
                code, out, err = self.gate(*extra)  # absent
                self.assertEqual((code, out), self.reference[extra])
                self.assertEqual(warnings_in(err), [])
                self.make_store()
                self.events.write_text(forged, encoding="utf-8")
                code, out, err = self.gate(*extra)  # present, with forged pass lines for this head
                self.assertEqual((code, out), self.reference[extra])
                self.assertEqual(warnings_in(err), [])
                kept = self.events.read_text(encoding="utf-8")
                self.assertTrue(kept.startswith(forged), "the forged lines stay as they were")
                self.assertEqual(len(kept.splitlines()), 3, "the run added its one line")
                self.assertEqual(json.loads(kept.splitlines()[-1])["decision"], "pending")
        if os.name == "posix" and os.geteuid() != 0:
            self.lock_down(self.store)
            for extra in ((), ("--json",)):
                with self.subTest(extra=extra, store="unwritable"):
                    code, out, _ = self.gate(*extra)
                    self.assertEqual((code, out), self.reference[extra])

    # A4 to A7: a store the writer refuses or cannot write

    @POSIX
    def test_a_hard_linked_events_file_is_refused_and_the_linked_file_is_untouched(self):  # A4
        sentinel = self.sentinel()
        self.make_store()
        os.link(sentinel, self.events)
        self.assert_unchanged_with_one_warning(self.gate())
        self.assertEqual(sentinel.read_bytes(), b"sentinel: not an event\n")
        self.assertEqual(os.stat(sentinel).st_nlink, 2)

    @POSIX
    def test_the_shared_writer_refuses_a_hard_linked_events_file_for_run_lines_too(self):  # A4
        sentinel = self.sentinel()
        self.make_store()
        os.link(sentinel, self.events)
        with self.assertRaises(lease.LeaseError):
            lease.record_event(self.root, "started", {"session_id": "s1", "work": "SPEC-1"})
        self.assertEqual(sentinel.read_bytes(), b"sentinel: not an event\n")

    @POSIX
    def test_a_symbolic_link_in_place_of_the_events_file_is_refused(self):  # A5
        sentinel = self.sentinel()
        self.make_store()
        os.symlink(sentinel, self.events)
        self.assert_unchanged_with_one_warning(self.gate())
        self.assertEqual(sentinel.read_bytes(), b"sentinel: not an event\n")

    @POSIX
    def test_a_symbolic_link_in_place_of_the_store_folder_is_refused(self):  # A5
        folder = self.outside / "elsewhere"
        folder.mkdir()
        sentinel = folder / "events.jsonl"
        sentinel.write_bytes(b"sentinel: not an event\n")
        os.symlink(folder, self.store)
        self.assert_unchanged_with_one_warning(self.gate())
        self.assertEqual(sentinel.read_bytes(), b"sentinel: not an event\n")
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ["events.jsonl"])

    @POSIX
    def test_a_lock_held_by_another_command_is_never_stolen_and_the_gate_still_finishes(self):  # A6
        self.make_store()
        lock = self.store / ".lock"
        lock.write_text("424242-feedfacefeedface", encoding="utf-8")  # fresh, with a token that is not this run's
        with mock.patch.object(store, "LOCK_WAIT_SECONDS", 0.2):
            got = self.gate()
        self.assert_unchanged_with_one_warning(got)
        self.assertEqual(lock.read_text(encoding="utf-8"), "424242-feedfacefeedface")
        self.assertFalse(self.events.exists())

    def test_a_store_file_with_a_non_utf8_byte_costs_one_warning_and_no_traceback(self):  # A7
        self.make_store()
        bad = b'{"decision": "pass"}\n\xff\n'
        self.events.write_bytes(bad)
        self.assert_unchanged_with_one_warning(self.gate())
        self.assertEqual(self.events.read_bytes(), bad)

    def test_a_store_that_is_a_regular_file_costs_one_warning_and_no_traceback(self):  # A7
        self.store.write_text("not a folder\n", encoding="utf-8")
        self.assert_unchanged_with_one_warning(self.gate())
        self.assertEqual(self.store.read_text(encoding="utf-8"), "not a folder\n")

    @POSIX
    def test_a_read_only_store_folder_costs_one_warning_and_no_traceback(self):  # A7
        self.make_store()
        self.events.write_text('{"decision": "pass"}\n', encoding="utf-8")
        self.lock_down(self.store)
        self.assert_unchanged_with_one_warning(self.gate())
        self.assertEqual(self.events.read_text(encoding="utf-8"), '{"decision": "pass"}\n')

    def test_the_mcp_gate_tool_survives_a_bad_store_and_answers_again(self):  # A7
        self.make_store()
        self.events.write_bytes(b"\xff\n")
        calls = [{"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": "gate", "arguments": {}}} for i in (1, 2)]
        out = io.StringIO()
        mcp_server.serve(io.StringIO("".join(json.dumps(m) + "\n" for m in [MCP_LEGACY_INITIALIZE, *calls])), out, root=str(self.root))
        replies = {r["id"]: r["result"] for r in map(json.loads, out.getvalue().splitlines()) if r["id"] != MCP_LEGACY_INITIALIZE["id"]}
        clean = Path(self.tmp.name) / "clean"  # the same call on a repository with no store
        shutil.copytree(self._template, clean, symlinks=True)
        out = io.StringIO()
        mcp_server.serve(io.StringIO("".join(json.dumps(m) + "\n" for m in [MCP_LEGACY_INITIALIZE, calls[0]])), out, root=str(clean))
        (want,) = [r["result"] for r in map(json.loads, out.getvalue().splitlines()) if r["id"] == 1]
        self.assertEqual(sorted(replies), [1, 2])
        for i in (1, 2):
            self.assertEqual(replies[i]["isError"], want["isError"])
            text = replies[i]["content"][0]["text"]
            self.assertTrue(text.startswith(want["content"][0]["text"].strip()), text)
            self.assertEqual(text.count(KEPT), 1, text)

    # A8: the size cap

    def test_a_file_over_8_mib_is_skipped_with_one_warning_that_names_it(self):  # A8
        self.make_store()
        self.events.write_bytes(b"x" * CAP + b"\n")  # 8 MiB and 1 byte
        before = os.stat(self.events)
        got = self.gate()
        self.assert_unchanged_with_one_warning(got)
        self.assertIn("events.jsonl", warnings_in(got[2])[0])
        after = os.stat(self.events)
        self.assertEqual((after.st_size, after.st_mtime_ns), (before.st_size, before.st_mtime_ns))

    def test_a_file_of_exactly_8_mib_still_takes_the_line(self):  # A8 (the boundary)
        self.make_store()
        self.events.write_bytes(b"x" * (CAP - 1) + b"\n")
        code, out, err = self.gate()
        self.assertEqual((code, out), self.reference[()])
        self.assertEqual(warnings_in(err), [])
        last = self.events.read_text(encoding="utf-8").splitlines()[-1]
        self.assertTrue(last.startswith("{"), "the run's line follows the 8 MiB one")
        self.assertEqual(json.loads(last)["change"], "fix")

    # A9: the autopilot's own readings

    def test_gate_lines_between_an_active_runs_lines_change_no_autopilot_answer(self):  # A9
        self.assertEqual(cli(self.root, "autopilot", "start", "--work", "SPEC-1", "--session", "s1")[0], 0)
        self.assertEqual(self.gate()[0], 3)
        self.assertEqual(cli(self.root, "autopilot", "note", "spec.in_progress ok", "--session", "s1", "--spec", "SPEC-1")[0], 0)
        self.assertEqual(self.gate()[0], 3)
        mixed = [json.loads(x) for x in self.events.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([x.get("kind", "gate") for x in mixed], ["autopilot", "gate", "autopilot", "gate"])

        def readings():
            _, status, _ = cli(self.root, "autopilot", "status", "--json")
            (held,) = lease.leases(self.root)
            _, runs, _ = cli(self.root, "metrics", "--autopilot", "--json")
            return json.loads(status), lease.ended(self.root, held), json.loads(runs), len(lease.events(self.root))

        with_gate = readings()
        self.events.write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in mixed if x.get("kind") == "autopilot"), encoding="utf-8")
        without_gate = readings()
        self.assertEqual(with_gate[:3], without_gate[:3])
        self.assertEqual((with_gate[3], without_gate[3]), (4, 2))  # the readers saw the gate lines, and drew nothing from them


class Ship(RepoTemplateCase):
    """`aidd land` in a shop: a good branch `fix`, a `broken` one whose tests fail, and `declared`, whose block fails first."""

    @classmethod
    def build_template(cls, root):
        shop(root, "solo")
        described_fix(root, "broken", "def total(items):\n    return 0\n")
        git(root, "switch", "-q", "main")
        git(root, "switch", "-qc", "declared")
        block = "```yaml aidd\nroute: minor\ntype: fix\nscope: [app/cart.py]\nassisted_by: [claude-code/claude-opus-5-5]\n```"
        _commit(root, f"chore: block\n\n{block}\n\nAssisted-by: claude-code/claude-opus-5-5", {"README.md": "outside the scope\n"})
        described_fix(root, "fix", FIX)

    def fresh(self, name: str) -> Path:
        """An independent copy of the shop, on branch `fix`, with no store."""
        dest = Path(self.tmp.name).resolve() / name / "repo"
        dest.parent.mkdir()
        shutil.copytree(self._template, dest, symlinks=True)
        return dest

    @staticmethod
    def landed(root: Path) -> tuple[int, str, str, str]:
        """(exit code, stdout with the commit ids hidden, stderr, the tree main ends with): what a ship run did."""
        code, out, err = as_person(root, "land")
        return code, re.sub(r"\b[0-9a-f]{12}\b", "<sha>", out), err, git(root, "rev-parse", "main^{tree}")

    def test_one_ship_run_adds_one_gate_line_with_its_last_decision_after_the_tests(self):  # A11
        root = self.fresh("one")
        head = git(root, "rev-parse", "HEAD")
        code, _, err, _ = self.landed(root)
        self.assertEqual(code, 0, err)
        line = only(gate_lines(root / ".git" / "aidd" / "events.jsonl"))  # never the early check as well
        self.assertEqual((line["decision"], line["head_sha"], line["change"]), ("pass", head, "fix"))
        self.assertEqual(json_schema.validate(line, "event.schema.json"), [])
        self.assertEqual(warnings_in(err), [])

    def test_a_ship_run_that_does_not_ship_records_its_decision_too(self):  # A11
        root = self.fresh("broken")
        git(root, "switch", "-q", "broken")
        code, _, err, _ = self.landed(root)
        self.assertEqual(code, 1, err)
        self.assertIn("Not landed", err)
        line = only(gate_lines(root / ".git" / "aidd" / "events.jsonl"))
        self.assertEqual((line["decision"], line["change"]), ("fail", "broken"))

    def test_a_ship_run_that_stops_at_the_declaration_records_nothing(self):  # A11 (the early check is no gate run)
        root = self.fresh("declared")
        git(root, "switch", "-q", "declared")
        code, _, err, _ = self.landed(root)
        self.assertEqual(code, 1, err)
        self.assertIn("no test ran", err)
        self.assertFalse((root / ".git" / "aidd" / "events.jsonl").exists())

    @POSIX
    def test_a_hard_linked_events_file_changes_nothing_about_a_ship_run_but_one_warning(self):  # A11
        control = self.landed(self.fresh("control"))
        root = self.fresh("linked")
        store = root / ".git" / "aidd"
        store.mkdir(mode=0o700)
        sentinel = Path(self.tmp.name) / "sentinel.txt"
        sentinel.write_bytes(b"sentinel: not an event\n")
        os.link(sentinel, store / "events.jsonl")
        code, out, err, tree = self.landed(root)
        self.assertEqual((code, out, tree), (control[0], control[1], control[3]))
        self.assertEqual(len(warnings_in(err)), 1, err)
        self.assertEqual(sentinel.read_bytes(), b"sentinel: not an event\n")

    @POSIX
    def test_an_unwritable_store_changes_nothing_about_a_ship_run_but_one_warning(self):  # A11
        control = self.landed(self.fresh("control"))
        root = self.fresh("readonly")
        store = root / ".git" / "aidd"
        store.mkdir(mode=0o700)
        os.chmod(store, 0o500)
        self.addCleanup(os.chmod, store, 0o700)
        code, out, err, tree = self.landed(root)
        self.assertEqual((code, out, tree), (control[0], control[1], control[3]))
        self.assertEqual(len(warnings_in(err)), 1, err)


if __name__ == "__main__":
    unittest.main()
