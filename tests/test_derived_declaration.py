"""A change with no Change Request block, and a config edit that sets only preference keys.

The gate derives what a change with no block declares from facts it checks (the diff, the commit subjects, the
commit trailers, the one Spec the diff carries), and never gives it a lower route than the diff computes. A config
edit routes like a doc only when base and head, read with the same strict reader, differ in preference keys alone.
"""

import copy
import json
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts src on sys.path)

from aidd import gate
from aidd.config import baseline
from aidd.evals import examples
from aidd.gate import routing
from aidd.workitems import spec_file

ROOT = Path(__file__).resolve().parent.parent
TEAM = (ROOT / "examples" / "_configs" / "team.yaml").read_text(encoding="utf-8")


def minor_docs(body: str = "Fix a typo in the setup guide.") -> dict:
    ctx, _ = examples.load_example(ROOT / "examples" / "01-minor-docs")
    ctx = copy.deepcopy(ctx)
    ctx["change"]["body"] = body
    return ctx


def with_config_edit(ctx: dict, head: str) -> dict:
    ctx["files"].append({"path": ".aidd/config.yaml", "previous_path": None, "additions": 1, "deletions": 0})
    ctx["head_files"][".aidd/config.yaml"] = head
    return ctx


class DerivedDeclarationTests(unittest.TestCase):
    def test_no_block_takes_the_computed_route_and_records_it_as_derived(self):
        d = gate.decide(minor_docs())
        self.assertEqual(d.decision, "pass", d.codes())
        self.assertEqual((d.record["declaration"], d.record["route"], d.record["type"]), ("derived", "minor", "chore"))
        self.assertEqual(d.record["assisted_by"], ["claude-code/claude-opus-5-5"])

    def test_a_block_is_recorded_as_one(self):
        ctx, _ = examples.load_example(ROOT / "examples" / "01-minor-docs")
        self.assertEqual(gate.decide(ctx).record["declaration"], "block")

    def test_the_riskiest_named_type_wins_whatever_its_order(self):
        for messages in (["docs: a", "security: b"], ["security: b", "docs: a"]):
            self.assertEqual(routing.derived_type(messages), "security", messages)
        self.assertEqual(routing.derived_type(["infra: a", "fix: b"]), "infra")
        self.assertEqual(routing.derived_type(["fix(cart)!: a", "docs: b"]), "fix")
        self.assertEqual(routing.derived_type(["Update the guide", "wip: b"]), "chore")

    def test_an_infra_commit_raises_a_derived_change_to_normal_which_needs_a_spec(self):
        ctx = minor_docs()
        ctx["commits"][0]["message"] = "infra: move the queue\n\nAssisted-by: claude-code/claude-opus-5-5"
        d = gate.decide(ctx)
        self.assertEqual(d.codes(), ["fail spec.missing"])
        self.assertEqual(d.record["route"], "normal")

    def test_a_merge_commit_subject_names_no_type_but_its_trailer_counts(self):
        ctx = minor_docs()
        ctx["commits"].append(
            {"sha": "2" * 40, "author": "alice", "committer": "alice", "message": "security: x\n\nAssisted-by: other/agent", "merge": True, "verified": True}
        )
        d = gate.decide(ctx)
        self.assertEqual(d.record["type"], "chore")
        self.assertEqual(d.record["assisted_by"], ["claude-code/claude-opus-5-5", "other/agent"])

    def test_an_agent_co_author_alone_is_declared(self):
        ctx = minor_docs()
        ctx["commits"][0]["message"] = "fix: a typo\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
        d = gate.decide(ctx)
        self.assertEqual(d.decision, "pass", d.codes())
        self.assertEqual(d.record["assisted_by"], ["claude-opus-5.5"])

    def test_assisted_by_of_keeps_declared_trailers_and_drops_none(self):
        msgs = ["a\n\nAssisted-by: claude-code/x\nAssisted-by: none", "b\n\nAssisted-by: claude-code/x"]
        self.assertEqual(spec_file.assisted_by_of(msgs), ["claude-code/x"])
        self.assertEqual(spec_file.assisted_by_of(["a\n\nAssisted-by: none"]), [])

    def test_no_block_never_derives_emergency_or_standard(self):
        # No block never derives emergency or standard: those need facts only a person declares, or a configured class.
        for messages in (["fix: hot\n\nAssisted-by: none"], ["chore: x"]):
            ctx = minor_docs()
            ctx["commits"][0]["message"] = messages[0]
            self.assertIn(gate.decide(ctx).record["route"], ("minor", "normal", "major"))


