"""Proposals: the case put to a client or to the company's own decision makers, before any code, with the two human
decisions on record, and the bridge to delivery once it is accepted."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, RepoTemplateCase, example, git

from aidd import guard, model, proposal, repo, resources

BASE = """+++
aidd_version = "1.0.0"
kind = "proposal"
id = "PROP-1"
title = "Checkout rebuild"
audience = "client"
addressee = "Acme Corp"
goal = "Checkout succeeds on the first try for 99% of shoppers"
status = "{status}"
{top}
[[needs]]
id = "N-1"
need = "Pay by card"
source = "RFP 3.2"
answer = "met"
epic = "Payments"

[[needs]]
id = "N-2"
need = "Pay by invoice"
answer = "partly_met"
epic = "Payments"
note = "Business customers only"

[[needs]]
id = "N-3"
need = "Same-day delivery"
answer = "not_met"

[[needs]]
id = "N-4"
need = "Order history"
answer = "met"

[estimate]
unit = "person-days"
low = 40
likely = 55
high = 90
basis = "three comparable checkouts"
+++

## Summary
"""
GO = 'go_no_go = { decision = "go", by = "@lead", on = "2026-09-01" }\n'
SIGNED = 'sign_off = { by = "@lead", on = "2026-09-20" }\n'
ACCEPTED = 'outcome = { decision = "accepted", by = "@lead", on = "2026-09-25" }\n'
SUBMITTED = 'outcome = { decision = "submitted", by = "@lead", on = "2026-09-21" }\n'


def load(status="exploring", top=""):
    return model.load_object(BASE.format(status=status, top=top), "p.md")


class DecisionTests(unittest.TestCase):
    def test_a_fresh_proposal_needs_no_decision_yet(self):
        self.assertEqual(load()[2], [])

    def test_drafting_needs_a_person_to_have_said_go(self):
        errors = load("drafting")[2]
        self.assertTrue(any("go_no_go.decision" in e for e in errors), errors)
        self.assertEqual(load("drafting", GO)[2], [])

    def test_sending_needs_a_sign_off(self):
        self.assertTrue(any("needs sign_off" in e for e in load("submitted", GO)[2]))
        self.assertTrue(any("needs outcome" in e for e in load("submitted", GO + SIGNED)[2]))
        self.assertEqual(load("submitted", GO + SIGNED + SUBMITTED)[2], [])
        self.assertTrue(any("outcome submitted needs sign_off" in e for e in load("submitted", GO + SUBMITTED)[2]))

    def test_every_decision_records_its_date_as_on(self):
        """go_no_go, sign_off, triage, and the outcome all say `on`; `at` is no name of it."""
        self.assertEqual(load("submitted", GO + SIGNED + SUBMITTED)[2], [])
        self.assertTrue(load("submitted", GO + SIGNED + SUBMITTED.replace(" on =", " at ="))[2])
        undated = 'outcome = { decision = "submitted", by = "@lead" }\n'
        self.assertTrue(load("submitted", GO + SIGNED + undated)[2])
        self.assertIn('on = "YYYY-MM-DD"', " ".join(load("accepted", GO + SIGNED)[2]))

    def test_the_status_is_derived_from_the_decisions_and_the_outcome(self):
        """Store only the person's decisions: the status follows from go_no_go, sign_off, and outcome."""
        no_go = 'go_no_go = { decision = "no_go", by = "@lead", on = "2026-09-01" }\n'
        for top, want in (
            ("", "exploring"),
            (no_go, "no_go"),
            (GO, "drafting"),
            (GO + SIGNED, "signed_off"),
            (GO + SIGNED + SUBMITTED, "submitted"),
            (GO + SIGNED + ACCEPTED, "accepted"),
        ):
            data = load("exploring", top)[0]
            self.assertEqual(model.proposal_status(data), want, top)
            no_status = BASE.format(status="x", top=top).replace('status = "x"\n', "")
            data, _, errors = model.load_object(no_status, "p.md")
            self.assertEqual((model.proposal_status(data), errors), (want, []))  # the status is optional
        # A stale cache warns; a status the schema does not know is an error (1.0.0 is the first release: no old tokens).
        (warn,) = load("exploring", GO)[2]
        self.assertTrue(warn.startswith("warning: p.md: status exploring is behind the recorded decisions, which make it drafting"), warn)
        errors = load("ready", GO + SIGNED)[2]
        self.assertTrue(errors and not any(e.startswith("warning:") for e in errors), errors)

    def test_no_go_is_recorded_as_a_decision(self):
        self.assertTrue(load("no_go")[2])
        self.assertEqual(load("no_go", 'go_no_go = { decision = "no_go", by = "@lead", on = "2026-09-01", reason = "not our market" }\n')[2], [])

    def test_the_range_must_be_ordered_and_ids_unique(self):
        bad = BASE.replace("low = 40", "low = 95").replace('id = "N-4"', 'id = "N-1"')
        errors = model.load_object(bad.format(status="exploring", top=""), "p.md")[2]
        self.assertTrue(any("low <= likely <= high" in e for e in errors), errors)
        self.assertTrue(any("needs: ids must be unique (N-1)" in e for e in errors), errors)

    def test_an_agent_account_cannot_decide(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".aidd").mkdir()
            (root / ".aidd" / "config.toml").write_text(
                'aidd_version = "1.0.0"\nprofile = "team"\n[owners]\napprovers = ["@lead"]\n[identities]\nbots = ["claude[bot]"]\n', encoding="utf-8"
            )
            folder = root / "proposals" / "PROP-1"
            folder.mkdir(parents=True)
            (folder / "proposal.md").write_text(BASE.format(status="drafting", top=GO.replace("@lead", "claude[bot]")), encoding="utf-8")
            errors, _ = repo.check_repo(root)
            self.assertTrue(any("go_no_go.by claude[bot] is an agent account" in e for e in errors), errors)


