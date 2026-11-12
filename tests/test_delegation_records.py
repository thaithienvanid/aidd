"""What a delegated merge counts as a Spec's approval, and what an unreadable record does to the check.

Invariants. (1) For every record a session can write, the only approval a delegated merge counts is the delegate's own
accept, only while `spec.approve` is delegated: a person's yes is never a record, and a reserved action is never the
delegate's. (2) The merge counts nothing the old check did not count. (3) A file that does not read as a record defers
the check, with the next step; a record that reads, in any type, does not."""

import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

from helpers import git
from test_delegation_check import ENV, Case, codes

from aidd import config, delegation, records
from aidd.delegation import action_checks

HEAD = "c" * 40
DELEGATED = {"decides": ["spec.approve", "git.merge"]}
RESERVED = {"decides": ["git.merge"]}


def old_approvals(root: str, spec_id: str) -> list[tuple[str, str]]:
    """`approvals` at the commit before this change: a `decision` from any writer, or the delegate's accept, as (when, head)."""
    pulled = records.pulled_ids(root)
    decisions = [r for r in records.read_records(root, record_type="decision")[0] if r.get("id") not in pulled]
    found = []
    for rec in [*decisions, *records.delegate_accepts(root, spec_id)]:
        data = rec.get("data") or {}
        covers = data.get("covers") or {}
        said = (data.get("answer") or {}).get("outcome") if rec.get("type") == "decision" else data.get("outcome")
        if data.get("action") == "spec.approve" and covers.get("spec") == spec_id and said == "accept" and covers.get("head"):
            found.append((str(rec.get("recorded_at", "")), str(covers["head"])))
    return sorted(found, reverse=True)


def write(root: str, kind: str) -> None:
    """One record of `kind` about SPEC-4's approval, written the way a session or the delegate writes it."""
    covers = {"spec": "SPEC-4", "head": HEAD, "tree": "d" * 40}
    if kind.startswith("decision"):
        data = {
            "action": "spec.approve",
            "question": {"type": "yes_no", "text": "Approve?"},
            "covers": covers,
            "answer": {"outcome": "accept", "words": "yes", "by": "Maya Lee"},
        }
        mcp = kind == "decision via the tool"
        with records.written_with_mcp() if mcp else nullcontext():
            records.add_record("decision", data, by="agent:claude-code/claude-opus-5-5", cwd=root)
        return
    data = {
        "action": "spec.approve",
        "covers": covers,
        "outcome": "defer" if kind == "delegate defer" else "accept",
        "reason": "ready",
        "check": "20261108T101500123Z-1a2b3c4d",
        "delegation_commit": "b" * 40,
    }
    by = "agent:claude-code/someone-else" if kind == "another writer" else config.DECIDED_BY
    with records.written_by_delegation():
        records.add_record("delegate_answer", data, by=by, cwd=root)


KINDS = ("none", "decision", "decision via the tool", "delegate accept", "delegate defer", "another writer")


class ApprovalTests(unittest.TestCase):
    def test_a_delegated_merge_counts_only_the_delegates_accept_and_only_while_spec_approve_is_delegated(self):
        counts = {("delegate accept", "delegated")}
        for kind in KINDS:
            for mode, block in (("delegated", DELEGATED), ("reserved", RESERVED)):
                with self.subTest(kind=kind, mode=mode), tempfile.TemporaryDirectory() as d:
                    git(Path(d), "init", "-q", "-b", "main")
                    if kind != "none":
                        write(d, kind)
                    new = [head for _when, head in action_checks.approvals(SimpleNamespace(top=d, delegation=block), "SPEC-4")]
                    self.assertEqual(new, [HEAD] if (kind, mode) in counts else [])

    def test_no_approval_counts_now_that_did_not_count_before(self):
        """The differential: the old function against the new one on every record and every delegation. The cells where
        the old counted and the new does not are a decision, in either mode, and the delegate's accept of a reserved action."""
        lost = []
        for kind in KINDS:
            for mode, block in (("delegated", DELEGATED), ("reserved", RESERVED)):
                with tempfile.TemporaryDirectory() as d:
                    git(Path(d), "init", "-q", "-b", "main")
                    if kind != "none":
                        write(d, kind)
                    old = {head for _when, head in old_approvals(d, "SPEC-4")}
                    new = {head for _when, head in action_checks.approvals(SimpleNamespace(top=d, delegation=block), "SPEC-4")}
                    self.assertLessEqual(new, old, f"{kind} / {mode}: a record counts now that did not count before")
                    if old - new:
                        lost.append((kind, mode))
        self.assertEqual(
            sorted(lost),
            [
                ("decision", "delegated"),
                ("decision", "reserved"),
                ("decision via the tool", "delegated"),
                ("decision via the tool", "reserved"),
                ("delegate accept", "reserved"),
            ],
        )


