"""`approve_spec` over MCP: the person approves a Spec in the client's own dialog (elicitation), in either era.

Only the person's exact Approve, for the hash the dialog showed, records anything; the model's call alone never does.
"""

import contextlib
import io
import json
import shutil
import unittest
from pathlib import Path

from helpers import RepoTemplateCase, git, run_cli
from test_flows import shop, spec_and_tests

from aidd import workitems
from aidd.cli import mcp_server
from aidd.workitems import approval_ledger

MODERN = "2026-07-28"
ELICITS = {"elicitation": {}}


def meta(capabilities: dict | None = None) -> dict:
    return {
        "io.modelcontextprotocol/protocolVersion": MODERN,
        "io.modelcontextprotocol/clientInfo": {"name": "test client!", "version": "1"},
        "io.modelcontextprotocol/clientCapabilities": capabilities if capabilities is not None else ELICITS,
    }


def call(mid, extra: dict | None = None, capabilities: dict | None = None) -> dict:
    params = {"name": "approve_spec", "arguments": {"spec": "SPEC-1"}, "_meta": meta(capabilities), **(extra or {})}
    return {"jsonrpc": "2.0", "id": mid, "method": "tools/call", "params": params}


class DialogCase(RepoTemplateCase):
    """A repository with one Spec and its tests, where alice records approvals: each dialog tool's test starts here."""

    @classmethod
    def build_template(cls, root):
        shop(root, "team", "email:alice@example.com")
        spec_and_tests(root)

    def setUp(self):
        super().setUp()
        git(self.root, "config", "user.email", "alice@example.com")

    def ask(self, msg: dict) -> dict:
        return mcp_server.handle_message(msg, str(self.root))

    def recorded(self) -> str:
        return (
            git(self.root, "log", "--format=%B", approval_ledger.APPROVALS_REF) if git(self.root, "for-each-ref", approval_ledger.APPROVALS_REF).strip() else ""
        )