class MatrixTests(unittest.TestCase):
    def test_the_tables_a_decision_maker_compares(self):
        import re

        p, _, errors = load(
            "drafting",
            GO + 'assumptions = [{ id = "A-1", text = "Acme provides test cards", owner = "Acme", status = "open" }]\nexclusions = ["Mobile apps"]\n',
        )
        self.assertEqual(errors, [])
        text = proposal.matrix(p)
        sections = {s.split("\n", 1)[0]: s.split("\n", 1)[1] for s in text.split("\n## ")[1:]}
        # The needs: a tally per answer, and one row per need that carries the data as written.
        needs = sections["Needs and how we answer them"]
        summary = next(ln for ln in needs.splitlines() if ln[:1].isdigit())
        tally = {word.lower(): int(n) for n, word in re.findall(r"(\d+) ([A-Za-z ]+?)(?=[,.])", summary.split(":", 1)[1])}
        want = {proposal.ANSWER_WORDS[a].lower(): sum(1 for n in p["needs"] if n["answer"] == a) for a in proposal.ANSWER_WORDS}
        self.assertEqual(tally, {k: v for k, v in want.items() if v})
        self.assertTrue(summary.startswith(f"{len(p['needs'])} needs"), summary)
        rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in needs.splitlines() if ln.startswith("| N-")]
        self.assertEqual(
            rows,
            [[n["id"], n["need"], n.get("source", ""), proposal.ANSWER_WORDS[n["answer"]], n.get("note", "")] for n in p["needs"]],
        )
        # The estimate: the range, the most likely value, the unit, and the basis.
        est = p["estimate"]
        numbers = [int(x) for x in re.findall(r"\d+", sections["Estimate"])]
        self.assertEqual(sorted(numbers), sorted([est["low"], est["likely"], est["high"]]))
        self.assertIn(est["unit"], sections["Estimate"])
        self.assertIn(est["basis"], sections["Estimate"])
        self.assertIn("| A-1 | Acme provides test cards | Acme | open |  |", sections["Assumptions"])
        self.assertEqual(sections["Not included"].split(), ["-", *p["exclusions"][0].split()])