class UnreadableRecordTests(Case):
    def plant(self, name: str, text: str) -> Path:
        folder = Path(git(self.root, "rev-parse", "--git-common-dir"))
        folder = folder if folder.is_absolute() else self.root / folder
        path = folder / "aidd" / "records" / "2026" / "11" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_a_file_that_does_not_read_as_a_record_defers_with_a_next_step_and_a_record_that_reads_does_not(self):
        repo = self.repo()
        head = repo.change()
        self.assertEqual(codes(repo.check(head)), [], "no record, no problem")
        honest = {
            "a record of a type a newer aidd writes": json.dumps(
                {"id": "20261111T000000000Z-aaaaaaaa", "type": "audit", "recorded_at": "2026-11-11T00:00:00Z", "by": "agent:x/y", "data": {"k": 1}}
            ),
            "a record with its keys in another order": json.dumps(
                {"data": {"k": 1}, "type": "audit", "id": "20261111T000001000Z-bbbbbbbb", "by": "agent:x/y", "recorded_at": "2026-11-11T00:00:01Z"}, indent=4
            ),
        }
        for name, text in honest.items():
            with self.subTest(name):
                path = self.plant(f"{json.loads(text)['id']}.json", text)
                self.assertEqual(codes(repo.check(head)), [], "a hand-written record that reads is not a problem")
                path.unlink()
        broken = {
            "a half-written file": '{"id": "20261111T000002000Z-cccccccc", "type": "delegate_answer", "da',
            "a trailing comma": '{"id": "20261111T000003000Z-dddddddd", "type": "report", "data": {"a": 1,},}',
            "no data": json.dumps({"id": "20261111T000004000Z-eeeeeeee", "type": "report"}),
            "not an object": "[1, 2]",
        }
        for name, text in broken.items():
            with self.subTest(name):
                path = self.plant(f"{name.replace(' ', '-')}.json", text)
                result = repo.check(head)
                self.assertEqual(codes(result), ["records_unreadable"])
                self.assertIn(path.name, result["reasons"][0]["detail"], "the reason names the file")
                self.assertIn("aidd records", result["next"]["what"], "the next step names the command that lists it")
                path.unlink()
                self.assertEqual(codes(repo.check(head)), [], "once the file reads or is gone, the check passes again")

    def test_an_unreadable_file_defers_every_delegated_action(self):
        repo = self.repo()
        head = repo.change()
        self.plant("broken.json", "{")
        asks = {
            "git.merge": dict(command=f"git merge --no-ff {head}"),
            "git.push": dict(command=f"git push origin {head}:refs/heads/feature"),
            "spec.approve": dict(command="", spec="SPEC-1"),
        }
        for action, ask in asks.items():
            with self.subTest(action):
                result = delegation.run_check(delegation.Request(action=action, head=head, cwd=str(self.root), env=ENV, **ask))
                self.assertIn("records_unreadable", codes(result))


if __name__ == "__main__":
    unittest.main()