@unittest.skipUnless(shutil.which("git"), "git is required")
class ApproveSpecTests(DialogCase):
    def test_a_modern_client_gets_a_dialog_then_the_approval_on_the_persons_approve(self):
        first = self.ask(call(1))["result"]
        self.assertEqual(first["resultType"], "input_required")
        request = first["inputRequests"]["approve"]
        self.assertEqual(request["method"], "elicitation/create")
        self.assertIn("SPEC-1: Apply a percentage discount", request["params"]["message"])
        decision = request["params"]["requestedSchema"]["properties"]["decision"]
        self.assertEqual((decision["enum"], decision["default"]), (["Not now", "Approve"], "Not now"))  # the safe answer first
        self.assertEqual(self.recorded(), "")  # asking records nothing
        retry = {"inputResponses": {"approve": {"action": "accept", "content": {"decision": "Approve"}}}, "requestState": first["requestState"]}
        done = self.ask(call(2, retry))["result"]
        self.assertFalse(done["isError"], done)
        self.assertIn("Approved SPEC-1", done["content"][0]["text"])
        self.assertIn(f"{approval_ledger.CONFIRMED_TRAILER}: mcp:testclient", self.recorded())

    def test_several_specs_in_one_dialog_each_recorded_for_its_hash(self):
        spec = Path(self.root, "specs/SPEC-1.md")
        Path(self.root, "specs/SPEC-2.md").write_text(spec.read_text(encoding="utf-8").replace("id: SPEC-1", "id: SPEC-2"), encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "spec: SPEC-2\n\nAssisted-by: claude-code/claude-opus-5-5")
        for bad in (["SPEC-1"], ["SPEC-1", "SPEC-1"], ["SPEC-1", "--help"]):
            self.assertTrue(self.ask(call(1, {"arguments": {"specs": bad}}))["result"]["isError"], bad)
        first = self.ask(call(2, {"arguments": {"specs": ["SPEC-1", "SPEC-2"]}}))["result"]
        message = first["inputRequests"]["approve"]["params"]["message"]
        self.assertIn("SPEC-1: Apply a percentage discount", message)
        self.assertIn("SPEC-2: Apply a percentage discount", message)
        self.assertEqual(message.count("Risk: "), 2)  # each Spec shown as its own dialog would show it
        title = first["inputRequests"]["approve"]["params"]["requestedSchema"]["properties"]["decision"]["title"]
        self.assertEqual(title, "Approve SPEC-1, SPEC-2?")
        retry = {"inputResponses": {"approve": {"action": "accept", "content": {"decision": "Approve"}}}, "requestState": first["requestState"]}
        done = self.ask(call(3, retry))["result"]
        self.assertFalse(done["isError"], done)
        self.assertIn("Approved SPEC-1", done["content"][0]["text"])
        self.assertIn("Approved SPEC-2", done["content"][0]["text"])
        self.assertEqual(self.recorded().count(" approve-spec SPEC-"), 2)  # one record per Spec, each with its own hash

    def test_not_now_decline_cancel_or_a_forged_state_records_nothing(self):
        state = self.ask(call(1))["result"]["requestState"]
        answers = [
            {"action": "accept", "content": {"decision": "Not now"}},
            {"action": "decline"},
            {"action": "cancel"},
            {"action": "accept", "content": {}},
        ]
        for i, answer in enumerate(answers):
            with self.subTest(answer=answer):
                result = self.ask(call(10 + i, {"inputResponses": {"approve": answer}, "requestState": state}))["result"]
                self.assertIn("Not approved", result["content"][0]["text"])
        forged = state.split(".")[0] + "." + "0" * 64
        result = self.ask(call(20, {"inputResponses": {"approve": answers[0] | {"content": {"decision": "Approve"}}}, "requestState": forged}))["result"]
        self.assertTrue(result["isError"])
        self.assertEqual(self.recorded(), "")

    def test_a_client_that_cannot_ask_gets_how_the_person_approves(self):
        result = self.ask(call(1, capabilities={}))["result"]
        self.assertEqual(result["resultType"], "complete")
        text = result["content"][0]["text"]
        self.assertIn("approve SPEC-1", text)
        self.assertIn("aidd approve spec SPEC-1", text)
        self.assertEqual(self.recorded(), "")

    def test_a_spec_changed_after_the_dialog_is_not_approved(self):
        first = self.ask(call(1))["result"]
        spec = self.root / "specs" / "SPEC-1.md"
        spec.write_text(spec.read_text(encoding="utf-8") + "\nOne more line.\n", encoding="utf-8")
        git(self.root, "commit", "-qam", "spec: change")
        retry = {"inputResponses": {"approve": {"action": "accept", "content": {"decision": "Approve"}}}, "requestState": first["requestState"]}
        result = self.ask(call(2, retry))["result"]
        self.assertTrue(result["isError"])
        self.assertIn("Nothing was recorded", result["content"][0]["text"])
        self.assertEqual(self.recorded(), "")

    def test_a_legacy_client_is_asked_mid_call_and_other_messages_wait(self):
        init = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25", "capabilities": ELICITS, "clientInfo": {"name": "ide"}},
        }
        approve = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "approve_spec", "arguments": {"spec": "SPEC-1"}}}
        ping = {"jsonrpc": "2.0", "id": 3, "method": "ping"}  # arrives while the server waits for the person
        answer = {"jsonrpc": "2.0", "id": "aidd-1", "result": {"action": "accept", "content": {"decision": "Approve"}}}
        out = io.StringIO()
        mcp_server.serve(io.StringIO("".join(json.dumps(m) + "\n" for m in (init, approve, ping, answer))), out, root=str(self.root))
        sent = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual([m.get("id") for m in sent], [1, "aidd-1", 2, 3])
        self.assertEqual(sent[1]["method"], "elicitation/create")
        self.assertEqual(sent[1]["params"]["mode"], "form")
        self.assertIn("Approved SPEC-1", sent[2]["result"]["content"][0]["text"])
        self.assertIn(f"{approval_ledger.CONFIRMED_TRAILER}: mcp:ide", self.recorded())

    def test_a_legacy_client_without_elicitation_is_told_how_instead(self):
        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}}}
        approve = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "approve_spec", "arguments": {"spec": "SPEC-1"}}}
        out = io.StringIO()
        mcp_server.serve(io.StringIO("".join(json.dumps(m) + "\n" for m in (init, approve))), out, root=str(self.root))
        sent = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual([m.get("id") for m in sent], [1, 2])
        self.assertIn("cannot ask the person here", sent[1]["result"]["content"][0]["text"])
        self.assertEqual(self.recorded(), "")

    def test_a_standing_approval_starts_only_on_the_persons_approve_in_the_dialog(self):
        def approve_all(mid, extra=None, arguments=None):
            params = {"name": "approve_all", "arguments": arguments or {"but_major": True}, "_meta": meta(), **(extra or {})}
            return {"jsonrpc": "2.0", "id": mid, "method": "tools/call", "params": params}

        bad = self.ask(approve_all(1, arguments={"until": "next week"}))["result"]
        self.assertTrue(bad["isError"])
        first = self.ask(approve_all(2))["result"]
        message = first["inputRequests"]["approve"]["params"]["message"]
        self.assertIn("every Spec approval and Merge approval for you, except on major changes,", message)
        self.assertIn("stop approving", message)
        self.assertEqual(self.recorded(), "")
        replayed = self.ask(
            call(3, {"inputResponses": {"approve": {"action": "accept", "content": {"decision": "Approve"}}}, "requestState": first["requestState"]})
        )
        self.assertTrue(replayed["result"]["isError"])  # a standing approval's dialog never approves a Spec
        answer = {"inputResponses": {"approve": {"action": "accept", "content": {"decision": "Approve"}}}, "requestState": first["requestState"]}
        done = self.ask(approve_all(4, answer))["result"]
        self.assertFalse(done["isError"], done)
        self.assertIn(f"{approval_ledger.STANDING_TRAILER}: all-but-major", self.recorded())
        self.assertIn(f"{approval_ledger.CONFIRMED_TRAILER}: mcp:testclient", self.recorded())
        self.assertEqual((approval_ledger.live_standing(str(self.root), ["email:alice@example.com"]) or {}).get("scope"), "all-but-major")