class ConvertTests(unittest.TestCase):
    def test_a_long_title_is_cut_and_a_too_long_id_writes_nothing(self):
        data = load("accepted", GO + SIGNED + ACCEPTED)[0]
        data["title"] = "A very long proposal title " * 10
        for n in data["needs"]:
            n["epic"] = "An epic group name that goes on and on " * 5
        with tempfile.TemporaryDirectory() as d:
            for p in proposal.convert(data, Path(d)):
                obj, _, errors = model.load_object(p.read_text(encoding="utf-8"), p.name)
                self.assertEqual(errors, [], p.name)
                self.assertLessEqual(len(obj["title"]), proposal.TITLE_MAX)
                self.assertTrue(obj["title"].endswith("…"))
        data["id"] = "PROP-" + "x" * 58  # a valid proposal id, but INIT- and EPIC- ids past it exceed 64 characters
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "would not validate"):
                proposal.convert(data, Path(d))
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_only_an_accepted_proposal_becomes_work(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError):
            proposal.convert(load("submitted", GO + SIGNED)[0], Path(d))

    def test_accepted_needs_become_epics_that_trace_back(self):
        with tempfile.TemporaryDirectory() as d:
            written = proposal.convert(load("accepted", GO + SIGNED + ACCEPTED)[0], Path(d), "checkout")
            self.assertEqual([p.name for p in written], ["INIT-PROP-1.md", "EPIC-PROP-1-1.md", "EPIC-PROP-1-2.md"])
            objects = {p.name: model.load_object(p.read_text(encoding="utf-8"), p.name) for p in written}
            for name, (_, _, errors) in objects.items():
                self.assertEqual(errors, [], name)
            self.assertEqual(objects["INIT-PROP-1.md"][0]["proposal"], "PROP-1")
            self.assertEqual(objects["EPIC-PROP-1-1.md"][0]["covers"], ["N-1", "N-2"])
            self.assertEqual(objects["EPIC-PROP-1-2.md"][0]["covers"], ["N-4"])  # N-3 is not met, so nobody delivers it
            self.assertEqual(objects["EPIC-PROP-1-1.md"][0]["parent"], "INIT-PROP-1")

    def test_converting_twice_writes_nothing_the_second_time(self):
        data = load("accepted", GO + SIGNED + ACCEPTED)[0]
        with tempfile.TemporaryDirectory() as d:
            written = proposal.convert(data, Path(d))
            (Path(d) / "EPIC-PROP-1-2.md").write_text("edited by the product manager\n", encoding="utf-8")
            before = {p.name: p.read_bytes() for p in Path(d).iterdir()}
            with self.assertRaisesRegex(FileExistsError, "INIT-PROP-1.md exists"):
                proposal.convert(data, Path(d))
            self.assertEqual({p.name: p.read_bytes() for p in Path(d).iterdir()}, before)
            self.assertEqual(sorted(before), sorted(p.name for p in written))

    def test_only_a_proposal_loads_as_one(self):
        with tempfile.TemporaryDirectory() as d:
            spec = Path(d) / "SPEC-220.md"
            spec.write_text(example("02-normal-feature")["head_files"]["specs/SPEC-220.md"], encoding="utf-8")
            with self.assertRaisesRegex(model.ModelError, "not a proposal"):
                proposal.load(spec)
            good = Path(d) / "proposal.md"
            good.write_text(BASE.format(status="accepted", top=GO + SIGNED + ACCEPTED), encoding="utf-8")
            self.assertEqual(proposal.load(good)["id"], "PROP-1")


