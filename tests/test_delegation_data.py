"""The data of a standing delegation: the config block a parent can only narrow, the record types only aidd writes, the
rise to ask, and the check's reason codes, each with its meaning and its next step."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from helpers import ROOT

from aidd import config, records, risk
from aidd.cli import mcp_tools
from aidd.delegation import action_checks, policy
from aidd.kernel import json_schema, resources
from aidd.records import files

DELEGATION = """delegation:
  set_by: "Maya Lee <maya@users.noreply.github.com>"
  decides: {decides}
  review_due: "{review_due}"
"""


def load(child: str, parent: str | None = None) -> config.Config:
    files = {"preset.yaml": f'aidd_version: "1.0.0"\nprofile: solo\n{parent}'} if parent is not None else {}
    head = 'aidd_version: "1.0.0"\nprofile: solo\n' + ("extends: [{path: preset.yaml}]\n" if parent is not None else "")
    return config.load_text(head + child, read=files.get)


def block(decides: str = "[spec.approve, git.push, git.merge, pr.merge]", review_due: str = "2027-02-06", extra: str = "") -> str:
    return DELEGATION.format(decides=decides, review_due=review_due) + extra


class PresetTests(unittest.TestCase):
    def test_preset_cannot_widen(self):
        cases = {
            "a parent's shorter list narrows a child's full one": (block(), block("[spec.approve]"), ["spec.approve"], 1),
            "a child's action the parent leaves out is dropped": (block("[spec.approve, pr.merge]"), block("[spec.approve]"), ["spec.approve"], 1),
            "a parent's full list keeps the child's shorter one": (block("[git.push]"), block(), ["git.push"], 0),
        }
        for name, (child, parent, decides, warned) in cases.items():
            with self.subTest(name):
                cfg = load(child, parent)
                self.assertEqual(cfg.get("delegation", "decides"), decides)
                self.assertEqual(sum("delegation.decides" in w for w in cfg.warnings), warned)

    def test_a_decides_that_is_no_list_fails_the_load_where_it_is_found(self):
        """`decides` is a list of asks: a word such as `all` fails the load, in a parent as in the repository's own config."""
        with self.assertRaises(config.ConfigError) as parent:
            load(block(), block("all"))
        self.assertIn("preset.yaml", str(parent.exception))
        self.assertIn("expected array", str(parent.exception))
        with self.assertRaises(config.ConfigError) as own:
            load(block("all"))
        self.assertIn("expected array", str(own.exception))

    def test_a_parent_reserves_and_reviews_sooner(self):
        child = block(extra="  reserved: [git.push]\n")
        parent = block(review_due="2026-12-01", extra="  reserved: [pr.merge]\n")
        cfg = load(child, parent)
        self.assertEqual(cfg.get("delegation", "reserved"), ["git.push", "pr.merge"])
        self.assertEqual(cfg.get("delegation", "review_due"), "2026-12-01")

    def test_a_child_cannot_say_nothing_deploys_where_a_parent_defines_an_environment(self):
        """`environments` merge by name, so a child's `environments: []` removes no environment a parent defines, locked or not.
        A child adds an environment or overrides one by name, and only a lock stops the override."""
        env = "environments:\n  - name: production\n    branches: [main]\n"
        lock = "risks:\n  rules:\n    - {action: deploy.run, level: ask, environment: production, locked: true}\n"
        cases = {
            "locked": (env + lock, ["production"]),
            "not locked": (env, ["production"]),
        }
        for name, (parent, kept) in cases.items():
            with self.subTest(name):
                cfg = load("environments: []\n" + block(), parent)
                self.assertEqual([e["name"] for e in cfg.get("environments")], kept)

    def test_a_parent_alone_never_starts_a_delegation(self):
        cfg = load("", block())
        self.assertIsNone(cfg.get("delegation"))
        self.assertTrue(any("only this repository's own config" in w for w in cfg.warnings))

    def test_the_block_refuses_what_it_does_not_know(self):
        bad = {
            "an unknown action": block("[deploy.run]"),
            "a set_by with a backtick": block().replace("Maya Lee", "Maya `x` Lee"),
            "a set_by with no address": block().replace(" <maya@users.noreply.github.com>", ""),
            "a date that is no date": block(review_due="soon"),
            "a key that was dropped": block(extra="  to: delegate\n"),
        }
        for name, text in bad.items():
            with self.subTest(name), self.assertRaises(config.ConfigError):
                load(text)