@unittest.skipUnless(shutil.which("git"), "git is required")
class ProposalDecisionTests(DialogCase):
    """`proposal_decide` and `proposal_sign_off`: the person's go/no-go and sign-off, in the client's own dialog."""

    def tool(self, mid, name, arguments, extra=None):
        params = {"name": name, "arguments": arguments, "_meta": meta(), **(extra or {})}
        return {"jsonrpc": "2.0", "id": mid, "method": "tools/call", "params": params}

    def test_go_then_sign_off_each_on_the_persons_approve(self):
        with contextlib.chdir(self.root):
            self.assertEqual(run_cli("new", "proposal", "PROP-1", "--title", "Move billing", "--audience", "internal", "--addressee", "the board")[0], 0)
        path = Path(self.root, "proposals", "PROP-1", "proposal.md")
        approve = {"approve": {"action": "accept", "content": {"decision": "Approve"}}}
        for named in ("--help", "../elsewhere/proposal.md", "/tmp/proposal.md", "proposals/PROP-1"):
            bad = self.ask(self.tool(1, "proposal_decide", {"proposal": named, "decision": "go"}))["result"]
            self.assertTrue(bad["isError"], named)
            self.assertIn("inside the repository", json.dumps(bad), named)
        early = self.ask(self.tool(2, "proposal_sign_off", {"proposal": "PROP-1"}))["result"]
        self.assertIn("has no go yet", json.dumps(early))
        first = self.ask(self.tool(3, "proposal_decide", {"proposal": "PROP-1", "decision": "go", "reason": "fits our plan"}))["result"]
        message = first["inputRequests"]["approve"]["params"]["message"]
        self.assertIn("Decision: go, because fits our plan", message)
        self.assertIn("File: proposals/PROP-1/proposal.md", message)
        self.assertNotIn("go_no_go:", path.read_text(encoding="utf-8").split("\n---\n", 1)[0].replace("# go_no_go", ""))
        done = self.ask(self.tool(4, "proposal_decide", {}, {"inputResponses": approve, "requestState": first["requestState"]}))["result"]
        self.assertFalse(done["isError"], done)
        self.assertEqual(workitems.load_proposal(path)["go_no_go"]["decision"], "go")
        # A state signed for a decision never stands in for a sign-off.
        crossed = self.ask(self.tool(5, "proposal_sign_off", {}, {"inputResponses": approve, "requestState": first["requestState"]}))["result"]
        self.assertTrue(crossed["isError"])
        first = self.ask(self.tool(6, "proposal_sign_off", {"proposal": "PROP-1"}))["result"]
        self.assertIn("it may be sent", first["inputRequests"]["approve"]["params"]["message"])
        done = self.ask(self.tool(7, "proposal_sign_off", {}, {"inputResponses": approve, "requestState": first["requestState"]}))["result"]
        self.assertFalse(done["isError"], done)
        self.assertEqual(workitems.load_proposal(path)["sign_off"]["hash"], workitems.proposal_hash(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