@unittest.skipUnless(shutil.which("git"), "git is required")
class GuardTests(RepoTemplateCase):
    """Proposal work comes before any Spec: the roles that write a proposal may do so with no Spec active, in the
    proposals folder only, and nobody who builds code writes there."""

    @classmethod
    def build_template(cls, root):
        git(root, "init", "-q", "-b", "main")
        repo.init(root, profile="team", ci="none", links=[], skill=False, approvers=["@x"], harnesses=[])

    def with_a_spec(self):
        """A branch with an active Spec: the builders' area is its Tasks' scope, which holds no proposal."""
        (self.root / "specs" / "SPEC-220.md").write_text(example("02-normal-feature")["head_files"]["specs/SPEC-220.md"], encoding="utf-8")

    def decide(self, role, path):
        return guard.check_edit(str(self.root), path, role)[0]

    def test_the_proposal_roles_write_their_parts_and_nothing_else(self):
        writers = {k for k, r in resources.roles()["roles"].items() if "{proposals_dir}" in r["writes"]}
        self.assertEqual(
            writers, {"product-manager", "delivery-manager", "architect", "product-designer", "security-engineer", "compliance-analyst", "sre", "tech-writer"}
        )
        # Intentionally changed: each role writes only its own part of the proposal's folder (guard.PROPOSAL_PARTS).
        self.assertEqual(set(guard.PROPOSAL_PARTS), writers)
        for role in sorted(writers):
            own = guard.PROPOSAL_PARTS[role][0]
            self.assertEqual(self.decide(role, f"proposals/PROP-1/{own}"), "allow", role)
            for other in {p for parts in guard.PROPOSAL_PARTS.values() for p in parts} - set(guard.PROPOSAL_PARTS[role]):
                other = f"{other}CO-1.md" if other.endswith("/") else other
                decision, reason = guard.check_edit(str(self.root), f"proposals/PROP-1/{other}", role)
                self.assertEqual(decision, "deny", (role, other))
                self.assertIn("only a person records go_no_go, sign_off, and outcome", reason)
            self.assertEqual(self.decide(role, "src/app.py"), "deny", role)
        # The delivery manager also writes the engagement's contract and its change orders.
        for part in ("contract.md", "change-orders/CO-1.md"):
            self.assertEqual(self.decide("delivery-manager", f"proposals/PROP-1/{part}"), "allow", part)
        # With no Spec the guard leaves a builder's edit to the gate (it may be fast-lane work); with one, the
        # builders keep to its scope, while the proposal roles still reach their proposal.
        self.with_a_spec()
        self.assertEqual(self.decide("architect", "proposals/PROP-1/architecture.md"), "allow")
        for role in ("developer", "tester", "reviewer", "verifier"):
            self.assertEqual(self.decide(role, "proposals/PROP-1/proposal.md"), "deny", role)

    def test_no_role_records_an_initiatives_go_no_go(self):
        """An Initiative's go_no_go is a person's decision too, in the proposal's shape: no role adds or changes it."""
        rel = "specs/INIT-1.md"
        path = self.root / rel
        draft = '+++\naidd_version = "1.0.0"\nkind = "initiative"\nid = "INIT-1"\ntitle = "t"\ngoal = "g"\n+++\n\n## Why\n'
        decided = draft.replace('goal = "g"\n', 'goal = "g"\n' + GO)

        def hook(role, tool, tool_input):
            event = {"tool_name": tool, "tool_input": {"file_path": str(path), **tool_input}, "agent_type": f"aidd-team:{role}"}
            return guard.check_agent_edit(str(self.root), rel, event)

        for role in ("product-manager", "delivery-manager"):
            with self.subTest(role=role):
                if path.exists():
                    path.unlink()
                decision, reason = hook(role, "Write", {"content": decided})
                self.assertEqual(decision, "deny", reason)
                self.assertIn("go_no_go", reason)
                self.assertIn("only a person records", reason)
                self.assertEqual(guard.reason_code(reason), "initiative_decision")
                path.write_text(draft, encoding="utf-8")
                self.assertEqual(hook(role, "Edit", {"old_string": 'goal = "g"\n', "new_string": 'goal = "g"\n' + GO})[0], "deny")
                path.write_text(decided, encoding="utf-8")
                self.assertEqual(hook(role, "MultiEdit", {"edits": [{"old_string": '"go"', "new_string": '"no_go"'}]})[0], "deny")
                self.assertEqual(hook(role, "Write", {"content": decided.replace('title = "t"', "title = ")})[0], "deny")  # cannot compare
        # The rest of the Initiative stays the product manager's to write, the recorded decision untouched.
        path.write_text(decided, encoding="utf-8")
        self.assertEqual(hook("product-manager", "Edit", {"old_string": "## Why\n", "new_string": "## Why\n\nCheckout is slow.\n"})[0], "allow")
        self.assertEqual(hook("product-manager", "Write", {"content": decided + "More text.\n"})[0], "allow")
        # A Spec carries no go_no_go of its own: the rule is the Initiative's, and the person's session records it.
        path.write_text(draft, encoding="utf-8")
        person = {"tool_name": "Write", "tool_input": {"file_path": str(path), "content": decided}}
        self.assertEqual(guard.check_agent_edit(str(self.root), rel, person)[0], "allow")

    def test_an_initiatives_go_no_go_is_held_in_a_sibling_worktree_too(self):
        """The rule resolves the target with guard.locate, as every edit rule does: a role in this worktree that edits
        an Initiative in a sibling worktree of the same repository meets the same rule there."""
        import io
        import json

        git(self.root, "add", "-A")
        git(self.root, "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-qm", "init")
        sibling = self.root.parent / "sibling"
        git(self.root, "worktree", "add", "-q", str(sibling), "-b", "sibling")
        path = sibling / "specs" / "INIT-1.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        draft = '+++\naidd_version = "1.0.0"\nkind = "initiative"\nid = "INIT-1"\ntitle = "t"\ngoal = "g"\n+++\n\n## Why\n'
        path.write_text(draft, encoding="utf-8")
        self.assertEqual(guard.locate(path).top, str(sibling))
        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(path), "old_string": 'goal = "g"\n', "new_string": 'goal = "g"\n' + GO},
            "agent_type": "aidd-team:product-manager",
            "cwd": str(self.root),
            "session_id": "s1",
            "hook_event_name": "PreToolUse",
        }
        out = io.StringIO()
        guard.pre_tool_hook(io.StringIO(json.dumps(event)), out)
        answer = json.loads(out.getvalue())["hookSpecificOutput"]
        self.assertEqual(answer["permissionDecision"], "deny")
        self.assertEqual(guard.reason_code(answer["permissionDecisionReason"]), "initiative_decision")

    def test_no_role_records_the_go_no_go_or_the_sign_off(self):
        rel = "proposals/PROP-1/proposal.md"
        path = self.root / rel
        path.parent.mkdir(parents=True)
        drafting = BASE.format(status="drafting", top="")
        decided = BASE.format(status="drafting", top=GO)
        signed = BASE.format(status="ready", top=GO + 'sign_off = { by = "@lead", on = "2026-09-02" }\n')

        def hook(tool, tool_input):
            event = {"tool_name": tool, "tool_input": {"file_path": str(path), **tool_input}, "agent_type": "aidd-team:product-manager"}
            return guard.check_agent_edit(str(self.root), rel, event)

        # A new file that already carries a decision, and an Edit or a Write that adds or changes one: denied.
        self.assertEqual(hook("Write", {"content": decided})[0], "deny")
        path.write_text(drafting, encoding="utf-8")
        decision, reason = hook("Edit", {"old_string": 'status = "drafting"\n', "new_string": 'status = "drafting"\n' + GO})
        self.assertEqual(decision, "deny")
        self.assertIn("only a person records", reason)
        self.assertEqual(hook("Write", {"content": decided})[0], "deny")
        path.write_text(decided, encoding="utf-8")
        self.assertEqual(hook("MultiEdit", {"edits": [{"old_string": '"go"', "new_string": '"no_go"'}]})[0], "deny")
        self.assertEqual(hook("Write", {"content": signed})[0], "deny")
        broken = decided.replace("[estimate]", "[estimate")
        self.assertEqual(hook("Write", {"content": broken})[0], "deny")  # cannot compare, and it names a decision
        # The rest of the proposal stays the role's to write, the recorded decision untouched.
        self.assertEqual(hook("Edit", {"old_string": "## Summary", "new_string": "## Summary\n\nWe rebuild checkout."})[0], "allow")
        self.assertEqual(hook("Write", {"content": decided + "\nMore text.\n"})[0], "allow")
        path.unlink()
        self.assertEqual(hook("Write", {"content": drafting})[0], "allow")


