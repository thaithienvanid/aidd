"""Local gate events, the read side (A2, A10): `aidd metrics` and `aidd digest` with no file argument read the git directory's
events.jsonl, then aidd-events.jsonl in the working directory; `aidd digest --client` keeps today's sources.

The gate lines here are written by hand, as valid events, into a real temporary repository that adopted aidd; the
write side (the lines a real gate run leaves) is tests/test_local_gate_events.py.
"""

import contextlib
import json
import unittest
from pathlib import Path

from helpers import RepoTemplateCase, make_repo, run_cli

from aidd import gate

SINCE = ("--since", "2020-01-01")  # the digest's window must reach the fixed times below


def event(change: str, ts: str, decision: str = "pass", **fields) -> dict:
    return (
        gate.event_header()
        | {"repo": "repo", "change": change, "ts": ts, "decision": decision, "route": "minor", "head_sha": "a" * 40, "platform": "local"}
        | {"failed_rules": [], "pending_rules": [], "approvals": 0, "author": None, "run_url": None}
        | fields
    )


GATE_LINES = [
    event("fix", "2026-10-14T09:00:00Z", "pending", pending_rules=["merge_approval"]),
    event("fix", "2026-10-14T10:00:00Z"),
    event("fix2", "2026-10-15T09:00:00Z", "pending", pending_rules=["merge_approval"]),
]


def write(path: Path, lines: list[dict]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in lines), encoding="utf-8")


class Read(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        make_repo(root, "solo", approvers=["@me"])

    def setUp(self):
        super().setUp()
        self.events = self.root / ".git" / "aidd" / "events.jsonl"
        self.ci = self.root / "aidd-events.jsonl"

    def cli(self, *argv: str) -> tuple[int, str]:
        with contextlib.chdir(self.root):
            return run_cli(*argv)

    def summary(self, *argv: str) -> dict:
        code, out = self.cli("metrics", "--json", *argv)
        self.assertEqual(code, 0, out)
        return json.loads(out)

    # A2: metrics

    def test_metrics_with_no_file_reads_the_events_in_the_git_directory(self):  # A2
        write(self.events, GATE_LINES)
        got = self.summary()
        self.assertEqual((got["events"], got["changes"]), (3, 2))

    def test_metrics_with_no_file_and_no_events_exits_2_and_names_the_default_path(self):  # A2
        code, out = self.cli("metrics")
        self.assertEqual(code, 2, out)
        self.assertIn(".git/aidd/events.jsonl", out.replace("\\", "/"))

    def test_an_explicit_file_replaces_the_default(self):  # A2 (as today)
        write(self.events, GATE_LINES)
        other = self.root / "other.jsonl"
        write(other, [event("7", "2026-10-13T09:00:00Z")])
        got = self.summary(str(other))
        self.assertEqual((got["events"], got["changes"]), (1, 1))

    def test_aidd_events_jsonl_in_the_working_directory_is_read_when_the_store_is_absent(self):  # A2
        write(self.ci, [event("7", "2026-10-13T09:00:00Z")])
        got = self.summary()
        self.assertEqual((got["events"], got["changes"]), (1, 1))

    def test_both_default_files_are_read_and_each_line_counts_once(self):  # A2
        write(self.events, GATE_LINES)
        write(self.ci, [event("7", "2026-10-13T09:00:00Z")])
        got = self.summary()
        self.assertEqual((got["events"], got["changes"]), (4, 3))

    def test_autopilot_run_lines_in_the_same_file_are_not_gate_events(self):  # A2
        self.assertEqual(self.cli("autopilot", "start", "--work", "SPEC-1", "--session", "s1")[0], 0)
        self.assertEqual(self.cli("autopilot", "note", "spec.in_progress ok", "--session", "s1", "--spec", "SPEC-1")[0], 0)
        runs = self.events.read_text(encoding="utf-8")
        self.assertEqual(len(runs.splitlines()), 2)
        self.events.write_text(runs + "".join(json.dumps(x, sort_keys=True) + "\n" for x in GATE_LINES), encoding="utf-8")
        got = self.summary()
        self.assertEqual((got["events"], got["changes"]), (3, 2))

    # A2: the digest's team view

    def test_the_digest_team_view_reads_the_default_files(self):  # A2
        code, out = self.cli("digest", "--json", *SINCE)
        self.assertEqual(code, 0, out)
        self.assertIsNone(json.loads(out)["metrics"])  # no events: no measures
        write(self.events, GATE_LINES)
        code, out = self.cli("digest", "--json", *SINCE)
        self.assertEqual(code, 0, out)
        self.assertIsNotNone(json.loads(out)["metrics"], "the digest read nothing")
        self.assertEqual(json.loads(out)["metrics"]["changes"], 2)

    # A10: the client view keeps today's sources

    def client(self, *argv: str) -> str:
        code, out = self.cli("digest", "--client", "--include-cost", "--cost", "cost.jsonl", "--json", *SINCE, *argv)
        self.assertEqual(code, 0, out)
        return out

    def test_the_client_digest_is_the_same_with_and_without_local_gate_lines(self):  # A10
        (self.root / "cost.jsonl").write_text(
            json.dumps({"ts": "2026-10-14T09:30:00Z", "amount": 1.5, "currency": "USD", "branch": "fix"}) + "\n", encoding="utf-8"
        )
        without = self.client()
        write(self.events, GATE_LINES)
        code, out = self.cli("digest", "--json", *SINCE)
        self.assertIsNotNone(json.loads(out)["metrics"], "the team view must read the lines this test is about")
        self.assertEqual(self.client(), without)
        # The control: the same lines named with --events do reach the client's cost, so the equality above is not empty.
        self.assertNotEqual(self.client("--events", str(self.events)), without)

    def test_the_client_digest_keeps_aidd_events_jsonl_as_its_default_source(self):  # A10 (as today)
        (self.root / "cost.jsonl").write_text(
            json.dumps({"ts": "2026-10-14T09:30:00Z", "amount": 1.5, "currency": "USD", "branch": "fix"}) + "\n", encoding="utf-8"
        )
        write(self.ci, GATE_LINES)
        write(self.events, [event("other", "2026-10-14T11:00:00Z")])
        self.assertEqual(self.client(), self.client("--events", "aidd-events.jsonl"))


if __name__ == "__main__":
    unittest.main()
