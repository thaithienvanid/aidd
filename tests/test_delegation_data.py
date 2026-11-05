"""The data of a standing delegation: the config block a parent can only narrow, the record types only aidd writes, the
rise to ask, and the check's reason codes, each with its meaning and its next step."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd import config, records, risk
from aidd.cli import mcp_tools
from aidd.kernel import json_schema, resources

DELEGATION = """delegation:
  to: delegate
  set_by: "Maya Lee <maya@users.noreply.github.com>"
  decides: {decides}
  review_by: "{review_by}"
"""


def load(child: str, parent: str | None = None) -> config.Config:
    files = {"preset.yaml": f'aidd_version: "1.0.0"\nprofile: solo\n{parent}'} if parent is not None else {}
    head = 'aidd_version: "1.0.0"\nprofile: solo\n' + ("extends: [{path: preset.yaml}]\n" if parent is not None else "")
    return config.load_text(head + child, read=files.get)


def block(decides: str = "all", review_by: str = "2027-02-06", extra: str = "") -> str:
    return DELEGATION.format(decides=decides, review_by=review_by) + extra


class PresetTests(unittest.TestCase):
    def test_preset_cannot_widen(self):
        cases = {
            "a parent's list narrows all": (block(), block("[spec.approve]"), ["spec.approve"], 0),
            "a child's action the parent leaves out is dropped": (block("[spec.approve, pr.merge]"), block("[spec.approve]"), ["spec.approve"], 1),
            "a parent's all keeps the child's list": (block("[git.push]"), block(), ["git.push"], 0),
        }
        for name, (child, parent, decides, warned) in cases.items():
            with self.subTest(name):
                cfg = load(child, parent)
                self.assertEqual(cfg.get("delegation", "decides"), decides)
                self.assertEqual(sum("delegation.decides" in w for w in cfg.warnings), warned)

    def test_a_parent_reserves_reviews_sooner_and_reads_deploys_strictly(self):
        child = block(extra="  reserved: [git.push]\n  default_branch_deploys: false\n")
        parent = block(review_by="2026-12-01", extra="  reserved: [pr.merge]\n")
        cfg = load(child, parent)
        self.assertEqual(cfg.get("delegation", "reserved"), ["git.push", "pr.merge"])
        self.assertEqual(cfg.get("delegation", "review_by"), "2026-12-01")
        self.assertNotIn("default_branch_deploys", cfg.get("delegation"), "the parent left it unknown, so it stays unknown")
        both = load(child, block(extra="  default_branch_deploys: true\n"))
        self.assertIs(both.get("delegation", "default_branch_deploys"), True)

    def test_a_parent_alone_never_starts_a_delegation(self):
        cfg = load("", block())
        self.assertIsNone(cfg.get("delegation"))
        self.assertTrue(any("only this repository's own config" in w for w in cfg.warnings))

    def test_the_block_refuses_what_it_does_not_know(self):
        bad = {
            "an unknown action": block("[deploy.run]"),
            "a set_by with a backtick": block().replace("Maya Lee", "Maya `x` Lee"),
            "a set_by with no address": block().replace(" <maya@users.noreply.github.com>", ""),
            "a date that is no date": block(review_by="soon"),
            "another role": block().replace("to: delegate", "to: reviewer"),
        }
        for name, text in bad.items():
            with self.subTest(name), self.assertRaises(config.ConfigError):
                load(text)


class RiseTests(unittest.TestCase):
    def test_reserved_actions_rise_to_ask(self):
        plain = risk.rule_set(load(""))
        delegated = risk.rule_set(load(block()))
        for action in ("dependency.add", "migration.run.local"):
            with self.subTest(action):
                self.assertEqual(risk.level_of(plain, action)[0], "report")
                level, rule = risk.level_of(delegated, action)
                self.assertEqual((level, rule.source), ("ask", "delegation"))

    def test_a_new_dependency_is_its_own_action(self):
        rs = risk.rule_set(None)
        found = risk.command_level(rs, "npm install left-pad", cwd=None)
        self.assertIn("dependency.add", [m["action"] for m in found["actions"]])


class RecordTypeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        subprocess.run(["git", "init", "-q", self.tmp.name], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def data(self) -> dict:
        return {
            "action": "pr.merge",
            "covers": {"head": "9c1e4a7b2d3f4e5a6b7c8d9e0f1a2b3c4d5e6f70", "tree": "77d0a1b2c3d4e5f60718293a4b5c6d7e8f901234"},
            "outcome": "defer",
            "reason": "the change drifts from the person's intent",
            "check": "20261108T101500123Z-1a2b3c4d",
            "delegation": "3f2a9c1e7b0d4c8a9e1f2b3c4d5e6f7a8b9c0d1e",
        }

    def test_records_add_refuses_delegate_types(self):
        for record_type in records.DELEGATION_TYPES:
            with self.subTest(record_type), self.assertRaisesRegex(records.RecordError, "aidd writes"):
                records.add_record(record_type, self.data(), by="agent:claude-code/claude-opus-5-5", cwd=self.tmp.name)
        with records.written_by_delegation():
            record, path = records.add_record("delegate_answer", self.data(), by="agent:claude-code/aidd-team:delegate", cwd=self.tmp.name)
        self.assertTrue(path.is_file())
        self.assertEqual(record["data"]["outcome"], "defer")

    def test_the_mcp_record_tool_offers_only_the_agents_types(self):
        tool = next(t for t in mcp_tools.TOOLS if t["name"] == "record")
        self.assertEqual(tool["inputSchema"]["properties"]["type"]["enum"], ["decision", "report"])


class TrailerTests(unittest.TestCase):
    def test_validate_warns_on_a_malformed_delegated_yes(self):
        from aidd.workitems import delegated_yes

        good = "Merge\n\nDecided-by: agent:claude-code/aidd-team:delegate\nOn-behalf-of: Maya Lee <maya@users.noreply.github.com>\nDelegation: " + "b" * 40
        self.assertEqual(delegated_yes.trailer_problems(good), [])
        self.assertEqual(delegated_yes.trailer_problems("Fix the total"), [], "a commit with no delegation trailer is no concern")
        cases = {
            "a missing trailer": good.replace("Delegation: " + "b" * 40, ""),
            "a person as Decided-by": good.replace("agent:claude-code/aidd-team:delegate", "Maya"),
            "Approved-by beside it": good + "\nApproved-by: Maya Lee <maya@users.noreply.github.com>",
            "Agreed-by beside it": good + "\nAgreed-by: Maya Lee <maya@users.noreply.github.com>",
            "no address": good.replace(" <maya@users.noreply.github.com>", ""),
        }
        for name, message in cases.items():
            with self.subTest(name):
                self.assertTrue(delegated_yes.trailer_problems(message))
        spec = {"type": "spec", "id": "SPEC-4", "delegate_answer": "20261108T101500123Z-1a2b3c4d", "approved_by": "Maya Lee <m@x.org>"}
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            found = delegated_yes.spec_warnings(Path(d), "specs/SPEC-4.md", spec)
        self.assertEqual(len(found), 2, "approved_by beside it, and no accept on record")


class ReasonCodeTests(unittest.TestCase):
    def test_every_reason_code_has_a_meaning_and_a_next_step(self):
        schema = resources.load_json("delegate-check.schema.json")
        codes = schema["$defs"]["reason_code"]["enum"]
        self.assertEqual(sorted(codes), sorted(schema["x-reasons"]))
        for code, entry in schema["x-reasons"].items():
            with self.subTest(code):
                self.assertEqual(set(entry), {"reserved", "means", "next"})
                self.assertTrue(entry["means"].endswith(".") and entry["next"].endswith("."))

    def test_the_delegable_actions_are_known_actions_with_their_templates(self):
        data = resources.load_json("risks.json")
        delegable = data["delegation"]["actions"]
        self.assertEqual(sorted(delegable), ["git.merge", "git.push", "pr.merge", "spec.approve"])
        for action, entry in delegable.items():
            with self.subTest(action):
                self.assertIn(action, data["actions"])
                self.assertFalse(data["actions"][action].get("irreversible"), "`all` never covers an irreversible action")
                self.assertEqual("template" in entry, action != "spec.approve")
        for area in data["delegation"]["reserved_areas"]:
            self.assertIn(area, data["areas"])
        deploys = data["areas"]["infra"]["deploys_on_merge"]
        self.assertTrue(set(deploys) <= set(data["areas"]["infra"]["paths"]), "the deploy files are infra paths")

    def test_the_check_output_schema_is_valid_and_strict(self):
        schema = json.loads((ROOT / "schemas" / "delegate-check.schema.json").read_text(encoding="utf-8"))
        sample = {
            "schema_version": "1",
            "outcome": "defer",
            "reserved": True,
            "action": "deploy.run",
            "covers": {"head": "9c1e4a7"},
            "reasons": [{"code": "reserved-action", "reserved": True, "detail": "deploy.run is reserved"}],
            "trailers": [],
            "next": "Ask the person.",
        }
        self.assertEqual(json_schema.validate(sample, "delegate-check.schema.json"), [])
        self.assertTrue(json_schema.validate(dict(sample, reasons=[{"code": "made-up", "reserved": False, "detail": ""}]), "delegate-check.schema.json"))
        self.assertEqual(schema["$id"], "urn:aidd:1:delegate-check")


if __name__ == "__main__":
    unittest.main()