class ConfigPreferenceTests(unittest.TestCase):
    def controls(self, head: str, base: str = TEAM) -> list[str]:
        return routing.config_controls_changed(base, head)

    def test_the_preference_list_is_purely_descriptive(self):
        self.assertEqual(baseline.baseline_data()["config_preference_keys"], ["goal", "locale", "mission"])

    def test_a_preference_edit_changes_no_control(self):
        self.assertEqual(self.controls(TEAM + 'mission: "Small shops get paid on time."\ngoal: "Pay out in a day."\nlocale: de\n'), [])
        self.assertEqual(self.controls(TEAM.replace("profile: team", "profile: team  # a comment")), [])
        self.assertEqual(self.controls(TEAM.replace("\n", "\r\n")), [])

    def test_every_other_change_is_a_control(self):
        for head, why in (
            (TEAM.replace("profile: team", "profile: solo"), "a control key"),
            (TEAM + 'Mission: "x"\n', "another case"),
            (TEAM + '"mіssion": "x"\n', "a lookalike letter"),
            (TEAM + "mission: [a, b]\n", "a preference set to a list"),
            (TEAM + "mission:\n  gates: x\n", "a preference set to a mapping"),
            (TEAM + 'mission: "' + "x" * 501 + '"\n', "a preference its schema refuses, which would break the merged config"),
            (TEAM + 'locale: "not a tag"\n', "a locale that is no BCP 47 tag"),
            (TEAM + "extends: [https://example.com/org.yaml]\n", "a parent config"),
            (TEAM + 'mission: &m "x"\ngoal: *m\n', "an anchor and an alias"),
            (TEAM + "profile: solo\n", "a key twice"),
            (TEAM + "---\nprofile: solo\n", "a second document"),
            (TEAM + "<<: {profile: solo}\n", "a merge key"),
            ("﻿" + TEAM, "a byte order mark"),
        ):
            self.assertTrue(self.controls(head), why)
        self.assertTrue(routing.config_controls_changed(None, TEAM), "a config added")
        self.assertTrue(routing.config_controls_changed(TEAM, None), "a config removed")
        self.assertTrue(routing.config_controls_changed("profile: [", TEAM), "a base that does not parse")

    def test_values_compare_by_type(self):
        base = TEAM + "emergency:\n  review_sla_days: 1\n"
        self.assertTrue(self.controls(base.replace("review_sla_days: 1", "review_sla_days: true"), base))
        self.assertTrue(self.controls(base.replace("review_sla_days: 1", "review_sla_days: 1.0"), base))

    def test_the_gate_leaves_protection_only_for_the_exact_config_path(self):
        ctx = with_config_edit(minor_docs(), TEAM + 'mission: "x"\n')
        self.assertEqual(gate.decide(ctx).codes(), ["warn route.config_preferences_only"])
        ctx = minor_docs()
        ctx["files"].append({"path": ".AIDD/config.yaml", "previous_path": None, "additions": 1, "deletions": 0})
        self.assertEqual(gate.decide(ctx).codes(), ["fail spec.missing"])
        ctx = minor_docs()
        ctx["files"].append({"path": ".aidd/other.yaml", "previous_path": None, "additions": 1, "deletions": 0})
        self.assertEqual(gate.decide(ctx).codes(), ["fail spec.missing"])

    def test_the_configs_own_protected_paths_still_hold(self):
        ctx = with_config_edit(minor_docs(), TEAM + 'protected_paths: [".aidd/config.yaml"]\nmission: "x"\n')
        ctx["base_config"] = TEAM + 'protected_paths: [".aidd/config.yaml"]\n'
        self.assertEqual(gate.decide(ctx).codes(), ["fail spec.missing", "warn route.config_preferences_only"])

    def test_a_control_edit_names_its_keys(self):
        ctx = with_config_edit(minor_docs(), TEAM.replace("profile: team", "profile: solo"))
        d = gate.decide(ctx)
        self.assertEqual(d.codes(), ["fail spec.missing"])
        self.assertIn(".aidd/config.yaml changes what checks read: profile", json.dumps(d.record["route_reasons"]))


if __name__ == "__main__":
    unittest.main()