class RiseTests(unittest.TestCase):
    def test_reserved_actions_rise_to_ask(self):
        """Under a delegation, every rule of a risen action rises to ask, whatever narrows it: a rule for one role, or one
        that names an environment, never keeps the level lower. A deploy to your own environment is the one cell that stays
        (`tests/test_delegation_own_environment.py`)."""
        own = "environments:\n  - {name: dev, branches: [dev], shared: false}\n"
        named = "risks:\n  rules:\n    - {action: deploy.run, environment: dev, level: report}\n"
        for_role = "risks:\n  rules:\n    - {action: migration.run.local, role: developer, level: allow}\n"
        cases = [
            # (config, action, narrowing, the level with no delegation)
            ("", "dependency.add", {}, "report"),
            ("", "migration.run.local", {}, "report"),
            (for_role, "migration.run.local", {"role": "developer"}, "allow"),
            (own + named, "deploy.run", {"environment": "dev"}, "report"),
        ]
        for extra, action, narrow, plain in cases:
            with self.subTest(action=action, **narrow):
                self.assertEqual(risk.level_of(risk.rule_set(load(extra)), action, **narrow)[0], plain)
                level, rule = risk.level_of(risk.rule_set(load(extra + block())), action, **narrow)
                self.assertEqual((level, rule.source if rule else None), ("ask", "delegation"))

    def test_the_rise_beats_a_parents_locked_lower_level(self):
        """Abuse cases: a parent's locked rule for a prefix (l1), for one environment (l2), or for every action (l3) keeps
        a level below ask. Under a delegation the reserved action still asks, because the rise only moves toward the
        person deciding."""
        own = "environments:\n  - {name: dev, branches: [dev], shared: false}\n"
        rules = "risks:\n  rules:\n    - {{action: {action}, level: {level}, locked: true{narrow}}}\n"
        cases = [
            # (case, the parent, the deploy it reads, the level with no delegation). A lock is a floor, so one below the
            # built-in level lowers nothing: l1 stays at the built-in ask, and l3 at the report of your own environment.
            ("l1", rules.format(action="deploy.*", level="report", narrow=""), {}, "ask"),
            ("l2", own + rules.format(action="deploy.run", level="report", narrow=", environment: dev"), {"environment": "dev"}, "report"),
            ("l3", own + rules.format(action="'*'", level="allow", narrow=""), {"environment": "dev"}, "report"),
        ]
        for case, parent, narrow, plain in cases:
            with self.subTest(case):
                self.assertEqual(risk.level_of(risk.rule_set(load("", parent)), "deploy.run", **narrow)[0], plain)
                delegated = risk.rule_set(load(block(), parent))
                self.assertEqual(risk.level_of(delegated, "deploy.run", **narrow)[0], "ask")
        line = risk.command_level(risk.rule_set(load(block(), cases[0][1])), "kubectl apply -f deploy.yaml", cwd=None)
        self.assertEqual(line["level"], "ask")

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
            "delegation_commit": "3f2a9c1e7b0d4c8a9e1f2b3c4d5e6f7a8b9c0d1e",
        }

    def test_records_add_refuses_delegate_types(self):
        for record_type in files.DELEGATION_TYPES:
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