class CliTests(unittest.TestCase):
    def test_new_matrix_and_validate_from_the_command_line(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            env = os.environ | {"PYTHONPATH": str(ROOT / "src")}
            run = lambda *a: subprocess.run([sys.executable, "-m", "aidd", *a], cwd=d, env=env, capture_output=True, text=True, encoding="utf-8")  # noqa: E731
            made = run("new", "proposal", "PROP-9", "--title", "Move billing to the cloud", "--audience", "internal", "--addressee", "the executive committee")
            self.assertEqual(made.returncode, 0, made.stderr)
            path = Path(d) / "proposals" / "PROP-9" / "proposal.md"
            self.assertIn('audience = "internal"', path.read_text(encoding="utf-8"))
            self.assertEqual(run("validate", str(path)).returncode, 0)
            shown = run("proposal", "matrix", str(path))
            self.assertEqual(shown.returncode, 0, shown.stderr)
            self.assertIn("For the executive committee.", shown.stdout)
            self.assertEqual(run("proposal", "convert", str(path)).returncode, 1)  # still exploring
            path.write_text(BASE.format(status="accepted", top=GO + SIGNED + ACCEPTED), encoding="utf-8")
            done = run("proposal", "convert", str(path))
            self.assertEqual(done.returncode, 0, done.stderr)
            wrote = [ln.split()[1] for ln in done.stdout.splitlines() if ln.startswith("wrote")]
            self.assertEqual(wrote, ["specs/INIT-PROP-1.md", "specs/EPIC-PROP-1-1.md", "specs/EPIC-PROP-1-2.md"])
            self.assertTrue(all((Path(d) / w).is_file() for w in wrote))
            self.assertEqual(run("proposal", "convert", str(path)).returncode, 1)  # the files exist: nothing is overwritten
            self.assertEqual(run("proposal", "matrix", str(Path(d) / wrote[0])).returncode, 2)  # an Initiative is not a proposal


if __name__ == "__main__":
    unittest.main()