class DelegateAcceptsTests(unittest.TestCase):
    """The delegate's own answers are one reader's answer (`records.delegate_answers`): `aidd validate`, the delegate check,
    the hook, and the digest count the same records, so a pulled one, or one under another name, counts in none."""

    HEAD = "9c1e4a7b2d3f4e5a6b7c8d9e0f1a2b3c4d5e6f70"
    DELEGATE = "agent:claude-code/aidd-team:delegate"
    # name: (what differs, who wrote it, whether it was pulled, whether it is an accept of SPEC-4's approval, whether the
    # digest and the hook read it as the delegate's accept of that tree and command)
    CASES = {
        "the delegate's accept": ({}, DELEGATE, False, True, True),
        "a pulled record": ({}, DELEGATE, True, False, False),
        "another writer": ({}, "agent:claude-code/claude-opus-5-5", False, False, False),
        "a defer": ({"outcome": "defer"}, DELEGATE, False, False, False),
        "another action": ({"action": "pr.merge"}, DELEGATE, False, False, True),
        "another Spec": ({"covers": {"spec": "SPEC-9", "head": HEAD}}, DELEGATE, False, False, True),
    }

    def test_validate_the_check_the_hook_and_the_digest_count_the_same_records(self):
        from aidd.delegation import answers, digest
        from aidd.workitems import delegated_yes

        for name, (change, by, pulled, counts, counts_here) in self.CASES.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
                (Path(d) / "a.txt").write_text("a\n", encoding="utf-8")
                subprocess.run(["git", "-C", d, "add", "a.txt"], check=True)
                message = ["-m", "A delegated change", "-m", "Delegation: " + "b" * 40]
                subprocess.run(["git", "-C", d, "-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-q", *message], check=True)
                tree = subprocess.run(["git", "-C", d, "rev-parse", "HEAD^{tree}"], check=True, capture_output=True, text=True).stdout.strip()
                data = {
                    "action": "spec.approve",
                    "covers": {"spec": "SPEC-4", "head": self.HEAD, "tree": tree, "command": "git merge --no-ff " + self.HEAD},
                    "outcome": "accept",
                    "reason": "ready",
                    "check": "20261108T101500123Z-1a2b3c4d",
                    "delegation_commit": "b" * 40,
                    **change,
                }
                data["covers"] = {"tree": tree, "command": "git merge --no-ff " + self.HEAD, **data["covers"]}
                with records.written_by_delegation():
                    record, _ = records.add_record("delegate_answer", data, by=by, cwd=d)
                if pulled:
                    (records.records_dir(d).parent / "records-pulled").write_text(record["id"] + "\n", encoding="utf-8")
                spec = {"type": "spec", "id": "SPEC-4", "delegate_answer": record["id"]}
                warned = bool(delegated_yes.spec_warnings(Path(d), "specs/SPEC-4.md", spec))
                approved = [head for _when, head in action_checks.approvals(SimpleNamespace(top=d, delegation={"decides": ["spec.approve"]}), "SPEC-4")]
                self.assertEqual((warned, approved), (not counts, [self.HEAD] if counts else []))
                self.assertEqual(digest.unrecorded(d, "main") == [], counts_here, "the digest names a delegated commit no delegate accepted")
                self.assertEqual("accept on" in digest.digest_text(d, "main"), counts_here, "the digest lists only the delegate's own answers")
                self.assertEqual(answers.accepted_here(d, data["action"], "git merge --no-ff " + self.HEAD, self.HEAD), counts_here)


class ReasonCodeTests(unittest.TestCase):
    def test_every_reason_code_has_a_meaning_and_a_next_step(self):
        codes = resources.load_json("delegate-check.schema.json")["$defs"]["reason_code"]["enum"]
        rows = policy.reasons()
        self.assertEqual(sorted(codes), sorted(rows))
        for code, entry in rows.items():
            with self.subTest(code):
                self.assertEqual(set(entry), {"severity", "title", "why", "next", "reserved"})
                self.assertTrue(entry["why"].endswith(".") and entry["next"]["what"].endswith("."))

    def test_the_delegable_actions_are_known_actions_with_their_templates(self):
        data = resources.load_json("risks.json")
        delegable = data["delegation"]["actions"]
        self.assertEqual(sorted(delegable), ["git.merge", "git.push", "pr.merge", "spec.approve"])
        for action, entry in delegable.items():
            with self.subTest(action):
                self.assertIn(action, data["actions"])
                self.assertFalse(data["actions"][action].get("irreversible"), "`undoable` never lists an irreversible action")
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
            "reasons": [{"code": "reserved_action", "reserved": True, "detail": "deploy.run is reserved"}],
            "trailers": [],
            "next": {"what": "Ask the person."},
        }
        self.assertEqual(json_schema.validate(sample, "delegate-check.schema.json"), [])
        self.assertTrue(json_schema.validate(dict(sample, reasons=[{"code": "made-up", "reserved": False, "detail": ""}]), "delegate-check.schema.json"))
        self.assertEqual(schema["$id"], "urn:aidd:1:delegate-check")

    def test_every_reason_code_fits_the_record_it_is_written_in(self):
        codes = resources.load_json("delegate-check.schema.json")["$defs"]["reason_code"]["enum"]
        problems = {}
        for code in codes:
            reasons = [{"code": code, "reserved": False, "detail": "d"}]
            data = {"outcome": "defer", "action": "git.merge", "covers": {"head": "9c1e4a7"}, "reasons": reasons}
            found = json_schema.validate(data, "records.json#/types/delegate_check/data")
            if found:
                problems[code] = found
        self.assertEqual(problems, {})


if __name__ == "__main__":
    unittest.main()
